#include "CborRpc.h"

#include "Common.h"
#include "Ble.h"
#include "Compression.h"
#include "Menu.h"
#include "Remote.h"
#include "Storage.h"
#include "Themes.h"
#include "Utils.h"

#include <tinycbor.h>
#include <string.h>

//
// Ensure RemoteState has an encode buffer of at least the given size.
// Grows the buffer if needed (up to CBOR_RPC_MAX_FRAME + framing overhead).
// Returns nullptr on allocation failure.
//
static uint8_t *rpcEnsureEncodeBuffer(RemoteState *state, size_t minSize)
{
  const size_t maxSize = CBOR_RPC_MAX_FRAME + 256;
  if (!state || minSize > maxSize)
    return nullptr;

  if (state->rpcEncodeBufCap < minSize)
  {
    if (state->rpcEncodeBuf)
    {
      free(state->rpcEncodeBuf);
      state->rpcEncodeBuf = nullptr;
      state->rpcEncodeBufCap = 0;
    }

    // Allocate in PSRAM if available, fall back to heap
    uint8_t *buf = (uint8_t *)ps_malloc(minSize);
    if (!buf)
      buf = (uint8_t *)malloc(minSize);
    if (!buf)
      return nullptr;

    state->rpcEncodeBuf = buf;
    state->rpcEncodeBufCap = minSize;
  }

  return state->rpcEncodeBuf;
}

static bool cborRpcSendFrame(CborRpcWriter *writer, const uint8_t *data, size_t len)
{
  if (!writer || !writer->send_frame)
    return false;
  return writer->send_frame(writer->ctx, data, len);
}

static bool cborRpcSendError(CborRpcWriter *writer, int64_t id, int code, const char *message)
{
  uint8_t buffer[512];
  CborEncoder encoder;
  CborEncoder map;
  CborEncoder errorMap;

  cbor_encoder_init(&encoder, buffer, sizeof(buffer), 0);
  cbor_encoder_create_map(&encoder, &map, 3);

  cbor_encode_text_stringz(&map, "id");
  cbor_encode_int(&map, id);

  cbor_encode_text_stringz(&map, "error");
  cbor_encoder_create_map(&map, &errorMap, 2);
  cbor_encode_text_stringz(&errorMap, "code");
  cbor_encode_int(&errorMap, code);
  cbor_encode_text_stringz(&errorMap, "message");
  cbor_encode_text_stringz(&errorMap, message ? message : "error");
  cbor_encoder_close_container(&map, &errorMap);

  cbor_encoder_close_container(&encoder, &map);

  size_t len = cbor_encoder_get_buffer_size(&encoder, buffer);
  return cborRpcSendFrame(writer, buffer, len);
}

static bool cborRpcSendSimpleResult(CborRpcWriter *writer, int64_t id, const char *key, int64_t value)
{
  uint8_t buffer[512];
  CborEncoder encoder;
  CborEncoder map;
  CborEncoder resultMap;

  cbor_encoder_init(&encoder, buffer, sizeof(buffer), 0);
  cbor_encoder_create_map(&encoder, &map, 2);

  cbor_encode_text_stringz(&map, "id");
  cbor_encode_int(&map, id);

  cbor_encode_text_stringz(&map, "result");
  cbor_encoder_create_map(&map, &resultMap, 1);
  cbor_encode_text_stringz(&resultMap, key);
  cbor_encode_int(&resultMap, value);
  cbor_encoder_close_container(&map, &resultMap);

  cbor_encoder_close_container(&encoder, &map);

  size_t len = cbor_encoder_get_buffer_size(&encoder, buffer);
  return cborRpcSendFrame(writer, buffer, len);
}

static bool cborRpcSendBoolResult(CborRpcWriter *writer, int64_t id, const char *key, bool value)
{
  uint8_t buffer[512];
  CborEncoder encoder;
  CborEncoder map;
  CborEncoder resultMap;

  cbor_encoder_init(&encoder, buffer, sizeof(buffer), 0);
  cbor_encoder_create_map(&encoder, &map, 2);

  cbor_encode_text_stringz(&map, "id");
  cbor_encode_int(&map, id);

  cbor_encode_text_stringz(&map, "result");
  cbor_encoder_create_map(&map, &resultMap, 1);
  cbor_encode_text_stringz(&resultMap, key);
  cbor_encode_boolean(&resultMap, value);
  cbor_encoder_close_container(&map, &resultMap);

  cbor_encoder_close_container(&encoder, &map);

  size_t len = cbor_encoder_get_buffer_size(&encoder, buffer);
  return cborRpcSendFrame(writer, buffer, len);
}

static bool cborRpcSendStatusResult(CborRpcWriter *writer, int64_t id)
{
  uint8_t buffer[768];
  CborEncoder encoder;
  CborEncoder map;
  CborEncoder resultMap;

  cbor_encoder_init(&encoder, buffer, sizeof(buffer), 0);
  cbor_encoder_create_map(&encoder, &map, 2);

  cbor_encode_text_stringz(&map, "id");
  cbor_encode_int(&map, id);

  cbor_encode_text_stringz(&map, "result");
  cbor_encoder_create_map(&map, &resultMap, 5);
  cbor_encode_text_stringz(&resultMap, "band");
  cbor_encode_text_stringz(&resultMap, getCurrentBand()->bandName);
  cbor_encode_text_stringz(&resultMap, "mode");
  cbor_encode_text_stringz(&resultMap, bandModeDesc[currentMode]);
  cbor_encode_text_stringz(&resultMap, "frequency");
  cbor_encode_uint(&resultMap, currentFrequency);
  cbor_encode_text_stringz(&resultMap, "bfo");
  cbor_encode_int(&resultMap, currentBFO);
  cbor_encode_text_stringz(&resultMap, "volume");
  cbor_encode_uint(&resultMap, volume);
  cbor_encoder_close_container(&map, &resultMap);

  cbor_encoder_close_container(&encoder, &map);

  size_t len = cbor_encoder_get_buffer_size(&encoder, buffer);
  return cborRpcSendFrame(writer, buffer, len);
}

static bool cborRpcSendCapabilitiesResult(CborRpcWriter *writer, int64_t id)
{
  uint8_t buffer[1024];
  CborEncoder encoder;
  CborEncoder map;
  CborEncoder resultMap;
  CborEncoder formatsArray;
  CborEncoder transportsArray;

  cbor_encoder_init(&encoder, buffer, sizeof(buffer), 0);
  cbor_encoder_create_map(&encoder, &map, 2);

  cbor_encode_text_stringz(&map, "id");
  cbor_encode_int(&map, id);

  cbor_encode_text_stringz(&map, "result");
  cbor_encoder_create_map(&map, &resultMap, 5);

  cbor_encode_text_stringz(&resultMap, "rpc_version");
  cbor_encode_uint(&resultMap, 1);
  cbor_encode_text_stringz(&resultMap, "max_frame");
  cbor_encode_uint(&resultMap, CBOR_RPC_MAX_FRAME);
  cbor_encode_text_stringz(&resultMap, "firmware");
  cbor_encode_uint(&resultMap, VER_APP);

  cbor_encode_text_stringz(&resultMap, "formats");
  cbor_encoder_create_array(&resultMap, &formatsArray, 2);
  cbor_encode_text_stringz(&formatsArray, "binary");
  cbor_encode_text_stringz(&formatsArray, "rle");
  cbor_encoder_close_container(&resultMap, &formatsArray);

  cbor_encode_text_stringz(&resultMap, "transports");
  cbor_encoder_create_array(&resultMap, &transportsArray, 3);
  cbor_encode_text_stringz(&transportsArray, "serial");
  cbor_encode_text_stringz(&transportsArray, "ble");
  cbor_encode_text_stringz(&transportsArray, "ws");
  cbor_encoder_close_container(&resultMap, &transportsArray);

  cbor_encoder_close_container(&map, &resultMap);
  cbor_encoder_close_container(&encoder, &map);

  size_t len = cbor_encoder_get_buffer_size(&encoder, buffer);
  return cborRpcSendFrame(writer, buffer, len);
}

static bool cborRpcSendCaptureResult(CborRpcWriter *writer, int64_t id, uint32_t streamId, const char *format, uint16_t width, uint16_t height)
{
  uint8_t buffer[512];
  CborEncoder encoder;
  CborEncoder map;
  CborEncoder resultMap;

  cbor_encoder_init(&encoder, buffer, sizeof(buffer), 0);
  cbor_encoder_create_map(&encoder, &map, 2);

  cbor_encode_text_stringz(&map, "id");
  cbor_encode_int(&map, id);

  cbor_encode_text_stringz(&map, "result");
  cbor_encoder_create_map(&map, &resultMap, 4);
  cbor_encode_text_stringz(&resultMap, "stream_id");
  cbor_encode_uint(&resultMap, streamId);
  cbor_encode_text_stringz(&resultMap, "format");
  cbor_encode_text_stringz(&resultMap, format);
  cbor_encode_text_stringz(&resultMap, "width");
  cbor_encode_uint(&resultMap, width);
  cbor_encode_text_stringz(&resultMap, "height");
  cbor_encode_uint(&resultMap, height);
  cbor_encoder_close_container(&map, &resultMap);

  cbor_encoder_close_container(&encoder, &map);

  size_t len = cbor_encoder_get_buffer_size(&encoder, buffer);
  return cborRpcSendFrame(writer, buffer, len);
}

class RpcChunkStream : public Stream
{
public:
  RpcChunkStream(CborRpcWriter *writer, RemoteState *state, uint32_t streamId)
      : writer(writer), state(state), streamId(streamId) {}

  size_t write(uint8_t c) override
  {
    return write(&c, 1);
  }

  size_t write(const uint8_t *buffer, size_t size) override
  {
    size_t remaining = size;
    const uint8_t *ptr = buffer;

    while (remaining > 0)
    {
      size_t space = sizeof(chunk) - chunkSize;
      size_t toCopy = remaining < space ? remaining : space;
      memcpy(chunk + chunkSize, ptr, toCopy);
      chunkSize += toCopy;
      ptr += toCopy;
      remaining -= toCopy;

      if (chunkSize == sizeof(chunk))
      {
        if (!sendChunk())
          return size - remaining;
      }
    }

    return size;
  }

  int available() override { return 0; }
  int read() override { return -1; }
  int peek() override { return -1; }
  void flush() override
  {
    sendChunk();
    sendDone();
  }

private:
  bool sendChunk()
  {
    if (chunkSize == 0)
      return true;

    uint8_t buffer[2048];
    CborEncoder encoder;
    CborEncoder map;
    CborEncoder paramsMap;

    cbor_encoder_init(&encoder, buffer, sizeof(buffer), 0);
    cbor_encoder_create_map(&encoder, &map, 4);
    cbor_encode_text_stringz(&map, "type");
    cbor_encode_text_stringz(&map, "event");
    cbor_encode_text_stringz(&map, "event");
    cbor_encode_text_stringz(&map, "screen.chunk");
    cbor_encode_text_stringz(&map, "seq");
    cbor_encode_uint(&map, state->rpcEventSeq++);
    cbor_encode_text_stringz(&map, "params");

    cbor_encoder_create_map(&map, &paramsMap, 3);
    cbor_encode_text_stringz(&paramsMap, "stream_id");
    cbor_encode_uint(&paramsMap, streamId);
    cbor_encode_text_stringz(&paramsMap, "offset");
    cbor_encode_uint(&paramsMap, offset);
    cbor_encode_text_stringz(&paramsMap, "data");
    cbor_encode_byte_string(&paramsMap, chunk, chunkSize);
    cbor_encoder_close_container(&map, &paramsMap);

    cbor_encoder_close_container(&encoder, &map);

    size_t len = cbor_encoder_get_buffer_size(&encoder, buffer);
    bool ok = cborRpcSendFrame(writer, buffer, len);
    offset += chunkSize;
    chunkSize = 0;
    return ok;
  }

  bool sendDone()
  {
    uint8_t buffer[512];
    CborEncoder encoder;
    CborEncoder map;
    CborEncoder paramsMap;

    cbor_encoder_init(&encoder, buffer, sizeof(buffer), 0);
    cbor_encoder_create_map(&encoder, &map, 4);
    cbor_encode_text_stringz(&map, "type");
    cbor_encode_text_stringz(&map, "event");
    cbor_encode_text_stringz(&map, "event");
    cbor_encode_text_stringz(&map, "screen.done");
    cbor_encode_text_stringz(&map, "seq");
    cbor_encode_uint(&map, state->rpcEventSeq++);
    cbor_encode_text_stringz(&map, "params");

    cbor_encoder_create_map(&map, &paramsMap, 2);
    cbor_encode_text_stringz(&paramsMap, "stream_id");
    cbor_encode_uint(&paramsMap, streamId);
    cbor_encode_text_stringz(&paramsMap, "bytes");
    cbor_encode_uint(&paramsMap, offset);
    cbor_encoder_close_container(&map, &paramsMap);

    cbor_encoder_close_container(&encoder, &map);

    size_t len = cbor_encoder_get_buffer_size(&encoder, buffer);
    return cborRpcSendFrame(writer, buffer, len);
  }

  CborRpcWriter *writer = nullptr;
  RemoteState *state = nullptr;
  uint32_t streamId = 0;
  uint32_t offset = 0;
  uint8_t chunk[512];
  size_t chunkSize = 0;
};

bool cborRpcConsumeStream(Stream *stream, RemoteState *state, CborRpcWriter *writer)
{
  bool handled = false;
  while (stream->available())
  {
    uint8_t byte = (uint8_t)stream->read();

    if (state->rpcExpected == 0)
    {
      state->rpcHeader[state->rpcHeaderRead++] = byte;
      if (state->rpcHeaderRead == sizeof(state->rpcHeader))
      {
        uint32_t len = ((uint32_t)state->rpcHeader[0] << 24) |
                       ((uint32_t)state->rpcHeader[1] << 16) |
                       ((uint32_t)state->rpcHeader[2] << 8) |
                       (uint32_t)state->rpcHeader[3];
        state->rpcHeaderRead = 0;
        state->rpcExpected = len;
        state->rpcRead = 0;
        if (len == 0 || len > CBOR_RPC_MAX_FRAME)
        {
          state->rpcExpected = 0;
          state->rpcRead = 0;
        }
      }
      continue;
    }

    if (state->rpcRead < CBOR_RPC_MAX_FRAME)
    {
      state->rpcBuf[state->rpcRead++] = byte;
    }

    if (state->rpcRead >= state->rpcExpected && state->rpcExpected > 0)
    {
      cborRpcHandleFrame(state->rpcBuf, state->rpcExpected, writer, state);
      state->rpcExpected = 0;
      state->rpcRead = 0;
      handled = true;
    }
  }

  return handled;
}

bool cborRpcSendStatsEvent(CborRpcWriter *writer, RemoteState *state)
{
  // Use persistent encode buffer for frequently-sent stats events
  const size_t bufSize = 1024;
  uint8_t *buffer = rpcEnsureEncodeBuffer(state, bufSize);
  if (!buffer)
    return false;

  CborEncoder encoder;
  CborEncoder map;
  CborEncoder paramsMap;

  cbor_encoder_init(&encoder, buffer, bufSize, 0);
  cbor_encoder_create_map(&encoder, &map, 4);

  cbor_encode_text_stringz(&map, "type");
  cbor_encode_text_stringz(&map, "event");
  cbor_encode_text_stringz(&map, "event");
  cbor_encode_text_stringz(&map, "stats");
  cbor_encode_text_stringz(&map, "seq");
  cbor_encode_uint(&map, state->rpcEventSeq++);
  cbor_encode_text_stringz(&map, "params");
  cbor_encoder_create_map(&map, &paramsMap, 15);

  float remoteVoltage = batteryMonitor();
  rx.getCurrentReceivedSignalQuality();
  uint8_t remoteRssi = rx.getCurrentRSSI();
  uint8_t remoteSnr = rx.getCurrentSNR();
  rx.getFrequency();
  uint16_t tuningCapacitor = rx.getAntennaTuningCapacitor();

  cbor_encode_text_stringz(&paramsMap, "version");
  cbor_encode_uint(&paramsMap, VER_APP);
  cbor_encode_text_stringz(&paramsMap, "frequency");
  cbor_encode_uint(&paramsMap, currentFrequency);
  cbor_encode_text_stringz(&paramsMap, "bfo");
  cbor_encode_int(&paramsMap, currentBFO);
  cbor_encode_text_stringz(&paramsMap, "cal");
  cbor_encode_int(&paramsMap,
                  (currentMode == USB) ? getCurrentBand()->usbCal : (currentMode == LSB) ? getCurrentBand()->lsbCal
                                                                                         : 0);
  cbor_encode_text_stringz(&paramsMap, "band");
  cbor_encode_text_stringz(&paramsMap, getCurrentBand()->bandName);
  cbor_encode_text_stringz(&paramsMap, "mode");
  cbor_encode_text_stringz(&paramsMap, bandModeDesc[currentMode]);
  cbor_encode_text_stringz(&paramsMap, "step");
  cbor_encode_text_stringz(&paramsMap, getCurrentStep()->desc);
  cbor_encode_text_stringz(&paramsMap, "bandwidth");
  cbor_encode_text_stringz(&paramsMap, getCurrentBandwidth()->desc);
  cbor_encode_text_stringz(&paramsMap, "agc");
  cbor_encode_uint(&paramsMap, agcIdx);
  cbor_encode_text_stringz(&paramsMap, "volume");
  cbor_encode_uint(&paramsMap, volume);
  cbor_encode_text_stringz(&paramsMap, "rssi");
  cbor_encode_uint(&paramsMap, remoteRssi);
  cbor_encode_text_stringz(&paramsMap, "snr");
  cbor_encode_uint(&paramsMap, remoteSnr);
  cbor_encode_text_stringz(&paramsMap, "cap");
  cbor_encode_uint(&paramsMap, tuningCapacitor);
  cbor_encode_text_stringz(&paramsMap, "voltage");
  cbor_encode_double(&paramsMap, (double)remoteVoltage);
  cbor_encode_text_stringz(&paramsMap, "seq");
  cbor_encode_uint(&paramsMap, state->remoteSeqnum++);

  cbor_encoder_close_container(&map, &paramsMap);
  cbor_encoder_close_container(&encoder, &map);

  size_t len = cbor_encoder_get_buffer_size(&encoder, buffer);
  return cborRpcSendFrame(writer, buffer, len);
}

static bool cborRpcSendEnumResult(CborRpcWriter *writer, int64_t id, int index, const char *name, int count)
{
  uint8_t buffer[512];
  CborEncoder encoder;
  CborEncoder map;
  CborEncoder resultMap;

  cbor_encoder_init(&encoder, buffer, sizeof(buffer), 0);
  cbor_encoder_create_map(&encoder, &map, 2);

  cbor_encode_text_stringz(&map, "id");
  cbor_encode_int(&map, id);

  cbor_encode_text_stringz(&map, "result");
  cbor_encoder_create_map(&map, &resultMap, 3);
  cbor_encode_text_stringz(&resultMap, "index");
  cbor_encode_int(&resultMap, index);
  cbor_encode_text_stringz(&resultMap, "name");
  cbor_encode_text_stringz(&resultMap, name);
  cbor_encode_text_stringz(&resultMap, "count");
  cbor_encode_int(&resultMap, count);
  cbor_encoder_close_container(&map, &resultMap);

  cbor_encoder_close_container(&encoder, &map);

  size_t len = cbor_encoder_get_buffer_size(&encoder, buffer);
  return cborRpcSendFrame(writer, buffer, len);
}

static bool cborRpcReadBool(CborValue *value, bool *out)
{
  if (!cbor_value_is_boolean(value))
    return false;
  return cbor_value_get_boolean(value, out) == CborNoError;
}

static bool cborRpcReadText(CborValue *value, char *out, size_t outLen)
{
  size_t len = outLen;
  if (!cbor_value_is_text_string(value))
    return false;
  CborError err = cbor_value_copy_text_string(value, out, &len, nullptr);
  return err == CborNoError;
}

static bool cborRpcReadInt(CborValue *value, int64_t *out)
{
  if (!cbor_value_is_integer(value))
    return false;
  return cbor_value_get_int64(value, out) == CborNoError;
}

static bool cborRpcReadTextOrInt(CborValue *value, char *textOut, size_t textLen, int64_t *intOut, bool *isText)
{
  if (cbor_value_is_text_string(value))
  {
    if (isText)
      *isText = true;
    return cborRpcReadText(value, textOut, textLen);
  }
  if (cbor_value_is_integer(value))
  {
    if (isText)
      *isText = false;
    return cborRpcReadInt(value, intOut);
  }
  return false;
}

bool cborRpcHandleFrame(const uint8_t *frame, size_t len, CborRpcWriter *writer, RemoteState *state)
{
  CborParser parser;
  CborValue root;
  CborError err = cbor_parser_init(frame, len, 0, &parser, &root);
  if (err != CborNoError || !cbor_value_is_map(&root))
  {
    return false;
  }

  CborValue methodVal;
  CborValue idVal;
  CborValue paramsVal;
  bool hasParams = false;
  char method[32] = {0};
  bool hasId = false;
  int64_t id = 0;

  if (cbor_value_map_find_value(&root, "method", &methodVal) == CborNoError)
  {
    cborRpcReadText(&methodVal, method, sizeof(method));
  }

  if (cbor_value_map_find_value(&root, "id", &idVal) == CborNoError)
  {
    if (cborRpcReadInt(&idVal, &id))
      hasId = true;
  }

  if (cbor_value_map_find_value(&root, "params", &paramsVal) == CborNoError)
  {
    hasParams = true;
  }

  if (method[0] == '\0')
  {
    if (hasId)
      cborRpcSendError(writer, id, -32600, "missing method");
    return false;
  }

  if (strcmp(method, "volume.set") == 0)
  {
    int64_t value = volume;
    CborValue val;
    if (hasParams && cbor_value_is_map(&paramsVal) && cbor_value_map_find_value(&paramsVal, "value", &val) == CborNoError)
    {
      cborRpcReadInt(&val, &value);
    }
    if (value < 0)
      value = 0;
    if (value > 63)
      value = 63;
    doVolume((int16_t)(value - volume));
    if (hasId)
      cborRpcSendSimpleResult(writer, id, "volume", volume);
    return true;
  }

  if (strcmp(method, "volume.up") == 0)
  {
    doVolume(1);
    prefsRequestSave(SAVE_SETTINGS);
    if (hasId)
      cborRpcSendStatusResult(writer, id);
    return true;
  }

  if (strcmp(method, "volume.down") == 0)
  {
    doVolume(-1);
    prefsRequestSave(SAVE_SETTINGS);
    if (hasId)
      cborRpcSendStatusResult(writer, id);
    return true;
  }

  if (strcmp(method, "volume.get") == 0)
  {
    if (hasId)
      cborRpcSendSimpleResult(writer, id, "volume", volume);
    return true;
  }

  if (strcmp(method, "capabilities.get") == 0)
  {
    if (hasId)
      cborRpcSendCapabilitiesResult(writer, id);
    return true;
  }

  if (strcmp(method, "band.up") == 0)
  {
    doBand(1);
    prefsRequestSave(SAVE_CUR_BAND);
    if (hasId)
      cborRpcSendStatusResult(writer, id);
    return true;
  }

  if (strcmp(method, "band.down") == 0)
  {
    doBand(-1);
    prefsRequestSave(SAVE_CUR_BAND);
    if (hasId)
      cborRpcSendStatusResult(writer, id);
    return true;
  }

  if (strcmp(method, "mode.up") == 0)
  {
    doMode(1);
    prefsRequestSave(SAVE_CUR_BAND);
    if (hasId)
      cborRpcSendStatusResult(writer, id);
    return true;
  }

  if (strcmp(method, "mode.down") == 0)
  {
    doMode(-1);
    prefsRequestSave(SAVE_CUR_BAND);
    if (hasId)
      cborRpcSendStatusResult(writer, id);
    return true;
  }

  if (strcmp(method, "step.up") == 0)
  {
    doStep(1);
    prefsRequestSave(SAVE_CUR_BAND);
    if (hasId)
      cborRpcSendStatusResult(writer, id);
    return true;
  }

  if (strcmp(method, "step.down") == 0)
  {
    doStep(-1);
    prefsRequestSave(SAVE_CUR_BAND);
    if (hasId)
      cborRpcSendStatusResult(writer, id);
    return true;
  }

  if (strcmp(method, "bandwidth.up") == 0)
  {
    doBandwidth(1);
    prefsRequestSave(SAVE_CUR_BAND);
    if (hasId)
      cborRpcSendStatusResult(writer, id);
    return true;
  }

  if (strcmp(method, "bandwidth.down") == 0)
  {
    doBandwidth(-1);
    prefsRequestSave(SAVE_CUR_BAND);
    if (hasId)
      cborRpcSendStatusResult(writer, id);
    return true;
  }

  if (strcmp(method, "agc.up") == 0)
  {
    doAgc(1);
    prefsRequestSave(SAVE_SETTINGS);
    if (hasId)
      cborRpcSendStatusResult(writer, id);
    return true;
  }

  if (strcmp(method, "agc.down") == 0)
  {
    doAgc(-1);
    prefsRequestSave(SAVE_SETTINGS);
    if (hasId)
      cborRpcSendStatusResult(writer, id);
    return true;
  }

  if (strcmp(method, "backlight.up") == 0)
  {
    doBrt(1);
    prefsRequestSave(SAVE_SETTINGS);
    if (hasId)
      cborRpcSendStatusResult(writer, id);
    return true;
  }

  if (strcmp(method, "backlight.down") == 0)
  {
    doBrt(-1);
    prefsRequestSave(SAVE_SETTINGS);
    if (hasId)
      cborRpcSendStatusResult(writer, id);
    return true;
  }

  if (strcmp(method, "cal.up") == 0)
  {
    doCal(1);
    prefsRequestSave(SAVE_CUR_BAND);
    if (hasId)
      cborRpcSendStatusResult(writer, id);
    return true;
  }

  if (strcmp(method, "cal.down") == 0)
  {
    doCal(-1);
    prefsRequestSave(SAVE_CUR_BAND);
    if (hasId)
      cborRpcSendStatusResult(writer, id);
    return true;
  }

  if (strcmp(method, "sleep.on") == 0)
  {
    sleepOn(true);
    if (hasId)
      cborRpcSendBoolResult(writer, id, "sleep", true);
    return true;
  }

  if (strcmp(method, "sleep.off") == 0)
  {
    sleepOn(false);
    if (hasId)
      cborRpcSendBoolResult(writer, id, "sleep", false);
    return true;
  }

  if (strcmp(method, "status.get") == 0)
  {
    if (hasId)
      cborRpcSendStatusResult(writer, id);
    return true;
  }

  if (strcmp(method, "memory.list") == 0)
  {
    if (!hasId)
      return false;
    uint8_t buffer[2048];
    CborEncoder encoder;
    CborEncoder map;
    CborEncoder resultMap;
    CborEncoder entries;

    cbor_encoder_init(&encoder, buffer, sizeof(buffer), 0);
    cbor_encoder_create_map(&encoder, &map, 2);
    cbor_encode_text_stringz(&map, "id");
    cbor_encode_int(&map, id);
    cbor_encode_text_stringz(&map, "result");
    cbor_encoder_create_map(&map, &resultMap, 1);
    cbor_encode_text_stringz(&resultMap, "memories");
    cbor_encoder_create_array(&resultMap, &entries, CborIndefiniteLength);

    for (uint8_t i = 0; i < getTotalMemories(); i++)
    {
      if (!memories[i].freq)
        continue;
      CborEncoder entry;
      cbor_encoder_create_map(&entries, &entry, 5);
      cbor_encode_text_stringz(&entry, "slot");
      cbor_encode_uint(&entry, i + 1);
      cbor_encode_text_stringz(&entry, "band");
      cbor_encode_text_stringz(&entry, bands[memories[i].band].bandName);
      cbor_encode_text_stringz(&entry, "mode");
      cbor_encode_text_stringz(&entry, bandModeDesc[memories[i].mode]);
      cbor_encode_text_stringz(&entry, "freq_hz");
      cbor_encode_uint(&entry, memories[i].freq);
      cbor_encode_text_stringz(&entry, "name");
      cbor_encode_text_stringz(&entry, memories[i].name);
      cbor_encoder_close_container(&entries, &entry);
    }

    cbor_encoder_close_container(&resultMap, &entries);
    cbor_encoder_close_container(&map, &resultMap);
    cbor_encoder_close_container(&encoder, &map);

    size_t len = cbor_encoder_get_buffer_size(&encoder, buffer);
    return cborRpcSendFrame(writer, buffer, len);
  }

  if (strcmp(method, "memory.set") == 0)
  {
    if (!hasId)
      return false;

    int64_t slot = 0;
    int64_t freq_hz = 0;
    int64_t modeIndex = currentMode;
    int64_t bandIndex = -1;
    char bandName[16] = {0};
    bool bandIsText = false;
    CborValue val;

    if (!hasParams || !cbor_value_is_map(&paramsVal))
    {
      return cborRpcSendError(writer, id, -32602, "missing params");
    }

    if (cbor_value_map_find_value(&paramsVal, "slot", &val) == CborNoError)
    {
      cborRpcReadInt(&val, &slot);
    }
    if (slot < 1 || slot > getTotalMemories())
    {
      return cborRpcSendError(writer, id, -32602, "invalid slot");
    }

    if (cbor_value_map_find_value(&paramsVal, "freq_hz", &val) == CborNoError)
    {
      cborRpcReadInt(&val, &freq_hz);
    }

    if (cbor_value_map_find_value(&paramsVal, "mode", &val) == CborNoError)
    {
      cborRpcReadInt(&val, &modeIndex);
    }

    if (cbor_value_map_find_value(&paramsVal, "band", &val) == CborNoError)
    {
      cborRpcReadTextOrInt(&val, bandName, sizeof(bandName), &bandIndex, &bandIsText);
    }

    Memory mem;
    memset(&mem, 0, sizeof(mem));
    mem.freq = (uint32_t)freq_hz;
    mem.mode = (uint8_t)modeIndex;
    mem.band = 0xFF;

    if (freq_hz == 0)
    {
      memories[slot - 1] = mem;
      prefsRequestSave(SAVE_MEMORIES);
      return cborRpcSendSimpleResult(writer, id, "slot", slot);
    }

    if (bandIsText && bandName[0] != '\0')
    {
      for (int i = 0; i < getTotalBands(); i++)
      {
        if (strcmp(bands[i].bandName, bandName) == 0)
        {
          mem.band = i;
          break;
        }
      }
    }
    else if (bandIndex >= 0 && bandIndex < getTotalBands())
    {
      mem.band = (uint8_t)bandIndex;
    }
    else
    {
      for (int i = 0; i < getTotalBands(); i++)
      {
        if (isMemoryInBand(&bands[i], &mem))
        {
          mem.band = i;
          break;
        }
      }
    }

    if (mem.band == 0xFF)
    {
      return cborRpcSendError(writer, id, -32602, "invalid band");
    }

    if (!isMemoryInBand(&bands[mem.band], &mem))
    {
      return cborRpcSendError(writer, id, -32602, "invalid frequency");
    }

    memories[slot - 1] = mem;
    prefsRequestSave(SAVE_MEMORIES);
    return cborRpcSendSimpleResult(writer, id, "slot", slot);
  }

  // --- settings.get: bulk query returning all settings ---
  if (strcmp(method, "settings.get") == 0)
  {
    if (!hasId)
      return true;

    // Use persistent encode buffer for large settings response
    size_t bufSize = 4096;
    uint8_t *buffer = rpcEnsureEncodeBuffer(state, bufSize);
    if (!buffer)
      return cborRpcSendError(writer, id, -32603, "out of memory");

    CborEncoder encoder;
    CborEncoder map;
    CborEncoder resultMap;
    CborEncoder nested;

    cbor_encoder_init(&encoder, buffer, bufSize, 0);
    cbor_encoder_create_map(&encoder, &map, 2);
    cbor_encode_text_stringz(&map, "id");
    cbor_encode_int(&map, id);
    cbor_encode_text_stringz(&map, "result");
    cbor_encoder_create_map(&map, &resultMap, CborIndefiniteLength);

    // Simple values
    cbor_encode_text_stringz(&resultMap, "volume");
    cbor_encode_uint(&resultMap, volume);
    cbor_encode_text_stringz(&resultMap, "frequency");
    cbor_encode_uint(&resultMap, currentFrequency);
    cbor_encode_text_stringz(&resultMap, "bfo");
    cbor_encode_int(&resultMap, currentBFO);
    cbor_encode_text_stringz(&resultMap, "squelch");
    cbor_encode_uint(&resultMap, currentSquelch);
    cbor_encode_text_stringz(&resultMap, "brightness");
    cbor_encode_uint(&resultMap, currentBrt);
    cbor_encode_text_stringz(&resultMap, "sleep_timeout");
    cbor_encode_uint(&resultMap, currentSleep);
    cbor_encode_text_stringz(&resultMap, "zoom_menu");
    cbor_encode_boolean(&resultMap, zoomMenu);
    cbor_encode_text_stringz(&resultMap, "scroll_direction");
    cbor_encode_int(&resultMap, scrollDirection);

    // Band
    cbor_encode_text_stringz(&resultMap, "band");
    cbor_encoder_create_map(&resultMap, &nested, 3);
    cbor_encode_text_stringz(&nested, "index");
    cbor_encode_uint(&nested, bandIdx);
    cbor_encode_text_stringz(&nested, "name");
    cbor_encode_text_stringz(&nested, getCurrentBand()->bandName);
    cbor_encode_text_stringz(&nested, "count");
    cbor_encode_uint(&nested, getTotalBands());
    cbor_encoder_close_container(&resultMap, &nested);

    // Mode
    cbor_encode_text_stringz(&resultMap, "mode");
    cbor_encoder_create_map(&resultMap, &nested, 3);
    cbor_encode_text_stringz(&nested, "index");
    cbor_encode_uint(&nested, currentMode);
    cbor_encode_text_stringz(&nested, "name");
    cbor_encode_text_stringz(&nested, bandModeDesc[currentMode]);
    cbor_encode_text_stringz(&nested, "count");
    cbor_encode_uint(&nested, getTotalModes());
    cbor_encoder_close_container(&resultMap, &nested);

    // Step
    cbor_encode_text_stringz(&resultMap, "step");
    cbor_encoder_create_map(&resultMap, &nested, 3);
    cbor_encode_text_stringz(&nested, "index");
    cbor_encode_uint(&nested, getCurrentBand()->currentStepIdx);
    cbor_encode_text_stringz(&nested, "name");
    cbor_encode_text_stringz(&nested, getCurrentStep()->desc);
    cbor_encode_text_stringz(&nested, "count");
    cbor_encode_uint(&nested, getTotalSteps());
    cbor_encoder_close_container(&resultMap, &nested);

    // Bandwidth
    cbor_encode_text_stringz(&resultMap, "bandwidth");
    cbor_encoder_create_map(&resultMap, &nested, 3);
    cbor_encode_text_stringz(&nested, "index");
    cbor_encode_uint(&nested, getCurrentBand()->bandwidthIdx);
    cbor_encode_text_stringz(&nested, "name");
    cbor_encode_text_stringz(&nested, getCurrentBandwidth()->desc);
    cbor_encode_text_stringz(&nested, "count");
    cbor_encode_uint(&nested, getTotalBandwidths());
    cbor_encoder_close_container(&resultMap, &nested);

    // AGC
    cbor_encode_text_stringz(&resultMap, "agc");
    cbor_encoder_create_map(&resultMap, &nested, 2);
    cbor_encode_text_stringz(&nested, "index");
    cbor_encode_uint(&nested, agcIdx);
    cbor_encode_text_stringz(&nested, "max");
    cbor_encode_uint(&nested, (currentMode == FM) ? 27 : isSSB() ? 1
                                                                 : 37);
    cbor_encoder_close_container(&resultMap, &nested);

    // Softmute
    cbor_encode_text_stringz(&resultMap, "softmute");
    cbor_encoder_create_map(&resultMap, &nested, 2);
    cbor_encode_text_stringz(&nested, "am");
    cbor_encode_uint(&nested, AmSoftMuteIdx);
    cbor_encode_text_stringz(&nested, "ssb");
    cbor_encode_uint(&nested, SsbSoftMuteIdx);
    cbor_encoder_close_container(&resultMap, &nested);

    // AVC
    cbor_encode_text_stringz(&resultMap, "avc");
    cbor_encoder_create_map(&resultMap, &nested, 2);
    cbor_encode_text_stringz(&nested, "am");
    cbor_encode_uint(&nested, AmAvcIdx);
    cbor_encode_text_stringz(&nested, "ssb");
    cbor_encode_uint(&nested, SsbAvcIdx);
    cbor_encoder_close_container(&resultMap, &nested);

    // Theme
    cbor_encode_text_stringz(&resultMap, "theme");
    cbor_encoder_create_map(&resultMap, &nested, 3);
    cbor_encode_text_stringz(&nested, "index");
    cbor_encode_uint(&nested, themeIdx);
    cbor_encode_text_stringz(&nested, "name");
    cbor_encode_text_stringz(&nested, theme[themeIdx].name);
    cbor_encode_text_stringz(&nested, "count");
    cbor_encode_uint(&nested, getTotalThemes());
    cbor_encoder_close_container(&resultMap, &nested);

    // Sleep mode
    cbor_encode_text_stringz(&resultMap, "sleep_mode");
    cbor_encoder_create_map(&resultMap, &nested, 3);
    cbor_encode_text_stringz(&nested, "index");
    cbor_encode_uint(&nested, sleepModeIdx);
    cbor_encode_text_stringz(&nested, "name");
    cbor_encode_text_stringz(&nested, getSleepModeDesc(sleepModeIdx));
    cbor_encode_text_stringz(&nested, "count");
    cbor_encode_uint(&nested, getTotalSleepModes());
    cbor_encoder_close_container(&resultMap, &nested);

    // RDS mode
    cbor_encode_text_stringz(&resultMap, "rds_mode");
    cbor_encoder_create_map(&resultMap, &nested, 3);
    cbor_encode_text_stringz(&nested, "index");
    cbor_encode_uint(&nested, rdsModeIdx);
    cbor_encode_text_stringz(&nested, "name");
    cbor_encode_text_stringz(&nested, getRDSModeDesc(rdsModeIdx));
    cbor_encode_text_stringz(&nested, "count");
    cbor_encode_uint(&nested, getTotalRDSModes());
    cbor_encoder_close_container(&resultMap, &nested);

    // UTC offset
    cbor_encode_text_stringz(&resultMap, "utc_offset");
    cbor_encoder_create_map(&resultMap, &nested, 3);
    cbor_encode_text_stringz(&nested, "index");
    cbor_encode_uint(&nested, utcOffsetIdx);
    cbor_encode_text_stringz(&nested, "name");
    cbor_encode_text_stringz(&nested, utcOffsets[utcOffsetIdx].desc);
    cbor_encode_text_stringz(&nested, "count");
    cbor_encode_uint(&nested, getTotalUTCOffsets());
    cbor_encoder_close_container(&resultMap, &nested);

    // FM region
    cbor_encode_text_stringz(&resultMap, "fm_region");
    cbor_encoder_create_map(&resultMap, &nested, 3);
    cbor_encode_text_stringz(&nested, "index");
    cbor_encode_uint(&nested, FmRegionIdx);
    cbor_encode_text_stringz(&nested, "name");
    cbor_encode_text_stringz(&nested, fmRegions[FmRegionIdx].desc);
    cbor_encode_text_stringz(&nested, "count");
    cbor_encode_uint(&nested, getTotalFmRegions());
    cbor_encoder_close_container(&resultMap, &nested);

    // UI layout
    cbor_encode_text_stringz(&resultMap, "ui_layout");
    cbor_encoder_create_map(&resultMap, &nested, 3);
    cbor_encode_text_stringz(&nested, "index");
    cbor_encode_uint(&nested, uiLayoutIdx);
    cbor_encode_text_stringz(&nested, "name");
    cbor_encode_text_stringz(&nested, getUILayoutDesc(uiLayoutIdx));
    cbor_encode_text_stringz(&nested, "count");
    cbor_encode_uint(&nested, getTotalUILayouts());
    cbor_encoder_close_container(&resultMap, &nested);

    // USB mode
    cbor_encode_text_stringz(&resultMap, "usb_mode");
    cbor_encoder_create_map(&resultMap, &nested, 3);
    cbor_encode_text_stringz(&nested, "index");
    cbor_encode_uint(&nested, usbModeIdx);
    cbor_encode_text_stringz(&nested, "name");
    cbor_encode_text_stringz(&nested, getUSBModeDesc(usbModeIdx));
    cbor_encode_text_stringz(&nested, "count");
    cbor_encode_uint(&nested, getTotalUSBModes());
    cbor_encoder_close_container(&resultMap, &nested);

    // BLE mode
    cbor_encode_text_stringz(&resultMap, "ble_mode");
    cbor_encoder_create_map(&resultMap, &nested, 3);
    cbor_encode_text_stringz(&nested, "index");
    cbor_encode_uint(&nested, bleModeIdx);
    cbor_encode_text_stringz(&nested, "name");
    cbor_encode_text_stringz(&nested, getBLEModeDesc(bleModeIdx));
    cbor_encode_text_stringz(&nested, "count");
    cbor_encode_uint(&nested, getTotalBleModes());
    cbor_encoder_close_container(&resultMap, &nested);

    // WiFi mode
    cbor_encode_text_stringz(&resultMap, "wifi_mode");
    cbor_encoder_create_map(&resultMap, &nested, 3);
    cbor_encode_text_stringz(&nested, "index");
    cbor_encode_uint(&nested, wifiModeIdx);
    cbor_encode_text_stringz(&nested, "name");
    cbor_encode_text_stringz(&nested, getWiFiModeDesc(wifiModeIdx));
    cbor_encode_text_stringz(&nested, "count");
    cbor_encode_uint(&nested, getTotalWiFiModes());
    cbor_encoder_close_container(&resultMap, &nested);

    // Calibration
    cbor_encode_text_stringz(&resultMap, "cal");
    cbor_encoder_create_map(&resultMap, &nested, 2);
    cbor_encode_text_stringz(&nested, "usb");
    cbor_encode_int(&nested, getCurrentBand()->usbCal);
    cbor_encode_text_stringz(&nested, "lsb");
    cbor_encode_int(&nested, getCurrentBand()->lsbCal);
    cbor_encoder_close_container(&resultMap, &nested);

    cbor_encoder_close_container(&map, &resultMap);
    cbor_encoder_close_container(&encoder, &map);

    size_t frameLen = cbor_encoder_get_buffer_size(&encoder, buffer);
    return cborRpcSendFrame(writer, buffer, frameLen);
  }

  // --- squelch.get / squelch.set ---
  if (strcmp(method, "squelch.get") == 0)
  {
    if (hasId)
      cborRpcSendSimpleResult(writer, id, "squelch", currentSquelch);
    return true;
  }

  if (strcmp(method, "squelch.set") == 0)
  {
    int64_t value = currentSquelch;
    CborValue val;
    if (hasParams && cbor_value_is_map(&paramsVal) &&
        cbor_value_map_find_value(&paramsVal, "value", &val) == CborNoError)
      cborRpcReadInt(&val, &value);
    if (value < 0)
      value = 0;
    if (value > 127)
      value = 127;
    currentSquelch = (uint8_t)value;
    prefsRequestSave(SAVE_SETTINGS);
    if (hasId)
      cborRpcSendSimpleResult(writer, id, "squelch", currentSquelch);
    return true;
  }

  // --- brightness.get / brightness.set ---
  if (strcmp(method, "brightness.get") == 0 || strcmp(method, "backlight.get") == 0)
  {
    if (hasId)
      cborRpcSendSimpleResult(writer, id, "brightness", currentBrt);
    return true;
  }

  if (strcmp(method, "brightness.set") == 0 || strcmp(method, "backlight.set") == 0)
  {
    int64_t value = currentBrt;
    CborValue val;
    if (hasParams && cbor_value_is_map(&paramsVal) &&
        cbor_value_map_find_value(&paramsVal, "value", &val) == CborNoError)
      cborRpcReadInt(&val, &value);
    if (value < 10)
      value = 10;
    if (value > 255)
      value = 255;
    int16_t delta = (int16_t)value - (int16_t)currentBrt;
    if (delta != 0)
    {
      // doBrt works in steps of 5, so set directly
      currentBrt = (uint16_t)value;
      if (!sleepOn())
        ledcWrite(LCD_BL_CH, currentBrt);
    }
    prefsRequestSave(SAVE_SETTINGS);
    if (hasId)
      cborRpcSendSimpleResult(writer, id, "brightness", currentBrt);
    return true;
  }

  // --- sleep.timeout.get / sleep.timeout.set ---
  if (strcmp(method, "sleep.timeout.get") == 0)
  {
    if (hasId)
      cborRpcSendSimpleResult(writer, id, "timeout", currentSleep);
    return true;
  }

  if (strcmp(method, "sleep.timeout.set") == 0)
  {
    int64_t value = currentSleep;
    CborValue val;
    if (hasParams && cbor_value_is_map(&paramsVal) &&
        cbor_value_map_find_value(&paramsVal, "value", &val) == CborNoError)
      cborRpcReadInt(&val, &value);
    if (value < 0)
      value = 0;
    if (value > 255)
      value = 255;
    currentSleep = (uint16_t)value;
    prefsRequestSave(SAVE_SETTINGS);
    if (hasId)
      cborRpcSendSimpleResult(writer, id, "timeout", currentSleep);
    return true;
  }

  // --- zoom.menu.get / zoom.menu.set ---
  if (strcmp(method, "zoom.menu.get") == 0)
  {
    if (hasId)
      cborRpcSendBoolResult(writer, id, "enabled", zoomMenu);
    return true;
  }

  if (strcmp(method, "zoom.menu.set") == 0)
  {
    bool value = zoomMenu;
    CborValue val;
    if (hasParams && cbor_value_is_map(&paramsVal) &&
        cbor_value_map_find_value(&paramsVal, "value", &val) == CborNoError)
      cborRpcReadBool(&val, &value);
    zoomMenu = value;
    prefsRequestSave(SAVE_SETTINGS);
    if (hasId)
      cborRpcSendBoolResult(writer, id, "enabled", zoomMenu);
    return true;
  }

  // --- scroll.direction.get / scroll.direction.set ---
  if (strcmp(method, "scroll.direction.get") == 0)
  {
    if (hasId)
      cborRpcSendSimpleResult(writer, id, "direction", scrollDirection);
    return true;
  }

  if (strcmp(method, "scroll.direction.set") == 0)
  {
    int64_t value = scrollDirection;
    CborValue val;
    if (hasParams && cbor_value_is_map(&paramsVal) &&
        cbor_value_map_find_value(&paramsVal, "value", &val) == CborNoError)
      cborRpcReadInt(&val, &value);
    scrollDirection = (value < 0) ? -1 : 1;
    prefsRequestSave(SAVE_SETTINGS);
    if (hasId)
      cborRpcSendSimpleResult(writer, id, "direction", scrollDirection);
    return true;
  }

  // --- theme.get / theme.set ---
  if (strcmp(method, "theme.get") == 0)
  {
    if (hasId)
      cborRpcSendEnumResult(writer, id, themeIdx, theme[themeIdx].name, getTotalThemes());
    return true;
  }

  if (strcmp(method, "theme.set") == 0)
  {
    int64_t value = themeIdx;
    CborValue val;
    if (hasParams && cbor_value_is_map(&paramsVal) &&
        cbor_value_map_find_value(&paramsVal, "value", &val) == CborNoError)
      cborRpcReadInt(&val, &value);
    if (value < 0 || value >= getTotalThemes())
      return cborRpcSendError(writer, id, -32602, "invalid theme index");
    themeIdx = (uint8_t)value;
    prefsRequestSave(SAVE_SETTINGS);
    if (hasId)
      cborRpcSendEnumResult(writer, id, themeIdx, theme[themeIdx].name, getTotalThemes());
    return true;
  }

  // --- ui.layout.get / ui.layout.set ---
  if (strcmp(method, "ui.layout.get") == 0)
  {
    if (hasId)
      cborRpcSendEnumResult(writer, id, uiLayoutIdx, getUILayoutDesc(uiLayoutIdx), getTotalUILayouts());
    return true;
  }

  if (strcmp(method, "ui.layout.set") == 0)
  {
    int64_t value = uiLayoutIdx;
    CborValue val;
    if (hasParams && cbor_value_is_map(&paramsVal) &&
        cbor_value_map_find_value(&paramsVal, "value", &val) == CborNoError)
      cborRpcReadInt(&val, &value);
    if (value < 0 || value >= getTotalUILayouts())
      return cborRpcSendError(writer, id, -32602, "invalid layout index");
    uiLayoutIdx = (uint8_t)value;
    prefsRequestSave(SAVE_SETTINGS);
    if (hasId)
      cborRpcSendEnumResult(writer, id, uiLayoutIdx, getUILayoutDesc(uiLayoutIdx), getTotalUILayouts());
    return true;
  }

  // --- sleep.mode.get / sleep.mode.set ---
  if (strcmp(method, "sleep.mode.get") == 0)
  {
    if (hasId)
      cborRpcSendEnumResult(writer, id, sleepModeIdx, getSleepModeDesc(sleepModeIdx), getTotalSleepModes());
    return true;
  }

  if (strcmp(method, "sleep.mode.set") == 0)
  {
    int64_t value = sleepModeIdx;
    CborValue val;
    if (hasParams && cbor_value_is_map(&paramsVal) &&
        cbor_value_map_find_value(&paramsVal, "value", &val) == CborNoError)
      cborRpcReadInt(&val, &value);
    if (value < 0 || value >= getTotalSleepModes())
      return cborRpcSendError(writer, id, -32602, "invalid sleep mode");
    sleepModeIdx = (uint8_t)value;
    prefsRequestSave(SAVE_SETTINGS);
    if (hasId)
      cborRpcSendEnumResult(writer, id, sleepModeIdx, getSleepModeDesc(sleepModeIdx), getTotalSleepModes());
    return true;
  }

  // --- usb.mode.get / usb.mode.set ---
  if (strcmp(method, "usb.mode.get") == 0)
  {
    if (hasId)
      cborRpcSendEnumResult(writer, id, usbModeIdx, getUSBModeDesc(usbModeIdx), getTotalUSBModes());
    return true;
  }

  if (strcmp(method, "usb.mode.set") == 0)
  {
    int64_t value = usbModeIdx;
    CborValue val;
    if (hasParams && cbor_value_is_map(&paramsVal) &&
        cbor_value_map_find_value(&paramsVal, "value", &val) == CborNoError)
      cborRpcReadInt(&val, &value);
    if (value < 0 || value >= getTotalUSBModes())
      return cborRpcSendError(writer, id, -32602, "invalid usb mode");
    usbModeIdx = (uint8_t)value;
    prefsRequestSave(SAVE_SETTINGS);
    if (hasId)
      cborRpcSendEnumResult(writer, id, usbModeIdx, getUSBModeDesc(usbModeIdx), getTotalUSBModes());
    return true;
  }

  // --- rds.mode.get / rds.mode.set ---
  if (strcmp(method, "rds.mode.get") == 0)
  {
    if (hasId)
      cborRpcSendEnumResult(writer, id, rdsModeIdx, getRDSModeDesc(rdsModeIdx), getTotalRDSModes());
    return true;
  }

  if (strcmp(method, "rds.mode.set") == 0)
  {
    int64_t value = rdsModeIdx;
    CborValue val;
    if (hasParams && cbor_value_is_map(&paramsVal) &&
        cbor_value_map_find_value(&paramsVal, "value", &val) == CborNoError)
      cborRpcReadInt(&val, &value);
    if (value < 0 || value >= getTotalRDSModes())
      return cborRpcSendError(writer, id, -32602, "invalid rds mode");
    rdsModeIdx = (uint8_t)value;
    if (!(getRDSMode() & RDS_CT))
      clockReset();
    prefsRequestSave(SAVE_SETTINGS);
    if (hasId)
      cborRpcSendEnumResult(writer, id, rdsModeIdx, getRDSModeDesc(rdsModeIdx), getTotalRDSModes());
    return true;
  }

  // --- utc.offset.get / utc.offset.set ---
  if (strcmp(method, "utc.offset.get") == 0)
  {
    if (hasId)
      cborRpcSendEnumResult(writer, id, utcOffsetIdx, utcOffsets[utcOffsetIdx].desc, getTotalUTCOffsets());
    return true;
  }

  if (strcmp(method, "utc.offset.set") == 0)
  {
    int64_t value = utcOffsetIdx;
    CborValue val;
    if (hasParams && cbor_value_is_map(&paramsVal) &&
        cbor_value_map_find_value(&paramsVal, "value", &val) == CborNoError)
      cborRpcReadInt(&val, &value);
    if (value < 0 || value >= getTotalUTCOffsets())
      return cborRpcSendError(writer, id, -32602, "invalid utc offset index");
    utcOffsetIdx = (uint8_t)value;
    clockRefreshTime();
    prefsRequestSave(SAVE_SETTINGS);
    if (hasId)
      cborRpcSendEnumResult(writer, id, utcOffsetIdx, utcOffsets[utcOffsetIdx].desc, getTotalUTCOffsets());
    return true;
  }

  // --- fm.region.get / fm.region.set ---
  if (strcmp(method, "fm.region.get") == 0)
  {
    if (hasId)
      cborRpcSendEnumResult(writer, id, FmRegionIdx, fmRegions[FmRegionIdx].desc, getTotalFmRegions());
    return true;
  }

  if (strcmp(method, "fm.region.set") == 0)
  {
    if (currentMode != FM)
      return cborRpcSendError(writer, id, -32602, "only available in FM mode");
    int64_t value = FmRegionIdx;
    CborValue val;
    if (hasParams && cbor_value_is_map(&paramsVal) &&
        cbor_value_map_find_value(&paramsVal, "value", &val) == CborNoError)
      cborRpcReadInt(&val, &value);
    if (value < 0 || value >= getTotalFmRegions())
      return cborRpcSendError(writer, id, -32602, "invalid fm region index");
    FmRegionIdx = (uint8_t)value;
    rx.setFMDeEmphasis(fmRegions[FmRegionIdx].value);
    prefsRequestSave(SAVE_SETTINGS);
    if (hasId)
      cborRpcSendEnumResult(writer, id, FmRegionIdx, fmRegions[FmRegionIdx].desc, getTotalFmRegions());
    return true;
  }

  // --- ble.mode.get / ble.mode.set ---
  if (strcmp(method, "ble.mode.get") == 0)
  {
    if (hasId)
      cborRpcSendEnumResult(writer, id, bleModeIdx, getBLEModeDesc(bleModeIdx), getTotalBleModes());
    return true;
  }

  if (strcmp(method, "ble.mode.set") == 0)
  {
    int64_t value = bleModeIdx;
    CborValue val;
    if (hasParams && cbor_value_is_map(&paramsVal) &&
        cbor_value_map_find_value(&paramsVal, "value", &val) == CborNoError)
      cborRpcReadInt(&val, &value);
    if (value < 0 || value >= getTotalBleModes())
      return cborRpcSendError(writer, id, -32602, "invalid ble mode");
    // Send response before changing mode (may disconnect BLE transport)
    if (hasId)
      cborRpcSendEnumResult(writer, id, (int)value, getBLEModeDesc((uint8_t)value), getTotalBleModes());
    bleInit((uint8_t)value);
    bleModeIdx = (uint8_t)value;
    prefsRequestSave(SAVE_SETTINGS);
    return true;
  }

  // --- wifi.mode.get / wifi.mode.set ---
  if (strcmp(method, "wifi.mode.get") == 0)
  {
    if (hasId)
      cborRpcSendEnumResult(writer, id, wifiModeIdx, getWiFiModeDesc(wifiModeIdx), getTotalWiFiModes());
    return true;
  }

  if (strcmp(method, "wifi.mode.set") == 0)
  {
    int64_t value = wifiModeIdx;
    CborValue val;
    if (hasParams && cbor_value_is_map(&paramsVal) &&
        cbor_value_map_find_value(&paramsVal, "value", &val) == CborNoError)
      cborRpcReadInt(&val, &value);
    if (value < 0 || value >= getTotalWiFiModes())
      return cborRpcSendError(writer, id, -32602, "invalid wifi mode");
    // Send response before changing mode (may disconnect WS transport)
    if (hasId)
      cborRpcSendEnumResult(writer, id, (int)value, getWiFiModeDesc((uint8_t)value), getTotalWiFiModes());
    wifiModeIdx = (uint8_t)value;
    netInit(wifiModeIdx);
    prefsRequestSave(SAVE_SETTINGS);
    return true;
  }

  // --- agc.get / agc.set ---
  if (strcmp(method, "agc.get") == 0)
  {
    if (!hasId)
      return true;
    uint8_t buffer[512];
    CborEncoder encoder, map2, resultMap2;
    cbor_encoder_init(&encoder, buffer, sizeof(buffer), 0);
    cbor_encoder_create_map(&encoder, &map2, 2);
    cbor_encode_text_stringz(&map2, "id");
    cbor_encode_int(&map2, id);
    cbor_encode_text_stringz(&map2, "result");
    cbor_encoder_create_map(&map2, &resultMap2, 2);
    cbor_encode_text_stringz(&resultMap2, "index");
    cbor_encode_int(&resultMap2, agcIdx);
    cbor_encode_text_stringz(&resultMap2, "max");
    cbor_encode_int(&resultMap2, (currentMode == FM) ? 27 : isSSB() ? 1
                                                                    : 37);
    cbor_encoder_close_container(&map2, &resultMap2);
    cbor_encoder_close_container(&encoder, &map2);
    size_t frameLen = cbor_encoder_get_buffer_size(&encoder, buffer);
    return cborRpcSendFrame(writer, buffer, frameLen);
  }

  if (strcmp(method, "agc.set") == 0)
  {
    int64_t value = agcIdx;
    CborValue val;
    if (hasParams && cbor_value_is_map(&paramsVal) &&
        cbor_value_map_find_value(&paramsVal, "value", &val) == CborNoError)
      cborRpcReadInt(&val, &value);
    int maxAgc = (currentMode == FM) ? 27 : isSSB() ? 1
                                                    : 37;
    if (value < 0 || value > maxAgc)
      return cborRpcSendError(writer, id, -32602, "invalid agc value");
    doAgc((int16_t)(value - agcIdx));
    prefsRequestSave(SAVE_SETTINGS);
    if (hasId)
    {
      uint8_t buffer[512];
      CborEncoder encoder, map2, resultMap2;
      cbor_encoder_init(&encoder, buffer, sizeof(buffer), 0);
      cbor_encoder_create_map(&encoder, &map2, 2);
      cbor_encode_text_stringz(&map2, "id");
      cbor_encode_int(&map2, id);
      cbor_encode_text_stringz(&map2, "result");
      cbor_encoder_create_map(&map2, &resultMap2, 2);
      cbor_encode_text_stringz(&resultMap2, "index");
      cbor_encode_int(&resultMap2, agcIdx);
      cbor_encode_text_stringz(&resultMap2, "max");
      cbor_encode_int(&resultMap2, maxAgc);
      cbor_encoder_close_container(&map2, &resultMap2);
      cbor_encoder_close_container(&encoder, &map2);
      size_t frameLen = cbor_encoder_get_buffer_size(&encoder, buffer);
      return cborRpcSendFrame(writer, buffer, frameLen);
    }
    return true;
  }

  // --- softmute.get / softmute.set ---
  if (strcmp(method, "softmute.get") == 0)
  {
    if (!hasId)
      return true;
    uint8_t buffer[512];
    CborEncoder encoder, map2, resultMap2;
    cbor_encoder_init(&encoder, buffer, sizeof(buffer), 0);
    cbor_encoder_create_map(&encoder, &map2, 2);
    cbor_encode_text_stringz(&map2, "id");
    cbor_encode_int(&map2, id);
    cbor_encode_text_stringz(&map2, "result");
    cbor_encoder_create_map(&map2, &resultMap2, 2);
    cbor_encode_text_stringz(&resultMap2, "am");
    cbor_encode_int(&resultMap2, AmSoftMuteIdx);
    cbor_encode_text_stringz(&resultMap2, "ssb");
    cbor_encode_int(&resultMap2, SsbSoftMuteIdx);
    cbor_encoder_close_container(&map2, &resultMap2);
    cbor_encoder_close_container(&encoder, &map2);
    size_t frameLen = cbor_encoder_get_buffer_size(&encoder, buffer);
    return cborRpcSendFrame(writer, buffer, frameLen);
  }

  if (strcmp(method, "softmute.set") == 0)
  {
    if (currentMode == FM)
      return cborRpcSendError(writer, id, -32602, "not available in FM mode");
    int64_t value = isSSB() ? SsbSoftMuteIdx : AmSoftMuteIdx;
    CborValue val;
    if (hasParams && cbor_value_is_map(&paramsVal) &&
        cbor_value_map_find_value(&paramsVal, "value", &val) == CborNoError)
      cborRpcReadInt(&val, &value);
    if (value < 0 || value > 32)
      return cborRpcSendError(writer, id, -32602, "invalid softmute value (0-32)");
    int8_t current = isSSB() ? SsbSoftMuteIdx : AmSoftMuteIdx;
    doSoftMute((int16_t)(value - current));
    prefsRequestSave(SAVE_SETTINGS);
    if (hasId)
    {
      uint8_t buffer[512];
      CborEncoder encoder, map2, resultMap2;
      cbor_encoder_init(&encoder, buffer, sizeof(buffer), 0);
      cbor_encoder_create_map(&encoder, &map2, 2);
      cbor_encode_text_stringz(&map2, "id");
      cbor_encode_int(&map2, id);
      cbor_encode_text_stringz(&map2, "result");
      cbor_encoder_create_map(&map2, &resultMap2, 2);
      cbor_encode_text_stringz(&resultMap2, "am");
      cbor_encode_int(&resultMap2, AmSoftMuteIdx);
      cbor_encode_text_stringz(&resultMap2, "ssb");
      cbor_encode_int(&resultMap2, SsbSoftMuteIdx);
      cbor_encoder_close_container(&map2, &resultMap2);
      cbor_encoder_close_container(&encoder, &map2);
      size_t frameLen = cbor_encoder_get_buffer_size(&encoder, buffer);
      return cborRpcSendFrame(writer, buffer, frameLen);
    }
    return true;
  }

  // --- avc.get / avc.set ---
  if (strcmp(method, "avc.get") == 0)
  {
    if (!hasId)
      return true;
    uint8_t buffer[512];
    CborEncoder encoder, map2, resultMap2;
    cbor_encoder_init(&encoder, buffer, sizeof(buffer), 0);
    cbor_encoder_create_map(&encoder, &map2, 2);
    cbor_encode_text_stringz(&map2, "id");
    cbor_encode_int(&map2, id);
    cbor_encode_text_stringz(&map2, "result");
    cbor_encoder_create_map(&map2, &resultMap2, 2);
    cbor_encode_text_stringz(&resultMap2, "am");
    cbor_encode_int(&resultMap2, AmAvcIdx);
    cbor_encode_text_stringz(&resultMap2, "ssb");
    cbor_encode_int(&resultMap2, SsbAvcIdx);
    cbor_encoder_close_container(&map2, &resultMap2);
    cbor_encoder_close_container(&encoder, &map2);
    size_t frameLen = cbor_encoder_get_buffer_size(&encoder, buffer);
    return cborRpcSendFrame(writer, buffer, frameLen);
  }

  if (strcmp(method, "avc.set") == 0)
  {
    if (currentMode == FM)
      return cborRpcSendError(writer, id, -32602, "not available in FM mode");
    int64_t value = isSSB() ? SsbAvcIdx : AmAvcIdx;
    CborValue val;
    if (hasParams && cbor_value_is_map(&paramsVal) &&
        cbor_value_map_find_value(&paramsVal, "value", &val) == CborNoError)
      cborRpcReadInt(&val, &value);
    if (value < 12 || value > 90 || (value % 2) != 0)
      return cborRpcSendError(writer, id, -32602, "invalid avc value (12-90, even)");
    int8_t current = isSSB() ? SsbAvcIdx : AmAvcIdx;
    // doAvc expects enc in units that get halved internally; compute delta directly
    if (isSSB())
      SsbAvcIdx = (int8_t)value;
    else
      AmAvcIdx = (int8_t)value;
    rx.setAvcAmMaxGain((int8_t)value);
    prefsRequestSave(SAVE_SETTINGS);
    if (hasId)
    {
      uint8_t buffer[512];
      CborEncoder encoder, map2, resultMap2;
      cbor_encoder_init(&encoder, buffer, sizeof(buffer), 0);
      cbor_encoder_create_map(&encoder, &map2, 2);
      cbor_encode_text_stringz(&map2, "id");
      cbor_encode_int(&map2, id);
      cbor_encode_text_stringz(&map2, "result");
      cbor_encoder_create_map(&map2, &resultMap2, 2);
      cbor_encode_text_stringz(&resultMap2, "am");
      cbor_encode_int(&resultMap2, AmAvcIdx);
      cbor_encode_text_stringz(&resultMap2, "ssb");
      cbor_encode_int(&resultMap2, SsbAvcIdx);
      cbor_encoder_close_container(&map2, &resultMap2);
      cbor_encoder_close_container(&encoder, &map2);
      size_t frameLen = cbor_encoder_get_buffer_size(&encoder, buffer);
      return cborRpcSendFrame(writer, buffer, frameLen);
    }
    return true;
  }

  // --- step.get / step.set ---
  if (strcmp(method, "step.get") == 0)
  {
    if (hasId)
      cborRpcSendEnumResult(writer, id, getCurrentBand()->currentStepIdx, getCurrentStep()->desc, getTotalSteps());
    return true;
  }

  if (strcmp(method, "step.set") == 0)
  {
    int64_t value = getCurrentBand()->currentStepIdx;
    CborValue val;
    if (hasParams && cbor_value_is_map(&paramsVal) &&
        cbor_value_map_find_value(&paramsVal, "value", &val) == CborNoError)
      cborRpcReadInt(&val, &value);
    int16_t delta = (int16_t)(value - getCurrentBand()->currentStepIdx);
    if (delta != 0)
      doStep(delta);
    prefsRequestSave(SAVE_CUR_BAND);
    if (hasId)
      cborRpcSendEnumResult(writer, id, getCurrentBand()->currentStepIdx, getCurrentStep()->desc, getTotalSteps());
    return true;
  }

  // --- bandwidth.get / bandwidth.set ---
  if (strcmp(method, "bandwidth.get") == 0)
  {
    if (hasId)
      cborRpcSendEnumResult(writer, id, getCurrentBand()->bandwidthIdx, getCurrentBandwidth()->desc, getTotalBandwidths());
    return true;
  }

  if (strcmp(method, "bandwidth.set") == 0)
  {
    int64_t value = getCurrentBand()->bandwidthIdx;
    CborValue val;
    if (hasParams && cbor_value_is_map(&paramsVal) &&
        cbor_value_map_find_value(&paramsVal, "value", &val) == CborNoError)
      cborRpcReadInt(&val, &value);
    int16_t delta = (int16_t)(value - getCurrentBand()->bandwidthIdx);
    if (delta != 0)
      doBandwidth(delta);
    prefsRequestSave(SAVE_CUR_BAND);
    if (hasId)
      cborRpcSendEnumResult(writer, id, getCurrentBand()->bandwidthIdx, getCurrentBandwidth()->desc, getTotalBandwidths());
    return true;
  }

  // --- cal.get / cal.set ---
  if (strcmp(method, "cal.get") == 0)
  {
    if (!hasId)
      return true;
    uint8_t buffer[512];
    CborEncoder encoder, map2, resultMap2;
    cbor_encoder_init(&encoder, buffer, sizeof(buffer), 0);
    cbor_encoder_create_map(&encoder, &map2, 2);
    cbor_encode_text_stringz(&map2, "id");
    cbor_encode_int(&map2, id);
    cbor_encode_text_stringz(&map2, "result");
    cbor_encoder_create_map(&map2, &resultMap2, 2);
    cbor_encode_text_stringz(&resultMap2, "usb");
    cbor_encode_int(&resultMap2, getCurrentBand()->usbCal);
    cbor_encode_text_stringz(&resultMap2, "lsb");
    cbor_encode_int(&resultMap2, getCurrentBand()->lsbCal);
    cbor_encoder_close_container(&map2, &resultMap2);
    cbor_encoder_close_container(&encoder, &map2);
    size_t frameLen = cbor_encoder_get_buffer_size(&encoder, buffer);
    return cborRpcSendFrame(writer, buffer, frameLen);
  }

  if (strcmp(method, "cal.set") == 0)
  {
    if (!isSSB())
      return cborRpcSendError(writer, id, -32602, "only available in SSB mode");
    int64_t value = (currentMode == USB) ? getCurrentBand()->usbCal : getCurrentBand()->lsbCal;
    CborValue val;
    if (hasParams && cbor_value_is_map(&paramsVal) &&
        cbor_value_map_find_value(&paramsVal, "value", &val) == CborNoError)
      cborRpcReadInt(&val, &value);
    if (value < -MAX_CAL || value > MAX_CAL)
      return cborRpcSendError(writer, id, -32602, "cal value out of range");
    if (currentMode == USB)
      getCurrentBand()->usbCal = (int16_t)value;
    else
      getCurrentBand()->lsbCal = (int16_t)value;
    updateBFO(currentBFO, true);
    prefsRequestSave(SAVE_CUR_BAND);
    if (hasId)
    {
      uint8_t buffer[512];
      CborEncoder encoder, map2, resultMap2;
      cbor_encoder_init(&encoder, buffer, sizeof(buffer), 0);
      cbor_encoder_create_map(&encoder, &map2, 2);
      cbor_encode_text_stringz(&map2, "id");
      cbor_encode_int(&map2, id);
      cbor_encode_text_stringz(&map2, "result");
      cbor_encoder_create_map(&map2, &resultMap2, 2);
      cbor_encode_text_stringz(&resultMap2, "usb");
      cbor_encode_int(&resultMap2, getCurrentBand()->usbCal);
      cbor_encode_text_stringz(&resultMap2, "lsb");
      cbor_encode_int(&resultMap2, getCurrentBand()->lsbCal);
      cbor_encoder_close_container(&map2, &resultMap2);
      cbor_encoder_close_container(&encoder, &map2);
      size_t frameLen = cbor_encoder_get_buffer_size(&encoder, buffer);
      return cborRpcSendFrame(writer, buffer, frameLen);
    }
    return true;
  }

  // --- band.get / band.set ---
  if (strcmp(method, "band.get") == 0)
  {
    if (hasId)
      cborRpcSendEnumResult(writer, id, bandIdx, getCurrentBand()->bandName, getTotalBands());
    return true;
  }

  if (strcmp(method, "band.set") == 0)
  {
    int64_t value = -1;
    char bandName[16] = {0};
    bool nameIsText = false;
    CborValue val;
    if (hasParams && cbor_value_is_map(&paramsVal) &&
        cbor_value_map_find_value(&paramsVal, "value", &val) == CborNoError)
      cborRpcReadTextOrInt(&val, bandName, sizeof(bandName), &value, &nameIsText);

    int targetBand = -1;
    if (nameIsText && bandName[0] != '\0')
    {
      for (int i = 0; i < getTotalBands(); i++)
      {
        if (strcmp(bands[i].bandName, bandName) == 0)
        {
          targetBand = i;
          break;
        }
      }
    }
    else if (value >= 0 && value < getTotalBands())
    {
      targetBand = (int)value;
    }

    if (targetBand < 0)
      return cborRpcSendError(writer, id, -32602, "invalid band");

    // Save current band and switch
    bands[bandIdx].currentFreq = currentFrequency + currentBFO / 1000;
    bands[bandIdx].bandMode = currentMode;
    selectBand((uint8_t)targetBand);
    prefsRequestSave(SAVE_CUR_BAND);
    if (hasId)
      cborRpcSendEnumResult(writer, id, bandIdx, getCurrentBand()->bandName, getTotalBands());
    return true;
  }

  // --- mode.get / mode.set ---
  if (strcmp(method, "mode.get") == 0)
  {
    if (hasId)
      cborRpcSendEnumResult(writer, id, currentMode, bandModeDesc[currentMode], getTotalModes());
    return true;
  }

  if (strcmp(method, "mode.set") == 0)
  {
    int64_t value = currentMode;
    CborValue val;
    if (hasParams && cbor_value_is_map(&paramsVal) &&
        cbor_value_map_find_value(&paramsVal, "value", &val) == CborNoError)
      cborRpcReadInt(&val, &value);
    if (value < 0 || value >= getTotalModes())
      return cborRpcSendError(writer, id, -32602, "invalid mode");
    if (currentMode == FM && value != FM)
      return cborRpcSendError(writer, id, -32602, "cannot change mode on FM band");
    if (currentMode != FM && value == FM)
      return cborRpcSendError(writer, id, -32602, "cannot switch to FM on non-FM band");
    if ((int64_t)currentMode != value)
    {
      int16_t delta = (int16_t)(value - currentMode);
      // doMode wraps, but we want to set directly
      bands[bandIdx].currentFreq = currentFrequency + currentBFO / 1000;
      bands[bandIdx].currentStepIdx = 5; // default SSB/AM step
      bands[bandIdx].bandMode = (uint8_t)value;
      currentMode = (uint8_t)value;
      selectBand(bandIdx);
    }
    prefsRequestSave(SAVE_CUR_BAND);
    if (hasId)
      cborRpcSendEnumResult(writer, id, currentMode, bandModeDesc[currentMode], getTotalModes());
    return true;
  }

  // --- frequency.get / frequency.set ---
  if (strcmp(method, "frequency.get") == 0)
  {
    if (!hasId)
      return true;
    uint8_t buffer[512];
    CborEncoder encoder, map2, resultMap2;
    cbor_encoder_init(&encoder, buffer, sizeof(buffer), 0);
    cbor_encoder_create_map(&encoder, &map2, 2);
    cbor_encode_text_stringz(&map2, "id");
    cbor_encode_int(&map2, id);
    cbor_encode_text_stringz(&map2, "result");
    cbor_encoder_create_map(&map2, &resultMap2, 2);
    cbor_encode_text_stringz(&resultMap2, "frequency");
    cbor_encode_uint(&resultMap2, currentFrequency);
    cbor_encode_text_stringz(&resultMap2, "bfo");
    cbor_encode_int(&resultMap2, currentBFO);
    cbor_encoder_close_container(&map2, &resultMap2);
    cbor_encoder_close_container(&encoder, &map2);
    size_t frameLen = cbor_encoder_get_buffer_size(&encoder, buffer);
    return cborRpcSendFrame(writer, buffer, frameLen);
  }

  if (strcmp(method, "frequency.set") == 0)
  {
    int64_t value = currentFrequency;
    CborValue val;
    if (hasParams && cbor_value_is_map(&paramsVal) &&
        cbor_value_map_find_value(&paramsVal, "value", &val) == CborNoError)
      cborRpcReadInt(&val, &value);
    if (value < getCurrentBand()->minimumFreq || value > getCurrentBand()->maximumFreq)
      return cborRpcSendError(writer, id, -32602, "frequency out of band range");
    currentFrequency = (uint16_t)value;
    rx.setFrequency(currentFrequency);
    getCurrentBand()->currentFreq = currentFrequency;
    currentBFO = 0;
    prefsRequestSave(SAVE_CUR_BAND);
    if (hasId)
    {
      uint8_t buffer[512];
      CborEncoder encoder, map2, resultMap2;
      cbor_encoder_init(&encoder, buffer, sizeof(buffer), 0);
      cbor_encoder_create_map(&encoder, &map2, 2);
      cbor_encode_text_stringz(&map2, "id");
      cbor_encode_int(&map2, id);
      cbor_encode_text_stringz(&map2, "result");
      cbor_encoder_create_map(&map2, &resultMap2, 2);
      cbor_encode_text_stringz(&resultMap2, "frequency");
      cbor_encode_uint(&resultMap2, currentFrequency);
      cbor_encode_text_stringz(&resultMap2, "bfo");
      cbor_encode_int(&resultMap2, currentBFO);
      cbor_encoder_close_container(&map2, &resultMap2);
      cbor_encoder_close_container(&encoder, &map2);
      size_t frameLen = cbor_encoder_get_buffer_size(&encoder, buffer);
      return cborRpcSendFrame(writer, buffer, frameLen);
    }
    return true;
  }

  if (strcmp(method, "events.subscribe") == 0 || strcmp(method, "events.unsubscribe") == 0)
  {
    bool enable = strcmp(method, "events.subscribe") == 0;
    char eventName[16] = {0};
    CborValue val;
    if (hasParams && cbor_value_is_map(&paramsVal) && cbor_value_map_find_value(&paramsVal, "event", &val) == CborNoError)
    {
      cborRpcReadText(&val, eventName, sizeof(eventName));
    }
    if (strcmp(eventName, "stats") == 0 || eventName[0] == '\0')
    {
      state->rpcEvents = enable;
      if (hasId)
        cborRpcSendBoolResult(writer, id, "enabled", state->rpcEvents);
      return true;
    }
    if (hasId)
      cborRpcSendError(writer, id, -32602, "unknown event");
    return false;
  }

  if (strcmp(method, "screen.capture") == 0)
  {
    if (!hasId)
    {
      return cborRpcSendError(writer, 0, -32602, "missing id");
    }

    char format[16] = "binary";
    CborValue val;
    if (hasParams && cbor_value_is_map(&paramsVal) && cbor_value_map_find_value(&paramsVal, "format", &val) == CborNoError)
    {
      cborRpcReadText(&val, format, sizeof(format));
    }

    uint32_t streamId = ++state->rpcStreamId;
    uint16_t width = spr.width();
    uint16_t height = spr.height();

    if (strcmp(format, "rle") == 0)
    {
      cborRpcSendCaptureResult(writer, id, streamId, "rle", width, height);
      RpcChunkStream chunkStream(writer, state, streamId);
      remoteCaptureDeltaRle(&chunkStream);
      chunkStream.flush();
      return true;
    }

    const char *formatName = (strcmp(format, "bmp") == 0) ? "binary" : "binary";
    cborRpcSendCaptureResult(writer, id, streamId, formatName, width, height);
    RpcChunkStream chunkStream(writer, state, streamId);
    remoteCaptureScreen(&chunkStream, true);
    chunkStream.flush();
    return true;
  }

  if (hasId)
    cborRpcSendError(writer, id, -32601, "method not found");
  return false;
}

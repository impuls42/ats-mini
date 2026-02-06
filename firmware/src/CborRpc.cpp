#include "CborRpc.h"

#include "Common.h"
#include "Menu.h"
#include "Compression.h"
#include "Remote.h"
#include "Storage.h"
#include "Utils.h"

#include <tinycbor.h>
#include <string.h>

static bool cborRpcSendFrame(CborRpcWriter *writer, const uint8_t *data, size_t len)
{
  if (!writer || !writer->send_frame) return false;
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
  cbor_encoder_create_map(&map, &resultMap, 6);

  cbor_encode_text_stringz(&resultMap, "rpc_version");
  cbor_encode_uint(&resultMap, 1);
  cbor_encode_text_stringz(&resultMap, "switch_byte");
  cbor_encode_uint(&resultMap, CBOR_RPC_SWITCH);
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

    while (remaining > 0) {
      size_t space = sizeof(chunk) - chunkSize;
      size_t toCopy = remaining < space ? remaining : space;
      memcpy(chunk + chunkSize, ptr, toCopy);
      chunkSize += toCopy;
      ptr += toCopy;
      remaining -= toCopy;

      if (chunkSize == sizeof(chunk)) {
        if (!sendChunk()) return size - remaining;
      }
    }

    return size;
  }

  int available() override { return 0; }
  int read() override { return -1; }
  int peek() override { return -1; }
  void flush() override { sendChunk(); sendDone(); }

private:
  bool sendChunk()
  {
    if (chunkSize == 0) return true;

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
  while (stream->available()) {
    uint8_t byte = (uint8_t)stream->read();

    if (byte == CBOR_RPC_SWITCH && state->rpcExpected == 0 && state->rpcHeaderRead == 0) {
      state->rpcRead = 0;
      continue;
    }

    if (state->rpcExpected == 0) {
      state->rpcHeader[state->rpcHeaderRead++] = byte;
      if (state->rpcHeaderRead == sizeof(state->rpcHeader)) {
        uint32_t len = ((uint32_t)state->rpcHeader[0] << 24) |
                       ((uint32_t)state->rpcHeader[1] << 16) |
                       ((uint32_t)state->rpcHeader[2] << 8) |
                       (uint32_t)state->rpcHeader[3];
        state->rpcHeaderRead = 0;
        state->rpcExpected = len;
        state->rpcRead = 0;
        if (len == 0 || len > CBOR_RPC_MAX_FRAME) {
          state->rpcExpected = 0;
          state->rpcRead = 0;
        }
      }
      continue;
    }

    if (state->rpcRead < CBOR_RPC_MAX_FRAME) {
      state->rpcBuf[state->rpcRead++] = byte;
    }

    if (state->rpcRead >= state->rpcExpected && state->rpcExpected > 0) {
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
  uint8_t buffer[1024];
  CborEncoder encoder;
  CborEncoder map;
  CborEncoder paramsMap;

  cbor_encoder_init(&encoder, buffer, sizeof(buffer), 0);
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
                  (currentMode == USB) ? getCurrentBand()->usbCal :
                  (currentMode == LSB) ? getCurrentBand()->lsbCal : 0);
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

static bool cborRpcReadText(CborValue *value, char *out, size_t outLen)
{
  size_t len = outLen;
  if (!cbor_value_is_text_string(value)) return false;
  CborError err = cbor_value_copy_text_string(value, out, &len, nullptr);
  return err == CborNoError;
}

static bool cborRpcReadInt(CborValue *value, int64_t *out)
{
  if (!cbor_value_is_integer(value)) return false;
  return cbor_value_get_int64(value, out) == CborNoError;
}

static bool cborRpcReadTextOrInt(CborValue *value, char *textOut, size_t textLen, int64_t *intOut, bool *isText)
{
  if (cbor_value_is_text_string(value)) {
    if (isText) *isText = true;
    return cborRpcReadText(value, textOut, textLen);
  }
  if (cbor_value_is_integer(value)) {
    if (isText) *isText = false;
    return cborRpcReadInt(value, intOut);
  }
  return false;
}

bool cborRpcHandleFrame(const uint8_t *frame, size_t len, CborRpcWriter *writer, RemoteState *state)
{
  CborParser parser;
  CborValue root;
  CborError err = cbor_parser_init(frame, len, 0, &parser, &root);
  if (err != CborNoError || !cbor_value_is_map(&root)) {
    return false;
  }

  CborValue methodVal;
  CborValue idVal;
  CborValue paramsVal;
  bool hasParams = false;
  char method[32] = {0};
  bool hasId = false;
  int64_t id = 0;

  if (cbor_value_map_find_value(&root, "method", &methodVal) == CborNoError) {
    cborRpcReadText(&methodVal, method, sizeof(method));
  }

  if (cbor_value_map_find_value(&root, "id", &idVal) == CborNoError) {
    if (cborRpcReadInt(&idVal, &id)) hasId = true;
  }

  if (cbor_value_map_find_value(&root, "params", &paramsVal) == CborNoError) {
    hasParams = true;
  }

  if (method[0] == '\0') {
    if (hasId) cborRpcSendError(writer, id, -32600, "missing method");
    return false;
  }

  if (strcmp(method, "volume.set") == 0) {
    int64_t value = volume;
    CborValue val;
    if (hasParams && cbor_value_is_map(&paramsVal) && cbor_value_map_find_value(&paramsVal, "value", &val) == CborNoError) {
      cborRpcReadInt(&val, &value);
    }
    if (value < 0) value = 0;
    if (value > 63) value = 63;
    doVolume((int16_t)(value - volume));
    if (hasId) cborRpcSendSimpleResult(writer, id, "volume", volume);
    return true;
  }

  if (strcmp(method, "volume.up") == 0) {
    doVolume(1);
    prefsRequestSave(SAVE_SETTINGS);
    if (hasId) cborRpcSendStatusResult(writer, id);
    return true;
  }

  if (strcmp(method, "volume.down") == 0) {
    doVolume(-1);
    prefsRequestSave(SAVE_SETTINGS);
    if (hasId) cborRpcSendStatusResult(writer, id);
    return true;
  }

  if (strcmp(method, "volume.get") == 0) {
    if (hasId) cborRpcSendSimpleResult(writer, id, "volume", volume);
    return true;
  }

  if (strcmp(method, "log.get") == 0) {
    if (hasId) cborRpcSendBoolResult(writer, id, "enabled", state->rpcEvents);
    return true;
  }

  if (strcmp(method, "capabilities.get") == 0) {
    if (hasId) cborRpcSendCapabilitiesResult(writer, id);
    return true;
  }

  if (strcmp(method, "log.toggle") == 0) {
    state->rpcEvents = !state->rpcEvents;
    if (hasId) cborRpcSendBoolResult(writer, id, "enabled", state->rpcEvents);
    return true;
  }

  if (strcmp(method, "band.up") == 0) {
    doBand(1);
    prefsRequestSave(SAVE_CUR_BAND);
    if (hasId) cborRpcSendStatusResult(writer, id);
    return true;
  }

  if (strcmp(method, "band.down") == 0) {
    doBand(-1);
    prefsRequestSave(SAVE_CUR_BAND);
    if (hasId) cborRpcSendStatusResult(writer, id);
    return true;
  }

  if (strcmp(method, "mode.up") == 0) {
    doMode(1);
    prefsRequestSave(SAVE_CUR_BAND);
    if (hasId) cborRpcSendStatusResult(writer, id);
    return true;
  }

  if (strcmp(method, "mode.down") == 0) {
    doMode(-1);
    prefsRequestSave(SAVE_CUR_BAND);
    if (hasId) cborRpcSendStatusResult(writer, id);
    return true;
  }

  if (strcmp(method, "step.up") == 0) {
    doStep(1);
    prefsRequestSave(SAVE_CUR_BAND);
    if (hasId) cborRpcSendStatusResult(writer, id);
    return true;
  }

  if (strcmp(method, "step.down") == 0) {
    doStep(-1);
    prefsRequestSave(SAVE_CUR_BAND);
    if (hasId) cborRpcSendStatusResult(writer, id);
    return true;
  }

  if (strcmp(method, "bandwidth.up") == 0) {
    doBandwidth(1);
    prefsRequestSave(SAVE_CUR_BAND);
    if (hasId) cborRpcSendStatusResult(writer, id);
    return true;
  }

  if (strcmp(method, "bandwidth.down") == 0) {
    doBandwidth(-1);
    prefsRequestSave(SAVE_CUR_BAND);
    if (hasId) cborRpcSendStatusResult(writer, id);
    return true;
  }

  if (strcmp(method, "agc.up") == 0) {
    doAgc(1);
    prefsRequestSave(SAVE_SETTINGS);
    if (hasId) cborRpcSendStatusResult(writer, id);
    return true;
  }

  if (strcmp(method, "agc.down") == 0) {
    doAgc(-1);
    prefsRequestSave(SAVE_SETTINGS);
    if (hasId) cborRpcSendStatusResult(writer, id);
    return true;
  }

  if (strcmp(method, "backlight.up") == 0) {
    doBrt(1);
    prefsRequestSave(SAVE_SETTINGS);
    if (hasId) cborRpcSendStatusResult(writer, id);
    return true;
  }

  if (strcmp(method, "backlight.down") == 0) {
    doBrt(-1);
    prefsRequestSave(SAVE_SETTINGS);
    if (hasId) cborRpcSendStatusResult(writer, id);
    return true;
  }

  if (strcmp(method, "cal.up") == 0) {
    doCal(1);
    prefsRequestSave(SAVE_CUR_BAND);
    if (hasId) cborRpcSendStatusResult(writer, id);
    return true;
  }

  if (strcmp(method, "cal.down") == 0) {
    doCal(-1);
    prefsRequestSave(SAVE_CUR_BAND);
    if (hasId) cborRpcSendStatusResult(writer, id);
    return true;
  }

  if (strcmp(method, "sleep.on") == 0) {
    sleepOn(true);
    if (hasId) cborRpcSendBoolResult(writer, id, "sleep", true);
    return true;
  }

  if (strcmp(method, "sleep.off") == 0) {
    sleepOn(false);
    if (hasId) cborRpcSendBoolResult(writer, id, "sleep", false);
    return true;
  }

  if (strcmp(method, "status.get") == 0) {
    if (hasId) cborRpcSendStatusResult(writer, id);
    return true;
  }

  if (strcmp(method, "memory.list") == 0) {
    if (!hasId) return false;
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

    for (uint8_t i = 0; i < getTotalMemories(); i++) {
      if (!memories[i].freq) continue;
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

  if (strcmp(method, "memory.set") == 0) {
    if (!hasId) return false;

    int64_t slot = 0;
    int64_t freq_hz = 0;
    int64_t modeIndex = currentMode;
    int64_t bandIndex = -1;
    char bandName[16] = {0};
    bool bandIsText = false;
    CborValue val;

    if (!hasParams || !cbor_value_is_map(&paramsVal)) {
      return cborRpcSendError(writer, id, -32602, "missing params");
    }

    if (cbor_value_map_find_value(&paramsVal, "slot", &val) == CborNoError) {
      cborRpcReadInt(&val, &slot);
    }
    if (slot < 1 || slot > getTotalMemories()) {
      return cborRpcSendError(writer, id, -32602, "invalid slot");
    }

    if (cbor_value_map_find_value(&paramsVal, "freq_hz", &val) == CborNoError) {
      cborRpcReadInt(&val, &freq_hz);
    }

    if (cbor_value_map_find_value(&paramsVal, "mode", &val) == CborNoError) {
      cborRpcReadInt(&val, &modeIndex);
    }

    if (cbor_value_map_find_value(&paramsVal, "band", &val) == CborNoError) {
      cborRpcReadTextOrInt(&val, bandName, sizeof(bandName), &bandIndex, &bandIsText);
    }

    Memory mem;
    memset(&mem, 0, sizeof(mem));
    mem.freq = (uint32_t)freq_hz;
    mem.mode = (uint8_t)modeIndex;
    mem.band = 0xFF;

    if (freq_hz == 0) {
      memories[slot - 1] = mem;
      prefsRequestSave(SAVE_MEMORIES);
      return cborRpcSendSimpleResult(writer, id, "slot", slot);
    }

    if (bandIsText && bandName[0] != '\0') {
      for (int i = 0; i < getTotalBands(); i++) {
        if (strcmp(bands[i].bandName, bandName) == 0) {
          mem.band = i;
          break;
        }
      }
    } else if (bandIndex >= 0 && bandIndex < getTotalBands()) {
      mem.band = (uint8_t)bandIndex;
    } else {
      for (int i = 0; i < getTotalBands(); i++) {
        if (isMemoryInBand(&bands[i], &mem)) {
          mem.band = i;
          break;
        }
      }
    }

    if (mem.band == 0xFF) {
      return cborRpcSendError(writer, id, -32602, "invalid band");
    }

    if (!isMemoryInBand(&bands[mem.band], &mem)) {
      return cborRpcSendError(writer, id, -32602, "invalid frequency");
    }

    memories[slot - 1] = mem;
    prefsRequestSave(SAVE_MEMORIES);
    return cborRpcSendSimpleResult(writer, id, "slot", slot);
  }

  if (strcmp(method, "events.subscribe") == 0 || strcmp(method, "events.unsubscribe") == 0) {
    bool enable = strcmp(method, "events.subscribe") == 0;
    char eventName[16] = {0};
    CborValue val;
    if (hasParams && cbor_value_is_map(&paramsVal) && cbor_value_map_find_value(&paramsVal, "event", &val) == CborNoError) {
      cborRpcReadText(&val, eventName, sizeof(eventName));
    }
    if (strcmp(eventName, "stats") == 0 || eventName[0] == '\0') {
      state->rpcEvents = enable;
      if (hasId) cborRpcSendBoolResult(writer, id, "enabled", state->rpcEvents);
      return true;
    }
    if (hasId) cborRpcSendError(writer, id, -32602, "unknown event");
    return false;
  }

  if (strcmp(method, "screen.capture") == 0) {
    if (!hasId) {
      return cborRpcSendError(writer, 0, -32602, "missing id");
    }

    char format[16] = "binary";
    CborValue val;
    if (hasParams && cbor_value_is_map(&paramsVal) && cbor_value_map_find_value(&paramsVal, "format", &val) == CborNoError) {
      cborRpcReadText(&val, format, sizeof(format));
    }

    uint32_t streamId = ++state->rpcStreamId;
    uint16_t width = spr.width();
    uint16_t height = spr.height();

    if (strcmp(format, "rle") == 0) {
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

  if (hasId) cborRpcSendError(writer, id, -32601, "method not found");
  return false;
}

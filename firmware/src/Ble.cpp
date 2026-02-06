#include "Common.h"
#include "Themes.h"
#include "Remote.h"
#include "Ble.h"
#include "CborRpc.h"

static bool cborRpcSendFrameStream(void *ctx, const uint8_t *data, size_t len)
{
  Stream *stream = (Stream *)ctx;
  uint8_t header[4] = {
      (uint8_t)((len >> 24) & 0xFF),
      (uint8_t)((len >> 16) & 0xFF),
      (uint8_t)((len >> 8) & 0xFF),
      (uint8_t)(len & 0xFF)};
  stream->write(header, sizeof(header));
  stream->write(data, len);
  return true;
}

static void cborRpcResetState(RemoteState *state)
{
  state->rpcExpected = 0;
  state->rpcRead = 0;
  state->rpcHeaderRead = 0;
}

static void cborRpcTickTime(Stream *stream, RemoteState *state)
{
  if (!state->rpcEvents)
    return;
  if (millis() - state->remoteTimer >= 500)
  {
    state->remoteTimer = millis();
    CborRpcWriter writer = {stream, cborRpcSendFrameStream};
    cborRpcSendStatsEvent(&writer, state);
  }
}

//
// Get current connection status
// (-1 - not connected, 0 - disabled, 1 - connected)
//
int8_t getBleStatus()
{
  if (!BLESerial.isStarted())
    return 0;
  return BLESerial.connectedCount() > 0 ? 1 : -1;
}

//
// Stop BLE hardware
//
void bleStop()
{
  if (!BLESerial.isStarted())
    return;
  BLESerial.stop();
}

void bleInit(uint8_t bleMode)
{
  bleStop();

  if (bleMode == BLE_OFF)
    return;
  BLESerial.start();
}

int bleDoCommand(Stream *stream, RemoteState *state, uint8_t bleMode)
{
  if (bleMode == BLE_OFF)
    return 0;

  if (BLESerial.connectedCount() > 0)
  {
    if (state->rpcMode)
    {
      CborRpcWriter writer = {stream, cborRpcSendFrameStream};
      cborRpcConsumeStream(stream, state, &writer);
      return 0;
    }

    if (BLESerial.available())
    {
      uint8_t key = BLESerial.read();
      if (key == CBOR_RPC_SWITCH)
      {
        state->rpcMode = true;
        cborRpcResetState(state);
        state->remoteTimer = millis();
        return 0;
      }
      return remoteDoCommand(stream, state, key);
    }
  }
  return 0;
}

void remoteBLETickTime(Stream *stream, RemoteState *state, uint8_t bleMode)
{
  if (bleMode == BLE_OFF)
    return;

  if (BLESerial.connectedCount() > 0)
  {
    if (state->rpcMode)
    {
      cborRpcTickTime(stream, state);
      return;
    }
    remoteTickTime(stream, state);
  }
}

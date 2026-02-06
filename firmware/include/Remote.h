#ifndef REMOTE_H
#define REMOTE_H

typedef struct {
  uint32_t remoteTimer = 0;
  uint32_t lastRxTime = 0;
  uint8_t remoteSeqnum = 0;
  bool remoteLogOn = false;
  bool rpcMode = false;
  bool rpcEvents = false;
  uint32_t rpcEventSeq = 0;
  uint32_t rpcStreamId = 0;
  uint32_t rpcExpected = 0;
  uint32_t rpcRead = 0;
  uint8_t rpcHeaderRead = 0;
  uint8_t rpcHeader[4] = {0};
  uint8_t rpcBuf[4096] = {0};
} RemoteState;

void remoteTickTime(Stream* stream, RemoteState* state);
int remoteDoCommand(Stream* stream, RemoteState* state, char key);
int serialDoCommand(Stream* stream, RemoteState* state, uint8_t usbMode);
void serialTickTime(Stream* stream, RemoteState* state, uint8_t usbMode);
void remoteCaptureScreen(Stream* stream, bool binary);

#endif

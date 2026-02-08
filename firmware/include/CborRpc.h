#ifndef CBOR_RPC_H
#define CBOR_RPC_H

#include <Stream.h>
#include <stddef.h>
#include "Remote.h"

#define CBOR_RPC_SWITCH 0x1E
#define CBOR_RPC_MAX_FRAME 4096

struct CborRpcWriter
{
  void *ctx;
  bool (*send_frame)(void *ctx, const uint8_t *data, size_t len);
};

bool cborRpcConsumeStream(Stream *stream, RemoteState *state, CborRpcWriter *writer);
bool cborRpcHandleFrame(const uint8_t *frame, size_t len, CborRpcWriter *writer, RemoteState *state);
bool cborRpcSendStatsEvent(CborRpcWriter *writer, RemoteState *state);

#endif

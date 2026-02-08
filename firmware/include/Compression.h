#ifndef COMPRESSION_H
#define COMPRESSION_H

#include <stdint.h>
#include <stddef.h>
#include <Stream.h>

// Compression mode constants
#define MAGIC_DELTA_RLE "DR"
#define MAGIC_ZLIB_RAW "ZR"
#define COMP_HEADER_LEN 16

// Flag bits for compression header
#define COMP_FLAG_DELTA 0x01
#define COMP_FLAG_ERROR 0x80

// Public API for compression modes
void remoteCaptureDeltaRle(Stream *stream);
void remoteCaptureZlibRaw(Stream *stream);

#endif // COMPRESSION_H

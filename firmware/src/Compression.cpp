/**
 * Compression Module for ATS-Mini Screenshot Capture
 *
 * Implements:
 * - Delta RLE compression (first frame full RLE, subsequent frames delta-encoded)
 * - zlib/raw compression (system zlib with graceful fallback)
 * - PSRAM-backed frame buffering with fallback to binary mode
 */

#include "Compression.h"
#include "Common.h"

// ESP32-targz library provides gzip compression via LZPacker
// NOTE: arduino-cli with profiles may show "Library 'ESP32-targz' not found" warning
// but the library IS included from ~/Documents/Arduino/libraries/ESP32-targz
#include <ESP32-targz.h>
#define ATSMINI_HAVE_ZLIB 1

// Forward declaration for fallback (defined in Remote.cpp)
extern void remoteCaptureScreen(Stream *stream, bool binary);

// Global state for delta RLE: previous frame buffer in PSRAM
static uint16_t *prevFrame = nullptr;
static uint32_t prevFrameCount = 0;
static bool prevFrameValid = false;

// ============================================================================
// Helper Functions
// ============================================================================

static void writeHeaderCompressed(Stream *stream, const char *magic, uint8_t flags,
                                  uint16_t width, uint16_t height,
                                  uint32_t rawSize, uint32_t payloadSize)
{
  uint8_t header[16];
  header[0] = magic[0];
  header[1] = magic[1];
  header[2] = 1; // version
  header[3] = flags;
  header[4] = width & 0xFF;
  header[5] = (width >> 8) & 0xFF;
  header[6] = height & 0xFF;
  header[7] = (height >> 8) & 0xFF;
  header[8] = rawSize & 0xFF;
  header[9] = (rawSize >> 8) & 0xFF;
  header[10] = (rawSize >> 16) & 0xFF;
  header[11] = (rawSize >> 24) & 0xFF;
  header[12] = payloadSize & 0xFF;
  header[13] = (payloadSize >> 8) & 0xFF;
  header[14] = (payloadSize >> 16) & 0xFF;
  header[15] = (payloadSize >> 24) & 0xFF;
  stream->write(header, sizeof(header));
}

static void streamWriteChunked(Stream *stream, const uint8_t *data, size_t len)
{
  const size_t chunkSize = 512;
  while (len > 0)
  {
    size_t chunk = len > chunkSize ? chunkSize : len;
    stream->write(data, chunk);
    data += chunk;
    len -= chunk;
  }
}

static bool ensurePrevFrame(uint32_t count)
{
  if (prevFrame && prevFrameCount == count)
    return true;
  if (prevFrame)
  {
    free(prevFrame);
    prevFrame = nullptr;
  }
  prevFrame = (uint16_t *)ps_malloc(count * sizeof(uint16_t));
  prevFrameCount = prevFrame ? count : 0;
  prevFrameValid = false;
  return prevFrame != nullptr;
}

// ============================================================================
// RLE (Run-Length Encoding) Functions
// ============================================================================

static uint32_t rleSizeFull(uint16_t width, uint16_t height)
{
  uint32_t total = 0;
  uint16_t runVal = 0;
  uint16_t run = 0;
  for (int y = height - 1; y >= 0; y--)
  {
    for (int x = 0; x < width; x++)
    {
      uint16_t pixel = spr.readPixel(x, y);
      if (run == 0)
      {
        runVal = pixel;
        run = 1;
      }
      else if (pixel == runVal && run < 255)
      {
        run++;
      }
      else
      {
        total += 3;
        runVal = pixel;
        run = 1;
      }
    }
  }
  if (run > 0)
    total += 3;
  return total;
}

static void rleEncodeFull(Stream *stream, uint16_t width, uint16_t height)
{
  uint16_t runVal = 0;
  uint16_t run = 0;
  uint32_t idx = 0;
  for (int y = height - 1; y >= 0; y--)
  {
    for (int x = 0; x < width; x++, idx++)
    {
      uint16_t pixel = spr.readPixel(x, y);
      if (prevFrame)
        prevFrame[idx] = pixel;
      if (run == 0)
      {
        runVal = pixel;
        run = 1;
      }
      else if (pixel == runVal && run < 255)
      {
        run++;
      }
      else
      {
        stream->write((uint8_t)run);
        stream->write((uint8_t)(runVal & 0xFF));
        stream->write((uint8_t)(runVal >> 8));
        runVal = pixel;
        run = 1;
      }
    }
  }
  if (run > 0)
  {
    stream->write((uint8_t)run);
    stream->write((uint8_t)(runVal & 0xFF));
    stream->write((uint8_t)(runVal >> 8));
  }
  prevFrameValid = true;
}

// ============================================================================
// Delta RLE (Delta-encoded Run-Length Encoding) Functions
// ============================================================================

static uint32_t deltaRleSize(uint16_t width, uint16_t height)
{
  if (!prevFrameValid || !prevFrame)
    return 0;
  uint32_t total = 0;
  uint32_t idx = 0;
  bool same = true;
  uint16_t run = 0;
  for (int y = height - 1; y >= 0; y--)
  {
    for (int x = 0; x < width; x++, idx++)
    {
      uint16_t pixel = spr.readPixel(x, y);
      bool curSame = (pixel == prevFrame[idx]);
      if (run == 0)
      {
        same = curSame;
        run = 1;
      }
      else if (curSame == same && run < 127)
      {
        run++;
      }
      else
      {
        total += same ? 1 : (1 + run * 2);
        same = curSame;
        run = 1;
      }
    }
  }
  if (run > 0)
    total += same ? 1 : (1 + run * 2);
  return total;
}

static void deltaRleEncode(Stream *stream, uint16_t width, uint16_t height)
{
  uint32_t idx = 0;
  bool same = true;
  uint16_t run = 0;
  uint16_t runPixels[127];
  uint16_t runCount = 0;

  for (int y = height - 1; y >= 0; y--)
  {
    for (int x = 0; x < width; x++, idx++)
    {
      uint16_t pixel = spr.readPixel(x, y);
      bool curSame = (pixel == prevFrame[idx]);
      if (run == 0)
      {
        same = curSame;
        run = 1;
        runCount = 0;
        if (!same)
          runPixels[runCount++] = pixel;
      }
      else if (curSame == same && run < 127)
      {
        run++;
        if (!same)
          runPixels[runCount++] = pixel;
      }
      else
      {
        uint8_t token = (same ? 0x80 : 0x00) | (uint8_t)run;
        stream->write(token);
        if (!same)
        {
          for (uint16_t i = 0; i < runCount; i++)
          {
            stream->write((uint8_t)(runPixels[i] & 0xFF));
            stream->write((uint8_t)(runPixels[i] >> 8));
          }
        }
        same = curSame;
        run = 1;
        runCount = 0;
        if (!same)
          runPixels[runCount++] = pixel;
      }
      prevFrame[idx] = pixel;
    }
  }

  if (run > 0)
  {
    uint8_t token = (same ? 0x80 : 0x00) | (uint8_t)run;
    stream->write(token);
    if (!same)
    {
      for (uint16_t i = 0; i < runCount; i++)
      {
        stream->write((uint8_t)(runPixels[i] & 0xFF));
        stream->write((uint8_t)(runPixels[i] >> 8));
      }
    }
  }
  prevFrameValid = true;
}

// ============================================================================
// Public API: Delta RLE Capture Handler
// ============================================================================

void remoteCaptureDeltaRle(Stream *stream)
{
  uint16_t width = spr.width();
  uint16_t height = spr.height();
  uint32_t count = (uint32_t)width * (uint32_t)height;
  uint32_t rawSize = count * 2;

  // Try delta RLE, but fall back to binary mode if PSRAM allocation fails
  if (!ensurePrevFrame(count))
  {
    remoteCaptureScreen(stream, true);
    return;
  }

  bool useDelta = prevFrameValid;
  uint8_t flags = useDelta ? COMP_FLAG_DELTA : 0x00;
  uint32_t payloadSize = useDelta ? deltaRleSize(width, height) : rleSizeFull(width, height);

  writeHeaderCompressed(stream, MAGIC_DELTA_RLE, flags, width, height, rawSize, payloadSize);

  if (useDelta)
  {
    deltaRleEncode(stream, width, height);
  }
  else
  {
    rleEncodeFull(stream, width, height);
  }

  delay(200);
}

// ============================================================================
// Public API: zlib/Raw Capture Handler
// ============================================================================

void remoteCaptureZlibRaw(Stream *stream)
{
  uint16_t width = spr.width();
  uint16_t height = spr.height();
  uint32_t rawSize = (uint32_t)width * (uint32_t)height * 2;

  uint8_t *raw = (uint8_t *)ps_malloc(rawSize);
  if (!raw)
  {
    // PSRAM allocation failed - can't compress
    // Send error header with zero payload
    writeHeaderCompressed(stream, MAGIC_ZLIB_RAW, COMP_FLAG_ERROR, width, height, rawSize, 0);
    return;
  }

  uint32_t idx = 0;
  for (int y = height - 1; y >= 0; y--)
  {
    for (int x = 0; x < width; x++)
    {
      uint16_t pixel = spr.readPixel(x, y);
      raw[idx++] = pixel & 0xFF;
      raw[idx++] = (pixel >> 8) & 0xFF;
    }
  }

  // Attempt compression using LZPacker
  uint8_t *compressed = nullptr;
  size_t compressedSize = 0;

  // Try LZPacker::compress with timeout protection
  // If it fails or hangs, the watchdog will catch it
  compressedSize = LZPacker::compress(raw, rawSize, &compressed);

  free(raw);

  // If compression produced valid output, use it
  if (compressedSize > 0 && compressed != nullptr && compressedSize < rawSize)
  {
    writeHeaderCompressed(stream, MAGIC_ZLIB_RAW, 0x00, width, height, rawSize, (uint32_t)compressedSize);
    streamWriteChunked(stream, compressed, compressedSize);
    free(compressed);
  }
  else
  {
    // Compression failed or produced invalid output, send error
    if (compressed)
      free(compressed);
    // Send error header with zero payload
    writeHeaderCompressed(stream, MAGIC_ZLIB_RAW, COMP_FLAG_ERROR, width, height, rawSize, 0);
  }

  delay(200);
}

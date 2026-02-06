#include "Common.h"
#include "Themes.h"
#include "Utils.h"
#include "Menu.h"
#include "Draw.h"
#include "Remote.h"
#include "Compression.h"
#include "CborRpc.h"

static uint8_t char2nibble(char key)
{
  if ((key >= '0') && (key <= '9'))
    return (key - '0');
  if ((key >= 'A') && (key <= 'F'))
    return (key - 'A' + 10);
  if ((key >= 'a') && (key <= 'f'))
    return (key - 'a' + 10);
  return (0);
}

static void writeHex32(Stream *stream, uint32_t value)
{
  stream->printf("%08x", (unsigned int)htonl(value));
}

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
// Capture current screen image to the remote
//
void remoteCaptureScreen(Stream *stream, bool binary)
{
  uint16_t width = spr.width();
  uint16_t height = spr.height();
  uint32_t imageSize = (uint32_t)(14 + 40 + 12 + width * height * 2);
  uint32_t pixelOffset = 14 + 40 + 12;

  if (!binary)
  {
    // 14 bytes of BMP header (hex mode)
    stream->println("");
    stream->print("424d"); // BM
    // Image size
    writeHex32(stream, imageSize);
    stream->print("00000000");
    // Offset to image data
    writeHex32(stream, pixelOffset);
    // Image header
    stream->print("28000000"); // Header size
    writeHex32(stream, width);
    writeHex32(stream, height);
    stream->print("01001000");   // 1 plane, 16 bpp
    stream->print("03000000");   // Compression
    stream->print("00000000");   // Compressed image size
    stream->print("00000000");   // X res
    stream->print("00000000");   // Y res
    stream->print("00000000");   // Color map
    stream->print("00000000");   // Colors
    stream->print("00f80000");   // Red mask
    stream->print("e0070000");   // Green mask
    stream->println("1f000000"); // Blue mask

    // Image data (hex mode)
    for (int y = height - 1; y >= 0; y--)
    {
      for (int x = 0; x < width; x++)
      {
        uint16_t pixel = spr.readPixel(x, y);
        stream->printf("%04x", htons(pixel));
      }
      stream->println("");
    }
  }
  else
  {
    // Binary mode with buffering for better BLE performance

    // Write BMP header
    uint8_t header[66];
    uint8_t *p = header;

    // File header (14 bytes)
    *p++ = 'B';
    *p++ = 'M';
    *p++ = imageSize & 0xFF;
    *p++ = (imageSize >> 8) & 0xFF;
    *p++ = (imageSize >> 16) & 0xFF;
    *p++ = (imageSize >> 24) & 0xFF;
    *p++ = 0;
    *p++ = 0;
    *p++ = 0;
    *p++ = 0; // Reserved
    *p++ = pixelOffset & 0xFF;
    *p++ = (pixelOffset >> 8) & 0xFF;
    *p++ = (pixelOffset >> 16) & 0xFF;
    *p++ = (pixelOffset >> 24) & 0xFF;

    // Info header (40 bytes)
    *p++ = 40;
    *p++ = 0;
    *p++ = 0;
    *p++ = 0; // Header size
    *p++ = width & 0xFF;
    *p++ = (width >> 8) & 0xFF;
    *p++ = (width >> 16) & 0xFF;
    *p++ = (width >> 24) & 0xFF;
    *p++ = height & 0xFF;
    *p++ = (height >> 8) & 0xFF;
    *p++ = (height >> 16) & 0xFF;
    *p++ = (height >> 24) & 0xFF;
    *p++ = 1;
    *p++ = 0; // Planes
    *p++ = 16;
    *p++ = 0; // Bits per pixel
    *p++ = 3;
    *p++ = 0;
    *p++ = 0;
    *p++ = 0; // Compression = BI_BITFIELDS
    *p++ = 0;
    *p++ = 0;
    *p++ = 0;
    *p++ = 0; // Image size
    *p++ = 0;
    *p++ = 0;
    *p++ = 0;
    *p++ = 0; // X pixels/meter
    *p++ = 0;
    *p++ = 0;
    *p++ = 0;
    *p++ = 0; // Y pixels/meter
    *p++ = 0;
    *p++ = 0;
    *p++ = 0;
    *p++ = 0; // Colors used
    *p++ = 0;
    *p++ = 0;
    *p++ = 0;
    *p++ = 0; // Important colors

    // Color masks (12 bytes)
    *p++ = 0x00;
    *p++ = 0xF8;
    *p++ = 0x00;
    *p++ = 0x00; // Red
    *p++ = 0xE0;
    *p++ = 0x07;
    *p++ = 0x00;
    *p++ = 0x00; // Green
    *p++ = 0x1F;
    *p++ = 0x00;
    *p++ = 0x00;
    *p++ = 0x00; // Blue

    stream->write(header, 66);

    // Buffer pixel data with stack allocation (avoid malloc failures on heap)
    // Use MTU-aligned 512-byte buffer for reliable BLE transfer
    uint8_t pixelBuffer[512];
    size_t bufferPos = 0;

    for (int y = height - 1; y >= 0; y--)
    {
      for (int x = 0; x < width; x++)
      {
        uint16_t pixel = spr.readPixel(x, y);

        // Flush buffer if adding next pixel would exceed capacity
        if ((bufferPos + 2) > (size_t)sizeof(pixelBuffer))
        {
          stream->write(pixelBuffer, bufferPos);
          bufferPos = 0;
        }

        // Add pixel to buffer (little-endian)
        pixelBuffer[bufferPos++] = pixel & 0xFF;
        pixelBuffer[bufferPos++] = (pixel >> 8) & 0xFF;
      }
    }

    // Flush all remaining data
    if (bufferPos > 0)
    {
      stream->write(pixelBuffer, bufferPos);
      bufferPos = 0;
    }

    // Explicit final delay to ensure last data is transmitted over BLE
    delay(500);
  }
}

char remoteReadChar(Stream *stream)
{
  char key;

  while (!stream->available())
    ;
  key = stream->read();
  stream->print(key);
  return key;
}

long int remoteReadInteger(Stream *stream)
{
  long int result = 0;
  while (true)
  {
    char ch = stream->peek();
    if (ch == 0xFF)
    {
      continue;
    }
    else if ((ch >= '0') && (ch <= '9'))
    {
      ch = remoteReadChar(stream);
      // Can overflow, but it's ok
      result = result * 10 + (ch - '0');
    }
    else
    {
      return result;
    }
  }
}

void remoteReadString(Stream *stream, char *bufStr, uint8_t bufLen)
{
  uint8_t length = 0;
  while (true)
  {
    char ch = stream->peek();
    if (ch == 0xFF)
    {
      continue;
    }
    else if (ch == ',' || ch < ' ')
    {
      bufStr[length] = '\0';
      return;
    }
    else
    {
      ch = remoteReadChar(stream);
      bufStr[length] = ch;
      if (++length >= bufLen - 1)
      {
        bufStr[length] = '\0';
        return;
      }
    }
  }
}

static bool expectNewline(Stream *stream)
{
  char ch;
  while ((ch = stream->peek()) == 0xFF)
    ;
  if (ch == '\r')
  {
    stream->read();
    return true;
  }
  return false;
}

static bool remoteShowError(Stream *stream, const char *message)
{
  // Consume the remaining input
  while (stream->available())
    remoteReadChar(stream);
  stream->printf("\r\nError: %s\r\n", message);
  return false;
}

static void remoteGetMemories(Stream *stream)
{
  for (uint8_t i = 0; i < getTotalMemories(); i++)
  {
    if (memories[i].freq)
    {
      stream->printf("#%02d,%s,%ld,%s\r\n", i + 1, bands[memories[i].band].bandName, memories[i].freq, bandModeDesc[memories[i].mode]);
    }
  }
}

static bool remoteSetMemory(Stream *stream)
{
  stream->print('#');
  Memory mem;
  uint32_t freq = 0;

  long int slot = remoteReadInteger(stream);
  if (remoteReadChar(stream) != ',')
    return remoteShowError(stream, "Expected ','");
  if (slot < 1 || slot > getTotalMemories())
    return remoteShowError(stream, "Invalid memory slot number");

  char band[8];
  remoteReadString(stream, band, 8);
  if (remoteReadChar(stream) != ',')
    return remoteShowError(stream, "Expected ','");
  mem.band = 0xFF;
  for (int i = 0; i < getTotalBands(); i++)
  {
    if (strcmp(bands[i].bandName, band) == 0)
    {
      mem.band = i;
      break;
    }
  }
  if (mem.band == 0xFF)
    return remoteShowError(stream, "No such band");

  freq = remoteReadInteger(stream);
  if (remoteReadChar(stream) != ',')
    return remoteShowError(stream, "Expected ','");

  char mode[4];
  remoteReadString(stream, mode, 4);
  if (!expectNewline(stream))
    return remoteShowError(stream, "Expected newline");
  stream->println();
  mem.mode = 15;
  for (int i = 0; i < getTotalModes(); i++)
  {
    if (strcmp(bandModeDesc[i], mode) == 0)
    {
      mem.mode = i;
      break;
    }
  }
  if (mem.mode == 15)
    return remoteShowError(stream, "No such mode");

  mem.freq = freq;

  if (!isMemoryInBand(&bands[mem.band], &mem))
  {
    if (!freq)
    {
      // Clear slot
      memories[slot - 1] = mem;
      return true;
    }
    else
    {
      // Handle duplicate band names (15M)
      mem.band = 0xFF;
      for (int i = getTotalBands() - 1; i >= 0; i--)
      {
        if (strcmp(bands[i].bandName, band) == 0)
        {
          mem.band = i;
          break;
        }
      }
      if (mem.band == 0xFF)
        return remoteShowError(stream, "No such band");
      if (!isMemoryInBand(&bands[mem.band], &mem))
        return remoteShowError(stream, "Invalid frequency or mode");
    }
  }

  memories[slot - 1] = mem;
  return true;
}

//
// Set current color theme from the remote
//
static void remoteSetColorTheme(Stream *stream)
{
  stream->print("Enter a string of hex colors (x0001x0002...): ");

  uint8_t *p = (uint8_t *)&(TH.bg);

  for (int i = 0;; i += sizeof(uint16_t))
  {
    if (i >= sizeof(ColorTheme) - offsetof(ColorTheme, bg))
    {
      stream->println(" Ok");
      break;
    }

    if (remoteReadChar(stream) != 'x')
    {
      stream->println(" Err");
      break;
    }

    p[i + 1] = char2nibble(remoteReadChar(stream)) * 16;
    p[i + 1] |= char2nibble(remoteReadChar(stream));
    p[i] = char2nibble(remoteReadChar(stream)) * 16;
    p[i] |= char2nibble(remoteReadChar(stream));
  }

  // Redraw screen
  drawScreen();
}

//
// Print current color theme to the remote
//
static void remoteGetColorTheme(Stream *stream)
{
  stream->printf("Color theme %s: ", TH.name);
  const uint8_t *p = (uint8_t *)&(TH.bg);

  for (int i = 0; i < sizeof(ColorTheme) - offsetof(ColorTheme, bg); i += sizeof(uint16_t))
  {
    stream->printf("x%02X%02X", p[i + 1], p[i]);
  }

  stream->println();
}

//
// Print current status to the remote
//
void remotePrintStatus(Stream *stream, RemoteState *state)
{
  // Prepare information ready to be sent
  float remoteVoltage = batteryMonitor();

  // S-Meter conditional on compile option
  rx.getCurrentReceivedSignalQuality();
  uint8_t remoteRssi = rx.getCurrentRSSI();
  uint8_t remoteSnr = rx.getCurrentSNR();

  // Use rx.getFrequency to force read of capacitor value from SI4732/5
  rx.getFrequency();
  uint16_t tuningCapacitor = rx.getAntennaTuningCapacitor();

  // Remote serial
  stream->printf("%u,%u,%d,%d,%s,%s,%s,%s,%hu,%hu,%hu,%hu,%hu,%.2f,%hu\r\n",
                 VER_APP,
                 currentFrequency,
                 currentBFO,
                 ((currentMode == USB) ? getCurrentBand()->usbCal : (currentMode == LSB) ? getCurrentBand()->lsbCal
                                                                                         : 0),
                 getCurrentBand()->bandName,
                 bandModeDesc[currentMode],
                 getCurrentStep()->desc,
                 getCurrentBandwidth()->desc,
                 agcIdx,
                 volume,
                 remoteRssi,
                 remoteSnr,
                 tuningCapacitor,
                 remoteVoltage,
                 state->remoteSeqnum);
}

//
// Tick remote time, periodically printing status
//
void remoteTickTime(Stream *stream, RemoteState *state)
{
  if (state->remoteLogOn && (millis() - state->remoteTimer >= 500))
  {
    // Mark time and increment diagnostic sequence number
    state->remoteTimer = millis();
    state->remoteSeqnum++;
    // Show status
    remotePrintStatus(stream, state);
  }
}

//
// Recognize and execute given remote command
//
int remoteDoCommand(Stream *stream, RemoteState *state, char key)
{
  int event = 0;

  switch (key)
  {
  case 'R': // Rotate Encoder Clockwise
    event |= 1 << REMOTE_DIRECTION;
    event |= REMOTE_PREFS;
    break;
  case 'r': // Rotate Encoder Counterclockwise
    event |= -1 << REMOTE_DIRECTION;
    event |= REMOTE_PREFS;
    break;
  case 'e': // Encoder Push Button
    event |= REMOTE_CLICK;
    break;
  case 'B': // Band Up
    doBand(1);
    event |= REMOTE_PREFS;
    break;
  case 'b': // Band Down
    doBand(-1);
    event |= REMOTE_PREFS;
    break;
  case 'M': // Mode Up
    doMode(1);
    event |= REMOTE_PREFS;
    break;
  case 'm': // Mode Down
    doMode(-1);
    event |= REMOTE_PREFS;
    break;
  case 'S': // Step Up
    doStep(1);
    event |= REMOTE_PREFS;
    break;
  case 's': // Step Down
    doStep(-1);
    event |= REMOTE_PREFS;
    break;
  case 'W': // Bandwidth Up
    doBandwidth(1);
    event |= REMOTE_PREFS;
    break;
  case 'w': // Bandwidth Down
    doBandwidth(-1);
    event |= REMOTE_PREFS;
    break;
  case 'A': // AGC/ATTN Up
    doAgc(1);
    event |= REMOTE_PREFS;
    break;
  case 'a': // AGC/ATTN Down
    doAgc(-1);
    event |= REMOTE_PREFS;
    break;
  case 'V': // Volume Up
    doVolume(1);
    event |= REMOTE_PREFS;
    break;
  case 'v': // Volume Down
    doVolume(-1);
    event |= REMOTE_PREFS;
    break;
  case 'L': // Backlight Up
    doBrt(1);
    event |= REMOTE_PREFS;
    break;
  case 'l': // Backlight Down
    doBrt(-1);
    event |= REMOTE_PREFS;
    break;
  case 'O':
    sleepOn(true);
    break;
  case 'o':
    sleepOn(false);
    break;
  case 'I':
    doCal(1);
    event |= REMOTE_PREFS;
    break;
  case 'i':
    doCal(-1);
    event |= REMOTE_PREFS;
    break;
  case 'C':
    state->remoteLogOn = false;
    remoteCaptureScreen(stream, false);
    break;
  case 'c':
    state->remoteLogOn = false;
    remoteCaptureScreen(stream, true);
    break;
  case 'd':
    state->remoteLogOn = false;
    remoteCaptureDeltaRle(stream);
    break;
  case 'z':
    state->remoteLogOn = false;
    remoteCaptureZlibRaw(stream);
    break;
  case 't':
    state->remoteLogOn = !state->remoteLogOn;
    break;

  case '$':
    remoteGetMemories(stream);
    break;
  case '#':
    if (remoteSetMemory(stream))
      event |= REMOTE_PREFS;
    break;

  case 'T':
    stream->println(switchThemeEditor(!switchThemeEditor()) ? "Theme editor enabled" : "Theme editor disabled");
    break;
  case '^':
    if (switchThemeEditor())
      remoteSetColorTheme(stream);
    break;
  case '@':
    if (switchThemeEditor())
      remoteGetColorTheme(stream);
    break;

  default:
    // Command not recognized
    return (event);
  }

  // Command recognized
  return (event | REMOTE_CHANGED);
}

int serialDoCommand(Stream *stream, RemoteState *state, uint8_t usbMode)
{
  if (usbMode == USB_OFF)
    return 0;

  if (state->rpcMode)
  {
    CborRpcWriter writer = {stream, cborRpcSendFrameStream};
    cborRpcConsumeStream(stream, state, &writer);
    return 0;
  }

  if (Serial.available())
  {
    uint8_t key = Serial.read();
    if (key == CBOR_RPC_SWITCH)
    {
      state->rpcMode = true;
      cborRpcResetState(state);
      state->remoteTimer = millis();
      return 0;
    }
    return remoteDoCommand(stream, state, key);
  }
  return 0;
}

void serialTickTime(Stream *stream, RemoteState *state, uint8_t usbMode)
{
  if (usbMode == USB_OFF)
    return;

  if (state->rpcMode)
  {
    cborRpcTickTime(stream, state);
    return;
  }

  remoteTickTime(stream, state);
}

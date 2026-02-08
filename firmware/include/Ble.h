#ifndef BLE_H
#define BLE_H

#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <BLE2902.h>
#include <array>
#include <string>

#include "Remote.h"

#define NORDIC_UART_SERVICE_UUID "6E400001-B5A3-F393-E0A9-E50E24DCCA9E"
#define NORDIC_UART_CHARACTERISTIC_UUID_RX "6E400002-B5A3-F393-E0A9-E50E24DCCA9E"
#define NORDIC_UART_CHARACTERISTIC_UUID_TX "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"

class NordicUART : public Stream, public BLEServerCallbacks, public BLECharacteristicCallbacks
{
private:
  // BLE components
  BLEServer *pServer;
  BLEService *pService;
  BLECharacteristic *pTxCharacteristic;
  BLECharacteristic *pRxCharacteristic;

  // Connection management
  bool started;

  // Data handling
  std::string incomingPacket;
  size_t unreadByteCount = 0;
  static constexpr size_t kRxQueueDepth = 4;
  std::array<std::string, kRxQueueDepth> rxQueue;
  size_t rxQueueHead = 0;
  size_t rxQueueTail = 0;
  size_t rxQueueCount = 0;

  // Device attributes
  const char *deviceName;

public:
  NordicUART(const char *name) : deviceName(name)
  {
    started = false;
    pServer = nullptr;
    pService = nullptr;
    pTxCharacteristic = nullptr;
    pRxCharacteristic = nullptr;
  }

  void clearRxQueue()
  {
    incomingPacket.clear();
    unreadByteCount = 0;
    rxQueueHead = 0;
    rxQueueTail = 0;
    rxQueueCount = 0;
  }

  void enqueueRxPacket(std::string &&value)
  {
    if (unreadByteCount == 0 && rxQueueCount == 0)
    {
      incomingPacket = std::move(value);
      unreadByteCount = incomingPacket.size();
      return;
    }

    if (rxQueueCount >= kRxQueueDepth)
    {
      return; // Drop newest packet if queue is full
    }

    rxQueue[rxQueueTail] = std::move(value);
    rxQueueTail = (rxQueueTail + 1) % kRxQueueDepth;
    rxQueueCount++;
  }

  void start()
  {
    BLEDevice::init(deviceName);
    BLEDevice::setPower(ESP_PWR_LVL_N0);

    BLEDevice::setMTU(517);

    pServer = BLEDevice::createServer();

    pServer->setCallbacks(this); // onConnect/onDisconnect
    pServer->getAdvertising()->addServiceUUID(NORDIC_UART_SERVICE_UUID);
    pService = pServer->createService(NORDIC_UART_SERVICE_UUID);
    // Use NOTIFY with retry logic for high-throughput reliable delivery
    pTxCharacteristic = pService->createCharacteristic(NORDIC_UART_CHARACTERISTIC_UUID_TX, BLECharacteristic::PROPERTY_NOTIFY);
    // Add CCCD descriptor so clients can enable notifications
    pTxCharacteristic->addDescriptor(new BLE2902());
    pTxCharacteristic->setCallbacks(this); // onSubscribe/onStatus
    pRxCharacteristic = pService->createCharacteristic(NORDIC_UART_CHARACTERISTIC_UUID_RX, BLECharacteristic::PROPERTY_WRITE);
    pRxCharacteristic->setCallbacks(this); // onWrite
    pService->start();
    pServer->getAdvertising()->start();
    started = true;
  }

  void stop()
  {
    if (pServer)
    {
      pServer->getAdvertising()->stop();
      pService->stop();
      pRxCharacteristic = nullptr;
      pTxCharacteristic = nullptr;
      pService = nullptr;
    }
    BLEDevice::deinit(false);
    started = false;
  }

  bool isStarted()
  {
    return started;
  }

  int connectedCount()
  {
    return (pServer != nullptr) ? pServer->getConnectedCount() : 0;
  }

  // Arduino BLE callbacks (BlueDroid API)
  void onConnect(BLEServer *pServer)
  {
    // BlueDroid callback signature - no access to low-level PHY/MTU settings
    // These would require NimBLE API which isn't available in Arduino framework
  }

  void onDisconnect(BLEServer *pServer)
  {
    clearRxQueue();
    pServer->getAdvertising()->start();
  }

  void onWrite(BLECharacteristic *pCharacteristic)
  {
    if (pCharacteristic == pRxCharacteristic)
    {
      // Non-blocking: enqueue packet or drop if queue is full
      std::string value = pCharacteristic->getValue();
      enqueueRxPacket(std::move(value));
    }
  }

  void onStatus(BLECharacteristic *pCharacteristic, Status s, uint32_t code)
  {
    // Status callback for debugging if needed
  }

  int available()
  {
    return unreadByteCount;
  }

  int peek()
  {
    if (unreadByteCount > 0)
    {
      size_t index = incomingPacket.size() - unreadByteCount;
      return static_cast<uint8_t>(incomingPacket[index]);
    }
    return -1;
  }

  int read()
  {
    if (unreadByteCount > 0)
    {
      size_t index = incomingPacket.size() - unreadByteCount;
      int result = static_cast<uint8_t>(incomingPacket[index]);
      unreadByteCount--;
      if (unreadByteCount == 0 && rxQueueCount > 0)
      {
        incomingPacket = std::move(rxQueue[rxQueueHead]);
        rxQueueHead = (rxQueueHead + 1) % kRxQueueDepth;
        rxQueueCount--;
        unreadByteCount = incomingPacket.size();
      }
      return result;
    }
    return -1;
  }

  size_t write(const uint8_t *data, size_t size)
  {
    if (pTxCharacteristic)
    {
      // Data is sent in chunks of (MTU - 3) to account for ATT header
      // Guard against underflow: if MTU <= 3, use safe default payload size
      uint16_t mtu = BLEDevice::getMTU();
      size_t chunkSize = (mtu > 3) ? (mtu - 3) : 20;
      size_t remainingByteCount = size;
      uint8_t *mutableData = (uint8_t *)data; // Cast away const for BLE API

      // Delay after each notification to ensure reliable delivery
      while (remainingByteCount >= chunkSize)
      {
        pTxCharacteristic->setValue(mutableData, chunkSize);
        pTxCharacteristic->notify();
        mutableData += chunkSize;
        remainingByteCount -= chunkSize;
        delay(5); // Minimal delay for 512-byte single-chunk writes
      }
      if (remainingByteCount > 0)
      {
        pTxCharacteristic->setValue(mutableData, remainingByteCount);
        pTxCharacteristic->notify();
      }
      // Final delay to ensure last data is transmitted
      delay(100);
      return size;
    }
    else
      return 0;
  }

  size_t write(uint8_t byte)
  {
    return write(&byte, 1);
  }

  size_t print(std::string str)
  {
    return write((const uint8_t *)str.data(), str.length());
  }

  size_t printf(const char *format, ...)
  {
    char dummy;
    va_list args;
    va_start(args, format);
    int requiredSize = vsnprintf(&dummy, 1, format, args);
    va_end(args);
    if (requiredSize <= 0)
    {
      return 0;
    }

    char *buffer = (char *)malloc(requiredSize + 1);
    if (buffer)
    {
      va_start(args, format);
      int result = vsnprintf(buffer, requiredSize + 1, format, args);
      va_end(args);
      if ((result > 0) && (result <= requiredSize))
      {
        size_t writtenBytesCount = write((uint8_t *)buffer, result);
        free(buffer);
        return writtenBytesCount;
      }
      free(buffer);
    }
    return 0;
  }
};

void bleInit(uint8_t bleMode);
void bleStop();
int8_t getBleStatus();
void remoteBLETickTime(Stream *stream, RemoteState *state, uint8_t bleMode);
int bleDoCommand(Stream *stream, RemoteState *state, uint8_t bleMode);
extern NordicUART BLESerial;

#endif

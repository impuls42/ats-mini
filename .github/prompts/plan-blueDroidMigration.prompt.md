# BlueDroid Migration Plan

## Overview
Migrate from NimBLE API (incompatible with Arduino-esp32 3.3.5) to BlueDroid API (built-in, fully compatible).

**Scope:** 2 direct API calls + complete Ble.h refactor

---

## Phase 1: Understanding the APIs

### NimBLE Callback (Current - BROKEN)
```cpp
void onWrite(BLECharacteristic *pCharacteristic, ble_gap_conn_desc *desc)
{
  if(pCharacteristic == pRxCharacteristic) { ... }
}

void onConnect(BLEServer *pServer, ble_gap_conn_desc *desc) { ... }
```

### BlueDroid Callback (Target - COMPATIBLE)
```cpp
void onWrite(BLECharacteristic *pCharacteristic)
{
  if(pCharacteristic == pRxCharacteristic) { ... }
}

void onConnect(BLEServer *pServer) { ... }

void onDisconnect(BLEServer *pServer) { ... }  // Called on disconnect
```

**Key Difference:** BlueDroid uses separate methods for callbacks, doesn't pass connection descriptor.

---

## Phase 2: Identify All Changes

### File: `firmware/include/Ble.h`
- [ ] Line 8: Remove `#include "host/ble_gap.h"`
- [ ] Line 27: Remove `uint16_t connHandle = BLE_HS_CONN_HANDLE_NONE;`
- [ ] Constructor: Remove connHandle initialization
- [ ] `onConnect()`: Change signature to `onConnect(BLEServer *pServer)`, remove PHY/data-len calls
- [ ] `onWrite()`: Change signature to `onWrite(BLECharacteristic *)`, remove `ble_gap_conn_desc` param
- [ ] `start()`: Remove `ble_gap_set_prefered_default_le_phy()` calls
- [ ] `start()`: Remove `ble_gap_write_sugg_def_data_len()` calls

**Impact:** onConnect loses ability to set PHY mode and data length (loss of low-level optimization)

### File: `firmware/src/Network.cpp`
- [ ] Line 315: Replace `wifiMulti.APlistClean()` with `wifiMulti.cleanAPlist()` or removal

**Impact:** WiFi API change only, functionality preserved

### File: `firmware/src/Ble.cpp`
- [ ] Check for any references to `ble_gap_*` or `ble_gap_conn_desc`

---

## Phase 3: Migration Details

### 3.1 Ble.h - Headers
**Before:**
```cpp
#include "host/ble_gap.h"
#include <semaphore>
```

**After:**
```cpp
#include <freertos/semphr.h>  // Use FreeRTOS semaphores (already in code)
```

### 3.2 Ble.h - Remove Connection Handle
**Before:**
```cpp
uint16_t connHandle = BLE_HS_CONN_HANDLE_NONE;
```

**After:**
```cpp
// Note: Connection handle not needed for BlueDroid callbacks
// Connections tracked via BLEServer instance
```

### 3.3 Ble.h - onConnect() Callback
**Before:**
```cpp
void onConnect(BLEServer *pServer, ble_gap_conn_desc *desc) {
  ble_gap_set_prefered_le_phy(desc->conn_handle, BLE_GAP_LE_PHY_ANY_MASK, ...);
  ble_gap_set_data_len(desc->conn_handle, 251, (251 + 14) * 8);
  pServer->updateConnParams(desc->conn_handle, 6, 12, 0, 200);
}
```

**After:**
```cpp
void onConnect(BLEServer *pServer) {
  // BlueDroid callback - basic connection setup only
  // PHY negotiation and data length settings happen automatically
  // Connection parameters set during characteristic setup
}
```

### 3.4 Ble.h - onWrite() Callback
**Before:**
```cpp
void onWrite(BLECharacteristic *pCharacteristic, ble_gap_conn_desc *desc) {
  if(pCharacteristic == pRxCharacteristic) {
    dataConsumed.acquire();
    incomingPacket = pCharacteristic->getValue();
    unreadByteCount = incomingPacket.length();
  }
}
```

**After:**
```cpp
void onWrite(BLECharacteristic *pCharacteristic) {
  if(pCharacteristic == pRxCharacteristic) {
    if (dataConsumedSem != nullptr) {
      xSemaphoreTake(dataConsumedSem, portMAX_DELAY);
    }
    std::string value = pCharacteristic->getValue();
    incomingPacket = String(value.c_str());
    unreadByteCount = incomingPacket.length();
  }
}
```

### 3.5 Ble.h - start() Method
**Before:**
```cpp
void start() {
  BLEDevice::init(deviceName);
  BLEDevice::setPower(ESP_PWR_LVL_N0);
  BLEDevice::getAdvertising()->setName(deviceName);
  
  BLEDevice::setMTU(517);
  ble_gap_set_prefered_default_le_phy(BLE_GAP_LE_PHY_ANY_MASK, ...);
  ble_gap_write_sugg_def_data_len(251, (251 + 14) * 8);
  
  pServer = BLEDevice::getServer();
  // ... rest of init
}
```

**After:**
```cpp
void start() {
  BLEDevice::init(deviceName);
  BLEDevice::setPower(ESP_PWR_LVL_N0);
  BLEDevice::getAdvertising()->setName(deviceName);
  
  BLEDevice::setMTU(517);  // Keep - controls chunk size for writes
  // Remove ble_gap_* calls - not available in BlueDroid
  
  pServer = BLEDevice::createServer();
  // ... rest of init
}
```

### 3.6 Network.cpp - WiFiMulti API
**Before:**
```cpp
wifiMulti.APlistClean();
```

**After:**
```cpp
// Option 1: Simply remove if not critical
// Option 2: Use newer API name
wifiMulti.cleanAPlist();  // Check if available
// Option 3: Just don't call it (list is cleaned on new add)
```

---

## Phase 4: Testing Strategy

1. **Syntax Check:** Compile with `pio run -e esp32s3-ospi 2>&1 | grep error`
2. **Runtime Test:** Verify BLE advertises properly
3. **Functional Test:** Connect with mobile app, test send/receive
4. **Regression Test:** Ensure radio functionality unchanged

---

## Phase 5: Known Limitations of BlueDroid vs NimBLE

| Feature | NimBLE | BlueDroid | Impact |
|---------|--------|-----------|--------|
| PHY Negotiation | ✅ (automatic + controllable) | ✅ (automatic only) | Slightly slower in rare cases |
| Data Length Extension | ✅ (automatic + controllable) | ✅ (automatic only) | Reduced throughput in older devices |
| Connection Parameters | ✅ Full control | ✅ Via updateConnParams | Can still optimize |
| MTU Setting | ✅ Full control | ✅ Full control | Unchanged |
| Callback Signatures | ✅ Connection info available | ❌ Not in callback | Lose access to conn descriptor |

**Bottom line:** Slight performance degradation in edge cases, but full functionality preserved.

---

## Phase 6: Implementation Order

1. Fix Network.cpp WiFi API (trivial, safe)
2. Rewrite Ble.h completely for BlueDroid
3. Test compilation
4. Test at runtime
5. Validate BLE functionality

---

## Effort Estimate
- **Phase 1-2:** 10 minutes (planning/analysis)
- **Phase 3:** 20 minutes (code changes)
- **Phase 4:** 10 minutes (testing)
- **Total:** ~40 minutes

**Ready to proceed?** I can implement all changes in Phase 3 once you confirm the plan above.

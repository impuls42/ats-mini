# Flashing the firmware

```{warning}
Flashing the firmware can make your receiver unusable.
```

Before proceeding, please check whether the receiver board has [BOOT & RESET buttons](hardware.md#boot-and-reset-buttons) soldered, which can help to [recover](recovery.md#recovery) it. Also there is a way to [back up](recovery.md#backup) the stock firmware, so you can roll back to it if you want.

## Partition layout

The ESP32-S3 flash is divided into several partitions:

| Partition | Type | Offset | Size | Purpose |
|-----------|------|--------|------|---------|
| (bootloader) | - | 0x0 | ~15KB | ESP32-S3 bootloader - initializes chip, loads firmware |
| (partition table) | - | 0x8000 | 3KB | Partition table - defines all partition locations/sizes |
| **nvs** | data/nvs | 0x9000 | 20KB | System non-volatile storage - WiFi credentials, calibration data |
| **otadata** | data/ota | 0xe000 | 8KB | OTA (Over-The-Air) update metadata - tracks active firmware slot |
| **app0** | app/ota_0 | 0x10000 | 3MB | Primary firmware slot - main application code |
| **app1** | app/ota_1 | 0x310000 | 3MB | Secondary firmware slot - OTA updates (currently unused) |
| **littlefs** | data/spiffs | 0x610000 | 1.8MB | LittleFS filesystem - theme files, SSB patches, user data |
| **settings** | data/nvs | 0x7e0000 | 64KB | Application settings - frequency, band, volume, preferences |
| **coredump** | data/coredump | 0x7f0000 | 64KB | Core dump storage - crash diagnostics (for debugging) |

**Important notes:**
- **app0** at 0x10000 is the active firmware partition. Standard flashing writes here.
- **settings** partition stores all user preferences. It survives firmware updates (unless flashing merged binary at 0x0).
- **littlefs** contains the SSB patch and theme archives. Flashing firmware normally preserves this data.
- **nvs** and **otadata** are managed by the ESP32 system. User settings are in the **settings** partition.
- Total flash size: 8MB (0x800000 bytes)

When you flash the **merged binary** at offset 0x0, it overwrites bootloader, partition table, and firmware, which resets the **nvs** and **settings** partitions. When you flash the three separate files (bootloader, partitions, firmware), the **settings** partition typically survives, preserving your configuration.

## Firmware files

```{hint}
The firmware releases are available on [GitHub](https://github.com/esp32-si4732/ats-mini/releases). You'll need either OSPI or QSPI variant depending on the ESP32-S3 PSRAM type, see the following table:

![](_static/esp32-psram-variants.png)

With the right firmware variant you should see a non-zero PSRAM amount on the Settings->About system info screen. Also check out the following discussion: [OSPI vs QSPI: How can I see what I have?](https://github.com/esp32-si4732/ats-mini/discussions/174).
```

A firmware archive contains the following files:

1. `CHANGELOG.md` - a text file that describes what's new in each firmware version
2. `bootloader.bin` - ESP32-S3 bootloader (should be flashed at address **`0x0`**)
3. `partitions.bin` - partition table (should be flashed at address **`0x8000`**)
4. `firmware.bin` - main application firmware (should be flashed at address **`0x10000`**)
5. `firmware.elf` - firmware with debug symbols (for crash analysis, not flashed)
6. `firmware.merged.bin` - all three binaries combined into one (should be flashed at address **`0x0`**)

So, you need to flash your receiver using **just one** of the following two ways:

- Flash the three separate files (**2** - `bootloader`, **3** - `partitions`, **4** - `firmware`) using the right addresses. Your receiver settings will be preserved.

**OR**

- Only flash the merged file (**6** - `firmware.merged`) at address **`0x0`**. This will erase all settings and reset the receiver to defaults.

## Flash using a web browser

Works on: Windows, macOS, Linux

This is the simplest method, but you need a browser that supports the [Web Serial API](https://developer.mozilla.org/en-US/docs/Web/API/Web_Serial_API). This means Chrome and [some other browsers](https://developer.mozilla.org/en-US/docs/Web/API/Web_Serial_API#browser_compatibility). No, Firefox and Safari can't do it.

```{tip}
On Linux, please make sure that the user account that runs your browser has the [necessary permissions](https://www.reddit.com/r/linuxquestions/comments/vqzev0/browser_serial_port_fails_to_open/) to access the serial port.
```

1. Connect your receiver to a computer using USB and power it on.
2. A new serial port should appear. On Windows check the USB Serial COM port in the Windows Device Manager, on macOS it will look like `/dev/tty.usbmodemXXXX`, on Linux like `/dev/ttyACMX`.
3. Open the following link: <https://espressif.github.io/esptool-js/>
4. Press the `Connect` button and choose the right serial port.
5. Add either the three separate firmware files at the [right addresses](#firmware-files), or the merged one at `0x0`.
6. Press the `Program` button.
7. Wait until the following text will appear in the black serial log window: `Leaving... Hard resetting via RTS pin...`
8. Press the `Disconnect` button.
9. Power off and power on the receiver.
10. Check out the firmware version in Menu -> Settings -> About on the receiver.

![](_static/esp-web-flasher.png)

## Flash Download Tool

Works on: Windows

1. Download the Expressif [Flash Download Tool](https://docs.espressif.com/projects/esp-test-tools/en/latest/esp32/production_stage/tools/flash_download_tool.html), unpack the archive.
2. Connect your receiver to a computer using USB and power it on.
3. A new serial port should appear, check the USB Serial COM port in the Windows Device Manager.
4. Run the `flash_dowload_tool` executable file.
5. Choose `Chip Type: ESP32-S3`, `WorkMode: Develop`, `LoadMode: UART`.
6. Add either the three separate firmware files at the [right addresses](#firmware-files), or the merged one at `0x0`. Enable the check boxes next to the file bars.
7. Set the COM port and other settings.
8. After checking all information is correct, press the `START` button.
9. Wait until the following text will appear in the black log window: `is stub and send flash finish`
10. Power off and power on the receiver.
11. Check out the firmware version in Menu -> Settings -> About on the receiver.

![](_static/flash-download-tool.png)

## esptool.py

Works on: Windows, macOS, Linux

1. Install `uv` (Windows, macOS, Linux) <https://docs.astral.sh/uv/getting-started/installation/>
2. Connect your receiver to a computer using USB and power it on.
3. A new serial port should appear. On Windows check the USB Serial COM port in the Windows Device Manager, on macOS it will look like `/dev/tty.usbmodemXXXX`, on Linux like `/dev/ttyACMX`.
3. Run **just one** of the two following commands (the first one uses three separate firmware files, the second one uses the single merged firmware file):
   ```shell
   uvx --from esptool esptool --chip esp32s3 --port SERIAL_PORT --baud 921600 --before default-reset --after hard-reset write_flash -z --flash-mode keep --flash-freq keep --flash-size keep 0x0 bootloader.bin 0x8000 partitions.bin 0x10000 firmware.bin

   # OR

   uvx --from esptool esptool --chip esp32s3 --port SERIAL_PORT --baud 921600 --before default-reset --after hard-reset write_flash -z --flash-mode keep --flash-freq keep --flash-size keep 0x0 firmware.merged.bin
   ```
4. Check out the firmware version in Menu -> Settings -> About on the receiver.

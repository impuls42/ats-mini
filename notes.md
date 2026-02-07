```
esptool.py --chip esp32s3 --no-stub --port /dev/ttyACM0 --baud 115200 \
  write_flash --flash_mode qio --flash_size 8MB \
  0x0 .pio/build/esp32s3-qspi/bootloader.bin \
  0x8000 .pio/build/esp32s3-qspi/partitions.bin \
  0xe000 ~/.platformio/packages/framework-arduinoespressif32/tools/partitions/boot_app0.bin \
  0x10000 .pio/build/esp32s3-qspi/firmware.bin
```
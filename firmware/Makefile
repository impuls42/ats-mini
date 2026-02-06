# PlatformIO wrapper Makefile for ATS-Mini Firmware
# Delegates to PlatformIO in the repo root (platformio.ini is at root)
# All pio commands run from repo root via 'cd ..' before execution

.PHONY: all help build upload monitor clean test debug

# Configuration
PROFILE ?= esp32s3-ospi
PORT ?= /dev/cu.usbmodem1101
DEBUG_LEVEL ?= 0

# Build flags
BUILD_FLAGS = -DDEBUG=$(DEBUG_LEVEL)
ifdef HALF_STEP
  BUILD_FLAGS += -DHALF_STEP
endif

# PlatformIO command
PIO = pio

# Default target
all: build

help:
	@echo "ATS-Mini Firmware Build"
	@echo ""
	@echo "Targets:"
	@echo "  make build     - Build firmware (default: esp32s3-ospi)"
	@echo "  make upload    - Build and upload"
	@echo "  make monitor   - Open serial monitor"
	@echo "  make clean     - Clean build artifacts"
	@echo ""
	@echo "Options:"
	@echo "  PROFILE=esp32s3-ospi  - OPI PSRAM (default)"
	@echo "  PROFILE=esp32s3-qspi  - QSPI PSRAM"
	@echo "  PORT=/dev/cu.usbmodem1101"
	@echo "  DEBUG_LEVEL=1"
	@echo "  HALF_STEP=1"
	@echo ""

build:
	@echo "Building: $(PROFILE)"
	@cd .. && $(PIO) run -e $(PROFILE)

upload: build
	@echo "Uploading to $(PORT)"
	@cd .. && $(PIO) run -e $(PROFILE) -t upload --upload-port $(PORT)

monitor:
	@echo "Monitor: $(PORT) @ 115200"
	@cd .. && $(PIO) device monitor -p $(PORT) -b 115200

clean:
	@echo "Cleaning..."
	@cd .. && $(PIO) run -t clean
	rm -rf build/


.PHONY: all help build upload monitor clean

.PHONY: help build upload monitor clean debug debug-build debug-upload

PROFILE ?= esp32s3-ospi
PORT ?= /dev/cu.usbmodem1101
DEBUG_LEVEL ?= 0
PIO = pio

# Build flags
BUILD_FLAGS = -DDEBUG=$(DEBUG_LEVEL)
ifdef HALF_STEP
  BUILD_FLAGS += -DHALF_STEP
endif

help:
	@echo "ATS-Mini Firmware Build"
	@echo ""
	@echo "Targets:"
	@echo "  make build     - Build firmware"
	@echo "  make upload    - Build and upload to device"
	@echo "  make monitor   - Open serial monitor"
	@echo "  make clean     - Clean build artifacts"
	@echo ""
	@echo "Debug Targets:"
	@echo "  make debug-build  - Build firmware with debug symbols"
	@echo "  make debug-upload - Build and upload debug firmware"
	@echo "  make debug        - Start debugging session (VSCode/CLI)"
	@echo ""
	@echo "Options:"
	@echo "  PROFILE=esp32s3-ospi  - OPI PSRAM (default)"
	@echo "  PROFILE=esp32s3-qspi  - QSPI PSRAM"
	@echo "  PORT=/dev/cu.usbmodem1101"
	@echo "  DEBUG_LEVEL=1         - Enable debug output (default: 0)"
	@echo "  HALF_STEP=1           - Enable encoder half-steps"
	@echo ""
	@echo "Examples:"
	@echo "  make build"
	@echo "  make build PROFILE=esp32s3-qspi"
	@echo "  make upload PORT=/dev/cu.usbmodem1101"
	@echo "  make build DEBUG_LEVEL=1 HALF_STEP=1"
	@echo "  make debug-build PROFILE=esp32s3-qspi"
	@echo ""

build:
	@echo "Building: $(PROFILE) [$(BUILD_FLAGS)]"
	$(PIO) run -e $(PROFILE)

upload: build
	@echo "Uploading to $(PORT)"
	$(PIO) run -e $(PROFILE) -t upload --upload-port $(PORT)

monitor:
	@echo "Monitor: $(PORT) @ 115200"
	$(PIO) device monitor -p $(PORT) -b 115200

clean:
	@echo "Cleaning build artifacts..."
	$(PIO) run -t clean
	rm -rf build/

# Debug targets
debug-build:
	@echo "Building debug: $(PROFILE)-debug [$(BUILD_FLAGS)]"
	$(PIO) run -e $(PROFILE)-debug

debug-upload: debug-build
	@echo "Uploading debug build to $(PORT)"
	$(PIO) run -e $(PROFILE)-debug -t upload --upload-port $(PORT)

debug:
	@echo "Starting debug session for $(PROFILE)-debug on $(PORT)"
	@echo "Use VSCode 'Run and Debug' panel or:"
	$(PIO) debug -e $(PROFILE)-debug --interface=gdb -x .piodebugger/launch.gdb

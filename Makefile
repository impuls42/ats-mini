.PHONY: help build upload fullflash monitor clean debug debug-build debug-upload test-serial test-ws full-test

SHELL := /bin/bash
PROFILE ?= esp32s3-ospi
ATSMINI_PORT ?= /dev/cu.usbmodem1101
PORT ?= $(ATSMINI_PORT)
DEBUG_LEVEL ?= 0
PIO = pio

# Build flags
BUILD_FLAGS = -DDEBUG=$(DEBUG_LEVEL)
ifdef HALF_STEP
  BUILD_FLAGS += -DHALF_STEP
endif

# Export build flags as environment variable for PlatformIO
export PLATFORMIO_BUILD_FLAGS = $(BUILD_FLAGS)

# Logging setup
ifdef LOGFILE
  LOG_DIR := $(dir $(LOGFILE))
  EXEC = @mkdir -p $(LOG_DIR); set -o pipefail;
  LOG_PIPE = 2>&1 | tee -a $(LOGFILE)
else
  EXEC = @
  LOG_PIPE =
endif

help:
	@echo "ATS-Mini Firmware Build"
	@echo ""
	@echo "Targets:"
	@echo "  make build     - Build firmware"
	@echo "  make upload    - Build and upload to device"
	@echo "  make fullflash - Build and upload full flash image (use after erase-flash)"
	@echo "  make monitor   - Open serial monitor"
	@echo "  make clean     - Clean build artifacts"
	@echo ""
	@echo "Debug Targets:"
	@echo "  make debug-build  - Build firmware with debug symbols"
	@echo "  make debug-upload - Build and upload debug firmware"
	@echo "  make debug        - Start debugging session (VSCode/CLI)"
	@echo ""
	@echo "Test Targets:"
	@echo "  make test-serial - Run serial RPC integration tests"
	@echo "  make test-ws     - Run WebSocket RPC integration tests"
	@echo "  make full-test   - Run all integration tests (requires hardware)"
	@echo ""
	@echo "Options:"
	@echo "  PROFILE=esp32s3-ospi  - OPI PSRAM (default)"
	@echo "  PROFILE=esp32s3-qspi  - QSPI PSRAM"
	@echo "  PORT=/dev/cu.usbmodem1101"
	@echo "  DEBUG_LEVEL=1         - Enable debug output (default: 0)"
	@echo "  HALF_STEP=1           - Enable encoder half-steps"
	@echo "  LOGFILE=path/to/log   - Log all output to file"
	@echo ""
	@echo "Examples:"
	@echo "  make build"
	@echo "  make build PROFILE=esp32s3-qspi"
	@echo "  make upload PORT=/dev/cu.usbmodem1101"
	@echo "  make build DEBUG_LEVEL=1 HALF_STEP=1"
	@echo "  make debug-build PROFILE=esp32s3-qspi"
	@echo "  LOGFILE=logs/build.log make build"
	@echo "  PORT=/dev/cu.usbmodem1101 LOGFILE=logs/test.log make full-test"
	@echo ""

build:
	$(EXEC) (echo "Building: $(PROFILE) [$(BUILD_FLAGS)]"; $(PIO) run -e $(PROFILE)) $(LOG_PIPE)

upload: build
	$(EXEC) (echo "Uploading to $(PORT)"; $(PIO) run -e $(PROFILE) -t upload --upload-port $(PORT)) $(LOG_PIPE)

fullflash: build
	$(EXEC) (echo "Full flash to $(PORT)"; $(PIO) run -e $(PROFILE) -t fullflash --upload-port $(PORT)) $(LOG_PIPE)

monitor:
	$(EXEC) (echo "Monitor: $(PORT) @ 115200"; $(PIO) device monitor -p $(PORT) -b 115200) $(LOG_PIPE)

clean:
	$(EXEC) (echo "Cleaning build artifacts..."; $(PIO) run -t clean; rm -rf build/) $(LOG_PIPE)

# Debug targets
debug-build:
	$(EXEC) (echo "Building debug: $(PROFILE)-debug [$(BUILD_FLAGS)]"; $(PIO) run -e $(PROFILE)-debug) $(LOG_PIPE)

debug-upload: debug-build
	$(EXEC) (echo "Uploading debug build to $(PORT)"; $(PIO) run -e $(PROFILE)-debug -t upload --upload-port $(PORT)) $(LOG_PIPE)

debug:
	$(EXEC) (echo "Starting debug session for $(PROFILE)-debug on $(PORT)"; echo "Use VSCode 'Run and Debug' panel or:"; $(PIO) debug -e $(PROFILE)-debug --interface=gdb -x .piodebugger/launch.gdb) $(LOG_PIPE)

# Test targets
test-serial:
	$(EXEC) (echo "Running serial RPC integration tests (port: $(ATSMINI_PORT))"; ATSMINI_PORT=$(ATSMINI_PORT) pytest sdk/tests/test_rpc_serial.py -v) $(LOG_PIPE)

test-ws:
	$(EXEC) (echo "Running WebSocket RPC integration tests"; pytest sdk/tests/test_rpc_ws.py -v) $(LOG_PIPE)

full-test: test-serial test-ws
	$(EXEC) echo "All integration tests completed" $(LOG_PIPE)

ARDUINO_CLI := arduino-cli

PROFILE	= esp32s3-qspi
FQBN	= esp32.esp32.esp32s3
INO	= ats-mini.ino
ELF	= ./build/$(FQBN)/$(INO).elf
PORT	?= /dev/cu.usbmodem1101
LOGFILE ?=

LOGPIPE = $(if $(LOGFILE), | tee -a $(LOGFILE),)

DEBUG_LEVEL ?= 0

#
# HALF_STEP       : Enable encoder half-steps
#
DEFINES = -DDEBUG=$(DEBUG_LEVEL)

ifdef HALF_STEP
        DEFINES += -DHALF_STEP
endif

OPTIONS = \
	--build-property "compiler.cpp.extra_flags=$(DEFINES)" \
	--warnings all

HEADERS = \
	Common.h Themes.h Menu.h Storage.h tft_setup.h Rotary.h \
	Utils.h Button.h EIBI.h Remote.h Ble.h SI4735-fixed.h patch_init.h Compression.h CborRpc.h

SRC = \
	$(INO) Utils.cpp Rotary.cpp Button.cpp Draw.cpp Menu.cpp \
	Station.cpp Battery.cpp Storage.cpp Themes.cpp Remote.cpp \
	Network.cpp EIBI.cpp Scan.cpp About.cpp Ble.cpp \
	Layout-Default.cpp Layout-SMeter.cpp Compression.cpp CborRpc.cpp

all: build

help:
	@echo 'Run this command to upload the firmware to your radio:'
	@echo
	@echo '  make upload PORT=/dev/cu.usbmodem1101'
	@echo
	@echo 'Optional logging:'
	@echo '  make build LOGFILE=logs/build.log'
	@echo '  make upload LOGFILE=logs/upload.log'
	@echo '  make test LOGFILE=logs/test.log'
	@echo

build: $(ELF)

$(ELF): $(INO) $(SRC) $(HEADERS)
	@if [ -n "$(LOGFILE)" ]; then mkdir -p $(dir $(LOGFILE)); fi
	$(ARDUINO_CLI) compile --export-binaries --profile $(PROFILE) $(OPTIONS)$(LOGPIPE)

upload: build
	@if [ -n "$(LOGFILE)" ]; then mkdir -p $(dir $(LOGFILE)); fi
	$(ARDUINO_CLI) upload --profile $(PROFILE) --port $(PORT)$(LOGPIPE)

test:
	@if [ -n "$(LOGFILE)" ]; then mkdir -p $(dir $(LOGFILE)); fi
	python3 -m pytest tools/atsmini_rpc/tests$(LOGPIPE)

full-test: upload test

clean:
	$(ARDUINO_CLI) cache clean
	rm -Rf ./build/


.PHONY: all help build upload clean test full-test

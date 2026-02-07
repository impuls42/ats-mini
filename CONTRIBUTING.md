## Contributing guidelines

* This is a learning project.
* People have different usage scenarios, UI preferences, etc. It is not possible to fit everything into a single firmware.
* All feature requests, ideas, observations, questions and answers should go into the [Discussions](https://github.com/esp32-si4732/ats-mini/discussions) section.
* [Issues](https://github.com/esp32-si4732/ats-mini/issues) should be used only for bugs and planned tasks.
* [Pull Requests](https://github.com/esp32-si4732/ats-mini/pulls) are not guaranteed to be accepted, unless the maintainer(s) consider them suitable for the majority of users. Documentation, bugfixes and code quality improvements are usually welcome! If in doubt, please propose your contribution as a [Discussion](https://github.com/esp32-si4732/ats-mini/discussions) first.
* You are encouraged to make your own custom firmware forks! Feel free to share a link to your firmware version in the [Discussions](https://github.com/esp32-si4732/ats-mini/discussions). Interesting features or color themes might be included into the ATS Mini firmware.

## Agent development guide

To keep changes reviewable and reproducible, please use the Make targets below and capture logs when running builds or tests.

### Recommended workflow

1. **Build and upload with logs**

	- Build: `LOGFILE=logs/build.log make build`
	- Upload: `PORT=/dev/cu.usbmodem1101 LOGFILE=logs/upload.log make upload`

	Optional: install RPC test dependencies with `uv sync --extra rpc` or `python -m pip install -e .[rpc]`.

2. **Full cycle test (hardware required)**

	```bash
	# Run all integration tests
	ATSMINI_PORT=/dev/cu.usbmodem1101 pytest sdk/tests/
	```

3. **Protocol integration tests**

	```bash
	# Serial transport
	ATSMINI_PORT=/dev/cu.usbmodem1101 pytest sdk/tests/test_rpc_serial.py

	# WebSocket transport
	ATSMINI_WS_URL=ws://atsmini.local/rpc pytest sdk/tests/test_rpc_ws.py

	# BLE transport
	pytest sdk/tests/test_rpc_ble.py
	```

### Notes

- CBOR‑RPC mode is opt‑in and activated via a switch byte (`0x1E`) on Serial/BLE.
- Legacy terminal commands remain the default path unless the switch byte is received.
- Tests are integration‑style and validate the transport and protocol flow; no unit tests are required.

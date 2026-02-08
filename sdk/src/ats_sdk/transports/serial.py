"""Async Serial RPC transport using asyncio.to_thread()."""

import asyncio
from typing import Optional

import serial

from ..base import AsyncRpcTransport
from ..framing import SWITCH_BYTE


class AsyncSerialRpc(AsyncRpcTransport):
    """Async Serial RPC client using asyncio.to_thread() for blocking I/O.

    Uses DTR control for ESP32-S3 and requires mode switching (0x1E byte)
    to activate CBOR-RPC protocol.
    """

    def __init__(self, port: str, baudrate: int = 115200, timeout: float = 1.0):
        super().__init__()
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self._serial: Optional[serial.Serial] = None
        self._lock = asyncio.Lock()  # Protect serial port access

    async def connect(self) -> None:
        """Establish serial connection and configure port."""
        def _open_serial():
            self.logger.debug(f"Opening serial port {self.port} at {self.baudrate} baud (timeout={self.timeout}s)")
            ser = serial.Serial(self.port, baudrate=self.baudrate, timeout=self.timeout)
            # Assert DTR to enable Serial on ESP32-S3
            ser.dtr = True
            ser.rts = False
            self.logger.debug("Set DTR=True, RTS=False")
            return ser

        self._serial = await asyncio.to_thread(_open_serial)

        # Brief settle time
        await asyncio.sleep(0.1)

        # Flush any pending data
        async with self._lock:
            ser = self._serial
            assert ser is not None
            flushed = await asyncio.to_thread(lambda: ser.in_waiting)  # type: ignore[union-attr]
            await asyncio.to_thread(ser.reset_input_buffer)
            if flushed > 0:
                self.logger.debug(f"Flushed {flushed} bytes from input buffer")

        self.logger.info(f"AsyncSerialRpc connected to {self.port}")

    async def close(self) -> None:
        """Close serial connection."""
        if self._serial:
            self.logger.debug(f"Closing serial port {self._serial.port}")
            await asyncio.to_thread(self._serial.close)
            self._serial = None
            self.logger.info("AsyncSerialRpc disconnected")

    async def switch_mode(self) -> None:
        """Switch device to CBOR-RPC mode (Serial only).

        Sends the SWITCH_BYTE (0x1E) to activate CBOR-RPC protocol.
        Required before making RPC requests.
        """
        if not self._serial:
            raise ConnectionError("Not connected")

        # Wait for device to finish booting before sending switch byte
        await asyncio.sleep(0.5)

        self.logger.debug(f"Switching to CBOR-RPC mode (sending 0x{SWITCH_BYTE:02X})")

        async with self._lock:
            await asyncio.to_thread(self._serial.write, bytes([SWITCH_BYTE]))
            await asyncio.to_thread(self._serial.flush)

        # Wait for mode switch to complete
        await asyncio.sleep(0.2)

        # Clear any leftover data from the input buffer (could be text mode data)
        async with self._lock:
            ser = self._serial
            assert ser is not None
            pending = await asyncio.to_thread(lambda: ser.in_waiting)  # type: ignore[union-attr]
            if pending > 0:
                self.logger.debug(f"Clearing {pending} bytes from input buffer after mode switch")
                await asyncio.to_thread(ser.reset_input_buffer)

        self.logger.info("CBOR-RPC mode activated")

    async def write_frame(self, frame: bytes) -> None:
        """Write frame to serial port."""
        if not self._serial:
            raise ConnectionError("Not connected")

        async with self._lock:
            await asyncio.to_thread(self._serial.write, frame)
            await asyncio.to_thread(self._serial.flush)

    async def read_frame(self, timeout: float) -> bytes:
        """Read frame from serial port."""
        if not self._serial:
            raise ConnectionError("Not connected")

        deadline = asyncio.get_event_loop().time() + timeout

        # Read 4-byte header
        header = await self._read_exact(4, deadline)
        length = int.from_bytes(header, "big")

        # Validate frame length (max 1MB for screen captures)
        if length > 1_000_000 or length == 0:
            # Corrupted frame - try to flush and resync
            self.logger.error(f"Invalid frame length: {length} bytes (0x{length:08X}), header={header.hex()}")
            # Check if this looks like CBOR data instead of a frame length
            if header[0] >= 0xa0:  # CBOR map/array markers
                self.logger.error("Header looks like CBOR data - firmware may not be sending frame headers")
            async with self._lock:
                ser = self._serial
                assert ser is not None
                pending = await asyncio.to_thread(lambda: ser.in_waiting)  # type: ignore[union-attr]
                self.logger.error(f"Flushing {pending} bytes from serial buffer")
                await asyncio.to_thread(ser.reset_input_buffer)
            raise ValueError(f"Invalid frame length: {length} bytes - stream may be out of sync")

        self.logger.debug(f"Message length: {length} bytes")

        # Read payload
        try:
            payload = await self._read_exact(length, deadline)
        except TimeoutError as e:
            self.logger.error(f"Timeout reading payload: expected {length} bytes")
            async with self._lock:
                ser = self._serial
                assert ser is not None
                pending = await asyncio.to_thread(lambda: ser.in_waiting)  # type: ignore[union-attr]
                self.logger.error(f"Only {pending} bytes available in buffer")
            raise

        return header + payload

    async def _read_exact(self, size: int, deadline: float) -> bytes:
        """Read exact number of bytes with timeout."""
        data = bytearray()

        while len(data) < size:
            remaining_time = deadline - asyncio.get_event_loop().time()
            if remaining_time <= 0:
                raise TimeoutError(
                    f"Timeout reading {size} bytes (got {len(data)} bytes)"
                )

            # Check if data is available before attempting read
            async with self._lock:
                ser = self._serial
                assert ser is not None
                available = await asyncio.to_thread(lambda: ser.in_waiting)  # type: ignore[union-attr]

            if available > 0:
                # Read available data (up to what we need)
                to_read = min(available, size - len(data))
                async with self._lock:
                    ser = self._serial
                    assert ser is not None
                    chunk = await asyncio.to_thread(ser.read, to_read)

                if chunk:
                    data.extend(chunk)
            else:
                # No data available, small sleep before retry
                await asyncio.sleep(0.01)

        return bytes(data)

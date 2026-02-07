"""BLE transport for ATS-Mini using Nordic UART Service."""

import asyncio
import logging
from typing import Optional

from bleak import BleakClient, BleakScanner
from bleak.backends.characteristic import BleakGATTCharacteristic

from .base import AsyncRpcTransport
from .framing import SWITCH_BYTE

# Nordic UART Service UUIDs
NUS_SERVICE_UUID = "6E400001-B5A3-F393-E0A9-E50E24DCCA9E"
NUS_RX_CHAR_UUID = "6E400002-B5A3-F393-E0A9-E50E24DCCA9E"  # Write to device
NUS_TX_CHAR_UUID = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"  # Notify from device


class AsyncBleRpc(AsyncRpcTransport):
    """Async BLE RPC client using Nordic UART Service.

    Connects to ESP32-S3 via BLE and communicates using the same CBOR-RPC
    protocol as Serial/WebSocket transports. Requires mode switching (0x1E byte).
    """

    def __init__(self, device_name: str = "ATS-Mini", scan_timeout: float = 10.0):
        """Initialize BLE RPC client.

        Args:
            device_name: BLE device name to search for (default: "ATS-Mini")
            scan_timeout: Timeout for device discovery scan in seconds
        """
        super().__init__()
        self.device_name = device_name
        self.scan_timeout = scan_timeout

        self._client: Optional[BleakClient] = None
        self._rx_buffer = bytearray()
        self._rx_event = asyncio.Event()
        self._disconnect_event = asyncio.Event()
        self._mtu = 517  # ESP32 default, effective payload is MTU-3

    async def connect(self) -> None:
        """Discover and connect to BLE device."""
        # Scan for device
        self.logger.info(f"Scanning for BLE device '{self.device_name}'...")

        device = await BleakScanner.find_device_by_name(
            self.device_name,
            timeout=self.scan_timeout
        )

        if device is None:
            raise ConnectionError(
                f"Device '{self.device_name}' not found after {self.scan_timeout}s scan. "
                f"Ensure device is powered on and BLE is enabled."
            )

        self.logger.info(f"Found device: {device.name} ({device.address})")

        # Connect
        self._client = BleakClient(
            device,
            disconnected_callback=self._on_disconnect
        )

        await self._client.connect()
        self.logger.info(f"Connected to {device.name}")

        # Subscribe to TX characteristic (notifications from device)
        await self._client.start_notify(
            NUS_TX_CHAR_UUID,
            self._on_notification
        )

        self.logger.info("Subscribed to TX notifications")

        # Get actual MTU
        if hasattr(self._client, 'mtu_size'):
            self._mtu = self._client.mtu_size
            self.logger.debug(f"MTU: {self._mtu} bytes")

    async def close(self) -> None:
        """Disconnect from BLE device."""
        if self._client and self._client.is_connected:
            try:
                await self._client.stop_notify(NUS_TX_CHAR_UUID)
            except Exception as e:
                self.logger.warning(f"Error stopping notifications: {e}")

            await self._client.disconnect()
            self._client = None
            self.logger.info("AsyncBleRpc disconnected")

    async def switch_mode(self) -> None:
        """Switch device to CBOR-RPC mode.

        Sends the SWITCH_BYTE (0x1E) to activate CBOR-RPC protocol.
        Required before making RPC requests.
        """
        self.logger.debug(f"Switching to CBOR-RPC mode (sending 0x{SWITCH_BYTE:02X})")
        await self.write_raw(bytes([SWITCH_BYTE]))
        await asyncio.sleep(0.1)
        self.logger.info("CBOR-RPC mode activated")

    async def write_raw(self, data: bytes) -> None:
        """Write raw bytes to RX characteristic (write to device)."""
        if not self._client or not self._client.is_connected:
            raise ConnectionError("Not connected to BLE device")

        # Write to RX characteristic (write to device)
        await self._client.write_gatt_char(
            NUS_RX_CHAR_UUID,
            data,
            response=False  # Write without response for speed
        )

    async def write_frame(self, frame: bytes) -> None:
        """Write frame to BLE device, chunking if necessary.

        BLE has lower MTU than serial/WebSocket, so large frames are split
        into chunks that fit within MTU limits.
        """
        # BLE has lower MTU than serial/WS, need to chunk
        chunk_size = self._mtu - 3  # Account for ATT header

        offset = 0
        while offset < len(frame):
            chunk = frame[offset:offset + chunk_size]
            await self.write_raw(chunk)
            offset += chunk_size

            # Small delay between chunks to avoid overwhelming device
            if offset < len(frame):
                await asyncio.sleep(0.005)  # 5ms, matches firmware delay

    async def read_frame(self, timeout: float) -> bytes:
        """Read frame from BLE device.

        Waits for notifications to accumulate a complete frame in the buffer.
        """
        deadline = asyncio.get_event_loop().time() + timeout

        # Wait for at least 4 bytes (header)
        while len(self._rx_buffer) < 4:
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                raise TimeoutError("Timeout waiting for frame header")

            try:
                await asyncio.wait_for(self._rx_event.wait(), timeout=remaining)
                self._rx_event.clear()
            except asyncio.TimeoutError:
                raise TimeoutError("Timeout waiting for frame header")

        # Parse length
        length = int.from_bytes(self._rx_buffer[:4], "big")
        total_size = 4 + length

        self.logger.debug(f"Message length: {length} bytes (total: {total_size})")

        # Wait for complete frame
        while len(self._rx_buffer) < total_size:
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                raise TimeoutError(
                    f"Timeout waiting for frame payload "
                    f"(got {len(self._rx_buffer)}/{total_size} bytes)"
                )

            try:
                await asyncio.wait_for(self._rx_event.wait(), timeout=remaining)
                self._rx_event.clear()
            except asyncio.TimeoutError:
                raise TimeoutError(
                    f"Timeout waiting for frame payload "
                    f"(got {len(self._rx_buffer)}/{total_size} bytes)"
                )

        # Extract complete frame
        frame = bytes(self._rx_buffer[:total_size])
        del self._rx_buffer[:total_size]

        return frame

    def _on_notification(self, characteristic: BleakGATTCharacteristic, data: bytearray):
        """Handle incoming notification from TX characteristic.

        Called by Bleak when data is received from the device.
        Accumulates data in buffer and signals the event.
        """
        self._rx_buffer.extend(data)
        self._rx_event.set()

    def _on_disconnect(self, client: BleakClient):
        """Handle disconnection event.

        Called by Bleak when connection is lost.
        """
        self.logger.warning("BLE device disconnected")
        self._disconnect_event.set()

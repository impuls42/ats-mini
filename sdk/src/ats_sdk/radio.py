"""High-level typed wrapper around ATS-Mini CBOR-RPC transport."""

from typing import Any, Dict, Optional

from .base import AsyncRpcTransport


class RpcError(Exception):
    """Raised when the device returns an RPC error."""

    def __init__(self, code: int, message: str):
        self.code = code
        self.message = message
        super().__init__(f"RPC error {code}: {message}")


class Radio:
    """Typed convenience wrapper around a raw RPC transport.

    Usage::

        async with AsyncSerialRpc(port) as transport:
            await transport.switch_mode()
            radio = Radio(transport)
            vol = await radio.get_volume()
            await radio.set_volume(10)
            settings = await radio.get_all_settings()
    """

    def __init__(self, transport: AsyncRpcTransport):
        self._t = transport

    async def _call(
        self,
        method: str,
        params: Optional[Dict[str, Any]] = None,
        timeout: float = 5.0,
    ) -> Dict[str, Any]:
        req_id = await self._t.request(method, params)
        reply = await self._t.read_response(req_id, timeout=timeout)
        err = reply.get("error")
        if err is not None:
            if isinstance(err, dict):
                code = err.get("code", -1)
                message = err.get("message", "unknown")
            else:
                code = -1
                message = str(err)
            raise RpcError(code, message)
        return reply.get("result", {})

    # -- bulk --

    async def get_all_settings(self) -> Dict[str, Any]:
        return await self._call("settings.get")

    async def get_status(self) -> Dict[str, Any]:
        return await self._call("status.get")

    async def get_capabilities(self) -> Dict[str, Any]:
        return await self._call("capabilities.get")

    # -- volume --

    async def get_volume(self) -> int:
        r = await self._call("volume.get")
        return r["volume"]

    async def set_volume(self, value: int) -> int:
        r = await self._call("volume.set", {"value": value})
        return r["volume"]

    # -- frequency --

    async def get_frequency(self) -> Dict[str, Any]:
        return await self._call("frequency.get")

    async def set_frequency(self, value: int) -> Dict[str, Any]:
        return await self._call("frequency.set", {"value": value})

    # -- band --

    async def get_band(self) -> Dict[str, Any]:
        return await self._call("band.get")

    async def set_band(self, value: int) -> Dict[str, Any]:
        return await self._call("band.set", {"value": value}, timeout=10.0)

    async def set_band_by_name(self, name: str) -> Dict[str, Any]:
        return await self._call("band.set", {"name": name}, timeout=10.0)

    # -- mode --

    async def get_mode(self) -> Dict[str, Any]:
        return await self._call("mode.get")

    async def set_mode(self, value: int) -> Dict[str, Any]:
        return await self._call("mode.set", {"value": value}, timeout=10.0)

    # -- step --

    async def get_step(self) -> Dict[str, Any]:
        return await self._call("step.get")

    async def set_step(self, value: int) -> Dict[str, Any]:
        return await self._call("step.set", {"value": value})

    # -- bandwidth --

    async def get_bandwidth(self) -> Dict[str, Any]:
        return await self._call("bandwidth.get")

    async def set_bandwidth(self, value: int) -> Dict[str, Any]:
        return await self._call("bandwidth.set", {"value": value})

    # -- agc --

    async def get_agc(self) -> Dict[str, Any]:
        return await self._call("agc.get")

    async def set_agc(self, value: int) -> Dict[str, Any]:
        return await self._call("agc.set", {"value": value})

    # -- squelch --

    async def get_squelch(self) -> int:
        r = await self._call("squelch.get")
        return r["squelch"]

    async def set_squelch(self, value: int) -> int:
        r = await self._call("squelch.set", {"value": value})
        return r["squelch"]

    # -- softmute --

    async def get_softmute(self) -> Dict[str, Any]:
        return await self._call("softmute.get")

    async def set_softmute(self, value: int) -> Dict[str, Any]:
        return await self._call("softmute.set", {"value": value})

    # -- avc --

    async def get_avc(self) -> Dict[str, Any]:
        return await self._call("avc.get")

    async def set_avc(self, value: int) -> Dict[str, Any]:
        return await self._call("avc.set", {"value": value})

    # -- theme --

    async def get_theme(self) -> Dict[str, Any]:
        return await self._call("theme.get")

    async def set_theme(self, value: int) -> Dict[str, Any]:
        return await self._call("theme.set", {"value": value})

    # -- brightness --

    async def get_brightness(self) -> int:
        r = await self._call("brightness.get")
        return r["brightness"]

    async def set_brightness(self, value: int) -> int:
        r = await self._call("brightness.set", {"value": value})
        return r["brightness"]

    # -- sleep timeout --

    async def get_sleep_timeout(self) -> int:
        r = await self._call("sleep.timeout.get")
        return r["sleep"]

    async def set_sleep_timeout(self, value: int) -> int:
        r = await self._call("sleep.timeout.set", {"value": value})
        return r["sleep"]

    # -- sleep mode --

    async def get_sleep_mode(self) -> Dict[str, Any]:
        return await self._call("sleep.mode.get")

    async def set_sleep_mode(self, value: int) -> Dict[str, Any]:
        return await self._call("sleep.mode.set", {"value": value})

    # -- rds mode --

    async def get_rds_mode(self) -> Dict[str, Any]:
        return await self._call("rds.mode.get")

    async def set_rds_mode(self, value: int) -> Dict[str, Any]:
        return await self._call("rds.mode.set", {"value": value})

    # -- utc offset --

    async def get_utc_offset(self) -> Dict[str, Any]:
        return await self._call("utc.offset.get")

    async def set_utc_offset(self, value: int) -> Dict[str, Any]:
        return await self._call("utc.offset.set", {"value": value})

    # -- fm region --

    async def get_fm_region(self) -> Dict[str, Any]:
        return await self._call("fm.region.get")

    async def set_fm_region(self, value: int) -> Dict[str, Any]:
        return await self._call("fm.region.set", {"value": value})

    # -- ui layout --

    async def get_ui_layout(self) -> Dict[str, Any]:
        return await self._call("ui.layout.get")

    async def set_ui_layout(self, value: int) -> Dict[str, Any]:
        return await self._call("ui.layout.set", {"value": value})

    # -- zoom menu --

    async def get_zoom_menu(self) -> bool:
        r = await self._call("zoom.menu.get")
        return r["enabled"]

    async def set_zoom_menu(self, value: bool) -> bool:
        r = await self._call("zoom.menu.set", {"value": value})
        return r["enabled"]

    # -- scroll direction --

    async def get_scroll_direction(self) -> int:
        r = await self._call("scroll.direction.get")
        return r["scroll_direction"]

    async def set_scroll_direction(self, value: int) -> int:
        r = await self._call("scroll.direction.set", {"value": value})
        return r["scroll_direction"]

    # -- usb mode --

    async def get_usb_mode(self) -> Dict[str, Any]:
        return await self._call("usb.mode.get")

    async def set_usb_mode(self, value: int) -> Dict[str, Any]:
        return await self._call("usb.mode.set", {"value": value})

    # -- ble mode --

    async def get_ble_mode(self) -> Dict[str, Any]:
        return await self._call("ble.mode.get")

    async def set_ble_mode(self, value: int) -> Dict[str, Any]:
        return await self._call("ble.mode.set", {"value": value})

    # -- wifi mode --

    async def get_wifi_mode(self) -> Dict[str, Any]:
        return await self._call("wifi.mode.get")

    async def set_wifi_mode(self, value: int) -> Dict[str, Any]:
        return await self._call("wifi.mode.set", {"value": value})

    # -- cal --

    async def get_cal(self) -> Dict[str, Any]:
        return await self._call("cal.get")

    async def set_cal(self, value: int) -> Dict[str, Any]:
        return await self._call("cal.set", {"value": value})

    # -- simple controls --

    async def sleep_on(self) -> Dict[str, Any]:
        return await self._call("sleep.on")

    async def sleep_off(self) -> Dict[str, Any]:
        return await self._call("sleep.off")

    async def memory_list(self) -> list:
        r = await self._call("memory.list")
        return r.get("memories", [])

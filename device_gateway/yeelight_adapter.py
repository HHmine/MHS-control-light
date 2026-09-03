from __future__ import annotations

import time
from typing import Any


class DeviceError(RuntimeError):
    pass


class YeelightAdapter:
    """Adapter for yeelink.light.bslamp2 using raw python-miio commands."""

    def __init__(self, ip: str, token: str) -> None:
        # Keep python-miio optional in simulated/agent environments.
        from miio import Device

        self.client = Device(ip=ip, token=token)

    @staticmethod
    def _ok(result: Any) -> bool:
        return result == ["ok"] or result == "ok"

    def _send(self, method: str, parameters: list[Any]) -> Any:
        started_at = time.perf_counter()
        try:
            result = self.client.send(method, parameters)
        except Exception as exc:
            elapsed_ms = (time.perf_counter() - started_at) * 1000
            print(f"[Miio] {method} 失败，耗时 {elapsed_ms:.1f} ms")
            raise DeviceError(f"设备命令 {method} 执行失败: {exc}") from exc
        elapsed_ms = (time.perf_counter() - started_at) * 1000
        print(f"[Miio] {method} 成功，耗时 {elapsed_ms:.1f} ms")
        if not self._ok(result):
            raise DeviceError(f"设备命令 {method} 未确认成功: {result!r}")
        return result

    def snapshot(self) -> dict[str, Any]:
        started_at = time.perf_counter()
        try:
            result = self.client.send(
                "get_prop",
                ["power", "bright", "ct", "rgb"],
            )
        except Exception as exc:
            elapsed_ms = (time.perf_counter() - started_at) * 1000
            print(f"[Miio] get_prop 失败，耗时 {elapsed_ms:.1f} ms")
            raise DeviceError(f"读取设备状态失败: {exc}") from exc

        if not isinstance(result, (list, tuple)) or len(result) < 4:
            raise DeviceError(f"设备状态返回格式异常: {result!r}")

        power, brightness, color_temperature, rgb = result[:4]
        return {
            "device_id": "bedside_lamp",
            "model": "yeelink.light.bslamp2",
            "backend": "yeelight",
            "online": True,
            "power": power == "on",
            "brightness": int(brightness),
            "color_temperature": int(color_temperature),
            "rgb": int(rgb),
            "active_fault": None,
        }

    def set_state(
        self,
        *,
        power: bool | None = None,
        brightness: int | None = None,
        color_temperature: int | None = None,
    ) -> dict[str, Any]:
        if power is not None:
            self._send("set_power", ["on" if power else "off"])
        if brightness is not None:
            self._send("set_bright", [brightness])
        if color_temperature is not None:
            self._send("set_ct_abx", [color_temperature])
        return self.snapshot()

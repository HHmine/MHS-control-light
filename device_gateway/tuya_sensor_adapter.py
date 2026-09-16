"""Tuya cloud light-sensor adapter used as independent physical evidence."""
from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable

from .sensor_adapter import now_iso


logging.getLogger("tuya_connector").setLevel(logging.WARNING)


class TuyaLightSensorAdapter:
    source_id = "tuya_light_sensor"

    def __init__(
        self,
        access_id: str,
        access_key: str,
        device_id: str,
        api_endpoint: str = "https://openapi.tuyacn.com",
        dp_code: str = "bright_value",
        light_threshold: int = 10,
        *,
        openapi_factory: Callable[..., Any] | None = None,
    ) -> None:
        if openapi_factory is None:
            try:
                from tuya_connector import TuyaOpenAPI
            except ImportError as exc:
                raise RuntimeError(
                    "SENSOR_BACKEND=tuya 需要安装 tuya-connector-python"
                ) from exc
            openapi_factory = TuyaOpenAPI
        self.device_id = device_id
        self.dp_code = dp_code
        self.light_threshold = light_threshold
        self._lock = threading.RLock()
        self._connected = False
        self._openapi = openapi_factory(api_endpoint, access_id, access_key)

    def _ensure_connected(self) -> None:
        if self._connected:
            return
        result = self._openapi.connect()
        if isinstance(result, dict) and result.get("success") is False:
            raise RuntimeError(
                f"涂鸦传感器连接失败: {result.get('msg', '未知错误')}"
            )
        self._connected = True

    def connectivity(self) -> tuple[bool, str]:
        try:
            with self._lock:
                self._ensure_connected()
        except Exception as exc:
            return False, f"Tuya light sensor unreachable: {exc}"
        return True, "Tuya light sensor reachable"

    def reading(self) -> dict[str, Any]:
        with self._lock:
            self._ensure_connected()
            response = self._openapi.get(
                f"/v1.0/iot-03/devices/{self.device_id}/status"
            )
        if not isinstance(response, dict) or not response.get("success", False):
            message = response.get("msg", "未知错误") if isinstance(response, dict) else "无效响应"
            raise RuntimeError(f"涂鸦传感器查询失败: {message}")

        raw_lux: object | None = None
        for item in response.get("result", []):
            if isinstance(item, dict) and item.get("code") == self.dp_code:
                raw_lux = item.get("value")
                break
        if raw_lux is None:
            raise RuntimeError(f"涂鸦传感器数据点中缺少 {self.dp_code}")
        if isinstance(raw_lux, bool):
            raise RuntimeError(f"涂鸦传感器 {self.dp_code} 不是数值")
        try:
            lux = int(raw_lux)
        except (TypeError, ValueError) as exc:
            raise RuntimeError(f"涂鸦传感器 {self.dp_code} 不是数值") from exc

        captured_at = time.time()
        return {
            "source_id": self.source_id,
            "lux": lux,
            "light_detected": lux > self.light_threshold,
            "captured_at": captured_at,
            "timestamp": now_iso(),
            "dp_code": self.dp_code,
        }

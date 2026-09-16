from __future__ import annotations

import threading
import os
from typing import Any

from .execution_port import ExecutionError, ExecutionRequest, build_execution_port


REAL_FAULT_BLOCK_POWER_ON = "block_power_on"
REAL_FAULT_BLOCK_POWER_OFF = "block_power_off"
SUPPORTED_REAL_FAULTS = {
    REAL_FAULT_BLOCK_POWER_ON,
    REAL_FAULT_BLOCK_POWER_OFF,
}


class DeviceService:
    """Validate requests and expose a stable contract to the HTTP gateway."""

    def __init__(
        self,
        backend: str,
        adapter: Any,
        execution_mode: str | None = None,
        sensor_adapter: Any | None = None,
    ) -> None:
        self.backend = backend
        self.adapter = adapter
        self.sensor_adapter = sensor_adapter
        self.execution_mode = (execution_mode or os.getenv("EXECUTION_MODE", "direct")).strip().lower()
        if self.execution_mode == "aurea" and backend != "yeelight":
            raise ValueError("AUREA physical-device 执行模式仅支持 yeelight 后端")
        self.execution_port = build_execution_port(
            self.execution_mode,
            adapter,
            sensor_adapter=sensor_adapter,
        )
        self._real_fault_lock = threading.RLock()
        self._active_real_fault: str | None = None

    @property
    def supports_faults(self) -> bool:
        return self.backend == "simulated"

    @property
    def supports_real_faults(self) -> bool:
        return self.backend == "yeelight"

    @property
    def supports_sensor(self) -> bool:
        return self.sensor_adapter is not None

    @property
    def active_real_fault(self) -> str | None:
        with self._real_fault_lock:
            return self._active_real_fault

    def health(self) -> dict[str, Any]:
        return {
            "ok": True,
            "service": "lamp-device-gateway",
            "backend": self.backend,
            "execution_mode": self.execution_mode,
            "supports_faults": self.supports_faults,
            "supports_sensor": self.supports_sensor,
        }

    def sensor_reading(self) -> dict[str, Any]:
        if self.sensor_adapter is None:
            raise RuntimeError("未配置光传感器")
        return self.sensor_adapter.reading()

    def get_state(self) -> dict[str, Any]:
        # Hidden real-device fault state is intentionally absent here. Agents
        # use this method and must not learn what the admin UI injected.
        state = dict(self.adapter.snapshot())
        if self.sensor_adapter is None:
            state["observed_power"] = "unknown"
            state["sensor_observation"] = None
            return state
        try:
            reading = self.sensor_adapter.reading()
            state["observed_power"] = (
                "on" if reading.get("light_detected") else "off"
            )
            state["sensor_observation"] = reading
        except Exception as exc:
            state["observed_power"] = "unknown"
            state["sensor_observation"] = {
                "available": False,
                "error": str(exc),
            }
        return state

    def control(
        self,
        *,
        power: bool | None = None,
        brightness: int | None = None,
        color_temperature: int | None = None,
    ) -> dict[str, Any]:
        if power is not None and not isinstance(power, bool):
            raise ValueError("power 必须是布尔值")

        if brightness is not None:
            if isinstance(brightness, bool) or not isinstance(brightness, int):
                raise ValueError("brightness 必须是整数")
            if not 1 <= brightness <= 100:
                raise ValueError("brightness 必须在 1..100 之间")

        if color_temperature is not None:
            if isinstance(color_temperature, bool) or not isinstance(
                color_temperature, int
            ):
                raise ValueError("color_temperature 必须是整数")
            if not 1700 <= color_temperature <= 6500:
                raise ValueError("color_temperature 必须在 1700..6500 K 之间")

        request = ExecutionRequest(
            power=power,
            brightness=brightness,
            color_temperature=color_temperature,
        )

        # Keep the guard locked through the selected execution port so an
        # injection cannot race with a real power command after the hidden check.
        with self._real_fault_lock:
            blocked_power = {
                REAL_FAULT_BLOCK_POWER_ON: True,
                REAL_FAULT_BLOCK_POWER_OFF: False,
            }.get(self._active_real_fault)
            try:
                return self.execution_port.control(
                    request,
                    is_blocked=lambda requested_power: (
                        requested_power is not None and requested_power is blocked_power
                    ),
                )
            except ExecutionError:
                raise

    def inject_fault(self, fault: str) -> dict[str, Any]:
        if not self.supports_faults:
            raise RuntimeError("真实设备模式不支持故障注入")
        return self.adapter.inject_fault(fault)

    def clear_fault(self) -> dict[str, Any]:
        if not self.supports_faults:
            raise RuntimeError("真实设备模式不支持清除模拟故障")
        return self.adapter.clear_fault()

    def real_fault_status(self) -> dict[str, Any]:
        """Admin-only state used by the device webpage, never Agent tools."""
        return {
            "ok": True,
            "backend": self.backend,
            "supports_real_faults": self.supports_real_faults,
            "active_real_fault": self.active_real_fault,
            "scope": "gateway_process",
        }

    def inject_real_fault(self, fault: str) -> dict[str, Any]:
        if not self.supports_real_faults:
            raise RuntimeError("真实故障注入仅支持 yeelight 后端")
        if fault not in SUPPORTED_REAL_FAULTS:
            supported = ", ".join(sorted(SUPPORTED_REAL_FAULTS))
            raise ValueError(f"不支持的真实故障；可选值：{supported}")
        with self._real_fault_lock:
            self._active_real_fault = fault
            return self.real_fault_status()

    def clear_real_fault(self) -> dict[str, Any]:
        if not self.supports_real_faults:
            raise RuntimeError("真实故障清除仅支持 yeelight 后端")
        with self._real_fault_lock:
            previous_fault = self._active_real_fault
            self._active_real_fault = None
            result = self.real_fault_status()
            result["previous_real_fault"] = previous_fault
            return result

    def subscribe(self):
        if not self.supports_faults:
            raise RuntimeError("真实设备模式暂不支持事件流")
        return self.adapter.subscribe()

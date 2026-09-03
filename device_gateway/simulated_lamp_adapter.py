"""Thread-safe simulated lamp with telemetry, events and fault injection."""
from __future__ import annotations
import copy, queue, random, threading
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterator
from zoneinfo import ZoneInfo

try:
    SHANGHAI = ZoneInfo("Asia/Shanghai")
except Exception:
    # Windows may not ship the IANA timezone database inside a fresh venv.
    SHANGHAI = timezone(timedelta(hours=8), name="Asia/Shanghai")
SUPPORTED_FAULTS = {"offline", "stuck_on", "stuck_off", "sensor_error", "overheat"}

def now_iso() -> str:
    return datetime.now(SHANGHAI).isoformat(timespec="milliseconds")

@dataclass
class LampState:
    device_id: str = "bedside-lamp-2-demo"
    model: str = "米家床头灯2（模拟）"
    online: bool = True
    power: bool = False
    brightness: int = 50
    color_temperature: int = 4000
    temperature_c: float | None = 26.0
    active_fault: str | None = None
    updated_at: str = ""

class DeviceError(RuntimeError):
    pass

class SimulatedLamp:
    def __init__(self) -> None:
        self._state = LampState(updated_at=now_iso())
        self._lock = threading.RLock()
        self._subscribers: list[queue.Queue[dict[str, Any]]] = []
        self._sequence = 0

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            data = asdict(self._state)
            if self._state.active_fault == "sensor_error":
                data["temperature_c"] = None
            elif self._state.online:
                base = 29.0 if self._state.power else 25.0
                data["temperature_c"] = round(base + random.uniform(-0.4, 0.4), 1)
            return copy.deepcopy(data)

    def _publish(self, event_type: str, detail: dict[str, Any] | None = None) -> None:
        self._sequence += 1
        event = {"sequence": self._sequence, "type": event_type,
                 "timestamp": now_iso(), "detail": detail or {}, "state": self.snapshot()}
        for subscriber in list(self._subscribers):
            try:
                subscriber.put_nowait(copy.deepcopy(event))
            except queue.Full:
                pass

    def set_state(self, *, power: bool | None = None, brightness: int | None = None,
                  color_temperature: int | None = None) -> dict[str, Any]:
        with self._lock:
            fault = self._state.active_fault
            if fault == "offline":
                raise DeviceError("设备离线，控制命令无法送达")
            if power is not None:
                if fault == "stuck_on" and not power:
                    raise DeviceError("故障 stuck_on：设备无法关闭")
                if fault == "stuck_off" and power:
                    raise DeviceError("故障 stuck_off：设备无法开启")
                self._state.power = power
            if brightness is not None:
                if not 1 <= brightness <= 100:
                    raise ValueError("brightness 必须在 1..100 之间")
                self._state.brightness = brightness
            if color_temperature is not None:
                if not 1700 <= color_temperature <= 6500:
                    raise ValueError("color_temperature 必须在 1700..6500 K 之间")
                self._state.color_temperature = color_temperature
            self._state.updated_at = now_iso()
            self._publish("state_changed")
            return self.snapshot()

    def inject_fault(self, fault: str) -> dict[str, Any]:
        if fault not in SUPPORTED_FAULTS:
            raise ValueError(f"不支持的故障；可选值：{', '.join(sorted(SUPPORTED_FAULTS))}")
        with self._lock:
            self._state.active_fault = fault
            self._state.online = fault != "offline"
            if fault == "stuck_on": self._state.power = True
            if fault == "stuck_off": self._state.power = False
            if fault == "overheat": self._state.temperature_c = 75.0
            self._state.updated_at = now_iso()
            self._publish("fault_injected", {"fault": fault})
            return self.snapshot()

    def clear_fault(self) -> dict[str, Any]:
        with self._lock:
            previous = self._state.active_fault
            self._state.active_fault = None
            self._state.online = True
            self._state.temperature_c = 26.0
            self._state.updated_at = now_iso()
            self._publish("fault_cleared", {"previous_fault": previous})
            return self.snapshot()

    def subscribe(self) -> Iterator[dict[str, Any]]:
        subscriber: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=100)
        with self._lock:
            self._subscribers.append(subscriber)
            self._publish("snapshot", {"subscriber_connected": True})
        try:
            while True:
                try:
                    yield subscriber.get(timeout=10)
                except queue.Empty:
                    yield {"sequence": self._sequence, "type": "heartbeat",
                           "timestamp": now_iso(), "detail": {}, "state": self.snapshot()}
        finally:
            with self._lock:
                if subscriber in self._subscribers:
                    self._subscribers.remove(subscriber)

lamp = SimulatedLamp()

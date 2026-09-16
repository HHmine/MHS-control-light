"""Light-sensor interfaces and the deterministic simulated implementation."""
from __future__ import annotations

from datetime import datetime, timezone
import threading
import time
from typing import Any, Protocol


DEFAULT_AMBIENT_LUX = 30
DEFAULT_LIGHT_THRESHOLD = 40
LUX_PER_BRIGHTNESS = 2


class LightSensor(Protocol):
    source_id: str
    light_threshold: int

    def connectivity(self) -> tuple[bool, str]: ...

    def reading(self) -> dict[str, Any]: ...


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class SimulatedLightSensorAdapter:
    """Test sensor whose reading follows an injected lamp adapter."""

    source_id = "simulated_light_sensor"

    def __init__(
        self,
        lamp_adapter: Any = None,
        light_threshold: int = DEFAULT_LIGHT_THRESHOLD,
    ) -> None:
        self._lamp_adapter = lamp_adapter
        self.light_threshold = light_threshold
        self._lock = threading.Lock()

    def connectivity(self) -> tuple[bool, str]:
        return True, "simulated light sensor reachable"

    def reading(self) -> dict[str, Any]:
        with self._lock:
            power = False
            brightness = 50
            if self._lamp_adapter is not None:
                state = self._lamp_adapter.snapshot()
                power = bool(state.get("power"))
                brightness = int(state.get("brightness", brightness))
            lux = DEFAULT_AMBIENT_LUX + (
                brightness * LUX_PER_BRIGHTNESS if power else 0
            )
            captured_at = time.time()
            return {
                "source_id": self.source_id,
                "lux": lux,
                "light_detected": lux > self.light_threshold,
                "captured_at": captured_at,
                "timestamp": now_iso(),
            }


# Preserve the old project name for callers that import it directly.
LightSensorAdapter = SimulatedLightSensorAdapter

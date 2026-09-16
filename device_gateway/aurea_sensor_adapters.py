"""AUREA observation adapter backed by an independent light sensor."""
from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass
import time
from typing import Any, Mapping

from .tuya_sensor_adapter import TuyaLightSensorAdapter


_active_sensor: ContextVar[Any | None] = ContextVar(
    "aurea_light_sensor", default=None
)
_verification: ContextVar["SensorVerification | None"] = ContextVar(
    "aurea_sensor_verification", default=None
)


@dataclass(frozen=True, slots=True)
class SensorVerification:
    baseline_lux: int
    direction: int
    threshold: int
    timeout: float
    poll_interval: float


def bind_sensor_runtime(sensor: Any) -> Token[Any | None]:
    return _active_sensor.set(sensor)


def unbind_sensor_runtime(token: Token[Any | None]) -> None:
    _active_sensor.reset(token)


def bind_sensor_verification(value: SensorVerification) -> Token[SensorVerification | None]:
    return _verification.set(value)


def unbind_sensor_verification(token: Token[SensorVerification | None]) -> None:
    _verification.reset(token)


def _runtime_sensor(configuration: Mapping[str, object]) -> Any:
    existing = _active_sensor.get()
    if existing is not None:
        return existing
    credentials = configuration.get("credentials", {})
    if not isinstance(credentials, Mapping):
        raise ValueError("Tuya sensor credentials are missing")
    required = ("access_id", "access_key", "device_id")
    values = {name: str(credentials.get(name, "")) for name in required}
    if not all(values.values()):
        raise ValueError("Tuya sensor credentials are missing")
    return TuyaLightSensorAdapter(
        access_id=values["access_id"],
        access_key=values["access_key"],
        device_id=values["device_id"],
        api_endpoint=str(
            configuration.get("api_endpoint", "https://openapi.tuyacn.com")
        ),
        dp_code=str(configuration.get("dp_code", "bright_value")),
    )


class TuyaLightObservationAdapter:
    source_id = "tuya_light_sensor"

    def __init__(self, configuration: Mapping[str, object]) -> None:
        self.sensor = _runtime_sensor(configuration)

    def connectivity(self):
        from aurea.adapters.physical_device import ConnectivityResult

        check = getattr(self.sensor, "connectivity", None)
        if not callable(check):
            return ConnectivityResult(True, "bound light sensor available")
        reachable, detail = check()
        return ConnectivityResult(bool(reachable), str(detail))

    def read(self, request):
        from aurea.adapters.physical_device import RawDeviceObservation

        verification = _verification.get()
        if verification is None:
            raise RuntimeError("light-sensor verification context is missing")

        deadline = time.monotonic() + verification.timeout
        latest: dict[str, Any] | None = None
        delta = 0
        while True:
            latest = self.sensor.reading()
            delta = int(latest["lux"]) - verification.baseline_lux
            if delta * verification.direction >= verification.threshold:
                break
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            time.sleep(min(verification.poll_interval, remaining))

        captured_at = float(latest.get("captured_at", time.time()))
        return RawDeviceObservation(
            source_id=self.source_id,
            subject_id=request.subject_id,
            property_path=request.property_path,
            raw_value=delta,
            captured_at=captured_at,
            execution_id=request.execution_id,
            provenance={
                "adapter": "TuyaLightObservationAdapter",
                "baseline_lux": verification.baseline_lux,
                "observed_lux": int(latest["lux"]),
                "direction": verification.direction,
                "threshold": verification.threshold,
                "sensor_source_id": latest.get("source_id"),
                "sensor_timestamp": latest.get("timestamp"),
            },
        )


def create_observation_adapter(
    configuration: Mapping[str, object],
) -> TuyaLightObservationAdapter:
    return TuyaLightObservationAdapter(configuration)

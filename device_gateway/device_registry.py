from __future__ import annotations

import os
from typing import Any

from dotenv import load_dotenv

from .sensor_adapter import SimulatedLightSensorAdapter
from .simulated_lamp_adapter import lamp as simulated_lamp

load_dotenv()


def build_lamp_adapter() -> tuple[str, Any]:
    """Build the configured lamp adapter without exposing credentials upstream."""
    backend = os.getenv("DEVICE_BACKEND", "simulated").strip().lower()

    if backend == "simulated":
        return backend, simulated_lamp

    if backend == "yeelight":
        from .yeelight_adapter import YeelightAdapter

        ip = os.getenv("BEDSIDE_LAMP_IP", "").strip()
        token = os.getenv("BEDSIDE_LAMP_TOKEN", "").strip()
        if not ip or not token:
            raise RuntimeError(
                "DEVICE_BACKEND=yeelight 时必须配置 BEDSIDE_LAMP_IP 和 "
                "BEDSIDE_LAMP_TOKEN"
            )
        return backend, YeelightAdapter(ip=ip, token=token)

    raise RuntimeError(
        f"不支持的 DEVICE_BACKEND: {backend!r}；可选值为 simulated、yeelight"
    )


def build_sensor_adapter(lamp_adapter: Any = None) -> Any | None:
    """Build the configured independent light sensor without exposing secrets."""

    sensor_backend = os.getenv("SENSOR_BACKEND", "disabled").strip().lower()
    if sensor_backend in {"", "disabled", "none"}:
        return None
    if sensor_backend == "simulated":
        return SimulatedLightSensorAdapter(lamp_adapter=lamp_adapter)
    if sensor_backend == "tuya":
        from .tuya_sensor_adapter import TuyaLightSensorAdapter

        access_id = os.getenv("TUYA_ACCESS_ID", "").strip()
        access_key = os.getenv("TUYA_ACCESS_KEY", "").strip()
        device_id = os.getenv("TUYA_SENSOR_DEVICE_ID", "").strip()
        if not access_id or not access_key or not device_id:
            raise RuntimeError(
                "SENSOR_BACKEND=tuya 时必须配置 TUYA_ACCESS_ID、"
                "TUYA_ACCESS_KEY 和 TUYA_SENSOR_DEVICE_ID"
            )
        return TuyaLightSensorAdapter(
            access_id=access_id,
            access_key=access_key,
            device_id=device_id,
            api_endpoint=os.getenv(
                "TUYA_API_ENDPOINT", "https://openapi.tuyacn.com"
            ).strip(),
            dp_code=os.getenv("TUYA_SENSOR_DP_CODE", "bright_value").strip(),
            light_threshold=int(os.getenv("SENSOR_LIGHT_THRESHOLD", "10")),
        )

    raise RuntimeError(
        f"不支持的 SENSOR_BACKEND: {sensor_backend!r}；"
        "可选值为 disabled、simulated、tuya"
    )

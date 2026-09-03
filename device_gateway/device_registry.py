from __future__ import annotations

import os
from typing import Any

from dotenv import load_dotenv

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

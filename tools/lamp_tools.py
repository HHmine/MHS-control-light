"""openJiuwen tools for the simulated lamp service."""
from __future__ import annotations

import os
from typing import Any

import httpx
from openjiuwen.core.foundation.tool import tool

_port = os.getenv("PORT", "8000")
BASE_URL = os.getenv("DEVICE_SERVICE_URL", f"http://127.0.0.1:{_port}")


@tool(name="get_lamp_state", description="实时获取米家床头灯2的在线状态、电源状态、亮度、色温、温度和当前故障。", stateless=True)
def get_lamp_state() -> dict[str, Any]:
    """获取小灯当前状态。"""
    response = httpx.get(f"{BASE_URL}/api/device/state", timeout=10)
    response.raise_for_status()
    return response.json()


def _build_control_payload(
    power: bool | None,
    brightness: int | None,
    color_temperature: int | None,
) -> dict[str, Any]:
    # Some OpenAI-compatible models use 0 for an omitted optional integer.
    if brightness == 0:
        brightness = None
    if color_temperature == 0:
        color_temperature = None

    values = {
        "power": power,
        "brightness": brightness,
        "color_temperature": color_temperature,
    }
    return {key: value for key, value in values.items() if value is not None}


@tool(name="control_lamp", description="控制米家床头灯2的开关、亮度和色温。只开关灯时仅传 power，不要传未指定的参数，也不要用 0 表示未指定。power 为 true 表示开灯，false 表示关灯；亮度范围 1 到 100；色温范围 1700 到 6500 K。", stateless=True)
def control_lamp(power: bool | None = None, brightness: int | None = None, color_temperature: int | None = None) -> dict[str, Any]:
    """控制小灯。"""
    payload = _build_control_payload(power, brightness, color_temperature)
    response = httpx.post(f"{BASE_URL}/api/device/control", json=payload, timeout=10)
    response.raise_for_status()
    return response.json()


LAMP_TOOLS = [
    get_lamp_state,
    control_lamp,
]

# LegacyReActAgent executes a tool by the model-facing name. Keep ToolCard.id
# aligned with ToolCard.name so ResourceManager lookup succeeds.
for lamp_tool in LAMP_TOOLS:
    lamp_tool.card.id = lamp_tool.card.name

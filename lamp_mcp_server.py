"""MCP tools that expose the local lamp device gateway to JiuwenSwarm."""
from __future__ import annotations

import os
import time
from typing import Annotated, Any

import httpx
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from pydantic import Field

DEFAULT_DEVICE_SERVICE_URL = "http://127.0.0.1:8000"
DEVICE_SERVICE_URL = os.getenv(
    "DEVICE_SERVICE_URL",
    DEFAULT_DEVICE_SERVICE_URL,
).rstrip("/")

mcp = FastMCP(
    "lamp-control",
    instructions=(
        "Control the user's physical bedside lamp through the local device gateway. "
        "Always use the returned state as the source of truth."
    ),
    strict_input_validation=True,
)

_client = httpx.Client(
    base_url=DEVICE_SERVICE_URL,
    timeout=httpx.Timeout(15.0),
    headers={"Accept": "application/json"},
)


def _error_detail(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return response.text.strip() or f"HTTP {response.status_code}"
    if isinstance(body, dict):
        if body.get("error_code") == "EFFECT_NOT_VERIFIED":
            return _format_effect_not_verified(body)
        if isinstance(body.get("detail"), str):
            return body["detail"]
    return str(body)


def _format_effect_not_verified(body: dict[str, Any]) -> str:
    """Explain evidence failure without exposing hidden admin fault state."""
    details = body.get("error_details")
    if not isinstance(details, dict):
        return str(body.get("detail") or "ADA-DCC 效果证据校验未通过")
    evidence = details.get("evidence")
    evidence = evidence if isinstance(evidence, dict) else {}
    capability_id = details.get("capability_id", "unknown")
    ack = details.get("provider_acknowledgement", "UNKNOWN")
    authority = details.get("provider_acknowledgement_authority", "UNKNOWN")
    source = evidence.get("source", "unknown")
    state_path = evidence.get("state_path", "unknown")
    operator = evidence.get("operator", "unknown")
    expected = evidence.get("expected")
    observed = evidence.get("observed")
    message = (
        f"本次控制未确认成功：AHA-EA {capability_id} 的效果证据校验未通过。"
        f"设备 Provider 已返回 {ack}（权限级别 {authority}），但这只能证明指令已被接收，"
        f"不能证明实体效果已经发生。{source} 的 {state_path} 要求 {operator} {expected}，"
        f"实际观测值为 {observed}，因此 AUREA 判定为 EFFECT_NOT_VERIFIED，"
        "未报告设备已改变。"
    )
    state = details.get("state")
    if isinstance(state, dict) and "power" in state:
        message += f" 当前设备电源状态为{'开启' if state['power'] else '关闭'}。"
    return message


def _request_json(
    operation: str,
    method: str,
    path: str,
    *,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    started_at = time.perf_counter()
    try:
        response = _client.request(method, path, json=payload)
        response.raise_for_status()
        state = response.json()
    except httpx.HTTPStatusError as exc:
        detail = _error_detail(exc.response)
        raise ToolError(
            f"小灯设备网关拒绝了 {operation} 操作：{detail}"
        ) from exc
    except (httpx.TimeoutException, httpx.NetworkError) as exc:
        raise ToolError(
            f"无法连接小灯设备网关 {DEVICE_SERVICE_URL}：{exc}"
        ) from exc
    except ValueError as exc:
        raise ToolError("小灯设备网关返回了无效的 JSON") from exc

    gateway_elapsed = response.headers.get("X-Process-Time-Ms")
    return {
        "ok": True,
        "operation": operation,
        "total_elapsed_ms": round((time.perf_counter() - started_at) * 1000, 1),
        "gateway_elapsed_ms": float(gateway_elapsed) if gateway_elapsed else None,
        "state": state,
    }


@mcp.tool(
    name="get_lamp_gateway_health",
    description="检查本地小灯设备网关是否可用，并返回当前后端类型。此操作不会改变灯的状态。",
)
def get_lamp_gateway_health() -> dict[str, Any]:
    """Check the device gateway without changing the lamp."""
    return _request_json("health", "GET", "/health")


@mcp.tool(
    name="get_lamp_state",
    description=(
        "实时查询实体小灯的在线状态、设备自报电源、传感器推断电源、"
        "亮度、色温、温度和故障状态。"
    ),
)
def get_lamp_state() -> dict[str, Any]:
    """Read the current lamp state."""
    return _request_json("get_state", "GET", "/api/device/state")


@mcp.tool(
    name="control_lamp",
    description=(
        "控制实体小灯的开关、亮度和色温。只传用户明确要求改变的字段；"
        "执行成功后返回设备读取到的真实状态。"
    ),
)
def control_lamp(
    power: Annotated[
        bool | None,
        Field(description="true 表示开灯，false 表示关灯；未要求改变开关时省略。"),
    ] = None,
    brightness: Annotated[
        int | None,
        Field(ge=1, le=100, description="亮度百分比，范围 1 到 100；未要求时省略。"),
    ] = None,
    color_temperature: Annotated[
        int | None,
        Field(ge=1700, le=6500, description="色温，单位 K，范围 1700 到 6500；未要求时省略。"),
    ] = None,
) -> dict[str, Any]:
    """Apply one or more explicitly requested lamp controls."""
    payload = {
        key: value
        for key, value in {
            "power": power,
            "brightness": brightness,
            "color_temperature": color_temperature,
        }.items()
        if value is not None
    }
    if not payload:
        raise ToolError("control_lamp 至少需要 power、brightness 或 color_temperature 中的一项")
    return _request_json(
        "control",
        "POST",
        "/api/device/control",
        payload=payload,
    )


if __name__ == "__main__":
    mcp.run(transport="stdio", show_banner=False)

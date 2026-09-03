from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse

from .device_registry import build_lamp_adapter
from .device_service import DeviceService

backend, adapter = build_lamp_adapter()
service = DeviceService(backend, adapter)

app = FastAPI(
    title="智能体硬件控制演示系统",
    description="米家床头灯2的模拟/真实设备网关。",
    version="0.2.0",
    docs_url=None,
    redoc_url=None,
)
DOCS_HTML = Path(__file__).with_name("docs_zh.html").read_text(encoding="utf-8")


@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    started_at = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = (time.perf_counter() - started_at) * 1000
    response.headers["X-Process-Time-Ms"] = f"{elapsed_ms:.1f}"
    return response


@app.get("/docs", response_class=HTMLResponse, include_in_schema=False)
def chinese_docs() -> str:
    return DOCS_HTML


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def home() -> str:
    return DOCS_HTML


@app.get("/health")
def health() -> dict[str, Any]:
    return service.health()


@app.get("/api/device/state")
def get_state() -> dict[str, Any]:
    try:
        return service.get_state()
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/api/device/control")
def control(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        return service.control(
            power=payload.get("power"),
            brightness=payload.get("brightness"),
            color_temperature=payload.get("color_temperature"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/faults/inject")
def inject_fault(payload: dict[str, str]) -> dict[str, Any]:
    try:
        return service.inject_fault(payload["fault"])
    except KeyError as exc:
        raise HTTPException(status_code=400, detail="缺少 fault 参数") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/faults/clear")
def clear_fault() -> dict[str, Any]:
    try:
        return service.clear_fault()
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/api/real-faults/state")
def real_fault_status() -> dict[str, Any]:
    """Read the hidden fault state for the local admin webpage."""
    return service.real_fault_status()


@app.post("/api/real-faults/inject")
def inject_real_fault(payload: dict[str, str]) -> dict[str, Any]:
    """Enable a hidden black-box fault from the local admin webpage."""
    try:
        return service.inject_real_fault(payload["fault"])
    except KeyError as exc:
        raise HTTPException(status_code=400, detail="缺少 fault 参数") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/real-faults/clear")
def clear_real_fault() -> dict[str, Any]:
    """Disable the gateway guard for commands sent to the real lamp."""
    try:
        return service.clear_real_fault()
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/api/device/events")
def events() -> StreamingResponse:
    if not service.supports_faults:
        raise HTTPException(status_code=409, detail="真实设备模式暂不支持事件流")

    def stream():
        for event in service.subscribe():
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

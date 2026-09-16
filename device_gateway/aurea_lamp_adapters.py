"""AUREA physical-device adapters for the Yeelight bedside lamp."""
from __future__ import annotations

from contextvars import ContextVar
import time
from typing import Any, Mapping

from .yeelight_adapter import YeelightAdapter


_active_adapter: ContextVar[Any | None] = ContextVar("aurea_lamp_adapter", default=None)
_blocked_power: ContextVar[bool | None] = ContextVar("aurea_blocked_power", default=None)


def bind_runtime(adapter: Any, blocked_power: bool | None):
    adapter_token = _active_adapter.set(adapter)
    fault_token = _blocked_power.set(blocked_power)
    return adapter_token, fault_token


def unbind_runtime(tokens: tuple[Any, Any]) -> None:
    adapter_token, fault_token = tokens
    _blocked_power.reset(fault_token)
    _active_adapter.reset(adapter_token)


def _runtime_adapter(configuration: Mapping[str, object]) -> Any:
    existing = _active_adapter.get()
    if existing is not None:
        return existing
    credentials = configuration.get("credentials", {})
    if not isinstance(credentials, Mapping):
        raise ValueError("Yeelight credentials are missing")
    ip = str(credentials.get("ip", ""))
    token = str(credentials.get("token", ""))
    if not ip or not token:
        raise ValueError("Yeelight IP/token credentials are missing")
    return YeelightAdapter(ip=ip, token=token)


class YeelightPhysicalProvider:
    def __init__(self, configuration: Mapping[str, object]) -> None:
        self.adapter = _runtime_adapter(configuration)
        self.native_action = str(configuration.get("native_action", ""))

    @property
    def provider_id(self) -> str:
        return "yeelight"

    def connectivity(self):
        from aurea.adapters.physical_device import ConnectivityResult

        try:
            self.adapter.snapshot()
        except Exception as exc:
            return ConnectivityResult(False, f"Yeelight 不可达：{exc}")
        return ConnectivityResult(True, "Yeelight device reachable")

    def dispatch(self, invocation):
        from aurea.adapters.physical_device import ProviderDispatchReceipt

        started = time.time()
        blocked = _blocked_power.get()
        requested_power = invocation.parameters.get("power")
        is_blocked = requested_power is not None and requested_power is blocked
        if not is_blocked:
            self.adapter.set_state(**dict(invocation.parameters))
        return ProviderDispatchReceipt(
            execution_id=invocation.execution_id,
            provider_id=self.provider_id,
            accepted=True,
            acknowledgement="ACCEPTED",
            dispatched_at=started,
            native_response={"blocked_by_admin_fault": is_blocked},
        )


class YeelightObservationAdapter:
    def __init__(self, configuration: Mapping[str, object]) -> None:
        self.adapter = _runtime_adapter(configuration)

    @property
    def source_id(self) -> str:
        return "yeelight_readback"

    def connectivity(self):
        from aurea.adapters.physical_device import ConnectivityResult

        try:
            self.adapter.snapshot()
        except Exception as exc:
            return ConnectivityResult(False, f"Yeelight readback 不可达：{exc}")
        return ConnectivityResult(True, "Yeelight readback reachable")

    def read(self, request):
        from aurea.adapters.physical_device import RawDeviceObservation

        state = self.adapter.snapshot()
        value = state.get(request.property_path)
        return RawDeviceObservation(
            source_id=self.source_id,
            subject_id=request.subject_id,
            property_path=request.property_path,
            raw_value=value,
            captured_at=time.time(),
            execution_id=request.execution_id,
            provenance={"adapter": "YeelightObservationAdapter", "state": state},
        )


def create_provider_adapter(configuration: Mapping[str, object]) -> YeelightPhysicalProvider:
    return YeelightPhysicalProvider(configuration)


def create_observation_adapter(configuration: Mapping[str, object]) -> YeelightObservationAdapter:
    return YeelightObservationAdapter(configuration)

"""Execution modes for the lamp gateway.

Direct mode preserves the original gateway acknowledgement behavior. Aurea
 mode uses AHA-EA's generic ExecutionPort for one dispatch and then performs a
fresh adapter snapshot to verify the requested physical state.
"""
from __future__ import annotations

import importlib
import os
from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Any, Callable, Mapping, Protocol


class ExecutionError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        status: str = "EXECUTION_FAILED",
        details: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        # Details are intentionally limited to execution and evidence data.
        # Adapter internals (including administrator fault flags) must not
        # cross the gateway boundary.
        self.details = dict(details or {})


@dataclass(frozen=True, slots=True)
class ExecutionRequest:
    power: bool | None = None
    brightness: int | None = None
    color_temperature: int | None = None

    @property
    def parameters(self) -> dict[str, object]:
        return {
            key: value
            for key, value in {
                "power": self.power,
                "brightness": self.brightness,
                "color_temperature": self.color_temperature,
            }.items()
            if value is not None
        }


class ExecutionPort(Protocol):
    mode: str

    def control(
        self,
        request: ExecutionRequest,
        *,
        is_blocked: Callable[[bool | None], bool],
    ) -> dict[str, Any]: ...


class DirectExecutionPort:
    mode = "direct"

    def __init__(self, adapter: Any) -> None:
        self.adapter = adapter

    def control(
        self,
        request: ExecutionRequest,
        *,
        is_blocked: Callable[[bool | None], bool],
    ) -> dict[str, Any]:
        if is_blocked(request.power):
            acknowledged = dict(self.adapter.snapshot())
            acknowledged.update(request.parameters)
            return acknowledged
        return self.adapter.set_state(**request.parameters)


class AureaExecutionPort:
    mode = "aurea"

    def __init__(self, adapter: Any, sensor_adapter: Any | None = None) -> None:
        self.adapter = adapter
        self.sensor_adapter = sensor_adapter
        self._load_aurea_modules()

    def _load_aurea_modules(self) -> None:
        source_root = os.getenv("AUREA_SOURCE_ROOT", "").strip()
        candidate = Path(source_root).expanduser().resolve() if source_root else Path(__file__).resolve().parents[2] / "aurea-agent-southbound-access" / "src"
        if candidate.exists() and str(candidate) not in sys.path:
            sys.path.insert(0, str(candidate))
        repository_root = candidate.parent
        if repository_root.exists() and str(repository_root) not in sys.path:
            # AUREA's ExecutionPort imports its evaluation EnvironmentAdapter
            # from the repository root in addition to the ``src`` package.
            sys.path.insert(0, str(repository_root))
        lab_source = repository_root / "experiments" / "lab_simulation" / "src"
        if lab_source.exists() and str(lab_source) not in sys.path:
            sys.path.insert(0, str(lab_source))
        try:
            physical_module = importlib.import_module("aurea.adapters.physical_device")
            dcc_module = importlib.import_module("aurea.core.ada_dcc")
            self._execute = physical_module.execute_authorized_capability
            self._preflight = physical_module.physical_preflight
            self._load_profile = physical_module.load_deployment_profile
            self._parse_contract = dcc_module.parse_ada_dcc_contract
            self._bind_runtime = importlib.import_module(
                "device_gateway.aurea_lamp_adapters"
            ).bind_runtime
            self._unbind_runtime = importlib.import_module(
                "device_gateway.aurea_lamp_adapters"
            ).unbind_runtime
            sensor_module = importlib.import_module(
                "device_gateway.aurea_sensor_adapters"
            )
            self._sensor_verification_type = sensor_module.SensorVerification
            self._bind_sensor_runtime = sensor_module.bind_sensor_runtime
            self._unbind_sensor_runtime = sensor_module.unbind_sensor_runtime
            self._bind_sensor_verification = sensor_module.bind_sensor_verification
            self._unbind_sensor_verification = sensor_module.unbind_sensor_verification
        except (ImportError, AttributeError) as exc:
            raise ExecutionError("EXECUTION_MODE=aurea 需要可导入 AUREA physical-device 模块；请设置 AUREA_SOURCE_ROOT", status="AUREA_UNAVAILABLE") from exc

    def control(self, request: ExecutionRequest, *, is_blocked: Callable[[bool | None], bool]) -> dict[str, Any]:
        if not request.parameters:
            raise ExecutionError("AUREA 控制请求不能为空", status="REJECTED")
        profile_path = Path(__file__).with_name("aurea") / "lamp.deployment.json"
        try:
            profile = self._load_profile(profile_path)
        except Exception as exc:
            raise ExecutionError(
                f"AUREA deployment profile 加载失败：{exc}",
                status="AUREA_PREFLIGHT_FAILED",
            ) from exc
        result: Any = None
        for field, expected in request.parameters.items():
            if field == "power":
                capability_id = "lamp.power_on" if expected is True else "lamp.power_off"
            elif field == "brightness":
                capability_id = "lamp.set_brightness"
            elif field == "color_temperature":
                capability_id = "lamp.set_color_temperature"
            else:
                raise ExecutionError(f"AUREA 不支持参数：{field}", status="REJECTED")

            try:
                from .aurea_contracts import load_fixed_contract

                contract = load_fixed_contract(
                    capability_id,
                    {field: expected},
                    parser=self._parse_contract,
                )
            except Exception as exc:
                raise ExecutionError(
                    f"固定 ADA-DCC 加载失败：{exc}",
                    status="AUREA_PREFLIGHT_FAILED",
                ) from exc
            if field == "power" and self.sensor_adapter is None:
                raise ExecutionError(
                    "AUREA 开关效果验证需要配置独立光传感器",
                    status="AUREA_PREFLIGHT_FAILED",
                )

            tokens = self._bind_runtime(self.adapter, expected if field == "power" and is_blocked(expected) else None)
            sensor_token = (
                self._bind_sensor_runtime(self.sensor_adapter)
                if field == "power"
                else None
            )
            try:
                # Bind the runtime adapter for both preflight and execution.
                # This keeps tests and injected-fault runs on the supplied
                # adapter instead of constructing a new real-device client.
                try:
                    report = self._preflight(contract, profile)
                except Exception as exc:
                    raise ExecutionError(
                        f"AUREA physical-device preflight 失败：{exc}",
                        status="AUREA_PREFLIGHT_FAILED",
                    ) from exc
                if not report.passed:
                    raise ExecutionError(
                        "AUREA physical-device preflight 未通过："
                        + "; ".join(report.errors),
                        status="AUREA_PREFLIGHT_FAILED",
                    )
                verification_token = None
                if field == "power":
                    try:
                        baseline = self.sensor_adapter.reading()
                        baseline_lux = int(baseline["lux"])
                    except Exception as exc:
                        raise ExecutionError(
                            f"读取光传感器基线失败：{exc}",
                            status="AUREA_PREFLIGHT_FAILED",
                        ) from exc
                    timeout = float(os.getenv("SENSOR_VERIFY_TIMEOUT", "6"))
                    poll_interval = float(
                        os.getenv("SENSOR_VERIFY_POLL_INTERVAL", "0.5")
                    )
                    if timeout <= 0 or poll_interval <= 0:
                        raise ExecutionError(
                            "传感器验证超时和轮询间隔必须大于 0",
                            status="AUREA_PREFLIGHT_FAILED",
                        )
                    contract_threshold = abs(
                        int(
                            contract.evidence_requirements[0]
                            .predicate.expected.native
                        )
                    )
                    verification_token = self._bind_sensor_verification(
                        self._sensor_verification_type(
                            baseline_lux=baseline_lux,
                            direction=1 if expected is True else -1,
                            threshold=contract_threshold,
                            timeout=timeout,
                            poll_interval=poll_interval,
                        )
                    )
                try:
                    result = self._execute(
                        contract,
                        profile,
                        parameters={field: expected},
                        verified_state={},
                    )
                finally:
                    if verification_token is not None:
                        self._unbind_sensor_verification(verification_token)
            except Exception as exc:
                if isinstance(exc, ExecutionError):
                    raise
                raise ExecutionError(f"AUREA physical-device 执行失败：{exc}", status="AUREA_DISPATCH_FAILED") from exc
            finally:
                if sensor_token is not None:
                    self._unbind_sensor_runtime(sensor_token)
                self._unbind_runtime(tokens)
            if result.disposition != "VERIFIED_EFFECT":
                details = self._effect_failure_details(
                    contract,
                    result,
                    field=field,
                    expected=expected,
                )
                raise ExecutionError(
                    self._effect_failure_message(details),
                    status="EFFECT_NOT_VERIFIED",
                    details=details,
                )
        return self.adapter.snapshot()

    @staticmethod
    def _safe_value(value: Any) -> Any:
        """Convert contract/AUREA values to JSON-safe primitive values."""
        native = getattr(value, "native", value)
        if isinstance(native, (str, int, float, bool)) or native is None:
            return native
        return str(native)

    def _effect_failure_details(
        self,
        contract: Any,
        result: Any,
        *,
        field: str,
        expected: Any,
    ) -> dict[str, Any]:
        requirement_results = dict(getattr(result, "requirement_results", {}) or {})
        failed_ids = [
            str(requirement_id)
            for requirement_id, passed in requirement_results.items()
            if not passed
        ]
        requirements = {
            str(item.requirement_id): item
            for item in getattr(contract, "evidence_requirements", ())
        }
        requirement_id = failed_ids[0] if failed_ids else None
        requirement = requirements.get(requirement_id) if requirement_id else None
        predicate = getattr(requirement, "predicate", None)
        state = getattr(predicate, "state", None)
        expected_value = getattr(predicate, "expected", None)
        operator = getattr(predicate, "operator", None)
        operator_text = getattr(operator, "value", operator)
        source = getattr(requirement, "source", None)

        observation = None
        for candidate in getattr(result, "semantic_observations", ()):
            if requirement_id is None or (
                getattr(candidate, "source_id", None)
                == getattr(source, "source_id", None)
                and getattr(candidate, "state_path", None)
                == getattr(state, "path", None)
            ):
                observation = candidate
                break

        actual_state: dict[str, Any] | None
        try:
            snapshot = self.adapter.snapshot()
            actual_state = dict(snapshot) if isinstance(snapshot, Mapping) else None
        except Exception:
            actual_state = None

        evidence: dict[str, Any] = {
            "requirement_id": requirement_id,
            "source": getattr(source, "source_id", None),
            "state_path": getattr(state, "path", None),
            "operator": str(operator_text) if operator_text is not None else None,
            "expected": self._safe_value(expected_value),
            "observed": self._safe_value(
                getattr(observation, "normalized_value", None)
                if observation is not None
                else None
            ),
            "captured_after_invocation": (
                getattr(observation, "execution_id", None)
                == getattr(result, "execution_id", None)
                if observation is not None
                else False
            ),
        }
        return {
            "phase": "post_dispatch_evidence",
            "capability_id": str(getattr(result, "capability_id", "")),
            "requested_field": field,
            "requested_value": expected,
            "provider_acknowledgement": str(
                getattr(result, "provider_acknowledgement", "UNKNOWN")
            ),
            "provider_acknowledgement_authority": str(
                getattr(result, "provider_acknowledgement_authority", "UNKNOWN")
            ),
            "requirement_results": requirement_results,
            "evidence": evidence,
            "state": actual_state,
            "disposition": str(getattr(result, "disposition", "EFFECT_NOT_VERIFIED")),
        }

    @staticmethod
    def _effect_failure_message(details: Mapping[str, Any]) -> str:
        evidence = details.get("evidence", {})
        capability_id = details.get("capability_id", "unknown")
        ack = details.get("provider_acknowledgement", "UNKNOWN")
        authority = details.get("provider_acknowledgement_authority", "UNKNOWN")
        source = evidence.get("source", "unknown")
        state_path = evidence.get("state_path", "unknown")
        operator = evidence.get("operator", "unknown")
        expected = evidence.get("expected")
        observed = evidence.get("observed")
        return (
            f"小灯控制效果未验证：AHA-EA {capability_id} 的效果证据校验未通过："
            f"Provider 已返回 {ack}（权限级别 {authority}），"
            f"但 {source} 的 {state_path} 需要 {operator} {expected}，"
            f"实际观测为 {observed}；本次执行判定为 EFFECT_NOT_VERIFIED，"
            "未确认实体设备已达到请求状态。"
        )


def build_execution_port(
    mode: str,
    adapter: Any,
    *,
    sensor_adapter: Any | None = None,
) -> ExecutionPort:
    normalized = mode.strip().lower()
    if normalized == "direct":
        return DirectExecutionPort(adapter)
    if normalized == "aurea":
        return AureaExecutionPort(adapter, sensor_adapter=sensor_adapter)
    raise ValueError("EXECUTION_MODE 必须是 direct 或 aurea")

from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
AUREA_ROOT = ROOT.parent / "aurea-agent-southbound-access"
for candidate in (
    AUREA_ROOT / "src",
    AUREA_ROOT,
    AUREA_ROOT / "experiments" / "lab_simulation" / "src",
):
    if candidate.exists() and str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from device_gateway.aurea_contracts import (  # noqa: E402
    CAPABILITY_FILES,
    capability_contract_path,
    load_fixed_contract,
)


class AureaArtifactTests(unittest.TestCase):
    def test_all_fixed_contracts_exist_and_parse(self) -> None:
        from aurea.core.ada_dcc import parse_ada_dcc_contract

        for capability_id, filename in CAPABILITY_FILES.items():
            path = capability_contract_path(capability_id)
            self.assertEqual(path.name, filename)
            self.assertTrue(path.is_file())
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["capability_id"], capability_id)
            contract = load_fixed_contract(
                capability_id,
                self._sample_parameters(capability_id),
                parser=parse_ada_dcc_contract,
            )
            self.assertEqual(contract.subject.subject_id, "bedside_lamp")
            expected_source = (
                "tuya_light_sensor"
                if capability_id.startswith("lamp.power_")
                else "yeelight_readback"
            )
            self.assertEqual(
                contract.evidence_requirements[0].source.source_id,
                expected_source,
            )

    def test_deployment_profile_loads_and_maps_each_capability_once(self) -> None:
        from aurea.adapters.physical_device import load_deployment_profile

        profile_path = ROOT / "device_gateway" / "aurea" / "lamp.deployment.json"
        profile = load_deployment_profile(profile_path)
        bindings = profile["capability_bindings"]
        self.assertEqual(
            [item["capability_id"] for item in bindings],
            list(CAPABILITY_FILES),
        )
        for item in bindings:
            self.assertEqual(item["subject_id"], "bedside_lamp")
            self.assertEqual(
                item["provider_adapter"]["implementation"],
                "device_gateway.aurea_lamp_adapters:create_provider_adapter",
            )

    def test_physical_preflight_passes_with_bound_test_adapter(self) -> None:
        from aurea.adapters.physical_device import (
            load_deployment_profile,
            physical_preflight,
        )
        from aurea.core.ada_dcc import parse_ada_dcc_contract
        from device_gateway.aurea_contracts import load_contract_document
        from device_gateway.aurea_lamp_adapters import bind_runtime, unbind_runtime
        from device_gateway.aurea_sensor_adapters import (
            bind_sensor_runtime,
            unbind_sensor_runtime,
        )
        from tests.test_execution_port import FakeLampAdapter, FakeLightSensor

        profile = load_deployment_profile(ROOT / "device_gateway" / "aurea" / "lamp.deployment.json")
        contract = parse_ada_dcc_contract(load_contract_document("lamp.power_on"))
        lamp = FakeLampAdapter()
        values = {
            "BEDSIDE_LAMP_IP": "test",
            "BEDSIDE_LAMP_TOKEN": "test",
            "TUYA_ACCESS_ID": "test",
            "TUYA_ACCESS_KEY": "test",
            "TUYA_SENSOR_DEVICE_ID": "test",
        }
        with patch.dict(os.environ, values):
            lamp_tokens = bind_runtime(lamp, None)
            sensor_token = bind_sensor_runtime(FakeLightSensor(lamp))
            try:
                report = physical_preflight(contract, profile)
            finally:
                unbind_sensor_runtime(sensor_token)
                unbind_runtime(lamp_tokens)
        self.assertTrue(report.passed, report.errors)
        self.assertIn("PROVIDER_REACHABLE", report.checks)

    def test_artifacts_contain_references_not_device_secrets(self) -> None:
        forbidden = ("BEDSIDE_LAMP_IP", "BEDSIDE_LAMP_TOKEN")
        for path in (
            ROOT / "device_gateway" / "aurea" / "lamp.source.json",
            ROOT / "device_gateway" / "aurea" / "lamp.review.json",
            *(
                ROOT / "device_gateway" / "aurea" / filename
                for filename in CAPABILITY_FILES.values()
            ),
        ):
            text = path.read_text(encoding="utf-8")
            self.assertFalse(any(secret in text for secret in forbidden), path.name)

    @staticmethod
    def _sample_parameters(capability_id: str) -> dict[str, object]:
        if capability_id.startswith("lamp.power_"):
            return {"power": capability_id.endswith("power_on")}
        if capability_id == "lamp.set_brightness":
            return {"brightness": 55}
        return {"color_temperature": 3200}


if __name__ == "__main__":
    unittest.main()

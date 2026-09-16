from __future__ import annotations

import os
from pathlib import Path
import time
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from device_gateway import api
from device_gateway.device_service import DeviceService


class FakeLampAdapter:
    def __init__(self) -> None:
        self.power = False
        self.brightness = 50
        self.color_temperature = 4000
        self.calls: list[dict[str, object]] = []

    def snapshot(self) -> dict[str, object]:
        return {
            "device_id": "fake-lamp",
            "model": "fake",
            "backend": "yeelight",
            "online": True,
            "power": self.power,
            "brightness": self.brightness,
            "color_temperature": self.color_temperature,
            "active_fault": None,
        }

    def set_state(
        self,
        *,
        power: bool | None = None,
        brightness: int | None = None,
        color_temperature: int | None = None,
    ) -> dict[str, object]:
        self.calls.append({
            "power": power,
            "brightness": brightness,
            "color_temperature": color_temperature,
        })
        if power is not None:
            self.power = power
        if brightness is not None:
            self.brightness = brightness
        if color_temperature is not None:
            self.color_temperature = color_temperature
        return self.snapshot()


class FakeLightSensor:
    source_id = "fake_light_sensor"
    light_threshold = 40

    def __init__(self, lamp: FakeLampAdapter) -> None:
        self.lamp = lamp

    def connectivity(self) -> tuple[bool, str]:
        return True, "fake sensor reachable"

    def reading(self) -> dict[str, object]:
        lux = 230 if self.lamp.power else 30
        return {
            "source_id": self.source_id,
            "lux": lux,
            "light_detected": lux > self.light_threshold,
            "captured_at": time.time(),
            "timestamp": "test",
        }


class ExecutionPortTests(unittest.TestCase):
    def setUp(self) -> None:
        values = {
            "TUYA_ACCESS_ID": "test",
            "TUYA_ACCESS_KEY": "test",
            "TUYA_SENSOR_DEVICE_ID": "test",
            "SENSOR_VERIFY_TIMEOUT": "0.01",
            "SENSOR_VERIFY_POLL_INTERVAL": "0.001",
        }
        self.environment_patch = patch.dict(os.environ, values)
        self.environment_patch.start()
        self.addCleanup(self.environment_patch.stop)

    def test_direct_mode_preserves_existing_control(self) -> None:
        adapter = FakeLampAdapter()
        service = DeviceService("yeelight", adapter, execution_mode="direct")

        state = service.control(power=True, brightness=80)

        self.assertTrue(state["power"])
        self.assertEqual(state["brightness"], 80)
        self.assertEqual(len(adapter.calls), 1)
        self.assertEqual(service.health()["execution_mode"], "direct")

    def test_aurea_mode_verifies_fresh_device_state(self) -> None:
        old_root = os.environ.get("AUREA_SOURCE_ROOT")
        os.environ["AUREA_SOURCE_ROOT"] = str(
            Path(__file__).resolve().parents[2]
            / "aurea-agent-southbound-access"
            / "src"
        )
        self.addCleanup(self._restore_aurea_root, old_root)

        adapter = FakeLampAdapter()
        service = DeviceService(
            "yeelight",
            adapter,
            execution_mode="aurea",
            sensor_adapter=FakeLightSensor(adapter),
        )

        state = service.control(power=True)

        self.assertTrue(state["power"])
        self.assertEqual(len(adapter.calls), 1)

    def test_aurea_mode_rejects_black_box_fake_success(self) -> None:
        old_root = os.environ.get("AUREA_SOURCE_ROOT")
        os.environ["AUREA_SOURCE_ROOT"] = str(
            Path(__file__).resolve().parents[2]
            / "aurea-agent-southbound-access"
            / "src"
        )
        self.addCleanup(self._restore_aurea_root, old_root)

        adapter = FakeLampAdapter()
        adapter.power = True
        service = DeviceService(
            "yeelight",
            adapter,
            execution_mode="aurea",
            sensor_adapter=FakeLightSensor(adapter),
        )
        service.inject_real_fault("block_power_off")

        with self.assertRaisesRegex(RuntimeError, "效果未验证") as context:
            service.control(power=False)

        self.assertEqual(getattr(context.exception, "status", None), "EFFECT_NOT_VERIFIED")
        details = getattr(context.exception, "details", {})
        self.assertEqual(details["phase"], "post_dispatch_evidence")
        self.assertEqual(details["capability_id"], "lamp.power_off")
        self.assertEqual(details["provider_acknowledgement"], "ACCEPTED")
        self.assertEqual(details["provider_acknowledgement_authority"], "LINEAGE_ONLY")
        self.assertEqual(details["evidence"]["source"], "tuya_light_sensor")
        self.assertEqual(details["evidence"]["state_path"], "illumination.lux_delta")
        self.assertEqual(details["evidence"]["observed"], 0)
        self.assertTrue(adapter.snapshot()["power"])
        self.assertEqual(adapter.calls, [])

    def test_api_maps_unverified_effect_to_conflict(self) -> None:
        old_root = os.environ.get("AUREA_SOURCE_ROOT")
        os.environ["AUREA_SOURCE_ROOT"] = str(
            Path(__file__).resolve().parents[2]
            / "aurea-agent-southbound-access"
            / "src"
        )
        self.addCleanup(self._restore_aurea_root, old_root)

        adapter = FakeLampAdapter()
        adapter.power = True
        service = DeviceService(
            "yeelight",
            adapter,
            execution_mode="aurea",
            sensor_adapter=FakeLightSensor(adapter),
        )
        service.inject_real_fault("block_power_off")
        with patch.object(api, "service", service):
            response = TestClient(api.app).post(
                "/api/device/control",
                json={"power": False},
            )

        self.assertEqual(response.status_code, 409)
        self.assertIn("效果未验证", response.json()["detail"])
        self.assertEqual(response.json()["error_code"], "EFFECT_NOT_VERIFIED")
        self.assertEqual(
            response.json()["error_details"]["evidence"]["expected"],
            -100,
        )
        self.assertEqual(
            response.json()["error_details"]["evidence"]["observed"],
            0,
        )

    def test_aurea_power_requires_independent_sensor(self) -> None:
        adapter = FakeLampAdapter()
        service = DeviceService("yeelight", adapter, execution_mode="aurea")

        with self.assertRaisesRegex(RuntimeError, "独立光传感器") as context:
            service.control(power=True)

        self.assertEqual(
            getattr(context.exception, "status", None),
            "AUREA_PREFLIGHT_FAILED",
        )
        self.assertEqual(adapter.calls, [])

    @staticmethod
    def _restore_aurea_root(value: str | None) -> None:
        if value is None:
            os.environ.pop("AUREA_SOURCE_ROOT", None)
        else:
            os.environ["AUREA_SOURCE_ROOT"] = value


if __name__ == "__main__":
    unittest.main()

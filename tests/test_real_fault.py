from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from device_gateway import api
from device_gateway.device_service import DeviceService


class FakeLampAdapter:
    def __init__(self) -> None:
        self.power = False
        self.calls: list[dict[str, object]] = []

    def snapshot(self) -> dict[str, object]:
        return {
            "device_id": "fake-real-lamp",
            "backend": "yeelight",
            "online": True,
            "power": self.power,
            "active_fault": None,
        }

    def set_state(
        self,
        *,
        power: bool | None = None,
        brightness: int | None = None,
        color_temperature: int | None = None,
    ) -> dict[str, object]:
        self.calls.append(
            {
                "power": power,
                "brightness": brightness,
                "color_temperature": color_temperature,
            }
        )
        if power is not None:
            self.power = power
        return self.snapshot()


class RealFaultTests(unittest.TestCase):
    def setUp(self) -> None:
        self.adapter = FakeLampAdapter()
        self.service = DeviceService("yeelight", self.adapter, execution_mode="direct")

    def test_block_power_on_acknowledges_success_without_adapter_call(self) -> None:
        status = self.service.inject_real_fault("block_power_on")
        self.assertEqual(status["active_real_fault"], "block_power_on")

        acknowledged = self.service.control(power=True, brightness=40)

        self.assertEqual(self.adapter.calls, [])
        self.assertTrue(acknowledged["power"])
        self.assertEqual(acknowledged["brightness"], 40)
        actual_state = self.service.get_state()
        self.assertFalse(actual_state["power"])
        self.assertNotIn("gateway_control_fault", actual_state)

    def test_power_off_remains_available_while_fault_is_active(self) -> None:
        self.adapter.power = True
        self.service.inject_real_fault("block_power_on")

        state = self.service.control(power=False)

        self.assertFalse(state["power"])
        self.assertEqual(len(self.adapter.calls), 1)

    def test_block_power_off_acknowledges_success_without_adapter_call(self) -> None:
        self.adapter.power = True
        status = self.service.inject_real_fault("block_power_off")
        self.assertEqual(status["active_real_fault"], "block_power_off")

        acknowledged = self.service.control(power=False)

        self.assertEqual(self.adapter.calls, [])
        self.assertFalse(acknowledged["power"])
        self.assertTrue(self.service.get_state()["power"])

    def test_power_on_remains_available_during_block_power_off(self) -> None:
        self.service.inject_real_fault("block_power_off")

        state = self.service.control(power=True)

        self.assertTrue(state["power"])
        self.assertEqual(len(self.adapter.calls), 1)

    def test_clear_restores_power_on(self) -> None:
        self.service.inject_real_fault("block_power_on")
        result = self.service.clear_real_fault()
        self.assertIsNone(result["active_real_fault"])
        self.assertEqual(result["previous_real_fault"], "block_power_on")

        state = self.service.control(power=True)

        self.assertTrue(state["power"])
        self.assertEqual(len(self.adapter.calls), 1)

    def test_real_fault_is_rejected_for_simulated_backend(self) -> None:
        service = DeviceService("simulated", self.adapter, execution_mode="direct")
        with self.assertRaisesRegex(RuntimeError, "仅支持 yeelight"):
            service.inject_real_fault("block_power_on")

    def test_http_inject_returns_success_without_reaching_adapter(self) -> None:
        with patch.object(api, "service", self.service):
            client = TestClient(api.app)
            injected = client.post(
                "/api/real-faults/inject",
                json={"fault": "block_power_on"},
            )
            blocked = client.post(
                "/api/device/control",
                json={"power": True},
            )
            actual = client.get("/api/device/state")
            health = client.get("/health")

        self.assertEqual(injected.status_code, 200)
        self.assertEqual(blocked.status_code, 200)
        self.assertTrue(blocked.json()["power"])
        self.assertFalse(actual.json()["power"])
        self.assertEqual(self.adapter.calls, [])
        self.assertNotIn("active_real_fault", actual.json())
        self.assertNotIn("active_real_fault", health.json())

    def test_http_block_power_off_returns_fake_success(self) -> None:
        self.adapter.power = True
        with patch.object(api, "service", self.service):
            client = TestClient(api.app)
            injected = client.post(
                "/api/real-faults/inject",
                json={"fault": "block_power_off"},
            )
            blocked = client.post(
                "/api/device/control",
                json={"power": False},
            )
            actual = client.get("/api/device/state")

        self.assertEqual(injected.status_code, 200)
        self.assertEqual(blocked.status_code, 200)
        self.assertFalse(blocked.json()["power"])
        self.assertTrue(actual.json()["power"])
        self.assertEqual(self.adapter.calls, [])

    def test_admin_page_exposes_black_box_fault_controls(self) -> None:
        with patch.object(api, "service", self.service):
            client = TestClient(api.app)
            page = client.get("/")

        self.assertEqual(page.status_code, 200)
        self.assertIn("真实设备黑盒故障注入", page.text)
        self.assertIn("禁止开灯（HTTP 仍返回成功）", page.text)
        self.assertIn("禁止关灯（HTTP 仍返回成功）", page.text)
        self.assertIn("/api/real-faults/inject", page.text)
        self.assertIn("Agent 不会看到故障配置", page.text)
        control_position = page.text.index("<h2>控制小灯</h2>")
        real_fault_position = page.text.index("<h2>真实设备黑盒故障注入</h2>")
        grid_end_position = page.text.index("</div>", real_fault_position)
        self.assertLess(control_position, real_fault_position)
        self.assertLess(real_fault_position, grid_end_position)


if __name__ == "__main__":
    unittest.main()

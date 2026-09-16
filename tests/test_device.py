from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from device_gateway import api
from device_gateway.device_service import DeviceService
from device_gateway.sensor_adapter import SimulatedLightSensorAdapter
from device_gateway.simulated_lamp_adapter import SimulatedLamp


class DeviceGatewayTests(unittest.TestCase):
    """Exercise the HTTP API with a fresh in-memory lamp, never real hardware."""

    def setUp(self) -> None:
        self.service = DeviceService("simulated", SimulatedLamp(), execution_mode="direct")
        self.service_patch = patch.object(api, "service", self.service)
        self.service_patch.start()
        self.addCleanup(self.service_patch.stop)
        self.client = TestClient(api.app)

    def test_health_and_state(self) -> None:
        self.assertTrue(self.client.get("/health").json()["ok"])
        state = self.client.get("/api/device/state").json()
        self.assertEqual(state["device_id"], "bedside-lamp-2-demo")
        self.assertEqual(state["backend"] if "backend" in state else "simulated", "simulated")

    def test_control_and_fault_lifecycle(self) -> None:
        state = self.client.post(
            "/api/device/control",
            json={"power": True, "brightness": 80},
        ).json()
        self.assertTrue(state["power"])
        self.assertEqual(state["brightness"], 80)

        state = self.client.post(
            "/api/faults/inject",
            json={"fault": "stuck_on"},
        ).json()
        self.assertEqual(state["active_fault"], "stuck_on")
        self.assertTrue(state["power"])
        self.assertEqual(
            self.client.post(
                "/api/device/control",
                json={"power": False},
            ).status_code,
            409,
        )

        state = self.client.post("/api/faults/clear").json()
        self.assertIsNone(state["active_fault"])
        self.assertTrue(state["online"])

    def test_sensor_reading_and_observed_power(self) -> None:
        lamp = SimulatedLamp()
        sensor = SimulatedLightSensorAdapter(lamp)
        service = DeviceService(
            "simulated",
            lamp,
            execution_mode="direct",
            sensor_adapter=sensor,
        )
        with patch.object(api, "service", service):
            client = TestClient(api.app)
            off = client.get("/api/device/state").json()
            reading = client.get("/api/sensor/reading").json()
            client.post("/api/device/control", json={"power": True})
            on = client.get("/api/device/state").json()

        self.assertEqual(off["observed_power"], "off")
        self.assertFalse(reading["light_detected"])
        self.assertEqual(on["observed_power"], "on")
        self.assertGreater(
            on["sensor_observation"]["lux"],
            off["sensor_observation"]["lux"],
        )


if __name__ == "__main__":
    unittest.main()

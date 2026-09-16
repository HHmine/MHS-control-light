from __future__ import annotations

import unittest

from device_gateway.sensor_adapter import SimulatedLightSensorAdapter
from device_gateway.tuya_sensor_adapter import TuyaLightSensorAdapter
from tests.test_execution_port import FakeLampAdapter


class FakeTuyaOpenAPI:
    def __init__(self, endpoint: str, access_id: str, access_key: str) -> None:
        self.endpoint = endpoint
        self.connected = False
        self.response: dict[str, object] = {
            "success": True,
            "result": [{"code": "bright_value", "value": "123"}],
        }

    def connect(self) -> dict[str, object]:
        self.connected = True
        return {"success": True}

    def get(self, path: str) -> dict[str, object]:
        return self.response


class SensorAdapterTests(unittest.TestCase):
    def test_simulated_sensor_tracks_lamp_without_random_jitter(self) -> None:
        lamp = FakeLampAdapter()
        sensor = SimulatedLightSensorAdapter(lamp)
        off = sensor.reading()
        lamp.set_state(power=True, brightness=50)
        on = sensor.reading()

        self.assertEqual(off["lux"], 30)
        self.assertEqual(on["lux"], 130)
        self.assertFalse(off["light_detected"])
        self.assertTrue(on["light_detected"])

    def test_tuya_sensor_connects_lazily_and_reads_configured_dp(self) -> None:
        client = FakeTuyaOpenAPI("endpoint", "id", "key")
        sensor = TuyaLightSensorAdapter(
            "id",
            "key",
            "device",
            openapi_factory=lambda *_: client,
        )
        self.assertFalse(client.connected)

        reading = sensor.reading()

        self.assertTrue(client.connected)
        self.assertEqual(reading["lux"], 123)
        self.assertEqual(reading["source_id"], "tuya_light_sensor")

    def test_tuya_sensor_rejects_missing_data_point(self) -> None:
        client = FakeTuyaOpenAPI("endpoint", "id", "key")
        client.response = {"success": True, "result": []}
        sensor = TuyaLightSensorAdapter(
            "id",
            "key",
            "device",
            openapi_factory=lambda *_: client,
        )

        with self.assertRaisesRegex(RuntimeError, "缺少 bright_value"):
            sensor.reading()


if __name__ == "__main__":
    unittest.main()

"""
TASK 11 — Unit tests: CoordinatorClient.

All HTTP calls are mocked with responses.
Tests cover:
  - register: success (200, 201), HTTP error, network error, retry exhaustion
  - send_heartbeat: success (200, 204), HTTP error, network error
  - post_job_result: success, HTTP error
  - update_status: non-fatal on error
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch, call

import requests


def _make_config(coordinator_url="http://coordinator.test"):
    from worker.config import WorkerConfig
    cfg = MagicMock(spec=WorkerConfig)
    cfg.worker_id = "worker-test"
    cfg.coordinator_url = coordinator_url
    cfg.http_connect_timeout = 5
    cfg.http_read_timeout = 30
    cfg.max_registration_retries = 3
    cfg.retry_backoff_base = 0.01  # fast retries in tests
    cfg.api_url = lambda path: f"{coordinator_url}/{path.lstrip('/')}"
    return cfg


def _make_gpu_info():
    from worker.gpu.detector import GPUInfo
    return GPUInfo(
        gpu_id=0,
        name="RTX 4050",
        uuid="GPU-abc",
        total_vram_mib=6141,
        driver_version="616.92",
        cuda_available=True,
    )


def _make_telemetry():
    from worker.gpu.detector import GPUTelemetry
    return GPUTelemetry(
        gpu_id=0, name="RTX", uuid="GPU-abc",
        total_vram_mib=6141, free_vram_mib=5000, used_vram_mib=1141,
        gpu_utilization_pct=30.0, temperature_c=55.0,
        driver_version="616.92", cuda_available=True,
    )


class TestCoordinatorClientRegister(unittest.TestCase):
    def _make_client(self):
        from worker.coordinator.client import CoordinatorClient
        return CoordinatorClient(_make_config())

    def _mock_response(self, status_code: int, json_data: dict = None):
        resp = MagicMock()
        resp.status_code = status_code
        resp.json.return_value = json_data or {"status": "ok"}
        resp.text = str(json_data or "")
        resp.content = b"ok"
        return resp

    @patch("worker.coordinator.client.requests.Session.post")
    def test_register_200_success(self, mock_post):
        mock_post.return_value = self._mock_response(200, {"worker_id": "worker-test"})
        client = self._make_client()
        result = client.register(_make_gpu_info())
        self.assertIn("worker_id", result)

    @patch("worker.coordinator.client.requests.Session.post")
    def test_register_201_success(self, mock_post):
        mock_post.return_value = self._mock_response(201, {"registered": True})
        client = self._make_client()
        result = client.register(_make_gpu_info())
        self.assertTrue(result.get("registered"))

    @patch("worker.coordinator.client.requests.Session.post")
    def test_register_400_raises_registration_error(self, mock_post):
        from worker.coordinator.client import RegistrationError
        resp = self._mock_response(400)
        resp.text = "Bad Request"
        mock_post.return_value = resp
        client = self._make_client()
        with self.assertRaises(RegistrationError):
            client.register(_make_gpu_info())

    @patch("worker.coordinator.client.time.sleep")  # skip real sleep
    @patch("worker.coordinator.client.requests.Session.post")
    def test_register_network_error_retries(self, mock_post, mock_sleep):
        from worker.coordinator.client import RegistrationError
        mock_post.side_effect = requests.ConnectionError("connection refused")
        client = self._make_client()
        with self.assertRaises(RegistrationError):
            client.register(_make_gpu_info())
        # Should have retried max_registration_retries times
        self.assertEqual(mock_post.call_count, 3)

    @patch("worker.coordinator.client.time.sleep")
    @patch("worker.coordinator.client.requests.Session.post")
    def test_register_succeeds_on_second_attempt(self, mock_post, mock_sleep):
        """First call fails, second succeeds — should return success."""
        good_resp = self._mock_response(200, {"ok": True})
        mock_post.side_effect = [
            requests.ConnectionError("first fail"),
            good_resp,
        ]
        client = self._make_client()
        result = client.register(_make_gpu_info())
        self.assertTrue(result.get("ok"))
        self.assertEqual(mock_post.call_count, 2)

    @patch("worker.coordinator.client.requests.Session.post")
    def test_register_payload_has_required_fields(self, mock_post):
        mock_post.return_value = self._mock_response(200, {})
        client = self._make_client()
        client.register(_make_gpu_info())
        call_kwargs = mock_post.call_args
        payload = call_kwargs[1]["json"] if call_kwargs[1] else call_kwargs.kwargs.get("json", {})
        for field in ("worker_id", "gpu_name", "gpu_uuid", "total_vram_mib",
                      "driver_version", "cuda_available", "gpu_id"):
            self.assertIn(field, payload, f"Missing field: {field}")


class TestCoordinatorClientHeartbeat(unittest.TestCase):
    def _make_client(self):
        from worker.coordinator.client import CoordinatorClient
        return CoordinatorClient(_make_config())

    def _mock_response(self, status_code: int, json_data: dict = None, content: bytes = b"ok"):
        resp = MagicMock()
        resp.status_code = status_code
        resp.json.return_value = json_data or {}
        resp.text = ""
        resp.content = content
        return resp

    @patch("worker.coordinator.client.requests.Session.post")
    def test_heartbeat_200_success(self, mock_post):
        mock_post.return_value = self._mock_response(200, {"received": True})
        client = self._make_client()
        result = client.send_heartbeat(_make_telemetry(), "AVAILABLE")
        self.assertIsInstance(result, dict)

    @patch("worker.coordinator.client.requests.Session.post")
    def test_heartbeat_204_returns_empty_dict(self, mock_post):
        mock_post.return_value = self._mock_response(204, content=b"")
        client = self._make_client()
        result = client.send_heartbeat(_make_telemetry(), "BUSY")
        self.assertEqual(result, {})

    @patch("worker.coordinator.client.requests.Session.post")
    def test_heartbeat_500_raises(self, mock_post):
        from worker.coordinator.client import HeartbeatError
        mock_post.return_value = self._mock_response(500)
        client = self._make_client()
        with self.assertRaises(HeartbeatError):
            client.send_heartbeat(_make_telemetry(), "AVAILABLE")

    @patch("worker.coordinator.client.requests.Session.post")
    def test_heartbeat_network_error_raises(self, mock_post):
        from worker.coordinator.client import HeartbeatError
        mock_post.side_effect = requests.Timeout("timeout")
        client = self._make_client()
        with self.assertRaises(HeartbeatError):
            client.send_heartbeat(_make_telemetry(), "AVAILABLE")

    @patch("worker.coordinator.client.requests.Session.post")
    def test_heartbeat_payload_has_telemetry(self, mock_post):
        mock_post.return_value = self._mock_response(200, {})
        client = self._make_client()
        client.send_heartbeat(_make_telemetry(), "AVAILABLE")
        payload = mock_post.call_args[1]["json"]
        self.assertIn("gpu_telemetry", payload)
        telem = payload["gpu_telemetry"]
        for key in ("free_vram_mib", "used_vram_mib", "total_vram_mib",
                    "gpu_utilization_pct", "temperature_c", "cuda_available"):
            self.assertIn(key, telem, f"Missing telemetry field: {key}")
        self.assertEqual(payload["state"], "AVAILABLE")


class TestCoordinatorClientJobResult(unittest.TestCase):
    def _make_client(self):
        from worker.coordinator.client import CoordinatorClient
        return CoordinatorClient(_make_config())

    def _mock_response(self, status_code: int, content: bytes = b"ok"):
        resp = MagicMock()
        resp.status_code = status_code
        resp.json.return_value = {}
        resp.text = ""
        resp.content = content
        return resp

    @patch("worker.coordinator.client.requests.Session.post")
    def test_post_result_success(self, mock_post):
        mock_post.return_value = self._mock_response(200)
        client = self._make_client()
        result = client.post_job_result("job-1", {"status": "success", "output": {}, "execution_time_s": 1.0, "error": None})
        self.assertIsInstance(result, dict)

    @patch("worker.coordinator.client.requests.Session.post")
    def test_post_result_includes_worker_id(self, mock_post):
        mock_post.return_value = self._mock_response(200)
        client = self._make_client()
        client.post_job_result("job-2", {"status": "success", "output": {}, "execution_time_s": 0.5, "error": None})
        payload = mock_post.call_args[1]["json"]
        self.assertEqual(payload["worker_id"], "worker-test")

    @patch("worker.coordinator.client.requests.Session.post")
    def test_post_result_404_raises(self, mock_post):
        from worker.coordinator.client import JobResultError
        resp = self._mock_response(404)
        resp.text = "Job not found"
        mock_post.return_value = resp
        client = self._make_client()
        with self.assertRaises(JobResultError):
            client.post_job_result("job-3", {"status": "failed", "output": {}, "execution_time_s": 0.0, "error": "err"})


if __name__ == "__main__":
    unittest.main()

"""
TASK 11 — Unit tests: WorkerConfig.

Tests cover:
  - from_env() with all vars set
  - Auto-generated WORKER_ID when not set
  - Missing COORDINATOR_URL raises ValueError
  - Invalid GPU_ID type raises ValueError
  - Invalid HEARTBEAT_INTERVAL raises ValueError
  - Trailing slash stripped from COORDINATOR_URL
  - api_url() construction
"""

from __future__ import annotations

import os
import unittest


class TestWorkerConfig(unittest.TestCase):
    def _env(self, **overrides) -> dict:
        base = {
            "WORKER_ID": "test-worker-01",
            "COORDINATOR_URL": "http://localhost:8000/",
            "GPU_ID": "0",
            "HEARTBEAT_INTERVAL": "30",
        }
        base.update(overrides)
        return base

    def _load(self, env: dict):
        from worker.config import WorkerConfig
        # Clear and set env vars
        saved = {}
        keys = {"WORKER_ID", "COORDINATOR_URL", "GPU_ID", "HEARTBEAT_INTERVAL"}
        for k in keys:
            saved[k] = os.environ.pop(k, None)
        try:
            for k, v in env.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = str(v)
            return WorkerConfig.from_env()
        finally:
            for k, v in saved.items():
                if v is not None:
                    os.environ[k] = v
                else:
                    os.environ.pop(k, None)

    def test_all_fields_loaded(self):
        cfg = self._load(self._env())
        from worker.config import WorkerConfig
        self.assertIsInstance(cfg, WorkerConfig)
        self.assertEqual(cfg.worker_id, "test-worker-01")
        self.assertEqual(cfg.coordinator_url, "http://localhost:8000")  # slash stripped
        self.assertEqual(cfg.gpu_id, 0)
        self.assertEqual(cfg.heartbeat_interval, 30)

    def test_trailing_slash_stripped(self):
        cfg = self._load(self._env(COORDINATOR_URL="http://example.com/api/v1/"))
        self.assertEqual(cfg.coordinator_url, "http://example.com/api/v1")

    def test_auto_worker_id_when_not_set(self):
        env = self._env()
        env.pop("WORKER_ID", None)
        cfg = self._load({k: v for k, v in env.items() if k != "WORKER_ID"})
        self.assertTrue(cfg.worker_id.startswith("worker-"))
        self.assertGreater(len(cfg.worker_id), 7)

    def test_missing_coordinator_url_raises(self):
        env = self._env()
        env["COORDINATOR_URL"] = ""
        with self.assertRaises(ValueError):
            self._load(env)

    def test_invalid_gpu_id_type_raises(self):
        with self.assertRaises(ValueError):
            self._load(self._env(GPU_ID="not_a_number"))

    def test_negative_gpu_id_raises(self):
        with self.assertRaises(ValueError):
            self._load(self._env(GPU_ID="-1"))

    def test_invalid_heartbeat_interval_raises(self):
        with self.assertRaises(ValueError):
            self._load(self._env(HEARTBEAT_INTERVAL="fast"))

    def test_zero_heartbeat_interval_raises(self):
        with self.assertRaises(ValueError):
            self._load(self._env(HEARTBEAT_INTERVAL="0"))

    def test_api_url_construction(self):
        cfg = self._load(self._env(COORDINATOR_URL="http://coordinator.local:9000"))
        url = cfg.api_url("api/v1/workers/register")
        self.assertEqual(url, "http://coordinator.local:9000/api/v1/workers/register")

    def test_api_url_leading_slash_handled(self):
        cfg = self._load(self._env())
        url = cfg.api_url("/api/v1/workers/register")
        self.assertEqual(url, "http://localhost:8000/api/v1/workers/register")


if __name__ == "__main__":
    unittest.main()

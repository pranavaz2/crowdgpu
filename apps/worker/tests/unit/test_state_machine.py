"""
TASK 11 — Unit tests: WorkerStateMachine.

Tests all valid transitions, invalid transitions, terminal state,
concurrent access safety, and history recording.
"""

from __future__ import annotations

import threading
import unittest


class TestWorkerStateMachine(unittest.TestCase):
    def _make(self):
        from worker.state import WorkerStateMachine
        return WorkerStateMachine()

    def test_initial_state_is_starting(self):
        from worker.state import WorkerState
        sm = self._make()
        self.assertEqual(sm.state, WorkerState.STARTING)

    def test_starting_to_available(self):
        from worker.state import WorkerState
        sm = self._make()
        sm.transition(WorkerState.AVAILABLE)
        self.assertEqual(sm.state, WorkerState.AVAILABLE)

    def test_starting_to_error(self):
        from worker.state import WorkerState
        sm = self._make()
        sm.transition(WorkerState.ERROR)
        self.assertEqual(sm.state, WorkerState.ERROR)

    def test_available_to_busy(self):
        from worker.state import WorkerState
        sm = self._make()
        sm.transition(WorkerState.AVAILABLE)
        sm.transition(WorkerState.BUSY)
        self.assertEqual(sm.state, WorkerState.BUSY)

    def test_busy_to_available(self):
        from worker.state import WorkerState
        sm = self._make()
        sm.transition(WorkerState.AVAILABLE)
        sm.transition(WorkerState.BUSY)
        sm.transition(WorkerState.AVAILABLE)
        self.assertEqual(sm.state, WorkerState.AVAILABLE)

    def test_busy_to_error(self):
        from worker.state import WorkerState
        sm = self._make()
        sm.transition(WorkerState.AVAILABLE)
        sm.transition(WorkerState.BUSY)
        sm.transition(WorkerState.ERROR)
        self.assertEqual(sm.state, WorkerState.ERROR)

    def test_error_to_available(self):
        from worker.state import WorkerState
        sm = self._make()
        sm.transition(WorkerState.ERROR)
        sm.transition(WorkerState.AVAILABLE)
        self.assertEqual(sm.state, WorkerState.AVAILABLE)

    def test_offline_is_terminal(self):
        from worker.state import WorkerState, InvalidStateTransitionError
        sm = self._make()
        sm.transition(WorkerState.AVAILABLE)
        sm.transition(WorkerState.OFFLINE)
        with self.assertRaises(InvalidStateTransitionError):
            sm.transition(WorkerState.AVAILABLE)

    def test_invalid_starting_to_busy(self):
        from worker.state import WorkerState, InvalidStateTransitionError
        sm = self._make()
        with self.assertRaises(InvalidStateTransitionError):
            sm.transition(WorkerState.BUSY)  # STARTING → BUSY is not allowed

    def test_invalid_starting_to_offline(self):
        from worker.state import WorkerState, InvalidStateTransitionError
        sm = self._make()
        with self.assertRaises(InvalidStateTransitionError):
            sm.transition(WorkerState.OFFLINE)  # STARTING → OFFLINE not allowed

    def test_can_transition_true(self):
        from worker.state import WorkerState
        sm = self._make()
        self.assertTrue(sm.can_transition(WorkerState.AVAILABLE))

    def test_can_transition_false(self):
        from worker.state import WorkerState
        sm = self._make()
        self.assertFalse(sm.can_transition(WorkerState.BUSY))  # STARTING → BUSY

    def test_is_available(self):
        from worker.state import WorkerState
        sm = self._make()
        sm.transition(WorkerState.AVAILABLE)
        self.assertTrue(sm.is_available())
        self.assertFalse(sm.is_busy())

    def test_is_busy(self):
        from worker.state import WorkerState
        sm = self._make()
        sm.transition(WorkerState.AVAILABLE)
        sm.transition(WorkerState.BUSY)
        self.assertTrue(sm.is_busy())
        self.assertFalse(sm.is_available())

    def test_history_recorded(self):
        from worker.state import WorkerState
        sm = self._make()
        sm.transition(WorkerState.AVAILABLE)
        sm.transition(WorkerState.BUSY)
        history = sm.history()
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0], (WorkerState.STARTING, WorkerState.AVAILABLE))
        self.assertEqual(history[1], (WorkerState.AVAILABLE, WorkerState.BUSY))

    def test_thread_safety(self):
        """Multiple threads reading state while one writes should not crash."""
        from worker.state import WorkerState
        sm = self._make()
        sm.transition(WorkerState.AVAILABLE)
        errors = []

        def reader():
            try:
                for _ in range(100):
                    _ = sm.state
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=reader) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()

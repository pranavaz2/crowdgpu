"""
TASK 5 — Worker state machine.

Valid states and allowed transitions:

    STARTING → AVAILABLE | ERROR
    AVAILABLE → BUSY | ERROR | OFFLINE
    BUSY → AVAILABLE | ERROR | OFFLINE
    ERROR → AVAILABLE | OFFLINE
    OFFLINE → (terminal, no further transitions)
"""

from __future__ import annotations

import logging
import threading
from enum import Enum
from typing import Set, Dict

logger = logging.getLogger(__name__)


class WorkerState(str, Enum):
    STARTING = "STARTING"
    AVAILABLE = "AVAILABLE"
    BUSY = "BUSY"
    ERROR = "ERROR"
    OFFLINE = "OFFLINE"


# Valid state transitions map
_TRANSITIONS: Dict[WorkerState, Set[WorkerState]] = {
    WorkerState.STARTING: {WorkerState.AVAILABLE, WorkerState.ERROR},
    WorkerState.AVAILABLE: {WorkerState.BUSY, WorkerState.ERROR, WorkerState.OFFLINE},
    WorkerState.BUSY: {WorkerState.AVAILABLE, WorkerState.ERROR, WorkerState.OFFLINE},
    WorkerState.ERROR: {WorkerState.AVAILABLE, WorkerState.OFFLINE},
    WorkerState.OFFLINE: set(),  # terminal
}


class InvalidStateTransitionError(RuntimeError):
    """Raised when an illegal state transition is attempted."""


class WorkerStateMachine:
    """
    Thread-safe worker state machine.

    Usage::

        sm = WorkerStateMachine()
        sm.transition(WorkerState.AVAILABLE)  # STARTING → AVAILABLE
        sm.transition(WorkerState.BUSY)        # AVAILABLE → BUSY
        sm.transition(WorkerState.AVAILABLE)  # BUSY → AVAILABLE
    """

    def __init__(self, initial: WorkerState = WorkerState.STARTING) -> None:
        self._state = initial
        self._lock = threading.Lock()
        self._history: list[tuple[WorkerState, WorkerState]] = []
        logger.info("WorkerStateMachine initialised in state %s", initial.value)

    @property
    def state(self) -> WorkerState:
        with self._lock:
            return self._state

    def transition(self, target: WorkerState) -> None:
        """
        Transition to *target* state.

        Raises InvalidStateTransitionError if the transition is not allowed.
        """
        with self._lock:
            current = self._state
            allowed = _TRANSITIONS.get(current, set())
            if target not in allowed:
                raise InvalidStateTransitionError(
                    f"Cannot transition {current.value} → {target.value}. "
                    f"Allowed from {current.value}: "
                    f"{[s.value for s in allowed] or 'none (terminal)'}."
                )
            self._state = target
            self._history.append((current, target))
            logger.info("State: %s → %s", current.value, target.value)

    def can_transition(self, target: WorkerState) -> bool:
        """Return True if transitioning to *target* is currently valid."""
        with self._lock:
            return target in _TRANSITIONS.get(self._state, set())

    def is_available(self) -> bool:
        return self.state == WorkerState.AVAILABLE

    def is_busy(self) -> bool:
        return self.state == WorkerState.BUSY

    def is_offline(self) -> bool:
        return self.state == WorkerState.OFFLINE

    def history(self) -> list[tuple[WorkerState, WorkerState]]:
        with self._lock:
            return list(self._history)

    def __repr__(self) -> str:
        return f"WorkerStateMachine(state={self._state.value})"

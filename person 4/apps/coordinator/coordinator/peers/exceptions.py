"""
Exceptions for the Peer domain.
"""

import uuid


class PeerDomainError(Exception):
    """Base exception for peer domain errors."""

    pass


class PeerNotFoundError(PeerDomainError):
    """Raised when a requested peer ID does not exist."""

    def __init__(self, peer_id: uuid.UUID) -> None:
        self.peer_id = peer_id
        super().__init__(f"Peer '{peer_id}' not found")


class OwnerNotFoundError(PeerDomainError):
    """Raised when the owner user ID specified during registration does not exist."""

    def __init__(self, owner_id: uuid.UUID) -> None:
        self.owner_id = owner_id
        super().__init__(f"Owner user '{owner_id}' not found")


class InvalidPeerStateError(PeerDomainError):
    """Raised when an invalid state transition or operation is attempted on a peer."""

    def __init__(self, message: str) -> None:
        super().__init__(message)

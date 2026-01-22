"""Node state machine for lifecycle management."""
from typing import ClassVar


class InvalidStateTransition(Exception):
    """Raised when an invalid state transition is attempted."""

    def __init__(self, from_state: str, to_state: str):
        self.from_state = from_state
        self.to_state = to_state
        super().__init__(
            f"Invalid state transition from '{from_state}' to '{to_state}'"
        )


class NodeStateMachine:
    """State machine for node lifecycle management.

    States:
        discovered: Node appeared via PXE, waiting for admin action
        pending: Workflow assigned, ready for next PXE boot
        installing: OS installation in progress
        install_failed: Installation failed after max retries
        installed: Installation complete, ready for local boot
        active: Running from local disk
        reprovision: Marked for reinstallation
        deprovisioning: Secure data erasure in progress
        migrating: Hardware replacement workflow
        retired: Removed from inventory
    """

    STATES: ClassVar[list[str]] = [
        "discovered",
        "pending",
        "installing",
        "install_failed",
        "installed",
        "active",
        "reprovision",
        "deprovisioning",
        "migrating",
        "retired",
    ]

    TRANSITIONS: ClassVar[dict[str, list[str]]] = {
        "discovered": ["pending"],
        "pending": ["installing"],
        "installing": ["installed", "install_failed"],
        "install_failed": ["pending"],
        "installed": ["active", "reprovision", "retired"],
        "active": ["reprovision", "deprovisioning", "migrating"],
        "reprovision": ["pending"],
        "deprovisioning": ["retired"],
        "migrating": ["active"],
        "retired": [],
    }

    @classmethod
    def can_transition(cls, from_state: str, to_state: str) -> bool:
        """Check if a state transition is valid.

        Args:
            from_state: Current state
            to_state: Target state

        Returns:
            True if transition is valid, False otherwise
        """
        # Admin can retire from any state
        if to_state == "retired":
            return from_state != "retired"

        return to_state in cls.TRANSITIONS.get(from_state, [])

    @classmethod
    def transition(cls, from_state: str, to_state: str) -> str:
        """Perform a state transition.

        Args:
            from_state: Current state
            to_state: Target state

        Returns:
            The new state

        Raises:
            InvalidStateTransition: If the transition is not valid
        """
        if not cls.can_transition(from_state, to_state):
            raise InvalidStateTransition(from_state, to_state)
        return to_state

    @classmethod
    def get_valid_transitions(cls, from_state: str) -> list[str]:
        """Get list of valid transitions from a state.

        Args:
            from_state: Current state

        Returns:
            List of valid target states
        """
        valid = list(cls.TRANSITIONS.get(from_state, []))
        # Can always retire (except from retired)
        if from_state != "retired" and "retired" not in valid:
            valid.append("retired")
        return valid

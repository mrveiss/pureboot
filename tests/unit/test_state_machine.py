"""Tests for node state machine."""
import pytest

from src.core.state_machine import NodeStateMachine, InvalidStateTransition


class TestNodeStateMachine:
    """Test state machine transitions."""

    def test_discovered_to_pending_allowed(self):
        """Can transition from discovered to pending."""
        assert NodeStateMachine.can_transition("discovered", "pending") is True

    def test_discovered_to_active_not_allowed(self):
        """Cannot skip states."""
        assert NodeStateMachine.can_transition("discovered", "active") is False

    def test_pending_to_installing_allowed(self):
        """Can transition from pending to installing."""
        assert NodeStateMachine.can_transition("pending", "installing") is True

    def test_installing_to_installed_allowed(self):
        """Can transition from installing to installed."""
        assert NodeStateMachine.can_transition("installing", "installed") is True

    def test_installed_to_active_allowed(self):
        """Can transition from installed to active."""
        assert NodeStateMachine.can_transition("installed", "active") is True

    def test_active_to_reprovision_allowed(self):
        """Can transition from active to reprovision."""
        assert NodeStateMachine.can_transition("active", "reprovision") is True

    def test_reprovision_to_pending_allowed(self):
        """Can transition from reprovision back to pending."""
        assert NodeStateMachine.can_transition("reprovision", "pending") is True

    def test_any_state_to_retired_allowed(self):
        """Can retire from any state."""
        for state in NodeStateMachine.STATES:
            if state != "retired":
                assert NodeStateMachine.can_transition(state, "retired") is True

    def test_retired_cannot_transition(self):
        """Retired state is terminal except to retired."""
        assert NodeStateMachine.can_transition("retired", "discovered") is False
        assert NodeStateMachine.can_transition("retired", "pending") is False

    def test_transition_raises_on_invalid(self):
        """transition() raises InvalidStateTransition for invalid transitions."""
        with pytest.raises(InvalidStateTransition) as exc_info:
            NodeStateMachine.transition("discovered", "active")
        assert "discovered" in str(exc_info.value)
        assert "active" in str(exc_info.value)

    def test_transition_returns_new_state_on_valid(self):
        """transition() returns new state on valid transition."""
        result = NodeStateMachine.transition("discovered", "pending")
        assert result == "pending"

    def test_get_valid_transitions(self):
        """get_valid_transitions returns list of valid next states."""
        valid = NodeStateMachine.get_valid_transitions("active")
        assert "reprovision" in valid
        assert "deprovisioning" in valid
        assert "migrating" in valid
        assert "serving_source" in valid
        assert "cloning_target" in valid
        assert "retired" in valid

    def test_installing_to_install_failed_allowed(self):
        """Can transition from installing to install_failed."""
        assert NodeStateMachine.can_transition("installing", "install_failed") is True

    def test_install_failed_to_pending_allowed(self):
        """Can transition from install_failed to pending."""
        assert NodeStateMachine.can_transition("install_failed", "pending") is True

    def test_all_states_defined(self):
        """All expected states are defined."""
        expected = {
            "discovered", "pending", "installing", "installed",
            "active", "reprovision", "deprovisioning", "migrating",
            "install_failed", "serving_source", "cloning_target", "retired"
        }
        assert set(NodeStateMachine.STATES) == expected

    # Cloning state transitions

    def test_active_to_serving_source_allowed(self):
        """Can transition from active to serving_source for disk cloning."""
        assert NodeStateMachine.can_transition("active", "serving_source") is True

    def test_active_to_cloning_target_allowed(self):
        """Can transition from active to cloning_target for disk cloning."""
        assert NodeStateMachine.can_transition("active", "cloning_target") is True

    def test_discovered_to_cloning_target_allowed(self):
        """Can transition from discovered to cloning_target for new node cloning."""
        assert NodeStateMachine.can_transition("discovered", "cloning_target") is True

    def test_serving_source_to_active_allowed(self):
        """Can transition from serving_source back to active after clone completes."""
        assert NodeStateMachine.can_transition("serving_source", "active") is True

    def test_cloning_target_to_installed_allowed(self):
        """Can transition from cloning_target to installed after clone completes."""
        assert NodeStateMachine.can_transition("cloning_target", "installed") is True

    def test_serving_source_cannot_skip_to_retired(self):
        """serving_source can retire (admin override) but not skip to other states."""
        assert NodeStateMachine.can_transition("serving_source", "pending") is False
        assert NodeStateMachine.can_transition("serving_source", "retired") is True

    def test_cloning_target_cannot_skip_states(self):
        """cloning_target must go to installed, not skip to active."""
        assert NodeStateMachine.can_transition("cloning_target", "active") is False
        assert NodeStateMachine.can_transition("cloning_target", "retired") is True

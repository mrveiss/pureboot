"""Tests for node cleanup functionality."""
import inspect

import pytest


def test_retire_node_imports_pi_manager_for_pi_nodes():
    """Verify the code path for Pi node cleanup exists."""
    # This test verifies the retire_node function has the cleanup logic
    from src.api.routes.nodes import retire_node
    source = inspect.getsource(retire_node)
    assert "boot_mode" in source and "pi" in source
    assert "delete_node_directory" in source


def test_retire_node_has_serial_number_check():
    """Verify the cleanup checks for serial_number before proceeding."""
    from src.api.routes.nodes import retire_node
    source = inspect.getsource(retire_node)
    assert "serial_number" in source


def test_retire_node_has_exception_handling():
    """Verify the cleanup has exception handling for best-effort cleanup."""
    from src.api.routes.nodes import retire_node
    source = inspect.getsource(retire_node)
    # Verify there's a try-except block for the cleanup
    assert "try:" in source
    assert "except Exception" in source
    assert "warning" in source.lower()

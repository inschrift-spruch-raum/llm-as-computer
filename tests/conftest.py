"""Pytest configuration and shared fixtures for the test suite."""

import importlib.util

import pytest


def pytest_collection_modifyitems(
    config: pytest.Config,
    items: list[pytest.Item],
) -> None:
    """Skip torch-dependent tests when PyTorch is not installed."""
    del config
    if importlib.util.find_spec("torch") is None:
        for item in items:
            if "torch" in item.nodeid.lower() or "pt_exec" in getattr(
                item, "fixturenames", []
            ):
                item.add_marker(pytest.mark.skip(reason="PyTorch not installed"))

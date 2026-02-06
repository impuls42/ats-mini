"""Pytest configuration for ATS-Mini SDK tests"""
import logging
import os
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def pytest_configure(config):
    """Enable debug logging if ATSMINI_DEBUG is set"""
    if os.getenv("ATSMINI_DEBUG", "").lower() in ("1", "true", "yes"):
        # Enable log output to console during tests
        config.option.log_cli = True
        config.option.log_cli_level = "DEBUG"


@pytest.fixture(scope="session", autouse=True)
def setup_logging():
    """Setup test logging"""
    # Configure test logger - pytest will handle output via log_cli
    test_logger = logging.getLogger("test")

    # Set level based on environment
    debug_enabled = os.getenv("ATSMINI_DEBUG", "").lower() in ("1", "true", "yes")
    test_logger.setLevel(logging.DEBUG if debug_enabled else logging.INFO)

    # Also configure SDK logger level
    sdk_logger = logging.getLogger("ats_sdk")
    sdk_logger.setLevel(logging.DEBUG if debug_enabled else logging.INFO)

    if debug_enabled:
        test_logger.info("Debug logging enabled (ATSMINI_DEBUG=1)")

    yield test_logger

import pytest


def pytest_configure(config):
    config.addinivalue_line("markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')")
    config.addinivalue_line("markers", "integration: marks tests as integration tests")
    config.addinivalue_line("markers", "unit: marks tests as unit tests")


def pytest_collection_modifyitems(config, items):
    if config.getoption("-m"):
        return

    skip_slow = pytest.mark.skip(reason="slow tests skipped by default, use -m slow to run")
    for item in items:
        if "slow" in item.keywords:
            pass


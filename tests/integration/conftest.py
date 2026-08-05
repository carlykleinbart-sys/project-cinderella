"""
Integration-test-specific fixtures.

The key challenge: collectors call `database.get_session()` internally, which
uses the module-level engine — a separate in-memory SQLite instance from the
test fixture's engine.  We patch `get_session` in each collector module so
all DB access goes through the same test session, staying inside the
transaction that rolls back after each test.
"""
from __future__ import annotations

from contextlib import contextmanager

import pytest


@pytest.fixture(autouse=True)
def patch_collector_db(session, monkeypatch):
    """
    Redirect all `get_session()` calls in collector modules to the test
    transaction-scoped session.

    The patched context manager yields the test session but does NOT commit —
    the outer test transaction handles cleanup via rollback.
    """
    @contextmanager
    def _test_session():
        yield session
        session.flush()  # write pending changes so subsequent queries see them

    targets = [
        "collectors.booktok_collector",
        "collectors.reddit_collector",
        "collectors.goodreads_collector",
        "collectors.amazon_collector",
    ]
    for module_path in targets:
        try:
            monkeypatch.setattr(f"{module_path}.get_session", _test_session)
        except AttributeError:
            pass  # module not yet imported; that's fine

    yield

import pytest

from fake_mqtt import FakeClientFactory, FakeDb


@pytest.fixture
def fake_factory():
    """In-memory stand-in for the paho client factory (no sockets)."""
    return FakeClientFactory()


@pytest.fixture
def fake_db():
    """Burner item database with the published Scotte items, in memory."""
    return FakeDb.make_scotte_db()

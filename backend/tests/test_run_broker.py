import pytest

from app.services.run_broker import RunBroker


@pytest.mark.asyncio
async def test_terminal_events_are_pruned_after_retention_period():
    broker = RunBroker(retention_seconds=0)
    broker.cancel("run-1")

    await broker.publish("run-1", "run.cancelled", {"status": "cancelled"})

    assert broker.has_events("run-1") is False
    assert "run-1" not in broker._events
    assert "run-1" not in broker._conditions
    assert "run-1" not in broker._cancelled

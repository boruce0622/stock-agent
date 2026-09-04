import asyncio
from collections import defaultdict
from collections.abc import AsyncIterator
from time import monotonic
from typing import Any

TERMINAL_EVENTS = {"message.completed", "run.error", "run.cancelled"}


class RunBroker:
    def __init__(self, retention_seconds: float = 300) -> None:
        self._events: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self._conditions: dict[str, asyncio.Condition] = defaultdict(asyncio.Condition)
        self._cancelled: set[str] = set()
        self._terminal_at: dict[str, float] = {}
        self.retention_seconds = retention_seconds

    def _prune_expired(self) -> None:
        cutoff = monotonic() - self.retention_seconds
        expired = [run_id for run_id, ended_at in self._terminal_at.items() if ended_at <= cutoff]
        for run_id in expired:
            self._events.pop(run_id, None)
            self._conditions.pop(run_id, None)
            self._cancelled.discard(run_id)
            self._terminal_at.pop(run_id, None)

    async def publish(self, run_id: str, event_type: str, data: dict[str, Any]) -> None:
        self._prune_expired()
        condition = self._conditions[run_id]
        async with condition:
            sequence = len(self._events[run_id]) + 1
            event = {
                "id": sequence,
                "event": event_type,
                "data": {"run_id": run_id, "sequence": sequence, **data},
            }
            self._events[run_id].append(event)
            if event_type in TERMINAL_EVENTS:
                self._terminal_at[run_id] = monotonic()
            condition.notify_all()

    def cancel(self, run_id: str) -> None:
        self._prune_expired()
        self._cancelled.add(run_id)

    def is_cancelled(self, run_id: str) -> bool:
        return run_id in self._cancelled

    def has_events(self, run_id: str) -> bool:
        self._prune_expired()
        return bool(self._events.get(run_id))

    async def subscribe(self, run_id: str, after: int = 0) -> AsyncIterator[dict[str, Any]]:
        self._prune_expired()
        index = after
        condition = self._conditions[run_id]
        while True:
            async with condition:
                if index >= len(self._events[run_id]):
                    try:
                        await asyncio.wait_for(condition.wait(), timeout=15)
                    except TimeoutError:
                        yield {"event": "heartbeat", "data": {"run_id": run_id}}
                        continue
                pending = self._events[run_id][index:]
            for event in pending:
                index += 1
                yield event
                if event["event"] in TERMINAL_EVENTS:
                    return


run_broker = RunBroker()

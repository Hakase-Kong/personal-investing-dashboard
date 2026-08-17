import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class CacheEntry:
    value: Any = None
    updated_at: float = 0.0
    error: str = ""
    refreshing: bool = False


class BackgroundDataEngine:
    """Small stale-while-revalidate cache for shared market data.

    Pages never need to wait for slow upstream APIs. The engine refreshes common
    datasets in the background and keeps the last successful value when a source
    temporarily fails.
    """

    def __init__(self):
        self.entries: dict[str, CacheEntry] = {}
        self.jobs: dict[str, tuple[Callable, float, tuple, dict]] = {}
        self._tasks: list[asyncio.Task] = []
        self._started = False

    def register(self, key: str, loader: Callable, interval: float, *args, **kwargs):
        self.jobs[key] = (loader, interval, args, kwargs)
        self.entries.setdefault(key, CacheEntry())

    def get(self, key: str, default=None):
        entry = self.entries.get(key)
        return default if not entry or entry.value is None else entry.value

    def meta(self, key: str):
        entry = self.entries.get(key) or CacheEntry()
        return {
            "updated_at": entry.updated_at,
            "age": time.time() - entry.updated_at if entry.updated_at else None,
            "error": entry.error,
            "refreshing": entry.refreshing,
            "ready": entry.value is not None,
        }

    async def refresh(self, key: str):
        job = self.jobs.get(key)
        if not job:
            return None
        loader, _, args, kwargs = job
        entry = self.entries.setdefault(key, CacheEntry())
        if entry.refreshing:
            return entry.value
        entry.refreshing = True
        try:
            value = await asyncio.to_thread(loader, *args, **kwargs)
            # Last-known-good: only replace cache with usable data.
            if value is not None:
                entry.value = value
                entry.updated_at = time.time()
                entry.error = ""
            return entry.value
        except Exception as exc:
            entry.error = str(exc)[:240]
            return entry.value
        finally:
            entry.refreshing = False

    async def _loop(self, key: str):
        _, interval, _, _ = self.jobs[key]
        # Warm immediately, but independently from page rendering.
        await self.refresh(key)
        while True:
            await asyncio.sleep(interval)
            await self.refresh(key)

    async def start(self):
        if self._started:
            return
        self._started = True
        for key in self.jobs:
            self._tasks.append(asyncio.create_task(self._loop(key)))

    async def stop(self):
        for task in self._tasks:
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        self._started = False


engine = BackgroundDataEngine()

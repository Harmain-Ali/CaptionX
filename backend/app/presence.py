"""Knows whether a captionX page is still open, so the packaged app can quit when its window is closed.

Every open page pings every few seconds with its own id and says "bye" when it is closed or reloaded. The launcher
asks `should_quit()`. It is false while a job is running, and false until a page has connected at least once.
"""
from __future__ import annotations

import threading
import time
from typing import Callable, Optional

GRACE_SECONDS = 6.0     # no pages for this long (e.g. not just a reload) -> quit
STALE_SECONDS = 150.0   # a page that stopped pinging without saying bye (crash, sleeping computer) is dropped


class Presence:
    def __init__(self, clock: Callable[[], float] = time.monotonic):
        self._clock = clock
        self._lock = threading.Lock()
        self._clients: dict[str, float] = {}
        self._empty_since: Optional[float] = None
        self._ever = False

    def ping(self, client_id: str) -> None:
        with self._lock:
            self._clients[client_id] = self._clock()
            self._empty_since = None
            self._ever = True

    def bye(self, client_id: str) -> None:
        with self._lock:
            self._clients.pop(client_id, None)
            if not self._clients and self._empty_since is None:
                self._empty_since = self._clock()

    def should_quit(self, busy: bool = False) -> bool:
        now = self._clock()
        with self._lock:
            for cid in [c for c, t in self._clients.items() if now - t > STALE_SECONDS]:
                del self._clients[cid]
            if self._ever and not self._clients and self._empty_since is None:
                self._empty_since = now
            if busy or not self._ever or self._clients:
                if busy and not self._clients:
                    self._empty_since = now  # restart the countdown once the job ends
                return False
            return self._empty_since is not None and now - self._empty_since >= GRACE_SECONDS

    def count(self) -> int:
        with self._lock:
            return len(self._clients)


presence = Presence()

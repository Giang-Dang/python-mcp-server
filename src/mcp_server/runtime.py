"""Explicit event-loop selection for psycopg on Windows; no global policy mutation."""

import asyncio
import selectors
import sys


def run_async(coroutine):
    factory = (
        (lambda: asyncio.SelectorEventLoop(selectors.SelectSelector()))
        if sys.platform == "win32"
        else asyncio.new_event_loop
    )
    return asyncio.run(coroutine, loop_factory=factory)

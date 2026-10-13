"""Run blocking calls off the event loop, a few at a time.

The blob-storage clients (Azure SDK, local disk) are synchronous. Calling
one straight from an `async def` route freezes the whole event loop for
the length of the call, so a big bulk upload would stall every other
request. This runs them in worker threads instead, with a cap on how many
run at once so we don't open hundreds of connections to storage.
"""
import asyncio
from collections.abc import Callable, Sequence
from typing import Any


async def run_in_threads(
    func: Callable[..., Any],
    calls: Sequence[tuple],
    concurrency: int,
) -> list[Any]:
    """Calls func(*args) for every args tuple in `calls`, at most
    `concurrency` at a time, each in a worker thread.

    Returns one entry per call, in the same order as `calls`. A call that
    raised yields the exception object in its slot instead of a value, so
    one failure never cancels or hides the others; the caller decides what
    to do with each. (KeyboardInterrupt/SystemExit are not swallowed.)
    """
    gate = asyncio.Semaphore(max(1, concurrency))

    async def one(args: tuple) -> Any:
        async with gate:
            try:
                return await asyncio.to_thread(func, *args)
            except Exception as exc:  # noqa: BLE001 - reported per call
                return exc

    return list(await asyncio.gather(*(one(args) for args in calls)))

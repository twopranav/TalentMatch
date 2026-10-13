"""
Tests for app/core/threaded.run_in_threads: blocking calls run off the
event loop, concurrently but capped, with per-call failures isolated.
Pure: no database, Redis or network.
"""
import asyncio
import threading
import time

import pytest

from app.core.threaded import run_in_threads


@pytest.fixture(scope="session", autouse=True)
def _prepare_test_database():
    yield


@pytest.fixture(autouse=True)
def _clean_tables():
    yield


def test_results_come_back_in_call_order():
    def work(n):
        time.sleep(0.05 * (5 - n))  # later calls finish first
        return n * 10

    out = asyncio.run(run_in_threads(work, [(n,) for n in range(5)], concurrency=5))

    assert out == [0, 10, 20, 30, 40]


def test_concurrency_is_capped_and_actually_parallel():
    lock = threading.Lock()
    state = {"now": 0, "peak": 0}

    def work(_):
        with lock:
            state["now"] += 1
            state["peak"] = max(state["peak"], state["now"])
        time.sleep(0.05)
        with lock:
            state["now"] -= 1

    asyncio.run(run_in_threads(work, [(i,) for i in range(12)], concurrency=3))

    assert state["peak"] == 3


def test_runs_off_the_calling_thread():
    main = threading.get_ident()

    out = asyncio.run(run_in_threads(lambda: threading.get_ident(), [()] * 4, concurrency=4))

    assert main not in out


def test_event_loop_stays_responsive_while_calls_block():
    """The whole point: a blocking call must not freeze the loop."""
    ticks = []

    async def main():
        async def ticker():
            for _ in range(10):
                ticks.append(time.perf_counter())
                await asyncio.sleep(0.02)

        t = asyncio.create_task(ticker())
        await run_in_threads(lambda: time.sleep(0.25), [()] * 2, concurrency=2)
        await t

    asyncio.run(main())

    gaps = [b - a for a, b in zip(ticks, ticks[1:])]
    assert max(gaps) < 0.15  # a frozen loop would show a ~0.25s gap


def test_one_failure_does_not_hide_or_cancel_the_others():
    def work(n):
        if n == 2:
            raise RuntimeError("boom")
        return n

    out = asyncio.run(run_in_threads(work, [(n,) for n in range(5)], concurrency=2))

    assert out[0] == 0 and out[1] == 1 and out[3] == 3 and out[4] == 4
    assert isinstance(out[2], RuntimeError)


def test_empty_input_and_nonsense_concurrency():
    assert asyncio.run(run_in_threads(lambda: 1, [], concurrency=4)) == []
    assert asyncio.run(run_in_threads(lambda x: x, [(7,)], concurrency=0)) == [7]

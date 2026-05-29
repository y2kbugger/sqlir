"""Throwaway benchmark for consuming TypedCursorProxy results.

Benchmarks four ways to consume the same 2,500-row result set:
- iterating the cursor directly
- fetchall() then iterating the returned list
- repeated fetchone()
- list(cursor) then iterating the returned list

Each strategy runs 10 times and prints a markdown table with mean, min, and
sample standard deviation in milliseconds.
"""

import gc
from collections.abc import Callable
from statistics import mean, stdev
from time import perf_counter_ns

import apsw

from sqlir.engine import Engine
from sqlir.model import TableRow

ROWS = 2_500
RUNS = 10


class BenchRow(TableRow):
    name: str
    score: float


type Strategy = Callable[[Engine], int]


def build_engine() -> Engine:
    engine = Engine(apsw.Connection(":memory:"))
    engine.ensure_table_created(BenchRow)

    with engine.connection:
        for index in range(ROWS):
            engine.insert(BenchRow(f"row-{index}", float(index % 100)))

    return engine


def sum_cursor_iteration(engine: Engine) -> int:
    total = 0
    cursor = engine.select(BenchRow)
    try:
        for row in cursor:
            assert row.id is not None
            total += row.id
    finally:
        cursor.close()
    return total


def sum_fetchall(engine: Engine) -> int:
    cursor = engine.select(BenchRow)
    try:
        rows = cursor.fetchall()
    finally:
        cursor.close()

    total = 0
    for row in rows:
        assert row.id is not None
        total += row.id
    return total


def sum_fetchone_loop(engine: Engine) -> int:
    total = 0
    cursor = engine.select(BenchRow)
    try:
        while True:
            row = cursor.fetchone()
            if row is None:
                break
            assert row.id is not None
            total += row.id
    finally:
        cursor.close()
    return total


def sum_list_cursor(engine: Engine) -> int:
    cursor = engine.select(BenchRow)
    try:
        rows = list(cursor)
    finally:
        cursor.close()

    total = 0
    for row in rows:
        assert row.id is not None
        total += row.id
    return total


def benchmark_strategy(engine: Engine, strategy: Strategy, *, runs: int) -> list[float]:
    expected_total = ROWS * (ROWS + 1) // 2

    warmup_total = strategy(engine)
    assert warmup_total == expected_total

    samples_ms: list[float] = []
    for _ in range(runs):
        gc.collect()
        gc_was_enabled = gc.isenabled()
        if gc_was_enabled:
            gc.disable()

        started_at = perf_counter_ns()
        try:
            total = strategy(engine)
        finally:
            if gc_was_enabled:
                gc.enable()
        elapsed_ms = (perf_counter_ns() - started_at) / 1_000_000

        assert total == expected_total
        samples_ms.append(elapsed_ms)

    return samples_ms


def print_results_table(results: list[tuple[str, list[float]]]) -> None:
    print(f"Benchmark rows: {ROWS}")
    print(f"Runs per strategy: {RUNS}")
    print()
    print("| Strategy | Mean ms | Min ms | Stddev ms | Runs |")
    print("| --- | ---: | ---: | ---: | ---: |")

    for name, samples in sorted(results, key=lambda item: mean(item[1])):
        deviation = stdev(samples) if len(samples) > 1 else 0.0
        print(f"| {name} | {mean(samples):8.3f} | {min(samples):8.3f} | {deviation:9.3f} | {len(samples):4d} |")


def main() -> None:
    engine = build_engine()
    results = [
        ("for row in cursor", benchmark_strategy(engine, sum_cursor_iteration, runs=RUNS)),
        ("cursor.fetchall()", benchmark_strategy(engine, sum_fetchall, runs=RUNS)),
        ("while cursor.fetchone()", benchmark_strategy(engine, sum_fetchone_loop, runs=RUNS)),
        ("list(cursor)", benchmark_strategy(engine, sum_list_cursor, runs=RUNS)),
    ]
    print_results_table(results)


if __name__ == "__main__":
    main()

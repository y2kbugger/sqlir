# Benchmarks

## apsw.Cursor consumption benchmark

Script: `python benchmarks/cursor_consumption_benchmark.py`

Setup:
- 2,500 rows
- 10 runs per strategy
- result set consumed through `engine.select(...)`

Last recorded result on this machine:

| Strategy | Mean ms | Min ms | Stddev ms | Runs |
| --- | ---: | ---: | ---: | ---: |
| list(cursor) | 6.568 | 5.945 | 0.630 | 10 |
| cursor.fetchall() | 6.688 | 5.988 | 0.628 | 10 |
| while cursor.fetchone() | 7.021 | 6.297 | 0.714 | 10 |
| for row in cursor | 7.138 | 6.209 | 1.081 | 10 |

Takeaway: on this machine, `list(cursor)` and `fetchall()` were effectively tied and a bit faster than repeated `fetchone()` or direct cursor iteration. Treat these as local measurements rather than stable truths; rerun after cursor/materialization changes.

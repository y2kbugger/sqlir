# AGENTS.md

Notes for AI coding agents working in this repo. For project intent and end-user
docs, see [README.md](README.md). For the evolving public API surface and
design discussion, see [API.md](API.md). Open TODOs / non-goals live in
[TODO.md](TODO.md) — **always re-check TODO.md before suggesting changes**;
many "obvious" features are in the *Never, Will not Implement* section.

## Project at a glance

- Pure-Python library (`sqlir/`) that persists immutable dataclass-style
  models (`Row`, `TableRow`) to SQLite via [apsw](https://rogerbinns.github.io/apsw/).
- **Python ≥ 3.14 only.** PEP 649 lazy annotations are the baseline — do **not**
  add `from __future__ import annotations`. Annotation resolution goes through
  `typing.get_type_hints()` at model-compile time.
- No runtime dependencies beyond `apsw` and `msgspec`. Keep it that way (`README.md` Design Principles: "no dependencies").
- Single-node, single-process design. Do not introduce pooling, threading, or
  multi-writer abstractions.

## Module map (`sqlir/`)

| File | Role |
|------|------|
| [model.py](sqlir/model.py) | `RowMeta` metaclass, `Row` / `TableRow`, deferred model compilation, schema-type inference |
| [engine.py](sqlir/engine.py) | `Engine` CRUD API: `insert`, `find`, `select`, `update`, `delete`, `query` |
| [adaptconvert.py](sqlir/adaptconvert.py) | SQLite ↔ Python adaptation; msgspec fallback for non-native types |
| [lazy.py](sqlir/lazy.py) | `Lazy[M]` deferred FK loader |
| [cursorproxy.py](sqlir/cursorproxy.py) | `AdaptingCursor` + per-model row materialization with `Lazy` FK proxies |
| [rel.py](sqlir/rel.py) | Relation AST: `FieldExpr`, `BinaryExpr`, `LogicalExpr` (produced by `Model.field == value` etc.) |
| [sql_rel.py](sqlir/sql_rel.py) | Lowers `rel` AST + t-strings to SQL fragments (EXISTS semi-joins for FK traversal) |
| [sql.py](sqlir/sql.py) | Whole-statement SQL builders (CREATE/SELECT/INSERT/UPDATE/DELETE) |
| [migrate.py](sqlir/migrate.py) | Migration state machine + apply/generate |
| [migrate_cli.py](sqlir/migrate_cli.py) | `sqlir-migrate` CLI |
| [migrate_scenarios/](sqlir/migrate_scenarios) | Per-scenario folders (`SCENARIO.md` + optional `m.py`) consumed by migrate tests |
| [conftest.py](sqlir/conftest.py) | Shared pytest fixtures (`engine`, `sql_log`, `benchmark`, `limit_stack_depth`) |

## Commands

```bash
ruff check --fix
ty check
```

There is a VS Code tool runTests `pytest` (`pytest -vv`). Use it when the user asks to "run the tests".
you should always run tests, then `ty check` then ` ruff check --fix` in that order before moving on to next step.

## Repo conventions (only the non-obvious bits)

- **Test files are co-located** and named `*_test.py` (see `pyproject.toml`
  `python_files`). Tests for `engine.py` live in
  [sqlir/engine_test.py](sqlir/engine_test.py).
- **Ruff line length is 190.** Don't break long signatures for cosmetic reasons.
  Selected rule set is broad (`SLF`, `SIM`, `PTH`, `PD`, `ANN001`, `ANN201`,
  `RUF` ...); run `ruff check --fix` after edits.
- **Type parameter naming:** use `type[R]` on APIs whose return type depends on
  the passed model (`find`, `select`, `query`); use the bare metaclass
  `RowMeta` for internal helpers that only need "a model class". See the
  docstring on `RowMeta` in [model.py](sqlir/model.py).
- **t-strings (PEP 750)** are used to embed model field references in raw
  SQL fragments, e.g. `t"{Athlete.team.name} = 'Red'"`. They are processed by
  `sql_rel.py`. Don't replace them with plain `f"..."`.
- **Benchmarks** are pytest-benchmark tests, disabled by default
  (`--benchmark-disable` in `addopts`). The `benchmark` fixture pins to CPU
  cores `{6, 7}` — this is intentional and host-specific; do not "fix" it.
- **`nbstripout`** runs in pre-commit; do not commit notebook outputs.
- **Docs split:** [API.md](API.md) is the authoritative API/usage reference
  (model types, joins, type-mapping table, web-framework error handling,
  migration states/CLI all live there). [SCRATCH.md](SCRATCH.md) is
  research/links/open-questions **only** — do not put API docs there.
- **Agent plugin** lives in `agent-plugin/` (`plugin.json` + `skills/sqlir/`).
  The skill bundles `API.md` and `example.py` (a jupytext "percent" export of
  [example.ipynb](example.ipynb)). **Both are generated — never hand-edit
  them.** [scripts/sync_plugin.py](scripts/sync_plugin.py) regenerates them and
  is wired into a `sync-plugin` pre-commit hook (triggers on changes to
  `API.md`, `example.ipynb`, or the script). `agent-plugin/` is excluded from ruff +
  ty. Edit the sources (`API.md` / `example.ipynb`), then run
  `python scripts/sync_plugin.py`.

## Gotchas

- **Model compilation is deferred** until first access of `__tablename__` /
  `__fields__` / `__converter__` etc. Errors surface at first use, not
  at `class` definition.
- **Field 0 of a `TableRow` must be `id: int | None`** (`FieldZeroIdMalformed`
  / `FieldZeroIdRequired`).
- **Table-model names may not contain `_`** — underscore is reserved for
  alternate / ad-hoc model naming (`InvalidTableName`).
- **FK fields must be `Model | None`** — unions with other concrete types are
  not supported.
- **`Row` (no `id`) cannot be used with `find`/`update`/`delete`** — those
  require a `TableRow`. `Row` is for ad-hoc / view-shaped query results only.
- **Records are immutable.** Use `dataclasses.replace(obj, field=value)`
  before re-saving; never mutate in place and expect persistence.

## When changing the public API

- Update [API.md](API.md) and [TODO.md](TODO.md) in the same change when
  semantics shift.
- Prefer deletion over deprecation shims — this is a pre-1.0 library and the
  TODO is explicit about minimizing surface area.
- Run the full suite (`pytest -vv`); all 227+ tests should pass

## Dev pratices
- Always check `TODO.md` before suggesting changes. Many "obvious" features are
  already tracked as non-goals or future work.
- Cross stuff of when you start it, not when you finish it. This helps track in-progress work and prevents
  duplication.
- Run tests, then `ty check`, then `ruff check --fix` in that order
    before moving on to the next step.
- Always consider updating this file when making changes to codebase or docs OR when ever I as to code in a specific way.
- Pick up on practices naturally as you work: when the user corrects your
    approach, expresses a preference, or you discover a non-obvious convention,
    record it in this file (AGENTS.md) without being asked. Treat each
    correction as a candidate rule, not a one-off.
- When the user interrupts mid-task to teach you a practice / record a note,
    apply the note and then **resume the original task** in the same turn. Do not
    stop and wait for re-prompting — the meta-instruction is a side quest, not a
    replacement for the in-flight work. This is the developmental flywheel: learn by
    doing, then codify the learning, then immediately apply it to the ongoing work.
- For experimental probes / one-off reproductions (e.g. reproducing a bug,
    poking at an API), create a `scratch.*.py` file at the repo root using the
    edit tools and run it with `python scratch.<name>.py`. Do **not** cram
    multi-line experiments into `python -c "..."` invocations — they are hard
    to read, hard to iterate on, and hard for the user to follow. The
    `scratch.*` prefix is gitignored / understood to be throwaway.

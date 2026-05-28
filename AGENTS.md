# AGENTS.md

Notes for AI coding agents working in this repo. For project intent and end-user
docs, see [README.md](README.md). For the evolving public API surface and
design discussion, see [API2.md](API2.md). Open TODOs / non-goals live in
[TODO.md](TODO.md) — **always re-check TODO.md before suggesting changes**;
many "obvious" features are in the *Never, Will not Implement* section.

## Project at a glance

- Pure-Python library (`tuplesaver/`) that persists immutable dataclass-style
  models (`Row`, `TableRow`) to SQLite via [apsw](https://rogerbinns.github.io/apsw/).
- **Python ≥ 3.14 only.** PEP 649 lazy annotations are the baseline — do **not**
  add `from __future__ import annotations`. Annotation resolution goes through
  `typing.get_type_hints()` at model-compile time.
- No runtime dependencies beyond `apsw` and `msgspec`. Keep it that way (`README.md` Design Principles: "no dependencies").
- Single-node, single-process design. Do not introduce pooling, threading, or
  multi-writer abstractions.

## Module map (`tuplesaver/`)

| File | Role |
|------|------|
| [model.py](tuplesaver/model.py) | `RowMeta` metaclass, `Row` / `TableRow`, deferred model compilation, schema-type inference |
| [rel.py](tuplesaver/rel.py) | Relation AST: `FieldExpr`, `BinaryExpr`, `LogicalExpr` (produced by `Model.field == value` etc.) |
| [rel_compiler.py](tuplesaver/rel_compiler.py) | Lowers `rel` AST + t-strings to SQL fragments (EXISTS semi-joins for FK traversal) |
| [sql.py](tuplesaver/sql.py) | DDL / DML template generation |
| [adaptconvert.py](tuplesaver/adaptconvert.py) | SQLite ↔ Python adaptation; msgspec fallback for non-native types |
| [cursorproxy.py](tuplesaver/cursorproxy.py) | `AdaptingCursor` + per-model row materialization with `Lazy` FK proxies |
| [lazy.py](tuplesaver/lazy.py) | `Lazy[M]` deferred FK loader |
| [engine.py](tuplesaver/engine.py) | `Engine` CRUD API: `insert`, `find`, `select`, `update`, `delete`, `query` |
| [migrate.py](tuplesaver/migrate.py) | Migration state machine + apply/generate |
| [migrate_cli.py](tuplesaver/migrate_cli.py) | `tuplesaver-migrate` CLI |
| [conftest.py](tuplesaver/conftest.py) | Shared pytest fixtures (`engine`, `sql_log`, `benchmark`, `limit_stack_depth`) |
| [migrate_scenarios/](tuplesaver/migrate_scenarios) | Per-scenario folders (`SCENARIO.md` + optional `m.py`) consumed by migrate tests |

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
  [tuplesaver/engine_test.py](tuplesaver/engine_test.py).
- **Ruff line length is 190.** Don't break long signatures for cosmetic reasons.
  Selected rule set is broad (`SLF`, `SIM`, `PTH`, `PD`, `ANN001`, `ANN201`,
  `RUF` ...); run `ruff check --fix` after edits.
- **Type parameter naming:** use `type[R]` on APIs whose return type depends on
  the passed model (`find`, `select`, `query`); use the bare metaclass
  `RowMeta` for internal helpers that only need "a model class". See the
  docstring on `RowMeta` in [model.py](tuplesaver/model.py).
- **t-strings (PEP 750)** are used to embed model field references in raw
  SQL fragments, e.g. `t"{Athlete.team.name} = 'Red'"`. They are processed by
  `rel_compiler.py`. Don't replace them with plain `f"..."`.
- **Benchmarks** are pytest-benchmark tests, disabled by default
  (`--benchmark-disable` in `addopts`). The `benchmark` fixture pins to CPU
  cores `{6, 7}` — this is intentional and host-specific; do not "fix" it.
- **`nbstripout`** runs in pre-commit; do not commit notebook outputs.

## Gotchas

- **`RowMeta.__getattr__` returns `FieldExpr` for any unknown attr.** Typos
  like `Model.namee` silently produce expressions instead of raising. When
  diagnosing weird query bugs, suspect this first.
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
- **The package name is still `tuplesaver` even though models are no longer
  `NamedTuple`s.** Renaming is a tracked TODO — don't preemptively rename.

## When changing the public API

- Update [API2.md](API2.md) and [TODO.md](TODO.md) in the same change when
  semantics shift.
- Prefer deletion over deprecation shims — this is a pre-1.0 library and the
  TODO is explicit about minimizing surface area.
- Run the full suite (`pytest -vv`); all 227+ tests should pass

## Dev pratices
- Always check `TODO.md` before suggesting changes. Many "obvious" features are
  already tracked as non-goals or future work.
- Run tests, then `ty check`, then `ruff check --fix` in that order
    before moving on to the next step.
- Always consider updating this file when making changes to codebase or docs OR when ever I as to code in a specific way.

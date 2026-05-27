# Docs/Notes
## Types of Models
- "table model" - Backed by a table in the database
- "alt model" - Backed by a view in the database, but could have fields that are added (eventually), removed, or modified. Still have an id field that mapps to the original table.
- "adhoc model" - Backed by any arbitrary query, doesnt have an id field, and can have any fields.
- "nontable model" - "alt model" or "adhoc model"
## JOINs
JOINs are automatic, and disambiguated by the the reference path `Athelete.team.name`
## Types
https://docs.python.org/3/library/sqlite3.html#sqlite3-types

These are the only built in type mappings

| Python | SQLite  |
|--------|---------|
| None   | NULL    |
| int    | INTEGER |
| float  | REAL    |
| str    | TEXT    |
| bytes  | BLOB    |

We also handle the following types automatically:

| Python                                           | SQLite Schema Type     | Mechanism                                            |
|:-------------------------------------------------|:-----------------------|:-----------------------------------------------------|
| `bool`                                           | `BOOL_INT` (INTEGER)   | built-in special case (0/1)                          |
| `datetime`                                       | `DATETIME_TEXT` (TEXT) | unquoted ISO-8601 string via `msgspec.to_builtins()` |
| `date`                                           | `DATE_TEXT` (TEXT)     | unquoted ISO-8601 string via `msgspec.to_builtins()` |
| `time`                                           | `TIME_TEXT` (TEXT)     | unquoted ISO-8601 string via `msgspec.to_builtins()` |
| `Decimal`                                        | `DECIMAL_TEXT` (TEXT)  | unquoted decimal string via `msgspec.to_builtins()`  |
| `UUID`                                           | `UUID_TEXT` (TEXT)     | unquoted UUID string via `msgspec.to_builtins()`     |
| `Enum` (String-based)                            | `ENUM_TEXT` (TEXT)     | unquoted string via `msgspec.to_builtins()`          |
| `Enum` (Integer-based)                           | `ENUM_INT` (INTEGER)   | unquoted int via `msgspec.to_builtins()`             |
| buffer protocol (e.g. `memoryview`, `bytearray`) | `BLOB` (BLOB)          | apsw auto-adapts via buffer protocol as bytes        |
| `dict`, `list`, `set`, `tuple`, `dataclass`, etc | `JSON_TEXT` (TEXT)     | msgspec JSON encode/decode fallback                  |

Any other type that msgspec can serialize is stored as JSON. If msgspec cannot serialize the type, it raises at write time.

### A note on datetime storage and SQLite date functions

Complex types like `list`, `dict`, and `dataclass` are stored as **JSON TEXT** (SQLite will report their `typeof()` as `text`). However, scalar types like `datetime`, `Decimal`, `UUID`, and string `Enum` are stored as pure unquoted strings (also `text` affinity). Integer `Enum`s are stored as plain integers. Buffer protocols (`bytes`, `bytearray`, `memoryview`) are stored as raw SQLite `BLOB`.

Because datetimes are stored as standard `TEXT`:
- `ORDER BY ts`, `WHERE ts = ?`, `BETWEEN ? AND ?` all work correctly — ISO strings sort lexically
- SQLite's date functions (`datetime()`, `strftime()`, `julianday()`, etc.) **work natively** on these columns (e.g. `SELECT strftime('%Y', ts)` returns the year)
- Raw string literals in SQL (`WHERE ts = '2024-06-15T12:00:00'`) **match correctly** without requiring parameter adaptation.

Note: When mixing naive and timezone-aware datetimes, sorting behavior follows ASCII string rules (e.g. 'Z' sorts after '.', while '+' and '-' sort before '.'). This means aware datetimes can sort incorrectly relative to naive datetimes with microseconds. Always store datetimes in a consistent timezone/format for chronological sorting.

## sqlite3
https://docs.python.org/3/library/sqlite3.html
https://sqlite.org/np1queryprob.html
https://andre.arko.net/2025/09/11/rails-on-sqlite-exciting-new-ways-to-cause-outages/
https://fractaledmind.com/2024/04/15/sqlite-on-rails-the-how-and-why-of-optimal-performance/
https://rogerbinns.github.io/apsw/cursor.html - Richard Hipp says this is a better wrapper.

## Other big users of apsw
see: https://clickpy.clickhouse.com/dashboard/apsw
- all of these seem to focus on data-exploration / analytics use cases
  - https://github.com/AnswerDotAI/fastlite
  Similar, add CRUD ORM on top of DataClass models that generate straight from the schema, or CREATE from dataclasses.
  - https://sqlite-utils.datasette.io/en/stable/python-api.html / https://github.com/AnswerDotAI/apswutils this is a library and a fork that adds apsw support to sqlite-utils.

## other SQLite ORMs
- https://pypi.org/project/sqler/ (repo seems deleted, downloaded tarball from pypi)


Really need to read and understand this new annotation sematics coming in 3.14, as well as difference between inspect.get_nnotations and typing.get_type_hints
https://docs.python.org/3/howto/annotations.html#annotations-howto
https://github.com/python/cpython/issues/102405
https://peps.python.org/pep-0649/

## Integrating into a web framework

### Error Handling for Web Frameworks

`engine.find()` raises `RecordNotFoundError` when no matching record exists, following Ruby on Rails semantics. This makes it easy to convert to HTTP 404 responses in web frameworks:

```python
from tuplesaver.engine import Engine, RecordNotFoundError

# Flask example
@app.errorhandler(RecordNotFoundError)
def handle_not_found(e):
    return {"error": str(e)}, 404

# FastAPI example
@app.exception_handler(RecordNotFoundError)
async def not_found_handler(request, exc):
    return JSONResponse(status_code=404, content={"detail": str(exc)})
```

Note: `engine.find_by()` returns `None` instead of raising, giving you the choice of how to handle missing records.


# Migration System

Manage development and application of SQLite schema migrations.

- Ensure schema matches TableRow models
- Ensure migrations apply cleanly to production
- Triage migration conflicts between devs
- Auto-generate obvious migrations

## File Layout

```
mydb.sqlite                    # working DB (refresh from production)
mydb.sqlite.ref                # reference DB (production snapshot, immutable)
mydb.sqlite.migrations/
    001.create_users.sql
    002.add_email_column.sql
mydb.sqlite.bak/
    2026-11-19T14-30-05.123456.000.mydb.sqlite
    2026-11-20T09-15-42.456789.001.mydb.sqlite
```

## States

Priority: ERROR > CONFLICTED > DIVERGED > PENDING > MISMATCH > CURRENT.

| State | Meaning | Fix |
|-------|---------|-----|
| `CURRENT` | Schema, scripts, and DB all agree | — |
| `MISMATCH` | Models differ from DB, no script yet | `generate()` → PENDING |
| `PENDING` | Unapplied migration scripts exist | `apply()` → MISMATCH or CURRENT |
| `DIVERGED` | Scripts differ from working DB (no ref) | `restore_db()` → PENDING |
| `CONFLICTED` | Scripts differ from ref DB | `restore_scripts()` → CURRENT or DIVERGED |
| `ERROR` | Bad migration files (gaps, dupes) | Manual fix |

### State Transitions Diagram

```
 start ────┐
           v
         ┌──────────┐
         │  check() │<──────────────────────────────yes─────┐
         └───┬──────┘                                       │
             │                                            state changed?─────no─────>done
   ┌──────┬──┴───┬─────────┬───────────┬──────────┐             ^
   v      v      v         v           v          v             │
 ERROR  CONFL  DIVERG    PENDING    MISMATCH   CURRENT          │
   │      │      │         │           │          │             │
   v      v      v         v           v          v             │
 exit 1  restore restore  backup &  generate   exit 0           │
         scripts  db      apply all                             │
           │      │         │                                   │
           └──────┴─────────┴──────────recurse──────────────────┘
```

Has both a Python API and CLI, which share the same underlying logic and state management. The CLI is just a thin wrapper around the API, so any action you can do in the CLI can also be done programmatically, and vice versa.

## CLI
Entry point: `tuplesaver-migrate` (or `python -m tuplesaver.migrate_cli`)

### Global flags (required, with pyproject.toml fallback)

```
--db-path PATH      Path to working DB
--models-module MODULE   Dotted module path, e.g. myapp.models
```

Set permanently in `./pyproject.toml`:
```toml
[tool.tuplesaver]
db_path = "data/mydb.sqlite"
models_module = "myapp.models"
```
## sqlite extensions
apsw bundles these.
should show example, for instance of turn on an using decimal summation?

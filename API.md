# API

## Concepts

**Model (M)** — Typed record definition. Subclass `TableRow` for persisted
tables, or `Row` for ad-hoc / view-shaped query results. Field `id: int | None`
is provided automatically by `TableRow` (kw-only, defaulted); do not declare it
yourself. Table models must subclass `TableRow` directly; subclassing an
existing table model raises `TableModelInheritanceError`. `Row` models may
subclass each other like normal frozen dataclasses. Models are frozen
dataclasses; use `dataclasses.replace(obj, ...)` to produce a modified copy.

```python
class User(TableRow):
    name: str
    age: int
    manager: User | None
```

**Relation (R)** — Predicate expression built from model fields. Traversal
across foreign keys is expressed by field chaining and lowered to **EXISTS
semi-joins** in SQL.

```python
User.name == "Jon"
User.manager.name == "Paul"
(User.name == "Jon") | (User.manager.name == "Paul")
```

Raw SQL predicates can be embedded with PEP 750 t-strings so model field
references stay refactor-safe:

```python
t"{User.name} LIKE 'J%'"
```

For find/update/delete-by-id, pass the integer id directly as the target
(compiled as `id = ?`):

```python
engine.find(User, 10)
```

## Engine API

```python
class Engine:
    def ensure_table_created(self, Model: type[TableRow]) -> None: ...

    def insert(self, row: M) -> M: ...

    def find(self, Model: type[M], target, params=None, /, *, order=None) -> M: ...
    def select(self, Model: type[M], target=None, params=None, /, *, order=None, limit=None, offset=None) -> TypedCursorProxy[M]: ...
    def query(self, Model: type[M], sql: str, parameters: Sequence | dict | None = None) -> TypedCursorProxy[M]: ...

    def update(self, Model: type[TableRow], target, params=None, /, **patch) -> int: ...
    def delete(self, Model: type[TableRow], target, params=None, /) -> int: ...
```

- `find` raises `RecordNotFoundError` when nothing matches.
- `select` returns a `TypedCursorProxy[M]`. The cursor is **iterable** (yields
  model instances) for streaming, and exposes the usual apsw methods
  (`fetchone`, `fetchall`, `fetchmany`). `target=None` selects all rows.
  ```python
  for row in engine.select(Post, Post.score > 95.7):  # streams row-by-row
      ...
  rows = engine.select(Post).fetchall()               # materialize all
  ```
- `query` is the **raw-SQL escape hatch**: pass a SQL string (+ optional
  `Sequence | dict` parameters) and get back a `TypedCursorProxy[M]`. For
  model-relation filtering use `select` / `find`.
- `update` / `delete` return the number of affected rows; `target=None`
  is a no-op (returns `0`).
- `insert` is for `TableRow` only and returns the inserted row with `id`
  populated.
- `params` (positional, on `find` / `select` / `update` / `delete`) overrides
  named parameters bound by a t-string `target`. Plain-value interpolations
  whose source expression is a valid identifier are bound under that name
  (e.g. `{tolerance}` → `:tolerance`), so the same predicate can be reused
  with different values:
  ```python
  pred = t"{Post.score} >= {min_score}"
  engine.select(Post, pred, {"min_score": 50})
  engine.select(Post, pred, {"min_score": 90})
  ```

## API Comparison

|   | Feature                                | sqlir                                                          | Rails ActiveRecord                                               |
|:--|:---------------------------------------|:--------------------------------------------------------------------|:-----------------------------------------------------------------|
|   | **Model Definition**                   |                                                                     |                                                                  |
|   | Model class                            | `class Post(TableRow): ...`                                         | `class Post < ApplicationRecord`                                 |
|   | Field definitions                      | `name: str`  (type annotation)                                      | Inferred from database schema                                    |
|   | Foreign key definition                 | `band: Band \| None` (type annotation)                              | `belongs_to :band`                                               |
|   | Model instantiation                    | `post = Post("Hi", dt.now())`                                       | `post = Post.new(name: "Hi")`                                    |
|   | Modify fields                          | `dataclasses.replace(post, name="Hello")`                           | `post.name = "Hello"`                                            |
|   | JSON fields                            | `list` / `dict` / etc via msgspec                                   | `serialize` or `json` column type                                |
|   | _Relationships_                      |                                                                     |                                                                  |
|   | Joins                                  | implicit by path reference, e.g. `Post.user.name` (EXISTS semi-join)| `joins(:team => :league)`                                        |
|   | Loading                                | always lazy (`Lazy[M]` FK proxy)                                    | lazy with `includes`                                             |
| * | Backref relationships                  | `teams: list[Person]`                                               | `has_many :people`                                               |
| * | Many-to-many                           | through join models                                                 | `has_and_belongs_to_many`                                        |
|   |                                        |                                                                     |                                                                  |
|   | **Read**                               |                                                                     |                                                                  |
|   | Find one by Id                         | `engine.find(Post, 1)`                                              | `Post.find(1)`                                                   |
|   | Find one by fields                     | `engine.find(Post, Post.name == "Hi")`                              | `Model.find_by(name: "Hi")`                                      |
|   | Find one (raw predicate)               | `engine.find(Post, t"{Post.name} = 'Hi'")`                          | `Post.find_by_sql(sql).take`                                     |
| * | Find one or Create                     | —                                                                   | `Post.find_or_create_by(a: 1, b: 2)`                             |
|   | Select all                             | `engine.select(Post)`                                               | `Post.all`                                                       |
|   | Select by relation                     | `engine.select(Post, Post.name == "Hi")`                            | `Post.where(name: "Hi").all`                                     |
|   | Select with order/limit/offset         | `engine.select(Post, ..., order="name", limit=10, offset=20)`       | `Post.where(...).order(...).limit(...).offset(...)`              |
|   | Streaming cursor                       | `for r in engine.select(Post, Post.name == "Hi"): ...`              | `Post.where(...).find_each`                                      |
|   | Raw SQL                                | `engine.query(Model, sql, params)`                                  | `Model.find_by_sql(sql)`                                         |
|   | Aggregations                           | raw SQL / VIEW with `Row` models (views + migrate work well)        | `Model.group(...).sum(...)`                                      |
| * | Exists                                 | —                                                                   | `Post.where(name: "Hi").exists?`                                 |
| * | Pluck (scalar columns)                 | —                                                                   | `Post.pluck(:name)`                                              |
| * | Take (first N)                         | `engine.select(Post, limit=N)`                                      | `Post.take(N)`                                                   |
|   |                                        |                                                                     |                                                                  |
|   | **Write**                              |                                                                     |                                                                  |
|   | Insert                                 | `post = engine.insert(post)`                                        | `post.save`                                                      |
|   | Insert (one-liner)                     | `post = engine.insert(Post("Hi", dt.now()))`                        | `Post.create(name: "Hi")`                                        |
|   | Update by Id                           | `engine.update(Post, id, name="Apple")`                             | `Post.update(id, name: "Apple")`                                 |
|   | Update by relation                     | `engine.update(Post, Post.title == "snails", name="y2k")`           | `Book.where(title: "snails").update_all(name: "y2k")`            |
|   | Update by raw predicate                | `engine.update(Post, t"{Post.title} LIKE '%snails%'", name="y2k")`  | `Book.where("title LIKE ?", "%snails%").update_all(name: "y2k")` |
|   | Delete by Id                           | `engine.delete(Post, id)`                                           | `Post.delete(id)`                                                |
|   | Delete by relation                     | `engine.delete(Post, Post.title == "snails")`                       | `Book.where(title: "snails").delete_all`                         |
|   | Delete by raw predicate                | `engine.delete(Post, t"{Post.title} LIKE '%snails%'")`              | `Book.where("title LIKE ?", "%snails%").delete_all`              |
| * | Insert many                            | —                                                                   | `Post.insert_all([{a: 1}, {a: 2}])`                              |
| * | Upsert (single statement, UQ cols req) | —                                                                   | `Post.upsert({a: 1, b: 2}, unique_by: ['a'])`                    |
| * | Upsert (select + update/insert)        | —                                                                   | `Post.update_or_create_by(...)`                                  |
|   |                                        |                                                                     |                                                                  |
|   | **Schema Management**                  |                                                                     |                                                                  |
|   | Adhoc Table creation                   | `engine.ensure_table_created(Model)`                                | Rails migrations                                                 |
|   | Migrations                             | `sqlir-migrate` CLI + Python API                               | `rails generate migration`                                       |
|   | Foreign key constraints                | auto-generated from `Model \| None` FK fields                       | manual in migrations                                             |
|   |                                        |                                                                     |                                                                  |
|   | **Connection Management**              |                                                                     |                                                                  |
|   | Connection handling                    | explicit `Engine` instance                                          | implicit connection pool                                         |
|   | Transactions                           | `with engine.connection:`                                           | `Model.transaction do ... end`                                   |
|   | Connection pooling                     | discouraged; use ephemeral connections, separate RW and RO          | per-thread connection                                            |
|   |                                        |                                                                     |                                                                  |
|   | **Advanced Features**                  |                                                                     |                                                                  |
|   | Validations                            | not planned                                                         | built-in validations                                             |
|   | Callbacks/Hooks                        | not planned                                                         | before_save, after_create, etc.                                  |
|   | N+1 problem mitigation                 | fast SQLite mitigates concern                                       | `includes()` eager loading                                       |

Rows prefixed with `*` are not implemented; see [TODO.md](TODO.md) for status.

## Model Types

- **table model** — Backed by a table in the database. Subclass `TableRow`.
- **alt model** — Backed by a view in the database, but could have fields that
  are added (eventually), removed, or modified. Still has an `id` field that
  maps back to the original table.
- **adhoc model** — Backed by any arbitrary query. Has no `id` field and can
  have any fields. Subclass `Row`.
- **nontable model** — an *alt model* or an *adhoc model*.

## Joins

JOINs are automatic, and disambiguated by the reference path
`Athlete.team.name`. Foreign-key traversal is lowered to **EXISTS semi-joins**
in SQL.

## Type Mapping

SQLite has only five native storage types
(see the [sqlite3 type docs](https://docs.python.org/3/library/sqlite3.html#sqlite3-types)):

| Python | SQLite  |
|--------|---------|
| None   | NULL    |
| int    | INTEGER |
| float  | REAL    |
| str    | TEXT    |
| bytes  | BLOB    |

On top of those, sqlir handles the following types automatically:

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

Any other type that msgspec can serialize is stored as JSON. If msgspec cannot
serialize the type, it raises at write time.

### `Any`

`Any` is **banned on table models** (`TableRow`): it has no storage/schema/SQL
type or affinity, so there is no sensible column to create. Declaring an `Any`
field on a `TableRow` raises `AnyTypeNotAllowedOnTableRow` at compile time.

`Any` **is allowed on ad-hoc `Row` models**, where it means "pass the raw
SQLite value through unconverted" — no adaptation on the way in, no conversion
on the way out.

### A note on datetime storage and SQLite date functions

Complex types like `list`, `dict`, and `dataclass` are stored as **JSON TEXT**
(SQLite will report their `typeof()` as `text`). However, scalar types like
`datetime`, `Decimal`, `UUID`, and string `Enum` are stored as pure unquoted
strings (also `text` affinity). Integer `Enum`s are stored as plain integers.
Buffer protocols (`bytes`, `bytearray`, `memoryview`) are stored as raw SQLite
`BLOB`.

Because datetimes are stored as standard `TEXT`:
- `ORDER BY ts`, `WHERE ts = ?`, `BETWEEN ? AND ?` all work correctly — ISO
  strings sort lexically
- SQLite's date functions (`datetime()`, `strftime()`, `julianday()`, etc.)
  **work natively** on these columns (e.g. `SELECT strftime('%Y', ts)` returns
  the year)
- Raw string literals in SQL (`WHERE ts = '2024-06-15T12:00:00'`) **match
  correctly** without requiring parameter adaptation.

Note: When mixing naive and timezone-aware datetimes, sorting behavior follows
ASCII string rules (e.g. 'Z' sorts after '.', while '+' and '-' sort before
'.'). This means aware datetimes can sort incorrectly relative to naive
datetimes with microseconds. Always store datetimes in a consistent
timezone/format for chronological sorting.

## Error Handling (Web Frameworks)

`engine.find()` raises `RecordNotFoundError` when no matching record exists,
following Ruby on Rails semantics. This makes it easy to convert to HTTP 404
responses in web frameworks:

```python
from sqlir.engine import Engine, RecordNotFoundError

# Flask example
@app.errorhandler(RecordNotFoundError)
def handle_not_found(e):
    return {"error": str(e)}, 404

# FastAPI example
@app.exception_handler(RecordNotFoundError)
async def not_found_handler(request, exc):
    return JSONResponse(status_code=404, content={"detail": str(exc)})
```

Note: `engine.find_by()` returns `None` instead of raising, giving you the
choice of how to handle missing records.

## Migrations

Manage development and application of SQLite schema migrations.

- Ensure schema matches `TableRow` models
- Ensure migrations apply cleanly to production
- Triage migration conflicts between devs
- Auto-generate obvious migrations

### File Layout

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

### States

Priority: ERROR > CONFLICTED > DIVERGED > PENDING > MISMATCH > CURRENT.

| State | Meaning | Fix |
|-------|---------|-----|
| `CURRENT` | Schema, scripts, and DB all agree | — |
| `MISMATCH` | Models differ from DB, no script yet | `generate()` → PENDING |
| `PENDING` | Unapplied migration scripts exist | `apply()` → MISMATCH or CURRENT |
| `DIVERGED` | Scripts differ from working DB (no ref) | `restore_db()` → PENDING |
| `CONFLICTED` | Scripts differ from ref DB | `restore_scripts()` → CURRENT or DIVERGED |
| `ERROR` | Bad migration files (gaps, dupes) | Manual fix |

#### State Transitions Diagram

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

Migrations have both a Python API and a CLI, which share the same underlying
logic and state management. The CLI is just a thin wrapper around the API, so
any action you can do in the CLI can also be done programmatically, and vice
versa.

### CLI

Entry point: `sqlir-migrate` (or `python -m sqlir.migrate_cli`)

Global flags (required, with `pyproject.toml` fallback):

```
--db-path PATH           Path to working DB
--models-module MODULE   Dotted module path, e.g. myapp.models
```

Set permanently in `./pyproject.toml`:

```toml
[tool.sqlir]
db_path = "data/mydb.sqlite"
models_module = "myapp.models"
```

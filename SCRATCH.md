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

We also include by default the following mappings

| Python   | SQLite            | Adapt/Convert      |
|----------|-------------------|--------------------|
| bool     | builtins.bool     | 1 -> x01, 0 -> x00 |
| list     | builtins.list     | json dumps/loads   |
| dict     | builtins.dict     | json dumps/loads   |
| date     | datetime.date     | .isoformat()       |
| datetime | datetime.datetime | .isoformat()       |

Any other types will attempt to be pickled.


If you want to customize how you serialize, we use a thin wrapper on top of Adapt/Convert api.
https://docs.python.org/3/library/sqlite3.html#sqlite3-adapter-converter-recipes

    def adapt_date_iso(val):
        """Adapt datetime.date to ISO 8601 date."""
        return val.isoformat()

    sqlite3.register_adapter(datetime.date, adapt_date_iso)


    def convert_date(val):
        """Convert ISO 8601 date to datetime.date object."""
        return datetime.date.fromisoformat(val.decode())

    sqlite3.register_converter("date", convert_date)

So our api which wraps the above would look like this:

    def adapt_datetime_iso(val: datetime.datetime) -> bytes:
        """Adapt datetime.datetime to ISO 8601 date and time."""
        return val.isoformat().encode()

    def convert_datetime_iso(data: bytes) -> datetime.datetime:
        """Convert ISO 8601 date and time to datetime.datetime object."""
        return dt.datetime.fromisoformat(data.decode())

    from tuplesaver import register_adapt_convert

    register_adapt_convert(datetime.datetime, adapt_datetime_iso, convert_datetime_iso)

### A note on JSON columns
Currently we do not apply adapters/converters to json dumps, because without specifying a schema there is no way to reliably recover type info.

Even something as simple as date, would be ambiguous, because it could be a date or str going in

    {"date": "2021-01-01"}

If we enable dt.datetime serialization, then the above could have been

    dict(date=dt.datetime(2021, 1, 1))

or

    dict(date="2021-01-01")

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

## API Comparison

|   | Feature                                | tuplesaver                                                          | Rails ActiveRecord                                               |
|:--|:---------------------------------------|:--------------------------------------------------------------------|:-----------------------------------------------------------------|
|   | **Model Definition**                   |                                                                     |                                                                  |
|   | Model class                            | `class Post(NamedTuple): ...`                                       | `class Post < ApplicationRecord`                                 |
|   | Field definitions                      | `name: str`  (type annotation)                                      | Inferred from database schema                                    |
|   | Foreign key definition                 | `band: Band` (type annotation)                                      | `belongs_to :band`                                               |
|   | Model instantiation                    | `post = Post(None, "Hi", dt.now())`                                 | `post = Post.new(name: "Hi")`                                    |
|   | Modify fields                          | `post._replace(name="Hello")`                                       | `post.name = "Hello"`                                            |
|   |                                        |                                                                     |                                                                  |
|   | **Read**                               |                                                                     |                                                                  |
|   | Find one by Id                         | `engine.find(Post, 1)`                                              | `Post.find(1)`                                                   |
|   | Find one by field                      | `engine.find_by(Post, name="Hi")`                                   | `Model.find_by(name: "Hi")`                                      |
|   | Find one or Create                     | Not planned                                                         | `Post.find_or_create_by(a: 1, b: 2)`                             |
|   | _many_                                 |                                                                     |                                                                  |
|   | Find many                              | `@select(Post): f"WHERE {Post.name} = 'Hi'"`                        | `Post.where(name: "Hi")`                                         |
|   | Query builder                          | `@select(Model)` decorator                                          | `Model.where(...).order(...)`                                    |
|   | Raw SQL                                | `engine.query(Model, sql)`                                          | `Model.find_by_sql(sql)`                                         |
|   | Aggregations                           | raw SQL with `Row` models, encourage using view migrations          | `Model.group(...).sum(...)`                                      |
|   | **Write**                              |                                                                     |                                                                  |
|   | Save (Insert or Update)                | `post = engine.save(post)`                                          | `post.save`                                                      |
|   | Save (one-liner)                       | `post = engine.save(Post(None, "Hi", dt.now()))`                    | `Post.create(name: "Hi")`                                        |
|   | Update by Id                           | `post = engine.update(Post, id, name="Apple")`                      | `Post.update(id, name: "Apple")`                                 |
|   | Update by instance                     | `post = engine.update(post, name="Apple")`                          | `post.update(name: "Apple")`                                     |
|   | Delete by Id                           | `engine.delete(Post, id)`                                           | `Post.delete(id)`                                                |
|   | Delete by instance                     | `engine.delete(post)`                                               | `post.destroy`                                                   |
|   | _many_                                 |                                                                     |                                                                  |
| * | Insert many                            | `engine.insert_all(Post, [Post(1,2), Post(3,4)])`                   | `Post.insert_all([{a: 1, b: 2}, {a: 3, b: 4}])`                  |
| * | Update many                            | `engine.update_all(Post, {name: "y2k"}, where={title="snails"})`    | `Book.where(:title => 'snails').update_all(name: 'y2k')`         |
| * | Delete many                            | `engine.delete_all(Post, where={title="snails"})`                   | `Book.where(:title => 'snails').delete_all`                      |
| * | Update many (full query)               | @update(Post, {name: 'y2k'}): f"WHERE {Post.title} LIKE '%snails%'" | `Book.where('title LIKE ?', '%snails%').update_all(name: 'y2k')` |
| * | Delete many (full query)               | @delete(Post): f"WHERE {Post.title} LIKE '%snails%'"                | `Book.where('title LIKE ?', '%snails%').delete_all`              |
|   |                                        |                                                                     |                                                                  |
|   | **Advanced CRUD Write**                |                                                                     |                                                                  |
| * | Upsert (Single statement, UQ cols req) | `engine.upsert(Post, {a:1, b:2}, unique_by=['a'])`                  | `Post.upsert({a: 1, b: 2}, unique_by: ['a'])`                    |
| * | Upsert (Select+Update/Insert, no UQ)   | `engine.update_or_create_by(Post, {a:1, b:2}, unique_by=['a'])`     | `Post.update_or_create_by(...)`                                  |
|   |                                        |                                                                     |                                                                  |
|   | **Relationships**                      |                                                                     |                                                                  |
|   | joins                                  | automatic explict by path reference e.g. `Post.user.name`           | `joins(:team => :league)`                                        |
|   | loading                                | always lazy                                                         | Lazy loading with `includes`                                     |
| * | Backref relationships                  | `teams: list[Person]`                                               | `has_many :people`                                               |
| * | Many-to-many                           | Through join models                                                 | `has_and_belongs_to_many`                                        |
|   |                                        |                                                                     |                                                                  |
|   | **Type System**                        |                                                                     |                                                                  |
|   | Type safety                            | static typing on cursor                                             | Runtime with Sorbet (optional)                                   |
|   | Custom types                           | `register_adapt_convert()`                                          | ActiveRecord serializers                                         |
|   | JSON fields                            | `list/dict` auto-serialized                                         | `serialize` or `json` column type                                |
|   |                                        |                                                                     |                                                                  |
|   | **Schema Management**                  |                                                                     |                                                                  |
|   | Table creation                         | `engine.ensure_table_created(Model)`                                | Rails migrations                                                 |
|   | Migrations                             | `tuplesave-migrate` cli + python api                                | `rails generate migration`                                       |
|   | Foreign key constraints                | Auto-generated                                                      | Manual in migrations                                             |
|   |                                        |                                                                     |                                                                  |
|   | **Connection Management**              |                                                                     |                                                                  |
|   | Connection handling                    | Explicit `Engine` instance                                          | Implicit connection pool                                         |
|   | Transactions                           | `with engine.connection:`                                           | `Model.transaction do ... end`                                   |
|   | Connection pooling                     | Discouraged, use ephemeral connections. Separate RW and RO          | per-thread connection                                            |
|   |                                        |                                                                     |                                                                  |
|   | **Advanced Features**                  |                                                                     |                                                                  |
|   | Validations                            | Not planned                                                         | Built-in validations                                             |
|   | Callbacks/Hooks                        | Not planned                                                         | before_save, after_create, etc.                                  |
|   | N+1 problem mitigation                 | fast SQLite mitigates concern                                       | `includes()` eager loading                                       |



## Notes from RoR Active Record
### Connection Handling
Implicit Connection Handling: Active Record uses a global connection pool and thread-local connections instead of an explicitly passed session object. On the first database call in a given thread (e.g. a web request thread), Active Record will check out a connection from the pool and associate it with that thread
discuss.rubyonrails.org . That same connection is reused for all queries in the thread by default, instead of checking out/in on every query, to reduce lock overhead discuss.rubyonrails.org . Rails keeps track of the “current” connection via a thread-local key, ensuring each thread uses its own database connection .

Request Lifecycle and Cleanup: In a typical Rails request, the framework ensures the connection is returned to the pool at the end. The Rack middleware

Transactions and Context: Active Record provides methods like Model.transaction do ... end to run a block of code in a database transaction. Internally, this just uses the thread’s connection to BEGIN/COMMIT

### No Identity Map
Identity Map (or Lack Thereof): One notable aspect of Active Record’s implicit approach is that it historically does not implement a global identity map by default (unlike explicit session ORMs which typically do). In other words, if you query the same record twice in Rails (outside of the same short-lived transaction or object reference), you’ll get two separate Ruby object instances representing the same row. Rails did experiment with an optional Identity Map in Rails 3.2 (to ensure each object is loaded only once per request/thread)
api.rubyonrails.org
api.rubyonrails.org
, but it was disabled by default and later removed. Without an explicit session tracking all loaded entities, Rails forgoes the complexity of a long-lived identity map. This means less memory overhead and bookkeeping, at the cost of potential duplicate objects

### No engine or session
These are injected into the objects themselves at runtime. AR assumes DB schema is source of truth.
Migrations are done in a DSL with an external

### recursive saves are configured per attribute/field

### ruby autocompletions for fields are not native and come in via rbi files (like pyi files)
### relationships defined with `has_many`, `belongs_to`, `has_one`, `has_and_belongs_to_many`,


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

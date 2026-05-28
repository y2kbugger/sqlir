# API

## Concepts

**Model (M)** — Typed record definition. Subclass `TableRow` for persisted
tables, or `Row` for ad-hoc / view-shaped query results. Field `id: int | None`
is provided automatically by `TableRow` (kw-only, defaulted); do not declare it
yourself. Models are frozen dataclasses; use `dataclasses.replace(obj, ...)` to
produce a modified copy.

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

    def find(self, Model: type[M], target, /, *, order=None) -> M: ...
    def select(self, Model: type[M], target=None, /, *, order=None, limit=None, offset=None) -> list[M]: ...
    def query(self, Model: type[M], sql_or_rel=None, parameters=None) -> TypedCursorProxy[M]: ...

    def update(self, Model: type[TableRow], target, /, **patch) -> int: ...
    def delete(self, Model: type[TableRow], target, /) -> int: ...
```

- `find` raises `RecordNotFoundError` when nothing matches.
- `select` returns `[]` when nothing matches; `target=None` selects all rows.
- `query` accepts either a raw SQL string (+ optional `Sequence | dict`
  parameters) or a relational expression (+ optional `dict` of extra params)
  and returns a `TypedCursorProxy[M]` for streaming / fetchmany use.
- `update` / `delete` return the number of affected rows; `target=None`
  is a no-op (returns `0`).
- `insert` is for `TableRow` only and returns the inserted row with `id`
  populated.

## API Comparison

|   | Feature                                | TupleSaver                                                          | Rails ActiveRecord                                               |
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
|   | Streaming cursor                       | `engine.query(Post, Post.name == "Hi")`                             | `Post.where(...).find_each`                                      |
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
|   | Migrations                             | `tuplesaver-migrate` CLI + Python API                               | `rails generate migration`                                       |
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

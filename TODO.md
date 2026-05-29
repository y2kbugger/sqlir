# WIP
- convert readme and docs and package name away from tuplesaver now that we don't save tuples

# Bugs
- Where exists clause should start on its own line
- if migration fails in the middle of a migration but before the bookkeeping, then we could fail with a partially applied migration and it wouldn't know to roll back or try again. We should probably have a way to detect this and roll back or try again on the next run. (or during error handling itself, but that might be risky)


# Testing
- Test delete by id (no match) and update id (no match)?
- Test that basic engine crud operation emit only the expected statements, e.g. no select before update, etc. DO FOR ALL Engine OPERATIONS
- test `Any` type on Row/TableRow models. Ban? Allow?
- test that you can add extra defs to a model without things blowing up (or add eager enforcement that you can't do this)
- relax eager enforcement of FK Models being registered
    - Test case for this
- Test case that you cannot subclass a tablemodel, e.g.
    ```python
    class BaseModel(TableRow):
        name: str

    class SubModel(BaseModel):  # should raise
        boogie: int
    ```
- test that everything works on when doing arbitrary adhoc model queries that select FK in as model relationships
- unit test for self join also
- test is_registered_fieldtype
  - unknown types, unregistered models, both Optional and non-Optional variants
- find, if more than one result matched
- Test that non Fields greater than zero cannot be called id
- Test for cyclic data structures e.g. A -> B -> C -> A
- Test the foreign key may only be a union with None i.e. Optional BUT NOT with int or something else
- Investigate/ Test what Happens when specifying Model | int, should this raise??
- how handle unions of two valid types, e.g. int | str
  - Adapting would work fine, but conversion could be ambiguous
  - I think we should just raise on this
- Test can get using model with int as FK rather than Model to stop recursive loading
  e.g. int instead of Node in a Person_IntFK model
- Test you can have two field of same type,e.g. right_node, left_node
- How to test that we don't trigger lazy queries ourselves?
- Validate in Meta creation that related models in fields of table models are actually table models and not alt/adhoc models
- Test duplicate joins in query.select deduplicates
- Benchmark and test connection creation and closing
- benchmark model creation, field access, hashing, and memory footprint vs plain unpatched NamedTuple, and dataclass,
    - maybe resurect some of the old benchmarks for this.
- ensure that ID fields are always stored as integer affinity. i really think there are some landmines with tables having "text" in the the name. maybe all id columns should just be INT now that we do adapt/convert without relying on sql column types.
- Can a modeul use dataclass feature like "field"? should we make a custom one?

## testingmeta
- I want to instrument sqlite to log and profile queries.
- use the assert_type from typing to check type hints
  - Test types on engine.find/select
- fix names / order of model_test.py, e.g. test_table_meta_... -> test_get_meta__....

# Next
- UUID should be supported natively without JSON quoting as root type (like date, Decimal, etc) so db can use it directly
- make rel template strings easily print as their resolved SQL for debugging
- types msgspec cannot encode raise at write time — confirm error message is clear and actionable
- interactive restore list too long. can you page restores or head results?
- Find and remove unused exceptions
- Ship example.ipynb or output with library
- ai skill for library usage
- Python 3.14 lazy annotations are now the baseline. Keep model annotation handling simple and avoid re-introducing `from __future__ import annotations`.


## Backpop
- ONCE FINISHED, un-skip the fanout prevention test, and make sure it actually works.
- Also considder one to one relationships that backpop to a single instance rather than a list
- set[M] vs list[M] vs BackPop[M] as typehint?
- backpop
  ```python
  class Team(NamedTuple):
      id: int | None
      name: str
      teams: list[Person] # Backpop

  class Person(NamedTuple):
      id: int | None
      name: str
      team: Team # Forward
  ```

  Need a way to differentiate between two different backpop of same type
  - backprop must include the full name of the forward reference as the prefix of it's name
  - if this is not specified or not unique, raise an `AmbiguousBackpopError`
  - not FK is allowed to be a subset of another FK on the same model. `AmbiguousForwardReferenceError`
  ```python
  # Ex 1. disambiguating backpop
  class Team(NamedTuple):
      id: int | None
      name: str
      primary_teams: list[Person]
      secondary_teams: list[Person]

  class Person(NamedTuple):
      id: int | None
      name: str
      primary_team: Team
      secondary_team: Team

  # Ex 2. disambiguating backpop
  class Employee(NamedTuple):
      id: int | None
      name: str
      manager_of: List[Project]
      lead_developer_of: List[Project]
      lead_maintainer_of: List[Project]

  class Project(NamedTuple):
      id: int | None
      name: str
      manager: Employee
      lead_developer: Employee
      lead_maintainer: Employee
      lead: Employee # not allowed, because it is an ambiguous subset of lead_developer
  ```

  - Backpop without a forward reference, should just be `AmbiguousBackpopError` because it is ambiguous if you cannot find a forward reference that is a complete prefixed subset of the backpop name.
    ```python
    class Team(NamedTuple):
        id: int | None
        name: str
        teams: list[Person]
    class Person(NamedTuple):
        id: int | None
        name: str
    ```
  - Many-to-Many shall just fall out of two 1:1, is not really a concept
  - Here is a test case with complex relations
  try and figure out if this is ambiguous or not
  ```python
  class Employee(NamedTuple):
      id: int | None
      name: str
      manager_of: List[Project]
      lead_developer_of: List[Project]
      contributor_roles: List[ProjectEmployee]

  class Project(NamedTuple):
      id: int | None
      name: str
      manager: Employee
      lead_developer: Employee
      contributors: List[ProjectEmployee]

  class ProjectEmployee(NamedTuple):
      project: Project
      employee: Employee
      role: str
  ```


# Later
- automate a benchmark suite that outputs one large markdown results file, including all context needed to interpret the numbers
- harmonize name rel, relation, pred and predicate

## JSONB format - probably a breaking change.....so its soon or never
Basically we would have to wrap all json fields in a sqlite function call that parses and stores the binary format.
## Shadow Swap Pattern for Zero-Downtime Table Rebuilds
Atomic table replacement that minimizes write-lock duration. Only the rename step holds the lock; all data loading and index building happen outside the critical section.

1. **Capture schema of T** — `SELECT sql FROM sqlite_schema` for the table, its indexes (`sql IS NOT NULL`), and triggers
2. **Create shadow table `T__new`** — rewrite captured `CREATE TABLE` replacing `T` → `T__new`
3. **Load data into `T__new`** — all ETL happens here; no production objects touched
4. **Build indexes on `T__new`** — rewrite each index: table ref `T` → `T__new`, name `idx` → `idx__new`
5. **Atomic swap** (only critical section):
   ```sql
   BEGIN IMMEDIATE;
   ALTER TABLE T RENAME TO T__old;
   ALTER TABLE T__new RENAME TO T;
   COMMIT;
   ```
   Rename updates FK/view references automatically (SQLite >= 3.26). Triggers and indexes move with `T__old`.
6. **Recreate triggers** — execute captured trigger SQL unchanged; they attach to the current `T`
7. **Optional cleanup** — `DROP TABLE T__old;` (or keep for rollback)

## Explain Model
I want to be able to explain model function. This would explain what the type annotation is., what the sqllite column type is, And why?. Like it would tell you that an INT is a built-in Python SQLite type., but a model is another model, And a list of a built-in type is stored as json., And then what it would attempt to pickle if there would be a pickle if it's unknown..
This would help distinguish between a list of model and a list of something else. 
This is cool cuz it blends casa no sql with SQL. We could probably even make a refactoring tool to switch between the two.
- Also want to explain querys from engine
  - This could also be an off ramp from engine.select to a more generic query builder, e.g. `engine.query(Model, sql, params)`

## Migrations
- consider https://martinfowler.com/articles/evodb.html
- Generate ALTER instead of DROP/CREATE
- Generate SELECT-INTO for general alters
- pragma user_version and pragma application_id for something?

## Connection Management and Concurrency
- one connection per thread, like RoR AR
- Another options is to have two thread pools, one for reads and one for writes
  - This is more complex, but elimnates Busy errors
   https://kerkour.com/sqlite-for-servers
- SQLite supports concurrent reads but locks on writes.
  - Can be configured to block instead of raising an error on write contention
    https://sqlite.org/c3ref/busy_timeout.html
- https://kerkour.com/sqlite-for-servers
  - A 2024 guide to SQLite use and tuning on backend
  - `PRAGMA busy_timeout = 5000;` 5 seconds for app, 15 seconds for API
    - Allows waiting for a write lock to be released before raising an error

## Read about rich hickeys datomic
https://docs.datomic.com/datomic-overview.html

# One Day Maybe
- check for valid json on json fields
- pickling type, make a type annotation like `Pickle[MyType]` that would automatically pickle and unpickle the field, and raise if it fails to pickle or unpickle. This fills a gap left by the expunging of custom adapt/convert pairs.
- support sql column defs with default values, e.g. `name: str = "default name"` and then have that be the default value for the column in the create table statement, and also have it be the default value for the field when creating a new instance of the model without specifying that field.
    - maybe we already have this via field
- Auto detect or provide a way to santize/escape LIKE params. e.g.  of % or _
- engine.exists (rails has relation.exists, e.g. Customer.where(first_name: "Ryan").exist
- scalar accessors, e.g. RoR AR's pick. get one value from one row and one. note: this is already built into apsw, engine.get
- RoR annotate (and sql comments so that later we can use it during observabilites)


## Frozen Model
- e.g. disable lazy loading of fields, etc
  - to guarantee immutability after load, before passing to template etc.


## GROUP BY / Aggregation
Aggregations queries are more tightly coupled to Row model because the model must define the aggregations, but the query defines the grouping. Therefore you might want to define the query f-string in the model def. But this is
just a stylistic choice

Use Python 3.14 lazy annotations directly here; do not rely on `from __future__ import annotations`.

```python
class Person_TotalScore(NamedTuple):
    name: str
    total_score: Annotated[int, f"sum({Person.score})"]

@select(Person_TotalScore)
def apple_total()
    f"""
    WHERE {Person.name} = 'Apple'
    GROUP BY {Person.name}
    """
engine.query(*apple_total)

# or in the nested style, to communicate coupling
class Person_TotalScore(NamedTuple):
    name: str
    total_score: Annotated[int, f"sum({Person.score})"]

  @select(Person_TotalScore)
  def apple_total():
      f"""
      WHERE {Person.name} = 'Apple'
      GROUP BY {Person.name}
      """
engine.query(Person_TotalScore.apple_total)
```
Both of these would generate the same SQL
```sql
SELECT name, sum(score) as total_score
FROM Person
WHERE name = 'Apple'
```

## engine.upsert
| Upsert          | `Model.upsert(attrs, unique_by)`  | Insert or update based on unique key |

infered constraits from DB
- https://sqlite.org/syntax/column-def.html
- https://sqlite.org/syntax/column-constraint.html
- We can just use migrations to add constraints and make db the source of truth.
- We don't actually even need to read them in except to add validation on upserts (ie, only allow upserting on sets of unique columns)


```sql
create table XXX (
    id integer primary key,
    name text,
    place text,
    value int
);
-- the obligate unique constraint
CREATE UNIQUE INDEX IF NOT EXISTS XXX_name_place ON XXX (name, place);

-- make upsert on name,place combo
insert into XXX (name, place, value) values ('a', 'b', 777)
on conflict(name, place) do update set value = excluded.value;
-- or even just allow it to happen on any conflict (just set all non-id fields)
-- This gets a little tricky with existing data, but if we follow api of insert
--   and up, this makes sense, all fields are persisted (in either case insert or
--   update)
insert into XXX (name, place, value) values ('a', 'b', 888)
on conflict
    do update
        set name = excluded.name, place = excluded.place, value = excluded.value;
```

This is the user code
```python
class XXX(NamedTuple):
    id: int | None
    name: str
    place: str
    value: int

    _meta = Meta(
        unique_contraints=[('name','place')]
    )

engine.ensure_table_created(XXX)
engine.upsert(XXX(name='a', place='b', value=777))
engine.upsert(XXX(name='a', place='c', value=888))

```

## Row model `SELECT`ing from multiple tables, e.g. ror's `pluck`

```python
class Athlete_WithTeamName(NamedTuple):
    name: str
    team_name: Annotated[str, f"{Athlete.team.name}"]

engine.query(*select(Athlete_WithTeamName))
```
```sql
SELECT Athlete.name, Athlete.team.name as team_name
FROM Athlete
JOIN Team team ON Athlete.team = team.id
```

## JSON extracted field in SELECT
This kind of thing is already supported effortlessly in select style predicates.
This might come for free with aggregations.
```python
class Character_WithSpell(NamedTuple):
    id: int
    name: str
    spell: Annotated[str, f"{Character.stats} -> '$.spell'"]

engine.query(*select(Character_WithSpell))
```
```sql
SELECT id, name, stats -> '$.spell' as spell
FROM Character
```

## A way to package queries with models to make view like objects??
Could be one or more queries for one model. Could have parameters. could want to
reuse by adding where, or somethiing else??
```python
class TableInfo(NamedTuple):
    cid: int
    name: str
    type: str
    notnull: int
    dflt_value: Any
    pk: int

sql = f"PRAGMA table_info({Athlete.__name__})"

cols = engine.query(TableInfo, sql).fetchall()
```
Note: this is sortof like RoR AR's scopes
  scope :in_print, -> { where(out_of_print: false) }
  scope :out_of_print, -> { where(out_of_print: true) }
  scope :old, -> { where(year_published: ...50.years.ago.year) }
  scope :out_of_print_and_expensive, -> { out_of_print.where("price > 500") }
  scope :costs_more_than, ->(amount) { where("price > ?", amount) }

also allows a default scope

  default_scope { where(out_of_print: false) }



## Performance
- https://kerkour.com/sqlite-for-servers
  - `PRAGMA synchronous = NORMAL;`
  - `PRAGMA journal_mode = WAL;`
  - `PRAGMA cache_size = 10000;`
  - `PRAGMA cache_size = 1000000000`
- https://gcollazo.com/optimal-sqlite-settings-for-django/
- types of eager loads, see https://guides.rubyonrails.org/active_record_querying.html#eager-loading-associations
approx 20% perf boost for execute many on 20k rows, not worth it, yet
- Bulk inserts

```python
def insert_all[R: Row](self, Model: type[R], rows: Iterable[R]) -> None:
    """Insert multiple rows at once."""
    insert = get_meta(Model).insert
    assert insert is not None, "Insert statement should be defined for the model."
    with self.connection:
        self.connection.executemany(insert, rows)
```

## Nontable Model Reuse/Composition
This would be like relations in RoR AR
I believe a nontable model can reference another one.
This seems in theory possible, but might have impossible edge cases
```python
class Character_WithPowerColumn(NamedTuple):
    id: int
    name: str
    power: Annotated[str, f"{Character.stats} -> '$.power'"]

class Character_TotalPower(NamedTuple):
    id: int
    name: str
    total_power: Annotated[str, f"sum{Character_WithPowerColumn.power}"]

  @select(Character_TotalPower)
  def total_power():
      f"GROUP BY {Character.name}"

engine.query(*Character_TotalPower.total_power)
```
```sql
SELECT id, name, sum(stats -> '$.power') as total_power
FROM Character
GROUP BY name
```

## Cython implementation for faster field descriptor access for lazy loading, etc
Cython implementation of FieldDescriptor for better performance
`field_descriptor.pyx`
``` python
from typing import NamedTuple

cdef class Column:
    """Fast Column class using Cython"""
    cdef public str name
    cdef public object coltype

    def __init__(self, str name, object coltype):
        self.name = name
        self.coltype = coltype

    def __repr__(self):
        return f"Column(name={self.name!r}, coltype={self.coltype!r})"

    def __eq__(self, other):
        if not isinstance(other, Column):
            return False
        return self.name == other.name and self.coltype == other.coltype


cdef class CythonFieldDescriptor:
    """High-performance field descriptor using Cython"""
    cdef public Column column
    cdef public int index

    def __init__(self, Column column, int index):
        self.column = column
        self.index = index

    def __get__(self, object instance, object owner):
        # Fast path: if instance is None, return Column
        if instance is None:
            return self.column
        # Fast path: direct tuple indexing for instances
        return instance[self.index]

    def __repr__(self):
        return f"CythonFieldDescriptor(column={self.column}, index={self.index})"
```

# Probably Never
- a true cursor proxy and fetchoneonly helper/wrapper
  - cost penalty for get row benchmark (maybe test again later)
  - a pretty thin wrapper over native functionality

# Never, Will not Implement
- `TypedId` — a typed int subclass that encapsulated which Model an id belonged to
  - The engine API always takes the Model explicitly, so the id alone never needs to carry that information
  - Added complexity to model compilation (type-hint normalization) and to `TableRow.id` / `Model.Id` signatures for zero practical benefit
- switch to dict based queries, e.g. `engine.find(MyModel, {MyModel.name: "Bart"})`
  - Too much magic and increases boilerplate
  - CON to skipping: lose perfect "refactorability"
- `Any` for table models
  - it would automatically use the dynamic type adapter, but it would not know which converter to use to get it back to the original type
- Add passthrough for commit? e.g. engine.commit
  - just let the user use the existing connection, engine.connection.commit()?
  - Violates, only do what can't be done with the sqlite standard library
- `register_adapt_convert` / custom serialization registration API
  - Removed in favor of msgspec as a universal automatic fallback
  - msgspec handles all common types (bool, list, dict, Enum, UUID, datetime, date, time, set, frozenset, NamedTuple, dataclasses) with zero configuration
  - Adding back a registration layer re-introduces adapter/converter bookkeeping that msgspec makes unnecessary
  - For types msgspec can't handle, convert at the application layer before storing
- push lazy field making from cursor proxy to adaptconvert?
    - no, becuase the engine scope/ref isn't available in adapt/convert.

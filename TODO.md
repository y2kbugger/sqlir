# WIP
- find_by arbitraqt sql predicates, e.g. `engine.find_by(MyModel, f"{MyModel.name} = 'Bart'")`
- allow list[str] as field type, inner types are just for static analysis, but it is always stored as json

## TableRow Model
- disambiguate Row vs TableRow in relation to `is_row_model` and `get_meta`
- Move lazy proxy descriptors to the metaclass
- Harmonize typing of type[Row] to RowMeta (i think)
- fix ty and ruff errors in all files
- move stuff out of meta and into the model class itself, and then use that directly. e.g. `Model._meta.table_name` -> `Model.__tablename__` and `Model._meta.fields` -> `Model.__fields__`.
- convert readme and docs and package name away from tuplesaver now that we don't save tuples
- backfill __tablename__ when it is missing, e.g. just use the class name, test this
- make adapt/convert registration global, store cached converter on the model. (makes engine creation lighter)

## APSW Integration
- Document how any type that implements buffer is auto adapted and you only need to add converter for it (might be annonying if trying to just pickle a numpy array)
- combine rowtrace for type converting types and lazy maker all together
    pragma user_version and pragma application_id for versioning and migrations
    https://rogerbinns.github.io/apsw/tips.html#query-patterns
    and maybe don't make it use rowtrace??


# Bugs
- params on select style queries should be type converted.
- Switch to semi joins in sql query generator auto-joiner
    - otherwise, fanout happen. Add regression test for this.
- if migration fails in the middle of a migration but before the bookkeeping, then we could fail with a partially applied migration and it wouldn't know to roll back or try again. We should probably have a way to detect this and roll back or try again on the next run. (or during error handling itself, but that might be risky)


# Testing
- Test delete by id (no match) and update (via save) id (no match)?
- Test that basic engine crud operation emit only the expected statements, e.g. no select before update, etc. DO FOR ALL Engine OPERATIONS
- test `Any` type on TableRow models. Ban? Allow?
- test that you can add extra defs to a model without things blowing up (or add eager enforcement that you can't do this)
- relax eager enforcement of FK Models being registered
    - Test case for this
- Test case that you cannot subclass a model, e.g.
    ```python
    class BaseModel(TableRow):
        name: str

    class SubModel(BaseModel):  # should raise
        boogie: int
    ```
- test that adapt convert can't be added after Models start being registered.
- test that everything works on when doing arbitrary adhoc model queries that select FK in as model relationships
- unit test for self join also
- test is_registered_fieldtype
  - unknown types, unregistered models, both Optional and non-Optional variants
- find/find_by raise if more than one result matched
- test reensureing model updates if and only if schema has been migrated correctly
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
- Test that you may not reregister an adapt-convert pair
- Ensure test exists for model with unregistered field type, and that it raises UnregisteredFieldTypeError

## testingmeta
- I want to instrument sqlite to log and profile queries.
- use the assert_type from typing to check type hints
  - Test types on select (both decorator and non)
- fix names / order of model_test.py, e.g. test_table_meta_... -> test_get_meta__....

## API comparison docs
- take
- pluck
- exists
- insert many?


# Next
- interactive restore list too long. can you page restores or head results?
- Ship example.ipynb or output with library
- ai skill for library usage
- Find a remove unused exceptions
- More standard adaptconverters Enum, set, tuple, time, frozenset, Path, UUID, Decimal, bytes
  - tests?, examples?
- I want to fall back to pickles for any type that is not configured, and just raise if pickle fails
  - tests?, examples?
- support sql column defs with default values, e.g. `name: str = "default name"` and then have that be the default value for the column in the create table statement, and also have it be the default value for the field when creating a new instance of the model without specifying that field.

## Backpop
- Also considder one to one relationships that backpop to a single instance rather than a list
- set vs list as typehint?
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
## leverage tstring for query-ten avoid AST hacking
## JSONB format

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


## Foreign Key enforcement
Off by default, but can be enabled with
- `PRAGMA foreign_keys = true;`

## Migrations
- consider https://martinfowler.com/articles/evodb.html
- Improved status detail for declarative migrations, e.g. show diff between file and db object
- Generate ALTER instead of DROP/CREATE
- Generate SELECT-INTO for general alters
- Warning if anyone else has edited the schema since migration has last ran.
    - Store Schema/application version pragma
    - could also do this via table schema comparison
- leave "ensure table created" just for testing? or come up with better way to do it??

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


- Runtime checking of model fields, e.g. if a field is not in the table, raise an error
  - This could be useful for making models from adhoc queries. e.g. have it actually tell you what the model should look like.
- how to express more complex updates like this:
    `Book.where('title LIKE ?', '%Rails%').update_all(author: 'David')`
- Auto detect or provide a way to santize/escape LIKE params. e.g.  of % or _
- engine.exists (rails has relation.exists, e.g. Customer.where(first_name: "Ryan").exist
- scalar accessors, e.g. RoR AR's pick. get one value from one row and one
  column (technically pick also allows multiple colums) don't see why not just use
  find/find_by then access the field
- RoR annotate (and sql comments so that later we can use it during observabilites)
- Consider dropping the injected Engine, and goto a fluent RoR AR style interface
  - e.g. `row.save()` ipo `engine.save(row)`
- use return on updates to enable single statement updates with return value?
- deeper nested type restoration on json fields, e.g. `stats: dict[str, set[int]]` (kinda hard to do fo arbitrary cases)


## Frozen Model
- e.g. disable lazy loading of fields, etc
  - to guarantee immutability after load, before passing to template etc.


## GROUP BY / Aggregation
Aggregations queries are more tightly coupled to the adhoc model because the model must define the aggregations, but the query defines the grouping. Therefore you might want to define the query f-string in the model def. But this is
just a stylistic choice

To make annotations work, we force usage of `from __future__ import annotations`

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

## Multi Table Alt Model SELECT, e.g. ror's pluck

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

## Alternate lambda syntax
Just a more concise version of the decorator version. might be hard to squeeze into the typehints
```python
M, q = select(Athlete)(lambda: f"WHERE name LIKE '%e%'")
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
Note: this is like RoR AR's scopes
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
- combining find with find_by
  - better not to overload too much
- switch to dict based queries, e.g. `engine.find(MyModel, {MyModel.name: "Bart"})`
  - Too much magic and increases boilerplate
  - CON to skipping: lose perfect "refactorability"
- `Any` for table models
  - it would automatically use the dynamic type adapter, but it would not know which converter to use to get it back to the original type
- A TypedId as primary key of base models, see `typedid` tag for exploratory implementation
  - Reason for investigating
    - Reference a row by a single value, rather than Model+id
    - could simplify delete/update/get api
    - could make fetching a relationship row simpler
      Honors: minimize boilerplate
  - How
    - return TypedId replaced during insert
    - Add adapters for TypedId -> int (only need one, because we are losing the type info)
    - Add converters for int -> TypedId (need one for each model/table, as we need to add the type info)
      - One problem here was that you needed use "parse column names" to make the convert recognized.
        this means there are two different return types to the query, one when you do the converter name in column hint way:
        `select id as "id [TypedId_MyModel]"`
        and the normal way:
        `select id, name`
        This to me could causes surprises, and also makes types lie if you do a manual query and "forget" to add the type info.
        It also just makes all the queries noisy to look at.
        violates
          - minimize boilerplate
          - minimize library specific knowledge requirements
          - actually simple vs seemingly simple
          - principle of least surprise
  - Why Not?
    - The typed ID is just another thing to know, and understand for users
      - violates actually simple vs seemingly simple
      - violates minimize library specific knowledge requirements
    - The supposed benefit of simpler delete api actually hurts readability.
      ```python
      engine.delete(some_id)
      ```
      is less clear than
      ```python
      engine.delete(MyModel, some_id)
      ```
      and we already have an overload for deleting a row
      ```python
      engine.delete(row)
      ```
      This violates choose boilerplate over magic
    - It is annoying that you have to repeat the Model name in the Model def:
      ```python
      class MyModel(NamedTuple):
          id: Id[MyModel]
          name: str
          date: dt.datetime
      ```
      Violates minimize boilerplate
- Add passthrough for commit? e.g. engine.commit
  - just let the user use the existing connection, engine.connection.commit()?
  - Violates, only do what can't be done with the sqlite standard library
- Allow str serde, i.e. in addtion to the bytes api
  - just explicitly encode/decode to bytes
  - Violates choose boilerplate over magic
- Query builder on engine
  - just use the query builder directly
  - Violates choose boilerplate over magic
  - better to use Model, sql, params as a stable and interoperable intermediate representation

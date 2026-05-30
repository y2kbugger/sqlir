# WIP

# Bugs


# Testing
- e.find without target predicate specified. allow/disallow?
- Test delete by id (no match) and update id (no match)?
- Test that basic engine crud operation emit only the expected statements, e.g. no select before update, etc. DO FOR ALL Engine OPERATIONS
- test `Any` type on Row/TableRow models. Ban? Allow?
- test that you can add extra defs to a model without things blowing up (or add eager enforcement that you can't do this)
- test that you can register a model with an FK that doesn exitst yet. Also test failure to actually evetually define it
- Test case that you cannot subclass a tablemodel, e.g.
    ```python
    class BaseModel(TableRow):
        name: str

    class SubModel(BaseModel):  # should raise
        boogie: int
    ```
- test types msgspec cannot encode raise at write time — confirm error message is clear and actionable
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
- benchmark model creation, field access, hashing, and memory footprint vs plain NamedTuple and dataclass baselines,
    - maybe resurect some of the old benchmarks for this.
- ensure that ID fields are always stored as integer affinity. i really think there are some landmines with tables having "text" in the the name. maybe all id columns should just be INT now that we do adapt/convert without relying on sql column types.
- Can a modeul use dataclass feature like "field"? should we make a custom one?
- Test that Row models DO NOT have __table_name__
    - Also why does find, and select etc, allow `Row` models currently? Once we do the `__select_query__` feature this makes more sense, but i don't think it could work right now.

## testingmeta
- I want to instrument sqlite to log and profile queries.
- use the assert_type from typing to check type hints
  - Test types on engine.find/select
- fix names / order of model_test.py, e.g. test_table_meta_... -> test_get_meta__....
- automate a benchmark suite that outputs one large markdown results file, including all context needed to interpret the numbers

# Next
- UUID should be supported natively without JSON quoting as root type (like date, Decimal, etc) so db can use it directly
- make rel template strings easily print as their resolved SQL for debugging
- migration interactive restore list too long. can you page restores or head results?
- Allow order on find?
 - row = e.select(ImportMeta, order="imported_at DESC", limit=1).fetchone()

## Row Model `__select_query__` for Arbitrary Queries
Define the query with the Row model, since they don't have a table.
They are always positionally mapped, so you can let columns be named anything.


```python
class TableInfo(Row):
    cid: int
    name: str
    type: str
    notnull: int
    dflt_value: Any
    pk: int

    __select_query__ = f"PRAGMA table_info({Athlete.__name__})"

engine.select(TableInfo)
```

It could also handle aggregations, e.g. total power by character name
```python
class Character_TotalPower(Row):
    id: int
    name: str
    total_power: float

    __select_query__ = f"""
        SELECT {Character.id}, {Character.name}, sum({Character.stats} -> '$.power') as total_power
        FROM {Character}
        GROUP BY {Character.name}
        """
engine.select(Character_TotalPower)
```

This would also cover many wacky query scenarios in addition to aggregations and simple plucking: it would allow custom joins, json manipulation, sqlite propreitary functions. UNION ... UNION ... monstrosities. and all you need to do is define the model. I suggest a field name __select_query__ or something like that to make it clear that this is a full query and not just a predicate. This can also be made to work with order and limit fields on e.find/e.select via subquery wrapping.

This could be the ultimate escape hatch, it might actually even remove need for e.query?? since like what is a query without a return model, it can even be done right now you always have to make the model anyway. With LLMs i think it is better to just drop to SQL earlier than later, and make it easy to do so, and clear about the return types.



## Backpop
- ONCE FINISHED, un-skip the fanout prevention test, and make sure it actually works.
- Also considder one to one relationships that backpop to a single instance rather than a list
- set[M] vs list[M] vs BackPop[M] as typehint?
- backpop
  ```python
  class Team(TableRow):
      name: str
      teams: list[Person] # Backpop

  class Person(TableRow):
      name: str
      team: Team # Forward
  ```

  Need a way to differentiate between two different backpop of same type
  - backprop must include the full name of the forward reference as the prefix of it's name
  - if this is not specified or not unique, raise an `AmbiguousBackpopError`
  - not FK is allowed to be a subset of another FK on the same model. `AmbiguousForwardReferenceError`
  ```python
  # Ex 1. disambiguating backpop
  class Team(TableRow):
      name: str
      primary_teams: list[Person]
      secondary_teams: list[Person]

  class Person(TableRow):
      name: str
      primary_team: Team
      secondary_team: Team

  # Ex 2. disambiguating backpop
  class Employee(TableRow):
      name: str
      manager_of: List[Project]
      lead_developer_of: List[Project]
      lead_maintainer_of: List[Project]

  class Project(TableRow):
      name: str
      manager: Employee
      lead_developer: Employee
      lead_maintainer: Employee
      lead: Employee # not allowed, because it is an ambiguous subset of lead_developer
  ```

  - Backpop without a forward reference, should just be `AmbiguousBackpopError` because it is ambiguous if you cannot find a forward reference that is a complete prefixed subset of the backpop name.
    ```python
    class Team(TableRow):
        name: str
        teams: list[Person]
    class Person(TableRow):
        name: str
    ```
  - Many-to-Many shall just fall out of two 1:1, is not really a concept
  - Here is a test case with complex relations
  try and figure out if this is ambiguous or not
  ```python
  class Employee(TableRow):
      name: str
      manager_of: List[Project]
      lead_developer_of: List[Project]
      contributor_roles: List[ProjectEmployee]

  class Project(TableRow):
      name: str
      manager: Employee
      lead_developer: Employee
      contributors: List[ProjectEmployee]

  class ProjectEmployee(TableRow):
      project: Project
      employee: Employee
      role: str
  ```


# Later
- Fix up example.ipynb to better structure relation and predicate separate from concept of `engine.select` and the `engine.query` escape hatch.
- harmonize name rel, relation, pred and predicate in code and docs.
- exprs in update values???
- template string support for full queries, not just predicates? e.g. t'{MyModel:SELECT_FROM} WHERE {MyModel.field} = 1'
    - what about plucky or aggregation queries?
    - how to specify types when getting plucky. righ now this is all solved by just making a Row model. JUST forcing make a model leaves LESS things to remember. this seems like a will not implement.
    - This should come after the `__select_query__` feature, which will end up leveraging this.
- fix typing for rel combos like: `winners_today = t"date({MyModel.date}) == date('now')" & (MyModel.score > 99.95)  # ty:ignore[unsupported-operator]`
- Find and remove unused exceptions


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
- support sql column defs with default values, e.g. `name: str = "default name"` and then have that be the default value for the column in the create table statement, and also have it be the default value for the field when creating a new instance of the model without specifying that field.
    - maybe we already have this via field
- Auto detect or provide a way to santize/escape LIKE params. e.g.  of % or _
- engine.exists (rails has relation.exists, e.g. Customer.where(first_name: "Ryan").exist
- scalar accessors, e.g. RoR AR's pick. get one value from one row and one. note: this is already built into apsw, engine.get
- RoR annotate (and sql comments so that later we can use it during observabilites)
- Ror-like scopes???
- FinalizedModel: disable lazy loading of fields, etc. e.g. guarantee immutability before passing to template etc. (needs better name i think)


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
class XXX(TableRow):
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


## JSONB format
We will default to TEXT for simplicity and forward compat.
JSONB[T] would be a custom type that uses the json1 extension to store the data in a binary format, which is more efficient for large JSON objects and allows for indexing. e.g. it would be opt-in
## pickling type
make a type annotation like `Pickle[MyType]` that would automatically pickle and unpickle the field, and raise if it fails to pickle or unpickle. This fills a gap left by the expunging of custom adapt/convert pairs.


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
    move this to a benchmark script:
    ```python
    def insert_all[R: Row](self, Model: type[R], rows: Iterable[R]) -> None:
        """Insert multiple rows at once."""
        insert = get_meta(Model).insert
        assert insert is not None, "Insert statement should be defined for the model."
        with self.connection:
            self.connection.executemany(insert, rows)
    ```

## Cython implementation for faster model, must benchmark and actually know

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

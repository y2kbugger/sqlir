# API Overhaul

**Model (M)**
Typed record definition.

```python
class User(Model):
    id: int
    name: str
    age: int
    manager: User | None
```

**Relation (R)**
Predicate expression built from model fields. Traversal across relations is expressed with field chaining and implemented as **semi-joins**.

```python
User.name == "Jon"
User.manager.name == "Paul"
(User.name == "Jon") | (User.manager.name == "Paul")
```

Typed ID relations.

```python
User.Id(10)
user.id
```

## Engine API

```python
class Engine:
    def insert(self, obj: M) -> M: ...
    def find(self, target: R, /, *, order=None) -> M | None: ...
    def select(self, target: R, /, *, order=None, limit=None, offset=None) -> list[M]: ...
    def update(self, target: R, /, **patch) -> int: ...
    def delete(self, target: R, /) -> int: ...
```

Please edit model.py so that the relations are possible to get wth good static typing also. play around with the minimal viable example (basically shown above) in a rel_play.py i wanna see not that it can generate sql, but at least it stores the metadata of each relation expr.


# Other thoughts on the API
__how to make query.select more integrated to Engine so its more like find__
SEE API2.md for more thoughts on this
- integrate fetchall into e.select, so you can do `engine.select(Model)` instead of `engine.query(*select(Model)).fetchall()`
- make save only do inserts. rename insert?
- consider collapse find and find_by into one method, e.g. `engine.find(Model, id)` and `engine.find(Model, name="Bart")` , but then we stray from AR

- Think about asymmetry between getting a cursor proxy from query vs getting collection from foreign key relationships
    - how often do we need to control fetchall vs fetchmany.
    - what about leveraging get?
    - what about fetch one only?
    - Also consider the error of leaving cursor unfinalized.
- is delete_all good?
- think about mutable immediate vs immutable explicit and ergonomics in example.
- Delete idempot? no raise?
- update(instance, colum="value) api creates  an abiguity (if records are mutable) basically right now it ignores mutations to the instance and only updates the fields in the kwargs.
    - Lazy Immuatable Records would fix this.
    - Also consider typed ID's again. This would fix up the api nicely, especially if tied into FastAPI path params to deliver the correct type to the endpoint, and then just pass that to the delete/update method.
        - This would also let us eliminate the overloaded delete and update methods completed and just require an explicit model_instance.id to be passed.
    - then we can use that exact where clause in select, update, and delete
    - attempt to overload these in a way feels natural, e.g. find returns one, select returns many, update and delete can work either by id or by where clause.
- Also allow an fstring for the where clause, e.g. `engine.find(MyModel, t"{MyModel.name} = 'Bart'")`??

## other other
- find_by arbitraqt sql predicates, e.g. `engine.find_by(MyModel, f"{MyModel.name} = 'Bart'")`

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
|   | Find one by fields                     | `engine.find_by(Post, name="Hi")`                                   | `Model.find_by(name: "Hi")`                                      |
|   | Find one (raw SQL)                     | `engine.find_by(Post, sql, params)`                                 | `Post.find_by_sql(sql).take/first`                               |
| * | Find one or Create                     | ?                                                                   | `Post.find_or_create_by(a: 1, b: 2)`                             |
|   | _many_                                 |                                                                     |                                                                  |
|   | Select all                             | `engine.select(Post)`                                               | `Post.all`                                                       |
|   | Select by field(s)                     | `engine.select(Post, name="Hi")`                                    | `Post.where(name: "Hi").all`                                     |
|   | Select query builder                   | `@select(Post)...f"WHERE...ORDER BY..."`                            | `Post.where(...).order(...)`                                     |
|   | Raw SQL                                | `engine.query(Model, sql)`                                          | `Model.find_by_sql(sql)`                                         |
|   | Aggregations                           | raw SQL/View with `Row` models (views+migrate works well)           | `Model.group(...).sum(...)`                                      |
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

## Static Typing Strategies for Relational Queries

Under the new unified `target: Expr` engine API, the `Engine.find()` and `Engine.select()` methods lose static typing context because they receive generic expressions (`Any` or `Expr`), resulting in an `Any` return type. Here is a summary of the options to restore precise static typing given Python's generic typing constraints:


## API comparison docs
- take
- pluck
- exists
- insert many?

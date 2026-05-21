### API Overhaul

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

### Engine API

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

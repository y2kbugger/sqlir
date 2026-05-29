# AUTO-GENERATED — DO NOT EDIT. Regenerate with: python scripts/sync_plugin.py
# Source: example.ipynb

# %%
from __future__ import annotations
import datetime as dt
from random import random
import sys

import apsw

from tuplesaver.engine import Engine
from tuplesaver.model import Row, TableRow

# %% [markdown]
# # Models

# %%
class MyModel(TableRow):
    name: str
    date: dt.datetime
    score: float

# %% [markdown]
# Connect to the database and create tables with an `Engine`

# %%
engine = Engine(apsw.Connection(":memory:"))
# engine = Engine(apsw.Connection("example.db"))
engine.ensure_table_created(MyModel)
engine.connection # just the real apsw connection object

# %%
def trace_sql_in_color(cursor, sql, params):
    print(f"\033[94m{sql}\033[0m")
    if params:
        # Get the !r (repr) of each param value individually
        if isinstance(params, dict):
            print(*(f"\033[1;96m{k}: {v!r}\033[0m" for k, v in params.items()), sep=", ")
        else:
            print(*(f"\033[1;96m{p!r}\033[0m" for p in params), sep=", ")
        print()  # Newline after printing all params
    return True

engine.connection.exec_trace = trace_sql_in_color

# %% [markdown]
# # Basic CRUD

# %% [markdown]
# ## Insert row

# %%
row =engine.insert(MyModel("Bart", dt.datetime.now(), 6.5))
row

# %% [markdown]
# ## Find row by id

# %%
engine.find(MyModel, row.id)

# %% [markdown]
# ## Find row by Expr

# %%
engine.find(MyModel, MyModel.name == "Bart")

# %% [markdown]
# ## Select rows

# %%
engine.select(MyModel, MyModel.score > 99.95)

# %% [markdown]
# ## Update rows

# %%
engine.update(MyModel, t"{MyModel.name} LIKE 'B%'" and MyModel.score < 1, score=99.9)

# %% [markdown]
# ## Delete rows

# %%
engine.delete(MyModel, row.id)

# %% [markdown]
# # Foreign Keys Relationships
# Models can be related by using a model as a field type in another model.

# %%
class Band(TableRow):
    name: str
    active: bool

class BandMember(TableRow):
    band: Band
    name: str
    instrument: str

engine.ensure_table_created(Band)
engine.ensure_table_created(BandMember)

# %% [markdown]
# You can save a model and then use it as a related field in another model.

# %%
devo = engine.insert(Band("Devo", True))
mark = engine.insert(BandMember(devo, "Mark Mothersbaugh", "Keyboards"))

# %% [markdown]
# ## Lazy loading
# FK related models are lazy loaded by default.

# %%
singer = engine.find(BandMember, mark.id)

print(singer.name)
print(singer.band.name) # `band` field gets lazy loaded

# %% [markdown]
# Dummy data for later, also demonstrates multi-level relationships.

# %%
class League(TableRow):
    leaguename: str

class Team(TableRow):
    teamname: str
    league: League

class Athlete(TableRow):
    name: str
    team: Team


engine.ensure_table_created(League)
engine.ensure_table_created(Team)
engine.ensure_table_created(Athlete)

with engine.connection:  # transaction
    # Insert dummy data
    leagues = [
        engine.insert(League("Big")),
        engine.insert(League("Small")),
        ]
    teams = [
        engine.insert(Team("Red", leagues[0])),
        engine.insert(Team("Ramble", leagues[1])),
        engine.insert(Team("Blue", leagues[0])),
        engine.insert(Team("Green", leagues[1])),
        ]
    players = [
        alice:=engine.insert(Athlete("Alice", teams[0])),
        engine.insert(Athlete("Bob", teams[0])),
        engine.insert(Athlete("Charlie", teams[1])),
        engine.insert(Athlete("Dave", teams[2])),
        engine.insert(Athlete("Beth", teams[3])),
        engine.insert(Athlete("Frank", teams[2])),
    ]

# %%
athlete = engine.find(Athlete, Athlete.name == "Alice")
athlete.team.league.leaguename # multi-step lazy loading

# %% [markdown]
# # Querying

# %% [markdown]
# `engine.query` is the raw-SQL escape hatch. Pass a SQL string and (optionally) parameters; it returns a typed cursor over the rows materialized as the given model.
#
# ```python
# engine.query(Model, sql, params)
# ```
#
# For model-relation-based filtering, use `engine.select` / `engine.find` instead — they generate the SQL for you.

# %%
# insert some data since we deleted all MyModels earlier
engine.insert(MyModel("Milhouse", dt.datetime.now(), 2.0))
engine.insert(MyModel("Maggie", dt.datetime.now(), 10.0))


class AverageScoreResults(Row):
    avg_score: float
    scorecount: int

sql = 'SELECT avg(score), count(*) FROM MyModel'

result = engine.query(AverageScoreResults, sql).fetchone()
assert result is not None

print(f'The table has {result.scorecount} rows, with an average of {result.avg_score:0.2f}')

# %% [markdown]
# `engine.select` is a simple yet powerful way to retrieve Models from the database. It returns a typed cursor, which you can iterate (`for row in engine.select(...)`) for streaming, or materialize all at once with `.fetchall()`.
#
# The most simple case selects all rows from a table.
#

# %%
for player in engine.select(Athlete):
    print(player.name)

# %% [markdown]
# You can use Model relation expressions to add `WHERE` clauses.

# %%
for player in engine.select(Athlete, Athlete.name == 'Beth'):
    print(player.name)

# %% [markdown]
# Queries spanning across relations are automatically generated using `EXISTS` semi-joins safely to prevent fanout.

# %%
for player in engine.select(Athlete, Athlete.team.teamname == 'Red'):
    print(player.name)

for player in engine.select(Athlete, Athlete.team.league.leaguename == 'Big'):
    print(player.name)

# %% [markdown]
# You can also pass t-string based expressions for more complex predicates.

# %%
for player in engine.select(Athlete, t'{Athlete.team.league.leaguename} LIKE "B%"'):
    print(player.name)

# %% [markdown]
# ## Complex predicates with t-strings
#
# t-string predicates can interpolate **model classes** (splice to table name),
# **field paths** (splice to qualified column / scalar subquery), and **plain
# values** (parameter-bound). That makes even non-trivial correlated / scalar
# subqueries refactor-friendly — rename a model or a field and every reference
# inside the t-string moves with it.

# %%
# Find every MyModel row whose score is within .05% of the table wide maximum.
# Three kinds of interpolation in one t-string:
#   {MyModel}         -> "MyModel"           (table name)
#   {MyModel.score}   -> "MyModel.score"     (qualified column)
#   {min_score}       -> :p0                 (bound parameter)

tolerance = 1 - 0.0005

top_scorers = t"""
    {MyModel.score} >= (
        SELECT MAX({MyModel.score}) * {tolerance}
        FROM {MyModel}
        )
"""

for r in engine.select(MyModel, top_scorers):
    print(f"{r.name:10s} {r.score:6.2f}  {r.date:%Y-%m-%d %H:%M:%S}")

# %% [markdown]
# you can also override the named params

# %%
for r in engine.select(MyModel, top_scorers, {'tolerance': .0002}):
    print(f"{r.name:10s} {r.score:6.2f}  {r.date:%Y-%m-%d %H:%M:%S}")

# %% [markdown]
# ## Querys requiring backrefs
#
# Eventually we will support backrefs:
#
# ```python
# class League(Row):
#     id: int | None
#     leaguename: str
#     teams: BackRef[Team] # backref will be something like this
# ```
#
# And then you could do:
#
# ```python
# engine.select(League, League.teams.teamname == "Big")
# ```
#
# For now just fallback to raw queries:

# %%
sql = """
SELECT * FROM League
JOIN Team ON Team.league = League.id
WHERE Team.teamname = 'Big'
"""

engine.query(League, sql).fetchone()

# %% [markdown]
# ## Ad-hoc models and the `Any` type
# Models can also be completely ad-hoc, instead of `TableRow`, they are merely `Row`. These models do not have an `id` field. They also have a special field type available, `Any`, which can be used to represent any type of data. This is particularly useful for dynamic or polymorphic data structures where the exact type may not be known until runtime.

# %%
from typing import Any

class TableInfo(Row):
    cid: int
    name: str
    type: str
    notnull: int
    dflt_value: Any # `Any` will return raw value matching python's bare sqlite3, without conversion
    pk: int

sql = f"PRAGMA table_info({Athlete.__name__})"

cols = engine.query(TableInfo, sql).fetchall()
for col in cols:
    print(f"{col.cid:2d} {col.name:10s} {col.type:10s} {str(col.dflt_value or 'None'):10s}")

# %% [markdown]
# ## SQLite3 Cursor
# Both `engine.query` and `engine.select` return a `TypedCursorProxy[M]` — a real `apsw.Cursor` with model-aware row materialization. Iterate it to stream, or call `fetchone` / `fetchall` / `fetchmany` as needed.

# %%
row = engine.select(Athlete).fetchone()

# %% [markdown]
# # Persisting Native and Advanced Python Types
# TupleSaver supports a wide variety of standard python types and automatically maps them to SQLite storage. For example, `datetime`, `date`, and `time`, and `Decimal`, `Enum` objects are seamlessly stored as TEXT (ISO-8601) giving them support for SQLite's native date functions. Buffer protocols (`bytes`, `bytearray`, `memoryview`) are automatically adapted to BLOBs.
#
# Additionally, data structures and objects that can be serialized by `msgspec` are natively supported as fallback JSON columns. This includes `list`, `dict`, `set`, `tuple`, `dataclass`, `UUID`, etc.

# %%
from enum import Enum
import datetime as dt
from decimal import Decimal
from dataclasses import dataclass

class ColorEnum(str, Enum):
    RED = "red"
    BLUE = "blue"

class StyleEnum(int, Enum):
    BOLD = 1
    ITALIC = 2
    UNDERLINE = 3

from typing import TypedDict

class SourceVerTD(TypedDict):
    source: str
    version: int

@dataclass
class LocationDC:
    lat: float
    lng: float


class AdvancedTypesModel(TableRow):
    # Native
    score: float

    # Datetimes
    created_at: dt.datetime
    precision_value: Decimal

    # Buffers
    raw_data: bytes

    # JSON fallbacks
    tags: set[str]
    metadata: dict
    source_ver: SourceVerTD
    new_style: StyleEnum
    favorite_color: ColorEnum
    colors: list[ColorEnum]
    location: LocationDC

engine.ensure_table_created(AdvancedTypesModel)

row = engine.insert(AdvancedTypesModel(
    score=42.5,
    created_at=dt.datetime(2024, 6, 15, 12, 0, 0, tzinfo=dt.UTC),
    precision_value=Decimal("123.456"),
    raw_data=b"hello_world",
    tags={"urgent", "new"},
    metadata={"kind": "demo", "featured": True},
    source_ver={"source": "api", "version": 1},
    new_style=StyleEnum.BOLD,
    favorite_color=ColorEnum.RED,
    colors=[ColorEnum.RED, ColorEnum.BLUE],
    location=LocationDC(lat=40.7128, lng=-74.0060),
))

fetched = engine.find(AdvancedTypesModel, row.id)
fetched

# %% [markdown]
# ## SQLite3 supports JSON extensions

# %%
from typing import TypedDict

class Stats(TypedDict):
    spell: str
    level: int

class Character(TableRow):
    name: str
    stats: Stats # JSON field

engine.ensure_table_created(Character)

engine.insert(Character('Harbel', {'spell': 'Fireball', 'level': 3}))
engine.insert(Character('Quenswen', {'spell': 'Waterspout', 'level': 27}))
engine.insert(Character('Ruthbag', {'spell': 'Fireball', 'level': 12}))

for c in engine.select(Character, t"{Character.stats} ->> '$.spell' = 'Fireball'"):
    print(f"{c.name} has a fireball at level {c.stats['level']}")

# %% [markdown]
# # Performance scenarios
# Every call to insert real full trip to the db. The data is ready to be queried immediately, in SQLAlchemy parlance, 'flushed'. Committig ends the implicit transaction and ensures that the data is persisted to disk. Data is then avialable to other connections e.g. other worker processes
#
# Because the db and app share a process, the performance is good enough that you can basically ignore the N+1 problem. This also simplifies implementation of this library, no need to track session etc. It also simplifies your app as data is syncronized immediately with the database, thus eliminates the need for a stateful cache, a source off many bugs and complexity.

# %%
engine.connection.exec_trace = None # disable echo SQL

# %% [markdown]
# ## Insert many (17,000 rows)

# %%
rows = [MyModel("foo", dt.datetime.now(), random()*100) for _ in range(17000)]

# %%
with engine.connection:  # transaction
    for r in rows:
        engine.insert(r)

# %% [markdown]
# ## Update many (17,000 rows)

# %%
updates = [{'id': row.id, 'score': random()*100, 'date': dt.datetime.now()} for row in rows]

# %%
with engine.connection:  # transaction
    for u in updates:
        engine.update(MyModel, u['id'], date=u['date'], score=u['score'])

# %% [markdown]
# ## Query many

# %%
def print_30_per_line(ss):
    for i, s in enumerate(ss, 1):
        print(s, end=" ")
        if i % 30 == 0:
            print()
    print()

# select returns a cursor; iterate it directly to stream rows without
# materializing them all into a list.
rows = engine.select(MyModel, MyModel.score > 95.7)
print_30_per_line(f"{r.score:5.1f}" for r in rows)

# %% [markdown]
# ## Giant Recursive BOM

# %%
class BOM(TableRow):
    name: str
    value: float
    child_a: BOM | None
    child_b: BOM | None

engine.ensure_table_created(BOM)

from random import random, choice
node_count = 0
def generate_node_name_node(depth: int) -> str:
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    return f"{choice(alphabet)}{choice(alphabet)}{choice(alphabet)}{depth:05d}_{node_count}"


# create a giant BOM, of 15 levels deep
def create_bom(depth: int) -> BOM:
    global node_count
    node_count += 1

    if depth == 1:
        child_a = None
        child_b = None
    else:
        child_a = create_bom(depth-1)
        child_b = create_bom(depth-1)

    return BOM(generate_node_name_node(depth), random()*1000 - 500, child_a, child_b)

root = create_bom(13)
print(f"Created a BOM with {node_count} nodes")

# %%
from dataclasses import replace

def save_bom_recursive(node: BOM) -> BOM:
    """Save BOM tree leaf-first (children must be saved before parents)."""
    return engine.insert(replace(
        node,
        child_a=save_bom_recursive(node.child_a) if node.child_a else None,
        child_b=save_bom_recursive(node.child_b) if node.child_b else None
    ))

with engine.connection:  # transaction
    inserted_root = save_bom_recursive(root)

print(f"Inserted BOM with id: {inserted_root.id}")

# %%
recovered_root = engine.find(BOM, inserted_root.id)
assert recovered_root is not None

def count_nodes(node: BOM | None) -> int:
    if node is None:
        return 0
    return 1 + count_nodes(node.child_a) + count_nodes(node.child_b)

# counting the node lazily traverses the whole tree, one query at a time
print(f"Recovered BOM with {count_nodes(recovered_root)} nodes")

# %%
import math

import matplotlib.pyplot as plt
import networkx as nx

def add_nodes_edges(G: nx.Graph, node: BOM | None):
    if node is None:
        return

    G.add_node(node.id, label=node.name)
    if node.child_a is not None:
        G.add_edge(node.id, node.child_a.id)
        add_nodes_edges(G, node.child_a)

    if node.child_b is not None:
        G.add_edge(node.id, node.child_b.id)
        add_nodes_edges(G, node.child_b)

def hierarchical_tree_layout(G, root_node):
    pos = {}

    # Build adjacency list from the graph
    adj = {node: list(G.neighbors(node)) for node in G.nodes()}

    # BFS to determine levels and children
    from collections import deque
    queue = deque([(root_node, 0)])
    visited = {root_node}
    levels = {}
    children = {node: [] for node in G.nodes()}

    while queue:
        node, level = queue.popleft()
        levels[node] = level

        for neighbor in adj[node]:
            if neighbor not in visited:
                visited.add(neighbor)
                children[node].append(neighbor)
                queue.append((neighbor, level + 1))

    # Position nodes level by level
    def position_subtree(node, level, angle_start, angle_end):
        # Position current node
        if level == 0:
            pos[node] = (0, 0)  # Root at center
        else:
            angle = (angle_start + angle_end)
            radius = level * 0.8  # Increase radius per level
            x = radius * math.cos(angle)
            y = radius * math.sin(angle)
            pos[node] = (x, y)

        # Position children
        kids = children[node]
        if kids:
            angle_span = min(angle_end - angle_start, 2 * math.pi / max(1, len(kids)))
            angle_per_child = angle_span / len(kids)

            for i, child in enumerate(kids):
                child_angle_start = angle_start + i * angle_per_child
                child_angle_end = child_angle_start + angle_per_child
                position_subtree(child, level + 1, child_angle_start, child_angle_end)

    # Start positioning from root
    position_subtree(root_node, 0, 0, 2 * math.pi)
    return pos


G = nx.Graph()
add_nodes_edges(G, recovered_root)

plt.figure(figsize=(10, 10))
nx.draw(G, hierarchical_tree_layout(G, recovered_root.id),
    node_size=6, width=0.2, node_color="blue",
    with_labels=node_count<1200,
    labels=nx.get_node_attributes(G, "label"),
    )
plt.show()

# %% [markdown]
# # Model Class
# The model class itself hold info about the table/model/types/etc
#
# See `tuplesaver/model.py` and `RowMeta` for more details.

# %%
Team.__fields__ # just one of a handfule of attrs defined on the model class, populated during compilation.

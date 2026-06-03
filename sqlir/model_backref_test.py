"""Backref (reverse relationship) declaration, navigation, and predicates.

A backref is declared with the `backref()` field specifier and either a typed
forward-FK reference (e.g. `backref(fk=Player.squad)`) or the equivalent
fully-qualified string (`backref(fk="Player.squad")`). It is a *virtual*
field: it backs no column and never appears in SQL. `list[Child]` is has_many;
a scalar `Child` is has_one.
"""

from textwrap import dedent

import pytest

from .engine import Engine
from .lazy import Rows
from .model import (
    BackrefCardinalityMismatch,
    BackrefFkMismatch,
    BackrefFkNotFieldReference,
    TableRow,
    backref,
)
from .sql import build_create_table_sql, build_insert_sql, build_select_sql

# --- has_many / has_one (the typed `fk=Child.parent` form resolves eagerly,
# so these examples stay child-first) ---


class Player(TableRow):
    name: str
    squad: Squad
    number: int


class Squad(TableRow):
    name: str
    players: Rows[Player] = backref(fk=Player.squad)


class Passport(TableRow):
    code: str
    holder: Citizen


class Citizen(TableRow):
    name: str
    passport: Passport = backref(fk=Passport.holder)


# --- multiple FKs to the same parent, disambiguated by the explicit fk= ---


class Game(TableRow):
    home: Club
    away: Club


class Club(TableRow):
    name: str
    home_games: Rows[Game] = backref(fk=Game.home)
    away_games: Rows[Game] = backref(fk=Game.away)


# --- many-to-many through an explicit join model ---


class Enrollment(TableRow):
    student: Student
    course: Course
    grade: str


class Student(TableRow):
    name: str
    enrollments: Rows[Enrollment] = backref(fk=Enrollment.student)


class Course(TableRow):
    title: str
    enrollments: Rows[Enrollment] = backref(fk=Enrollment.course)


# --- string fk form (can be used generally; here it also allows parent-first
# declaration because the child model is resolved later) ---


class StringSquad(TableRow):
    name: str
    players: Rows[StringPlayer] = backref(fk="StringPlayer.squad")


class StringPlayer(TableRow):
    name: str
    squad: StringSquad
    number: int


# --- self-referential; the same string form also covers the in-class self ref ---


class Node(TableRow):
    name: str
    parent: Node | None
    children: Rows[Node] = backref(fk="Node.parent")


# Negative string-fk cases (module-level so the forward ref resolves; errors
# still surface lazily at first `__fields__` access).


class BareStringNode(TableRow):
    name: str
    parent: BareStringNode | None
    children: Rows[BareStringNode] = backref(fk="parent")  # bare field name, not "Model.field"


class WrongModelNode(TableRow):
    name: str
    parent: WrongModelNode | None
    children: Rows[WrongModelNode] = backref(fk="Node.parent")  # names a different model


def dd(sql: str) -> str:
    return dedent(sql).strip()


# ---------------------------------------------------------------------------
# Virtual-field invariants
# ---------------------------------------------------------------------------


def test_backref_field_is_virtual() -> None:
    assert [f.name for f in Squad.__fields__] == ["id", "name"]
    assert "players" not in {f.name for f in Squad.__fields__}
    assert Squad.__refs_by_name__["players"].is_back


def test_backref_absent_from_ddl_and_insert() -> None:
    assert "players" not in build_create_table_sql(Squad)
    assert "players" not in build_insert_sql(Squad)


def test_backref_relation_metadata() -> None:
    rel = Squad.__refs_by_name__["players"]
    assert rel.name == "players"
    assert rel.target is Player
    assert rel.far_col == "squad"
    assert rel.is_back is True
    assert rel.is_collection is True

    assert Citizen.__refs_by_name__["passport"].is_collection is False


# ---------------------------------------------------------------------------
# Navigation
# ---------------------------------------------------------------------------


def test_has_many_navigation_returns_materialized_list(engine: Engine) -> None:
    engine.ensure_table_created(Squad)
    engine.ensure_table_created(Player)

    squad = engine.insert(Squad(name="Reds"))
    engine.insert(Player(name="Alice", squad=squad, number=1))
    engine.insert(Player(name="Bob", squad=squad, number=2))

    members = squad.players
    assert isinstance(members, Rows)
    assert {p.name for p in members} == {"Alice", "Bob"}


def test_has_many_navigation_caches(engine: Engine) -> None:
    engine.ensure_table_created(Squad)
    engine.ensure_table_created(Player)

    squad = engine.insert(Squad(name="Reds"))
    engine.insert(Player(name="Alice", squad=squad, number=1))

    assert squad.players is squad.players  # materialized once, cached


def test_has_one_navigation_returns_single_or_none(engine: Engine) -> None:
    engine.ensure_table_created(Citizen)
    engine.ensure_table_created(Passport)

    bob = engine.insert(Citizen(name="Bob"))
    engine.insert(Passport(code="X1", holder=bob))
    assert bob.passport is not None
    assert bob.passport.code == "X1"

    nodoc = engine.insert(Citizen(name="NoDoc"))
    assert nodoc.passport is None


def test_backref_on_unsaved_parent_is_empty() -> None:
    assert Squad(name="ghost").players == Rows()  # has_many -> empty Rows
    assert Citizen(name="ghost").passport is None  # has_one -> None


def test_repr_does_not_recurse_through_backref(engine: Engine) -> None:
    # A backref closes a parent->children->parent cycle; including it in the
    # dataclass repr would recurse forever. Backref fields are repr=False.
    engine.ensure_table_created(Squad)
    engine.ensure_table_created(Player)

    squad = engine.insert(Squad(name="Reds"))
    engine.insert(Player(name="Alice", squad=squad, number=1))

    fetched = engine.find(Squad, squad.id)
    assert repr(fetched) == "Squad(id=1, name='Reds')"  # no `players`, no recursion


def test_multiple_fk_backrefs_stay_separate(engine: Engine) -> None:
    engine.ensure_table_created(Club)
    engine.ensure_table_created(Game)

    a = engine.insert(Club(name="A"))
    b = engine.insert(Club(name="B"))
    engine.insert(Game(home=a, away=b))
    engine.insert(Game(home=b, away=a))

    assert len(a.home_games) == 1
    assert len(a.away_games) == 1


def test_many_to_many_navigation_through_join(engine: Engine) -> None:
    for model in (Student, Course, Enrollment):
        engine.ensure_table_created(model)

    alice = engine.insert(Student(name="Alice"))
    bob = engine.insert(Student(name="Bob"))
    math = engine.insert(Course(title="Math"))
    art = engine.insert(Course(title="Art"))
    engine.insert(Enrollment(student=alice, course=math, grade="A"))
    engine.insert(Enrollment(student=alice, course=art, grade="B"))
    engine.insert(Enrollment(student=bob, course=math, grade="C"))

    assert {e.course.title for e in alice.enrollments} == {"Math", "Art"}


def test_string_fk_can_define_parent_before_child(engine: Engine) -> None:
    engine.ensure_table_created(StringSquad)
    engine.ensure_table_created(StringPlayer)

    squad = engine.insert(StringSquad(name="Reds"))
    engine.insert(StringPlayer(name="Alice", squad=squad, number=1))
    engine.insert(StringPlayer(name="Bob", squad=squad, number=2))

    fetched = engine.find(StringSquad, squad.id)
    assert {player.name for player in fetched.players} == {"Alice", "Bob"}


# ---------------------------------------------------------------------------
# Self-referential string-fk backref
# ---------------------------------------------------------------------------


def test_self_referential_backref_metadata() -> None:
    rel = Node.__refs_by_name__["children"]
    assert rel.name == "children"
    assert rel.target is Node  # the model points back at itself
    assert rel.far_col == "parent"
    assert rel.is_collection is True


def test_self_referential_backref_navigation(engine: Engine) -> None:
    engine.ensure_table_created(Node)

    root = engine.insert(Node(name="root", parent=None))
    engine.insert(Node(name="a", parent=root))
    engine.insert(Node(name="b", parent=root))

    fetched = engine.find(Node, root.id)
    assert {child.name for child in fetched.children} == {"a", "b"}


def test_self_referential_reverse_predicate(engine: Engine) -> None:
    engine.ensure_table_created(Node)

    root = engine.insert(Node(name="root", parent=None))
    leaf = engine.insert(Node(name="leaf", parent=root))
    engine.insert(Node(name="lonely", parent=None))

    # Parents that have a child named "leaf" -> only root.
    parents = engine.select(Node, Node.children[0].name == "leaf").fetchall()
    assert {n.name for n in parents} == {"root"}
    assert leaf.name == "leaf"


# ---------------------------------------------------------------------------
# Predicates (reverse EXISTS — no fan-out)
# ---------------------------------------------------------------------------


def test_reverse_predicate_sql() -> None:
    params: dict[str, object] = {}
    sql = build_select_sql(Squad, Squad.players[0].number == 7, params)

    assert sql == dd("""
        SELECT Squad.id, Squad.name FROM Squad
        WHERE EXISTS (
            SELECT 1 FROM Player players
            WHERE players.squad = Squad.id
            AND players.number = :p0
        )
    """)
    assert params == {"p0": 7}


def test_reverse_predicate_no_fanout(engine: Engine) -> None:
    engine.ensure_table_created(Squad)
    engine.ensure_table_created(Player)

    red = engine.insert(Squad(name="Red"))
    blue = engine.insert(Squad(name="Blue"))
    yellow = engine.insert(Squad(name="Yellow"))

    # Blue has TWO players numbered 7 — a JOIN would fan Blue out twice.
    engine.insert(Player(name="Alice", squad=red, number=1))
    engine.insert(Player(name="Xanadu", squad=blue, number=7))
    engine.insert(Player(name="Yvonne", squad=blue, number=7))
    engine.insert(Player(name="Zak", squad=yellow, number=9))

    squads = engine.select(Squad, Squad.players[0].number == 7).fetchall()
    assert {s.name for s in squads} == {"Blue"}
    assert len(squads) == 1  # Blue appears once despite two matching players


def test_many_to_many_predicate_through_join(engine: Engine) -> None:
    for model in (Student, Course, Enrollment):
        engine.ensure_table_created(model)

    alice = engine.insert(Student(name="Alice"))
    bob = engine.insert(Student(name="Bob"))
    math = engine.insert(Course(title="Math"))
    art = engine.insert(Course(title="Art"))
    engine.insert(Enrollment(student=alice, course=math, grade="A"))
    engine.insert(Enrollment(student=alice, course=art, grade="B"))
    engine.insert(Enrollment(student=bob, course=math, grade="C"))

    # Courses Alice is enrolled in: reverse hop (Course<-Enrollment) then
    # forward hop (Enrollment->Student).
    courses = engine.select(Course, Course.enrollments[0].student.name == "Alice").fetchall()
    assert {c.title for c in courses} == {"Math", "Art"}


# ---------------------------------------------------------------------------
# Declaration validation (errors surface at first use)
# ---------------------------------------------------------------------------


def test_backref_rejects_bare_string_fk() -> None:
    # String fk references must be fully-qualified as "Model.field".
    with pytest.raises(BackrefFkNotFieldReference):
        _ = BareStringNode.__fields__


def test_backref_rejects_mismatched_model_in_string_fk() -> None:
    # The "Model" part of the string must match the annotated child model.
    with pytest.raises(BackrefFkNotFieldReference):
        _ = WrongModelNode.__fields__


def test_backref_fk_must_point_back_at_parent() -> None:
    class Stranger(TableRow):
        name: str
        players: Rows[Player] = backref(fk=Player.squad)  # Player.squad points at Squad, not Stranger

    with pytest.raises(BackrefFkMismatch):
        _ = Stranger.__fields__


def test_backref_cardinality_must_match_child() -> None:
    class BadSquad(TableRow):
        name: str
        players: Rows[Squad] = backref(fk=Player.squad)  # annotated Rows[Squad] but fk child is Player

    with pytest.raises(BackrefCardinalityMismatch):
        _ = BadSquad.__fields__

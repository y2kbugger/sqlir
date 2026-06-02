"""Backref (reverse relationship) declaration, navigation, and predicates.

A backref is declared with the `backref()` field specifier and an explicit,
non-stringly forward-FK reference (e.g. `backref(fk=Player.squad)`). It is a
*virtual* field: it backs no column and never appears in SQL. `list[Child]`
is has_many; a scalar `Child` is has_one.
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

# --- has_many / has_one (define child-first so `fk=Child.parent` resolves) ---


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


def dd(sql: str) -> str:
    return dedent(sql).strip()


# ---------------------------------------------------------------------------
# Virtual-field invariants
# ---------------------------------------------------------------------------


def test_backref_field_is_virtual() -> None:
    assert [f.name for f in Squad.__fields__] == ["id", "name"]
    assert "players" not in {f.name for f in Squad.__fields__}
    assert "players" in Squad.__backref_by_name__


def test_backref_absent_from_ddl_and_insert() -> None:
    assert "players" not in build_create_table_sql(Squad)
    assert "players" not in build_insert_sql(Squad)


def test_backref_relation_metadata() -> None:
    (rel,) = Squad.__backref_by_name__.values()
    assert rel.name == "players"
    assert rel.child_model is Player
    assert rel.fk_name == "squad"
    assert rel.is_many is True

    (one_rel,) = Citizen.__backref_by_name__.values()
    assert one_rel.is_many is False


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


def test_backref_requires_field_reference_not_string() -> None:
    class Stringy(TableRow):
        name: str
        players: Rows[Player] = backref(fk="squad")

    with pytest.raises(BackrefFkNotFieldReference):
        _ = Stringy.__fields__


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

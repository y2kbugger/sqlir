from __future__ import annotations

from dataclasses import replace
from typing import Any, cast

import apsw
import pytest
from pytest_benchmark.fixture import BenchmarkFixture

from .engine import (
    Engine,
    InvalidKwargFieldSpecifiedError,
    NoKwargFieldSpecifiedError,
    RecordNotFoundError,
    UnpersistedRelationshipError,
)
from .model import Row, TableRow


class Team(TableRow):
    name: str
    size: int


class Person(TableRow):
    name: str
    team: Team


class Arm(TableRow):
    length: float
    person: Person


class AdHoc(Row):
    score: float


class SqliteMaster(Row):
    __tablename__ = "sqlite_master"
    type: str
    sql: str
    name: str


def test_engine_connection(engine: Engine) -> None:
    hasattr(engine.connection, "cursor")
    hasattr(engine.connection, "execute")


def test_find__by_id(engine: Engine) -> None:
    engine.ensure_table_created(Team)
    row = Team("Lions", 30)
    row = engine.insert(row)

    retrieved_row = engine.find(Team, row.id)

    assert retrieved_row is not None
    assert retrieved_row == row
    assert type(retrieved_row) is Team


def test_find__benchmark(engine: Engine, benchmark: BenchmarkFixture) -> None:
    engine.ensure_table_created(Team)
    engine.insert(Team("Lions", 30))

    def find():
        engine.find(Team, 1)

    benchmark(find)


def test_find__id_is_none(engine: Engine) -> None:
    engine.ensure_table_created(Team)
    with pytest.raises(RecordNotFoundError):
        engine.find(Team, None)


def test_find__id_no_match(engine: Engine) -> None:
    engine.ensure_table_created(Team)
    with pytest.raises(RecordNotFoundError):
        engine.find(Team, 78787)


def test_find__adhoc_model(engine: Engine) -> None:
    with pytest.raises(apsw.SQLError):
        engine.find(AdHoc, 1)


def test_find_by__field(engine: Engine) -> None:
    engine.ensure_table_created(Team)

    engine.insert(Team("Lions", 30))
    engine.insert(Team("Tigers", 33))

    found = engine.find(Team, Team.name == "Lions")
    assert isinstance(found, Team)

    assert engine.find(Team, Team.name == "Lions") == Team("Lions", 30, id=1)
    assert engine.find(Team, Team.size == 30) == Team("Lions", 30, id=1)
    assert engine.find(Team, Team.name == "Tigers") == Team("Tigers", 33, id=2)
    assert engine.find(Team, Team.size == 33) == Team("Tigers", 33, id=2)


def test_find_by__field_no_match(engine: Engine) -> None:
    engine.ensure_table_created(Team)

    engine.insert(Team("Lions", 30))
    engine.insert(Team("Tigers", 33))

    with pytest.raises(RecordNotFoundError):
        engine.find(Team, Team.name == "Karl")


def test_find_by__fields(engine: Engine) -> None:
    engine.ensure_table_created(Team)
    r1 = engine.insert(Team("Lions", 30))
    r2 = engine.insert(Team("Tigers", 33))
    r3 = engine.insert(Team("Lions", 33))

    assert engine.find(Team, (Team.name == "Lions") & (Team.size == 30)) == r1
    assert engine.find(Team, (Team.name == "Tigers") & (Team.size == 33)) == r2
    assert engine.find(Team, (Team.name == "Lions") & (Team.size == 33)) == r3


def test_find_by__fields_with_no_kwargs(engine: Engine) -> None:
    engine.ensure_table_created(Team)
    with pytest.raises(RecordNotFoundError):
        engine.find(Team, None)


def test_find_by__fields_with_invalid_kwargs(engine: Engine) -> None:
    engine.ensure_table_created(Team)
    with pytest.raises(apsw.SQLError):
        engine.find(Team, Team.doesnt_exist == "test")


def test_find_by__adhoc_model(engine: Engine) -> None:
    engine.ensure_table_created(Team)
    r = engine.find(SqliteMaster, SqliteMaster.type == 'table')
    assert r is not None
    assert r.type == 'table'
    assert r.name == 'Team'


def test_select__returns_all_rows(engine: Engine) -> None:
    engine.ensure_table_created(Team)
    engine.insert(Team("Lions", 30))
    engine.insert(Team("Tigers", 33))
    engine.insert(Team("Bears", 25))

    rows = engine.select(Team)

    assert len(rows) == 3
    assert all(isinstance(r, Team) for r in rows)
    assert rows[0] == Team("Lions", 30, id=1)
    assert rows[1] == Team("Tigers", 33, id=2)
    assert rows[2] == Team("Bears", 25, id=3)


def test_select__with_kwargs_filters(engine: Engine) -> None:
    engine.ensure_table_created(Team)
    engine.insert(Team("Lions", 30))
    engine.insert(Team("Tigers", 33))
    engine.insert(Team("Lions", 25))

    rows = engine.select(Team, Team.name == "Lions")

    assert len(rows) == 2
    assert rows[0] == Team("Lions", 30, id=1)
    assert rows[1] == Team("Lions", 25, id=3)


def test_select__with_kwargs_no_match(engine: Engine) -> None:
    engine.ensure_table_created(Team)
    engine.insert(Team("Lions", 30))

    rows = engine.select(Team, Team.name == "Nobody")

    assert rows == []


def test_select__invalid_kwargs(engine: Engine) -> None:
    engine.ensure_table_created(Team)
    with pytest.raises(apsw.SQLError):
        engine.select(Team, Team.doesnt_exist == "test")


def test_select__adhoc_model(engine: Engine) -> None:
    r = engine.select(SqliteMaster, SqliteMaster.type == 'table')
    assert len(r) == 0
    engine.ensure_table_created(Team)
    r = engine.select(SqliteMaster, SqliteMaster.type == 'table')
    assert len(r) == 1
    assert any(row.name == 'Team' for row in r)


def test_query__table_model__succeeds_with_returns_cursor_proxy(engine: Engine) -> None:
    engine.ensure_table_created(Team)
    engine.insert(Team("Lions", 30))

    cur = engine.query(Team, "SELECT * FROM Team;")

    row = cur.fetchone()
    assert isinstance(row, Team)
    assert row == Team("Lions", 30, id=1)


def test_query__adhoc_model__succeeds_with_returns_cursor_proxy(engine: Engine) -> None:
    cur = engine.query(AdHoc, "SELECT 7.7 as score;")

    row = cur.fetchone()
    assert isinstance(row, AdHoc)
    assert row == AdHoc(7.7)


def test_query__datetime_param_is_adapted(engine: Engine) -> None:
    import datetime as dt

    class Event(TableRow):
        name: str
        happened_at: dt.datetime

    engine.ensure_table_created(Event)
    ts = dt.datetime(2024, 6, 15, 12, 0, 0)
    engine.insert(Event("launch", ts))
    engine.insert(Event("deploy", dt.datetime(2025, 1, 1, 9, 0, 0)))

    cur = engine.query(Event, "SELECT * FROM Event WHERE happened_at = ?", (ts,))
    row = cur.fetchone()

    assert row is not None
    assert row.name == "launch"
    assert row.happened_at == ts


def test_save__on_success__inserts_record_to_db(engine: Engine) -> None:
    engine.ensure_table_created(Team)
    row = engine.insert(Team("Lions", 30))

    cursor = engine.connection.cursor()
    cursor.execute("SELECT * FROM Team;")
    rows = cursor.fetchall()
    assert len(rows) == 1
    assert rows[0] == (row.id, "Lions", 30)


def test_save__on_success__returns_model_with_filled_in_id(engine: Engine) -> None:
    engine.ensure_table_created(Team)
    row = Team("Lions", 30)

    returned_row = engine.insert(row)
    assert returned_row.id == 1

    returned_row = engine.insert(row)
    assert returned_row.id == 2


def test_save__benchmark(engine: Engine, benchmark: BenchmarkFixture) -> None:
    engine.ensure_table_created(Team)
    row = Team("Lions", 30)

    def save():
        engine.insert(row)

    benchmark(save)


def test_save__nonexistent_id(engine: Engine) -> None:
    engine.ensure_table_created(Team)
    engine.insert(Team("Lions", 30, id=78787))


def test_save__related_model(engine: Engine) -> None:
    engine.ensure_table_created(Team)
    engine.ensure_table_created(Person)

    team = engine.insert(Team("Lions", 5))
    person = engine.insert(Person("Alice", team))

    row = engine.query(Person, "SELECT * FROM Person;").fetchone()
    assert row is not None
    assert row == person


def test_save__unpersisted_relation__raises(engine: Engine) -> None:
    engine.ensure_table_created(Team)
    engine.ensure_table_created(Person)

    team = Team("Lions", 5)
    with pytest.raises(UnpersistedRelationshipError):
        _person = engine.insert(Person("Alice", team))


def test_save__three_model_relation_chain(engine: Engine) -> None:
    engine.ensure_table_created(Team)
    engine.ensure_table_created(Person)
    engine.ensure_table_created(Arm)

    team = engine.insert(Team("Lions", 5))
    person = engine.insert(Person("Alice", team))
    arm = engine.insert(Arm(30.0, person))

    row = engine.query(Arm, "SELECT * FROM Arm;").fetchone()
    assert row == arm


def test_save__null_relation(engine: Engine) -> None:
    class A(TableRow):
        pass

    class B(TableRow):
        team: A | None

    engine.ensure_table_created(A)
    engine.ensure_table_created(B)

    person = engine.insert(B(None))

    row = engine.query(B, "SELECT * FROM B;").fetchone()
    assert row is not None
    assert row == person


def test_save__none_in_not_null_column__raises(engine: Engine) -> None:
    engine.ensure_table_created(Team)
    row = Team("Lions", cast(Any, None))

    with pytest.raises(apsw.ConstraintError, match="NOT NULL constraint failed"):
        engine.insert(row)


def test_save__updates_row(engine: Engine) -> None:
    engine.ensure_table_created(Team)
    row = engine.insert(Team("Lions", 30))

    with pytest.raises(apsw.ConstraintError):
        engine.insert(replace(row, name="Alice"))


def test_delete__by_id(engine: Engine) -> None:
    engine.ensure_table_created(Team)
    row = engine.insert(Team("Lions", 30))

    cursor = engine.connection.cursor()
    cursor.execute("SELECT * FROM Team;")
    assert len(cursor.fetchall()) == 1

    engine.delete(Team, row.id)

    cursor.execute("SELECT * FROM Team;")
    assert len(cursor.fetchall()) == 0


def test_delete__by_row(engine: Engine) -> None:
    engine.ensure_table_created(Team)
    row = engine.insert(Team("Lions", 30))

    cursor = engine.connection.cursor()
    cursor.execute("SELECT * FROM Team;")
    assert len(cursor.fetchall()) == 1

    engine.delete(Team, row.id)

    cursor.execute("SELECT * FROM Team;")
    assert len(cursor.fetchall()) == 0


def test_delete__nonexistent_id(engine: Engine) -> None:
    engine.ensure_table_created(Team)
    changes = engine.delete(Team, 78787)
    assert changes == 0


def test_delete__id_none(engine: Engine) -> None:
    engine.ensure_table_created(Team)
    changes = engine.delete(Team, None)
    assert changes == 0


def test_update__by_model_and_id(engine: Engine) -> None:
    engine.ensure_table_created(Team)
    row = engine.insert(Team("Lions", 30))

    changes = engine.update(Team, row.id, name="Tigers")

    assert changes == 1
    assert engine.find(Team, row.id) == Team("Tigers", 30, id=row.id)


def test_update__by_instance(engine: Engine) -> None:
    engine.ensure_table_created(Team)
    row = engine.insert(Team("Lions", 30))

    changes = engine.update(Team, row.id, name="Tigers")

    assert changes == 1
    assert engine.find(Team, row.id) == Team("Tigers", 30, id=row.id)


def test_update__multiple_fields(engine: Engine) -> None:
    engine.ensure_table_created(Team)
    row = engine.insert(Team("Lions", 30))

    changes = engine.update(Team, row.id, name="Tigers", size=50)

    assert changes == 1
    assert engine.find(Team, row.id) == Team("Tigers", 50, id=row.id)


def test_update__id_none(engine: Engine) -> None:
    engine.ensure_table_created(Team)
    changes = engine.update(Team, None, name="Tigers")
    assert changes == 0


def test_update__nonexistent_id(engine: Engine) -> None:
    engine.ensure_table_created(Team)
    changes = engine.update(Team, 78787, name="Tigers")
    assert changes == 0


def test_update__no_kwargs(engine: Engine) -> None:
    engine.ensure_table_created(Team)
    row = engine.insert(Team("Lions", 30))
    with pytest.raises(NoKwargFieldSpecifiedError, match="At least one field must be specified"):
        engine.update(Team, row.id)


def test_update__invalid_kwargs(engine: Engine) -> None:
    engine.ensure_table_created(Team)
    row = engine.insert(Team("Lions", 30))
    with pytest.raises(InvalidKwargFieldSpecifiedError):
        engine.update(Team, row.id, doesnt_exist="test")

from textwrap import dedent

import apsw
import pytest

from tuplesaver.engine import Engine
from tuplesaver.model import Row, TableRow


class League(TableRow):
    leaguename: str


class Team(TableRow):
    teamname: str
    league: League


class Athlete(TableRow):
    name: str
    team: Team
    number: int


class AthleteView(Row):
    __tablename__ = "Athlete"
    name: str


def dd(sql: str) -> str:
    return dedent(sql).strip()


def test_select_on_table() -> None:
    engine = Engine(apsw.Connection(":memory:"))
    engine.ensure_table_created(League)
    engine.ensure_table_created(Team)
    engine.ensure_table_created(Athlete)

    q = engine.select(Athlete)

    # Check that without params, it's just selecting the table
    # Since we can't easily introspect the query from engine.select's public API without executing,
    # we'll just check that it runs
    assert q.fetchall() == []


def test_select_on_view_model() -> None:
    engine = Engine(apsw.Connection(":memory:"))
    engine.ensure_table_created(Athlete)

    # We create a dummy view and select from it
    # Currently engine.select needs TableRow or Row with __tablename__
    query = engine.select(AthleteView)
    assert query.fetchall() == []


@pytest.mark.skip(reason="need backrefs to support this exists query")
def test_fanout_not_occur() -> None:
    engine = Engine(apsw.Connection(":memory:"))
    engine.ensure_table_created(League)
    engine.ensure_table_created(Team)
    engine.ensure_table_created(Athlete)

    # Insert a situation where a JOIN might cause a fanout if we selected the ONE side based on the MANY side.
    # Here Athlete -> Team is Many to One.
    # To test fanout from standard paths, let's just make sure queries spanning relationships don't return duplicates
    # of the base object by incorrectly joining.
    league = engine.insert(League(leaguename="Big"))

    team_red = engine.insert(Team(teamname="Red", league=league))
    team_blue = engine.insert(Team(teamname="Blue", league=league))
    team_yellow = engine.insert(Team(teamname="Yellow", league=league))

    players = [
        Athlete("Alice", team_red, 1),
        Athlete("Bob", team_red, 2),
        Athlete("Charlie", team_red, 3),
        Athlete("Xanadu", team_blue, 7),  # 1
        Athlete("Yvonne", team_blue, 7),  # 2, two players from this team
        Athlete("Zak", team_blue, 9),
        Athlete("Melinda", team_yellow, 7),  # 3
    ]
    for player in players:
        engine.insert(player)

    # normal usage to check condition on related table
    cur_semi = engine.select(Team, Team.athlete.number == 7)
    # assert it generates the EXISTS implicitly via normal usage
    assert "EXISTS" in cur_semi.sql

    rows_semi = cur_semi.fetchall()

    # only two teams have a player with #7, even though there are three players #7
    assert len(rows_semi) == 2
    assert {r.teamname for r in rows_semi} == {"Red", "Blue"}

    # A join from Team (one side) to Athlete (many side) fans out.
    rows_join = engine.query(
        Team,
        """
            SELECT Team.* FROM Team
            JOIN Athlete ON Athlete.team = Team.id"
            WHERE Athlete.number = 7
            """,
    ).fetchall()
    assert len(rows_join) == 3
    assert [r.teamname for r in rows_join] == ["Red", "Blue", "Blue"]

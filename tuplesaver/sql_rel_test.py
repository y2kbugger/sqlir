from textwrap import dedent

from tuplesaver.model import TableRow
from tuplesaver.sql_rel import compile_expr


class League(TableRow):
    leaguename: str


class Team(TableRow):
    teamname: str
    league: League


class Athlete(TableRow):
    name: str
    team: Team
    age: int


def dd(sql: str) -> str:
    return dedent(sql).strip()


def test_compile_simple_binary():
    expr = Athlete.name == "Alice"
    params = {}
    sql, next_idx = compile_expr(expr, params)

    assert sql == "Athlete.name = :p0"
    assert params == {"p0": "Alice"}
    assert next_idx == 1

    expr = Athlete.age == 30
    sql, _ = compile_expr(expr, {})
    assert sql == "Athlete.age = :p0"

    expr = Athlete.age < 30
    sql, _ = compile_expr(expr, {})
    assert sql == "Athlete.age < :p0"

    expr = Athlete.age >= 18
    sql, _ = compile_expr(expr, {})
    assert sql == "Athlete.age >= :p0"


def test_compile_logical():
    expr = (Athlete.name == "Alice") & (Athlete.age > 20)
    params = {}
    sql, next_idx = compile_expr(expr, params)
    assert sql == "(Athlete.name = :p0 AND Athlete.age > :p1)"
    assert params == {"p0": "Alice", "p1": 20}
    assert next_idx == 2

    expr = (Athlete.name == "Alice") | (Athlete.name == "Bob")
    params = {}
    sql, next_idx = compile_expr(expr, params)
    assert sql == "(Athlete.name = :p0 OR Athlete.name = :p1)"
    assert params == {"p0": "Alice", "p1": "Bob"}
    assert next_idx == 2


def test_compile_nested_semijoin():
    expr = Athlete.team.teamname == "Red"
    params = {}
    sql, next_idx = compile_expr(expr, params)

    assert sql == dd("""
        EXISTS (
            SELECT 1 FROM Team team
            WHERE team.id = Athlete.team
            AND team.teamname = :p0
        )
    """)
    assert params == {"p0": "Red"}
    assert next_idx == 1


def test_compile_multi_step_nested_semijoin():
    expr = Athlete.team.league.leaguename == "Big"
    params = {}
    sql, next_idx = compile_expr(expr, params)

    assert sql == dd("""
        EXISTS (
            SELECT 1 FROM Team team
            WHERE team.id = Athlete.team
            AND EXISTS (
                SELECT 1 FROM League team_league
                WHERE team_league.id = team.league
                AND team_league.leaguename = :p0
            )
        )
    """)
    assert params == {"p0": "Big"}
    assert next_idx == 1


def test_compile_template_string_scalar_subquery():
    expr = t"LOWER({Athlete.team.teamname}) = 'red stonks'"
    params = {}
    sql, next_idx = compile_expr(expr, params)

    assert sql == "LOWER((SELECT team.teamname FROM Team team WHERE team.id = Athlete.team)) = 'red stonks'"
    assert params == {}
    assert next_idx == 0


def test_compile_template_string_model_splices_tablename():
    expr = t"{Athlete.name} IN (SELECT name FROM {Athlete})"
    params = {}
    sql, next_idx = compile_expr(expr, params)

    assert sql == "Athlete.name IN (SELECT name FROM Athlete)"
    assert params == {}
    assert next_idx == 0


def test_compile_template_string_multi_step_scalar_subquery():
    expr = t"LOWER({Athlete.team.league.leaguename}) = 'big'"
    params = {}
    sql, next_idx = compile_expr(expr, params)

    assert sql == "LOWER((SELECT (SELECT team_league.leaguename FROM League team_league WHERE team_league.id = team.league) FROM Team team WHERE team.id = Athlete.team)) = 'big'"
    assert params == {}
    assert next_idx == 0

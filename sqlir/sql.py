"""Whole-statement SQL generation.

This module owns CREATE/SELECT/INSERT/UPDATE/DELETE templates built from
compiled model class attributes, as well as assembly of full statements that
splice in WHERE clauses produced by `sql_rel`. Predicate AST lowering
itself stays in `sql_rel.py`.
"""

from functools import cache
from textwrap import dedent
from typing import Any

# NOTE: sql.py should only depend on .model and .sql_rel — never .engine or .query.
from .model import RowMeta, TableRow
from .sql_rel import compile_expr

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _append_where(sql: str, target: Any, params: dict[str, Any]) -> str:
    """Append a `WHERE <clause>` compiled from `target` to `sql`, mutating `params`."""
    if target is None:
        return sql
    where_clause, _ = compile_expr(target, params)
    if where_clause:
        sql += f" WHERE {where_clause}"
    return sql


@cache
def _select_clause(Model: RowMeta) -> str:
    table = Model.__tablename__
    cols = ", ".join(f"{table}.{f.name}" for f in Model.__fields__)
    return f"SELECT {cols} FROM {table}"


@cache
def _update_clause(Model: type[TableRow], field_names: frozenset[str]) -> str:
    sets = ", ".join(f"{name} = :{name}" for name in field_names)
    return f"UPDATE {Model.__tablename__} SET {sets}"


# ---------------------------------------------------------------------------
# DDL
# ---------------------------------------------------------------------------


@cache
def build_create_table_sql(Model: type[TableRow]) -> str:
    """`CREATE TABLE` DDL for a table model."""
    cols = ", ".join(f.sql_columndef for f in Model.__fields__)
    return dedent(f"""
        CREATE TABLE {Model.__tablename__} (
        {cols}
        )""").strip()


def build_sqlite_schema_query(table_name: str) -> str:
    """Query `sqlite_master` for the stored `CREATE TABLE` text of `table_name`."""
    return f"SELECT sql FROM sqlite_master WHERE type='table' AND name='{table_name}'"


# ---------------------------------------------------------------------------
# SELECT
# ---------------------------------------------------------------------------


def build_select_sql(
    Model: RowMeta,
    target: Any = None,
    params: dict[str, Any] | None = None,
    *,
    order: str | None = None,
    limit: int | None = None,
    offset: int | None = None,
) -> str:
    """Assemble a full `SELECT` for `Model`, splicing a WHERE clause compiled from `target`."""
    if params is None:
        params = {}
    sql = _append_where(_select_clause(Model), target, params)
    if order:
        sql += f" ORDER BY {order}"
    if limit is not None:
        sql += f" LIMIT {limit}"
    if offset is not None:
        sql += f" OFFSET {offset}"
    return sql


# ---------------------------------------------------------------------------
# INSERT
# ---------------------------------------------------------------------------


@cache
def build_insert_sql(Model: type[TableRow]) -> str:
    """`INSERT INTO ... RETURNING ...` for every field of `Model`."""
    names = [f.name for f in Model.__fields__]
    cols = ", ".join(names)
    placeholders = ", ".join(f":{name}" for name in names)
    return dedent(f"""
        INSERT INTO {Model.__tablename__} (
            {cols}
        ) VALUES (
            {placeholders}
        )
        RETURNING {cols}
        """).strip()


# ---------------------------------------------------------------------------
# UPDATE
# ---------------------------------------------------------------------------


def build_update_sql(
    Model: type[TableRow],
    target: Any,
    params: dict[str, Any],
    field_names: frozenset[str],
) -> str:
    """Assemble a full `UPDATE` setting `field_names`, with WHERE compiled from `target`."""
    return _append_where(_update_clause(Model, field_names), target, params)


# ---------------------------------------------------------------------------
# DELETE
# ---------------------------------------------------------------------------


def build_delete_sql(
    Model: type[TableRow],
    target: Any,
    params: dict[str, Any],
) -> str:
    """Assemble a full `DELETE` for `Model`, with WHERE compiled from `target`."""
    return _append_where(f"DELETE FROM {Model.__tablename__}", target, params)

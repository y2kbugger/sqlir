"""Whole-statement SQL generation.

This module owns SELECT/INSERT/UPDATE/DELETE/DDL templates built from compiled
model class attributes. Predicate AST lowering stays in rel_compiler.py.
"""

from functools import cache, lru_cache
from textwrap import dedent

# NOTE: sql.py should only know about .model, but not .engine or .query
from .model import RowMeta, TableRow


@cache
def generate_create_table_ddl(Model: type[TableRow]) -> str:
    """Generate CREATE TABLE DDL statement for a table model."""
    table_name = Model.__tablename__
    fields = Model.__fields__
    return dedent(f"""
        CREATE TABLE {table_name} (
        {', '.join(field.sql_columndef for field in fields)}
        )""").strip()


@cache
def generate_select_sql(Model: RowMeta) -> str:
    table_name = Model.__tablename__
    fields = Model.__fields__
    return f"SELECT {', '.join(table_name + '.' + field.name for field in fields)} FROM {table_name}"


@lru_cache(maxsize=256)
def generate_select_by_field_sql(Model: RowMeta, field_names: frozenset[str]) -> str:
    select = generate_select_sql(Model)
    where_clause = " AND ".join(f"{field} = :{field}" for field in sorted(field_names))
    return dedent(f"""
        {select}
        WHERE {where_clause}
        """).strip()


@cache
def generate_insert_sql(Model: type[TableRow]) -> str:
    table_name = Model.__tablename__
    fields = Model.__fields__
    return dedent(f"""
        INSERT INTO {table_name} (
            {', '.join(field.name for field in fields)}
        ) VALUES (
            {', '.join(f":{field.name}" for field in fields)}
        )
        RETURNING {', '.join(field.name for field in fields)}
        """).strip()


@cache
def generate_update_sql(Model: type[TableRow]) -> str:
    table_name = Model.__tablename__
    fields = Model.__fields__
    return dedent(f"""
        UPDATE {table_name}
        SET {', '.join(f"{field.name} = :{field.name}" for field in fields)}
        WHERE id = :id
        RETURNING {', '.join(field.name for field in fields)}
        """).strip()


@lru_cache(maxsize=256)
def generate_update_set_fields_sql(Model: type[TableRow], field_names: frozenset[str]) -> str:
    table_name = Model.__tablename__
    return dedent(f"""
        UPDATE {table_name}
        SET {', '.join(f"{name} = :{name}" for name in field_names)}
        """).strip()


@cache
def generate_delete_sql(Model: type[TableRow]) -> str:
    table_name = Model.__tablename__
    return dedent(f"""
        DELETE FROM {table_name}
        """).strip()

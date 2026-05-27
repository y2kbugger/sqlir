from __future__ import annotations

from functools import cache, lru_cache
from textwrap import dedent

# NOTE: sql.py should only know about .model, but not .engine or .query
from .model import Row, TableRow


@cache
def generate_create_table_ddl(Model: type[TableRow]) -> str:
    """Generate CREATE TABLE DDL statement for a table model."""
    meta = Model.meta
    assert meta.table_name is not None, "Table name must be defined for the model to create it."
    ddl = dedent(f"""
        CREATE TABLE {meta.table_name} (
        {', '.join(f.sql_columndef for f in meta.fields)}
        )""").strip()

    return ddl


@cache
def generate_select_sql[R: Row | TableRow](Model: type[R]) -> str:
    meta = Model.meta
    assert meta.table_name is not None, "Table name must be defined for the model"
    return f"SELECT {', '.join(meta.table_name + '.' + f.name for f in meta.fields)} FROM {meta.table_name}"


@lru_cache(maxsize=256)
def generate_select_by_field_sql[R: Row | TableRow](Model: type[R], field_names: frozenset[str]) -> str:
    select = generate_select_sql(Model)
    where_clause = " AND ".join(f"{field} = :{field}" for field in sorted(field_names))
    return dedent(f"""
        {select}
        WHERE {where_clause}
        """).strip()


@cache
def generate_insert_sql(Model: type[TableRow]) -> str:
    meta = Model.meta
    assert meta.table_name is not None, "Table name must be defined for the model to modify it."
    return dedent(f"""
        INSERT INTO {meta.table_name} (
            {', '.join(f.name for f in meta.fields)}
        ) VALUES (
            {', '.join(f":{f.name}" for f in meta.fields)}
        )
        RETURNING {', '.join(f.name for f in meta.fields)}
        """).strip()


@cache
def generate_update_sql(Model: type[TableRow]) -> str:
    meta = Model.meta
    assert meta.table_name is not None, "Table name must be defined for the model to modify it."
    return dedent(f"""
        UPDATE {meta.table_name}
        SET {', '.join(f"{f.name} = :{f.name}" for f in meta.fields)}
        WHERE id = :id
        RETURNING {', '.join(f.name for f in meta.fields)}
        """).strip()


@lru_cache(maxsize=256)
def generate_update_set_fields_sql(Model: type[TableRow], field_names: frozenset[str]) -> str:
    meta = Model.meta
    assert meta.table_name is not None, "Table name must be defined for the model to modify it."
    return dedent(f"""
        UPDATE {meta.table_name}
        SET {', '.join(f"{name} = :{name}" for name in field_names)}
        """).strip()


@cache
def generate_delete_sql(Model: type[TableRow]) -> str:
    meta = Model.meta
    assert meta.table_name is not None, "Table name must be defined for the model to modify it."
    return dedent(f"""
        DELETE FROM {meta.table_name}
        """).strip()

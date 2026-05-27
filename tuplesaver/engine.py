from __future__ import annotations

import logging
import os
import re
from collections.abc import Sequence
from dataclasses import fields
from typing import Any

import apsw

from .adaptconvert import AdaptConvertCursor, adapt_value
from .cursorproxy import TypedCursorProxy

# NOTE: engine.py should only know about .model, but not .query
from .model import (
    Row,
    TableRow,
    is_row_model,
)
from .sql import (
    generate_create_table_ddl,
    generate_delete_sql,
    generate_insert_sql,
    generate_select_sql,
    generate_update_set_fields_sql,
)

logger = logging.getLogger(__name__)


class TableSchemaMismatch(Exception):
    def __init__(self, table_name: str, existing_table_schema: str, new_table_schema: str) -> None:
        super().__init__(
            f"Table `{table_name}` already exists but the schema does not match the expected schema.\nExisting schema:\n\t{existing_table_schema}.\nExpected schema:\n\t{new_table_schema}"
        )


class UnpersistedRelationshipError(Exception):
    def __init__(self, model_name: str, field_name: str, row: TableRow) -> None:
        super().__init__(self, f"Cannot save {model_name} with unpersisted {model_name}.{field_name} of row {row}")


class LookupByAdHocModelImpossible(Exception):
    def __init__(self, model_name: str) -> None:
        super().__init__(f"Cannot lookup via adhoc model: `{model_name}`. Only table or alt models can be used for lookups.")


class NoKwargFieldSpecifiedError(ValueError):
    def __init__(self) -> None:
        super().__init__("At least one field must be specified to find a row.")


class InvalidKwargFieldSpecifiedError(ValueError):
    def __init__(self, Model: type[TableRow], kwargs: dict[str, Any]) -> None:
        super().__init__(f"Invalid fields for {Model.__name__}: {', '.join(kwargs.keys())}. Valid fields are: {', '.join(f.name for f in Model.meta.fields)}")


class IdNoneError(ValueError):
    pass


class RecordNotFoundError(ValueError):
    def __init__(self, model_name: str, target: Any) -> None:
        super().__init__(f"No row found for {model_name} matching {target}")


class NoRecordToUpdateError(ValueError):
    pass


class NoRecordToDeleteError(ValueError):
    pass


__all_errors__ = [
    TableSchemaMismatch,
    UnpersistedRelationshipError,
    LookupByAdHocModelImpossible,
    NoKwargFieldSpecifiedError,
    InvalidKwargFieldSpecifiedError,
    IdNoneError,
    RecordNotFoundError,
    NoRecordToUpdateError,
    NoRecordToDeleteError,
]


class Engine:
    def __init__(self, db_path: str | os.PathLike[str] | apsw.Connection) -> None:
        if isinstance(db_path, apsw.Connection):
            self.connection = db_path
            self.db_path = self.connection.filename
        else:
            self.db_path = db_path
            self.connection: apsw.Connection = apsw.Connection(str(db_path))

        self.connection.cursor_factory = AdaptConvertCursor

    def ensure_table_created(self, Model: type[TableRow]) -> None:
        assert is_row_model(Model), f"Model `{Model.__name__}` is not a valid table model."
        meta = Model.meta

        ddl = generate_create_table_ddl(Model)

        try:
            self.connection.execute(ddl)
        except apsw.SQLError as e:
            assert meta.table_name is not None, "Table name must be defined for the model to create it."
            if f"table {meta.table_name} already exists" in str(e):
                # Check existing table, it might be ok
                def _normalize_whitespace(s: str) -> str:
                    return re.sub(r'\s+', ' ', s).strip()

                def _get_sql_for_existing_table(table_name: str) -> str:
                    # TODO: is there a apsw method for this?
                    query = f"SELECT sql FROM sqlite_master WHERE type='table' AND name='{table_name}'"
                    cursor = self.connection.execute(query)
                    result = cursor.fetchone()
                    cursor.close()
                    assert result is not None, f"Table {table_name} not found in sqlite_master"
                    return result[0]

                existing_table_schema = _normalize_whitespace(_get_sql_for_existing_table(meta.table_name))
                new_table_schema = _normalize_whitespace(ddl)

                if existing_table_schema != new_table_schema:
                    raise TableSchemaMismatch(meta.table_name, existing_table_schema, new_table_schema) from e
            else:
                # error is not about the table already existing
                raise
        except Exception as e:
            raise e

    ##### Reading
    def find[R: Row | TableRow](self, Model: type[R], target: Any, /, *, order: str | None = None) -> R:
        """Find a single row by a relational expression. Raises RecordNotFoundError if no row is found."""
        from .rel_compiler import compile_expr

        meta = Model.meta

        if meta.table_name is None:
            raise LookupByAdHocModelImpossible(meta.model_name)

        sql = generate_select_sql(Model)
        params: dict[str, Any] = {}

        if target is not None:
            where_clause, _ = compile_expr(target, params)
            if where_clause:
                sql += f" WHERE {where_clause}"

        if order:
            sql += f" ORDER BY {order}"
        sql += " LIMIT 1"

        cur = self.query(Model, sql, params)
        row = cur.fetchone()
        cur.close()

        if row is None:
            raise RecordNotFoundError(Model.__name__, target)
        return row

    def select[R: Row | TableRow](self, Model: type[R], target: Any = None, /, *, order: str | None = None, limit: int | None = None, offset: int | None = None) -> list[R]:
        """Select rows by a relational expression, returning a list of rows.

        If target is missing, selects all rows.
        """
        from .rel_compiler import compile_expr

        meta = Model.meta

        if meta.table_name is None:
            raise LookupByAdHocModelImpossible(meta.model_name)

        sql = generate_select_sql(Model)
        params: dict[str, Any] = {}

        if target is not None:
            where_clause, _ = compile_expr(target, params)
            if where_clause:
                sql += f" WHERE {where_clause}"

        if order:
            sql += f" ORDER BY {order}"
        if limit is not None:
            sql += f" LIMIT {limit}"
        if offset is not None:
            sql += f" OFFSET {offset}"

        cur = self.query(Model, sql, params)
        res = cur.fetchall()
        cur.close()
        return res

    def query[R: Row | TableRow](self, Model: type[R], sql_or_rel: Any = None, parameters: Sequence | dict | None = None) -> TypedCursorProxy[R]:
        if not isinstance(sql_or_rel, str):
            from .rel_compiler import compile_expr

            sql = generate_select_sql(Model)
            params: dict[str, Any] = {}
            if sql_or_rel is not None:
                where_clause, _ = compile_expr(sql_or_rel, params)
                if where_clause:
                    sql += f" WHERE {where_clause}"
            if parameters:
                if isinstance(parameters, dict):
                    params.update(parameters)
                else:
                    raise ValueError("Can only use dict parameters when providing a relational expression")
            parameters = params
        else:
            sql = sql_or_rel
            if parameters is None:
                parameters = tuple()

        if isinstance(parameters, dict):
            parameters = {k: adapt_value(v) if v is not None else None for k, v in parameters.items()}
        elif parameters:
            parameters = tuple(adapt_value(v) if v is not None else None for v in parameters)
        cursor = self.connection.execute(sql, parameters)
        return TypedCursorProxy.proxy_cursor_lazy(Model, cursor, self)

    #### Writing
    def insert[R: TableRow](self, row: R) -> R:
        """Insert a record."""
        # Don't allow saving if a related row is not persisted
        for f in fields(row)[1:]:  # skip id field
            related_row = getattr(row, f.name)
            if is_row_model(related_row.__class__) and related_row.id is None:
                raise UnpersistedRelationshipError(type(row).__name__, f.name, row)

        Model = type(row)
        insert = generate_insert_sql(Model)
        cur = self.query(Model, insert, vars(row))
        result = cur.fetchone()
        cur.close()
        assert result is not None  # INSERT always returns a row on success
        return result

    def update(self, Model: type[TableRow], target: Any, /, **patch: Any) -> int:
        """Update records matching the target expression."""
        from .rel_compiler import compile_expr

        if target is None:
            return 0

        if not patch:
            raise NoKwargFieldSpecifiedError()

        field_names = {f.name for f in Model.meta.fields}
        invalid_kwargs = {k: v for k, v in patch.items() if k not in field_names}
        if invalid_kwargs:
            raise InvalidKwargFieldSpecifiedError(Model, invalid_kwargs)

        sql = generate_update_set_fields_sql(Model, frozenset(patch.keys()))

        params: dict[str, Any] = {**patch}
        where_clause, _ = compile_expr(target, params)
        if where_clause:
            sql += f" WHERE {where_clause}"

        cur = self.query(Model, sql, params)
        changes = self.connection.changes()
        cur.close()
        return changes

    def delete(self, Model: type[TableRow], target: Any, /) -> int:
        """Delete records matching the target expression."""
        from .rel_compiler import compile_expr

        if target is None:
            return 0

        query = generate_delete_sql(Model)

        params: dict[str, Any] = {}
        where_clause, _ = compile_expr(target, params)
        if where_clause:
            query += f" WHERE {where_clause}"

        self.connection.execute(query, params)
        return self.connection.changes()


__all__ = [Engine, *__all_errors__]

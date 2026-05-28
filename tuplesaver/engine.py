import logging
import os
import re
from collections.abc import Sequence
from dataclasses import fields
from typing import Any

import apsw

from .adaptconvert import AdaptingCursor, adapt_value
from .cursorproxy import TypedCursorProxy

# NOTE: engine.py should only know about .model, but not .query
from .model import (
    Row,
    TableRow,
    is_tablerow_model,
)
from .sql import (
    build_create_table_sql,
    build_delete_sql,
    build_insert_sql,
    build_select_sql,
    build_sqlite_schema_query,
    build_update_sql,
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
        super().__init__(f"Invalid fields for {Model.__name__}: {', '.join(kwargs.keys())}. Valid fields are: {', '.join(f.name for f in Model.__fields__)}")


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

        self.connection.cursor_factory = AdaptingCursor

    def ensure_table_created(self, Model: type[TableRow]) -> None:
        assert is_tablerow_model(Model), f"Model `{Model.__name__}` is not a valid table model."
        table_name = Model.__tablename__

        ddl = build_create_table_sql(Model)

        try:
            self.connection.execute(ddl)
        except apsw.SQLError as e:
            if f"table {table_name} already exists" in str(e):
                # Check existing table, it might be ok
                def _normalize_whitespace(s: str) -> str:
                    return re.sub(r'\s+', ' ', s).strip()

                def _get_sql_for_existing_table(table_name: str) -> str:
                    # TODO: is there a apsw method for this?
                    query = build_sqlite_schema_query(table_name)
                    cursor = self.connection.execute(query)
                    result = cursor.fetchone()
                    cursor.close()
                    assert result is not None, f"Table {table_name} not found in sqlite_master"
                    return result[0]

                existing_table_schema = _normalize_whitespace(_get_sql_for_existing_table(table_name))
                new_table_schema = _normalize_whitespace(ddl)

                if existing_table_schema != new_table_schema:
                    raise TableSchemaMismatch(table_name, existing_table_schema, new_table_schema) from e
            else:
                # error is not about the table already existing
                raise
        except Exception as e:
            raise e

    ##### Reading
    def find[R: Row | TableRow](self, Model: type[R], target: Any, /, *, order: str | None = None) -> R:
        """Find a single row by a relational expression. Raises RecordNotFoundError if no row is found."""
        params: dict[str, Any] = {}
        sql = build_select_sql(Model, target, params, order=order, limit=1)

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
        params: dict[str, Any] = {}
        sql = build_select_sql(Model, target, params, order=order, limit=limit, offset=offset)

        cur = self.query(Model, sql, params)
        res = cur.fetchall()
        cur.close()
        return res

    def query[R: Row | TableRow](self, Model: type[R], sql_or_rel: Any = None, parameters: Sequence | dict | None = None) -> TypedCursorProxy[R]:
        if not isinstance(sql_or_rel, str):
            params: dict[str, Any] = {}
            sql = build_select_sql(Model, sql_or_rel, params)
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
            if is_tablerow_model(related_row.__class__) and related_row.id is None:
                raise UnpersistedRelationshipError(type(row).__name__, f.name, row)

        Model = type(row)
        insert = build_insert_sql(Model)
        cur = self.query(Model, insert, vars(row))
        result = cur.fetchone()
        cur.close()
        assert result is not None  # INSERT always returns a row on success
        return result

    def update(self, Model: type[TableRow], target: Any, /, **patch: Any) -> int:
        """Update records matching the target expression."""
        if target is None:
            return 0

        if not patch:
            raise NoKwargFieldSpecifiedError()

        field_names = {f.name for f in Model.__fields__}
        invalid_kwargs = {k: v for k, v in patch.items() if k not in field_names}
        if invalid_kwargs:
            raise InvalidKwargFieldSpecifiedError(Model, invalid_kwargs)

        params: dict[str, Any] = {**patch}
        sql = build_update_sql(Model, target, params, frozenset(patch.keys()))

        cur = self.query(Model, sql, params)
        changes = self.connection.changes()
        cur.close()
        return changes

    def delete(self, Model: type[TableRow], target: Any, /) -> int:
        """Delete records matching the target expression."""
        if target is None:
            return 0

        params: dict[str, Any] = {}
        query = build_delete_sql(Model, target, params)

        self.connection.execute(query, params)
        return self.connection.changes()


__all__ = [Engine, *__all_errors__]

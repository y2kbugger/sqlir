"""Cursor-to-model materialization.

This module turns APSW rows into model instances.
"""

from collections.abc import Iterator
from typing import TYPE_CHECKING, Any, cast

import apsw
import apsw.unicode

from sqlir.model import TableRow

from .lazy import Lazy, LazyCollection
from .model import Row, RowConverter, is_tablerow_model

if TYPE_CHECKING:
    from .engine import Engine
else:
    Engine = Any


class TypedCursorProxy[R: Row | TableRow](apsw.Cursor):
    if TYPE_CHECKING:

        def fetchone(self) -> R | None: ...
        def fetchall(self) -> list[R]: ...  # ty:ignore[invalid-method-override]
        def __iter__(self) -> Iterator[R]: ...  # ty:ignore[invalid-method-override]
        def __next__(self) -> R: ...

    @staticmethod
    def proxy_cursor_lazy(Model: type[R], cursor: apsw.Cursor, engine: Engine) -> TypedCursorProxy[R]:
        convert: RowConverter = cast(Any, Model.__converter__)

        if is_tablerow_model(Model):
            assert issubclass(Model, TableRow)
            TableModel = cast(type[TableRow], Model)
            lazy_relations = TableModel.__lazy_relations__
            backref_relations = tuple(TableModel.__backref_by_name__.values())

            def row_fac(c: apsw.Cursor, r: apsw.SQLiteValues) -> R:
                root_row = convert(r)
                row = Model(*root_row[1:], id=root_row[0])

                for idx, field_name, related_model in lazy_relations:
                    fk_value = root_row[idx]
                    assert isinstance(fk_value, int | type(None))
                    if fk_value is not None:
                        object.__setattr__(row, field_name, Lazy(engine, related_model, fk_value))

                parent_id = root_row[0]
                if parent_id is not None:
                    for rel in backref_relations:
                        object.__setattr__(row, rel.name, LazyCollection(engine, cast(type[TableRow], rel.child_model), rel.fk_name, parent_id, rel.is_many))

                return row
        else:
            assert issubclass(Model, Row)

            def row_fac(c: apsw.Cursor, r: apsw.SQLiteValues) -> R:
                return Model(*convert(r))

        cursor.row_trace = row_fac

        return cast(TypedCursorProxy[R], cursor)

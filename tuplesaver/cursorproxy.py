# Provides various useful routines
from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any, cast

import apsw
import apsw.unicode

from tuplesaver.model import TableRow

# NOTE: cursorproxy.py should only know about .model and .adaptconvert
from .model import Row, is_tablerow_model

if TYPE_CHECKING:
    from .engine import Engine


class Lazy[Model]:
    __slots__ = ("_cached", "_engine", "_id", "_model")

    def __init__(self, engine: Engine, model: type[TableRow], id_: int):
        self._engine = engine
        self._model = model
        self._id = id_
        self._cached = None

    def _obj(self) -> Model:
        if self._cached is None:
            self._cached = self._engine.find(self._model, self._id)
        return cast(Model, self._cached)

    def __hash__(self):
        return hash((self._model, self._id))

    def __eq__(self, other: object) -> bool:
        if isinstance(other, int):
            return self._id == other
        elif isinstance(other, TableRow) and type(other) is self._model:
            return self._id == other.id
        elif isinstance(other, Lazy):
            return self._model == other._model and self._id == other._id
        return False

    def __repr__(self):
        if self._cached is None:
            return f"<{self.__class__.__name__}[{self._model.__name__}]:{self._id} (pending)>"
        return f"<{self.__class__.__name__}:{self._cached!r}>"


def _make_model_lazy[R: Row | TableRow](RootModel: type[R], c: apsw.Cursor, root_row: apsw.SQLiteValues, engine: Engine) -> R:
    """Lazy loading of relationships, only fetches sub-models when accessed."""

    is_table_model = is_tablerow_model(RootModel)
    model_ctor = cast(Any, RootModel)

    if is_table_model:
        row = cast(R, model_ctor(*root_row[1:], id=root_row[0]))
    else:
        row = cast(R, model_ctor(*root_row))
        # adhoc dataclass
        return row

    RootModel: type[TableRow] = cast(type[TableRow], RootModel)

    # Now iterate over the fields and replace any foreign keys with Lazy proxies
    for idx, fld in enumerate(RootModel.meta.fields):
        if fld.type is not None and is_tablerow_model(fld.type):
            # Replace with Lazy proxy
            related_model = cast(type[TableRow], fld.type)
            fk_value = root_row[idx]
            assert isinstance(fk_value, int | type(None))
            if fk_value is not None:
                row = replace(row, **{fld.name: Lazy(engine, related_model, fk_value)})

    return row  # Return the root model with lazy-loaded relationships


class TypedCursorProxy[R: Row | TableRow](apsw.Cursor):
    if TYPE_CHECKING:

        def fetchone(self) -> R | None: ...

        def fetchall(self) -> list[R]: ...  # ty:ignore[invalid-method-override]

    @staticmethod
    def proxy_cursor_lazy(Model: type[R], cursor: apsw.Cursor, engine: Engine) -> TypedCursorProxy[R]:
        from .adaptconvert import get_model_converter

        convert = get_model_converter(Model)

        def row_fac_lazy(c: apsw.Cursor, r: apsw.SQLiteValues) -> R:
            return _make_model_lazy(Model, c, convert(r), engine)

        cursor.row_trace = row_fac_lazy

        return cast(TypedCursorProxy[R], cursor)

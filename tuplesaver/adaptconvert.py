from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

import apsw
import msgspec

from .model import RowMeta, is_row_model, native_columntypes

logger = logging.getLogger(__name__)


class AdaptConvertRegistry:
    """Provides cursors that can convert objects into one of the types supported by SQLite, or back from SQLite"""

    def __init__(self):
        self._model_converters: dict[type, Callable[[apsw.SQLiteValues], tuple]] = {}

    def __call__(self, connection: apsw.Connection) -> AdaptConvertCursor:
        "Returns a new convertor :class:`cursor <apsw.Cursor>` for the `connection`"
        return AdaptConvertRegistry.AdaptConvertCursor(connection, self)

    def adapt_value(self, value: Any) -> apsw.SQLiteValue:
        "Returns SQLite representation of `value`"
        typ = type(value)
        if typ in native_columntypes:
            return value

        if typ is bool:
            return int(value)

        # Fallback for Row models - extract id for FK storage
        if is_row_model(typ):
            return value.id

        # Fallback to msgspec
        return msgspec.json.encode(value)

    def make_converter_for_model(self, Model: RowMeta) -> Callable[[apsw.SQLiteValues], tuple]:
        """Build and cache an optimized row-converter for *Model*.

        Generates (via ``exec``) a tight converter function that maps a
        raw SQLite row-tuple to a Python-typed tuple. None values are
        passed through without calling converters. Fields whose
        type has no explicit converter are passed through if native, or decoded via msgspec.
        """

        # -- build converter via exec -------------------------------------------
        ns: dict[str, Any] = {"msgspec": msgspec}
        parts: list[str] = []

        for i, field in enumerate(Model.meta.fields):
            # Pass-through condition: natives, FKs, or Any
            if field.type in native_columntypes or is_row_model(field.type) or field.type is Any:
                parts.append(f'r[{i}]')

            elif field.type is bool:
                parts.append(f'bool(r[{i}]) if r[{i}] is not None else None')

            # Fallback to Msgspec
            else:
                cname = f'_t{i}'
                ns[cname] = field.type
                parts.append(f'msgspec.json.decode(r[{i}], type={cname}) if r[{i}] is not None else None')

        body = ', '.join(parts)
        func_code = f'def _convert(r):\n    return ({body},)'
        exec(func_code, ns)

        converter_func = ns['_convert']
        self._model_converters[Model] = converter_func
        return converter_func

    def get_model_converter(self, Model: RowMeta) -> Callable[[apsw.SQLiteValues], tuple]:
        """Return the cached converter for *Model*, building one if needed."""
        try:
            return self._model_converters[Model]
        except KeyError:
            return self.make_converter_for_model(Model)

    def _convert_binding(self, _: apsw.Cursor, __: int, value: Any) -> apsw.SQLiteValue:
        # TODO: I think we could make this smarter by storing the adapters for a specific Model as a tuple and indexing into it, instead of calling adapt_value each time
        # TODO: also could we put this as a def on the cursor class itself?
        return self.adapt_value(value)

    class AdaptConvertCursor(apsw.Cursor):
        def __init__(self, connection: apsw.Connection, ac_registry: AdaptConvertRegistry):
            super().__init__(connection)
            self.factory = ac_registry
            self.convert_binding = ac_registry._convert_binding  # adapt callback

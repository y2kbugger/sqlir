"""Value adaptation and row conversion.

This module owns SQLite <-> Python value conversion. It uses compiled model
class attributes from model.py, but it does not decide statement shape or
relationship traversal semantics.
"""

import datetime as dt
import enum
import logging
import uuid
from decimal import Decimal
from typing import Any, cast

import apsw
import msgspec

from .model import RowConverter, RowMeta, is_tablerow_model, native_columntypes

logger = logging.getLogger(__name__)


def _is_unquoted_msgspec_type(t: type | Any) -> bool:
    """When adapting/converting these as root values, we don't want them to be
    quoted. This will let SQLite operate on them natively, e.g. for datetime
    comparisons, or for enums to be stored as their int value instead of a JSON string."""
    try:
        return issubclass(t, (dt.datetime, dt.date, dt.time, Decimal, enum.Enum, uuid.UUID))
    except TypeError:
        return False


def adapt_value(value: Any) -> apsw.SQLiteValue:
    "Returns SQLite representation of `value`"
    typ = type(value)
    if typ in native_columntypes:
        return value

    if typ is bool:
        return int(value)

    if _is_unquoted_msgspec_type(typ):
        return msgspec.to_builtins(value)

    if isinstance(value, (bytearray, memoryview)):
        return value

    # Fallback for Row models - extract id for FK storage
    if is_tablerow_model(typ):
        return value.id

    # Fallback to msgspec, decode to TEXT for SQLite JSON functions
    return msgspec.json.encode(value).decode('utf-8')


def make_converter_for_model(Model: RowMeta) -> RowConverter:
    """Build and cache an optimized row-converter for *Model*.

    Generates (via ``exec``) a tight converter function that maps a
    raw SQLite row-tuple to a Python-typed tuple. None values are
    passed through without calling converters. Fields whose
    type has no explicit converter are passed through if native, or decoded via msgspec.
    """

    fields = Model.__fields__

    # -- build converter via exec -------------------------------------------
    ns: dict[str, Any] = {"msgspec": msgspec, "_dt": dt.datetime, "_date": dt.date, "_time": dt.time, "_Decimal": Decimal}
    parts: list[str] = []

    for i, field in enumerate(fields):
        if field.type is bool:
            parts.append(f'bool(r[{i}]) if r[{i}] is not None else None')
            continue

        # Pass-through condition: natives, FKs, or Any
        is_native = False
        try:
            if field.type in native_columntypes or issubclass(field.type, tuple(native_columntypes.keys())):
                import enum

                if not issubclass(field.type, enum.Enum):
                    is_native = True
        except TypeError:
            pass

        if is_native or is_tablerow_model(field.type) or field.type is Any:
            parts.append(f'r[{i}]')

        elif field.type is bytearray:
            parts.append(f'bytearray(r[{i}]) if r[{i}] is not None else None')

        elif field.type is memoryview:
            parts.append(f'memoryview(r[{i}]) if r[{i}] is not None else None')

        elif _is_unquoted_msgspec_type(field.type):
            cname = f'_t{i}'
            ns[cname] = field.type
            parts.append(f'msgspec.convert(r[{i}], type={cname}) if r[{i}] is not None else None')

        # Fallback to Msgspec
        else:
            cname = f'_t{i}'
            ns[cname] = field.type
            parts.append(f'msgspec.json.decode(r[{i}], type={cname}) if r[{i}] is not None else None')

    body = ', '.join(parts)
    func_code = f'def _convert(r):\n    return ({body},)'
    exec(func_code, ns)

    converter_func = cast(RowConverter, ns['_convert'])
    cast(Any, Model).__converter__ = converter_func
    return converter_func


class AdaptingCursor(apsw.Cursor):
    @staticmethod
    def _adapt_binding(_: apsw.Cursor, __: int, value: Any) -> apsw.SQLiteValue:
        # TODO: I think we could make this smarter by storing the adapters for a specific Model as a tuple and indexing into it, instead of calling adapt_value each time
        return adapt_value(value)

    def __init__(self, connection: apsw.Connection):
        super().__init__(connection)
        self.convert_binding = self._adapt_binding

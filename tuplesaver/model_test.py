from __future__ import annotations

import datetime as dt
from typing import NamedTuple, Optional, Union

import pytest

from .model import (
    FieldZeroIdMalformed,
    Meta,
    MetaField,
    Row,
    TableRow,
    _sql_columndef,
    _unwrap_optional_type,
    is_tablerow_model,
    schematype,
)


def test_unwrap_optional_type() -> None:
    # Non-optional hint
    assert _unwrap_optional_type(int) == (False, int)

    # Show that any pair optional syntaxs are == equivalent
    assert Union[int, None] == Optional[int]  # noqa: UP007, UP045
    assert Union[int, None] == int | None  # noqa: UP007
    assert Optional[int] == int | None  # noqa: UP045
    assert Optional[int] == Union[int, None]  # noqa: UP007, UP045
    assert int | None == Union[int, None]  # noqa: UP007
    assert int | None == Optional[int]  # noqa: UP045

    # Simple standard optional hints
    assert _unwrap_optional_type(Union[int, None]) == (True, int)  # noqa: UP007
    assert _unwrap_optional_type(Optional[int]) == (True, int)  # noqa: UP045
    assert _unwrap_optional_type(int | None) == (True, int)

    # Unions including more than one type in addition to None
    assert _unwrap_optional_type(Union[int, str, None]) == (True, int | str)  # noqa: UP007
    assert _unwrap_optional_type(int | str | None) == (True, int | str)

    # Unions not including None
    assert _unwrap_optional_type(Union[int, str]) == (False, int | str)  # noqa: UP007
    assert _unwrap_optional_type(int | str) == (False, int | str)

    # Types nested within optional
    assert _unwrap_optional_type(Union[int | str, None]) == (True, int | str)  # noqa: UP007
    assert _unwrap_optional_type(Optional[int | str]) == (True, int | str)  # noqa: UP045
    assert _unwrap_optional_type((int | str) | None) == (True, int | str)

    assert _unwrap_optional_type(Union[Union[int, str], None]) == (True, int | str)  # noqa: UP007
    assert _unwrap_optional_type(Optional[int | str]) == (True, int | str)  # noqa: UP045
    assert _unwrap_optional_type((Union[int, str]) | None) == (True, int | str)  # noqa: UP007

    # Nest unions are flattened and deduped and thus nested optionals are not preserved
    OU = Optional[int | None]  # noqa: UP045
    OUT = Optional[int | None]  # noqa: UP045
    assert OU == OUT
    assert _unwrap_optional_type(Union[OU, None]) == (True, (int))  # noqa: UP007
    assert _unwrap_optional_type(Optional[OU]) == (True, (int))  # noqa: UP045
    assert _unwrap_optional_type((OU) | None) == (True, (int))

    assert _unwrap_optional_type(Union[OUT, None]) == (True, (int))  # noqa: UP007
    assert _unwrap_optional_type(Optional[OUT]) == (True, (int))  # noqa: UP045

    # JSON_TEXT fields can be optional also
    assert _unwrap_optional_type(Optional[list]) == (True, list)  # noqa: UP045
    assert _unwrap_optional_type(Optional[dict]) == (True, dict)  # noqa: UP045
    assert _unwrap_optional_type(Optional[list[str]]) == (True, list[str])  # noqa: UP045
    assert _unwrap_optional_type(Optional[dict[str, int]]) == (True, dict[str, int])  # noqa: UP045


def test_is_row_model() -> None:
    assert is_tablerow_model(int) is False
    assert is_tablerow_model(str) is False
    assert is_tablerow_model(float) is False
    assert is_tablerow_model(bytes) is False
    assert is_tablerow_model(None) is False
    assert is_tablerow_model(tuple) is False
    assert is_tablerow_model(int | str) is False
    assert is_tablerow_model(int | None) is False

    class Model(TableRow):
        name: str

    assert is_tablerow_model(Model) is True
    assert is_tablerow_model(Model) is True
    assert is_tablerow_model(Model | None) is False  # you have to unwrap it yourself
    assert is_tablerow_model(Model | int) is False  # invalid

    class NTModel(NamedTuple):
        name: str

    assert is_tablerow_model(NTModel) is False

    import dataclasses

    @dataclasses.dataclass
    class DCModel:
        name: str

    assert is_tablerow_model(DCModel) is False

    class AdHocModel(Row):
        score: float

    assert is_tablerow_model(AdHocModel) is False

    class Obj: ...

    assert is_tablerow_model(Obj) is False


def test_sqltypename() -> None:
    assert schematype(int) == "INTEGER"
    assert schematype(str) == "TEXT"
    assert schematype(float) == "REAL"
    assert schematype(bytes) == "BLOB"
    assert schematype(bool) == "BOOL_INT"
    assert schematype(dt.date) == "DATE_TEXT"
    assert schematype(dt.datetime) == "DATETIME_TEXT"
    assert schematype(dt.time) == "TIME_TEXT"

    from decimal import Decimal

    assert schematype(Decimal) == "DECIMAL_TEXT"

    import uuid

    assert schematype(uuid.UUID) == "UUID_TEXT"

    import enum

    class IEnum(int, enum.Enum):
        A = 1

    assert schematype(IEnum) == "ENUM_INT"

    class SEnum(enum.Enum):
        A = "a"

    assert schematype(SEnum) == "ENUM_TEXT"

    class UnregisteredType: ...

    assert schematype(UnregisteredType) == "JSON_TEXT"

    # Test related models as fields
    class ModelA(TableRow):
        name: str

    assert schematype(ModelA) == "ModelA_ID"


def test_column_definition() -> None:
    assert _sql_columndef('id', True, int) == "id [INTEGER] PRIMARY KEY NOT NULL"
    with pytest.raises(FieldZeroIdMalformed):
        _sql_columndef('id', False, int)

    assert _sql_columndef("value", False, float) == "value [REAL] NOT NULL"
    assert _sql_columndef("value", True, float) == "value [REAL] NULL"

    class ModelA(TableRow):
        name: str

    assert _sql_columndef("moda", False, ModelA) == "moda [ModelA_ID] NOT NULL REFERENCES ModelA(id)"
    assert _sql_columndef("moda", True, ModelA) == "moda [ModelA_ID] NULL REFERENCES ModelA(id)"


def test_meta__model_missing_id() -> None:
    """With Roww base class, id is always inherited - test removed as no longer applicable"""

    # The id field is now always inherited from Roww, so this test is no longer needed
    class TWithInheritedId(TableRow):
        name: str

    # This should work fine - id is inherited
    meta = TWithInheritedId.meta
    assert meta.fields[0].name == "id"


def test_meta__valid_table_model() -> None:
    class ModelA(TableRow):
        name: str

    assert ModelA.meta == Meta(
        Model=ModelA,
        model_name="ModelA",
        table_name="ModelA",
        fields=(
            MetaField(name="id", type=int, full_type=int | None, nullable=True, is_fk=False, is_pk=True, sql_typename="INTEGER", sql_columndef="id [INTEGER] PRIMARY KEY NOT NULL"),
            MetaField(name="name", type=str, full_type=str, nullable=False, is_fk=False, is_pk=False, sql_typename="TEXT", sql_columndef="name [TEXT] NOT NULL"),
        ),
    )


def test_meta__custom_tablename() -> None:
    """__tablename__ overrides the default table_name (which is the class name)."""

    class MyModel(TableRow):
        __tablename__ = "custom_table"
        name: str

    assert MyModel.meta.model_name == "MyModel"
    assert MyModel.meta.table_name == "custom_table"


def test_meta__custom_tablename__not_a_field() -> None:
    """__tablename__ does not appear as a dataclass field."""

    class MyModel(TableRow):
        __tablename__ = "custom_table"
        name: str

    field_names = [f.name for f in MyModel.meta.fields]
    assert "__tablename__" not in field_names
    assert field_names == ["id", "name"]


def test_meta__model_malformed_id_raises() -> None:
    """Overriding id with wrong type causes TypeError at class definition time"""
    with pytest.raises(TypeError, match="non-default argument"):

        class TBadID(TableRow):
            id: str | None  # id is not int - override causes kw_only conflict
            name: str


def test_meta__model_id_not_optional() -> None:
    """Overriding id to be non-optional causes TypeError at class definition time"""
    with pytest.raises(TypeError, match="non-default argument"):

        class TBadID(TableRow):
            id: int  # id is not optional - override causes kw_only conflict
            name: str


def test_table_meta___related_model() -> None:
    class A(TableRow):
        name: str

    class B(TableRow):
        name: str
        unknown: A

    _ = B.meta


def test_table_meta__related_model_containing_class_declared_first() -> None:
    """This works because we made M.meta a lazy lambda, which initializes only when first accessed."""

    class B(TableRow):
        name: str
        unknown: A

    class A(TableRow):
        name: str

    _ = B.meta


def test_table_meta__related_model_recursive() -> None:
    class A(TableRow):
        name: str
        a: A | None

    _ = A.meta


def test_table_meta__unregistered_field_type__doesnt_raise() -> None:
    class NewType: ...

    class ModelUnknownType(TableRow):
        name: str
        unknown: NewType

    meta = ModelUnknownType.meta
    assert meta.fields[2].sql_typename == "JSON_TEXT"


def test_meta__json_style_fields__preserve_full_type_and_use_jsontext_storage() -> None:
    from dataclasses import dataclass

    @dataclass
    class JsonData:
        name: str
        value: int

    class TypedJsonModel(TableRow):
        created_on: dt.date
        created_at: dt.datetime
        names: list[str]
        counts: dict[str, int]
        payload: list[dict[str, int]]
        payload_item: JsonData
        payload_dataclasses: list[JsonData]

    meta = TypedJsonModel.meta
    by_name = {field.name: field for field in meta.fields}

    assert schematype(list) == "JSON_TEXT"
    assert schematype(dict) == "JSON_TEXT"
    assert schematype(dt.date) == "DATE_TEXT"
    assert schematype(dt.datetime) == "DATETIME_TEXT"

    assert by_name["created_on"].full_type == dt.date
    assert by_name["created_on"].type is dt.date
    assert by_name["created_on"].sql_typename == "DATE_TEXT"
    assert by_name["created_on"].sql_columndef == "created_on [DATE_TEXT] NOT NULL"

    assert by_name["created_at"].full_type == dt.datetime
    assert by_name["created_at"].type is dt.datetime
    assert by_name["created_at"].sql_typename == "DATETIME_TEXT"
    assert by_name["created_at"].sql_columndef == "created_at [DATETIME_TEXT] NOT NULL"

    assert by_name["names"].full_type == list[str]
    assert by_name["names"].type == list[str]
    assert by_name["names"].sql_typename == "JSON_TEXT"
    assert by_name["names"].sql_columndef == "names [JSON_TEXT] NOT NULL"

    assert by_name["counts"].full_type == dict[str, int]
    assert by_name["counts"].type == dict[str, int]
    assert by_name["counts"].sql_typename == "JSON_TEXT"
    assert by_name["counts"].sql_columndef == "counts [JSON_TEXT] NOT NULL"

    assert by_name["payload"].full_type == list[dict[str, int]]
    assert by_name["payload"].type == list[dict[str, int]]
    assert by_name["payload"].sql_typename == "JSON_TEXT"
    assert by_name["payload"].sql_columndef == "payload [JSON_TEXT] NOT NULL"

    assert by_name["payload_item"].full_type == JsonData
    assert by_name["payload_item"].type == JsonData
    assert by_name["payload_item"].sql_typename == "JSON_TEXT"
    assert by_name["payload_item"].sql_columndef == "payload_item [JSON_TEXT] NOT NULL"

    assert by_name["payload_dataclasses"].full_type == list[JsonData]
    assert by_name["payload_dataclasses"].type == list[JsonData]
    assert by_name["payload_dataclasses"].sql_typename == "JSON_TEXT"
    assert by_name["payload_dataclasses"].sql_columndef == "payload_dataclasses [JSON_TEXT] NOT NULL"

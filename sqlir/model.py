"""Model declaration and compilation.

This module owns model-class compilation and the class-level attributes derived
from annotations. Other modules should consume the compiled class attributes it
exposes rather than re-deriving model shape.
"""

import logging
import types
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, NamedTuple, Union, cast, dataclass_transform, get_args, get_origin, get_type_hints

import apsw

from .lazy import Lazy

logger = logging.getLogger(__name__)


# Raw class attrs populated during compilation.
_COMPILED_CACHE_ATTRS = frozenset(
    {
        "__tablename__",
        "__fields__",
        "__fields_by_name__",
        "__lazy_relations__",
        "__lazy_field_names__",
        "__converter__",
    }
)

# Type alias for the converter function type, which maps a raw SQLite row to Python Types
type RowConverter = Callable[[apsw.SQLiteValues], tuple[Any, ...]]


class ModelField(NamedTuple):
    name: str
    type: type
    full_type: Any  # e.g. includes Optional
    nullable: bool
    is_fk: bool
    is_pk: bool
    sql_typename: str
    sql_columndef: str


def _uncompiled_rowconverter(_: apsw.SQLiteValues) -> tuple[Any, ...]:
    raise AssertionError("Model converter accessed before model compilation")


@dataclass_transform(field_specifiers=(field,))
class RowMeta(type):
    """Metaclass that transforms model classes into frozen dataclasses.

    Typing rule:
    - Use ``RowMeta`` for helpers that only need "a model class" and read
      class-level cached state such as ``__tablename__``, ``__fields__``,
      ``__converter__``, or cached SQL.
    - Use ``type[R]`` only on generic APIs whose return type depends on the
      specific model class that was passed in, such as ``Engine.find`` or
      ``TypedCursorProxy.proxy_cursor_lazy``.

        Compilation rule:
        - We intentionally do not compile model metadata eagerly in ``__new__``.
            A model can reference another model declared later in the same scope, so
            type-hint resolution has to wait until first real use.
        - To keep that deferred compile from leaking everywhere else, this
            metaclass compiles on first access to any of the compiled cache
            attrs (``__tablename__``, ``__fields__``, etc.).

    This keeps internal helpers simple without giving up precise inference on
    the public, type-propagating APIs.
    """

    __tablename__: str
    __fields__: tuple[ModelField, ...]
    __fields_by_name__: dict[str, ModelField]
    __lazy_relations__: tuple[tuple[int, str, type[TableRow]], ...]
    __lazy_field_names__: frozenset[str]
    __converter__: RowConverter
    _is_dataclass_parsing: bool
    _tablename_is_default: bool
    _is_compiled: bool

    def __new__(cls, typename: str, bases: tuple[type, ...], ns: dict[str, Any]) -> type:
        model_cls = cast(RowMeta, super().__new__(cls, typename, bases, ns))

        # apply the dataclass decorator if not already applied
        if "__dataclass_fields__" not in model_cls.__dict__:
            # Temporarily block __getattr__ from returning FieldExprs so dataclass
            # doesn't mistake them for default values.
            type.__setattr__(model_cls, "_is_dataclass_parsing", True)
            model_cls = cast(RowMeta, dataclass(model_cls, frozen=True))  # ty:ignore[no-matching-overload]
            type.__setattr__(model_cls, "_is_dataclass_parsing", False)

        model_cls.__tablename__ = ns.get("__tablename__", typename)
        model_cls.__fields__ = ()
        model_cls.__fields_by_name__ = {}
        model_cls.__lazy_relations__ = ()
        model_cls.__lazy_field_names__ = frozenset()
        model_cls.__converter__ = _uncompiled_rowconverter
        type.__setattr__(model_cls, "_tablename_is_default", "__tablename__" not in ns)
        type.__setattr__(model_cls, "_is_compiled", False)

        return model_cls

    def _field_expr(cls, name: str) -> Any:
        from .rel import FieldExpr

        field = cls.__fields_by_name__[name]
        target_model = field.type if field.is_fk else None
        return FieldExpr(name, cls, target_model=target_model)

    def __getattribute__(cls, name: str) -> Any:
        if name in _COMPILED_CACHE_ATTRS:
            cls._ensure_compiled()

        # Dunders (incl. the compiled-cache attrs above) are never fields.
        if name.startswith("__") and name.endswith("__"):
            return type.__getattribute__(cls, name)

        cls_dict = type.__getattribute__(cls, "__dict__")

        # While dataclass introspects defaults, let it see the real values.
        if cls_dict.get("_is_dataclass_parsing", False):
            return type.__getattribute__(cls, name)

        # Declared fields resolve to a FieldExpr, shadowing the concrete default
        # attr dataclass sets for defaulted fields (``id``, nullable fields).
        if name in cls_dict.get("__dataclass_fields__", ()):
            return cls._field_expr(name)

        return type.__getattribute__(cls, name)

    def __getattr__(cls, name: str) -> Any:
        # __getattribute__ intercepts every declared field, so any name reaching
        # __getattr__ is a genuinely missing attribute. Dunder probes get a plain
        # error; everything else gets a typo-friendly "no field" message.
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(name)
        raise AttributeError(f"{cls.__name__!r} has no field {name!r}")

    def _ensure_compiled(cls) -> None:
        if not cls._is_compiled:
            cls._compile_model()

    def _compile_model(cls) -> None:
        annotations = _get_resolved_annotations(cls)
        fieldnames = cls.__dataclass_fields__.keys()
        full_types = tuple(annotations.values())
        unwrapped_types = tuple(_unwrap_optional_type(t) for t in full_types)

        # `Any` has no storage/schema/affinity, so it cannot back a column on a
        # table model. It is allowed on `Row` (ad-hoc/view-shaped) models, where
        # it just means "pass the raw SQLite value through without converting".
        if is_tablerow_model(cls):
            for fieldname, (_, FieldType) in zip(fieldnames, unwrapped_types, strict=False):
                if FieldType is Any:
                    raise AnyTypeNotAllowedOnTableRow(cls.__name__, fieldname)

        fields = tuple(
            ModelField(
                name=fieldname,
                type=FieldType,
                full_type=full_type,
                nullable=nullable,
                is_fk=is_tablerow_model(FieldType),
                is_pk=fieldname == "id",
                sql_typename=schematype(FieldType),
                sql_columndef=_sql_columndef(fieldname, nullable, FieldType),
            )
            for fieldname, full_type, (nullable, FieldType) in zip(fieldnames, full_types, unwrapped_types, strict=False)
        )

        table_name = _current_table_name(cls)

        if "_" in cls.__name__:
            raise InvalidTableName(cls.__name__)

        lazy_relations = tuple((idx, field.name, cast(type[TableRow], field.type)) for idx, field in enumerate(fields) if field.is_fk)

        cls.__tablename__ = table_name
        cls.__fields__ = fields
        cls.__fields_by_name__ = {field.name: field for field in fields}
        cls.__lazy_relations__ = lazy_relations
        cls.__lazy_field_names__ = frozenset(name for _, name, _ in lazy_relations)

        type.__setattr__(cls, "_is_compiled", True)

        from .adaptconvert import make_converter_for_model

        try:
            cls.__converter__ = make_converter_for_model(cls)
        except Exception:
            type.__setattr__(cls, "_is_compiled", False)
            raise


class Row(metaclass=RowMeta):
    pass


class TableRow(metaclass=RowMeta):
    id: int | None = field(default=None, kw_only=True)

    def __getattribute__(self, name: str, /) -> Any:
        value = object.__getattribute__(self, name)

        if name.startswith("__"):
            return value

        lazy_field_names = type(self).__lazy_field_names__
        if name not in lazy_field_names:
            return value

        if isinstance(value, Lazy):
            return value._obj()  # materialize & return real row  # noqa: SLF001
        return value

    @classmethod
    def Id(cls, id_val: int | None) -> Any:
        from .rel import FieldExpr

        if id_val is None:
            raise ValueError(f"{cls.__name__}.Id() requires a persisted id, got None")

        return FieldExpr("id", cls) == int(id_val)


class ModelDefinitionError(Exception):
    pass


class FieldZeroIdRequired(ModelDefinitionError):
    def __init__(self, model_name: str, field_zero_name: str, field_zero_typehint: Any) -> None:
        super().__init__(
            self,
            f"Field 0 of {model_name} is required to be `id: int | None` but instead is `{field_zero_name}: {field_zero_typehint}`",
        )


class FieldZeroIdMalformed(ModelDefinitionError):
    def __init__(self, field_zero_typehint: Any) -> None:
        super().__init__(
            self,
            f"`id` field is required to be `id: int | None` but instead is `id: {field_zero_typehint}`",
        )


class InvalidTableName(ModelDefinitionError):
    def __init__(self, table_name: str) -> None:
        super().__init__(f"Invalid table name: `{table_name}`. Table names must not contain underscores, these are reserved for alternate models.")


class AnyTypeNotAllowedOnTableRow(ModelDefinitionError):
    def __init__(self, model_name: str, field_name: str) -> None:
        super().__init__(
            f"Field `{field_name}` of table model `{model_name}` is typed `Any`, which has no storage/schema/SQL type or affinity. "
            f"`Any` is only allowed on `Row` (ad-hoc) models, where it passes the raw SQLite value through unconverted.",
        )


native_columntypes: dict[type, str] = {
    str: "TEXT",
    float: "REAL",
    int: "INTEGER",
    bytes: "BLOB",
}


def is_tablerow_model(cls: object) -> bool:
    """Test at runtime whether an object is a TableRow model."""
    return isinstance(cls, type) and issubclass(cls, TableRow)


def _current_table_name(Model: RowMeta) -> str:
    class_dict = type.__getattribute__(Model, "__dict__")
    if cast(bool, class_dict.get("_tablename_is_default", False)):
        return Model.__name__
    return cast(str, class_dict.get("__tablename__", Model.__name__))


def schematype(FieldType: type) -> str:
    if FieldType in native_columntypes:
        return native_columntypes[FieldType]
    elif FieldType is bool:
        return "BOOL_INT"
    elif is_tablerow_model(FieldType):
        # a yet unregistered foreign key
        return f"{FieldType.__name__}_ID"
    else:
        import datetime as dt
        import enum
        import uuid
        from decimal import Decimal

        try:
            match FieldType:
                case _ if issubclass(FieldType, int) and issubclass(FieldType, enum.Enum):
                    return "ENUM_INT"
                case _ if issubclass(FieldType, enum.Enum):
                    return "ENUM_TEXT"
                case _ if issubclass(FieldType, dt.datetime):
                    return "DATETIME_TEXT"
                case _ if issubclass(FieldType, dt.date):
                    return "DATE_TEXT"
                case _ if issubclass(FieldType, dt.time):
                    return "TIME_TEXT"
                case _ if issubclass(FieldType, Decimal):
                    return "DECIMAL_TEXT"
                case _ if issubclass(FieldType, uuid.UUID):
                    return "UUID_TEXT"
        except TypeError:
            pass
        return "JSON_TEXT"


def _sql_columndef(field_name: str, nullable: bool, FieldType: type) -> str:
    if field_name == "id":
        if not (issubclass(FieldType, int) and nullable):
            raise FieldZeroIdMalformed(FieldType)
        return "id [INTEGER] PRIMARY KEY NOT NULL"

    if nullable:
        nullable_sql = "NULL"
    else:
        nullable_sql = "NOT NULL"

    columntype = schematype(FieldType)

    # Add FK constraint for related models
    if is_tablerow_model(FieldType):
        fk_table = _current_table_name(cast(RowMeta, FieldType))
        fk_clause = f" REFERENCES {fk_table}(id)"
    else:
        fk_clause = ""

    return f"{field_name} [{columntype}] {nullable_sql}{fk_clause}"


def _unwrap_optional_type(type_hint: Any) -> tuple[bool, Any]:
    """Determine if a given type hint is an Optional type

    Supports the following forms of Optional types:
    UnionType (e.g., int | None)
    Optional  (e.g., Optional[int])
    Union (e.g., Union[int, None])

    Returns
    - A boolean indicating if it is Optional.
    - The underlying type if it is Optional, otherwise the original type.
    """

    # Not any form of Union type
    if not (isinstance(type_hint, types.UnionType) or get_origin(type_hint) is Union):
        return False, type_hint

    args = get_args(type_hint)
    optional = type(None) in args

    underlying_types = tuple(arg for arg in args if arg is not type(None))

    underlying_type = underlying_types[0]
    for t in underlying_types[1:]:
        underlying_type |= t

    return optional, underlying_type


def _get_resolved_annotations(Model: Any) -> dict[str, Any]:
    """Resolve annotations for a model class.

    Python 3.14 already defers annotation evaluation, so by the time model
    compilation runs we can ask ``get_type_hints()`` for the resolved values
    directly.
    """
    hints = get_type_hints(Model, include_extras=True)

    # Ensure ordering matches dataclass field order
    if hasattr(Model, "__dataclass_fields__"):
        ordered = {}
        for name in Model.__dataclass_fields__:
            if name in hints:
                ordered[name] = hints[name]
        return ordered

    return hints

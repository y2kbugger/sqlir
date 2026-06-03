"""Model declaration and compilation.

This module owns model-class compilation and the class-level attributes derived
from annotations. Other modules should consume the compiled class attributes it
exposes rather than re-deriving model shape.
"""

import logging
import types
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Union, cast, dataclass_transform, get_args, get_origin, get_type_hints

import apsw

from .lazy import Lazy, LazyCollection, Rows

logger = logging.getLogger(__name__)


# Metadata key under which `backref()` stashes its target FK FieldExpr on the
# dataclass field, read back during model compilation.
_BACKREF_KEY = "sqlir_backref"


def backref(*, fk: Any, init: bool = False) -> Any:
    """Declare a virtual reverse relationship from the parent side.

    `fk` is normally the child's forward-FK field reference (e.g.
    `Athlete.team`). You may also spell that same reference as the fully-
    qualified string `"Athlete.team"`. The typed form is more refactor-safe,
    while the string form resolves later and can be convenient when forward
    references or declaration order make the typed form awkward. A
    `list[Child]` annotation makes it has_many; a scalar `Child` annotation
    makes it has_one.

    Example self-reference:
    `children: Rows["Node"] = backref(fk="Node.parent")`.

    Backref fields are *virtual*: they back no column and never appear in any
    SQL (DDL/INSERT/SELECT). They materialize lazily on first access.

    `init` exists only so PEP 681 type checkers treat the field as excluded from
    the synthesized `__init__`; it defaults to `False` and should not be passed.
    """
    # repr=False: a backref is virtual and lazily loaded, so including it in the
    # dataclass repr would trigger a DB query and recurse forever through
    # circular relations (parent -> children -> parent -> ...).
    return field(default=None, init=init, repr=False, metadata={_BACKREF_KEY: fk})


# Raw class attrs populated during compilation.
_COMPILED_CACHE_ATTRS = frozenset(
    {
        "__tablename__",
        "__fields__",
        "__fields_by_name__",
        "__refs_by_name__",
        "__converter__",
    }
)

# Type alias for the converter function type, which maps a raw SQLite row to Python Types
type RowConverter = Callable[[apsw.SQLiteValues], tuple[Any, ...]]


@dataclass(frozen=True, slots=True)
class ModelField:
    name: str
    type: type
    full_type: Any  # e.g. includes Optional
    nullable: bool
    is_fk: bool
    is_pk: bool
    sql_typename: str
    sql_columndef: str


@dataclass(frozen=True, slots=True)
class Ref:
    """A navigable reference — forward FK or backref  for {target}.{name}

    Join columns are precomputed so traversal/SQL never re-branch on direction:
    the predicate is always `{far_alias}.{far_col} = {near_alias}.{near_col}`.
    """

    name: str
    target: type[TableRow]
    near_col: str  # source-side join column (the FK column forward, "id" for a backref)
    far_col: str  # target-side join column ("id" forward, the child FK for a backref)
    is_back: bool  # reverse (queried children) vs forward (stored FK column)
    is_collection: bool  # many (Rows) vs a single row / None
    index: int  # FK value's column index in a fetched row (forward only; -1 for a backref)


def _uncompiled_rowconverter(_: apsw.SQLiteValues) -> tuple[Any, ...]:
    raise AssertionError("Model converter accessed before model compilation")


@dataclass_transform(field_specifiers=(field, backref))
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
    __refs_by_name__: dict[str, Ref]
    __converter__: RowConverter
    __select_query__: Any
    _is_dataclass_parsing: bool
    _tablename_is_default: bool
    _is_compiled: bool

    def __new__(cls, typename: str, bases: tuple[type, ...], ns: dict[str, Any]) -> type:
        table_row_type = globals().get("TableRow")
        if isinstance(table_row_type, type):
            invalid_base = next((base for base in bases if issubclass(base, table_row_type) and base is not table_row_type), None)
            if invalid_base is not None:
                raise TableModelInheritanceError(typename, invalid_base.__name__)

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
        model_cls.__refs_by_name__ = {}
        model_cls.__converter__ = _uncompiled_rowconverter
        model_cls.__select_query__ = ns.get("__select_query__")
        type.__setattr__(model_cls, "_tablename_is_default", "__tablename__" not in ns)
        type.__setattr__(model_cls, "_is_compiled", False)

        return model_cls

    def _field_expr(cls, name: str) -> Any:
        from .rel import FieldExpr

        # Build the expr without forcing compilation: a backref like
        # `backref(fk=Athlete.team)` accesses `Athlete.team` while `Team` is
        # still being defined, so compiling `Athlete` here would fail to resolve
        # the `Team` forward reference. `FieldExpr` resolves its target model
        # lazily, by which point both models exist.
        return FieldExpr(name, cls)

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
        dataclass_fields = cls.__dataclass_fields__

        # Split declared fields into real columns and virtual backrefs. Backref
        # fields back no column and never enter any SQL, so they are excluded
        # from `__fields__`, DDL, INSERT/SELECT, and the converter.
        backref_specs = {name: f.metadata[_BACKREF_KEY] for name, f in dataclass_fields.items() if _BACKREF_KEY in f.metadata}

        fieldnames = [name for name in dataclass_fields if name not in backref_specs]
        full_types = tuple(annotations[name] for name in fieldnames)
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

        if is_tablerow_model(cls):
            if "_" in cls.__name__:
                raise InvalidTableName(cls.__name__)
            if cls.__select_query__ is not None:
                raise SelectQueryNotAllowedOnTableRow(cls.__name__)

        # A self-referential backref's child is `cls` itself, still mid-compile,
        # so its `__fields_by_name__` attr isn't set yet. Pass the locally-built
        # mapping so validation reads it without re-triggering compilation.
        own_fields_by_name = {field.name: field for field in fields}
        backref_refs = (_build_backref_ref(cls, name, annotations[name], fk, own_fields_by_name) for name, fk in backref_specs.items())

        # Forward FKs and backrefs share one ref map so traversal, SQL, and lazy
        # loading read a single shape.
        forward_refs = (
            Ref(name=f.name, target=cast(type[TableRow], f.type), near_col=f.name, far_col="id", is_back=False, is_collection=False, index=idx) for idx, f in enumerate(fields) if f.is_fk
        )

        cls.__tablename__ = table_name
        cls.__fields__ = fields
        cls.__fields_by_name__ = {field.name: field for field in fields}
        cls.__refs_by_name__ = {ref.name: ref for ref in (*forward_refs, *backref_refs)}

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

        cls = type(self)

        ref = cls.__refs_by_name__.get(name)
        if ref is None:
            return value

        if not ref.is_back:
            # Forward FK: materialize the `Lazy` proxy on access.
            return value._obj() if isinstance(value, Lazy) else value  # noqa: SLF001

        if isinstance(value, LazyCollection):
            return value._obj()  # materialize & cache the reverse query  # noqa: SLF001
        # Unmaterialized (a manually constructed, not-yet-loaded parent): there
        # is no engine to query, so give an honest empty result.
        return Rows() if ref.is_collection else None

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


class SelectQueryNotAllowedOnTableRow(ModelDefinitionError):
    def __init__(self, model_name: str) -> None:
        super().__init__(
            f"Table model `{model_name}` cannot define `__select_query__`. `__select_query__` is only allowed on `Row` (ad-hoc) models, which have no backing table.",
        )


class AnyTypeNotAllowedOnTableRow(ModelDefinitionError):
    def __init__(self, model_name: str, field_name: str) -> None:
        super().__init__(
            f"Field `{field_name}` of table model `{model_name}` is typed `Any`, which has no storage/schema/SQL type or affinity. "
            f"`Any` is only allowed on `Row` (ad-hoc) models, where it passes the raw SQLite value through unconverted.",
        )


class TableModelInheritanceError(ModelDefinitionError):
    def __init__(self, model_name: str, base_model_name: str) -> None:
        super().__init__(f"Table model `{model_name}` cannot subclass table model `{base_model_name}`. Subclass `TableRow` directly, or use `Row` for inherited ad-hoc models.")


class BackrefError(ModelDefinitionError):
    pass


class BackrefFkNotFieldReference(BackrefError):
    def __init__(self, model_name: str, field_name: str) -> None:
        super().__init__(
            f"Backref `{model_name}.{field_name}` needs `fk=` to be a single forward-FK field reference like `Child.parent` "
            f"or the fully-qualified string `\"Child.parent\"`, not a bare field name or multi-hop path.",
        )


class BackrefChildNotTableRow(BackrefError):
    def __init__(self, model_name: str, field_name: str, child_name: str) -> None:
        super().__init__(f"Backref `{model_name}.{field_name}` points at `{child_name}`, which is not a `TableRow` model.")


class BackrefFkMismatch(BackrefError):
    def __init__(self, model_name: str, field_name: str, child_name: str, fk_name: str) -> None:
        super().__init__(
            f"Backref `{model_name}.{field_name}` uses `fk={child_name}.{fk_name}`, but `{child_name}.{fk_name}` is not a foreign key pointing back at `{model_name}`.",
        )


class BackrefCardinalityMismatch(BackrefError):
    def __init__(self, model_name: str, field_name: str, child_name: str, annotated_name: str) -> None:
        super().__init__(
            f"Backref `{model_name}.{field_name}` is annotated for `{annotated_name}` but `fk=` points at `{child_name}`. Use `list[{child_name}]` (has_many) or `{child_name}` (has_one).",
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


def _build_backref_ref(parent_cls: RowMeta, field_name: str, full_type: Any, fk: Any, parent_fields_by_name: dict[str, ModelField]) -> Ref:
    """Validate one `backref()` declaration and lower it to a reverse `Ref`.

    `parent_fields_by_name` is the parent's locally-built field map; it is used
    instead of the not-yet-set `__fields_by_name__` attr when the backref is
    self-referential (the child is the parent itself, still compiling).
    """
    from .rel import FieldExpr

    # has_many is `Rows[Child]`; has_one is a bare scalar `Child`.
    _, unwrapped = _unwrap_optional_type(full_type)
    is_collection = get_origin(unwrapped) is Rows
    annotated_model = get_args(unwrapped)[0] if is_collection else unwrapped

    # `fk` is a single forward-FK field reference, spelled either as the typed
    # `Child.team` (a `FieldExpr`) or the fully-qualified string `"Child.team"`.
    # The string mirrors the typed surface while resolving later, which makes it
    # usable for parent-first declarations and self-referential backrefs. The
    # string's model prefix is redundant with the annotation on purpose
    # (double-entry): a mismatch is a refactor-drift bug. Normalize both spellings
    # to a single `FieldExpr` so the rest of the function has one path.
    if isinstance(fk, str):
        model_name, _, fk_name = fk.partition(".")
        if not fk_name or "." in fk_name or model_name != getattr(annotated_model, "__name__", None):
            raise BackrefFkNotFieldReference(parent_cls.__name__, field_name)
        fk = FieldExpr(fk_name, annotated_model)
    elif not (isinstance(fk, FieldExpr) and fk._model is not None and "." not in fk._name):  # noqa: SLF001
        raise BackrefFkNotFieldReference(parent_cls.__name__, field_name)

    child_model = fk._model  # noqa: SLF001
    fk_name = fk._name  # noqa: SLF001

    if not is_tablerow_model(child_model):
        raise BackrefChildNotTableRow(parent_cls.__name__, field_name, getattr(child_model, "__name__", repr(child_model)))

    if annotated_model is not child_model:
        raise BackrefCardinalityMismatch(parent_cls.__name__, field_name, child_model.__name__, getattr(annotated_model, "__name__", repr(annotated_model)))

    # Self-referential child is `parent_cls` still mid-compile; read its fields
    # from the locally-built map rather than the unset attribute.
    child_fields_by_name = parent_fields_by_name if child_model is parent_cls else child_model.__fields_by_name__
    child_field = child_fields_by_name.get(fk_name)
    if child_field is None or not child_field.is_fk or child_field.type is not parent_cls:
        raise BackrefFkMismatch(parent_cls.__name__, field_name, child_model.__name__, fk_name)

    # Reverse hop: queried from the child side, joining child.<fk> back to our id.
    return Ref(name=field_name, target=child_model, near_col="id", far_col=fk_name, is_back=True, is_collection=is_collection, index=-1)


def has_select_query(Model: object) -> bool:
    """Test whether a model binds its own query via `__select_query__`, an arbitrary SQL the model is loaded from."""
    return getattr(Model, "__select_query__", None) is not None


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

"""Relational expression AST.

This module defines the user-facing expression objects built from model field
access like ``Person.name == \"Alice\"``. It does not emit SQL text.
"""

from typing import Any

# Sentinel: a FieldExpr whose target model has not yet been resolved (lazily).
_UNRESOLVED = object()


class BooleanCoercionError(TypeError):
    """Raised when a relational expression is used in a boolean context.

    Python's ``and`` / ``or`` / ``not`` keywords short-circuit via ``__bool__``
    and cannot be overloaded; use the bitwise ``&`` / ``|`` / ``~`` operators
    to compose rel expressions instead.
    """


class Expr:
    __hash__ = object.__hash__

    def __bool__(self) -> bool:
        raise BooleanCoercionError(
            f"Cannot evaluate {type(self).__name__} as bool. "
            "Use `&` / `|` (bitwise) to combine rel expressions, not `and` / `or`. "
            "Note: `t\"...\" and expr` silently drops the t-string because Templates are always truthy."
        )

    def __eq__(self, other: Any) -> Expr:  # type: ignore[override, ty:invalid-method-override]
        return BinaryExpr(self, "==", other)

    def __ne__(self, other: Any) -> Expr:  # type: ignore[override, ty:invalid-method-override]
        return BinaryExpr(self, "!=", other)

    def __lt__(self, other: Any) -> Expr:
        return BinaryExpr(self, "<", other)

    def __le__(self, other: Any) -> Expr:
        return BinaryExpr(self, "<=", other)

    def __gt__(self, other: Any) -> Expr:
        return BinaryExpr(self, ">", other)

    def __ge__(self, other: Any) -> Expr:
        return BinaryExpr(self, ">=", other)

    def __or__(self, other: Any) -> Expr:
        return LogicalExpr(self, "OR", other)

    def __and__(self, other: Any) -> Expr:
        return LogicalExpr(self, "AND", other)

    def __ror__(self, other: Any) -> Expr:
        return LogicalExpr(other, "OR", self)

    def __rand__(self, other: Any) -> Expr:
        return LogicalExpr(other, "AND", self)


class FieldExpr(Expr):
    def __init__(self, name: str, model: Any = None, target_model: Any = _UNRESOLVED):
        self._name = name
        self._model = model  # Root model where this field expression started (e.g. Employee for Employee.department.name)
        self._target_model_value = target_model  # Final model in chain, resolved lazily (see `_target_model`)

    @property
    def _target_model(self) -> Any:
        # Resolved lazily: building a FieldExpr (e.g. for `backref(fk=Child.parent)`)
        # must not force model compilation, since the referenced models may not
        # all be defined yet at field-access time.
        if self._target_model_value is _UNRESOLVED:
            self._target_model_value = self._resolve_target_model()
        return self._target_model_value

    def _resolve_target_model(self) -> Any:
        model = self._model
        if model is None:
            return None
        ref = model.__refs_by_name__.get(self._name)
        return ref.target if ref is not None else None

    def __getattr__(self, item: str) -> FieldExpr:
        if item.startswith("_"):
            raise AttributeError(item)

        target = self._target_model
        if target is None:
            raise AttributeError(
                f"cannot access {item!r} on {self!r}: field type is not a foreign-key model",
            )

        ref = target.__refs_by_name__.get(item)
        if ref is not None:
            next_target = ref.target
        elif item in target.__fields_by_name__:
            next_target = None  # a terminal (non-navigable) field
        else:
            raise AttributeError(f"{target.__name__!r} has no field {item!r}")
        return FieldExpr(f"{self._name}.{item}", self._model, target_model=next_target)

    def __getitem__(self, index: Any) -> FieldExpr:
        # Typing bridge for has_many traversal: `Squad.players[0].number`. A
        # has_many field is statically a `Rows[Child]`, so `[0]` is a `Child`
        # and member access type-checks. At runtime the index is irrelevant —
        # the generated semi-join spans the whole relation — so we just keep
        # walking the same path.
        return self

    def __repr__(self) -> str:
        prefix = f"{self._model.__name__}." if self._model else ""
        return f"FieldExpr('{prefix}{self._name}')"


class BinaryExpr(Expr):
    def __init__(self, left: Expr, op: str, right: Any):
        self.left = left
        self.op = op
        self.right = right

    def __repr__(self) -> str:
        return f"({self.left} {self.op} {self.right!r})"


class LogicalExpr(Expr):
    def __init__(self, left: Expr, op: str, right: Expr):
        self.left = left
        self.op = op
        self.right = right

    def __repr__(self) -> str:
        return f"({self.left} {self.op} {self.right})"

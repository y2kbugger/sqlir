"""Relational expression AST.

This module defines the user-facing expression objects built from model field
access like ``Person.name == \"Alice\"``. It does not emit SQL text.
"""

from typing import Any


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
    def __init__(self, name: str, model: Any = None, target_model: Any = None):
        self._name = name
        self._model = model  # Root model where this field expression started (e.g. Employee for Employee.department.name)
        self._target_model = target_model  # Final model in chain (e.g. Manager for Employee.department.manager) or None if the final field is not a FK to a TableRow

    def __getattr__(self, item: str) -> FieldExpr:
        if item.startswith("_"):
            raise AttributeError(item)

        target = self._target_model
        if target is None:
            raise AttributeError(
                f"cannot access {item!r} on {self!r}: field type is not a foreign-key model",
            )

        fields_by_name = target.__fields_by_name__
        if item not in fields_by_name:
            raise AttributeError(f"{target.__name__!r} has no field {item!r}")

        field = fields_by_name[item]
        next_target = field.type if field.is_fk else None
        return FieldExpr(f"{self._name}.{item}", self._model, target_model=next_target)

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

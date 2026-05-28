"""Relational expression AST.

This module defines the user-facing expression objects built from model field
access like ``Person.name == \"Alice\"``. It does not emit SQL text.
"""

from typing import Any


class Expr:
    __hash__ = object.__hash__

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
    def __init__(self, name: str, model: Any = None):
        self._name = name
        self._model = model

    def __getattr__(self, item: str) -> FieldExpr:
        if item.startswith("_"):
            raise AttributeError(item)
        return FieldExpr(f"{self._name}.{item}", self._model)

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

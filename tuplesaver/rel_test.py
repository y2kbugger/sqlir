import pytest

from .model import TableRow
from .rel import BinaryExpr, FieldExpr, LogicalExpr


class Employee(TableRow):
    name: str
    department: Department


class Department(TableRow):
    name: str


def test_ast_generation():
    # Test field expression
    expr = Employee.name == "Alice"
    assert isinstance(expr, BinaryExpr)
    assert isinstance(expr.left, FieldExpr)
    assert expr.left._name == "name"  # noqa: SLF001
    assert expr.op == "=="
    assert expr.right == "Alice"

    # Test path traversal
    expr2 = Employee.department.name == "HR"
    assert isinstance(expr2, BinaryExpr)
    assert isinstance(expr2.left, FieldExpr)
    assert expr2.left._name == "department.name"  # noqa: SLF001
    assert expr2.op == "=="

    # Test logical combinations
    expr3 = (Employee.name == "Alice") | (Employee.department.name == "HR")
    assert isinstance(expr3, LogicalExpr)
    assert expr3.op == "OR"
    assert isinstance(expr3.left, BinaryExpr)
    assert isinstance(expr3.right, BinaryExpr)


def test_id_shortcut():
    expr = Employee.Id(42)
    assert isinstance(expr, BinaryExpr)
    assert isinstance(expr.left, FieldExpr)
    assert expr.left._name == "id"  # noqa: SLF001
    assert expr.op == "=="
    assert expr.right == 42


def test_unknown_field_raises_attribute_error():
    with pytest.raises(AttributeError, match="nonexistent"):
        Employee.nonexistent  # noqa: B018


def test_chained_fk_access_valid():
    # ``department`` is a FK to Department, ``name`` is a field on Department
    expr = Employee.department.name
    assert isinstance(expr, FieldExpr)
    assert expr._name == "department.name"  # noqa: SLF001
    assert expr._model is Employee  # noqa: SLF001

    # ``id`` is inherited from TableRow
    expr_id = Employee.department.id
    assert isinstance(expr_id, FieldExpr)
    assert expr_id._name == "department.id"  # noqa: SLF001


def test_chained_fk_access_unknown_field_raises():
    with pytest.raises(AttributeError, match=r"Department.*nonexistent"):
        Employee.department.nonexistent  # noqa: B018


def test_chained_access_through_non_fk_raises():
    # ``name`` is a ``str`` field, not a foreign key — further access is invalid.
    with pytest.raises(AttributeError, match="not a foreign-key model"):
        Employee.name.anything  # ty:ignore[unresolved-attribute]  # noqa: B018


# Models for validating that chain validation uses the FK target, not the root.
class Parent(TableRow):
    shared: str
    child: Child
    parent_only: int


class Child(TableRow):
    shared: str
    child_only: int


def test_chained_access_validates_against_fk_target_not_root():
    # ``child_only`` exists only on Child, not on Parent. Naive impls that
    # validate against the root model (Parent) would reject this even though
    # it's a legitimate chain. Conversely, ``parent_only`` exists on Parent
    # but not on Child, so it must be rejected on the chain.
    expr = Parent.child.child_only
    assert isinstance(expr, FieldExpr)
    assert expr._name == "child.child_only"  # noqa: SLF001

    with pytest.raises(AttributeError, match=r"Child.*parent_only"):
        Parent.child.parent_only  # noqa: B018

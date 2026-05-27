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
    assert expr.left._name == "name"
    assert expr.op == "=="
    assert expr.right == "Alice"

    # Test path traversal
    expr2 = Employee.department.name == "HR"
    assert isinstance(expr2, BinaryExpr)
    assert isinstance(expr2.left, FieldExpr)
    assert expr2.left._name == "department.name"
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
    assert expr.left._name == "id"
    assert expr.op == "=="
    assert expr.right == 42

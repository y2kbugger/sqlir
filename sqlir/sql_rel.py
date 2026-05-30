"""Lower `rel.py` expressions to SQL fragments.

This module compiles the relational AST (and embedded t-strings) into WHERE
clause fragments and scalar subqueries. Whole-statement templates that
splice these fragments live in `sql.py`.

This module should only be used by `sql.py` and test code.
This module should only depend on `model.py` and `rel.py`
"""

from collections.abc import Iterator
from typing import Any, cast

from .model import RowMeta, TableRow
from .rel import BinaryExpr, FieldExpr, LogicalExpr

# ---------------------------------------------------------------------------
# FK path traversal
# ---------------------------------------------------------------------------


def _walk_fk_hops(BaseModel: type[TableRow], attrs: list[str]) -> Iterator[tuple[str, str, type[TableRow], str]]:
    """Walk a chain of FK attributes from `BaseModel`.

    Yields `(current_alias, attr, next_model, next_alias)` for each hop.
    The first hop starts at the base table's own name; subsequent aliases
    are joined with underscores to remain unique within a query.
    """
    base_table = BaseModel.__tablename__
    current_model: type[TableRow] = BaseModel
    current_alias = base_table
    for attr in attrs:
        field = current_model.__fields_by_name__[attr]
        next_model = cast(type[TableRow], field.type)
        next_alias = f"{current_alias}_{attr}" if current_alias != base_table else attr
        yield current_alias, attr, next_model, next_alias
        current_model = next_model
        current_alias = next_alias


def _build_scalar_subquery(BaseModel: type[TableRow], path: str) -> str:
    """Compile a dotted FK path to a scalar SQL expression (nested SELECT per hop)."""
    parts = path.split('.')
    base_table = BaseModel.__tablename__
    if len(parts) == 1:
        return f"{base_table}.{parts[0]}"

    hops = list(_walk_fk_hops(BaseModel, parts[:-1]))
    last_alias = hops[-1][3]
    expr = f"{last_alias}.{parts[-1]}"
    for depth, (current_alias, attr, next_model, next_alias) in enumerate(reversed(hops)):
        indent = "    " * (len(hops) - 1 - depth)
        expr = f"(\n{indent}    SELECT {expr}\n{indent}    FROM {next_model.__tablename__} {next_alias}\n{indent}    WHERE {next_alias}.id = {current_alias}.{attr}\n{indent})"
    return expr


def _build_exists(BaseModel: type[TableRow], path: str, op: str, value_sql: str) -> str:
    """Compile a dotted FK path comparison to a (nested) EXISTS semi-join."""
    op = {"==": "="}.get(op, op)
    parts = path.split('.')
    base_table = BaseModel.__tablename__
    if len(parts) == 1:
        return f"{base_table}.{parts[0]} {op} {value_sql}"

    hops = list(_walk_fk_hops(BaseModel, parts[:-1]))
    last_alias = hops[-1][3]
    inner = f"{last_alias}.{parts[-1]} {op} {value_sql}"
    for depth, (current_alias, attr, next_model, next_alias) in enumerate(reversed(hops)):
        indent = "    " * (len(hops) - 1 - depth)
        inner = f"EXISTS (\n{indent}    SELECT 1 FROM {next_model.__tablename__} {next_alias}\n{indent}    WHERE {next_alias}.id = {current_alias}.{attr}\n{indent}    AND {inner}\n{indent})"
    return inner


# ---------------------------------------------------------------------------
# AST / t-string compilation
# ---------------------------------------------------------------------------


def _compile_field_comparison(left: FieldExpr, op: str, value_sql: str) -> str:
    """Render `left <op> value_sql` — using EXISTS if `left` traverses an FK chain."""
    if left._model:  # noqa: SLF001
        return _build_exists(left._model, left._name, op, value_sql)  # noqa: SLF001
    field_name = getattr(left, "_name", str(left))
    op = {"==": "="}.get(op, op)
    return f"{field_name} {op} {value_sql}"


def _bind_param(value: Any, params: dict[str, Any], param_idx: int, name: str | None = None) -> tuple[str, int]:
    """Register `value` as a named parameter and return its `:<name>` placeholder.

    If `name` is provided and is a valid identifier not already bound, it is
    used directly so callers can override it by name later. Otherwise a
    generated `p<idx>` name is used.
    """

    # Prefer using the expression name as the parameter name, if it's a valid identifier and not already taken.
    if name and name.isidentifier() and name not in params:
        params[name] = value
        return f":{name}", param_idx

    # Fall back to a generated name.
    param_name = f"p{param_idx}"
    params[param_name] = value
    return f":{param_name}", param_idx + 1


def _compile_tstring(expr: Any, params: dict[str, Any], param_idx: int) -> tuple[str, int]:
    """Compile a PEP 750 t-string with FieldExpr / sub-expression / literal interpolations."""
    sql_parts: list[str] = []
    for i, string_part in enumerate(expr.strings):
        sql_parts.append(string_part)
        if i >= len(expr.interpolations):
            continue
        interp = expr.interpolations[i]
        val = interp.value
        if isinstance(val, RowMeta):
            sql_parts.append(val.__tablename__)
        elif isinstance(val, FieldExpr) and val._model:  # noqa: SLF001
            sql_parts.append(_build_scalar_subquery(val._model, val._name))  # noqa: SLF001
        elif hasattr(val, "_name"):
            sql_parts.append(val._name)  # noqa: SLF001
        elif hasattr(val, "op"):
            sub_sql, param_idx = compile_expr(val, params, param_idx)
            sql_parts.append(sub_sql)
        else:
            placeholder, param_idx = _bind_param(val, params, param_idx, name=interp.expression)
            sql_parts.append(placeholder)
    return "".join(sql_parts), param_idx


def compile_expr(expr: Any, params: dict[str, Any], param_idx: int = 0) -> tuple[str, int]:
    """Compile a rel expression / t-string / id-int to a SQL fragment.

    Returns `(sql_fragment, next_param_idx)`. Bound values are added to
    `params` under generated `p<idx>` names.
    """
    if hasattr(expr, "interpolations") and hasattr(expr, "strings"):
        return _compile_tstring(expr, params, param_idx)
    if isinstance(expr, int):
        placeholder, param_idx = _bind_param(int(expr), params, param_idx)
        return f"id = {placeholder}", param_idx
    if isinstance(expr, BinaryExpr):
        placeholder, param_idx = _bind_param(expr.right, params, param_idx)
        return _compile_field_comparison(expr.left, expr.op, placeholder), param_idx
    if isinstance(expr, LogicalExpr):
        left_sql, param_idx = compile_expr(expr.left, params, param_idx)
        right_sql, param_idx = compile_expr(expr.right, params, param_idx)
        return f"({left_sql} {expr.op} {right_sql})", param_idx
    raise ValueError(f"Unknown expression type: {type(expr)}")


__all__ = ["compile_expr"]

"""Compile rel.py expressions into SQL fragments.

This module lowers the relational AST into WHERE-clause and scalar-subquery
fragments. Whole-statement templates stay in sql.py.
"""

from typing import Any, cast

from .model import TableRow
from .rel import BinaryExpr, FieldExpr, LogicalExpr


def _build_exists(BaseModel: type[TableRow], path: str, op: str, value_sql: str) -> str:
    parts = path.split('.')
    op = {"==": "="}.get(op, op)
    base_table_name = BaseModel.__tablename__

    if len(parts) == 1:
        return f"{base_table_name}.{parts[0]} {op} {value_sql}"

    outer_alias = base_table_name

    def step(i: int, current_model: type[TableRow], current_alias: str, indent: str) -> str:
        if i == len(parts) - 1:
            return f"{current_alias}.{parts[i]} {op} {value_sql}"

        attr = parts[i]
        field = current_model.__fields_by_name__[attr]
        next_model = cast(type[TableRow], field.type)
        next_alias = f"{current_alias}_{attr}" if current_alias != base_table_name else attr

        inner = step(i + 1, next_model, next_alias, indent + "    ")

        return f"EXISTS (\n{indent}    SELECT 1 FROM {next_model.__tablename__} {next_alias}\n{indent}    WHERE {next_alias}.id = {current_alias}.{attr}\n{indent}    AND {inner}\n{indent})"

    return step(0, BaseModel, outer_alias, "")


def _build_scalar_subquery(BaseModel: type[TableRow], path: str) -> str:
    parts = path.split('.')
    base_table_name = BaseModel.__tablename__
    if len(parts) == 1:
        return f"{base_table_name}.{parts[0]}"

    outer_alias = base_table_name

    def step(i: int, current_model: type[TableRow], current_alias: str) -> str:
        if i == len(parts) - 1:
            return f"{current_alias}.{parts[i]}"

        attr = parts[i]
        field = current_model.__fields_by_name__[attr]
        next_model = cast(type[TableRow], field.type)
        next_alias = f"{current_alias}_{attr}" if current_alias != base_table_name else attr

        inner = step(i + 1, next_model, next_alias)

        return f"(SELECT {inner} FROM {next_model.__tablename__} {next_alias} WHERE {next_alias}.id = {current_alias}.{attr})"

    return step(0, BaseModel, outer_alias)


def compile_expr(expr: Any, params: dict[str, Any], param_idx: int = 0) -> tuple[str, int]:
    if hasattr(expr, "interpolations") and hasattr(expr, "strings"):
        sql_parts = []
        strings = expr.strings
        interpolations = expr.interpolations
        for i, string_part in enumerate(strings):
            sql_parts.append(string_part)
            if i < len(interpolations):
                interp = interpolations[i]
                val = interp.value
                if isinstance(val, FieldExpr) and val._model:  # noqa: SLF001
                    sql_parts.append(_build_scalar_subquery(val._model, val._name))  # noqa: SLF001
                elif hasattr(val, "_name"):
                    sql_parts.append(val._name)  # noqa: SLF001
                elif hasattr(val, "op"):
                    sub_sql, param_idx = compile_expr(val, params, param_idx)
                    sql_parts.append(sub_sql)
                else:
                    param_name = f"p{param_idx}"
                    params[param_name] = val
                    sql_parts.append(f":{param_name}")
                    param_idx += 1
        return "".join(sql_parts), param_idx
    elif isinstance(expr, int):
        param_name = f"p{param_idx}"
        params[param_name] = int(expr)
        return f"id = :{param_name}", param_idx + 1
    elif isinstance(expr, BinaryExpr):
        param_name = f"p{param_idx}"
        params[param_name] = expr.right

        if isinstance(expr.left, FieldExpr) and expr.left._model:  # noqa: SLF001
            sql = _build_exists(expr.left._model, expr.left._name, expr.op, f":{param_name}")  # noqa: SLF001
            return sql, param_idx + 1
        else:
            field_name = getattr(expr.left, "_name", str(expr.left))
            op = {"==": "="}.get(expr.op, expr.op)
            return f"{field_name} {op} :{param_name}", param_idx + 1
    elif isinstance(expr, LogicalExpr):
        left_sql, param_idx = compile_expr(expr.left, params, param_idx)
        right_sql, param_idx = compile_expr(expr.right, params, param_idx)
        return f"({left_sql} {expr.op} {right_sql})", param_idx
    else:
        raise ValueError(f"Unknown expression type: {type(expr)}")

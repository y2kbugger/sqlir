from typing import Any

from .rel import BinaryExpr, FieldExpr, LogicalExpr


def _build_exists(BaseModel: type, path: str, op: str, value_sql: str) -> str:
    parts = path.split('.')
    op = {"==": "="}.get(op, op)

    if len(parts) == 1:
        return f"{BaseModel.meta.table_name}.{parts[0]} {op} {value_sql}"

    meta = BaseModel.meta
    outer_alias = BaseModel.meta.table_name

    def step(i: int, current_meta, current_alias: str, indent: str) -> str:
        if i == len(parts) - 1:
            return f"{current_alias}.{parts[i]} {op} {value_sql}"

        attr = parts[i]
        field = next(f for f in current_meta.fields if f.name == attr)
        next_meta = field.type.meta
        next_alias = f"{current_alias}_{attr}" if current_alias != BaseModel.meta.table_name else attr

        inner = step(i + 1, next_meta, next_alias, indent + "    ")

        return f"EXISTS (\n{indent}    SELECT 1 FROM {next_meta.table_name} {next_alias}\n{indent}    WHERE {next_alias}.id = {current_alias}.{attr}\n{indent}    AND {inner}\n{indent})"

    return step(0, meta, outer_alias, "")


def _build_scalar_subquery(BaseModel: type, path: str) -> str:
    parts = path.split('.')
    if len(parts) == 1:
        return f"{BaseModel.meta.table_name}.{parts[0]}"

    meta = BaseModel.meta
    outer_alias = BaseModel.meta.table_name

    def step(i: int, current_meta, current_alias: str) -> str:
        if i == len(parts) - 1:
            return f"{current_alias}.{parts[i]}"

        attr = parts[i]
        field = next(f for f in current_meta.fields if f.name == attr)
        next_meta = field.type.meta
        next_alias = f"{current_alias}_{attr}" if current_alias != BaseModel.meta.table_name else attr

        inner = step(i + 1, next_meta, next_alias)

        return f"(SELECT {inner} FROM {next_meta.table_name} {next_alias} WHERE {next_alias}.id = {current_alias}.{attr})"

    return step(0, meta, outer_alias)


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
                if isinstance(val, FieldExpr) and val._model:
                    sql_parts.append(_build_scalar_subquery(val._model, val._name))
                elif hasattr(val, "_name"):
                    sql_parts.append(val._name)
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

        if isinstance(expr.left, FieldExpr) and expr.left._model:
            sql = _build_exists(expr.left._model, expr.left._name, expr.op, f":{param_name}")
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

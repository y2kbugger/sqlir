"""Lazy relationship proxy."""

from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from .engine import Engine
    from .model import TableRow
else:
    Engine = Any
    TableRow = Any


class Rows[Model](tuple[Model, ...]):
    """An immutable, iterable collection of model rows (a has_many backref result).

    It subclasses `tuple`, so it is hashable, ordered, indexable, and cannot be
    mutated — you can't `append` to a relationship. Indexing yields the
    contained model (`squad.players[0]` is a `Player`). That element typing is
    also what makes typed predicate traversal work: `Squad.players[0].number`
    type-checks because `[0]` is a `Player`, whereas `Squad.players.number`
    would not (a collection has no `number`).
    """

    __slots__ = ()

    def __repr__(self) -> str:
        return f"Rows({list(self)!r})"


class Lazy[Model]:
    __slots__ = ("_cached", "_engine", "_id", "_model")

    def __init__(self, engine: Engine, model: type[TableRow], id_: int):
        self._engine = engine
        self._model = model
        self._id = id_
        self._cached = None

    def _obj(self) -> Model:
        if self._cached is None:
            self._cached = self._engine.find(self._model, self._id)
        return cast(Model, self._cached)

    def __hash__(self):
        return hash((self._model, self._id))

    def __eq__(self, other: object) -> bool:
        from .model import TableRow

        if isinstance(other, int):
            return self._id == other
        elif isinstance(other, TableRow) and type(other) is self._model:
            return self._id == other.id
        elif isinstance(other, Lazy):
            return self._model == other._model and self._id == other._id
        return False

    def __repr__(self):
        if self._cached is None:
            return f"<{self.__class__.__name__}[{self._model.__name__}]:{self._id} (pending)>"
        return f"<{self.__class__.__name__}:{self._cached!r}>"


_UNFETCHED = object()


class LazyCollection[Model]:
    """Deferred reverse-relation loader (the plural sibling of `Lazy`).

    Holds the child model + the child's FK field name pointing back at the
    parent. On first access it runs one `select` (`child.<fk> == parent_id`)
    and caches the full materialized result: a `list` for has_many, a single
    row or `None` for has_one.
    """

    __slots__ = ("_cached", "_child_model", "_engine", "_fk_name", "_is_many", "_parent_id")

    def __init__(self, engine: Engine, child_model: type[TableRow], fk_name: str, parent_id: int, is_many: bool):
        self._engine = engine
        self._child_model = child_model
        self._fk_name = fk_name
        self._parent_id = parent_id
        self._is_many = is_many
        self._cached = _UNFETCHED

    def _obj(self) -> Any:
        if self._cached is _UNFETCHED:
            from .rel import FieldExpr

            target = FieldExpr(self._fk_name, self._child_model) == self._parent_id
            cursor = self._engine.select(self._child_model, target)
            self._cached = Rows(cursor.fetchall()) if self._is_many else cursor.fetchone()
        return self._cached

    def __repr__(self):
        kind = "many" if self._is_many else "one"
        if self._cached is _UNFETCHED:
            return f"<{self.__class__.__name__}[{self._child_model.__name__}] {kind} via {self._fk_name}={self._parent_id} (pending)>"
        return f"<{self.__class__.__name__}:{self._cached!r}>"

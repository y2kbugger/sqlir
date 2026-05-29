"""Lazy relationship proxy."""

from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from .engine import Engine
    from .model import TableRow
else:
    Engine = Any
    TableRow = Any


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

from __future__ import annotations

import datetime as dt
import enum
from dataclasses import dataclass

import pytest

from .engine import Engine
from .model import TableRow


def test_can_store_and_retrieve_datetime_as_iso(engine: Engine) -> None:
    class T(TableRow):
        date: dt.datetime

    engine.ensure_table_created(T)
    now = dt.datetime.now()
    row = engine.save(T(now))

    returned_row = engine.find(T, row.id)

    assert returned_row.date == now


def test_can_store_and_retrieve_date_as_iso(engine: Engine) -> None:
    class T(TableRow):
        date: dt.date

    engine.ensure_table_created(T)
    today = dt.date.today()
    row = engine.save(T(today))

    returned_row = engine.find(T, row.id)

    assert returned_row.date == today


def test_can_store_and_retrieve_bool_as_int(engine: Engine) -> None:
    class T(TableRow):
        flag: bool

    engine.ensure_table_created(T)
    row = engine.save(T(True))

    returned_row = engine.find(T, row.id)

    assert returned_row.flag is True

    row = engine.save(T(False))

    returned_row = engine.find(T, row.id)

    assert returned_row.flag is False


def test_can_store_and_retrieve_enum_as_json(engine: Engine) -> None:
    class Status(str, enum.Enum):
        ACTIVE = "active"
        DISABLED = "disabled"

    class T(TableRow):
        status: Status

    engine.ensure_table_created(T)
    row = engine.save(T(Status.ACTIVE))

    returned_row = engine.find(T, row.id)

    assert returned_row.status is Status.ACTIVE


def test_can_store_and_retrieve_list_as_json(engine: Engine) -> None:
    class T(TableRow):
        names: list

    engine.ensure_table_created(T)
    names = ["Alice", "Bob", "Charlie", 2]
    row = engine.save(T(names))

    returned_row = engine.find(T, row.id)

    assert returned_row.names == names


def test_can_store_and_retrieve_typed_list_as_json(engine: Engine) -> None:
    class T(TableRow):
        names: list[str]

    engine.ensure_table_created(T)
    names = ["Alice", "Bob", "Charlie"]
    row = engine.save(T(names))

    returned_row = engine.find(T, row.id)

    assert returned_row.names == names


def test_can_store_and_retrieve_dict_as_json(engine: Engine) -> None:
    class T(TableRow):
        names: dict

    engine.ensure_table_created(T)
    names = {"Alice": 1, "Bob": 2, "Charlie": 3}
    row = engine.save(T(names))

    returned_row = engine.find(T, row.id)

    assert returned_row.names == names


def test_can_store_and_retrieve_typed_dict_as_json(engine: Engine) -> None:
    class T(TableRow):
        counts: dict[str, int]

    engine.ensure_table_created(T)
    counts = {"Alice": 1, "Bob": 2, "Charlie": 3}
    row = engine.save(T(counts))

    returned_row = engine.find(T, row.id)

    assert returned_row.counts == counts


def test_can_store_and_retrieve_nested_typed_json_as_json(engine: Engine) -> None:
    class T(TableRow):
        payload: list[dict[str, int]]

    engine.ensure_table_created(T)
    payload = [{"a": 1}, {"b": 2, "c": 3}]
    row = engine.save(T(payload))

    returned_row = engine.find(T, row.id)

    assert returned_row.payload == payload


@dataclass
class JsonDataClass:
    name: str
    score: int


def test_can_store_and_retrieve_dataclass_as_json(engine: Engine) -> None:
    class T(TableRow):
        payload: JsonDataClass

    engine.ensure_table_created(T)
    payload = JsonDataClass(name="Alice", score=42)
    row = engine.save(T(payload))

    returned_row = engine.find(T, row.id)

    assert returned_row.payload == payload


def test_can_store_and_retrieve_list_of_dataclass_as_json(engine: Engine) -> None:
    class T(TableRow):
        payload: list[JsonDataClass]

    engine.ensure_table_created(T)
    payload = [
        JsonDataClass(name="Alice", score=42),
        JsonDataClass(name="Bob", score=7),
    ]
    row = engine.save(T(payload))

    returned_row = engine.find(T, row.id)

    assert returned_row.payload == payload


def test_can_store_and_retrieve_nested_dataclass_json_as_json(engine: Engine) -> None:
    class T(TableRow):
        payload: dict[str, list[JsonDataClass]]

    engine.ensure_table_created(T)
    payload = {
        "alpha": [JsonDataClass(name="Alice", score=42)],
        "beta": [JsonDataClass(name="Bob", score=7), JsonDataClass(name="Charlie", score=3)],
    }
    row = engine.save(T(payload))

    returned_row = engine.find(T, row.id)

    assert returned_row.payload == payload


def test_raises_on_json_when_not_msgspec_encodeable(engine: Engine) -> None:
    class T(TableRow):
        dates: list

    engine.ensure_table_created(T)

    class Unserializable:
        pass

    unserializable_object = Unserializable()

    with pytest.raises(TypeError, match="Encoding objects of type Unserializable is unsupported"):
        engine.save(T([unserializable_object]))

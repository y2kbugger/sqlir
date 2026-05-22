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


def test_datetime_roundtrip_preserves_microseconds(engine: Engine) -> None:
    class T(TableRow):
        ts: dt.datetime

    engine.ensure_table_created(T)
    ts = dt.datetime(2024, 6, 15, 12, 30, 45, 123456)
    row = engine.save(T(ts))

    assert engine.find(T, row.id).ts == ts


def test_datetime_roundtrip_preserves_utc_timezone(engine: Engine) -> None:
    class T(TableRow):
        ts: dt.datetime

    engine.ensure_table_created(T)
    ts = dt.datetime(2024, 6, 15, 12, 0, 0, tzinfo=dt.UTC)
    row = engine.save(T(ts))

    returned = engine.find(T, row.id)
    assert returned.ts == ts
    assert returned.ts.tzinfo is not None


def test_naive_datetime_lexical_sort_order(engine: Engine) -> None:
    """Naive ISO-8601 datetimes stored by msgspec sort correctly via ORDER BY."""

    class T(TableRow):
        ts: dt.datetime

    engine.ensure_table_created(T)
    t1 = dt.datetime(2023, 12, 31, 23, 59, 59)
    t2 = dt.datetime(2024, 1, 1, 0, 0, 0)
    t3 = dt.datetime(2024, 6, 15, 12, 0, 0)
    t4 = dt.datetime(2024, 6, 15, 12, 0, 0, 999999)

    # insert out of order
    for ts in [t3, t1, t4, t2]:
        engine.save(T(ts))

    rows = engine.query(T, "SELECT * FROM T ORDER BY ts").fetchall()
    assert [r.ts for r in rows] == [t1, t2, t3, t4]


def test_naive_datetime_between_predicate(engine: Engine) -> None:
    """Naive ISO-8601 datetimes work correctly with SQL BETWEEN."""

    class T(TableRow):
        ts: dt.datetime

    engine.ensure_table_created(T)
    t_before = dt.datetime(2023, 12, 31, 23, 59, 59)
    t_start = dt.datetime(2024, 1, 1, 0, 0, 0)
    t_mid = dt.datetime(2024, 6, 15, 12, 0, 0)
    t_end = dt.datetime(2024, 12, 31, 23, 59, 59)
    t_after = dt.datetime(2025, 1, 1, 0, 0, 0)

    for ts in [t_before, t_start, t_mid, t_end, t_after]:
        engine.save(T(ts))

    rows = engine.query(
        T,
        "SELECT * FROM T WHERE ts BETWEEN ? AND ? ORDER BY ts",
        (t_start, t_end),
    ).fetchall()
    assert [r.ts for r in rows] == [t_start, t_mid, t_end]


def test_mixing_naive_and_aware_datetime_breaks_sort_order(engine: Engine) -> None:
    """
    Lexical sort is WRONG when mixing naive and timezone-aware datetimes.
    UTC-aware '2024-06-15T12:00:00Z' sorts AFTER naive '2024-06-15T12:00:00.999999'
    because 'Z' sorts after '.' in ASCII.
    This is a known limitation of lexical string sorting: always store datetimes
    in one consistent form.
    """

    class T(TableRow):
        ts: dt.datetime

    engine.ensure_table_created(T)

    naive = dt.datetime(2024, 6, 15, 12, 0, 0)
    aware = dt.datetime(2024, 6, 15, 12, 0, 0, tzinfo=dt.UTC)
    with_us = dt.datetime(2024, 6, 15, 12, 0, 0, 999999)  # naive + microseconds

    for ts in [aware, naive, with_us]:
        engine.save(T(ts))

    rows = engine.query(T, "SELECT * FROM T ORDER BY ts").fetchall()
    stored_order = [r.ts for r in rows]

    # naive < naive+microseconds < aware
    # i.e. '12:00:00' < '12:00:00.999999' < '12:00:00Z'
    # This is NOT chronological order (aware == naive in wall time here)
    assert stored_order.index(naive) < stored_order.index(with_us)
    assert stored_order.index(with_us) < stored_order.index(aware)


def test_sqlite_datetime_funcs_working(engine: Engine) -> None:
    """
    Stored datetime values are saved as TEXT ISO strings (e.g. '2024-06-15T12:00:00'),
    so SQLite's native date functions (datetime, strftime, julianday, etc.)
    now work natively!
    """

    class T(TableRow):
        ts: dt.datetime

    engine.ensure_table_created(T)
    engine.save(T(dt.datetime(2024, 6, 15, 12, 0, 0, 123456)))

    cur = engine.connection.cursor()

    cur.execute("SELECT typeof(ts) FROM T")
    assert cur.fetchone()[0] == "text"

    cur.execute("SELECT datetime(ts), strftime('%Y', ts) FROM T")
    row = cur.fetchone()
    # SQLite's datetime() truncates fractional seconds
    assert row == ("2024-06-15 12:00:00", "2024")


def test_datetime_string_literals_in_sql_match(engine: Engine) -> None:
    """
    Because stored datetimes are TEXT, SQL string literals evaluate and
    can match exact representations natively!
    """

    class T(TableRow):
        ts: dt.datetime

    engine.ensure_table_created(T)
    ts = dt.datetime(2024, 6, 15, 12, 0, 0)
    engine.save(T(ts))

    cur = engine.connection.cursor()

    # raw string literal does successfully match our TEXT storage
    cur.execute("SELECT COUNT(*) FROM T WHERE ts = '2024-06-15T12:00:00'")
    assert cur.fetchone()[0] == 1

    # adapted ? parameter produces the same BLOB — this works
    from .adaptconvert import AdaptConvertRegistry

    registry = AdaptConvertRegistry()
    adapted = registry.adapt_value(ts)
    cur.execute("SELECT COUNT(*) FROM T WHERE ts = ?", (adapted,))
    assert cur.fetchone()[0] == 1


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


def test_can_store_and_retrieve_strenum(engine: Engine) -> None:
    class Status(enum.StrEnum):
        ACTIVE = "active"
        DISABLED = "disabled"

    class T(TableRow):
        status: Status

    engine.ensure_table_created(T)
    row = engine.save(T(Status.ACTIVE))

    returned_row = engine.find(T, row.id)

    assert returned_row.status is Status.ACTIVE


def test_can_store_and_retrieve_intenum(engine: Engine) -> None:
    class Status(enum.IntEnum):
        ACTIVE = 1
        DISABLED = 2

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


def test_can_store_and_retrieve_a_list_of_datetimes_as_json(engine: Engine) -> None:
    class T(TableRow):
        payload: list[dt.datetime]

    engine.ensure_table_created(T)
    payload = [
        dt.datetime(2024, 6, 15, 12, 0, 0),
        dt.datetime(2024, 6, 16, 13, 30, 0),
    ]
    row = engine.save(T(payload))

    returned_row = engine.find(T, row.id)

    assert returned_row.payload == payload


def test_can_store_and_retrieve_a_set_of_int_as_json(engine: Engine) -> None:
    class T(TableRow):
        payload: set[int]

    engine.ensure_table_created(T)
    payload = {1, 2, 3}
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


def test_comprehensive_sidechannel_storage_types_and_roundtrips(engine: Engine) -> None:
    """
    Test a comprehensive suite of Python types for both correct roundtripping
    through the ORM, AND test the actual backed storage representations via a
    raw SQLite cursor (to prove they are backed with the intended type affinity).
    """
    import dataclasses
    import datetime as dt
    from decimal import Decimal
    from enum import Enum

    import msgspec

    class Color(Enum):
        RED = "red"
        BLUE = "blue"

    class Priority(int, Enum):
        LOW = 1
        HIGH = 2

    @dataclasses.dataclass
    class MyDC:
        name: str

    class AllTypesModel(TableRow):
        # Native primitives
        i_val: int
        f_val: float
        s_val: str
        b: bool
        # Datetimes
        dt_val: dt.datetime
        d_val: dt.date
        t_val: dt.time
        # Buffers
        by_val: bytes
        ba_val: bytearray
        mv_val: memoryview
        # msgspec Fallbacks
        dict_val: dict
        list_val: list
        enum_val: Color
        custom_val: MyDC
        dec_val: Decimal
        set_val: set[str]
        tuple_val: tuple[int, str]
        dict_simple_val: dict[str, int]
        int_enum_val: Priority

    engine.ensure_table_created(AllTypesModel)
    eastern_tz = dt.timezone(dt.timedelta(hours=-4))

    # Definition format: (field_name, python_input_value, expected_sqlite_type, expected_db_raw_value, expected_to_builtins)
    matrix = [
        # Native primitives
        ("i_val", 42, "integer", 42, 42),
        ("f_val", 3.14, "real", 3.14, 3.14),
        ("s_val", "hello", "text", "hello", "hello"),
        ("b", True, "integer", 1, True),
        # Datetimes (Natively stored as unquoted strings)
        ("dt_val", dt.datetime(2024, 6, 15, 12, 0, 0, tzinfo=eastern_tz), "text", "2024-06-15T12:00:00-04:00", "2024-06-15T12:00:00-04:00"),
        ("d_val", dt.date(2024, 6, 15), "text", "2024-06-15", "2024-06-15"),
        ("t_val", dt.time(12, 0, 0), "text", "12:00:00", "12:00:00"),
        # Buffers (Natively stored as blobs)
        ("by_val", b"raw_bytes", "blob", b"raw_bytes", "cmF3X2J5dGVz"),
        ("ba_val", bytearray(b"byte_array"), "blob", b"byte_array", "Ynl0ZV9hcnJheQ=="),
        ("mv_val", memoryview(b"memory_view"), "blob", b"memory_view", "bWVtb3J5X3ZpZXc="),
        # Msgspec JSON fallbacks
        ("dict_val", {"key": "value"}, "text", '{"key":"value"}', {"key": "value"}),
        ("list_val", [1, 2, 3], "text", '[1,2,3]', [1, 2, 3]),
        ("enum_val", Color.RED, "text", "red", "red"),
        ("custom_val", MyDC(name="test"), "text", '{"name":"test"}', {"name": "test"}),
        ("dec_val", Decimal("123.45"), "text", "123.45", "123.45"),
        ("set_val", {"single_item"}, "text", '["single_item"]', ["single_item"]),
        ("tuple_val", (1, "two"), "text", '[1,"two"]', (1, "two")),
        ("dict_simple_val", {"k": 5}, "text", '{"k":5}', {"k": 5}),
        ("int_enum_val", Priority.HIGH, "integer", 2, 2),  # int enums use msgspec.to_builtins and map to INTEGER
    ]

    # Save to db
    record = AllTypesModel(**{m[0]: m[1] for m in matrix})
    saved = engine.save(record)

    cur = engine.connection.cursor()
    cols = [m[0] for m in matrix]

    # 1. Side-channel check via raw cursor for both types and literal values
    cur.execute(f"SELECT {', '.join(cols)} FROM AllTypesModel WHERE id = ?", (saved.id,))
    raw_values = cur.fetchone()

    cur.execute(f"SELECT {', '.join(f'typeof({c})' for c in cols)} FROM AllTypesModel WHERE id = ?", (saved.id,))
    raw_types = cur.fetchone()

    for i, (field, _, exp_type, exp_raw, _) in enumerate(matrix):
        assert raw_types[i] == exp_type, f"Field '{field}' expected type '{exp_type}', got '{raw_types[i]}'"
        assert raw_values[i] == exp_raw, f"Field '{field}' expected raw {exp_raw!r}, got {raw_values[i]!r}"

    # 2. Verify complete TupleSaver round-trip object inflation
    fetched = engine.find(AllTypesModel, saved.id)

    for field, inp_val, _, _, _ in matrix:
        fetched_val = getattr(fetched, field)
        if field == "mv_val":
            # memoryviews don't eq each other natively unless same identity, compare by bytes
            assert bytes(fetched_val) == bytes(inp_val)
        else:
            assert fetched_val == inp_val, f"Field '{field}' roundtrip failed: {fetched_val!r} != {inp_val!r}"

    # 3. Verify msgspec.to_builtins conversion
    for field, inp_val, _, _, exp_builtins in matrix:
        result = msgspec.to_builtins(inp_val)
        assert result == exp_builtins, f"Field '{field}' to_builtins failed: {result!r} != {exp_builtins!r}"


def test_sqlite_decimal_extension_support(engine: Engine) -> None:
    """
    Test whether the current SQLite/apsw build includes the optional 'decimal' extension (e.g. decimal_add).
    The decimal extension allows for arbitrary-precision decimal arithmetic on strings.
    If it is not included in the amalgamation, this test is safely skipped.
    """
    cur = engine.connection.cursor()
    try:
        cur.execute("SELECT decimal_add('1.2', '2.3')")
        result = cur.fetchone()[0]
        assert result == "3.5"
    except Exception as e:  # Catch any apsw SQLError
        if "no such function: decimal_add" in str(e):
            pytest.skip(f"SQLite decimal extension not loaded or supported in this apsw build: {e}")
        else:
            raise

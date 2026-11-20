"""Day 1 tests: DBC parsing + frame decoding."""

from pathlib import Path

import pytest

from candbc.dbc import DbcParseError, decode, load_dbc, parse_dbc, range_violations

DBC_PATH = Path(__file__).parent.parent / "data" / "power_window.dbc"


@pytest.fixture(scope="module")
def db():
    return load_dbc(DBC_PATH)


# --- parsing ------------------------------------------------------------------

def test_all_messages_found(db):
    names = {m.name for m in db.messages.values()}
    assert names == {"BCM_WindowSwitch", "DCU_WindowStatus", "EEC1", "HIL_Sensors"}


def test_message_header(db):
    msg = db.by_name("BCM_WindowSwitch")
    assert (msg.frame_id, msg.dlc, msg.sender) == (0x200, 8, "BCM")
    assert [s.name for s in msg.signals] == ["SwUp", "SwDown", "AliveCounter"]


def test_signal_attributes(db):
    s = db.by_name("DCU_WindowStatus").signal("MotorCurrent")
    assert (s.start_bit, s.length, s.little_endian, s.signed) == (8, 8, True, False)
    assert (s.scale, s.offset, s.minimum, s.maximum, s.unit) == (0.1, 0, 0, 25.5, "A")
    assert s.receivers == ["BCM"]


def test_motorola_and_signed_flags(db):
    msg = db.by_name("HIL_Sensors")
    assert msg.signal("PosRaw").little_endian is False
    assert msg.signal("Temperature").signed is True


def test_extended_id_flag_removed(db):
    """CSS guide: DBC stores 29-bit IDs with bit 31 set (0x8CF00400 -> 0x0CF00400)."""
    msg = db.by_name("EEC1")
    assert msg.is_extended and msg.frame_id == 0x0CF00400
    assert db.by_frame_id(0x0CF00400, is_extended=True) is msg
    assert db.by_frame_id(0x0CF00400) is None  # same number as 11-bit ID != same message


def test_cycle_times(db):
    assert db.by_name("BCM_WindowSwitch").cycle_time_ms == 20
    assert db.by_name("DCU_WindowStatus").cycle_time_ms == 100
    assert db.by_name("HIL_Sensors").cycle_time_ms is None


def test_value_table(db):
    assert db.by_name("DCU_WindowStatus").signal("MotorState").choices == {
        0: "Stop", 1: "Up", 2: "Down"}


# --- decoding -----------------------------------------------------------------

def test_engine_speed_example_from_guide(db):
    """Guide oracle: 0CF00400 FF FF FF 68 13 FF FF FF -> 621 rpm."""
    values = decode(db.by_name("EEC1"), bytes.fromhex("FFFFFF6813FFFFFF"))
    assert values["EngineSpeed"] == pytest.approx(621.0)


def test_decode_window_switch(db):
    # SwUp=1, SwDown=0, AliveCounter=5 -> byte0 = 0101 0001
    values = decode(db.by_name("BCM_WindowSwitch"), bytes([0x51]) + bytes(7))
    assert values == {"SwUp": 1, "SwDown": 0, "AliveCounter": 5}


def test_decode_window_status_with_value_table(db):
    # Pos 50 % (raw 100), 2.0 A (raw 20), MotorState Up, PinchFlag 1, Vbat 12.6 V
    data = bytes([100, 20, 0b0000_0101, 126, 0, 0, 0, 0])
    v = decode(db.by_name("DCU_WindowStatus"), data)
    assert v["Position"] == 50.0
    assert v["MotorCurrent"] == pytest.approx(2.0)
    assert v["MotorState"] == "Up"
    assert v["PinchFlag"] == 1 and v["DTC_SwitchTimeout"] == 0
    assert v["Vbat"] == pytest.approx(12.6)


def test_decode_motorola_and_negative(db):
    # PosRaw big-endian 0x1388 = 5000 -> 50.00 %; Temperature 0xF6 = -10 degC
    v = decode(db.by_name("HIL_Sensors"), bytes([0x13, 0x88, 0xF6]) + bytes(5))
    assert v["PosRaw"] == pytest.approx(50.0)
    assert v["Temperature"] == -10


def test_short_payload_rejected(db):
    with pytest.raises(ValueError, match="past the end"):
        decode(db.by_name("DCU_WindowStatus"), bytes(2))


# --- plausibility (a tester's view of the DBC) --------------------------------

def test_range_violation_detected(db):
    # Position raw 255 -> 127.5 % > 100 %
    assert range_violations(db.by_name("DCU_WindowStatus"), bytes([255]) + bytes(7)) == [
        "Position=127.5 outside [0|100]"]


def test_no_range_violation_for_valid_frame(db):
    assert range_violations(db.by_name("DCU_WindowStatus"), bytes([100, 20, 1, 126, 0, 0, 0, 0])) == []


# --- negative tests: broken DBC files -----------------------------------------

@pytest.mark.parametrize(
    "bad_line",
    [
        ' SG_ X : 0|8@2+ (1,0) [0|1] "" A',      # byte order must be 0 or 1
        ' SG_ X : 0|8@1+ (abc,0) [0|1] "" A',    # scale not a number
        ' SG_ X : 0|0@1+ (1,0) [0|1] "" A',      # length 0
    ],
)
def test_bad_signal_line_reports_line_number(bad_line):
    with pytest.raises(DbcParseError, match="line 2"):
        parse_dbc("BO_ 1 M: 8 A\n" + bad_line)


def test_signal_before_message_rejected():
    with pytest.raises(DbcParseError, match="before any BO_"):
        parse_dbc(' SG_ X : 0|8@1+ (1,0) [0|1] "" A')


def test_duplicate_message_id_rejected():
    with pytest.raises(DbcParseError, match="duplicate"):
        parse_dbc("BO_ 1 A: 8 X\nBO_ 1 B: 8 X")


def test_multiplexed_message_not_silently_decoded():
    db = parse_dbc('BO_ 1 M: 8 A\n SG_ Mux M : 0|8@1+ (1,0) [0|0] "" B')
    with pytest.raises(NotImplementedError):
        decode(db.by_name("M"), bytes(8))

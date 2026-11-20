"""Parse a DBC file (the subset real projects use) and decode CAN frames.

Supported: BO_ (messages), SG_ (signals, Intel/Motorola, signed/unsigned),
BA_ "GenMsgCycleTime", VAL_ (value tables), 29-bit IDs.
Not yet: multiplexed signals (M / mNN), CAN FD > 8 bytes, SIG_VALTYPE_ floats.

Reference: CSS Electronics "CAN bus - the ultimate guide", ch. "CAN DBC File
Explained" (message syntax p. 196, signal syntax p. 197-198).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

EXTENDED_FLAG = 0x80000000

_BO = re.compile(r"^BO_\s+(\d+)\s+(\w+)\s*:\s*(\d+)\s+(\w+)\s*$")
_SG = re.compile(
    r"^SG_\s+(\w+)\s*(M|m\d+)?\s*:\s*"
    r"(\d+)\|(\d+)@([01])([+-])\s*"
    r"\(\s*([^,\s]+)\s*,\s*([^)\s]+)\s*\)\s*"
    r"\[\s*([^|\s]+)\s*\|\s*([^\]\s]+)\s*\]\s*"
    r'"([^"]*)"\s*(.*)$'
)
_CYCLE = re.compile(r'^BA_\s+"GenMsgCycleTime"\s+BO_\s+(\d+)\s+(\d+)\s*;')
_VAL = re.compile(r"^VAL_\s+(\d+)\s+(\w+)\s+(.*);\s*$")
_VAL_PAIR = re.compile(r'(-?\d+)\s+"([^"]*)"')


class DbcParseError(ValueError):
    """Raised with the line number, so a broken DBC is easy to fix."""


@dataclass
class Signal:
    name: str
    start_bit: int
    length: int
    little_endian: bool
    signed: bool
    scale: float
    offset: float
    minimum: float
    maximum: float
    unit: str
    receivers: list[str]
    multiplex: str | None = None
    choices: dict[int, str] = field(default_factory=dict)


@dataclass
class Message:
    frame_id: int          # without the DBC extended flag
    is_extended: bool
    name: str
    dlc: int
    sender: str
    signals: list[Signal] = field(default_factory=list)
    cycle_time_ms: int | None = None

    def signal(self, name: str) -> Signal:
        for s in self.signals:
            if s.name == name:
                return s
        raise KeyError(f"{self.name} has no signal {name!r}")


@dataclass
class Database:
    messages: dict[int, Message]   # key = DBC id (extended flag included)

    def by_name(self, name: str) -> Message:
        for m in self.messages.values():
            if m.name == name:
                return m
        raise KeyError(f"no message {name!r}")

    def by_frame_id(self, frame_id: int, is_extended: bool = False) -> Message | None:
        key = frame_id | EXTENDED_FLAG if is_extended else frame_id
        return self.messages.get(key)


def _num(text: str, lineno: int) -> float:
    try:
        return float(text)
    except ValueError:
        raise DbcParseError(f"line {lineno}: {text!r} is not a number") from None


def parse_dbc(text: str) -> Database:
    messages: dict[int, Message] = {}
    current: Message | None = None

    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("//"):
            continue

        if line.startswith("BO_ "):
            m = _BO.match(line)
            if not m:
                raise DbcParseError(f"line {lineno}: bad BO_ line: {line}")
            dbc_id = int(m.group(1))
            current = Message(
                frame_id=dbc_id & 0x1FFFFFFF,
                is_extended=bool(dbc_id & EXTENDED_FLAG),
                name=m.group(2),
                dlc=int(m.group(3)),
                sender=m.group(4),
            )
            if dbc_id in messages:
                raise DbcParseError(f"line {lineno}: duplicate message id {dbc_id}")
            messages[dbc_id] = current
            continue

        if line.startswith("SG_ "):
            if current is None:
                raise DbcParseError(f"line {lineno}: SG_ before any BO_")
            m = _SG.match(line)
            if not m:
                raise DbcParseError(f"line {lineno}: bad SG_ line: {line}")
            sig = Signal(
                name=m.group(1),
                multiplex=m.group(2),
                start_bit=int(m.group(3)),
                length=int(m.group(4)),
                little_endian=m.group(5) == "1",
                signed=m.group(6) == "-",
                scale=_num(m.group(7), lineno),
                offset=_num(m.group(8), lineno),
                minimum=_num(m.group(9), lineno),
                maximum=_num(m.group(10), lineno),
                unit=m.group(11),
                receivers=[r for r in re.split(r"[,\s]+", m.group(12)) if r],
            )
            if sig.length < 1 or sig.length > 64:
                raise DbcParseError(f"line {lineno}: {sig.name} length {sig.length} not 1..64")
            current.signals.append(sig)
            continue

        current = None  # any other keyword ends the BO_ block

        if (m := _CYCLE.match(line)) and int(m.group(1)) in messages:
            messages[int(m.group(1))].cycle_time_ms = int(m.group(2))
        elif (m := _VAL.match(line)) and int(m.group(1)) in messages:
            msg = messages[int(m.group(1))]
            msg.signal(m.group(2)).choices = {
                int(k): v for k, v in _VAL_PAIR.findall(m.group(3))
            }

    return Database(messages)


def load_dbc(path: str | Path) -> Database:
    return parse_dbc(Path(path).read_text(encoding="utf-8"))


# --- decoding -----------------------------------------------------------------

def extract_raw(data: bytes, sig: Signal) -> int:
    """Exact integer raw value (no float -> no precision loss for 64 bits)."""
    if sig.little_endian:
        if sig.start_bit + sig.length > len(data) * 8:
            raise ValueError(f"{sig.name} runs past the end of the {len(data)}-byte payload")
        raw = (int.from_bytes(data, "little") >> sig.start_bit) & ((1 << sig.length) - 1)
    else:
        raw, bit = 0, sig.start_bit
        for _ in range(sig.length):
            byte_idx, bit_in_byte = divmod(bit, 8)
            if byte_idx >= len(data):
                raise ValueError(f"{sig.name} runs past the end of the {len(data)}-byte payload")
            raw = (raw << 1) | ((data[byte_idx] >> bit_in_byte) & 1)
            bit = (byte_idx + 1) * 8 + 7 if bit_in_byte == 0 else bit - 1
    if sig.signed and raw & (1 << (sig.length - 1)):
        raw -= 1 << sig.length
    return raw


def decode(msg: Message, data: bytes) -> dict[str, float | int | str]:
    """Return {signal: physical value}; value-table names replace numbers."""
    if msg.signals and any(s.multiplex for s in msg.signals):
        raise NotImplementedError(f"{msg.name}: multiplexed signals not supported yet")
    out: dict[str, float | int | str] = {}
    for sig in msg.signals:
        raw = extract_raw(data, sig)
        if raw in sig.choices:
            out[sig.name] = sig.choices[raw]
            continue
        phys = sig.offset + sig.scale * raw
        out[sig.name] = int(phys) if float(phys).is_integer() and sig.scale == 1 else phys
    return out


def range_violations(msg: Message, data: bytes) -> list[str]:
    """Signals whose physical value is outside the DBC [min|max] range."""
    problems = []
    for sig in msg.signals:
        if sig.minimum == sig.maximum == 0:
            continue  # [0|0] = no range defined
        phys = sig.offset + sig.scale * extract_raw(data, sig)
        if not sig.minimum <= phys <= sig.maximum:
            problems.append(f"{sig.name}={phys:g} outside [{sig.minimum:g}|{sig.maximum:g}]")
    return problems

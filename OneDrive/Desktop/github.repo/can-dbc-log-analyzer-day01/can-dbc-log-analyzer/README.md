# CAN DBC Log Analyzer

![tests](https://github.com/vivekkumar-ramanandi/can-dbc-log-analyzer/actions/workflows/tests.yml/badge.svg)

A small tool for **ECU test engineers**: load a DBC, read a CAN log, and check it automatically for decoded values, cycle times, alive counters, value ranges and bus load, with a PASS/FAIL report for CI.

Built from scratch (no `cantools` inside) so every bit of the DBC logic is understood and tested.

> 🚧 **Work in progress**: day-by-day build plan in [PLAN.md](PLAN.md), progress in [docs/LEARNING_LOG.md](docs/LEARNING_LOG.md).

## Features
| Status | Feature |
|---|---|
| ✅ | DBC parser: messages, signals (Intel/Motorola, signed), cycle times, value tables, 29-bit IDs |
| ✅ | Frame decoder → physical values; range check against DBC `[min\|max]` |
| ✅ | Clear errors with line numbers for broken DBC files |
| ⏳ | candump log reader · CSV export · cycle-time / alive-counter / plausibility checks · bus load · report · CLI |

## Quick start
```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[test]"
pytest -v
```
```python
from candbc.dbc import load_dbc, decode

db = load_dbc("data/power_window.dbc")
decode(db.by_name("EEC1"), bytes.fromhex("FFFFFF6813FFFFFF"))
# {'EngineSpeed': 621.0}   <- worked example from the CSS Electronics CAN guide
```

## Test approach
- **Test oracle from the literature:** the EngineSpeed example (`0CF00400 … 68 13` → 621 rpm) from the CSS Electronics guide.
- **Negative tests:** invalid byte order, non-numeric scale, zero-length signal, duplicate IDs, signal before message.
- **Safety-minded default:** multiplexed messages raise `NotImplementedError` instead of being decoded wrongly.

## Example DBC
`data/power_window.dbc` is a simplified version of the DBC from my [power-window-ecu-testing](https://github.com/vivekkumar-ramanandi/power-window-ecu-testing) project, plus a J1939 message (EEC1) and a Motorola/signed test message.

## References
CSS Electronics, *CAN bus – the ultimate guide* (DBC chapter) · ISTQB® CT-AuT, CTAL-TA syllabi.

# Plan: 13 days, 1 commit per day

**Project 1 of the series** · Start Fri 20 Nov 2026 · Target `v1.0` on Wed 2 Dec 2026
**Goal:** a command-line tool that takes a **DBC + a CAN log** and checks it automatically: decoded signals, cycle times, alive counters, value ranges, bus load, and a PASS/FAIL report for CI.
**Why recruiters care:** every HIL/vehicle test team does log analysis. This is what CANoe/CANalyzer test modules do, built and tested by hand.

**Sources:** CSS Electronics *CAN bus – the ultimate guide* (DBC p. 192–202, candump/log formats, bus load, error frames) · ISTQB CT-AuT ch. 3 (XiL) · CTAL-TA ch. 3 (EP/BVA for tolerances) · CTAL-TAE (reporting, CI).

| Day | Date | Build | Test technique | Commit message |
|---|---|---|---|---|
| 1 ✅ | Fri 20 Nov | DBC parser (BO_, SG_, cycle time, VAL_), decoder (Intel/Motorola, signed), range check | Oracle = guide example; negative tests for broken DBC | `feat: DBC parser and frame decoder` |
| 2 | Sat 21 Nov | candump log reader: `(t) vcan0 200#51…` → `Frame(t, id, data)`; also 29-bit IDs | EP on line formats, malformed lines with line numbers | `feat: candump log reader` |
| 3 | Sun 22 Nov | Decode a whole log → CSV time series per signal | Golden-file test (expected CSV in `tests/data`) | `feat: decode log to CSV` |
| 4 | Mon 23 Nov | Cycle-time check vs. `GenMsgCycleTime` (±10 %), missing-message timeout | **BVA** on the tolerance: 18/18.1/21.9/22 ms | `feat: cycle time check` |
| 5 | Tue 24 Nov | Alive-counter check: gaps, repeats, frozen counter (your REQ_17/18) | State-based test cases, wrap 15→0 | `feat: alive counter check` |
| 6 | Wed 25 Nov | Plausibility: range violations, DLC mismatch, unknown IDs | Decision table: known ID × DLC ok × range ok | `feat: plausibility checks` |
| 7 | Thu 26 Nov | Bus load (worst-case bit stuffing, 500 kbit/s) per 1 s window | Hand-calculated oracle in the test | `feat: bus load calculation` |
| 8 | Fri 27 Nov | Markdown test report: one row per check, PASS/FAIL, REQ-ID | Snapshot test of the report | `feat: markdown test report` |
| 9 | Sat 28 Nov | CLI `candbc check <log> --dbc <file>`; exit code 1 on FAIL | CLI tests with `subprocess` / `capsys` | `feat: command line interface` |
| 10 | Sun 29 Nov | Back-to-back test vs. `cantools` (skipped if not installed) + multiplexed signals | **Back-to-back testing** | `test: back-to-back against cantools` |
| 11 | Mon 30 Nov | Log generator with fault injection: drop / delay / freeze / out-of-range | Each injected fault must be found (fault-injection testing) | `feat: log generator with fault injection` |
| 12 | Tue 1 Dec | GitHub Actions: run the tool on a sample log, upload the report; coverage ≥ 90 % | Quality gate in CI | `ci: analyse sample log, coverage gate` |
| 13 | Wed 2 Dec | README with screenshot, `v1.0` tag + release, LinkedIn post | Fresh-clone re-run | `docs: v1.0 README and release` |

**Rule:** a day isn't done until `pytest` is green and the push is on GitHub. Missed a day? Do it the next day. Don't squash two days into one commit, and don't back-date.

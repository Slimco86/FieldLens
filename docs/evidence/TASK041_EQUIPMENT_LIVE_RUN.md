# TASK-041 EQ-11: live equipment-candidate run (reported, not gated)

Run 2026-11-01 06:35 UTC. Class: LIVE (`muse-spark-1.3`, effort `low`, page concurrency 3, upright 1600 px).
Values are model-read and UNVERIFIED; they are never accepted, never used in calculations and the
reference below is an AGENT-READ reference (TASK-042), NOT human verified. Agreement figures are rough.

Spend cap USD 3.000000; committed USD 0.676365 (placeholder rates, not provider rates); wall 22.5 s.

| Doc | Page | State | Items | Latency s | In tok | Out tok | Cost USD |
|---|---|---|---|---|---|---|---|
| PV-17 | 4 | failed | 0 | 4.6 | 3916 | 899 | 0.042055 |
| PV-17 | 29 | succeeded | 16 | 9.8 | 10539 | 2682 | 0.119745 |
| PV-17 | 30 | failed | 0 | 4.0 | 3916 | 679 | 0.036555 |
| PV-17 | 35 | succeeded | 9 | 7.5 | 10538 | 1882 | 0.099740 |
| PV-17 | 36 | failed | 0 | 3.1 | 3916 | 809 | 0.039805 |
| PV-21 (control) | 13 | succeeded | 0 | 3.0 | 10643 | 253 | 0.059540 |
| PV-21 | 48 | failed | 0 | 8.5 | 10534 | 1741 | 0.096195 |
| PV-21 | 49 | failed | 0 | 10.9 | 0 | 0 | 0.000000 |
| PV-21 (control) | 50 | succeeded | 0 | 2.6 | 10572 | 316 | 0.060760 |

## Agreement with the agent-read reference (rough)

- PV-17:4: category agreement 0.0 (0 read / 1 reference); size matches 0/0
- PV-17:29: category agreement 1.0 (16 read / 12 reference); size matches 1/1
- PV-17:30: category agreement 0.0 (0 read / 2 reference); size matches 0/0
- PV-17:35: category agreement 1.0 (9 read / 1 reference); size matches 0/0
- PV-17:36: category agreement 0.0 (0 read / 21 reference); size matches 0/8
- PV-21:13: control page, 0 item(s) read (expected 0)
- PV-21:48: category agreement 0.0 (0 read / 5 reference); size matches 0/5
- PV-21:49: category agreement 0.0 (0 read / 22 reference); size matches 0/17
- PV-21:50: control page, 0 item(s) read (expected 0)

## Notes

- model-read and unverified; documents named only by their project document ids
- control pages are included only with --include-controls
- F-14 FWR completion (PV-17): run failed (pages_failed); partial coverage, not complete
- F-5 completion report (PV-21): run failed (pages_failed); partial coverage, not complete

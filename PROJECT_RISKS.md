# Project Risks (top)

Full register: [docs/17-risk-register.md](docs/17-risk-register.md).

| ID | Risk | Score | Mitigation (short) |
|---|---|---|---|
| R-01 | Hindi/Hinglish & phone-number recognition in a noisy reception | 20 | On-hardware bake-off, AEC speakerphone, read-back, keypad fallback, cascaded Indic fallback |
| R-02 | Unknown capacity/exclusivity/hours rules | 16 | Close D-01/D-02 before Sprint 2; engine supports both capacity modes |
| R-03 | Double calendar during DaySchedule migration | 15 | Write-freeze cut-over, import + reconciliation, rollback plan |
| R-09 | Venue internet outage | 12 | 4G failover; offline screen |
| R-04 | AI invents facts / false confirmation | 10 | Tool-only facts, backend state machine, eval with zero tolerance |
| R-12 | PII shown to next customer | 10 | In-memory kiosk state, reset on all paths, E2E test |

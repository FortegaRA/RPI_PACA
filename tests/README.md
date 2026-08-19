# RPI_Cluster — Unit tests

These tests pin down the **empty-vs-error** contract: for every health authority,
a run that produces 0 records must say *why* —

- **EMPTY** — the portal answered fine, there is simply **no registration for that
  molecule**. Clean zero, no error recorded.
- **FAILED / ERROR** — the extractor **could not fetch/parse** (network down, portal
  changed, endpoint moved). A message is recorded in `config["partial_errors"]`,
  and the run summary shows ⚠️ Failed / ❌ Error instead of ⚠️ Empty.

They run with **no network and no real Chrome** — the `requests.Session` and the
Selenium `WebDriver` are replaced by fakes in `tests/_fakes.py`.

There are two layers:

- **Unit tests** (`test_status_classification`, `test_http_extractors`,
  `test_selenium_extractors`, `test_honduras`) — fast, offline, fully mocked.
- **Live integration tests** (`test_integration_live`) — hit the real portals to
  confirm the same contract end-to-end. They skip automatically when a portal host
  is unreachable, and can be turned off entirely with `RPI_SKIP_INTEGRATION=1`.

## Run

```bash
# fast unit tests only (offline, ~10s) — recommended for day-to-day
RPI_SKIP_INTEGRATION=1 python -m unittest discover -s tests -t .

# everything, including the live portal checks (needs network, ~4-5 min)
python -m unittest discover -s tests -t .

# one module
python -m unittest tests.test_http_extractors -v
python -m unittest tests.test_integration_live -v
```

On Windows PowerShell, set the env var with `$env:RPI_SKIP_INTEGRATION=1` first.

No third-party test runner is required (stdlib `unittest`). `openpyxl` is needed
for the Honduras/Costa Rica fixtures (already in `requirements.txt`); the live
tests also need `requests` (and Chrome, for the Guatemala live test only).

## Coverage (per webpage)

| File | Health authorities | What it asserts |
|------|--------------------|-----------------|
| `test_status_classification.py` | orchestrator | `run_extractor` maps (rows, errors) → EMPTY / FAILED / OK / PARTIAL / ERROR; summary labels are distinct |
| `test_http_extractors.py` | EMA, FDA, Colombia-approvals, El Salvador, Ecuador | no-record → `[]` + no error; fetch failure → error. Ecuador also: *responded-but-no-match* (empty) vs *nothing-responded* (error) |
| `test_selenium_extractors.py` | Guatemala, Dominican Rep., Costa Rica, Peru-approvals, Peru-submissions, Colombia-submissions | search succeeds but table empty → `[]` + no error; navigation/attach failure → error |
| `test_honduras.py` | Honduras | workbook downloaded but no target molecule → `[]` + no error; download fails (no Selenium fallback) → error |
| `test_postfilter.py` | (cross-cutting) | indication/sub-type filters: Tadalafil→PAH/ophthalmic, Bevacizumab→ophthalmic, Ranibizumab→biosimilar; non-filtered molecules pass through; `_indication_hint` never leaks to the CSV |
| `test_alias_search.py` | (cross-cutting) | LATAM extractors also search a molecule's INN-variant aliases (so Tadalafil's `TADALAFILO` is found, not just `TADAFILO`), tagging rows with the canonical term; broad class aliases (`FACTOR VIII`) are excluded |
| `test_presence.py` | (cross-cutting) | novel molecules with no data in a searched country get a NULL-filled `NO_DATA` presence row; never for non-flagged molecules or unsearched countries; rows are valid canonical (PK present) |
| `test_report.py` | (output) | xlsx report builds with the right sheets/KPIs and a 90-day recent-approvals signal; `NO_DATA` rows excluded from counts; the newest consolidated file is picked by parsing its day-first `DDMMYYYY` stamp, not alphabetically |
| `test_integration_live.py` | EMA, FDA, Colombia, El Salvador, Honduras, Guatemala (live) | known molecule → real rows + no error; nonsense molecule → `[]` + no error, **confirmed against the live portal** |

Each HA has at least one **EMPTY** case and one **ERROR** case; several also have a
**real-record** case proving a genuine hit is not mistaken for empty.

**Ecuador is intentionally not in the live tests** — its portal blocks IPs that
request faster than ~15s apart, so a test must not risk getting the IP blocked.
EC's empty-vs-error logic is fully covered by the (mocked) unit tests.

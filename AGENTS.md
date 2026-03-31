# AGENTS.md — APDA-FFT Technical Guidelines

## Project Overview

**APDA-FFT** (Adaptive Peak Detection for FFT-based Structural Monitoring) is a Python 3.x system that runs on a Digi IX15 gateway with an integrated XBee radio module. It receives accelerometer data from wireless sensors, performs FFT analysis, detects structural vibration peaks, and uploads results to FTP servers and FastAPI endpoints.

---

## Build / Run / Test Commands

| Action | Command |
|--------|---------|
| Run the gateway | `python GT_FFT_v5.py` |
| Run a single module | `python <module_path.py>` (e.g. `python metrics/fft_iterativa.py`) |
| Lint / format | **None configured** — follow style guidelines below |
| Tests | **None exist** — project has zero test infrastructure |

**No dependency manager exists** (no `requirements.txt`, `pyproject.toml`, or `setup.py`). Dependencies are implicit: Python 3.x standard library + `digidevice` (hardware-specific, pre-installed on the IX15 gateway).

---

## Code Style Guidelines

### Imports
- Standard library imports first, grouped by module (e.g. `os`, `json`, `time`, `math`, `cmath`, `statistics`, `ctypes`, `ftplib`, `urllib.request`, `datetime`, `re`, `resource`).
- Internal imports use dot-notation from project root: `from metrics.fft_iterativa import start_fft`, `from utils.load_data import load_sensor`.
- No `__init__.py` files in subpackages — the project is run from root, so modules resolve via `sys.path`.
- Comment out unused imports rather than removing them (e.g. `# from utils.influxdb_manager import InfluxHandler`).

### Naming Conventions
- **Classes:** PascalCase — `Gateway`, `ProtocolDecoder`, `FTPClient`, `FastAPIHandler`
- **Functions / Methods:** snake_case — `process_data`, `load_sensor`, `get_top_peaks_prominence`, `build_sync_packet`
- **Variables:** snake_case — `payload_slice`, `is_append`, `config_dict`
- **Constants:** UPPER_SNAKE_CASE at class level — `DATA_DIR`, `RANGE_MAP`, `ODR_MAP`
- **Module-level lookup dicts:** short lowercase names are acceptable — `rl`, `ol`, `al`, `sl`

### Formatting
- **Indentation:** 4 spaces (no tabs).
- **Line length:** No hard limit enforced; keep lines reasonable (~100 chars).
- **Blank lines:** 2 blank lines between top-level functions/classes; 1 blank line between methods within a class.
- **Trailing whitespace:** Avoid.
- **No formatter configured** — apply these rules manually.

### Types
- **No type hints** are used anywhere in the codebase. Do not add type annotations unless explicitly requested.
- Document argument types and return values in docstrings instead.

### Docstrings & Comments
- Docstrings use triple-double-quotes (`"""..."""`) immediately after `def`/`class`.
- Brief one-liner docstrings are acceptable for simple functions.
- Longer docstrings may include `Args:` and `Returns:` sections (Google-style, but informal).
- **Comments are in Italian** — follow this convention for consistency.
- Comment out dead code blocks rather than deleting them (preserves history and intent).

### Error Handling
- Use broad `try / except Exception as e` blocks — this is the established pattern.
- Report errors via a `logger_callback` function (passed into constructors) rather than raising exceptions.
- On failure, return safe defaults: `[]`, `None`, or sentinel values.
- Timeout exceptions in radio receive loops are silently ignored.
- Critical unrecoverable errors may call `exit(1)` or `raise`.
- Specific exception types are caught when useful (e.g. `urllib.error.HTTPError`).

### Code Organization
- `GT_FFT_v5.py` — main orchestrator (~943 lines). Contains the `Gateway` class.
- `protocol_decoder.py` — hex packet codec (`ProtocolDecoder` class with `@staticmethod`/`@classmethod` methods).
- `protocol_radio.py` — XBee connection manager (`XBeeManager` class).
- `metrics/` — computational modules (e.g. `fft_iterativa.py`).
- `utils/` — utility modules (FTP, FastAPI, InfluxDB, data loading, peak detection).
- `configs/` — JSON and text configuration files (not committed with real credentials).

---

## Configuration & Secrets

- **Never commit real credentials.** `configs/gw_config.json` in the repo contains placeholder/example values.
- Before deployment, create `gw_create.json` with actual credentials (FTP, InfluxDB token, etc.).
- Sensor configurations live in `configs/config.txt` (one line per sensor: MAC + 17 parameters).

---

## Git Workflow

- Branches: `main`, `test`, `queue`, `backup-queue`
- Commit messages: brief, descriptive, Italian or English acceptable.
- Do not push to `main` without explicit instruction.

---

## OpenCode Agent Configuration

Defined in `opencode.json`:
- **build** — primary development agent (write/edit/bash enabled)
- **criticality-analyst** — read-only security/quality auditor (reports issues, no file modifications)
- **plan** — read-only planning agent (no tool access)

---

## Known TODOs (from `checklist`)

1. Create a DB connection pool to avoid opening a connection per upload/request.
2. Improve volatile memory send queues (FTP & API): consider an internal mini-DB or `.sentinel` files to track sent files.

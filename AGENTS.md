# Repository Guidelines

## Project Structure & Module Organization
- `app/`: main application entry (`solar12vups.py`, class `SolarMain`).
- `ble/`: BLE discovery/clients and tasks (Bleak usage; see Linux notes).
- `gui/`: Tkinter UI components (frames, gauges, tooltips).
- `lib/`: logging (`log.py`), utilities, async helpers, color enums.
- `images/`, favicons: screenshots and assets used in docs/UI.
- Top-level: `solar_runner.py` (CLI), `setup.py` (packaging), `version.py`.

## Build, Test, and Development Commands
```bash
# Setup a virtual environment and install editable
python3 -m venv .venv && source .venv/bin/activate
pip install -e .

# Run the app (console script)
solar12vups --stderr

# Or run directly from source
python solar_runner.py --stderr

# Show package version
python version.py
```

## Coding Style & Naming Conventions
- Python 3.9+; 4-space indentation; follow PEP 8.
- Names: modules/files lower_snake_case; functions/vars lower_snake_case; classes PascalCase.
- Prefer type hints on new/modified code; add concise docstrings for public APIs.
- Logging: use `lib.log.setup_logger()` and `lib.log.xreport()`; avoid bare `print()`.

## Testing Guidelines
- No test suite yet. If adding tests, use `pytest`.
- Place tests under `tests/`; name files `test_*.py` and functions `test_*`.
- Mock BLE I/O; cover parsing, state transitions, and GUI logic where feasible.

## Commit & Pull Request Guidelines
- Commits: short, imperative summaries (≤72 chars), e.g., "add --stderr arg".
- PRs: clear description, rationale, linked issues, and repro/test steps.
- Include screenshots for GUI changes (store under `images/` when appropriate).
- Update READMEs when behavior, setup, or UX changes.

## Security & Configuration Tips
- Linux BLE scanning behavior: see `README-Bleak-Linux.md`.
- UI uses Matplotlib `TkAgg`; ensure a Tk runtime is installed.
- Logs are written to `~/solar12vups/STDERR.txt` by default (`--stderr` for console).


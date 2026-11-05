# guitarr — notes for AI assistants

A guitar practice companion: a Python listener grades what you play (live or from a recording),
and a local web UI teaches, tracks and shapes your sound.

## Run and test
- `.venv/bin/python -m guitarr gui --no-browser` → http://127.0.0.1:8765
- `.venv/bin/python -m pytest -q` (no audio hardware needed; every test gets its own `~/.guitarr` via `tests/conftest.py`)
- Docker: `docker compose up --build` (no live audio input on macOS/Windows)

## Layout
- `guitarr/` — Python: listening (`session.py`, `follow.py`, `dsp.py`), analysis, `progress.py` (XP, streak),
  `plan.py` (practice time), `rig.py` (tone presets storage), `gui/server.py` (FastAPI).
- `guitarr/gui/static/` — plain ES modules, no build step, no npm. `main.js` routes; `views/*.js` mount/unmount;
  `lib/` shared helpers; `lib/rig/` the Web Audio tone rig; vendored libraries live in `vendor/`.

## Rules
- **Language:** code, comments, data files and docs in English. Spanish (and any other language) only through
  i18next: every UI string is a key in `locales/en.json` **and** `locales/es.json` (keep the key sets identical).
- **The listener grades the clean signal.** The tone rig is for monitoring only; never route effects into grading.
- **Decisions live on the server.** Scores, XP, streaks and plan numbers are computed in Python and stored in
  `config.HOME` (`~/.guitarr`); the UI only displays them. Use `config.HOME` paths so tests stay isolated.
- **API errors** are `{"detail": {"code", "message"}}`; the UI translates `errors.<code>` (or a view's own keys)
  and falls back to the English message. Forms show errors under the field that caused them and keep what the
  user typed.
- **No `alert`, `confirm` or `prompt`.** Confirm in place ("Remove? Yes / No") or use a `<dialog>`.
- **Color never stands alone:** every status color comes with a number or a word.
- **Rounding:** practice time is rounded to the minute before computing colors, goals and streaks.
- **Gear names are generic** (no brands) in the tone rig.
- **Audio safety while testing:** don't play sound through the user's speakers. Measure rig levels before the master
  volume (`rig.levels().sound`) with the master gain at 0, and keep the limiter at the end of the chain.
- Keep changes small and focused; don't add features, files or dependencies beyond the request.

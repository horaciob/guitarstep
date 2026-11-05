# Sets up the development environment in .venv (Python 3.10 or 3.11: basic-pitch supports up to 3.11).
# Usage: make install            (or: make install PYTHON=/path/to/python3.11)

VENV   := .venv
PY     := $(VENV)/bin/python
PYTHON ?= $(shell command -v python3.11 || command -v python3.10)

.PHONY: install

install: $(PY)
	$(PY) -m pip install --upgrade pip
ifeq ($(shell uname -s),Linux)
	. $(VENV)/bin/activate && scripts/install-linux.sh --dev
else
	$(PY) -m pip install -e ".[dev]"
endif
	$(PY) -m playwright install chromium
	@echo "Done. Run: $(PY) -m guitarr gui"

$(PY):
	@test -n "$(PYTHON)" || { echo "Python 3.10 or 3.11 not found (try: brew install python@3.11)"; exit 1; }
	$(PYTHON) -m venv $(VENV)

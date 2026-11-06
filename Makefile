# Sets up the development environment in .venv (Python 3.10 or 3.11: basic-pitch supports up to 3.11).
# Usage: make install            (or: make install PYTHON=/path/to/python3.11)
#        make run                (web UI in the background; make run PORT=9000 ARGS=--no-browser)
#        make stop

VENV   := .venv
PY     := $(VENV)/bin/python
PYTHON ?= $(shell command -v python3.11 || command -v python3.10)
PORT   ?= 8765
ARGS   ?=
PID    := $(VENV)/guitarr.pid
LOG    := $(VENV)/guitarr.log

.PHONY: install run stop

run:
	@test -x $(PY) || { echo "Run make install first"; exit 1; }
	@if [ -f $(PID) ] && kill -0 $$(cat $(PID)) 2>/dev/null; then \
		echo "Already running (pid $$(cat $(PID))) → http://127.0.0.1:$(PORT)"; exit 0; fi; \
	if lsof -t -iTCP:$(PORT) -sTCP:LISTEN >/dev/null 2>&1; then \
		echo "Port $(PORT) is already in use (make stop, or make run PORT=...)"; exit 1; fi; \
	nohup $(PY) -m guitarr gui --port $(PORT) $(ARGS) > $(LOG) 2>&1 & echo $$! > $(PID); \
	echo "Started (pid $$!) → http://127.0.0.1:$(PORT)  log: $(LOG)"

# Stops the server started by make run, or any guitarr gui listening on PORT (e.g. started by hand).
stop:
	@if [ -f $(PID) ] && kill $$(cat $(PID)) 2>/dev/null; then echo "Stopped (pid $$(cat $(PID)))"; rm -f $(PID); exit 0; fi; \
	rm -f $(PID); \
	for p in $$(lsof -t -iTCP:$(PORT) -sTCP:LISTEN 2>/dev/null); do \
		if ps -o command= -p $$p | grep -q 'guitarr gui'; then kill $$p && echo "Stopped (pid $$p)" && exit 0; \
		else echo "Port $(PORT) is used by another program (pid $$p), not stopping it"; exit 1; fi; \
	done; echo "Not running"

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

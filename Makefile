# guitarr: the local app (.venv) and the web service (Docker Compose). `make` lists the commands.
#
# Local app:   make install · make run · make stop · make test
# Web service: make up · make login EMAIL=… · make down · make logs · make migrate         (HTTPS=1: behind Caddy, compose.https.yaml)
# Web service outside Docker (Postgres from Compose): make db-start · make db-migrate · make run-service

VENV   := .venv
PY     := $(VENV)/bin/python
PYTHON ?= $(shell command -v python3.11 || command -v python3.10)
PORT   ?= 8765
ARGS   ?=
PID    := $(VENV)/guitarr.pid
LOG    := $(VENV)/guitarr.log

# POSTGRES_PASSWORD, GUITARR_DB_PORT, ... as Compose reads them
-include .env

COMPOSE := docker compose -f compose.yaml $(if $(HTTPS),-f compose.https.yaml)
# app containers (more than 1 needs HTTPS=1), job workers, one service for make logs
APPS    ?= 1
WORKERS ?= 1
S       ?=
FILE    ?= guitarr-$(shell date +%Y%m%d-%H%M).sql
DATABASE_URL ?= postgresql://guitarr:$(or $(POSTGRES_PASSWORD),guitarr)@127.0.0.1:$(or $(GUITARR_DB_PORT),5442)/guitarr
# users' files for the web service outside Docker (apart from the local app's ~/.guitarr)
SERVICE_HOME ?= $(HOME)/.guitarr-service
SERVICE_ENV  = GUITARR_DATABASE_URL='$(DATABASE_URL)' GUITARR_HOME='$(SERVICE_HOME)'

.DEFAULT_GOAL := help
.PHONY: help install run stop test test-fast \
        db-start db-stop db-migrate db-status db-new run-service worker \
        up down restart logs ps migrate db-status-docker psql backup login login-local

help:
	@echo "Local app"
	@echo "  make install           .venv with everything (PYTHON=/path/to/python3.11 to choose)"
	@echo "  make run / make stop   the app in the background on PORT ($(PORT)); ARGS=--no-browser"
	@echo "  make test              all the tests (make test-fast: without the browser ones)"
	@echo ""
	@echo "Web service in Docker (HTTPS=1: https in front, compose.https.yaml)"
	@echo "  make up                build and start (APPS=n app containers with HTTPS=1, WORKERS=n)"
	@echo "  make down              stop it (your data stays in the volumes)"
	@echo "  make restart           down + up"
	@echo "  make logs              follow the logs (S=guitarr|worker|db|migrate|proxy for one)"
	@echo "  make ps                what's running"
	@echo "  make migrate           apply pending migrations (make db-status-docker: what's pending)"
	@echo "  make psql              a SQL prompt in the database"
	@echo "  make backup            dump the database to FILE ($(FILE))"
	@echo "  make login EMAIL=you@example.com   a sign-in link printed here (the account is made if new)"
	@echo ""
	@echo "Web service outside Docker (Postgres from Compose on 127.0.0.1:$(or $(GUITARR_DB_PORT),5442))"
	@echo "  make db-start          start only Postgres (make db-stop)"
	@echo "  make db-migrate        apply pending migrations (make db-status: what's pending)"
	@echo "  make db-new NAME=x     a new migration file, guitarr/db/migrations/NNNN_x.sql"
	@echo "  make run-service       the app as a web service on PORT, jobs included (foreground)"
	@echo "  make worker            an extra job worker (foreground)"
	@echo "  make login-local EMAIL=you@example.com   a sign-in link for it"
	@echo "  DATABASE_URL=... to use another Postgres"

# ---------------------------------------------------------------- local app

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
	@echo "Done. Run: make run"

$(PY):
	@test -n "$(PYTHON)" || { echo "Python 3.10 or 3.11 not found (try: brew install python@3.11)"; exit 1; }
	$(PYTHON) -m venv $(VENV)

test:
	$(PY) -m pytest -q

test-fast:
	$(PY) -m pytest -q --ignore=tests/e2e

# ---------------------------------------------------------------- web service outside Docker

db-start:
	docker compose up -d --wait db
	@echo "Postgres → $(DATABASE_URL)"

db-stop:
	docker compose stop db

db-migrate:
	GUITARR_DATABASE_URL='$(DATABASE_URL)' $(PY) -m guitarr db migrate

db-status:
	GUITARR_DATABASE_URL='$(DATABASE_URL)' $(PY) -m guitarr db status

db-new:
	@test -n "$(NAME)" || { echo "Usage: make db-new NAME=add_something"; exit 1; }
	$(PY) -m guitarr db new $(NAME)

run-service:
	$(SERVICE_ENV) GUITARR_PUBLIC_URL=http://localhost:$(PORT) \
		$(PY) -m guitarr gui --no-browser --port $(PORT) $(ARGS)

worker:
	$(SERVICE_ENV) $(PY) -m guitarr worker

login-local:
	@test -n "$(EMAIL)" || { echo "Usage: make login-local EMAIL=you@example.com"; exit 1; }
	@$(SERVICE_ENV) GUITARR_PUBLIC_URL=http://localhost:$(PORT) $(PY) -m guitarr user link '$(EMAIL)'

# ---------------------------------------------------------------- web service in Docker

up:
	$(COMPOSE) up --build -d --scale guitarr=$(APPS) --scale worker=$(WORKERS)
	@$(if $(HTTPS),echo "→ https://$(or $(GUITARR_DOMAIN),localhost)",echo "→ http://localhost:$(or $(GUITARR_PORT),8765)  (sign-in links: make logs S=guitarr)")

down:
	$(COMPOSE) down

restart: down up

logs:
	$(COMPOSE) logs -f --tail=100 $(S)

ps:
	$(COMPOSE) ps

migrate:
	$(COMPOSE) run --rm migrate

db-status-docker:
	$(COMPOSE) run --rm migrate guitarr db status

psql:
	$(COMPOSE) exec db psql -U guitarr guitarr

backup:
	$(COMPOSE) exec -T db pg_dump -U guitarr guitarr > $(FILE)
	@echo "Saved $(FILE) (restore: $(COMPOSE) exec -T db psql -U guitarr guitarr < $(FILE))"

login:
	@test -n "$(EMAIL)" || { echo "Usage: make login EMAIL=you@example.com"; exit 1; }
	@$(COMPOSE) exec guitarr guitarr user link '$(EMAIL)'

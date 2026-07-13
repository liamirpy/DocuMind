SHELL := /bin/bash

.PHONY: init up down build logs ps test lint format check process

init:
	@test -f .env || cp .env.example .env
	@mkdir -p data/outputs

up: init
	docker compose up -d --build

build:
	docker compose build

down:
	docker compose down

logs:
	docker compose logs -f agent-api

ps:
	docker compose ps

test:
	python -m pytest -q

lint:
	ruff check app tests

format:
	ruff format app tests
	ruff check --fix app tests

check:
	ruff format --check app tests
	ruff check app tests
	python -m pytest -q
	python -m compileall -q app

process:
	@test -n "$(PDF)" || (echo "Usage: make process PDF=/path/to/article.pdf [USE_LLM=true]" && exit 2)
	curl --fail --show-error -X POST http://localhost:$${AGENT_PORT:-8100}/v1/process \
	  -F "file=@$(PDF);type=application/pdf" \
	  -F "use_llm=$(if $(USE_LLM),$(USE_LLM),false)" | jq

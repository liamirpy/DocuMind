SHELL := /bin/bash

COMPOSE := docker compose -f compose.yaml
COMPOSE_GPU := docker compose -f compose.yaml -f compose.nvidia.yaml

.PHONY: init up-cpu up-gpu ready process logs logs-gpu down down-gpu pull-model test lint format check clean

init:
	@test -f .env || cp .env.example .env
	@mkdir -p outputs
	@echo "Edit .env if needed, especially OUTPUT_DIR and OLLAMA_MODEL."

up-cpu: init
	$(COMPOSE) up -d --build

up-gpu: init
	$(COMPOSE_GPU) up -d --build

ready:
	@echo "Tools:" && curl -fsS http://localhost:8090/health/ready | jq
	@echo "Agent:" && curl -fsS http://localhost:8100/health/ready | jq
	@echo "Runtime:" && curl -fsS http://localhost:8100/v1/runtime | jq

process:
	@test -n "$(PDF)" || (echo "Usage: make process PDF=/absolute/path/article.pdf [OUTPUT_FOLDER=case_001] [USE_LLM=true] [OVERWRITE=false]" && exit 2)
	@args=( \
	  --fail --show-error -X POST http://localhost:8100/v1/process \
	  -F "file=@$(PDF);type=application/pdf" \
	  -F "use_llm=$(if $(USE_LLM),$(USE_LLM),false)" \
	); \
	if [[ -n "$(OUTPUT_FOLDER)" ]]; then args+=( -F "output_folder=$(OUTPUT_FOLDER)" ); fi; \
	if [[ -n "$(OVERWRITE)" ]]; then args+=( -F "overwrite=$(OVERWRITE)" ); fi; \
	curl "$${args[@]}" -o agent-result.json
	jq . agent-result.json

pull-model:
	$(COMPOSE) run --rm ollama-model-init

logs:
	$(COMPOSE) logs -f --tail=100

logs-gpu:
	$(COMPOSE_GPU) logs -f --tail=100

down:
	$(COMPOSE) down --remove-orphans

down-gpu:
	$(COMPOSE_GPU) down --remove-orphans

test:
	$(MAKE) -C tools test
	$(MAKE) -C agent test

lint:
	$(MAKE) -C tools lint
	$(MAKE) -C agent lint

format:
	$(MAKE) -C tools format
	$(MAKE) -C agent format

check:
	$(MAKE) -C agent check
	cd tools/api && ruff format --check . && ruff check . && python -m pytest -q && python -m compileall -q app

clean:
	-$(COMPOSE) down --remove-orphans
	rm -rf outputs/*
	rm -f agent-result.json

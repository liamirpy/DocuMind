SHELL := /bin/bash
CPU_COMPOSE := docker compose -f docker-compose.yml
GPU_COMPOSE := docker compose -f docker-compose.yml -f docker-compose.gpu.yml

.PHONY: init build-cpu up-cpu build-gpu up-gpu down down-gpu logs ps ready runtime test lint format smoke clean

init:
	cp -n .env.example .env || true
	mkdir -p data/assets output

build-cpu:
	$(CPU_COMPOSE) build extractor-api

up-cpu: init
	$(CPU_COMPOSE) up -d --build

build-gpu:
	$(GPU_COMPOSE) build extractor-api

up-gpu: init
	$(GPU_COMPOSE) up -d --build

# Use down-gpu after a GPU launch so Compose sees the same merged project definition.
down:
	$(CPU_COMPOSE) down --remove-orphans

down-gpu:
	$(GPU_COMPOSE) down --remove-orphans

logs:
	$(CPU_COMPOSE) logs -f --tail=200

ps:
	$(CPU_COMPOSE) ps

ready:
	curl -fsS http://localhost:$${API_PORT:-8090}/health/ready | python -m json.tool

runtime:
	curl -fsS http://localhost:$${API_PORT:-8090}/v1/runtime | python -m json.tool

test:
	cd api && python -m pytest

lint:
	cd api && ruff check . && ruff format --check .

format:
	cd api && ruff check --fix . && ruff format .

smoke:
	./scripts/smoke_test.sh tests/fixtures/scientific_sample.pdf

clean:
	$(GPU_COMPOSE) down -v --remove-orphans
	rm -rf output/* data/assets/*
	touch data/assets/.gitkeep

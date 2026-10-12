# ManualChat — shared make targets for local development.
#
# This file is COMMITTED so a fresh clone gets the documented targets out of the
# box. Personal shortcuts and machine-specific aliases belong in `Makefile.local`
# (git-ignored), which is auto-loaded at the bottom of this file — see that file
# for examples. Targets there can add to, or shadow, anything listed here.

SHELL := /bin/bash
BACKEND_URL ?= http://localhost:8000
MODEL ?= ~deepseek/deepseek-flash-latest

.DEFAULT_GOAL := help

.PHONY: help build backend frontend down ps health models chat \
        logs-backend logs-frontend backend-shell clean

help: ## List all documented targets (shared + local)
	@grep -hE '^[a-zA-Z0-9_.-]+:.*## .*$$' $(MAKEFILE_LIST) | sort | awk -F ':.*## ' '{printf "  %-18s %s\n", $$1, $$2}'

build: ## Build both Docker images
	docker compose build

backend: ## Start the FastAPI backend on :8000 (terminal 1)
	docker compose up backend

frontend: ## Start the Next.js frontend on :3000 (terminal 2)
	docker compose up frontend

down: ## Stop and remove running containers
	docker compose down

ps: ## Show running compose services
	docker compose ps

health: ## GET /health on the backend
	curl -s $(BACKEND_URL)/health; echo

models: ## GET /models (available model slugs)
	curl -s $(BACKEND_URL)/models; echo

chat: ## POST /chat (usage: make chat Q="change the oil" [MODEL="~deepseek/deepseek-pro-latest"])
	curl -s -X POST $(BACKEND_URL)/chat -H 'Content-Type: application/json' -d '{"query":"$(Q)","model":"$(MODEL)"}'; echo

logs-backend: ## Tail backend logs
	docker compose logs -f backend

logs-frontend: ## Tail frontend logs
	docker compose logs -f frontend

backend-shell: ## Open a bash shell in the backend container
	docker compose exec backend bash

clean: ## Stop containers and remove orphans
	docker compose down --remove-orphans

# Personal aliases (git-ignored) are loaded last so they can add/shadow targets.
# The leading '-' means a missing Makefile.local is not an error.
-include Makefile.local
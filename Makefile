# ManualChat — shared make targets for local development.
#
# This file is COMMITTED so a fresh clone gets the documented targets out of the
# box. Personal shortcuts and machine-specific aliases belong in `Makefile.local`
# (git-ignored), which is auto-loaded at the bottom of this file — see that file
# for examples. Targets there can add to, or shadow, anything listed here.

SHELL := /bin/bash
BACKEND_URL ?= http://localhost:8000
FRONTEND_URL ?= http://localhost:3000
MODEL ?= ~deepseek/deepseek-flash-latest

.DEFAULT_GOAL := help

.PHONY: help build backend frontend down ps status health models chat \
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

# Source is bind-mounted and hot-reloaded, so a running service always serves the
# files on disk. "Up to date" therefore checks the two things that can drift:
# baked dependencies (the image) and the git working tree.
status: ## Check services run and are up to date
	@set -u; \
	echo; echo "Services"; \
	curl -fsS -m 3 -o /dev/null 2>/dev/null "$(BACKEND_URL)/health" && echo "  backend           running  ($(BACKEND_URL)/health)" || echo "  backend           NOT running"; \
	curl -fsS -m 3 -o /dev/null 2>/dev/null "$(FRONTEND_URL)/" && echo "  frontend          running  ($(FRONTEND_URL)/)" || echo "  frontend          NOT running"; \
	echo; echo "Docker images (stale = a dependency manifest changed after the build)"; \
	check_img() { \
		local label="$$1" image="$$2"; shift 2; \
		local created im nm t f; \
		created="$$(docker image inspect --format '{{.Created}}' "$$image" 2>/dev/null)"; \
		if [ -z "$$created" ]; then echo "  $$label  not built"; return; fi; \
		im="$$(date -u -d "$$created" +%s)"; nm=0; \
		for f in "$$@"; do t="$$(stat -c %Y "$$f" 2>/dev/null || echo 0)"; [ "$$t" -gt "$$nm" ] && nm=$$t; done; \
		if [ "$$nm" -gt "$$im" ]; then echo "  $$label  STALE (run: make build)"; else echo "  $$label up to date"; fi; \
	}; \
	check_img "backend image" manualchat-backend backend/uv.lock backend/pyproject.toml backend/Dockerfile; \
	check_img "frontend image" manualchat-frontend frontend/package.json frontend/package-lock.json frontend/Dockerfile; \
	echo; echo "Git"; \
	echo "  branch            $$(git rev-parse --abbrev-ref HEAD)"; \
	upstream="$$(git rev-parse --abbrev-ref --symbolic-full-name @{u} 2>/dev/null)"; \
	if [ -n "$$upstream" ]; then \
		ahead="$$(git rev-list --count @{u}..HEAD 2>/dev/null || echo 0)"; \
		behind="$$(git rev-list --count HEAD..@{u} 2>/dev/null || echo 0)"; \
		echo "  vs upstream       $$upstream (ahead $$ahead, behind $$behind; last-known, run 'git fetch' to refresh)"; \
	else \
		echo "  upstream          none (branch not pushed)"; \
	fi; \
	changes="$$(git status --porcelain | wc -l | tr -d ' ')"; \
	if [ "$$changes" = "0" ]; then echo "  changes           working tree clean"; else echo "  changes           $$changes uncommitted (run: git status)"; fi; \
	echo

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
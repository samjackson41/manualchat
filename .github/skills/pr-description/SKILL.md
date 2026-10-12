---
name: pr-description
description: |
  Draft and post a pull-request description for the current branch with the gh
  CLI. It reads the repo PR template, summarizes the real diff, validates the
  checks the description claims, then creates the PR or updates it if one
  already exists. Use when the user says "draft a PR description", "post a PR",
  "open a PR", "write the PR body", "create the pull request", or asks to do
  any of these with gh.
license: MIT
compatibility: claude-code cursor codex gemini-cli opencode
metadata:
  version: "1.0.0"
---

# Pull-request description

Draft a pull-request description that tells the truth about the diff, then post
it with the gh CLI. Do the steps in order. Do not skip a step.

## When to use

Use this skill when the user asks for a PR description, or for opening or
posting a pull request. The repo is ManualChat (FastAPI and LangGraph backend,
Next.js frontend). The rules for that repo are in its `CONTRIBUTING.md` and its
`.github/PULL_REQUEST_TEMPLATE.md`.

## Steps

### 1. Gather context

Read `README.md`, `DECISIONS.md`, and `PROGRESS.md` at the start. They hold the
current state, the plan, and the ratified decisions.

Then find what the branch actually changes:

- `git status` and `git branch --show-current` to name the branch.
- `git log --oneline main..HEAD` to list the commits on the branch.
- `git diff --stat main...HEAD` to see which files changed.
- `git diff main...HEAD -- <changed files>` to read the changes you will
  describe.

Read the repo PR template at `.github/PULL_REQUEST_TEMPLATE.md` and keep its
section headings.

### 2. Draft the description

Write the draft to a file in `/tmp` (for example
`/tmp/manualchat-pr-body.md`). Never save it inside the repo.

Follow the section headings of the repo PR template:

- Summary. One or two sentences. Say what changed and why.
- Scope. State whether the change stays inside the MVP scope.
- Deviations from DECISIONS.md. If the change corrects a ratified decision,
  say so here and update `DECISIONS.md`. Never diverge silently.
- How to test. Give the exact commands and the output a correct run shows.
- Evidence. Say where the proof lives (CI, local command output).
- Secrets and configuration. State that no keys are in the diff. Name any new
  env var or config key, and make sure `README.md` documents it.
- Checklist. Mark an item done only when it is true.

### 3. Validate before you claim

Run the checks the description mentions before you check the box
"Ran it locally and it works".

Backend, when the diff touches `backend/`:

```
cd backend && uv run python -m compileall -q agent api config.py llm.py __init__.py
```

Frontend, when the diff touches `frontend/`:

```
cd frontend && npm run typecheck && npm run build
```

If a check fails, say so. Do not claim a check passed.

### 4. Make sure gh is logged in

Run `gh auth status`. If it says you are not logged in, tell the user and ask
them to run `gh auth login`. Wait for them to confirm before you continue.

Never read, print, or echo a token or an API key. `gh auth status` shows a
masked token, which is fine.

### 5. Post the description

If the branch has no PR yet, create it:

```
gh pr create --base main --head <branch> \
  --title "<title>" --body-file /tmp/manualchat-pr-body.md
```

If the command says a PR already exists, update that PR instead. Never create a
duplicate:

```
gh pr view <number> --json title,state,body
gh pr edit <number> --title "<title>" --body-file /tmp/manualchat-pr-body.md
```

Use a Conventional Commit style title (for example
`chore(workflow): GitHub Flow guide, PR template, and CI`).

Verify the post:

```
gh pr view <number> --json title,url,state
```

## Rules

- One branch gets one PR into `main` (GitHub Flow). Squash-merge only.
- Never force-push, never delete a branch or a commit, never push without
  instruction, never merge.
- Never post a description that claims a check you did not run.
- Keep the description in plain English per the simple-english skill.

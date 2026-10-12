---
name: open-pr
description: |
  Open a pull request for the current branch with the gh CLI. It checks the gh
  login, runs the checks for the files the branch changes, drafts the body from
  the repo PR template, pushes the branch, creates the PR, and verifies the
  result. It updates an existing PR instead of opening a second one. Use when
  the user says "/open-pr", "open a PR", "open the PR", "push this branch and
  open a PR", "create the pull request", "raise a PR", "put this up for
  review", or asks to open a pull request with gh.
license: MIT
compatibility: claude-code cursor codex gemini-cli opencode
metadata:
  version: "1.0.0"
---

# Open a pull request

Open one pull request for the current branch with the gh CLI. Do the steps in
order. Do not skip a step. This skill replaces the former `pr-description`
skill and it drafts the body the same way.

A pull request (PR) is a request to merge one branch into `main`. The repo is
ManualChat. It has a FastAPI and LangGraph backend, a Next.js frontend, and
OpenRouter models. The merge rules are in `CONTRIBUTING.md`. The PR body
headings are in `.github/PULL_REQUEST_TEMPLATE.md`.

## Steps

### 1. Gather context

Read `README.md`, `DECISIONS.md`, and `PROGRESS.md`. They hold the current
state, the plan, and the ratified decisions.

Name the branch and the changes:

- `git branch --show-current` names the branch.
- `git status --short` shows uncommitted work.
- `git log --oneline main..HEAD` lists the commits on the branch.
- `git diff --stat main...HEAD` lists the changed files.
- `git diff main...HEAD -- <changed files>` shows the changes to describe.

Read `.github/PULL_REQUEST_TEMPLATE.md` and keep its section headings.

### 2. Check the branch is ready

Make sure that all work is committed. If `git status --short` shows changes,
commit them first with a Conventional Commit message. Do not open a PR for a
dirty tree.

Make sure that the branch name matches its type in `CONTRIBUTING.md`
(`feat/`, `fix/`, `chore/`, or `docs/`).

### 3. Run the checks

Run the checks for each path the branch changes. Report the command and the
output.

Backend, when the diff touches `backend/`:

```
cd backend && uv run python -m compileall -q agent api config.py llm.py __init__.py
```

Frontend, when the diff touches `frontend/`:

```
cd frontend && npm run typecheck && npm run build
```

If a check fails, stop and say so. Do not open a PR that fails a check.

### 4. Draft the body

Write the body to a file in `/tmp`, for example `/tmp/manualchat-pr-body.md`.
Never save the body inside the repo.

Follow the headings of the repo template:

- Summary. One or two sentences. Say what changed and why.
- Scope. State whether the change stays inside the MVP scope.
- Deviations from DECISIONS.md. Name any change to a ratified decision and
  update `DECISIONS.md`. Never diverge silently.
- How to test. Give the exact commands and the output of a correct run.
- Evidence. Say where the proof lives, such as the local output or CI.
- Secrets and configuration. State that the diff holds no keys. Name each new
  configuration key and make sure that `README.md` documents it.
- Checklist. Mark an item done only when it is true.

Keep the body in plain English per the simple-english skill.

### 5. Make sure gh is logged in

Run `gh auth status`. If the command says you are not logged in, tell the user
to run `gh auth login`. Wait for the user to confirm before you continue.

Never read, print, or echo a token or an API key. `gh auth status` shows a
masked token, and that is safe.

### 6. Push the branch

Push the branch and set its upstream:

```
git push -u origin <branch>
```

Push only when the user asked for a pull request or for a push. Never
force-push. Never delete a branch or a commit.

### 7. Create or update the PR

Make sure that no PR exists for the branch:

```
gh pr list --head <branch> --json number,title,url,state
```

If the list is empty, create the PR:

```
gh pr create --base main --head <branch> \
  --title "<title>" --body-file /tmp/manualchat-pr-body.md
```

Use a Conventional Commit style title, for example
`chore(workflow): open-pr skill`.

If a PR already exists, update it. Never create a duplicate:

```
gh pr edit <number> --title "<title>" --body-file /tmp/manualchat-pr-body.md
```

Add `--draft` to `gh pr create` when the user asks for a draft, or when the
branch work is incomplete.

### 8. Verify and report

Read back the result:

```
gh pr view <number> --json title,url,state,isDraft
```

Report the PR number, the title, the URL, and the state to the user.

## Rules

- One branch gets one PR into `main`. Merge with squash only.
- Never force-push, never delete a branch or a commit, never merge.
- Never push without a clear instruction from the user.
- Never claim a check that you did not run.
- Never read, print, or echo a secret, a token, or a `.env` file.
- Keep the body in plain English per the simple-english skill.

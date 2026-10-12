# ManualChat

A grounded repair-manual assistant. Backend is FastAPI and LangGraph. Frontend is
Next.js. Models come from OpenRouter.

## Read these first

Read `README.md`, `DECISIONS.md`, and `PROGRESS.md` at the start of every task.
They hold the current state, the plan, and the ratified decisions.

## The assistant runs with auto-approve

Plan first, then make one small change at a time. Commit each step with a
Conventional Commit message. After each step, run the cheapest check that proves
the change works and report the command and the output.

Never force-push, delete branches or commits, delete data, push, or open a pull
request without a clear instruction. Never read or print a secret, key, token, or
`.env` file. Work only inside this repo.

## Rules

- Every tunable value lives in config. Never hardcode it (DECISIONS P1).
- Secrets stay out of config and out of git.
- Write docs and pull request descriptions in plain English per the
  `simple-english` skill (`.github/skills/simple-english/SKILL.md`).
- Update `PROGRESS.md` at the end of each session.

## Where targeted rules live

- `backend/**` → `.github/instructions/backend.instructions.md`
- `frontend/**` → `.github/instructions/frontend.instructions.md`
- `**/*.md` → `.github/instructions/docs.instructions.md`
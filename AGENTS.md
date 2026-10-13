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
- Write a comment only when the code, the name, or the file cannot say it.
  Never restate the obvious. Keep an in-code comment to two lines at most, and
  prefer one line. Move anything longer into the docstring, the top of the file,
  or the wiki.
- Write docs and pull request descriptions in plain English per the
  `simple-english` skill (`.github/skills/simple-english/SKILL.md`).
- Update `PROGRESS.md` at the end of each session.
- Keep the graph-shape wiki page current. When a change touches the LangGraph
  graph, an agent tool, or the graph state (`backend/agent/graph.py`,
  `backend/tools.py`), update the Mermaid diagram and tables on the wiki `Home`
  page as part of that change. The wiki is a separate repo, checked out in the
  workspace as `manualchat.wiki/`, and the page file is `manualchat.wiki/Home.md`
  (rendered at https://github.com/samjackson41/manualchat/wiki/Home).

## Testing

- Prefer end-to-end and feature tests over unit tests. Write a unit test only
  when the behaviour cannot be verified live or end-to-end.
- Keep tests small and fast. Use simple inputs and human-readable outputs.
- Do not spend a lot of time on tests, and do not let them grow into a monolith.
- Run the cheapest check that proves the change works; report the command and
  its output.

## Where targeted rules live

The instruction files live in the VS Code workspace `.github/` folder, one level
above this repo. Their `applyTo` globs are relative to the workspace root:

- `**/backend/**` → `.github/instructions/backend.instructions.md`
- `**/frontend/**` → `.github/instructions/frontend.instructions.md`
- `**/*.md` → `.github/instructions/docs.instructions.md`
# Contributing to ManualChat

Short-lived **feature branches + pull requests** into a **protected `main`**.
Squash-merge so `main` stays one linear, reviewable history.

## Branch strategy (GitHub Flow)

- `main` is always runnable and is protected (see "Branch protection").
- Every change starts on a branch named by type:

  | Type     | Branch pattern      | Example              |
  |----------|---------------------|----------------------|
  | feature  | `feat/<kebab-case>` | `feat/rag-retrieval` |
  | fix      | `fix/<kebab-case>`  | `fix/openrouter-400` |
  | chore    | `chore/<kebab-case>`| `chore/git-workflow` |
  | docs     | `docs/<kebab-case>` | `docs/decisions-note`|

- One branch = one coherent change. Open the PR **early** (draft is fine) so
  there's always a review surface.

## Commit + PR conventions

- Commits follow [Conventional Commits](https://www.conventionalcommits.org/):
  `feat:`, `fix:`, `chore:`, `docs:`, `refactor:`, `test:`.
- PRs are **squash-merged** into a single Conventional-Commit message, so `main`
  reads like a changelog via `git log --oneline`.
- If a change contradicts a ratified decision, flag it in the PR body **and**
  update `DECISIONS.md` — never silently diverge.

## Branch protection (set up once on GitHub)

Settings → Branches → *Add branch protection rule* for `main`:

1. Require a pull request before merging (dismiss stale reviews on new commits).
2. Require approvals → **1** (mentor review or careful self-review is fine for a
   solo capstone).
3. Require **squash** merge (linear history).

## Day-to-day workflow

```bash
git checkout main && git pull
git checkout -b feat/rag-retrieval
# ... tinker, commit incrementally ...
git push -u origin feat/rag-retrieval
# open the PR, get a review, squash-merge, delete the branch
```

## Run & test

See `README.md`, or use the Makefile (`make help` for all targets):

- Terminal 1: `make backend`  (FastAPI on :8000)
- Terminal 2: `make frontend` (Next.js on :3000)

## Secrets

Never commit `OPENROUTER_API_KEY` (or any key/token). It is supplied at runtime:

```bash
OPENROUTER_API_KEY=sk-or-... docker compose up backend
```

`Makefile.local` and `.env` are git-ignored by design.
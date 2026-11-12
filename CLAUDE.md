# Working rules

## Ground yourself in the graph

`graphify-out/` holds a knowledge graph of the code, the docs, and the
decisions behind them. When `graphify-out/graph.json` exists, use it before you
read source:

1. `graphify query "<question>"` returns a scoped subgraph for a plain-language
   question. Start here.
2. `graphify path "<A>" "<B>"` traces how two things connect.
3. `graphify explain "<symbol>"` describes one node and its connections.
4. Read only the files and lines the graph points to. Fall back to grep or a
   full file read only when the graph misses.

Put this rule in every subagent prompt that explores code. Use
`graphify-out/GRAPH_REPORT.md` only for a broad architecture review.

## Keep the graph current

- After changing code, run `make graph` (`graphify update .`).
- After changing docs, run `/graphify --update` in the assistant. `make graph`
  refreshes code only.
- `graphify-out/` is generated and git-ignored. Rebuild it locally; never
  commit it.

## Isolate your work

Do each change on its own branch, in its own worktree:

1. Create both before you edit: `git worktree add ../manualchat-<topic> -b <type>/<topic>`.
2. Work and commit there, in Conventional Commits.
3. Push the branch and open a pull request into `main` when the work is ready.
4. After the pull request merges, remove the worktree
   (`git worktree remove ../manualchat-<topic>`) and delete the branch
   (`git branch -d <type>/<topic>`).

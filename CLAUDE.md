# Agent guide

Conventions for anyone (human or agent) working in this repo. Kept in sync with
[`AGENTS.md`](AGENTS.md).

## Code comments

Let the code speak for itself. Do **not** write comments that describe *what* the
code does — clear names, small functions, and obvious structure should make that
unnecessary. If a comment is restating the line below it, delete it and, if the code
wasn't clear enough on its own, improve the code instead (rename, extract, simplify).

Only add a comment when it captures something you genuinely cannot read from the code:

- **why** a non-obvious choice was made — a workaround, an ordering constraint, a
  perf tradeoff, a deliberate deviation from the obvious approach
- an **external gotcha** — an API quirk, a service limit, a spec/RFC reference
- a **pointer** to related code when the connection isn't visible locally
  (e.g. `see agent/db.py cache_get`)

Keep them short. Prefer one line. A paragraph of narration above a function is a
smell — move the durable parts into a docstring and cut the rest.

This applies to every language here: Python, JS/JSX, SQL, shell.

# Git worktree setup - copies .env and installs deps
# Usage: make worktree-setup
# Or with custom .env path: make worktree-setup ENV_SOURCE=../other/path/.env
ENV_SOURCE ?= ../../ai/.env

.PHONY: worktree-setup worktree-copy-env install

worktree-setup: worktree-copy-env install

worktree-copy-env:
	@if [ -f "$(ENV_SOURCE)" ]; then \
		cp "$(ENV_SOURCE)" .; \
		echo "Copied .env from $(ENV_SOURCE)"; \
	else \
		echo "Error: $(ENV_SOURCE) not found."; \
		echo "Your worktree directory structure may be incorrect."; \
		echo "Expected: projects/prefix/branch-name (e.g., projects/feat/my-feature)"; \
		echo "Make sure your branch uses a prefix (feat/, test/, yourname/) so the path resolves."; \
		echo "Or specify a custom path: make worktree-setup ENV_SOURCE=/path/to/.env"; \
		exit 1; \
	fi

# app/ tracks pnpm-lock.yaml but README and run.sh drive npm, and the lockfile is stale
# (missing @supabase/supabase-js), so a frozen install fails. --no-package-lock installs
# from package.json ranges without writing a second lockfile into the worktree.
install:
	uv sync --frozen
	cd app && npm install --no-package-lock --no-audit --no-fund

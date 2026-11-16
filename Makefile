# Everything CI runs. Needs uv (Python tests and lint) and pnpm (dashboard).
PY ?= 3.9   # oldest Python hooks may run under (macOS /usr/bin/python3)

.PHONY: check test lint docs ui ui-dev ui-typecheck plugin-validate

check: lint test ui-typecheck plugin-validate  ## what CI runs

test:  ## offline tests in throwaway HOMEs; FILTER=-k\ name to select
	uv run --python $(PY) --with pytest pytest $(FILTER)

docs:  ## regenerate docs/reference/cli.md
	PYTHONPATH=src python3 -c 'from ai_toolkit.cli import reference_markdown as r; print(r(), end="")' > docs/reference/cli.md

lint:
	uvx ruff check src tests bin hooks

ui:  ## build the dashboard into ui/dist
	pnpm -C ui install --frozen-lockfile && pnpm -C ui build

ui-typecheck:
	pnpm -C ui install --frozen-lockfile && pnpm -C ui typecheck

ui-dev:  ## API on :7319 and Vite with hot reload; open the URL Vite prints
	bin/ait ui --api-only & pnpm -C ui dev

plugin-validate:  ## skipped when the claude CLI isn't installed (e.g. in CI)
	@command -v claude >/dev/null && claude plugin validate . || echo "claude CLI not found; skipping plugin validate"

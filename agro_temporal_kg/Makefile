.PHONY: run_checks


run_checks:
	uv run ruff format
	uv run ruff check . --fix
	uv run pytest
	uv run mypy

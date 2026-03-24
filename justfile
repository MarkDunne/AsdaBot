default:
    @just --list

lint:
    uv run ruff check asdabot/
    uv run ruff format --check asdabot/

fix:
    uv run ruff check --fix asdabot/
    uv run ruff format asdabot/

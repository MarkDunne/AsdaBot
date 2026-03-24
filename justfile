default:
    @just --list

lint:
    uv run ruff check asdabot/
    uv run ruff format --check asdabot/

fix:
    uv run ruff check --fix asdabot/
    uv run ruff format asdabot/

# Bump version and publish to PyPI. Usage: just publish patch|minor|major
publish bump="patch":
    uv version --bump {{bump}}
    uv build
    uv publish

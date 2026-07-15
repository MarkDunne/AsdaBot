default:
    @just --list

# Re-authenticate with ASDA (opens a browser to log in). Run this when the refresh token is rejected.
login:
    uv run asdabot auth login

lint:
    uv run ruff check asdabot/ tests/
    uv run ruff format --check asdabot/ tests/

test:
    uv run pytest tests/ -q

fix:
    uv run ruff check --fix asdabot/
    uv run ruff format asdabot/

# Bump version and publish to PyPI. Usage: just publish patch|minor|major
publish bump="patch":
    uv version --bump {{bump}}
    sed -i '' 's/"version": "[^"]*"/"version": "'$(uv version | awk '{print $2}')'"/' .claude-plugin/plugin.json
    uv build
    uv publish

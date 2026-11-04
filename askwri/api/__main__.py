"""Run the API: `uv run python -m askwri.api` (set PORT=8787 locally to keep 8080 for the agent)."""

from askwri.api.server import serve

serve()

"""The AskWRI API between the browser and the agent: streams chat events from AgentCore Runtime
and hands out short-lived PDF download links. Runs on Lambda (Lambda Web Adapter, response
streaming) or locally with `uv run python -m askwri.api`."""

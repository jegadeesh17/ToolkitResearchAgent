# Changelog

All notable changes to this project will be documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Antigravity CLI (`agy`) model backend (`agent/agy_client.py`), selected with `LLM_BACKEND=agy`; calls run in plan mode from a prompt file and cost nothing on the API side.
- Composio catalog check (`scripts/composio_catalog.py`, `agent/score.catalog_agreement`): the agent's auth methods compared with the auth schemes of Composio's own toolkits.
- Wilson 95% confidence intervals on every accuracy figure (`agent/score.wilson`).
- Rule: an official or third-party MCP claim without a URL is downgraded to `unknown`.
- Apps with no vendor-hosted API (CLI tools) are recorded as `none_public` and `blocked`.
- Per-category random sample (`scripts/make_splits.py`) and an offline hand-labelling form (`verification/label.html`).

### Changed
- Scoring is set up for hand labels instead of AI-made reference labels.
- Auth-method definitions follow Composio's own wording.
- The report leads with outreach tiers: ready to build, needs outreach, blocked.

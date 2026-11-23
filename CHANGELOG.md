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
- A shorter 10-app labelling form for verdict and auth methods (`verification/quick_label.html`).
- Published pass-1 results for all 100 apps and the report site, deployed to GitHub Pages.

### Changed
- Scoring is set up for hand labels instead of AI-made reference labels.
- Auth-method definitions follow Composio's own wording.
- The report leads with outreach tiers: ready to build, needs outreach, blocked.
- The report uses a light theme.
- The report shows no accuracy figure until hand labels exist, and states how many apps pass 2 covered.
- `S2S_OAUTH2` catalog schemes count as OAuth 2.0.

### Removed
- The AI reference-label import and spot-check tools, and their report sections.

### Fixed
- The report no longer says a person labelled the sample, or that results were verified, when no labels were made.
- The headline no longer calls every gated app "needs outreach"; paid-plan and app-review gates are counted as gated.
- Pass-2 catalog agreement is scored only on the apps pass 2 covered, instead of counting the rest as misses.
- The run-stats table no longer shows an empty "?" model row.
- `python -m agent.validate --help` no longer crashes on a cp1252 console.
- README setup, configuration defaults and reproduction steps match the code.

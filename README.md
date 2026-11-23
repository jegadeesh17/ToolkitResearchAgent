# Toolkit Research Agent

Which of 100 SaaS apps could become an AI-agent toolkit today? This repository implements an autonomous research agent that analyzes each app's official developer documentation, extracts authentication schemes, developer onboarding pathways, API breadths, and build blockers — with verbatim quote citations for every answer — verifies predictions across multi-model consensus and bounded re-research loops, and cross-checks accuracy against hand-checked human ground truth with Wilson confidence intervals, as well as Composio's real-world catalog of 1,519+ toolkits.

Builds on my September 2026 attempt at this brief ([ToolkitBuildabilityResearch](https://github.com/jegadeesh17/ToolkitBuildabilityResearch)); this version adds stricter evidence rules, a check against Composio's own catalog and Wilson confidence intervals.

**Results in this submission:** pass 1 covers all 100 apps. Pass 2 (second model, judge, re-research) is built and tested but was stopped after 19 apps to meet the deadline, so the published results are pass 1. Accuracy against hand labels was not measured: the labelling form and scoring code are included (`verification/label.html`, `agent/score.py`), but no labels were completed in time.

The full findings are published as a standalone interactive case study in `site/index.html` and reproducible data in `site/results.json`.

---

## Architecture & Pipeline

```
data/apps.json (100 apps, 10 categories)
  │
  ├─ PASS 1  agent/run.py → agent/pipeline.py          (concurrency 4)
  │    Search (4 query templates) → fetch ≤6 official pages → evidence bundle
  │    → schema-bound extraction via Antigravity CLI (gemini-3.8-flash-medium)
  │    → schema validation + repair loops → consistency rules → quote grounding
  │    → results/pass1.json
  │
  ├─ PASS 2  agent/verify.py
  │    L1 Deterministic quote grounding
  │    L2 Cross-model extraction via Antigravity CLI (gpt-oss-120b-medium)
  │    L3 Adjudication judge for disputed fields (claude-sonnet-4-6)
  │    L4 Bounded re-research (≤5 targeted tool calls for missing citations)
  │    → results/pass2.json (all changes audited in pass2_diff)
  │
  ├─ CATALOG CHECK  scripts/composio_catalog.py
  │    Fetch Composio's live 1,519-toolkit catalog from GitHub
  │    Compare predicted auth schemes against Composio's supported schemes
  │    → verification/catalog_agreement.json
  │
  ├─ SCORING  agent/score.py
  │    Score Pass 1 & Pass 2 against verification/ground_truth.json (human hand-labels)
  │    Compute field-level accuracies and Wilson 95% binomial confidence intervals
  │    → verification/score_report_pass1.json, score_report_pass2.json, compare.json
  │
  └─ REPORT  scripts/build_site.py → site/index.html + site/results.json
```

### Core Tenets

- **Grounded Evidence or `unknown`:** Every answered field contains `{url, quote}`. Quotes must be verbatim substrings of the cited page. If no documentation confirms an answer, it is recorded as `unknown` with a specific diagnostic reason.
- **No API spend:** model calls run through the Antigravity CLI (`agy`) on the owner's plan, so LLM cost is recorded as $0. Three model families are used: `gemini-3.8-flash-medium` (pass 1), `gpt-oss-120b-medium` (second model) and `claude-sonnet-4-6` (judge).
- **Resilient Tooling:** Automated developer doc retrieval uses Composio search with automated fallback to direct Tavily search/extract and DuckDuckGo.
- **Auditable Observability:** Every search, page fetch, LLM inference, retry, latency, and status is logged to `results/runs/run_log.jsonl`.

---

## Quickstart

### Prerequisites
- Python 3.13
- Antigravity CLI (`agy`) installed and authenticated
- Composio API key (from [dashboard.composio.dev](https://dashboard.composio.dev))

### Setup

```bash
# Clone and prepare virtual environment
git clone https://github.com/jegadeesh17/ToolkitResearchAgent.git
cd ToolkitResearchAgent
python -m venv .venv
.venv\Scripts\activate            # Windows  (source .venv/bin/activate on Unix)
pip install -r requirements.txt

# Run offline unit test suite (no API keys required)
pytest -q

# Set environment variables
export LLM_BACKEND=agy
export PASS1_MODEL=gemini-3.8-flash-medium
export VERIFY_MODEL=gpt-oss-120b-medium
export JUDGE_MODEL=claude-sonnet-4-6

# Configure keys
cp .env.example .env              # Add COMPOSIO_API_KEY (and optional TAVILY_API_KEY)
```

### Reproducing the Pipeline

```bash
# 1. Pass 1: Initial research across all 100 apps
python -m agent.run --all --resume --concurrency 4
python -m agent.validate results/pass1.json --expect 100

# 2. Pass 2: Verification, cross-model consensus, and judge adjudication
python -m agent.verify --concurrency 4
python -m agent.validate results/pass2.json --expect 100

# 3. Check consistency against Composio's real catalog
python scripts/composio_catalog.py --fetch
python scripts/composio_catalog.py --check results/pass1.json results/pass2.json

# 4. Score against hand-labeled human ground truth
python -m agent.score --compare results/pass1.json results/pass2.json

# 5. Build static case-study site
python scripts/build_site.py
python -m playwright install chromium && python scripts/qa_site.py
```

---

## Configuration

Settings are managed via environment variables or `.env` (`.env` is strictly gitignored):

| Variable | Default | Purpose |
|---|---|---|
| `LLM_BACKEND` | `agy` | LLM execution engine (`agy` for Antigravity CLI, `openrouter` for API) |
| `PASS1_MODEL` | `gemini-3.8-flash-medium` | First-pass research model |
| `VERIFY_MODEL` | `gpt-oss-120b-medium` | Second-pass cross-model verification model |
| `JUDGE_MODEL` | `claude-sonnet-4-6` | Adjudication judge for disputed fields |
| `COMPOSIO_API_KEY` | *(Required)* | Project API key for Composio developer tools |
| `TAVILY_API_KEY` | *(Optional)* | Direct Tavily API key for search/extract fallback |
| `BUDGET_CAP_USD` | `4.00` | Safety spending cap guardrail |

---

## Known Limitations & Tradeoffs

1. **No measured accuracy:** no hand labels were completed in the submission window, so the report gives no accuracy figure. The evidence offered instead is the verbatim-quote check on every answer and agreement with Composio's own catalog (53 of 59 catalogued apps).
2. **Catalog Agreement Scope:** Composio's toolkit catalog represents integrations currently supported by Composio (often a focused subset of an app's total public API), so catalog agreement serves as a consistency check rather than absolute ground truth.
3. **Execution Limits & Throughput:** Antigravity CLI local concurrency and rate limits bound how frequently the full 100-app pipeline can be re-run from scratch.
4. **Retrieval Blindspots:** Documentation gated behind enterprise logins, single-page client-rendered JavaScript apps without static mirrors, or downloadable PDF manuals can result in `unknown` fields.
5. **No Direct Browser Automation:** Analysis is conducted over static HTML and Markdown extractions rather than headless browser interaction.

---

## Project Structure

```
agent/           Core pipeline, verification loops, agy client, scoring, budget guard
scripts/         Site builder, Composio catalog check, QA test scripts
data/            100 target apps, catalog aliases, and held-out evaluation splits
results/         Pass 1 & Pass 2 results, run logs, and pilot benchmarks
site/            Static case study site (index.html) and published data
tests/           Comprehensive offline unit and contract test suites
```

---

## How This Was Built

Designed and built by jegadeesh17 with [SoftwareEngineeringAgents](https://github.com/jegadeesh17/SoftwareEngineeringAgents), a multi-agent workflow for Claude Code and Antigravity. All architecture calls and test runs were made and checked by the project owner.

---

## License

[MIT](LICENSE)

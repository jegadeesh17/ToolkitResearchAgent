"""Composio catalog integration script.

Fetches the Composio toolkits catalog, suggests slug matches for data/apps.json,
builds data/composio_catalog.json, and checks pass1/pass2 results against Composio auth schemes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import httpx  # noqa: E402

from agent.score import catalog_agreement  # noqa: E402
from agent.store import load_apps, load_results  # noqa: E402

TOOLKITS_URL = "https://raw.githubusercontent.com/ComposioHQ/composio/main/docs/public/data/toolkits.json"
RAW_TOOLKITS_PATH = Path("results/raw/composio_toolkits.json")
META_PATH = Path("data/composio_catalog_meta.json")
APPS_PATH = Path("data/apps.json")
SUGGESTED_PATH = Path("data/composio_aliases.suggested.json")
ALIASES_PATH = Path("data/composio_aliases.json")
CATALOG_PATH = Path("data/composio_catalog.json")
VERIFICATION_DIR = Path("verification")


def _norm(s: str) -> str:
    """Normalize string to lowercase alphanumerics."""
    return re.sub(r"[^a-z0-9]", "", s.lower())


def fetch_toolkits(url: str = TOOLKITS_URL, raw_path: Path = RAW_TOOLKITS_PATH, meta_path: Path = META_PATH) -> int:
    """Download toolkits catalog, save to raw_path, record sha256 and fetch time in meta_path."""
    print(f"Fetching toolkits from {url}...")
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.parent.mkdir(parents=True, exist_ok=True)

    with httpx.Client(timeout=60.0) as client:
        resp = client.get(url)
        resp.raise_for_status()
        content = resp.content

    raw_path.write_bytes(content)
    sha256 = hashlib.sha256(content).hexdigest()
    fetched_at = datetime.now(UTC).isoformat()

    try:
        data = json.loads(content.decode("utf-8"))
        count = len(data) if isinstance(data, list) else 0
    except Exception:
        count = 0

    meta = {
        "source_url": url,
        "fetched_at": fetched_at,
        "sha256": sha256,
        "toolkit_count": count,
    }
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"Saved {count} toolkits to {raw_path}")
    print(f"SHA256: {sha256}")
    print(f"Fetched at: {fetched_at}")
    return 0


def suggest_aliases(
    apps_path: Path = APPS_PATH,
    raw_path: Path = RAW_TOOLKITS_PATH,
    suggested_path: Path = SUGGESTED_PATH,
) -> int:
    """Match apps in data/apps.json against toolkits slugs and names."""
    if not raw_path.exists():
        print(f"Error: {raw_path} not found. Run with --fetch first.", file=sys.stderr)
        return 1

    toolkits: list[dict[str, Any]] = json.loads(raw_path.read_text(encoding="utf-8"))
    apps = load_apps(apps_path)

    # Build lookup maps. Slugs ending in _mcp never count as the app's own toolkit.
    exact_slug: dict[str, str] = {}
    norm_slug: dict[str, str] = {}
    norm_name: dict[str, str] = {}

    for t in toolkits:
        slug = t.get("slug")
        if not slug or slug.endswith("_mcp"):
            continue
        exact_slug[slug.lower()] = slug
        norm_slug[_norm(slug)] = slug
        name = t.get("name")
        if name:
            norm_name[_norm(name)] = slug

    suggested: dict[str, str | None] = {}
    unmatched: list[tuple[int, str]] = []

    for app in apps:
        app_id_str = str(app.id)
        name = app.app
        n_name = _norm(name)

        matched_slug: str | None = None
        # 1. Exact match on slug
        if name.lower() in exact_slug:
            matched_slug = exact_slug[name.lower()]
        # 2. Normalized match on slug
        elif n_name in norm_slug:
            matched_slug = norm_slug[n_name]
        # 3. Normalized match on toolkit name
        elif n_name in norm_name:
            matched_slug = norm_name[n_name]

        suggested[app_id_str] = matched_slug
        if matched_slug is None:
            unmatched.append((app.id, name))

    suggested_path.parent.mkdir(parents=True, exist_ok=True)
    suggested_path.write_text(json.dumps(suggested, indent=2), encoding="utf-8")

    matched_count = len(apps) - len(unmatched)
    print(f"Suggested matches: {matched_count}/{len(apps)} apps matched.")
    print(f"Wrote suggestions to {suggested_path}")
    if unmatched:
        print(f"\nUnmatched apps ({len(unmatched)}):")
        for aid, aname in unmatched:
            print(f"  [{aid}] {aname}")

    return 0


def build_catalog(
    apps_path: Path = APPS_PATH,
    aliases_path: Path = ALIASES_PATH,
    raw_path: Path = RAW_TOOLKITS_PATH,
    catalog_path: Path = CATALOG_PATH,
) -> int:
    """Build data/composio_catalog.json from aliases and raw toolkits."""
    if not raw_path.exists():
        print(f"Error: {raw_path} not found. Run with --fetch first.", file=sys.stderr)
        return 1
    if not aliases_path.exists():
        print(f"Error: {aliases_path} not found. Generate or create it first.", file=sys.stderr)
        return 1

    toolkits: list[dict[str, Any]] = json.loads(raw_path.read_text(encoding="utf-8"))
    toolkits_by_slug = {t.get("slug"): t for t in toolkits if t.get("slug")}

    apps = load_apps(apps_path)
    aliases_raw = json.loads(aliases_path.read_text(encoding="utf-8"))

    # Convert aliases_raw to {int_id: slug}
    aliases: dict[int, str | None] = {}
    if isinstance(aliases_raw, dict):
        for k, v in aliases_raw.items():
            aliases[int(k)] = v
    elif isinstance(aliases_raw, list):
        for item in aliases_raw:
            aliases[int(item["id"])] = item.get("slug")

    catalog: list[dict[str, Any]] = []
    in_catalog_count = 0

    for app in apps:
        slug = aliases.get(app.id)
        auth_schemes: list[str] = []
        if slug:
            tk = toolkits_by_slug.get(slug)
            if tk:
                auth_schemes = list(tk.get("authSchemes") or [])
                in_catalog_count += 1
            else:
                print(f"Warning: slug '{slug}' for app [{app.id}] {app.app} not found in toolkits.", file=sys.stderr)
                slug = None

        catalog.append({
            "id": app.id,
            "app": app.app,
            "slug": slug,
            "authSchemes": auth_schemes,
        })

    catalog_path.parent.mkdir(parents=True, exist_ok=True)
    catalog_path.write_text(json.dumps(catalog, indent=2), encoding="utf-8")
    print(f"Wrote catalog to {catalog_path}: {in_catalog_count}/{len(apps)} apps in Composio catalog.")
    return 0


def check_agreement(
    pass1_path: Path,
    pass2_path: Path,
    catalog_path: Path = CATALOG_PATH,
    meta_path: Path = META_PATH,
    out_path: Path = VERIFICATION_DIR / "catalog_agreement.json",
) -> int:
    """Compare Pass 1 and Pass 2 results against Composio catalog."""
    if not catalog_path.exists():
        print(f"Error: {catalog_path} not found. Run build first.", file=sys.stderr)
        return 1
    if not pass1_path.exists():
        print(f"Error: {pass1_path} not found.", file=sys.stderr)
        return 1
    if not pass2_path.exists():
        print(f"Error: {pass2_path} not found.", file=sys.stderr)
        return 1

    catalog: list[dict[str, Any]] = json.loads(catalog_path.read_text(encoding="utf-8"))
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}

    p1_rows = load_results(pass1_path)
    p2_rows = load_results(pass2_path)

    res1 = catalog_agreement(p1_rows, catalog)
    # Pass 2 covers only a subset of the apps; score it on the catalog entries it contains.
    ids2 = {r.id for r in p2_rows}
    res2 = catalog_agreement(p2_rows, [c for c in catalog if c.get("id") in ids2])

    report = {
        "pass1": res1,
        "pass2": res2,
        "catalog_meta": meta,
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Catalog agreement check written to {out_path}")
    print(f"Pass 1: n={res1['n']} covers_all={res1['covers_all']} ({res1['covers_all_rate']*100:.1f}%) "
          f"overlaps={res1['overlaps']} CI=[{res1['ci_low']}, {res1['ci_high']}]")
    print(f"Pass 2: n={res2['n']} covers_all={res2['covers_all']} ({res2['covers_all_rate']*100:.1f}%) "
          f"overlaps={res2['overlaps']} CI=[{res2['ci_low']}, {res2['ci_high']}]")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Composio toolkits catalog helper and verification.")
    parser.add_argument("--fetch", action="store_true", help="Download toolkits.json from GitHub")
    parser.add_argument("--suggest", action="store_true", help="Suggest slug matches for data/apps.json")
    parser.add_argument("--build", action="store_true", help="Build data/composio_catalog.json from aliases")
    parser.add_argument(
        "--check", nargs=2, metavar=("PASS1", "PASS2"), help="Check catalog agreement for pass1 and pass2"
    )

    args = parser.parse_args(argv)

    if args.fetch:
        return fetch_toolkits()
    if args.suggest:
        return suggest_aliases()
    if args.check:
        return check_agreement(Path(args.check[0]), Path(args.check[1]))
    # Default or --build
    return build_catalog()


if __name__ == "__main__":
    sys.exit(main())

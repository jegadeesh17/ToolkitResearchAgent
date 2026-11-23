"""Seeded, stratified splits: held-out sample (2/category by default) + 10-app pilot (1/category)."""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def make_splits(apps: list[dict], seed: int, per_category: int = 2) -> tuple[list[int], list[int]]:
    """Return (sample_ids, pilot_ids). Pilot is sorted and drawn from non-sample apps.

    The sample is ordered in rounds: the first 2 picks of every category (sorted), then each later
    pick (sorted), so a labeller who stops after round 1 still holds a 2-per-category sample.
    """
    if per_category < 2:
        raise ValueError("per_category must be at least 2")
    rng = random.Random(seed)
    by_cat: dict[str, list[int]] = defaultdict(list)
    for a in apps:
        by_cat[a["category"]].append(a["id"])
    rounds: list[list[int]] = [[] for _ in range(per_category - 1)]
    pilot: list[int] = []
    for cat in sorted(by_cat):  # fixed iteration order keeps the split reproducible
        ids = sorted(by_cat[cat])
        chosen = rng.sample(ids, per_category)
        rounds[0] += chosen[:2]
        for r, app_id in enumerate(chosen[2:], start=1):
            rounds[r].append(app_id)
        pilot += rng.sample([i for i in ids if i not in chosen], 1)
    sample = [i for rnd in rounds for i in sorted(rnd)]
    return sample, sorted(pilot)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--apps", default=str(ROOT / "data" / "apps.json"))
    ap.add_argument("--out-dir", default=str(ROOT / "data"))
    ap.add_argument("--per-category", type=int, default=2, help="sample size per category (default 2)")
    args = ap.parse_args(argv)
    apps = json.loads(Path(args.apps).read_text(encoding="utf-8"))
    sample, pilot = make_splits(apps, args.seed, args.per_category)
    out = Path(args.out_dir)
    for name, ids in (("sample", sample), ("pilot", pilot)):
        meta = {"seed": args.seed, "per_category": args.per_category} if name == "sample" else {"seed": args.seed}
        payload = json.dumps({**meta, "ids": ids}) + "\n"
        (out / f"{name}.json").write_text(payload, encoding="utf-8")
    print(f"sample={len(sample)} ids, pilot={len(pilot)} ids, seed={args.seed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

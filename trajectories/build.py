#!/usr/bin/env python3
"""Build the self-contained Trajectory Lens site.

Reads the m_v2 batch trajectory JSONs (out_batch by default, or pass a
different dir as argv[1]), joins in the GLM verifier scores for SWE and the
discrimination matrix, embeds everything into template.html, and writes
index.html next to this script.
"""
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA_DIR = Path(
    sys.argv[1] if len(sys.argv) > 1 else
    "/inspire/qb-ilm/project/qproject-fundationmodel/public/yelv_eval/"
    "fine_grained_eval/new_start_61/m_v2/out_batch"
)
M_V2 = DATA_DIR.parent  # discrimination matrix / verifier / out_full live one level up
FULL_DIR = M_V2 / "out_full"  # full-corpus per-trajectory metrics (analysis tabs)

# batch id -> trajectory file. batch ids match discrimination_matrix "sources".
BATCH_FILES = [
    ("swe_difficult", "swe_difficult_trajectories.json"),
    ("swe_codeact",   "swe_codeact_trajectories.json"),
    ("swe_sweagent",  "swe_sweagent_trajectories.json"),
    ("innovator",     "innovator_trajectories.json"),
    ("agency_openai", "agency_openai_trajectories.json"),
    ("agency_claude", "agency_claude_trajectories.json"),
    ("agency_publish", "agency_publish_trajectories.json"),
]

# full-corpus rows embedded per source are capped (stratified sample) so the
# page stays loadable now that out_full holds the true full corpora (~29k rows)
FULL_ROWS_CAP = int(__import__("os").environ.get("FULL_ROWS_CAP", "2000"))


def load_verifier() -> dict:
    """GLM verifier scores for swe_difficult, keyed by sample_name."""
    p = M_V2 / "verifier" / "scores_swe_difficult.jsonl"
    out = {}
    if not p.exists():
        print(f"[warn] missing {p}, SWE runs will have no verifier scores")
        return out
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        rec = json.loads(line)
        out[rec["sample_name"]] = {
            "resolved": rec.get("resolved"),
            "score": rec.get("score"),
            "confidence": rec.get("confidence"),
            "reason": rec.get("reason"),
        }
    return out


def load_full_metrics(template: str):
    """Slim full-corpus metric rows for the analysis tabs (Models/Insights +
    detail-view percentiles). Only the metric keys the template actually
    references are kept, so the payload stays small (no turns embedded)."""
    keys = sorted(set(re.findall(r"\bM\d+_[A-Za-z0-9_]+", template)))
    rows, counts = [], {}
    for batch, _ in BATCH_FILES:
        p = FULL_DIR / f"{batch}_metrics.json"
        if not p.exists():
            print(f"[warn] missing {p}, full corpus skips {batch}")
            continue
        recs = json.loads(p.read_text())
        counts[batch] = len(recs)
        if len(recs) > FULL_ROWS_CAP:
            import random
            recs = random.Random(0).sample(recs, FULL_ROWS_CAP)
            print(f"  [cap] {batch}: {counts[batch]} -> {len(recs)} embedded rows")
        for r in recs:
            met = {}
            for k in keys:
                v = r.get(k)
                if v is None:
                    continue
                if isinstance(v, float):
                    v = round(v, 6)
                met[k] = v
            rows.append({
                "sample_name": r.get("sample_name"),
                "batch": batch,
                "model": r.get("model") or None,
                "metrics": met,
            })
    print(f"  full corpus: {len(rows)} metric rows "
          f"({', '.join(f'{b}={n}' for b, n in counts.items())}) · "
          f"{len(keys)} whitelisted metric keys")
    return {"rows": rows, "counts": counts, "n_total": len(rows)}


def main() -> None:
    verifier = load_verifier()
    runs, joined = [], 0
    for batch, name in BATCH_FILES:
        p = DATA_DIR / name
        if not p.exists():
            print(f"[warn] missing {p}, skipping")
            continue
        recs = json.loads(p.read_text())
        for r in recs:
            r["batch"] = batch
            if batch == "swe_difficult" and r["sample_name"] in verifier:
                r["verifier"] = verifier[r["sample_name"]]
                joined += 1
        print(f"  {name}: {len(recs)} trajectories")
        runs.extend(recs)
    print(f"  verifier scores joined onto {joined} swe_difficult runs")

    # prefer the FULL-corpus discrimination matrix (3805 trajectories incl.
    # supersets); fall back to the old sample matrix if it is missing.
    discrimination = None
    for name in ("discrimination_matrix_full.json", "discrimination_matrix.json"):
        disc_path = M_V2 / name
        if disc_path.exists():
            discrimination = json.loads(disc_path.read_text())
            n_src = discrimination.get("n_per_source") or {}
            print(f"  discrimination matrix ({name}): "
                  f"{len(discrimination['matrix'])} metric rows, "
                  f"{len(discrimination['sources'])} sources, "
                  f"{sum(n_src.values())} trajectories")
            break
    if discrimination is None:
        print(f"[warn] no discrimination matrix found in {M_V2}")

    template = (HERE / "template.html").read_text()
    full = load_full_metrics(template)

    payload = {
        "generated_from": str(DATA_DIR),
        "runs": runs,
        "discrimination": discrimination,
        "full": full,
    }
    # compact dump; escape "</" so the inline <script> block can't be closed early
    blob = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    blob = blob.replace("</", "<\\/")

    marker = "/*__DATA__*/"
    assert marker in template, "template.html lost its /*__DATA__*/ marker"
    html = template.replace(marker, blob, 1)

    out = HERE / "index.html"
    out.write_text(html)
    print(f"wrote {out} ({out.stat().st_size/1e6:.2f} MB, {len(runs)} runs)")


if __name__ == "__main__":
    main()

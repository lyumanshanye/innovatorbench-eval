#!/usr/bin/env python3
"""Build the self-contained Trajectory Lens site.

Reads the m_v2 batch trajectory JSONs (out_batch by default, or pass a
different dir as argv[1]), joins in the GLM verifier scores for SWE and the
discrimination matrix, embeds everything into template.html, and writes
index.html next to this script.
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA_DIR = Path(
    sys.argv[1] if len(sys.argv) > 1 else
    "/inspire/qb-ilm/project/qproject-fundationmodel/public/yelv_eval/"
    "fine_grained_eval/new_start_61/m_v2/out_batch"
)
M_V2 = DATA_DIR.parent  # discrimination_matrix.json / verifier live one level up

# batch id -> trajectory file. batch ids match discrimination_matrix "sources".
BATCH_FILES = [
    ("swe_difficult", "swe_difficult_trajectories.json"),
    ("swe_codeact",   "swe_codeact_trajectories.json"),
    ("swe_sweagent",  "swe_sweagent_trajectories.json"),
    ("innovator",     "innovator_trajectories.json"),
    ("agency_openai", "agency_openai_trajectories.json"),
    ("agency_claude", "agency_claude_trajectories.json"),
]


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

    disc_path = M_V2 / "discrimination_matrix.json"
    discrimination = json.loads(disc_path.read_text()) if disc_path.exists() else None
    if discrimination:
        print(f"  discrimination matrix: {len(discrimination['matrix'])} metric rows, "
              f"{len(discrimination['sources'])} sources")
    else:
        print(f"[warn] missing {disc_path}")

    payload = {
        "generated_from": str(DATA_DIR),
        "runs": runs,
        "discrimination": discrimination,
    }
    # compact dump; escape "</" so the inline <script> block can't be closed early
    blob = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    blob = blob.replace("</", "<\\/")

    template = (HERE / "template.html").read_text()
    marker = "/*__DATA__*/"
    assert marker in template, "template.html lost its /*__DATA__*/ marker"
    html = template.replace(marker, blob, 1)

    out = HERE / "index.html"
    out.write_text(html)
    print(f"wrote {out} ({out.stat().st_size/1e6:.2f} MB, {len(runs)} runs)")


if __name__ == "__main__":
    main()

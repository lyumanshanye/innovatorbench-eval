#!/usr/bin/env python3
"""Build the self-contained Trajectory Lens site.

Reads the m_v2 batch trajectory JSONs (out_batch by default, or pass a
different dir as argv[1]), joins in the GLM verifier scores for SWE and the
discrimination matrix, embeds everything into template.html, and writes
index.html next to this script.
"""
import json
import math
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


def json_safe(value):
    """Return a standards-compliant JSON value tree.

    Python's json encoder emits bare NaN/Infinity tokens by default. They are
    accepted by Python's decoder but rejected by the browser's JSON.parse,
    which made the fully embedded Trajectory Lens payload unloadable. Missing
    or undefined numeric metrics are represented as JSON null instead.
    """
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [json_safe(item) for item in value]
    return value


def load_verifier() -> dict:
    """GLM verifier scores+reasons, keyed by sample_name. Merges the
    swe_difficult batch and the 150-sample full run so every run with a
    judged deliverable shows the judge's reason (2026-07-10)."""
    out = {}
    for name in ("scores_full_sample.jsonl", "scores_swe_difficult.jsonl"):
        p = M_V2 / "verifier" / name
        if not p.exists():
            print(f"[warn] missing {p}")
            continue
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


def load_archetypes() -> dict:
    """(source, sample_name) -> archetype id from the bottom-up failure
    taxonomy (failure_taxonomy/, length-controlled KMeans, 2026-07-10)."""
    import csv
    p = M_V2 / "failure_taxonomy" / "archetype_assignments_lengthctrl.csv"
    out = {}
    if not p.exists():
        print(f"[warn] missing {p}, no archetype badges")
        return out
    with open(p) as f:
        for r in csv.DictReader(f):
            out[(r["source"], r["sample_name"])] = int(r["archetype"])
    print(f"  archetype labels: {len(out)}")
    return out


# ---- zh translations (produced by m_v2/translate_zh.py, cached by md5) ----
ERR_MARKERS = ["traceback (most recent call last)", "error:", "errno", "no such file",
               "command not found", "syntaxerror", "exception:", "fatal:", "permission denied",
               "not found", "failed", "cannot ", "could not "]


def _unwrap_obs(msg):
    if msg and msg.startswith("{"):
        try:
            o = json.loads(msg)
            if isinstance(o, dict) and isinstance(o.get("message"), str):
                return o["message"]
        except Exception:
            pass
    return msg or ""


def _fail_scan(msg):
    """Keep in sync with template.html failScan + m_v2/translate_zh.py."""
    low = msg.lower()
    for mk in ERR_MARKERS:
        p = low.find(mk)
        while p != -1:
            ls = low.rfind("\n", 0, p) + 1
            if p < 200 or p - ls < 40:
                le = low.find("\n", p)
                end = min(len(msg), ls + 240) if le == -1 else min(le, ls + 240)
                line = msg[ls:end].strip()
                return line or msg[p:p + 160]
            p = low.find(mk, p + 1)
    return None


def load_zh() -> dict:
    import hashlib  # noqa: F401 (used below)
    p = DATA_DIR / "zh_cache.jsonl"
    out = {}
    if p.exists():
        for ln in p.read_text().splitlines():
            ln = ln.strip()
            if ln:
                try:
                    r = json.loads(ln)
                    out[r["h"]] = r["zh"]
                except Exception:
                    pass
    print(f"  zh cache: {len(out)} translations")
    return out


def zh_of(zh_map, text):
    import hashlib
    t = (text or "").strip()
    if len(t) < 6:
        return None
    return zh_map.get(hashlib.md5(t.encode("utf-8")).hexdigest())


def attach_zh(runs) -> None:
    zh = load_zh()
    n = 0
    for r in runs:
        for tu in r.get("turns") or []:
            z = zh_of(zh, tu.get("content"))
            if z:
                tu["content_zh"] = z; n += 1
            z = zh_of(zh, tu.get("thought"))
            if z:
                tu["thought_zh"] = z; n += 1
            if tu.get("success") is False:
                line = _fail_scan(_unwrap_obs(tu.get("obs_msg")))
                z = zh_of(zh, line) if line else None
                if z:
                    tu["freason_zh"] = z; n += 1
        v = r.get("verifier")
        if v and v.get("reason"):
            z = zh_of(zh, v["reason"])
            if z:
                v["reason_zh"] = z; n += 1
    print(f"  zh attached onto {n} fields")


def main() -> None:
    verifier = load_verifier()
    arch = load_archetypes()
    runs, joined = [], 0
    for batch, name in BATCH_FILES:
        p = DATA_DIR / name
        if not p.exists():
            print(f"[warn] missing {p}, skipping")
            continue
        recs = json.loads(p.read_text())
        for r in recs:
            r["batch"] = batch
            if r["sample_name"] in verifier:
                r["verifier"] = verifier[r["sample_name"]]
                joined += 1
            a = arch.get((batch, r["sample_name"]))
            if a is not None:
                r["archetype"] = a
        print(f"  {name}: {len(recs)} trajectories")
        runs.extend(recs)
    print(f"  verifier scores joined onto {joined} swe_difficult runs")
    attach_zh(runs)

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
    # data externalized to data.json (fetched async by the page) so the HTML
    # shell stays tiny and the browser never blocks parsing a ~28MB inline
    # <script> — that inline blob was crashing the tab (2026-07-18 fix).
    # Keep the external payload valid for the browser's strict response.json().
    # The explicit allow_nan=False is a final guard against future unsupported
    # numeric types escaping json_safe.
    blob = json.dumps(
        json_safe(payload),
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    )
    (HERE / "data.json").write_text(blob)

    out = HERE / "index.html"
    out.write_text(template)  # template fetches ./data.json on load
    print(f"wrote {out} ({out.stat().st_size/1e6:.3f} MB shell) + "
          f"data.json ({len(blob)/1e6:.2f} MB, {len(runs)} runs)")


if __name__ == "__main__":
    main()

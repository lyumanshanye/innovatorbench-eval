#!/usr/bin/env python3
"""
Inject Case Studies sections into M-class rubric pages.

Source of truth: the `trajExamples` JS array in index.html — already has curated
cases (Innovator/Agency/SWE/Claw) per metric. This script:

  1. Spawns node to evaluate the JS-literal array (handles all the unquoted keys
     and JS-only string syntax that defeat naive regex parsing).
  2. Groups by metric id.
  3. For every rubrics/m*.html whose id has cases, replaces / inserts a
     `<h2>Case Studies</h2>` block right before the `<h2>Source</h2>` heading.
  4. Pages whose id has no curated cases get a stub "no cases yet" note instead
     of being skipped silently — so it's obvious which ones still need data.

Re-running is idempotent: previous Case Studies blocks are detected by an
HTML comment marker and replaced.
"""
from __future__ import annotations

import html
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
INDEX = os.path.join(HERE, "index.html")
RUBRICS = os.path.join(HERE, "rubrics")

MARK_BEGIN = "<!-- BEGIN: M Case Studies (auto-injected) -->"
MARK_END = "<!-- END: M Case Studies -->"


# ---------- step 1: extract trajExamples via node ----------

def _eval_js_array(var_name: str) -> list[dict]:
    js = f"""
const fs = require('fs');
const txt = fs.readFileSync(process.argv[1], 'utf8');
const m = txt.match(/const {var_name} = \\[([\\s\\S]*?)^\\];/m);
if (!m) {{ console.error('{var_name} not found'); process.exit(1); }}
const body = m[1].replace(/\\/\\/[^\\n]*\\n/g, '\\n');
const arr = eval('[' + body + ']');
process.stdout.write(JSON.stringify(arr));
"""
    out = subprocess.check_output(
        ["node", "-e", js, INDEX], cwd=HERE, text=True
    )
    return json.loads(out)


def load_traj_examples() -> list[dict]:
    return _eval_js_array("trajExamples")


def load_metric_catalog() -> dict[str, dict]:
    arr = _eval_js_array("metricData")
    out = {}
    for e in arr:
        mid = e.get("id", "")
        if mid:
            out[mid] = e
        # M variants embedded under mVariant
        v = e.get("mVariant")
        if v and v.get("id"):
            out[v["id"]] = v
    return out


# ---------- step 2: render one case card ----------

BENCH_ORDER = [
    "InnovatorBench",
    "AgencyBench",
    "SWE-bench",
    "ClawBench",
    # Aggregate / meta cards land last
    "Aggregate Snapshot",
]


def _bench_rank(b: str) -> int:
    if b in BENCH_ORDER:
        return BENCH_ORDER.index(b)
    if b.startswith("Aggregate"):
        return len(BENCH_ORDER)
    return len(BENCH_ORDER) + 1


def render_step(s) -> str:
    if isinstance(s, str):
        return (
            f'<span class="traj-step traj-action">{html.escape(s)}</span>'
        )
    cls = s.get("c", "action")
    return (
        f'<span class="traj-step traj-{html.escape(cls)}">'
        f'{html.escape(s.get("t", ""))}</span>'
    )


def render_case(c: dict) -> str:
    badge_cls = c.get("badge", "")
    val = html.escape(c.get("val", ""))
    name = html.escape(c.get("name", ""))
    src = html.escape(c.get("src", ""))
    desc = html.escape(c.get("desc", ""))
    formula = c.get("formula", "")  # may contain HTML (<br>) — keep verbatim
    steps = c.get("steps", [])
    sep = '<span class="traj-arrow">&rarr;</span>'
    steps_html = sep.join(render_step(s) for s in steps)
    badge_class = "metric-value-badge" + (f" {html.escape(badge_cls)}" if badge_cls else "")
    return (
        '<div class="case-card expanded">'
        '<div class="case-card-header">'
        '<div class="case-title">'
        f'<span class="{badge_class}">{val}</span>'
        f'<div><h3>{html.escape(c["bench"])} · {name}</h3>'
        f'<div class="case-task">Source: {src}</div></div></div></div>'
        '<div class="case-card-body">'
        f'<div class="case-desc">{desc}</div>'
        f'<div class="trajectory-flow">{steps_html}</div>'
        f'<div class="traj-formula"><code>{formula}</code></div>'
        '</div></div>'
    )


# ---------- step 3: CSS to embed in each page (rubric pages are standalone) ----------

CASE_CSS = """
<style>
/* Auto-injected: case study cards */
.case-cards { display: flex; flex-direction: column; gap: 1rem; margin-top: 1rem; }
.case-card {
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 1rem 1.25rem;
    box-shadow: 0 1px 3px rgba(0,0,0,0.04);
}
.case-card-header { display: flex; align-items: flex-start; gap: 1rem; margin-bottom: 0.75rem; }
.case-title { display: flex; gap: 1rem; align-items: flex-start; flex: 1; }
.case-title h3 { font-size: 1rem; font-weight: 600; color: var(--navy); margin: 0; }
.case-task { font-size: 0.8rem; color: var(--text-muted); margin-top: 0.2rem; font-family: 'JetBrains Mono', monospace; }
.metric-value-badge {
    display: inline-flex; align-items: center; justify-content: center;
    min-width: 48px; height: 32px; padding: 0 0.6rem; border-radius: 8px;
    font-weight: 700; font-size: 0.82rem;
    font-family: 'JetBrains Mono', monospace;
    background: rgba(37,99,235,0.10); color: var(--accent); flex-shrink: 0;
}
.metric-value-badge.badge-good { background: rgba(5,150,105,0.12); color: var(--green); }
.metric-value-badge.badge-bad  { background: rgba(220,38,38,0.12); color: #dc2626; }
.metric-value-badge.badge-warn { background: rgba(217,119,6,0.12);  color: var(--gold); }
.case-desc { font-size: 0.9rem; color: var(--text); line-height: 1.7; margin-bottom: 0.5rem; }
.trajectory-flow {
    display: flex; flex-wrap: wrap; gap: 0.5rem; align-items: center;
    margin: 0.75rem 0;
}
.traj-step {
    padding: 0.3rem 0.7rem; border-radius: 6px;
    font-size: 0.76rem; font-family: 'JetBrains Mono', monospace;
    font-weight: 500;
    background: rgba(99,102,241,0.10); color: #4f46e5;
}
.traj-think   { background: rgba(124,58,237,0.10);  color: #7c3aed; }
.traj-action  { background: rgba(99,102,241,0.10);  color: #4f46e5; }
.traj-error   { background: rgba(220,38,38,0.10);   color: #dc2626; }
.traj-success { background: rgba(5,150,105,0.10);   color: var(--green); }
.traj-loop    { background: rgba(220,38,38,0.08);   color: #dc2626; border: 1px dashed #dc2626; }
.traj-arrow   { color: var(--text-muted); font-size: 0.8rem; }
.traj-formula {
    margin-top: 0.6rem; padding: 0.55rem 0.9rem;
    background: var(--bg); border-radius: 6px;
    border-left: 3px solid var(--accent); font-size: 0.82rem;
}
.traj-formula code {
    font-family: 'JetBrains Mono', monospace;
    background: none; padding: 0; color: var(--text); font-size: 0.82rem;
}
.no-cases-note {
    padding: 1rem 1.25rem; border: 1px dashed var(--border);
    border-radius: 8px; color: var(--text-muted); font-size: 0.9rem;
    background: var(--bg);
}
</style>
"""


# ---------- step 4: build the section, inject into a page ----------

REAL_PICKS_DIR = os.path.join(HERE, "_real_picks")


def load_real_picks(metric_id: str) -> list[dict]:
    """Load real-trajectory cards from `_real_picks/` for a metric.

    Filenames are like `M12B-WORST.json`, `M84-TOP.json`, etc. — single
    object per file. They were extracted from real workspace_backup/
    nodes (no synthesis). Returns [] if no files for this metric.
    """
    if not os.path.isdir(REAL_PICKS_DIR):
        return []
    out = []
    prefix = metric_id.upper() + "-"
    for fname in sorted(os.listdir(REAL_PICKS_DIR)):
        if not fname.endswith(".json") or fname.startswith("_"):
            continue
        if not fname.upper().startswith(prefix):
            continue
        try:
            with open(os.path.join(REAL_PICKS_DIR, fname)) as f:
                d = json.load(f)
        except Exception:
            continue
        if isinstance(d, list):
            out.extend(d)
        elif isinstance(d, dict):
            out.append(d)
    return out


def build_section(metric_id: str, cases: list[dict]) -> str:
    """Return the full HTML block (markers + heading + CSS + cards)."""
    if cases:
        # Order: Innovator → Agency → SWE → Claw → Aggregate; preserve original within bench
        cases = sorted(cases, key=lambda c: _bench_rank(c.get("bench", "")))
        cards = "\n".join(render_case(c) for c in cases)
        body = f'<div class="case-cards">\n{cards}\n</div>'
        sub = (
            f"Curated trajectory examples across 4 harnesses showing how "
            f"{metric_id} behaves on real runs."
        )
    else:
        body = (
            '<div class="no-cases-note">No curated trajectory cases for this '
            'metric yet — see the index page for aggregate statistics.</div>'
        )
        sub = ""
    sub_html = f'<p>{html.escape(sub)}</p>\n' if sub else ""
    return (
        f"\n        {MARK_BEGIN}\n"
        f"        {CASE_CSS.strip()}\n"
        f"        <h2>Case Studies</h2>\n"
        f"        {sub_html}        {body}\n"
        f"        {MARK_END}\n"
    )


def slug_to_id(filename: str) -> str:
    # m74_action_entropy.html -> M74; m12b_resource_reclaim_rate.html -> M12B
    base = filename.split("_", 1)[0]
    return base.upper()


def inject(path: str, section: str) -> str:
    with open(path, encoding="utf-8") as f:
        text = f.read()

    # 1. Strip any previously-injected block (idempotency).
    #    Match the leading newline + indent, the block, and exactly one
    #    trailing newline. Don't gobble the indent of the next line — that's
    #    what made earlier versions accumulate blanks.
    pat = re.compile(
        r"\n[ \t]*"
        + re.escape(MARK_BEGIN)
        + r".*?"
        + re.escape(MARK_END)
        + r"\n",
        flags=re.DOTALL,
    )
    text = pat.sub("\n", text)

    # 2. Insert immediately BEFORE the <h2>Source</h2> heading so the page's
    #    final section stays the source pointer. The section already begins
    #    with "\n        " and ends with MARK_END + "\n"; we add nothing else
    #    so re-running is byte-stable.
    src_marker = "        <h2>Source</h2>"
    if src_marker not in text:
        # fall back to before </main>
        text = text.replace("</main>", section + "    </main>")
    else:
        text = text.replace(src_marker, section.lstrip("\n") + src_marker, 1)
    return text


def main() -> None:
    examples = load_traj_examples()
    by_id: dict[str, list[dict]] = {}
    for e in examples:
        by_id.setdefault(e["id"], []).append(e)

    written = []
    real = []
    bare = []
    for fname in sorted(os.listdir(RUBRICS)):
        if not fname.startswith("m") or not fname.endswith(".html"):
            continue
        mid = slug_to_id(fname)
        path = os.path.join(RUBRICS, fname)
        # Real picks (extracted from real workspace_backup nodes) ALWAYS win over
        # trajExamples — they describe a single concrete trajectory each, with
        # real step numbers, paths, session_ids, error messages.
        picks = load_real_picks(mid)
        if picks:
            cases = picks
            real.append((mid, len(picks), fname))
        else:
            cases = list(by_id.get(mid, []))
            if cases:
                written.append((mid, len(cases), fname))
            else:
                bare.append((mid, fname))
        section = build_section(mid, cases)
        with open(path, encoding="utf-8") as f:
            current = f.read()
        new = inject(path, section)
        if new != current:
            with open(path, "w", encoding="utf-8") as f:
                f.write(new)

    total = len(written) + len(real) + len(bare)
    print(f"Patched {total} M rubric pages.")
    print(f"  with curated trajExamples : {len(written)}")
    for mid, n, fn in written:
        print(f"    {mid:>5}  {n} case(s)  {fn}")
    print(f"  real picks (from nodes)   : {len(real)}")
    for mid, n, fn in real:
        print(f"    {mid:>5}  {n} case(s)  {fn}")
    if bare:
        print(f"  no data at all (stub)     : {len(bare)}")
        for mid, fn in bare:
            print(f"    {mid:>5}  {fn}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""build_judge_reasons.py — static page surfacing every preserved judge reason.

Two corpora (2026-07-10):
  1. GLM-5.2 verifier (gen-4 line): 190 deliverable judgements with reason
     (m_v2/verifier/scores_full_sample.jsonl + scores_swe_difficult.jsonl)
  2. gen-2 J-judge full rollout (claude-4.7-opus): 3,930 metric judgements
     with reason (rubrics/full_rollout_results.json)

Output: judge_reasons.html (self-contained, client-side filters).
"""
import html
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
FG = HERE.parent
M_V2 = FG / "new_start_61" / "m_v2"

ver = {}
for name in ("scores_full_sample.jsonl", "scores_swe_difficult.jsonl"):
    p = M_V2 / "verifier" / name
    if not p.exists():
        continue
    for line in p.read_text().splitlines():
        if line.strip():
            r = json.loads(line)
            ver[r["sample_name"]] = r
ver_rows = list(ver.values())

jd = json.loads((FG / "rubrics" / "full_rollout_results.json").read_text())
jd = [r for r in jd if r.get("reason")]

esc = html.escape


def ver_row(r):
    ok = r.get("resolved")
    badge = ("✓" if ok else "✗") if ok is not None else "?"
    cls = "ok" if ok else "bad"
    return (f'<tr><td class="mono">{esc(str(r.get("sample_name","")))[:70]}</td>'
            f'<td class="{cls}">{badge}</td><td>{esc(str(r.get("score","")))}</td>'
            f'<td>{esc(str(r.get("confidence","")))}</td>'
            f'<td class="reason">{esc(str(r.get("reason","")))}</td></tr>')


def jj_row(r):
    return (f'<tr data-m="{esc(str(r.get("metric_id","")))}" data-mod="{esc(str(r.get("model_family","")))}">'
            f'<td class="mono">{esc(str(r.get("metric_id","")))}</td>'
            f'<td>{esc(str(r.get("model_family","")))}</td>'
            f'<td>task{esc(str(r.get("task_id","")))}</td>'
            f'<td>{esc(str(r.get("score_raw", r.get("score",""))))}</td>'
            f'<td class="reason">{esc(str(r.get("reason","")))}</td></tr>')


metrics = sorted({r.get("metric_id", "") for r in jd})
models = sorted({r.get("model_family", "") for r in jd})

page = f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Judge Reasons — 判决理由全集</title>
<style>
body{{font-family:-apple-system,'Segoe UI',sans-serif;margin:0;background:#0f1115;color:#dde1e8}}
.wrap{{max-width:1200px;margin:0 auto;padding:24px 16px}}
h1{{font-size:22px}} h2{{font-size:17px;margin-top:36px;border-bottom:1px solid #2a2f3a;padding-bottom:6px}}
.note{{background:#1a1f2b;border-left:3px solid #e0b84d;padding:10px 14px;font-size:13px;line-height:1.6;border-radius:4px}}
table{{width:100%;border-collapse:collapse;font-size:12.5px;margin-top:12px}}
th,td{{padding:6px 8px;border-bottom:1px solid #232833;text-align:left;vertical-align:top}}
th{{position:sticky;top:0;background:#151923;font-weight:600}}
.mono{{font-family:ui-monospace,monospace;font-size:11.5px;color:#9aa4b5}}
.reason{{line-height:1.55;color:#c6cdd8}}
.ok{{color:#4cc38a;font-weight:700}} .bad{{color:#e5534b;font-weight:700}}
select,input{{background:#151923;color:#dde1e8;border:1px solid #2a2f3a;border-radius:4px;padding:6px 8px;font-size:13px;margin-right:8px}}
.tools{{margin:14px 0;position:sticky;top:0;background:#0f1115;padding:8px 0;z-index:5}}
a{{color:#e0b84d}}
@media(prefers-color-scheme:light){{body{{background:#fafbfc;color:#1c2330}}
 .note{{background:#fff7e0;color:#5a4a12}} th{{background:#eef1f6}} td,th{{border-color:#e2e6ee}}
 .mono{{color:#5b6575}} .reason{{color:#33404f}} select,input{{background:#fff;color:#1c2330;border-color:#cfd6e2}}
 .tools{{background:#fafbfc}}}}
</style></head><body><div class="wrap">
<h1>Judge Reasons 判决理由全集</h1>
<p class="note">本页汇集项目留存的全部 LLM-judge 判决理由原文。第 1 节是现役第 4 代管线的
GLM-5.2 deliverable verifier（2026-07-06/07，{len(ver_rows)} 条，Trajectory Lens 的 run
详情里也可见）；第 2 节是第 2 代 J-judge 体系（claude-4.7-opus，2026-05/06，
{len(jd)} 条判分理由，体系已被 m_v2 规则指标取代，理由文本作为历史证据保留）。
原始 thinking 轨迹各代均未存储，本页为 judge 输出的结构化 reason 字段。
<a href="index.html">← Home</a> · <a href="trajectories/">Trajectory Lens</a></p>

<h2>1. GLM-5.2 Verifier（第4代，deliverable 判决，n={len(ver_rows)}）</h2>
<table><thead><tr><th>sample</th><th>resolved</th><th>score</th><th>conf</th><th>reason</th></tr></thead>
<tbody>{''.join(ver_row(r) for r in ver_rows)}</tbody></table>

<h2>2. J-judge 全量（第2代，claude-4.7-opus，n={len(jd)}）</h2>
<div class="tools">
<select id="fm"><option value="">全部指标</option>{''.join(f'<option>{esc(m)}</option>' for m in metrics)}</select>
<select id="fd"><option value="">全部模型</option>{''.join(f'<option>{esc(m)}</option>' for m in models)}</select>
<input id="fq" placeholder="搜索理由文本…" size="30">
<span id="fc"></span>
</div>
<table><thead><tr><th>metric</th><th>model</th><th>task</th><th>score</th><th>reason</th></tr></thead>
<tbody id="jj">{''.join(jj_row(r) for r in jd)}</tbody></table>
<script>
const fm=document.getElementById('fm'),fd=document.getElementById('fd'),fq=document.getElementById('fq'),
 rows=[...document.querySelectorAll('#jj tr')],fc=document.getElementById('fc');
function apply(){{const m=fm.value,d=fd.value,q=fq.value.toLowerCase();let n=0;
 for(const r of rows){{const show=(!m||r.dataset.m===m)&&(!d||r.dataset.mod===d)&&(!q||r.textContent.toLowerCase().includes(q));
  r.style.display=show?'':'none'; if(show)n++;}} fc.textContent=n+' / '+rows.length;}}
fm.onchange=fd.onchange=apply; fq.oninput=apply; apply();
</script>
</div></body></html>"""

out = HERE / "judge_reasons.html"
out.write_text(page, encoding="utf-8")
print(f"wrote {out} ({out.stat().st_size/1e6:.2f} MB): verifier={len(ver_rows)}, jjudge={len(jd)}")

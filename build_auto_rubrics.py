#!/usr/bin/env python3
"""Generate rubric pages for the 18 url='#' metrics that have real computed data.

Source of truth: index.html metric data array (formula / scoring / detail strings)
plus auditor-confirmed source files. Output style matches m74_action_entropy.html.
"""
from __future__ import annotations
import html
import os

OUT_DIR = os.path.join(os.path.dirname(__file__), "rubrics")
TEMPLATE_SOURCE = os.path.join(OUT_DIR, "m74_action_entropy.html")


def _slice_template():
    with open(TEMPLATE_SOURCE, encoding="utf-8") as f:
        s = f.read()
    open_tag = '<main class="content">'
    close_tag = '</main>'
    i = s.index(open_tag) + len(open_tag)
    j = s.index(close_tag, i)
    return s[:i], s[j:]


PREFIX, SUFFIX = _slice_template()


METRICS = [
    {
        "id": "M29", "slug": "m29_parameter_schema_compliance",
        "en": "Parameter Schema Compliance", "zh": "参数 Schema 合规率",
        "method": "Auto / Rule",
        "intuition": (
            "Fraction of tool calls whose argument object validates against a per-action_type schema. "
            "Catches malformed arguments (wrong key spelling, missing required field, type mismatch) "
            "before they hit the tool implementation."
        ),
        "value_range": "0-1 ratio",
        "direction": "Higher is better. 1.0 = full compliance; <0.9 = frequent schema violations.",
        "formula": "M29_compliance = count(args ⊨ schema_for(action_type)) / count(tool_calls)",
        "inputs": "<code>response.tool_calls[].name</code>, <code>response.tool_calls[].arguments</code>, plus a per-action_type JSON schema map.",
        "procedure": [
            "For each react node, iterate response.tool_calls.",
            "Look up the schema for tool_call.name (declared in the action_type registry).",
            "Validate arguments against the schema (jsonschema.validate or equivalent).",
            "Increment compliant_count if validation passes; total_count regardless.",
            "Trajectory metric = compliant_count / total_count.",
        ],
        "worked": (
            "Across 661 InnovatorBench trajectories: <code>n=637, mean=0.997, std=0.035</code>. ρ=0.059, "
            "Kruskal H=41.4, rating=D. Compliance is near-saturated (most modern tool-calling models emit "
            "schema-correct args ≥99% of the time), so this metric has weak discrimination on this benchmark."
        ),
        "edge_cases": [
            "Trajectories with 0 tool calls ⇒ rate is None (excluded from the mean).",
            "Schema is action_type-specific; an action without a registered schema is excluded from the denominator (not counted as failure).",
            "Near-saturation on capable models — consider stratifying by model family or pairing with M28.",
        ],
        "outputs": ["<code>M29_parameter_schema_compliance</code>"],
        "source": "compute_metrics.py (per-action schema validation loop). Numeric data comes from metrics_results_424.csv / .json (the M29 column, embedded into the index.html detail string).",
    },
    {
        "id": "M33", "slug": "m33_scaling_bottleneck",
        "en": "Scaling Bottleneck", "zh": "性能衰减拐点",
        "method": "Auto / Rule",
        "intuition": (
            "The first cliff in the score-vs-step curve. Bin trajectories by step_count, compute mean score per bin, "
            "then take the largest negative first-difference between adjacent bins. Identifies the step budget at "
            "which adding more reasoning stops helping (or starts hurting)."
        ),
        "value_range": "step count (≥0)",
        "direction": "Higher = agent uses more steps productively; very early bottleneck (<50) = collapses on long-horizon tasks.",
        "formula": (
            "bins = quantile_bins(trajectories.step_count, k=5)\n"
            "curve = [mean(score | bin=b) for b in bins]\n"
            "Δ = first-differences of curve\n"
            "M33_scaling_bottleneck = step_count of bin where Δ is most negative"
        ),
        "inputs": "<code>step_count</code> per trajectory, <code>overall_score</code> per trajectory.",
        "procedure": [
            "Group all trajectories into 5 step-count quantile bins.",
            "Compute mean overall_score per bin → 5-point curve.",
            "First-difference the curve; the bin with the largest negative drop is the bottleneck.",
            "Report the bin's step count as M33; also expose the score before/after the cliff.",
            "Spearman ρ between step_count and score is exposed alongside as a robustness check.",
        ],
        "worked": (
            "Across 655 trajectories the score curve drops from <code>15.16 → 12.08</code> at the bin-4 boundary "
            "(<code>step ≈ 128.6</code>). Spearman ρ(step, score)=0.238, p=6.79e-10 — more steps still helps overall, "
            "but the marginal value collapses around bin 4."
        ),
        "edge_cases": [
            "Very-short-trajectory regime: bin 0 may dominate if too many trajectories abort early; consider min-bin floor.",
            "If the curve is monotonically increasing, M33 = max(step_count) (no bottleneck).",
            "Bin boundaries depend on the trajectory population — not directly comparable across benchmarks.",
        ],
        "outputs": ["<code>M33_scaling_bottleneck</code> (step count, int)", "<code>M33_score_before</code>, <code>M33_score_after</code> (mean scores around the cliff)"],
        "source": "compute_metrics.py (score-vs-step curve + first-difference). Numeric values come from the 661-trajectory aggregate exposed in metrics_results_424.csv.",
    },
    {
        "id": "M56", "slug": "m56_bug_reproduction_rate",
        "en": "Bug Reproduction Rate", "zh": "Bug 复现率",
        "method": "Auto / Rule",
        "intuition": (
            "Fraction of trajectories that ran a reproduction command (run_command / eval) BEFORE issuing their first "
            "edit. Test-driven debugging baseline — high rate = agent reproduces the failure first; low rate = blind editing. "
            "InnovatorBench tasks are not all bug-fix shaped, so this is an ADAPTED proxy, not the SWE-bench original."
        ),
        "value_range": "0-1 ratio",
        "direction": "Higher = test-driven; lower = edit-first / hope-it-works.",
        "formula": "M56_bug_reproduction_rate = 1[any (run_command|eval) action precedes the first edit_file action]",
        "inputs": "<code>action.action_type</code> sequence per trajectory.",
        "procedure": [
            "Walk react nodes; record indices of run_command, eval, and edit_file events.",
            "If first_edit_index exists AND any run/eval precedes it ⇒ trajectory contributes 1, else 0.",
            "Trajectories with 0 edits ⇒ excluded (None).",
            "Aggregate across trajectories as a mean.",
        ],
        "worked": (
            "Across 661 InnovatorBench trajectories: <code>n=502, mean=0.8884, std=0.3151</code>. ρ=0.206 with score, "
            "Kruskal H=53.5 — moderate discrimination. The 11% who do NOT reproduce-then-edit are heavily over-represented "
            "in low-scoring runs."
        ),
        "edge_cases": [
            "Trajectories with no edit_file action ⇒ M56 is undefined; excluded from the mean.",
            "Pure data-eng / non-debug tasks (e.g. dataset cleaning) inflate the rate trivially — a run_command always precedes the edit.",
            "Does not check that the run actually <em>reproduced</em> the failure — only that it was attempted.",
        ],
        "outputs": ["<code>M56_bug_reproduction_rate</code>"],
        "source": "compute_metrics.py / compute_metrics_swe.py (proxy: run before first edit). Numeric data embedded into index.html detail string from metrics_results_424.csv.",
    },
    {
        "id": "M58", "slug": "m58_edit_rollback_rate",
        "en": "Edit Rollback Rate", "zh": "编辑回滚率",
        "method": "Auto / Rule (semi)",
        "intuition": (
            "Fraction of edits that re-touch the same file path within a 5-action window. Catches agents who write, then "
            "immediately re-edit the same location — a proxy for thrash / contradicting-self / blind retry on same target. "
            "Diff-tracking would refine to literal restore-of-prior-content; the 5-window proxy is what's actually shipped."
        ),
        "value_range": "0-1 ratio",
        "direction": "Lower is better. <0.1 = monotonic editing; >0.3 = repeatedly rewriting same files.",
        "formula": "M58_edit_rollback_rate = count(edit_file with same path as a prior edit_file within last 5 actions) / total_edits",
        "inputs": "<code>action.action_type == 'edit_file'</code> events with their <code>arguments.path</code>.",
        "procedure": [
            "Walk all edit_file events in trajectory order.",
            "For each, check whether the same path appeared in any of the previous 5 actions.",
            "If yes, increment rollback_count; total_count always increments.",
            "Trajectory metric = rollback_count / total_count; None when total_count == 0.",
        ],
        "worked": (
            "Across 661 InnovatorBench trajectories: <code>n=502, mean=0.3561, std=0.2598</code>. ρ=−0.029 with score (weak), "
            "but Kruskal H=94.9 — strong cross-model discrimination even though within-model rollback rate is only weakly tied "
            "to outcome."
        ),
        "edge_cases": [
            "Trajectories with <2 edits ⇒ excluded (None).",
            "5-action window is heuristic; widening it would inflate the count for slow trajectories.",
            "Does not distinguish 'rewrite same line' from 'edit a different region of the same file' — current proxy treats both as rollback.",
        ],
        "outputs": ["<code>M58_edit_rollback_rate</code>"],
        "source": "compute_metrics.py (path-history scan with 5-action window). Numeric data from metrics_results_424.csv embedded in the index.html detail string.",
    },
    {
        "id": "M62", "slug": "m62_passive_trigger_ratio",
        "en": "Passive Trigger Ratio", "zh": "被动触发比例",
        "method": "Auto / Rule",
        "intuition": (
            "Of all human-intervention events, what fraction were triggered REACTIVELY by an agent error message vs "
            "PROACTIVELY by the agent asking for help? Captures a form of self-awareness — high passive ratio = "
            "agent only escalates when it fails outright; low = agent verifies-by-asking before failing. "
            "InnovatorBench has no human-in-loop, so this metric resolves to N/A on the current dataset."
        ),
        "value_range": "0-1 ratio (or N/A when no human nodes)",
        "direction": "Lower = proactive; higher = error-only escalation.",
        "formula": "M62_passive_trigger_ratio = count(human node within 1 step of an agent error) / count(all human nodes)",
        "inputs": "Trajectory must contain human-intervention nodes (currently: none on InnovatorBench).",
        "procedure": [
            "Detect human-intervention nodes (special node_type or sender field).",
            "For each, check the previous react step's observation.success — False = passive trigger.",
            "Aggregate as count_passive / count_human.",
            "Returns None when count_human == 0 (the InnovatorBench case).",
        ],
        "worked": (
            "On InnovatorBench: <code>0 human-style nodes detected total across 661 trajectories</code>. M62 is "
            "categorically N/A; preserved for cross-benchmark comparability with frameworks that do support "
            "human-in-loop."
        ),
        "edge_cases": [
            "InnovatorBench: no human nodes ⇒ value is null and excluded from aggregation.",
            "Even on benchmarks with human nodes, the 1-step proximity window is heuristic.",
        ],
        "outputs": ["<code>M62_passive_trigger_ratio</code> (None on InnovatorBench)"],
        "source": "compute_metrics.py (human-node detection). Confirmed N/A on InnovatorBench in metrics_results_424.csv.",
    },
    {
        "id": "M75", "slug": "m75_cross_model_efficiency",
        "en": "Cross-Model Same-Task Efficiency", "zh": "跨模型同任务效率差",
        "method": "Auto / Rule (cross-trajectory)",
        "intuition": (
            "For each task, take the standard deviation of step_count across models that attempted it. Average across tasks. "
            "Reveals which tasks separate strong models from weak ones by sheer step-economy — vs tasks where every model "
            "ends up using similar effort regardless of skill."
        ),
        "value_range": "≥0 (steps)",
        "direction": "Higher = stronger models save substantially more steps on these tasks; lower = step count is task-dictated.",
        "formula": (
            "for each task t with ≥3 models:\n"
            "    step_std_t = std([mean_steps(model=m, task=t) for m in models])\n"
            "M75 = mean(step_std_t)"
        ),
        "inputs": "trajectory-level <code>step_count</code> grouped by (model, task_id).",
        "procedure": [
            "Group trajectories by task_id; require ≥3 distinct models per task.",
            "Compute per-model mean step_count for each task.",
            "Take the std across models within each task.",
            "M75 = mean of those per-task stds; companion fields list top-discriminating and most-convergent task ids.",
        ],
        "worked": (
            "Across 20 tasks (each with ≥3 models): <code>mean step_std = 104.91, sd of step_std = 67.60</code>. "
            "Top discriminating tasks (largest cross-model step variance): <code>[13, 15, 2, 10, 18]</code>. "
            "Most convergent: <code>[5, 12, 7, 20, 9]</code>. Spearman(step_std, score_std)=−0.271 — step variance "
            "and score variance are weakly anti-correlated."
        ),
        "edge_cases": [
            "Tasks with <3 models are dropped from the average.",
            "Sensitive to step-count outliers — consider trimmed std for noisy benchmarks.",
            "Cross-benchmark comparison only meaningful when the same task set is evaluated on the same models.",
        ],
        "outputs": [
            "<code>M75_step_std_mean</code>", "<code>M75_top_discriminating_tasks</code>", "<code>M75_most_convergent_tasks</code>",
        ],
        "source": "compute_metrics.py (cross-model step_std aggregation). Data embedded in index.html detail string from the 661-trajectory dataset.",
    },
    {
        "id": "M78", "slug": "m78_token_controlled_success",
        "en": "Token-Controlled Success", "zh": "Token 控制成功率",
        "method": "Auto / Statistical (GLM)",
        "intuition": (
            "Generalized linear model that controls for log(total_tokens) and per-task fixed effects, exposing each model's "
            "true contribution to the score after stripping out 'spent more tokens, scored higher' confounding. The std of "
            "the model fixed effects measures the residual differentiation."
        ),
        "value_range": "model-coefficient std (≥0); per-model β can be ±",
        "direction": "Std=0 ⇒ token spend explains all model differences; std>>0 ⇒ models differ even at equal token budget.",
        "formula": "score ~ C(model) + log(total_tokens) + C(task_id)\nM78_diff = std(β_model)\nM78_token_coef = β_log_tokens",
        "inputs": "<code>overall_score</code>, <code>total_tokens</code>, <code>task_id</code>, <code>model</code> per trajectory.",
        "procedure": [
            "Fit OLS / GLM: score ~ C(model) + log(total_tokens+1) + C(task_id) on all trajectories.",
            "Extract β_model coefficients (one per model, omitted-baseline contrast).",
            "M78_diff = std of those β_model values (the 'true differentiation' after controlling tokens).",
            "M78_token_coef = β on log(tokens), reported separately as the size of the token-spend channel.",
        ],
        "worked": (
            "Fit on 655 trajectories: R²=0.397, F=7.3. <code>M78_diff (std of model β) = 7.630</code>; "
            "<code>β_log_tokens = +4.085</code> (more tokens helps). Top-3 model β: kimi-k2.5(+19.50), glm47(+8.31), "
            "glm47_data_w_codeact_…(+3.60). Bottom-3: grok-4(−9.19), grok-code-fast-1(−9.x), kimi-k2-instruct-…(−x.x)."
        ),
        "edge_cases": [
            "Requires ≥2 trajectories per (model, task) cell for stable estimates; very sparse models inflate variance.",
            "Multicollinearity if model and tokens are nearly co-linear (e.g. one model always uses ~same token count).",
            "log(tokens+1) is the regressor — raw tokens distort by skewness.",
        ],
        "outputs": ["<code>M78_diff</code>", "<code>M78_token_coef</code>", "<code>M78_per_model_beta</code>"],
        "source": "compute_metrics.py / analyze_discrimination.py (statsmodels OLS fit). Coefficients embedded in index.html detail string.",
    },
    {
        "id": "M79", "slug": "m79_step_controlled_success",
        "en": "Step-Controlled Success", "zh": "步数控制成功率",
        "method": "Auto / Statistical (GLM)",
        "intuition": (
            "Same family as M78 but controls for tool_chain_depth (a step-budget proxy) plus task fixed effects. "
            "Reveals model-quality differences that survive equalizing trajectory length."
        ),
        "value_range": "model-coefficient std (≥0)",
        "direction": "High std = strong residual model differentiation; near 0 = step budget explains the gap.",
        "formula": "score ~ C(model) + tool_chain_depth + C(task_id)\nM79_diff = std(β_model)",
        "inputs": "<code>overall_score</code>, <code>tool_chain_depth</code>, <code>task_id</code>, <code>model</code>.",
        "procedure": [
            "Fit OLS: score ~ C(model) + tool_chain_depth + C(task_id) on all trajectories.",
            "Take std of β_model coefficients as the M79 differentiation score.",
            "Report β_tool_chain_depth as the size of the step-budget channel.",
        ],
        "worked": (
            "Fit on 655 trajectories: R²=0.374, F=6.6. <code>M79_diff = 9.236</code>; "
            "<code>β_tool_chain_depth = +0.011</code>. Top-3: kimi-k2.5(+20.15), glm47(+8.95), "
            "glm47_data_w_codeact(+3.35). Bottom-3: grok-4(−13.26), grok-code-fast-1(−13.x), …"
        ),
        "edge_cases": [
            "tool_chain_depth is a noisy proxy for step count — replace with raw step_count for benchmarks where the difference matters.",
            "Same multicollinearity warning as M78.",
        ],
        "outputs": ["<code>M79_diff</code>", "<code>M79_step_coef</code>", "<code>M79_per_model_beta</code>"],
        "source": "compute_metrics.py / analyze_discrimination.py (statsmodels OLS fit).",
    },
    {
        "id": "M80", "slug": "m80_reasoning_length_controlled",
        "en": "Reasoning-Length Controlled", "zh": "推理长度控制评分",
        "method": "Auto / Statistical (GLM)",
        "intuition": (
            "GLM controlling for reasoning-channel length (and total output tokens), revealing whether a model's score "
            "is driven by how MUCH it thinks vs by inherent quality. Only models that emit a reasoning channel are well-modeled; "
            "the others contribute via their output_tokens proxy."
        ),
        "value_range": "model-coefficient std (≥0)",
        "direction": "Higher = quality differences survive; near 0 = score is reasoning-volume-driven.",
        "formula": "M24 ~ C(model) + log(output_tokens+1) + C(task_id)\nM80_diff = std(β_model)\nM80_reasoning_coef = β on log(reasoning_len) (when present)",
        "inputs": "<code>M24</code> (token-per-point score), <code>output_tokens</code>, <code>task_id</code>, <code>model</code>; reasoning length when available.",
        "procedure": [
            "Fit OLS: M24 ~ C(model) + log(output_tokens+1) + C(task_id) on the n=655 set.",
            "Extract β_model std as M80_diff (controlled quality measure).",
            "Report β_log_reasoning_len for the subset that exposes a reasoning channel.",
        ],
        "worked": (
            "<code>n=655, R²=0.379, F=6.80</code>. <code>M80_diff = 10.195</code>; <code>β_log_reasoning_len = 3.109</code> "
            "(longer reasoning → higher M24 score on the reasoning-equipped subset)."
        ),
        "edge_cases": [
            "Reasoning length is only defined for models with response.reasoning ≠ ''; for the others the coefficient is implicit zero.",
            "Output tokens act as a second-order proxy when reasoning length is missing — the controlled-score interpretation weakens.",
        ],
        "outputs": ["<code>M80_diff</code>", "<code>M80_reasoning_coef</code>", "<code>M80_per_model_beta</code>"],
        "source": "compute_metrics.py / analyze_discrimination.py (statsmodels OLS fit).",
    },
    {
        "id": "M84", "slug": "m84_verbosity_normalized_score",
        "en": "Verbosity-Normalized Score", "zh": "冗长归一化评分",
        "method": "Auto / Rule",
        "intuition": (
            "Per-trajectory normalization that divides M24 (token-per-point score) by log(total_tokens+1). "
            "Penalizes long-trace low-score runs. Spearman with raw score is essentially 1 (strong rank-coupling), "
            "but the absolute level differs between verbose and concise models."
        ),
        "value_range": "≥0 (continuous)",
        "direction": "Higher = more score per unit log-token; lower = verbose-but-flat.",
        "formula": "M84_verbosity_normalized = M24 / log(total_tokens + 1)",
        "inputs": "<code>M24</code> (per-point score), <code>total_tokens</code>.",
        "procedure": [
            "Compute M24 per trajectory (separately).",
            "Divide by log(total_tokens + 1) — Laplace-smoothed log to avoid zero-token blow-ups.",
            "Aggregate as mean / std / Kruskal H across models.",
        ],
        "worked": (
            "Across 655 trajectories: <code>mean=0.7313, std=1.378</code>. Kruskal H=123.88 (p=1.09e-19) — the metric "
            "discriminates models strongly. Spearman vs raw score ρ=1.000 — same ranking but different absolute scale, "
            "which exposes verbosity as a level-shift between model families."
        ),
        "edge_cases": [
            "Trajectories with 0 tokens ⇒ denominator becomes log(1)=0; use additive smoothing already in the formula.",
            "Identical rank to raw M24 means it's NOT a separate ranking signal — interpret only as a level-shift visualisation.",
        ],
        "outputs": ["<code>M84_verbosity_normalized_score</code>"],
        "source": "compute_metrics.py (Laplace-smoothed log-normalization of M24).",
    },
    {
        "id": "M85", "slug": "m85_model_attribute_spearman",
        "en": "Sρ(m,a) — Model×Attribute Spearman", "zh": "模型×属性 Spearman",
        "method": "Auto / Statistical (meta)",
        "intuition": (
            "For each (model m, attribute a) pair, take the Spearman rank-correlation between bucket-wise attribute values "
            "and bucket-wise scores within that model's trajectories. |ρ| close to 1 = the attribute monotonically tracks "
            "score for THAT model. Diagnostic of which attributes drive each model's success/failure."
        ),
        "value_range": "[−1, 1] per (m,a) cell; aggregate stats across cells",
        "direction": "|ρ|>0.5 = strong monotonic effect for that model; sign tells direction.",
        "formula": "Sρ(m,a) = scipy.stats.spearmanr(bucket_mean(a, m, b), bucket_mean(score, m, b))_b",
        "inputs": "Per-trajectory attribute values for a, score, model id.",
        "procedure": [
            "For each (m, a): bucket the model's trajectories by quartile of attribute a (4 buckets).",
            "Compute mean attribute value and mean score per bucket.",
            "Spearman ρ across the 4 (attr_mean, score_mean) points.",
            "Aggregate over (m, a) pairs: |ρ| mean / max / fraction with |ρ|>0.5.",
        ],
        "worked": (
            "Over 380 (m,a) pairs: <code>mean|ρ|=0.223, max|ρ|=0.996, 8.7% exceed 0.5</code>. "
            "Strongest monotonic links: gpt-5 × M24_num_evals (ρ=+0.996), gpt-5 × M93_score_delta (ρ=+0.943), "
            "kimi-k2-instruct × M24_token_per_point (ρ=−0.927) — token efficiency is the single most sensitive attribute."
        ),
        "edge_cases": [
            "Quartile bucketing requires ≥4 distinct trajectories per model; sparser models drop out.",
            "ρ on 4 points is noisy — use it as ranking signal, not p-value.",
            "Pairs with constant attribute or score values are excluded (ρ undefined).",
        ],
        "outputs": ["<code>M85_per_pair_rho</code>", "<code>M85_mean_abs_rho</code>", "<code>M85_top_pairs</code>"],
        "source": "analyze_discrimination.py (per-(model,attribute) Spearman). Cross-pair aggregates embedded into index.html detail string.",
    },
    {
        "id": "M86", "slug": "m86_model_attribute_std",
        "en": "Sσ(m,a) — Model×Attribute Std", "zh": "模型×属性桶间标准差",
        "method": "Auto / Statistical (meta)",
        "intuition": (
            "Std of bucket-wise score for each (model m, attribute a) pair. High σ = the model's score swings widely across "
            "the attribute's quartiles (sensitive). Low σ = stable across the attribute."
        ),
        "value_range": "≥0 (score units)",
        "direction": "High = volatile; low = stable.",
        "formula": "Sσ(m,a) = std([bucket_mean_score(m, a, b) for b in 4 buckets])",
        "inputs": "Per-trajectory score, model, attribute value.",
        "procedure": [
            "For each (m, a): bucket trajectories by attribute a quartiles.",
            "Compute mean score per bucket → 4-vector.",
            "Sσ(m,a) = std of that 4-vector.",
            "Aggregate across pairs (mean, std, top/bottom-5 by σ).",
        ],
        "worked": (
            "Over 275 valid (m,a) pairs: <code>mean=15.996, std=9.988</code>. "
            "Most volatile: kimi-k2.5 × M07_read_before_edit_rate (Sσ=40.56). "
            "Most stable: kimi-k2-instruct-0905-gzy × M02_tool_chain_depth (Sσ=0.000)."
        ),
        "edge_cases": [
            "Pairs with <2 non-empty buckets are dropped.",
            "σ is a level-statistic — pair with M85 (Spearman) for direction.",
        ],
        "outputs": ["<code>M86_per_pair_sigma</code>", "<code>M86_top_volatile</code>", "<code>M86_most_stable</code>"],
        "source": "analyze_discrimination.py (cross-bucket score std).",
    },
    {
        "id": "M87", "slug": "m87_attribute_universal_bias",
        "en": "ζ(a) — Task-Independent Bias", "zh": "属性普遍偏差",
        "method": "Auto / Statistical (meta)",
        "intuition": (
            "ζ(a) = mean over models of Sρ(m,a). Captures attribute a's UNIVERSAL effect — does it monotonically "
            "drive score across all models, or only some? |ζ| close to 1 = everyone responds to a in the same direction."
        ),
        "value_range": "[−1, 1]",
        "direction": "|ζ|>0.5 = attribute matters for ≈all models; ≈0 = effect is model-specific.",
        "formula": "ζ(a) = mean_m( Sρ(m,a) )    -- using signed ρ, not |ρ|",
        "inputs": "M85 per-pair ρ table.",
        "procedure": [
            "Compute Sρ(m,a) per (m,a) pair (M85).",
            "Average over models for each attribute a.",
            "Rank attributes by |ζ|; report top-5 with sign.",
        ],
        "worked": (
            "Top-5 attributes by |ζ|: <code>M24_token_per_point (ζ=−0.798)</code>, M93_retry_improved (+0.579), "
            "M24_num_evals (+0.414), M93_score_delta (+0.378), M43_max_consecutive_sleep (+0.235). "
            "Token-efficiency dominates universally — every model that wastes tokens loses score."
        ),
        "edge_cases": [
            "Attributes with <3 contributing models excluded (ζ unstable).",
            "Sign matters — ζ=−0.8 means HIGH attribute correlates with LOW score for all models.",
        ],
        "outputs": ["<code>M87_per_attr_zeta</code>", "<code>M87_top_attributes</code>"],
        "source": "analyze_discrimination.py (cross-model averaging of M85 cells).",
    },
    {
        "id": "M88", "slug": "m88_attribute_dependent_variability",
        "en": "ρ(a) — Task-Dependent Variability", "zh": "属性敏感度差异",
        "method": "Auto / Statistical (meta)",
        "intuition": (
            "Std over models of Sρ(m,a). Attributes with high ρ(a) are the ones where models DISAGREE about whether the "
            "attribute helps or hurts. Highlights model-specific levers vs universal ones."
        ),
        "value_range": "≥0",
        "direction": "High = different models react differently to the attribute; low = consistent reaction.",
        "formula": "ρ(a) = std_m( Sρ(m,a) )    -- using signed ρ",
        "inputs": "M85 per-pair ρ table.",
        "procedure": [
            "Compute Sρ(m,a) per (m,a) pair (M85).",
            "Take std across models for each attribute a.",
            "Rank attributes by descending ρ(a).",
        ],
        "worked": (
            "Top-5 attributes by ρ(a): <code>M93_score_delta (ρ=0.330)</code>, M12_resource_reclaim_rate (0.324), "
            "M53_code_locate_efficiency (0.268), M11_eval_abuse_rate (0.231), M24_num_evals (0.228). "
            "These are the attributes where model behavior diverges most — useful for stratified analysis."
        ),
        "edge_cases": [
            "Attributes with <3 models excluded.",
            "Pair with M87 — high ρ(a) and low |ζ(a)| = the attribute splits models into camps.",
        ],
        "outputs": ["<code>M88_per_attr_rho</code>", "<code>M88_top_attributes</code>"],
        "source": "analyze_discrimination.py (cross-model std of M85 cells).",
    },
    {
        "id": "M89", "slug": "m89_bucket_self_diagnosis",
        "en": "Bucket-wise Self-Diagnosis", "zh": "桶级自诊断",
        "method": "Auto / Statistical (meta)",
        "intuition": (
            "For each (model, attribute) pair, compute the score gap between the worst and best quartile bucket. "
            "Large positive gap (Q4 > Q1) AND monotonic curve = the attribute is a clean lever for that model — push it "
            "and the model improves."
        ),
        "value_range": "score units (≥0 for monotonic pairs)",
        "direction": "Larger gap = stronger lever; pair must be monotonic to be diagnostic.",
        "formula": "M89_gap(m,a) = bucket_mean(score | m, a@Q4) − bucket_mean(score | m, a@Q1)\nM89_monotonic = curve passes monotonicity check",
        "inputs": "Per-trajectory score, model, attribute value.",
        "procedure": [
            "Bucket trajectories per (m, a) into quartiles of a.",
            "Take mean score per bucket; check monotonicity (Q1 < Q2 < Q3 < Q4 or strictly reverse).",
            "Compute gap = Q4 − Q1; report pairs with gap > 0 AND monotonic curve.",
            "Aggregate: count of monotonic pairs / mean gap / top gaps.",
        ],
        "worked": (
            "<code>62 / 275</code> (m,a) pairs are monotonic. <code>mean gap = 15.90, std = 12.80</code>. "
            "Top-5 gaps: kimi-k2.5/M24_token_per_point gap=78.52; glm-4-5-full-data-gzy/M24_token_per_point gap=58.06; "
            "glm47/M24_token_per_point gap=54.81; glm-4-5-full-data-wo-interact-gzy/M24_token_per_point gap=… ; etc. "
            "Token-per-point dominates the diagnostic for every strong model."
        ),
        "edge_cases": [
            "Non-monotonic curves are dropped — they're not actionable levers (the relationship is not single-signed).",
            "Quartile bucketing requires ≥4 trajectories per (m, a); sparse pairs excluded.",
        ],
        "outputs": ["<code>M89_monotonic_pairs</code>", "<code>M89_gap_per_pair</code>", "<code>M89_top_gaps</code>"],
        "source": "analyze_discrimination.py (Q1-vs-Q4 monotonicity check + gap computation).",
    },
    {
        "id": "M90", "slug": "m90_significance_testing",
        "en": "Significance Testing Protocol", "zh": "显著性检验协议",
        "method": "Auto / Statistical (meta)",
        "intuition": (
            "Friedman χ² overall + pairwise Wilcoxon with Holm-Bonferroni correction for multi-model multi-task "
            "score comparison. Reports the corrected p-value matrix; flags which pairwise model comparisons survive "
            "multiple-comparisons control."
        ),
        "value_range": "p-values ∈ [0,1]",
        "direction": "p<0.05 (corrected) ⇒ statistically significant model difference.",
        "formula": (
            "Friedman: χ² = scipy.stats.friedmanchisquare(*model_scores_per_task)\n"
            "Pairwise: for each (m_i, m_j): Wilcoxon signed-rank on paired task scores\n"
            "Correction: Holm-Bonferroni over the (n_models choose 2) p-values"
        ),
        "inputs": "Per-(model, task) score matrix (one row per model, one column per task).",
        "procedure": [
            "Build the model×task score matrix.",
            "Run scipy.stats.friedmanchisquare across the matrix rows.",
            "For each pair of models, run scipy.stats.wilcoxon on their per-task score vectors.",
            "Apply Holm-Bonferroni step-down correction across all pairwise p-values.",
            "Report Friedman χ², the count of significant pairs, and top-5 most-significant pairs.",
        ],
        "worked": (
            "<code>Friedman χ²=72.523, p=6.715e-10</code> (overall significant). "
            "Pairwise Wilcoxon: <code>0 / 105</code> pairs survive Holm-Bonferroni at α=0.05 (the per-task variance is too "
            "high to separate any single pair confidently). Top-5 (raw_p=2.05e-1): claude-4-sonnet-gzy vs glm-4-5-gzy / "
            "vs grok-4 / vs grok-code-fast-1 / vs kimi-k2-instruct-… — all hit the same correction floor."
        ),
        "edge_cases": [
            "Friedman requires ≥3 models and complete task coverage; missing cells are dropped or imputed.",
            "Holm correction is conservative — alternative: Benjamini-Hochberg if FDR is preferred over FWER.",
            "Non-significant pairwise after correction is a frequent outcome when n_tasks is small.",
        ],
        "outputs": ["<code>M90_friedman_chi2</code>", "<code>M90_friedman_p</code>", "<code>M90_pairwise_corrected_p</code>"],
        "source": "analyze_discrimination.py (scipy.stats friedmanchisquare + wilcoxon + Holm correction).",
    },
    {
        "id": "M94", "slug": "m94_compile_vs_runtime_error",
        "en": "Compile vs Runtime Error Ratio", "zh": "编译-运行时错误比",
        "method": "Auto / Rule (semi)",
        "intuition": (
            "Laplace-smoothed ratio of compile-class failures to runtime-class failures observed in observation messages. "
            "High ratio = errors dominated by syntax / format issues; low = semantic / logic failures dominate. "
            "Categorisation needs an error classifier — currently regex/keyword based."
        ),
        "value_range": "≥0 (ratio); 1.0 = balanced",
        "direction": "Diagnostic, not directional. Pair with M41s/M41l for persistence.",
        "formula": "M94 = (compile_fails + 1) / (runtime_fails + 1)    -- Laplace-smoothed",
        "inputs": "<code>observation.success == False</code> events plus <code>observation.message</code>.",
        "procedure": [
            "Walk all react nodes; collect failures (success=False).",
            "Classify each failure message via regex/keyword: SyntaxError, IndentationError, parse error, malformed JSON, missing parenthesis ⇒ compile; everything else ⇒ runtime.",
            "Apply Laplace smoothing: (compile+1)/(runtime+1) to handle zero-error trajectories.",
            "Aggregate as mean / std / Kruskal H across models.",
        ],
        "worked": (
            "Across 655 trajectories: <code>mean=1.002, std=0.180</code> — compile and runtime errors are roughly "
            "balanced on average. ρ=0.064 (weak), Kruskal H=77.7. Rating D — useful descriptor but weak score-discriminator."
        ),
        "edge_cases": [
            "Trajectories with zero failures still get value=1.0 (Laplace smoothing) — flag separately if you need a 'no errors' signal.",
            "Classifier is regex-based — false positives on logs that mention 'syntax' without an actual SyntaxError.",
        ],
        "outputs": ["<code>M94_compile_runtime_ratio</code>"],
        "source": "compute_metrics.py (Laplace-smoothed error-class ratio).",
    },
    {
        "id": "J38", "slug": "j38_propagation_length_distribution",
        "en": "Propagation Length Distribution", "zh": "传播长度分布",
        "method": "Auto / Aggregate (built on J37)",
        "intuition": (
            "Aggregates J37 (per-error propagation length, in steps) into a per-model distribution: mean, std, and "
            "p25/p50/p75/p95. Low mean + low std = errors die fast; high mean = errors live long; high std = inconsistent."
        ),
        "value_range": "non-negative integers (steps)",
        "direction": "Lower mean & std = healthier; high mean or std = error-handling weakness.",
        "formula": (
            "for each model m:\n"
            "    lengths = [J37(t) for t in trajectories where model=m]\n"
            "    J38_mean(m) = mean(lengths)\n"
            "    J38_std(m)  = std(lengths)\n"
            "    J38_p{25,50,75,95}(m) = numpy.percentile(lengths, q)"
        ),
        "inputs": "Per-trajectory <code>J37_propagation_length</code> values keyed by model.",
        "procedure": [
            "Run J37 on every trajectory (separate judge step).",
            "Group J37 values by model.",
            "Compute mean, std, and quartile + p95 percentiles per model.",
            "Persist as a per-model row in <code>judge_m37_m38/m38_aggregated.json</code>.",
        ],
        "worked": (
            "Aggregated from <code>judge_m37_m38/results.json</code> (per-trajectory J37) into "
            "<code>judge_m37_m38/m38_aggregated.json</code>. Per-model rows include "
            "<code>{mean, std, p25, p50, p75, p95}</code>. The current presentation page does not yet expose model-level "
            "comparison tables — open the JSON for raw values."
        ),
        "edge_cases": [
            "Models with <5 trajectories ⇒ percentiles unreliable; flag as low-n in the output.",
            "If J37 is missing for a trajectory (judge parse error), it's dropped from the aggregate.",
        ],
        "outputs": ["<code>J38_mean_per_model</code>", "<code>J38_std_per_model</code>", "<code>J38_p25/p50/p75/p95</code>"],
        "source": "judge_m37_m38.py (aggregation step over J37 results). Aggregated JSON: judge_m37_m38/m38_aggregated.json.",
    },
]


def render(m):
    bullets = lambda items: "\n".join(f"<li>{x}</li>" for x in items)
    procedure_html = "<ol>\n" + bullets(m["procedure"]) + "\n</ol>"
    edge_html = "<ul>\n" + bullets(m["edge_cases"]) + "\n</ul>"
    outputs_html = "<ul>\n" + bullets(m["outputs"]) + "\n</ul>"
    body = f"""
        <p>{m["intuition"]}</p>

        <h2>At a Glance</h2>
        <div class="table-wrapper"><table>
          <thead><tr><th>Field</th><th>Value</th></tr></thead>
          <tbody>
            <tr><td><strong>Metric ID</strong></td><td><code>{html.escape(m["id"])}</code></td></tr>
            <tr><td><strong>English</strong></td><td>{html.escape(m["en"])}</td></tr>
            <tr><td><strong>中文</strong></td><td>{html.escape(m["zh"])}</td></tr>
            <tr><td><strong>Method</strong></td><td>{html.escape(m["method"])}</td></tr>
            <tr><td><strong>Value range</strong></td><td>{html.escape(m["value_range"])}</td></tr>
            <tr><td><strong>Direction</strong></td><td>{m["direction"]}</td></tr>
          </tbody>
        </table></div>

        <h2>Formula</h2>
        <div class="code-block"><pre><code>{html.escape(m["formula"])}</code></pre></div>

        <h2>Required Inputs</h2>
        <p>{m["inputs"]}</p>

        <h2>Procedure</h2>
        {procedure_html}

        <h2>Worked Example</h2>
        <p>{m["worked"]}</p>

        <h2>Edge Cases</h2>
        {edge_html}

        <h2>Output Keys</h2>
        {outputs_html}

        <h2>Source</h2>
        <p>{html.escape(m["source"])}</p>
    """
    page = PREFIX + body + SUFFIX
    # Patch the head: title + badge + h1 inside header
    page = page.replace(
        "<title>M74 - Action Entropy</title>",
        f'<title>{html.escape(m["id"])} - {html.escape(m["en"])}</title>',
    )
    # The header has a metric-badge div with M74; replace to current id
    page = page.replace(">M74<", f'>{html.escape(m["id"])}<')
    page = page.replace("Action Entropy <span", f'{html.escape(m["en"])} <span')
    page = page.replace("动作熵 / 行为多样性", html.escape(m["zh"]))
    return page


def main():
    written = []
    for m in METRICS:
        out = os.path.join(OUT_DIR, f"{m['slug']}.html")
        with open(out, "w", encoding="utf-8") as f:
            f.write(render(m))
        written.append(out)
    print(f"wrote {len(written)} auto/stat rubric pages")
    for p in written:
        print(" -", os.path.relpath(p, os.path.dirname(__file__)))


if __name__ == "__main__":
    main()

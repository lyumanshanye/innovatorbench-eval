#!/usr/bin/env python3
"""Generate one rubric HTML per M-prefixed auto metric, matching the J39 visual style."""
from __future__ import annotations
import html
import os
import re
import textwrap

OUT_DIR = os.path.join(os.path.dirname(__file__), "rubrics")
TEMPLATE_SOURCE = os.path.join(OUT_DIR, "j39_failure_pattern.html")


# ---------- definitions for the 29 M metrics ----------

METRICS = [
    {
        "id": "M02",
        "slug": "m02_tool_chain_depth",
        "en": "Tool Chain Depth",
        "zh": "工具链深度",
        "kind": "Auto / Rule",
        "range": "≥ 0 (integer)",
        "direction": "Neutral — extreme high suggests inefficiency, very low suggests under-exploration",
        "formula": "M02 = len(react_nodes)",
        "inputs": "node.node_type == 'react'",
        "intuition": "How many tool-using steps the agent took. Each react node is one (think|action, observation) pair.",
        "procedure": [
            "Iterate over the trajectory's nodes.",
            "Count nodes whose node_type == 'react'.",
            "Return the integer count.",
        ],
        "bands": [
            ("XS", "<30 steps", "Tiny task or instant crash"),
            ("S", "30-80", "Short task"),
            ("M", "80-160", "Medium task"),
            ("L", "160-300", "Long task"),
            ("XL", "300+", "Extended/runaway"),
        ],
        "example": "Primary trajectory has 225 react nodes ⇒ M02 = 225.",
        "edge_cases": [
            "Trajectory with 0 react nodes (planning-only) ⇒ M02 = 0.",
            "Cancelled / incomplete trajectories still count whatever react nodes exist.",
        ],
        "output_keys": ["M02_tool_chain_depth"],
    },
    {
        "id": "M03",
        "slug": "m03_subtask_count",
        "en": "Subtask Count",
        "zh": "子任务数量",
        "kind": "Auto / Rule",
        "range": "≥ 0 (integer)",
        "direction": "Higher = more decomposed planning (only meaningful when M76 = 1)",
        "formula": "M03 = sum(len(planning_node.subgoals) for planning_node in planning_nodes)",
        "inputs": "planning_node.subgoals (list[str])",
        "intuition": "Total number of subgoals declared across all planning nodes. Captures how finely the agent decomposes the task.",
        "procedure": [
            "Filter nodes with node_type == 'planning'.",
            "For each, read the 'subgoals' list.",
            "Sum the lengths across all planning nodes.",
        ],
        "bands": [
            ("0", "0", "No planning at all"),
            ("Small", "1-2", "Coarse plan"),
            ("Mid", "3-5", "Standard"),
            ("High", "6-10", "Detailed"),
            ("Very high", "10+", "Possibly over-decomposed"),
        ],
        "example": "GPT-5 trajectory on task_10 declared 14 subgoals across its single planning node ⇒ M03 = 14.",
        "edge_cases": [
            "Trajectories with no planning node ⇒ M03 = 0 (use M76 to distinguish 'no plan' from 'empty plan').",
            "Multiple planning nodes are summed, not averaged.",
        ],
        "output_keys": ["M03_subtask_count"],
    },
    {
        "id": "M05",
        "slug": "m05_tool_reuse_rate",
        "en": "Tool Reuse Rate",
        "zh": "工具复用率",
        "kind": "Auto / Rule",
        "range": "[0, 1]",
        "direction": "Higher = more editing existing files vs creating new ones",
        "formula": "M05 = n_edit / (n_create + n_edit)",
        "inputs": "action.action_type ∈ {edit_file, create_file}",
        "intuition": "Fraction of file-mutating actions that were edits to existing files (vs creating fresh files). Low values mean the agent prefers re-creating files instead of iterating on them.",
        "procedure": [
            "Count action_type == 'create_file' as n_create.",
            "Count action_type == 'edit_file' as n_edit.",
            "If n_create + n_edit == 0, return None (no file mutations).",
            "Return n_edit / (n_create + n_edit).",
        ],
        "bands": [
            ("0.0", "All creates", "No iteration on existing files"),
            ("0.0-0.3", "Mostly create", "Greenfield-heavy"),
            ("0.3-0.7", "Mixed", "Balanced"),
            ("0.7-0.9", "Mostly edit", "Iterative"),
            ("1.0", "All edits", "Pure refinement"),
        ],
        "example": "Steps 34-165: create=2 (r1gui.py, custom.py), edit=5 (__init__.py, custom.py, config.yaml, r1gui.py×2) ⇒ M05 = 5/7 = 0.71.",
        "edge_cases": [
            "0 file mutations ⇒ None (excluded from numeric analysis).",
            "Pure read-only trajectories return None.",
        ],
        "output_keys": ["M05_tool_reuse_rate"],
    },
    {
        "id": "M07",
        "slug": "m07_read_before_edit_rate",
        "en": "Read-Before-Edit Rate",
        "zh": "先读后改率",
        "kind": "Auto / Rule",
        "range": "[0, 1]",
        "direction": "Higher = more careful (reads file before editing it)",
        "formula": "M07 = count(edits with open_file on same path within prior 20 steps) / count(edits)",
        "inputs": "action.action_type == 'edit_file', action.path",
        "intuition": "Did the agent open and read a file before editing it? A blind edit (no prior open) is a known cause of broken patches and merge errors.",
        "procedure": [
            "Find every edit_file action's index ei and path p.",
            "Look back up to 20 steps; if any open_file with action.path == p is found, mark ei as 'preceded'.",
            "Return preceded_count / total_edits. None if no edits.",
        ],
        "bands": [
            ("0.0-0.3", "Risky", "Edits often blind"),
            ("0.3-0.6", "Mixed", "Sometimes reads first"),
            ("0.6-0.8", "Standard", "Mostly reads first"),
            ("0.8-1.0", "Cautious", "Almost always reads first"),
            ("1.0", "Always", "Strict read-then-edit"),
        ],
        "example": "5 edits; 3 had a matching open within prior 20 steps ⇒ M07 = 3/5 = 0.60.",
        "edge_cases": [
            "Empty edit_path is skipped (counts toward denominator but never satisfies match).",
            "20-step lookback is fixed; edits to the same file long after a read are NOT credited.",
            "Trajectories with 0 edits ⇒ None.",
        ],
        "output_keys": ["M07_read_before_edit_rate"],
    },
    {
        "id": "M10",
        "slug": "m10_blind_retry",
        "en": "Blind Retry",
        "zh": "盲目重试",
        "kind": "Auto / Rule",
        "range": "M10_max_blind_retry ≥ 0; M10_blind_retry_step_ratio ∈ [0, 1]",
        "direction": "Lower = better (no panic-loops)",
        "formula": "M10_max_blind_retry = max consecutive run-length of identical failed observation messages\nM10_blind_retry_step_ratio = sum(run_len for runs ≥ 3) / n_react",
        "inputs": "observation.success == false, observation.message",
        "intuition": "Detects panic-retry loops: the agent retries the same action and gets the same error message back-to-back without diagnosing the cause.",
        "procedure": [
            "Walk react nodes in order; compute the run-length of consecutive failed steps with identical, non-trivial (>10 char) error messages.",
            "Track the maximum such run length ⇒ M10_max_blind_retry.",
            "For runs of length ≥3, sum their lengths and divide by n_react ⇒ M10_blind_retry_step_ratio.",
        ],
        "bands": [
            ("0", "Healthy", "No identical-error retries"),
            ("1-2", "Light", "Occasional immediate retry"),
            ("3-5", "Notable", "Mild panic-loop"),
            ("6-10", "Bad", "Clear loop"),
            ("10+", "Severe", "Stuck"),
        ],
        "example": "Steps 124-125: identical 'Error: Session not found' twice ⇒ max_blind_retry = 2; threshold ≥3 not met ⇒ blind_retry_step_ratio = 0/225 = 0.0.",
        "edge_cases": [
            "Messages ≤ 10 chars are ignored (filters out generic 'OK'/'').",
            "Successful steps reset the run counter.",
            "Only contiguous runs are counted; intermittent retries don't accumulate.",
        ],
        "output_keys": ["M10_max_blind_retry", "M10_blind_retry_step_ratio"],
    },
    {
        "id": "M11",
        "slug": "m11_eval_abuse_rate",
        "en": "Eval Abuse Rate",
        "zh": "Eval 滥用率",
        "kind": "Auto / Rule",
        "range": "[0, 1]",
        "direction": "Lower = better (each eval should follow some change)",
        "formula": "M11 = count(consecutive eval pairs with no edit between) / count(eval pairs)",
        "inputs": "action.action_type ∈ {eval, edit_file, create_file}",
        "intuition": "Repeated eval calls without any intervening edit/create are wasteful — the score cannot change. Captures the 'spam-eval' pattern.",
        "procedure": [
            "Collect indices of all eval actions.",
            "For each consecutive pair (eval_k, eval_{k+1}), check if any edit_file/create_file lies strictly between.",
            "abuse_count += 1 when no edit found.",
            "Return abuse_count / (len(eval_indices) - 1). 0.0 if <2 evals.",
        ],
        "bands": [
            ("0.0", "Clean", "Every eval follows a change"),
            ("0.0-0.2", "Mostly clean", "Rare duplicate"),
            ("0.2-0.5", "Notable", "Some spam"),
            ("0.5-0.8", "Heavy", "Often re-evaluates without changes"),
            ("0.8-1.0", "Pathological", "Eval spam"),
        ],
        "example": "evals at steps 24 and 37, with edit_file between ⇒ abuse_count = 0 ⇒ M11 = 0/1 = 0.0.",
        "edge_cases": [
            "Trajectories with <2 evals return 0.0 (no pairs to evaluate).",
            "edit_file and create_file count equally as 'a change'.",
            "run_command alone does NOT count — only file mutations.",
        ],
        "output_keys": ["M11_eval_abuse_rate"],
    },
    {
        "id": "M12",
        "slug": "m12_session_leak",
        "en": "Session Leak",
        "zh": "会话泄漏",
        "kind": "Auto / Rule",
        "range": "≥ 0 (integer)",
        "direction": "Lower = better (close everything you create)",
        "formula": "M12_session_leak = max(0, n_create_session - n_close_session)",
        "inputs": "action.action_type ∈ {create_session, close_session, close_all_sessions}",
        "intuition": "Counts sessions opened but not explicitly closed. Leaked sessions accumulate to consume cluster slots and signal sloppy resource hygiene.",
        "procedure": [
            "n_create = count(action_type == 'create_session').",
            "n_close = count(action_type ∈ {close_session, close_all_sessions}).",
            "Return max(0, n_create - n_close).",
        ],
        "bands": [
            ("0", "Clean", "All sessions closed"),
            ("1", "Minor", "1 leak"),
            ("2-3", "Moderate", "Sloppy"),
            ("4-6", "Bad", "Multiple leaks"),
            ("7+", "Severe", "Resource hog"),
        ],
        "example": "create=3, close/kill=2 ⇒ M12_session_leak = 1.",
        "edge_cases": [
            "kill_session_processes is NOT counted as a close (it terminates child procs but leaves the session open).",
            "close_all_sessions counts as a single close action (intentional, conservative).",
        ],
        "output_keys": ["M12_session_leak", "M12_resource_reclaim_rate"],
    },
    {
        "id": "M12b",
        "slug": "m12b_resource_reclaim_rate",
        "en": "Resource Reclaim Rate",
        "zh": "资源回收率",
        "kind": "Auto / Rule",
        "range": "[0, 1]",
        "direction": "Higher = better",
        "formula": "M12b = min(n_close_session / n_create_session, 1.0)",
        "inputs": "action.action_type ∈ {create_session, close_session, close_all_sessions}",
        "intuition": "Companion to M12: ratio of sessions closed to sessions created, capped at 1.0. 1.0 = every created session was eventually closed.",
        "procedure": [
            "Same counts as M12.",
            "If n_create_session == 0 ⇒ None.",
            "Else return min(n_close / n_create, 1.0).",
        ],
        "bands": [
            ("0.0", "No reclaim", "Created sessions never closed"),
            ("0.0-0.5", "Poor", "Half-or-more leaked"),
            ("0.5-0.9", "Partial", "Most reclaimed"),
            ("0.9-1.0", "Good", "Almost all reclaimed"),
            ("1.0", "Perfect", "All reclaimed"),
        ],
        "example": "create=3, close=2 ⇒ M12b = min(2/3, 1.0) = 0.67.",
        "edge_cases": [
            "n_create == 0 ⇒ None (excluded from analysis).",
            "Capped at 1.0 to handle close_all_sessions inflating the count.",
        ],
        "output_keys": ["M12_resource_reclaim_rate"],
    },
    {
        "id": "M14",
        "slug": "m14_deadlock_step_ratio",
        "en": "Deadlock Step Ratio",
        "zh": "死锁步数占比",
        "kind": "Auto / Rule",
        "range": "[0, 1]",
        "direction": "Lower = better",
        "formula": "M14 = sum(run_len for runs ≥ 10 of {sleep, check_session_idle, list_sessions, get_session_output}) / n_react",
        "inputs": "action.action_type sequence",
        "intuition": "Detects monitor-deadlock: long uninterrupted runs of polling actions (sleep + check) with no productive action in between. Indicates the agent is stuck waiting and not intervening.",
        "procedure": [
            "Walk action_types; maintain run_len of consecutive deadlock-type actions.",
            "When the chain breaks (or at the end), if run_len ≥ 10, add it to deadlock_steps.",
            "Return deadlock_steps / n_react.",
        ],
        "bands": [
            ("0.0", "Healthy", "No long polling loops"),
            ("0.0-0.05", "Light", "Brief monitoring"),
            ("0.05-0.15", "Notable", "Occasional waits"),
            ("0.15-0.30", "Bad", "Significant idle time"),
            ("0.30+", "Stuck", "Trajectory dominated by polling"),
        ],
        "example": "Steps 52-65: 14-step sleep/check/get_output cycle ⇒ deadlock_steps = 14 ⇒ M14 = 14/225 = 0.062.",
        "edge_cases": [
            "Threshold is hard ≥10; runs of 9 are NOT counted.",
            "Any non-deadlock action breaks the run.",
            "n_react == 0 ⇒ 0.",
        ],
        "output_keys": ["M14_deadlock_step_ratio"],
    },
    {
        "id": "M15",
        "slug": "m15_repeated_view_rate",
        "en": "Repeated View Rate",
        "zh": "重复查看率",
        "kind": "Auto / Rule",
        "range": "[0, 1]",
        "direction": "Lower = better (reading the same file 3+ times suggests forgetting/confusion)",
        "formula": "M15 = count(unique paths opened ≥ 3 times) / count(unique paths opened)",
        "inputs": "action.action_type == 'open_file', action.path",
        "intuition": "Fraction of opened files that the agent re-reads three or more times. High values indicate poor working memory or repeatedly losing context.",
        "procedure": [
            "Build a Counter of paths from open_file actions.",
            "n_files_viewed = number of unique paths.",
            "n_files_repeat = number of paths with count ≥ 3.",
            "Return n_files_repeat / n_files_viewed.",
        ],
        "bands": [
            ("0.0", "Clean", "Each file read once or twice"),
            ("0.0-0.1", "Minor", "Rare re-read"),
            ("0.1-0.3", "Notable", "Some re-reading"),
            ("0.3-0.5", "Bad", "Heavy re-reading"),
            ("0.5-1.0", "Severe", "Most files re-read"),
        ],
        "example": "8 unique paths viewed; 3 of them opened ≥3 times ⇒ M15 = 3/8 = 0.375.",
        "edge_cases": [
            "Empty paths are filtered out before counting.",
            "0 open_file actions ⇒ M15 = 0.0 (vacuously clean).",
        ],
        "output_keys": ["M15_repeated_view_rate"],
    },
    {
        "id": "M16",
        "slug": "m16_search_vs_open_ratio",
        "en": "Search vs Open Ratio",
        "zh": "搜索 vs 打开 比",
        "kind": "Auto / Rule",
        "range": "[0, 1]",
        "direction": "Neutral — encodes information-gathering style",
        "formula": "M16 = n_search / (n_search + n_open)",
        "inputs": "action.action_type ∈ {search_dir, search_file, find_file, open_file}",
        "intuition": "Classifies the agent's exploration strategy: low ratio = open-file-heavy (linear reading), high ratio = search/find-heavy (query-driven discovery).",
        "procedure": [
            "n_search = count(search_dir + search_file + find_file).",
            "n_open = count(open_file).",
            "If n_search + n_open == 0 ⇒ None.",
            "Return n_search / (n_search + n_open).",
        ],
        "bands": [
            ("0.0", "All open", "Linear reader"),
            ("0.0-0.2", "Mostly open", "Open-heavy"),
            ("0.2-0.5", "Mixed", "Balanced"),
            ("0.5-0.8", "Mostly search", "Query-driven"),
            ("0.8-1.0", "All search", "Discovery-only"),
        ],
        "example": "search=4, open=12 ⇒ M16 = 4/16 = 0.25.",
        "edge_cases": [
            "0 of both ⇒ None (no info-gathering at all).",
            "Strategy interpretation depends on task — a research task may justify high values; a code-fix task usually does not.",
        ],
        "output_keys": ["M16_search_vs_open_ratio"],
    },
    {
        "id": "M19",
        "slug": "m19_token_consumption",
        "en": "Token Consumption",
        "zh": "Token 消耗量",
        "kind": "Auto / Rule",
        "range": "≥ 0 (integer)",
        "direction": "Lower = cheaper, but no quality signal alone — pair with M24",
        "formula": "M19_total_tokens = Σ response.usage.total_tokens over (react ∪ planning ∪ summary) nodes\nM19_input_tokens = Σ react.response.usage.input_tokens\nM19_output_tokens = Σ react.response.usage.output_tokens",
        "inputs": "node.response.usage.{input_tokens, output_tokens, total_tokens}",
        "intuition": "Total LLM tokens consumed across the full trajectory. Direct cost proxy.",
        "procedure": [
            "For each react/planning/summary node, read response.usage.",
            "Accumulate total_tokens across all node types.",
            "Accumulate input_tokens and output_tokens across react nodes only.",
        ],
        "bands": [
            ("XS", "<1M", "Cheap"),
            ("S", "1M-5M", "Moderate"),
            ("M", "5M-15M", "Standard"),
            ("L", "15M-50M", "Heavy"),
            ("XL", "50M+", "Very heavy"),
        ],
        "example": "M19_total_tokens=13,248,915; M19_input_tokens=12,914,280; M19_output_tokens=334,635.",
        "edge_cases": [
            "Nodes missing 'usage' contribute 0.",
            "Cached/prefix tokens are not separated here.",
        ],
        "output_keys": ["M19_total_tokens", "M19_input_tokens", "M19_output_tokens"],
    },
    {
        "id": "M20",
        "slug": "m20_duration_seconds",
        "en": "Duration Seconds",
        "zh": "任务耗时",
        "kind": "Auto / Rule",
        "range": "≥ 0 (seconds)",
        "direction": "Lower = faster wall-clock; pair with M02 to detect blocking I/O",
        "formula": "M20 = (max(timestamps) - min(timestamps)).total_seconds()",
        "inputs": "node.timestamp (ISO-8601)",
        "intuition": "Wall-clock time from the trajectory's first node to its last. Includes idle waits during sleep/polling.",
        "procedure": [
            "Collect timestamps from all node types (root/react/planning/judge/summary).",
            "Sort; t0 = first, t1 = last.",
            "Return (t1 - t0).total_seconds().",
        ],
        "bands": [
            ("XS", "<10 min", "Quick"),
            ("S", "10-60 min", "Short"),
            ("M", "1-3 h", "Standard"),
            ("L", "3-9 h", "Long"),
            ("XL", "9 h+", "Marathon"),
        ],
        "example": "First ts 01:25:20, last 10:38:03 ⇒ M20 = 33,163 s ≈ 9 h 13 m.",
        "edge_cases": [
            "Fewer than 2 timestamps ⇒ None.",
            "ISO parsing failure ⇒ None.",
            "High duration ≠ poor work — long trainings inflate this naturally.",
        ],
        "output_keys": ["M20_duration_seconds"],
    },
    {
        "id": "M21",
        "slug": "m21_format_fail_rate",
        "en": "Format Fail Rate",
        "zh": "格式失败率",
        "kind": "Auto / Rule",
        "range": "[0, 1]",
        "direction": "Lower = better",
        "formula": "M21 = count(action_type ∈ {null, ''}) / n_react",
        "inputs": "action.action_type",
        "intuition": "Fraction of react steps where the model failed to emit a parseable action. Strong signal of generation/format failure.",
        "procedure": [
            "n_null = count of react nodes with empty or null action_type.",
            "Return n_null / n_react.",
        ],
        "bands": [
            ("0.0", "Clean", "No format failures"),
            ("0.0-0.02", "Minor", "Rare slip"),
            ("0.02-0.10", "Notable", "Multiple slips"),
            ("0.10-0.25", "Bad", "Format trouble"),
            ("0.25+", "Broken", "Output structure collapsing"),
        ],
        "example": "task_10 grok-4 step 79: action == null ⇒ counted ⇒ M21 = 1/80 = 0.0125.",
        "edge_cases": [
            "n_react == 0 ⇒ 0.",
            "Empty string ('') and missing action are both counted.",
        ],
        "output_keys": ["M21_format_fail_rate"],
    },
    {
        "id": "M23",
        "slug": "m23_effective_step_rate",
        "en": "Effective Step Rate",
        "zh": "有效步骤率",
        "kind": "Auto / Rule (composite)",
        "range": "[0, 1]",
        "direction": "Higher = better",
        "formula": "M23 = max(0, 1 - (M21_format_fail_rate + M10_blind_retry_step_ratio + M14_deadlock_step_ratio))",
        "inputs": "M21, M10 step ratio, M14 (computed first)",
        "intuition": "Composite metric: fraction of react steps that are NOT wasted on format failures, blind retries, or deadlock polling.",
        "procedure": [
            "Compute M21, M10_blind_retry_step_ratio, M14 first.",
            "Sum them as 'waste'.",
            "Return max(0, 1 - waste).",
        ],
        "bands": [
            ("<0.6", "Severe", "Most steps wasted"),
            ("0.6-0.8", "Bad", "Significant waste"),
            ("0.8-0.9", "OK", "Some waste"),
            ("0.9-0.97", "Good", "Mostly productive"),
            ("0.97-1.0", "Excellent", "Near-zero waste"),
        ],
        "example": "format_fail=0/225, blind_retry=0/225, deadlock=14/225 ⇒ waste = 0.062 ⇒ M23 = 0.938.",
        "edge_cases": [
            "Companion metric M96 uses identical math but normalised by raw step counts; in the canonical implementation the values coincide.",
            "Lower-bounded at 0.",
        ],
        "output_keys": ["M23_effective_step_rate"],
    },
    {
        "id": "M24",
        "slug": "m24_token_per_point",
        "en": "Token-per-Point",
        "zh": "Token 单点成本",
        "kind": "Auto / Rule",
        "range": "≥ 0 (tokens/score)",
        "direction": "Lower = better (cheaper per quality unit)",
        "formula": "M24_token_per_point = M19_total_tokens / M24_best_eval_score",
        "inputs": "react node with action.action_type == 'eval', observation.overall_score",
        "intuition": "Cost-efficiency metric: how many LLM tokens were spent per evaluation point. Combines cost (M19) and quality (best eval).",
        "procedure": [
            "Collect all eval observation.overall_score values.",
            "best_score = max(scores); num_evals = len(scores).",
            "If best_score > 0 and total_tokens > 0 ⇒ M24 = total_tokens / best_score.",
            "Else ⇒ None.",
        ],
        "bands": [
            ("<100K", "Excellent", "Cheap quality"),
            ("100K-500K", "Good", ""),
            ("500K-2M", "Standard", ""),
            ("2M-10M", "Expensive", ""),
            (">10M", "Very expensive", "Cost dominated"),
        ],
        "example": "best_score = 8.45, total_tokens = 13.2M ⇒ M24 ≈ 1.56M tokens/point.",
        "edge_cases": [
            "0 evals or 0 score ⇒ None.",
            "Highly skewed; consider log scale in plots.",
        ],
        "output_keys": ["M24_token_per_point", "M24_best_eval_score", "M24_num_evals"],
    },
    {
        "id": "M26",
        "slug": "m26_first_eval_step",
        "en": "First Eval Step",
        "zh": "首次评估步骤",
        "kind": "Auto / Rule",
        "range": "≥ 0 (integer step index)",
        "direction": "Lower = earlier feedback loop (good); but too early may waste evals",
        "formula": "M26 = first index i in react_nodes where action.action_type == 'eval', else None",
        "inputs": "action.action_type == 'eval'",
        "intuition": "When did the agent first invoke eval? Early evals reveal a tighter feedback loop; very late evals indicate the agent waited until the end.",
        "procedure": [
            "Iterate react nodes in order.",
            "Return the index of the first 'eval' action, or None if none.",
        ],
        "bands": [
            ("<20", "Very early", "Quick checkpoint"),
            ("20-60", "Early", "Iterative"),
            ("60-130", "Mid", "Standard"),
            ("130-200", "Late", "Big-bang style"),
            (">200", "Very late", "Eval at the end"),
        ],
        "example": "First 'eval' at react node[145] ⇒ M26 = 145 (≈ 64% through the 225-step trajectory).",
        "edge_cases": [
            "0 eval actions ⇒ None.",
            "Index is 0-based across react nodes only.",
        ],
        "output_keys": ["M26_first_eval_step"],
    },
    {
        "id": "M43",
        "slug": "m43_precursor_signals",
        "en": "Precursor Signals",
        "zh": "预警信号集",
        "kind": "Auto / Rule (composite)",
        "range": "Multiple sub-fields, see Output Keys",
        "direction": "All three sub-signals: lower = healthier",
        "formula": "M43_session_create_count = count(action_type == 'create_session')\nM43_max_consecutive_sleep = longest run of {sleep, check_session_idle}\nM43_token_burn_rate_first10pct = mean tokens per step over the first ⌊0.1 × n_react⌋ steps",
        "inputs": "action.action_type, response.usage.total_tokens",
        "intuition": "Three early-warning signals that often correlate with later failure: too many sessions, sleep storms, and front-loaded token burn.",
        "procedure": [
            "Count 'create_session' actions.",
            "Compute max consecutive run of {sleep, check_session_idle}.",
            "If n_react ≥ 10, take first ⌊0.1·n_react⌋ steps and compute mean total_tokens per step.",
        ],
        "bands": [
            ("session_create", "0-1 healthy", "2-3 caution", "4+ leaky"),
            ("max_consec_sleep", "<5 healthy", "5-15 polling", "15+ stuck"),
            ("token_burn_first10pct", "low (<5K) cheap", "5K-30K standard", "30K+ front-loaded"),
            ("", "", ""),
            ("", "", ""),
        ],
        "example": "session_create=3 (steps 127, 171, 202), max_consecutive_sleep=7 (steps 69-83), token_burn_first10pct ≈ 15.4K tokens/step.",
        "edge_cases": [
            "n_react < 10 ⇒ token_burn_first10pct = None.",
            "These signals are strongest as features in a downstream classifier — single-signal thresholds are coarse.",
        ],
        "output_keys": [
            "M43_session_create_count",
            "M43_max_consecutive_sleep",
            "M43_token_burn_rate_first10pct",
        ],
    },
    {
        "id": "M43b",
        "slug": "m43b_session_create_count",
        "en": "Session Create Count",
        "zh": "会话创建数",
        "kind": "Auto / Rule",
        "range": "≥ 0 (integer)",
        "direction": "Lower = better (resource hygiene)",
        "formula": "M43b = count(action.action_type == 'create_session')",
        "inputs": "action.action_type",
        "intuition": "Standalone count of create_session actions. Pair with M12_session_leak; when both are high the agent is creating sessions and never closing them.",
        "procedure": [
            "Count react nodes where action.action_type == 'create_session'.",
        ],
        "bands": [
            ("0-1", "Minimal", "Stays in 1 session"),
            ("2-3", "Standard", ""),
            ("4-6", "Heavy", ""),
            ("7-10", "Very heavy", ""),
            ("10+", "Extreme", "Likely leaking"),
        ],
        "example": "Steps 127, 171, 202 ⇒ M43b = 3.",
        "edge_cases": [
            "Same as M43_session_create_count — exposed as its own row for the leaderboard.",
        ],
        "output_keys": ["M43_session_create_count"],
    },
    {
        "id": "M53",
        "slug": "m53_code_locate_efficiency",
        "en": "Code Locate Efficiency",
        "zh": "代码定位效率",
        "kind": "Auto / Rule",
        "range": "[0, 1]",
        "direction": "Lower = better (faster to first edit/create)",
        "formula": "M53 = first_edit_or_create_index / n_react",
        "inputs": "action.action_type ∈ {edit_file, create_file}",
        "intuition": "How deep into the trajectory does the agent take its first file-mutating action? Lower means it located the right spot quickly.",
        "procedure": [
            "Find first index i where action_type ∈ {edit_file, create_file}.",
            "If none exists or n_react == 0 ⇒ None.",
            "Return i / n_react.",
        ],
        "bands": [
            ("0.0-0.05", "Excellent", "First edit very early"),
            ("0.05-0.15", "Good", "Quick to act"),
            ("0.15-0.30", "Standard", ""),
            ("0.30-0.50", "Slow", "Long preamble"),
            ("0.50+", "Very slow", "Lots of exploration before any edit"),
        ],
        "example": "First create_file at step 34 ⇒ M53 = 34/225 = 0.151.",
        "edge_cases": [
            "Trajectories with no edits ⇒ None.",
            "A high score is not always bad — extensive research before editing can be appropriate.",
        ],
        "output_keys": ["M53_code_locate_efficiency"],
    },
    {
        "id": "M54",
        "slug": "m54_explore_edit_ratio",
        "en": "Explore-Edit Ratio",
        "zh": "探索-编辑比",
        "kind": "Auto / Rule",
        "range": "≥ 0",
        "direction": "Neutral — too high = research-heavy; too low = edit-without-context",
        "formula": "M54 = n_explore / n_edit_total\nexplore_types = {open_file, search_dir, search_file, find_file, list_files, get_file_info}\nedit_types = {edit_file, create_file}",
        "inputs": "action.action_type",
        "intuition": "How many exploration actions per file mutation. Encodes the agent's investigate-vs-act tempo.",
        "procedure": [
            "n_explore = count of actions in explore_types.",
            "n_edit_total = count in edit_types.",
            "If n_edit_total == 0 ⇒ None.",
            "Return n_explore / n_edit_total.",
        ],
        "bands": [
            ("<1", "Edit-heavy", "Often blind edits"),
            ("1-2", "Balanced", ""),
            ("2-5", "Explore-leaning", "Standard for new tasks"),
            ("5-10", "Research-heavy", ""),
            ("10+", "Investigation-only", "Slow to act"),
        ],
        "example": "n_explore = 22, n_edit_total = 7 ⇒ M54 = 22/7 ≈ 3.14.",
        "edge_cases": [
            "0 edits ⇒ None.",
            "Research/data-cleaning tasks legitimately ride high values.",
        ],
        "output_keys": ["M54_explore_edit_ratio"],
    },
    {
        "id": "M55",
        "slug": "m55_file_reach_rate",
        "en": "File Reach Rate",
        "zh": "文件触达率",
        "kind": "Auto / Rule",
        "range": "≥ 0",
        "direction": "Higher = wider context coverage",
        "formula": "M55 = |unique paths in explore_types| / |unique paths in edit_types|\nexplore_types and edit_types as in M54",
        "inputs": "action.path",
        "intuition": "Ratio of distinct files seen during exploration to distinct files actually edited. Captures whether the agent reads broadly before narrowing.",
        "procedure": [
            "viewed_paths = set of action.path where action_type ∈ explore_types.",
            "edited_paths = set of action.path where action_type ∈ edit_types.",
            "If edited_paths empty ⇒ None.",
            "Return len(viewed_paths) / len(edited_paths).",
        ],
        "bands": [
            ("<1", "Narrow", "Edits files barely explored"),
            ("1-2", "Tight focus", ""),
            ("2-5", "Standard", ""),
            ("5-10", "Wide", ""),
            ("10+", "Very wide", "Heavy reading per edit"),
        ],
        "example": "viewed = 8 unique paths, edited = 5 ⇒ M55 = 8/5 = 1.60.",
        "edge_cases": [
            "0 edits ⇒ None.",
            "Empty paths are filtered.",
        ],
        "output_keys": ["M55_file_reach_rate"],
    },
    {
        "id": "M57",
        "slug": "m57_post_fix_verify",
        "en": "Post-Fix Verify",
        "zh": "修复后验证",
        "kind": "Auto / Rule",
        "range": "{0, 1}",
        "direction": "1 = better (last edit was followed by a verification step)",
        "formula": "Let i* = index of last edit_file/create_file.\nM57 = 1.0 if any j > i* with action_type ∈ {run_command, eval} else 0.0",
        "inputs": "action.action_type",
        "intuition": "After the final code change, did the agent run anything to verify? An unverified final edit is a common failure mode.",
        "procedure": [
            "Find last index i* with action_type ∈ {edit_file, create_file}.",
            "If none ⇒ None.",
            "Scan steps after i*; if any run_command or eval present ⇒ 1.0; else 0.0.",
        ],
        "bands": [
            ("0", "Unverified", "Final change never tested"),
            ("", "", ""),
            ("", "", ""),
            ("", "", ""),
            ("1", "Verified", "Final change was tested"),
        ],
        "example": "Last edit at node[165] (config.yaml), followed by run_command at node[167] ⇒ M57 = 1.0.",
        "edge_cases": [
            "No edits at all ⇒ None.",
            "Binary metric; do not interpret intermediate values.",
        ],
        "output_keys": ["M57_post_fix_verify"],
    },
    {
        "id": "M71",
        "slug": "m71_reasoning_degradation",
        "en": "Reasoning Degradation Index",
        "zh": "推理退化指数",
        "kind": "Auto / Rule",
        "range": "≥ 0",
        "direction": "<1 = late responses shorter than early (degradation); ≈1 = stable; >1 = late responses longer",
        "formula": "seg = n_react // 5\nM71 = mean(content_lens[-seg:]) / mean(content_lens[:seg])",
        "inputs": "len(react.response.content)",
        "intuition": "Compares response content length in the trajectory's last 20% vs first 20%. Strong drop signals fatigue/context-pressure-induced degradation.",
        "procedure": [
            "Compute content length per react node.",
            "If n_react < 10 ⇒ None.",
            "seg = n_react // 5; first_avg = mean(first seg lengths); last_avg = mean(last seg lengths).",
            "Return last_avg / first_avg if first_avg > 0 else None.",
        ],
        "bands": [
            ("<0.3", "Severe", "Late responses collapsing"),
            ("0.3-0.6", "Bad", "Clear degradation"),
            ("0.6-0.9", "Mild", "Some shrinkage"),
            ("0.9-1.1", "Stable", ""),
            (">1.1", "Inflating", "Late responses longer (still notable)"),
        ],
        "example": "first 20% avg 312 chars, last 20% avg 47 chars ⇒ M71 = 47/312 = 0.15 (severe degradation).",
        "edge_cases": [
            "n_react < 10 ⇒ None.",
            "first_avg == 0 ⇒ None.",
            "Highly skewed distribution; consider log scale or capping at 5x.",
        ],
        "output_keys": ["M71_reasoning_degradation"],
    },
    {
        "id": "M72",
        "slug": "m72_think_effectiveness",
        "en": "Think Effectiveness",
        "zh": "Think 工具有效性",
        "kind": "Auto / Rule",
        "range": "[-1, 1]",
        "direction": "Higher = think actions actually help",
        "formula": "think_sr = #(think → next.success) / #(think actions)\nnon_think_sr = #(non-think → next.success) / #(non-think actions)\nM72 = think_sr - non_think_sr",
        "inputs": "action.action_type, observation.success",
        "intuition": "Difference in next-step success rate between steps preceded by 'think' and steps not preceded by 'think'. Positive ⇒ thinking pays off.",
        "procedure": [
            "For each i in [0, n_react-1): inspect obs_successes[i+1].",
            "Bucket into think_count / non_think_count and the success-prefixed counters.",
            "If both buckets non-empty: return think_sr - non_think_sr; else None.",
        ],
        "bands": [
            ("<-0.1", "Harmful", "Think before failing"),
            ("-0.1 to 0", "Neutral-low", ""),
            ("0 to 0.1", "Neutral-high", ""),
            ("0.1-0.3", "Helpful", ""),
            (">0.3", "Strongly helpful", ""),
        ],
        "example": "5/6 think→success, 140/219 non-think→success ⇒ M72 = 0.833 - 0.639 = 0.194.",
        "edge_cases": [
            "Either bucket empty ⇒ None.",
            "Tiny think_count amplifies noise; consider think_count ≥ 5 for trust.",
        ],
        "output_keys": ["M72_think_effectiveness", "M72_think_count"],
    },
    {
        "id": "M74",
        "slug": "m74_action_entropy",
        "en": "Action Entropy",
        "zh": "动作熵 / 行为多样性",
        "kind": "Auto / Rule",
        "range": "≥ 0 (bits)",
        "direction": "Mid = healthy; very low = stuck in 1-2 actions; very high = scattered",
        "formula": "Let bigrams = Counter of (action_types[i], action_types[i+1]) over the trajectory.\nM74_top_bigrams = top-5 bigrams as a string.\np_b = bigram_count_b / Σ bigram_count\nM74_action_entropy = -Σ p_b · log2(p_b) (bits)",
        "inputs": "action.action_type sequence",
        "intuition": "Shannon entropy of the bigram (consecutive action-type pair) distribution. Low entropy ⇒ stuck repeating one transition (e.g., sleep→check); high entropy ⇒ varied behavior. Companion field M74_top_bigrams stores the top-5 bigrams as a sparse summary of the full transition matrix.",
        "procedure": [
            "Build Counter of (a_i, a_{i+1}) for adjacent actions.",
            "Take 5 most common as M74_top_bigrams (string-formatted).",
            "Compute p_b = c_b / Σc; entropy = -Σ p_b·log2(p_b).",
            "If Σc == 0 ⇒ entropy = None.",
        ],
        "bands": [
            ("<2", "Very low", "Repetitive (stuck)"),
            ("2-3", "Low", "Narrow tool repertoire"),
            ("3-4", "Mid", "Balanced"),
            ("4-5", "High", "Varied"),
            (">5", "Very high", "Possibly scattered"),
        ],
        "example": "17 distinct action types, dominant pairs sleep→check_session_idle×28, check→get_session_output×18 ⇒ M74_action_entropy ≈ 3.24 bits.",
        "edge_cases": [
            "Trajectories with <2 actions ⇒ entropy = None.",
            "M74_top_bigrams is a string (not numeric); excluded from numeric discrimination analysis.",
        ],
        "output_keys": ["M74_top_bigrams", "M74_action_entropy"],
    },
    {
        "id": "M76",
        "slug": "m76_has_planning",
        "en": "Has Planning",
        "zh": "规划检测",
        "kind": "Auto / Rule",
        "range": "{0, 1} for has_planning; ≥0 for n_planning_nodes",
        "direction": "1 = explicit planning present",
        "formula": "M76_has_planning = 1 if planning_nodes else 0\nM76_n_planning_nodes = len(planning_nodes)",
        "inputs": "node.node_type == 'planning'",
        "intuition": "Whether the agent emitted any planning node. Pair with M03 (subtask count) for plan depth.",
        "procedure": [
            "Filter nodes by node_type == 'planning'.",
            "Set M76_has_planning = 1 if any exist, else 0.",
            "Set M76_n_planning_nodes to the count.",
        ],
        "bands": [
            ("0", "No planning", "Direct action"),
            ("", "", ""),
            ("", "", ""),
            ("", "", ""),
            ("1", "Has planning", ""),
        ],
        "example": "Primary trajectory: 0 planning nodes ⇒ has_planning=0. GPT-5 trajectory: 26 planning nodes ⇒ has_planning=1, n_planning_nodes=26.",
        "edge_cases": [
            "has_planning is binary; n_planning_nodes captures intensity.",
            "Some agents emit dense planning at the start; others sprinkle them throughout.",
        ],
        "output_keys": ["M76_has_planning", "M76_n_planning_nodes"],
    },
    {
        "id": "M93",
        "slug": "m93_retry_improved",
        "en": "Retry Improved",
        "zh": "重试改善",
        "kind": "Auto / Rule",
        "range": "{0, 1} + delta",
        "direction": "1 = score went up across retries",
        "formula": "If len(eval_scores) ≥ 2:\n  M93_retry_improved = 1 if eval_scores[-1] > eval_scores[0] else 0\n  M93_score_delta = eval_scores[-1] - eval_scores[0]\nElse: both None.",
        "inputs": "react.action.action_type == 'eval', observation.overall_score",
        "intuition": "Did the last eval beat the first? Captures whether iterative refinement actually paid off.",
        "procedure": [
            "Collect overall_score from each eval observation.",
            "If <2 evals ⇒ None.",
            "Else compare last vs first; emit binary improved + raw delta.",
        ],
        "bands": [
            ("delta < -2", "Regressed", "Worse than first try"),
            ("delta -2 to 0", "Flat / down", ""),
            ("delta 0 to 1", "Slight gain", ""),
            ("delta 1 to 3", "Real gain", ""),
            ("delta > 3", "Big gain", ""),
        ],
        "example": "eval_scores = [5.0, 8.45, 8.42] ⇒ M93_retry_improved = 1 (8.42 > 5.0); M93_score_delta = 3.42.",
        "edge_cases": [
            "<2 eval calls ⇒ None for both fields.",
            "Compares first vs last only — does NOT penalize mid-trajectory regression as long as the last beats the first.",
        ],
        "output_keys": ["M93_retry_improved", "M93_score_delta"],
    },
    {
        "id": "M96",
        "slug": "m96_budget_utilization",
        "en": "Budget Utilization",
        "zh": "预算利用率",
        "kind": "Auto / Rule (composite)",
        "range": "[0, 1]",
        "direction": "Higher = better",
        "formula": "waste_steps = n_null + blind_retry_steps + deadlock_steps\nM96 = (n_react - waste_steps) / n_react",
        "inputs": "Computed from M21, M10, M14 step counts",
        "intuition": "Same idea as M23 but expressed in raw step counts: fraction of react steps that were not formatted-failed, blind-retried, or polled.",
        "procedure": [
            "n_null = format-fail steps; blind_retry_steps = sum of runs ≥3; deadlock_steps = sum of runs ≥10 of polling.",
            "waste = n_null + blind_retry_steps + deadlock_steps.",
            "Return (n_react - waste) / n_react.",
        ],
        "bands": [
            ("<0.6", "Severe waste", ""),
            ("0.6-0.8", "Bad", ""),
            ("0.8-0.9", "OK", ""),
            ("0.9-0.97", "Good", ""),
            ("0.97-1.0", "Excellent", ""),
        ],
        "example": "n_react=225, format_fail=0, blind_retry=0, deadlock=14 ⇒ waste=14 ⇒ M96 = 211/225 = 0.938.",
        "edge_cases": [
            "n_react == 0 ⇒ 0.",
            "Coincides with M23 in the canonical implementation; future versions may diverge if the waste definition changes.",
        ],
        "output_keys": ["M96_budget_utilization"],
    },
]


# ---------- shared template (extracted from j39) ----------

def _read_j39_head() -> str:
    """Read j39's <!DOCTYPE html> through the closing </header> + <main class=content> tags."""
    with open(TEMPLATE_SOURCE, encoding="utf-8") as f:
        s = f.read()
    return s


_J39 = _read_j39_head()


def _slice_template() -> tuple[str, str]:
    """Return (prefix_to_main_open, suffix_after_main_close) where the metric body goes between."""
    main_open = '<main class="content">'
    main_close = '</main>'
    i = _J39.index(main_open) + len(main_open)
    j = _J39.index(main_close, i)
    return _J39[:i], _J39[j:]


_PREFIX, _SUFFIX = _slice_template()


# ---------- per-page rendering ----------

def _render_scale(bands: list[tuple]) -> str:
    """Render the 5-band visual. bands is list of (label, range_text, desc)."""
    n = min(5, len(bands))
    pad = 5 - n
    cells = list(bands) + [("", "", "")] * pad
    label_html = "\n".join(
        f'            <span>{html.escape(c[0])}</span>'
        for c in cells
    )
    detail_html = "\n".join(
        f'            <div class="scale-detail"><span class="num">{html.escape(c[0])}</span> '
        f'{html.escape(c[1])}'
        + (f'<br><span style="color:var(--text-muted);font-size:0.65rem;">{html.escape(c[2])}</span>' if c[2] else "")
        + '</div>'
        for c in cells
    )
    return f"""
    <div class="scoring-scale">
        <h3>Value Bands</h3>
        <div class="scale-bar">
            <div class="scale-step"></div>
            <div class="scale-step"></div>
            <div class="scale-step"></div>
            <div class="scale-step"></div>
            <div class="scale-step"></div>
        </div>
        <div class="scale-labels">
{label_html}
        </div>
        <div class="scale-details">
{detail_html}
        </div>
    </div>
"""


def _patch_header(metric: dict, page: str) -> str:
    """Replace J39 header content with the metric's id + name."""
    page = re.sub(
        r'<title>.*?</title>',
        f'<title>{html.escape(metric["id"])} - {html.escape(metric["en"])}</title>',
        page,
        count=1,
    )
    page = re.sub(
        r'<div class="metric-badge">.*?</div>',
        f'<div class="metric-badge">{html.escape(metric["id"])}</div>',
        page,
        count=1,
    )
    page = re.sub(
        r'<header class="page-header">.*?<h1>.*?</h1>',
        lambda m: re.sub(r'<h1>.*?</h1>', f'<h1>{html.escape(metric["en"])} <span style="font-weight:400;font-size:0.7em;color:rgba(255,255,255,0.7);margin-left:0.5em;">{html.escape(metric["zh"])}</span></h1>', m.group(0), count=1),
        page,
        count=1,
        flags=re.DOTALL,
    )
    return page


def _patch_scale(page: str, bands: list[tuple]) -> str:
    """Replace the 1-5 scoring-scale block with our value-bands block."""
    new_scale = _render_scale(bands)
    return re.sub(
        r'<div class="scoring-scale">.*?</div>\s*</div>\s*</div>',
        new_scale.strip(),
        page,
        count=1,
        flags=re.DOTALL,
    )


def _render_body(metric: dict) -> str:
    """Render the inner content of <main class='content'>."""
    bullets = lambda items: "\n".join(f'<li>{x}</li>' for x in items)
    return f"""
        <p>{html.escape(metric["intuition"])}</p>

        <h2>At a Glance</h2>
        <div class="table-wrapper"><table>
          <thead><tr><th>Field</th><th>Value</th></tr></thead>
          <tbody>
            <tr><td><strong>Metric ID</strong></td><td><code>{html.escape(metric["id"])}</code></td></tr>
            <tr><td><strong>English</strong></td><td>{html.escape(metric["en"])}</td></tr>
            <tr><td><strong>中文</strong></td><td>{html.escape(metric["zh"])}</td></tr>
            <tr><td><strong>Method</strong></td><td>{html.escape(metric["kind"])}</td></tr>
            <tr><td><strong>Value range</strong></td><td>{html.escape(metric["range"])}</td></tr>
            <tr><td><strong>Direction</strong></td><td>{html.escape(metric["direction"])}</td></tr>
          </tbody>
        </table></div>

        <h2>Formula</h2>
        <div class="code-block"><pre><code>{html.escape(metric["formula"])}</code></pre></div>

        <h2>Required Inputs</h2>
        <p><code>{html.escape(metric["inputs"])}</code></p>

        <h2>Procedure</h2>
        <ol>{bullets(metric["procedure"])}</ol>

        <h2>Worked Example</h2>
        <p>{html.escape(metric["example"])}</p>

        <h2>Edge Cases</h2>
        <ul>{bullets(metric["edge_cases"])}</ul>

        <h2>Output Keys</h2>
        <ul>{bullets(f'<code>{html.escape(k)}</code>' for k in metric["output_keys"])}</ul>

        <h2>Source</h2>
        <p>Implementation: <code>compute_metrics.py</code> (see the section labelled <code>Metric #{metric["id"][1:].lstrip("0") or "0"}</code> in the source file). The numeric data shown on the index page comes from <code>metrics_results_424.csv</code> / <code>.json</code>.</p>
    """


def render(metric: dict) -> str:
    page = _PREFIX + _render_body(metric) + _SUFFIX
    page = _patch_header(metric, page)
    page = _patch_scale(page, metric["bands"])
    return page


def main() -> None:
    if not os.path.isdir(OUT_DIR):
        raise SystemExit(f"rubrics dir not found: {OUT_DIR}")
    written = []
    for m in METRICS:
        out_path = os.path.join(OUT_DIR, f"{m['slug']}.html")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(render(m))
        written.append(out_path)
    print(f"wrote {len(written)} files into {OUT_DIR}")
    for p in written:
        print(" -", os.path.relpath(p, os.path.dirname(__file__)))

    # Re-inject Case Studies sections so a regen never silently drops them.
    # _inject_m_cases lives next to this file; import lazily to keep it
    # optional during isolated testing.
    here = os.path.dirname(os.path.abspath(__file__))
    injector = os.path.join(here, "_inject_m_cases.py")
    if os.path.exists(injector):
        import subprocess
        print("re-injecting Case Studies...")
        subprocess.check_call(["python3", injector], cwd=here)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Extract real trajectory cases for the 16 M-rubric pages that don't have
curated trajExamples cases.

Walks all 661 workspace_task_* directories under
/inspire/hdd/project/qproject-fundationmodel/public/ai_engineer/workspace_backup
and computes per-trajectory metric values. For each metric we pick a real
trajectory (top, bottom, median, or contribution-extreme) and emit a
case-card payload identical in shape to the trajExamples entries on the
present-site index.html.

Output: real_cases.json next to this file.
"""
from __future__ import annotations

import json
import math
import os
import re
import statistics
import sys
from collections import Counter, defaultdict

WORKSPACE = "/inspire/hdd/project/qproject-fundationmodel/public/ai_engineer/workspace_backup"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "real_cases.json")

# ---------- node-walk helpers ----------

def list_trajectories() -> list[str]:
    out = []
    for name in sorted(os.listdir(WORKSPACE)):
        if not name.startswith("workspace_task_"):
            continue
        nodes_dir = os.path.join(WORKSPACE, name, "nodes")
        if os.path.isdir(nodes_dir):
            out.append(name)
    return out


def parse_dirname(name: str) -> dict:
    # workspace_task_<id>_<date>_step<N>_<model>
    m = re.match(r"workspace_task_(\d+)_([\d\-:.T]+)_step(\d+)_(.+)", name)
    if not m:
        return {"task_id": None, "model": name}
    return {"task_id": int(m.group(1)), "run_date": m.group(2),
            "step": m.group(3), "model": m.group(4)}


def load_nodes(name: str) -> list[dict]:
    nodes_dir = os.path.join(WORKSPACE, name, "nodes")
    files = os.listdir(nodes_dir)
    # Filename suffix is ISO timestamp — sort lexicographically.
    files = sorted(files, key=lambda f: f.split("_")[-1])
    out = []
    for f in files:
        path = os.path.join(nodes_dir, f)
        try:
            with open(path) as fh:
                out.append(json.load(fh))
        except Exception:
            continue
    return out


def get_action_type(node: dict) -> str | None:
    a = node.get("action")
    if isinstance(a, dict):
        return a.get("action_type")
    return None


def get_action_path(node: dict) -> str | None:
    a = node.get("action") or {}
    # path is in action.path or action.file_path or action.arguments.path
    for k in ("file_path", "path", "filename"):
        v = a.get(k)
        if v:
            return v
    args = a.get("arguments") or {}
    if isinstance(args, dict):
        for k in ("file_path", "path"):
            v = args.get(k)
            if v:
                return v
    return None


def get_obs(node: dict) -> dict:
    o = node.get("observation")
    return o if isinstance(o, dict) else {}


# ---------- per-trajectory metric computation ----------

# Action types treated as "tool calls" for schema-compliance and other counts.
TOOL_TYPES = {
    "run_command", "create_session", "close_session", "kill_session_processes",
    "check_session_idle", "get_session_output", "open_file", "edit_file",
    "create_file", "list_files", "find_file", "search_dir", "search_file",
    "file_scroll_up", "file_scroll_down", "web_search", "web_browse",
    "eval", "think", "sleep", "summarize", "judge",
}

# Compile-class failure regex for M94.
COMPILE_RE = re.compile(
    r"(SyntaxError|IndentationError|parse[ -]?error|malformed JSON|"
    r"unexpected (?:EOF|indent|token)|missing parenthesis|"
    r"could not parse|invalid syntax)",
    flags=re.IGNORECASE,
)


def compute(name: str, nodes: list[dict]) -> dict:
    react = [n for n in nodes if n.get("node_type") == "react"]
    n_react = len(react)
    actions = [(n, get_action_type(n)) for n in react]
    at_only = [t for _, t in actions if t]
    at_counter = Counter(at_only)

    # --- M12b: resource reclaim ---
    n_create = at_counter.get("create_session", 0)
    n_close = at_counter.get("close_session", 0) + at_counter.get(
        "close_all_sessions", 0
    )
    m12b = min(n_close / n_create, 1.0) if n_create > 0 else None

    # --- M43b: session create count ---
    m43b = n_create

    # --- M29: parameter schema compliance ---
    # We don't have JSON schemas for each action_type at hand; use a
    # heuristic that approximates the deployed metric: a tool call is
    # compliant iff the action object parses (action_type is non-null) AND
    # the observation isn't a "pydantic validation" / "argument" error.
    schema_total = 0
    schema_ok = 0
    for n, at in actions:
        if not at:
            continue
        schema_total += 1
        msg = (get_obs(n).get("message") or "")
        if not isinstance(msg, str):
            msg = str(msg)
        bad = re.search(
            r"(validation error|argument missing|required field|"
            r"invalid (?:type|schema|argument)|TypeError: .* argument)",
            msg, re.IGNORECASE,
        )
        if not bad:
            schema_ok += 1
    m29 = (schema_ok / schema_total) if schema_total else None

    # --- M56: bug reproduction (run_command or eval before first edit) ---
    edit_idxs = [i for i, (_, t) in enumerate(actions) if t == "edit_file"]
    if edit_idxs:
        first_edit = edit_idxs[0]
        precedes = any(
            t in ("run_command", "eval") for _, t in actions[:first_edit]
        )
        m56 = 1.0 if precedes else 0.0
    else:
        m56 = None

    # --- M58: edit rollback within 5-action window ---
    rollback = 0
    total_edits = 0
    recent_paths: list[str | None] = []
    for n, at in actions:
        if at == "edit_file":
            total_edits += 1
            p = get_action_path(n)
            if p and p in recent_paths[-5:]:
                rollback += 1
        # update window
        recent_paths.append(get_action_path(n) if at == "edit_file" else None)
    m58 = (rollback / total_edits) if total_edits >= 2 else None

    # --- M84: verbosity-normalized score = M24 / log(total_tokens + 1) ---
    # M24 = best eval score; need eval observations.
    eval_scores: list[float] = []
    for n, at in actions:
        if at == "eval":
            obs = get_obs(n)
            msg = obs.get("message") or ""
            if isinstance(msg, str):
                # Look for "score: X.XX" or "{score: X}" etc.
                m = re.search(r"score[\"' :=]+\s*([0-9.]+)", msg)
                if m:
                    try:
                        eval_scores.append(float(m.group(1)))
                    except ValueError:
                        pass
    best_eval = max(eval_scores) if eval_scores else None
    total_tokens = 0
    for n in react:
        usage = ((n.get("response") or {}).get("usage")) or {}
        if isinstance(usage, dict):
            total_tokens += int(usage.get("total_tokens", 0) or 0)
    m84 = (best_eval / math.log(total_tokens + 1)) if best_eval and total_tokens else None

    # --- M94: compile vs runtime ratio (Laplace) ---
    compile_fail = 0
    runtime_fail = 0
    for n in react:
        obs = get_obs(n)
        if obs.get("success") is False:
            msg = obs.get("message") or ""
            if not isinstance(msg, str):
                msg = str(msg)
            if COMPILE_RE.search(msg):
                compile_fail += 1
            else:
                runtime_fail += 1
    m94 = (compile_fail + 1) / (runtime_fail + 1)

    # --- duration (seconds), tokens for meta cases ---
    timestamps = []
    for n in nodes:
        ts = n.get("timestamp")
        if isinstance(ts, str):
            timestamps.append(ts)
    duration = None
    if len(timestamps) >= 2:
        # ISO format — string sort works for duration calc with parsing
        try:
            from datetime import datetime
            ts0 = min(timestamps)
            ts1 = max(timestamps)
            duration = (datetime.fromisoformat(ts1) - datetime.fromisoformat(ts0)).total_seconds()
        except Exception:
            duration = None

    return {
        "name": name,
        **parse_dirname(name),
        "n_react": n_react,
        "action_counts": dict(at_counter.most_common(15)),
        "n_create_session": n_create,
        "n_close_session": n_close,
        "n_edits": total_edits,
        "edit_rollbacks": rollback,
        "compile_fail": compile_fail,
        "runtime_fail": runtime_fail,
        "schema_total": schema_total,
        "schema_ok": schema_ok,
        "best_eval": best_eval,
        "n_evals": len(eval_scores),
        "total_tokens": total_tokens,
        "duration_sec": duration,
        "M12b": m12b,
        "M43b": m43b,
        "M29": m29,
        "M56": m56,
        "M58": m58,
        "M84": m84,
        "M94": m94,
    }


def main() -> None:
    trajs = list_trajectories()
    print(f"Found {len(trajs)} trajectories", file=sys.stderr)
    rows = []
    for i, name in enumerate(trajs):
        if i % 50 == 0:
            print(f"  [{i}/{len(trajs)}] {name}", file=sys.stderr)
        try:
            nodes = load_nodes(name)
            rows.append(compute(name, nodes))
        except Exception as e:
            print(f"  SKIP {name}: {e}", file=sys.stderr)
    with open(OUT, "w") as f:
        json.dump(rows, f, indent=1, default=str)
    print(f"wrote {len(rows)} rows -> {OUT}", file=sys.stderr)


if __name__ == "__main__":
    main()

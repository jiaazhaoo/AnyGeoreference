"""One door to Claude for every model job (reader, composer, planner, chooser): the Claude Code CLI headless, in an
isolated config directory holding only credentials, an empty working directory, a job-specific system prompt, JSON
out, and a local cache keyed by the exact request so replays are free and reproducible."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path

DEFAULT_CONFIG = "/data/lab/projects/georeference-anything/claude-config"
DEFAULT_WORKDIR = "/tmp/ga-planner-cwd"


def parse_json_answer(text: str) -> dict:
    """The one JSON object in a model's answer, tolerant of code fences, prose around it, and an answer that is a
    JSON string containing JSON (double-encoded)."""
    t = text.strip()
    if t.startswith("```"):
        t = t.strip("`").strip()
        if t.lower().startswith("json"):
            t = t[4:]
    for cand in (t, t[t.find("{"):t.rfind("}") + 1] if "{" in t else ""):
        if not cand:
            continue
        try:
            obj = json.loads(cand)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, str):
            obj = json.loads(obj)
        if isinstance(obj, dict):
            return obj
    raise ValueError(f"no JSON object in the answer: {text[:120]}")


def ask_json(system: str, user: str, model: str = "claude-sonnet-5", cache: str | Path | None = None, timeout: int = 300,
             max_turns: int = 1, allowed_tools: str | None = None, workdir: str | None = None) -> dict:
    key = hashlib.sha256(json.dumps([model, system, user, allowed_tools], sort_keys=True).encode()).hexdigest()
    cache = Path(cache) if cache else None
    if cache and cache.exists():
        for line in open(cache):
            r = json.loads(line)
            if r["key"] == key:
                return r["answer"]
    env = {"HOME": os.environ.get("HOME", ""), "PATH": os.environ.get("PATH", ""), "TERM": "xterm",
           "CLAUDE_CONFIG_DIR": os.environ.get("GA_CLAUDE_CONFIG", DEFAULT_CONFIG)}
    wd = Path(workdir or os.environ.get("GA_CLAUDE_WORKDIR", DEFAULT_WORKDIR)); wd.mkdir(parents=True, exist_ok=True)
    cmd = ["claude", "-p", user, "--system-prompt", system + " Answer with exactly one JSON object and nothing else: no prose, no code fences.",
           "--output-format", "json", "--max-turns", str(max_turns), "--model", model]
    if allowed_tools:
        cmd += ["--allowedTools", allowed_tools]
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env, cwd=str(wd))
    res = json.loads(out.stdout)
    if res.get("is_error"):
        raise RuntimeError(res.get("result", "claude cli error"))
    answer = parse_json_answer(res["result"])
    if cache:
        with open(cache, "a") as f:
            f.write(json.dumps({"key": key, "answer": answer, "usage": {"cost_usd": res.get("total_cost_usd"), "duration_ms": res.get("duration_ms")}, "model": model}) + "\n")
    return answer

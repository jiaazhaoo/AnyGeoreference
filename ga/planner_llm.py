"""An LLM chooser for the Planner: shown the runnable tools and the state summary (no coordinates), it names the
next tool or `stop`. Goes through whatever OpenAI-compatible endpoint DEEPSEEK_BASE_URL points at (under a control
layer that is its gateway, which holds the key, caches and caps); every answer is also cached locally by the exact
request, so a replay costs nothing and is reproducible."""
from __future__ import annotations

import hashlib
import json
import os
import urllib.request
from pathlib import Path

SYSTEM = """You plan one georeferencing run. You see the tools you may call next (name, what each consumes and
produces, its evidence family, whether it is deterministic, its cost) and the current state: cues read off the
sheet, candidate areas, placement hypotheses with scores, evidence, cost so far, steps taken. You never see
coordinates. Choose the single next tool that most improves the chance of a verified placement, or answer `stop`
when the state has a verified hypothesis (evidence supports the best hypothesis) or no tool can add anything.
Prefer deterministic, cheap tools; do not repeat a tool that already ran unless its inputs changed. Answer with
one JSON object: {"tool": "<name or stop>", "why": "<one sentence>"}."""


class LLMChooser:
    def __init__(self, model: str = "deepseek-chat", cache: str | Path | None = None, temperature: float = 0.0, log: list | None = None):
        self.model, self.temperature = model, temperature
        self.base = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1").rstrip("/")
        self.key = os.environ.get("DEEPSEEK_API_KEY", "")
        self.cache = Path(cache) if cache else None
        self._mem: dict[str, dict] = {}
        if self.cache and self.cache.exists():
            for line in open(self.cache):
                r = json.loads(line)
                self._mem[r["key"]] = r
        self.log = log if log is not None else []
        self.calls = self.cached = 0

    def _ask(self, messages: list[dict]) -> dict:
        key = hashlib.sha256(json.dumps([self.model, self.temperature, messages], sort_keys=True).encode()).hexdigest()
        if key in self._mem:
            self.cached += 1
            return self._mem[key]["answer"]
        if not self.key:
            raise RuntimeError("DEEPSEEK_API_KEY not set (run under the control layer's gateway, or set it)")
        body = {"model": self.model, "temperature": self.temperature, "messages": messages, "response_format": {"type": "json_object"}, "max_tokens": 200}
        req = urllib.request.Request(f"{self.base}/chat/completions", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.key}"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            out = json.loads(resp.read())
        self.calls += 1
        text = out["choices"][0]["message"]["content"]
        try:
            answer = json.loads(text)
        except json.JSONDecodeError:
            answer = {"tool": "stop", "why": f"unparseable: {text[:80]}"}
        usage = out.get("usage", {})
        rec = {"key": key, "answer": answer, "usage": usage, "model": self.model}
        self._mem[key] = rec
        if self.cache:
            with open(self.cache, "a") as f:
                f.write(json.dumps(rec) + "\n")
        return answer

    def __call__(self, summary: dict, options: list[dict]) -> str:
        if not options:
            return "stop"
        messages = [{"role": "system", "content": SYSTEM},
                    {"role": "user", "content": json.dumps({"tools": options, "state": summary}, ensure_ascii=False)}]
        a = self._ask(messages)
        self.log.append({"sheet": summary.get("sheet"), "step": len(summary.get("steps", [])), "chose": a.get("tool"), "why": a.get("why")})
        tool = a.get("tool", "stop")
        return tool if tool == "stop" or any(o["name"] == tool for o in options) else "stop"


class ClaudeCLIChooser(LLMChooser):
    """The same chooser through the Claude Code CLI in headless mode (`claude -p`): the platform's own subscription,
    no provider key in this process. Runs in an isolated config directory (credentials only, no CLAUDE.md or
    settings from the person's own setup) and an empty working directory, with the planner's system prompt, so the
    model sees nothing but the tools and the state. Needs a logged-in CLI (`claude login`) whose credentials were
    copied into GA_CLAUDE_CONFIG. Answers are cached like the API path."""
    def __init__(self, model: str = "claude-sonnet-5", cache: str | Path | None = None, log: list | None = None, timeout: int = 180,
                 config_dir: str | None = None, workdir: str | None = None):
        super().__init__(model=model, cache=cache, temperature=0.0, log=log)
        self.key = "cli"
        self.timeout = timeout
        self.config_dir = config_dir or os.environ.get("GA_CLAUDE_CONFIG", "/data/lab/projects/georeference-anything/claude-config")
        self.workdir = Path(workdir or os.environ.get("GA_CLAUDE_WORKDIR", "/tmp/ga-planner-cwd"))
        self.workdir.mkdir(parents=True, exist_ok=True)

    def _ask(self, messages: list[dict]) -> dict:
        import subprocess
        key = hashlib.sha256(json.dumps([self.model, "cli", messages], sort_keys=True).encode()).hexdigest()
        if key in self._mem:
            self.cached += 1
            return self._mem[key]["answer"]
        env = {"HOME": os.environ.get("HOME", ""), "PATH": os.environ.get("PATH", ""), "TERM": "xterm", "CLAUDE_CONFIG_DIR": self.config_dir}
        cmd = ["claude", "-p", messages[1]["content"], "--system-prompt", messages[0]["content"] + " Answer with exactly one JSON object and nothing else: no prose, no code fences.",
               "--output-format", "json", "--max-turns", "1", "--model", self.model]
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=self.timeout, env=env, cwd=str(self.workdir))
        try:
            res = json.loads(out.stdout)
            if res.get("is_error"):
                raise RuntimeError(res.get("result", "claude cli error"))
            text = res["result"]
            answer = json.loads(text[text.index("{"):text.rindex("}") + 1])
            usage = {"cost_usd": res.get("total_cost_usd"), "duration_ms": res.get("duration_ms")}
        except (json.JSONDecodeError, ValueError, KeyError) as e:
            raise RuntimeError(f"claude cli: {e}: {out.stdout[:200]} {out.stderr[:200]}")
        self.calls += 1
        rec = {"key": key, "answer": answer, "usage": usage, "model": self.model}
        self._mem[key] = rec
        if self.cache:
            with open(self.cache, "a") as f:
                f.write(json.dumps(rec) + "\n")
        return answer

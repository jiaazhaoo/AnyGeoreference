"""The builder: when a plan names a primitive the library lacks, a Claude session with tools writes it, tests it
and the loop uses it. This is the one place the system generates code. Boundaries: the primitive's contract is
fixed (one function over the loop State, one output kind, a declared family, no coordinates from a model); the
session works in its own git worktree of this repository, with only Read / Write / Edit and the test runner; the
result is copied in only when its synthetic test passes; the worktree branch stays for a person to review."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PY = os.environ.get("GA_PY", "/env/code/plot-reasoning/GeoPlanAgent/.venv/bin/python")
WT_ROOT = Path(os.environ.get("GA_BUILD_ROOT", "/data/lab/projects/georeference-anything/build-worktrees"))

SYSTEM = """You implement one missing primitive for a georeferencing system, in the repository you are working in.
Write ga/primitives/generated/<name>.py and tests/generated/test_<name>.py, run the test with the given Python until
it passes, then stop. Follow the contract in the task exactly. Use only the standard library, numpy, shapely,
opencv (cv2), sqlite3 and the library's existing readers. Never call a hosted model or the network inside the
primitive. Keep the module under 250 lines. Do not edit any other file."""

TASK = """Primitive to build: {name}
Why the plan needs it: {why}
Consumes (object kinds that must be present in the State): {consumes}
Produces (one kind): {produces}
Evidence family: {family}
Method (implement this): {method}

Knowledge that applies:
{knowledge}

Contract (from ga/primitives/__init__.py and ga/model.py, read them first):
- def {name}(state, **params) -> list of {produces_cls} objects; read state.cues / state.candidates / state.hypotheses /
  state.layers / state.sheet (image path, record dict, meta dict with width/height/town_xy).
- Register at import time:  from .. import Primitive, register ; register(Primitive("{name}", "{family}", True, {consumes_tuple}, "{produces}", "<about>", {name}, "generated", requires=(...)))
- A Hypothesis carries transform (6 affine coefficients a,b,c,d,e,f with x' = a*x + b*y + c, y' = d*x + e*y + f, sheet px -> CRS),
  site_wkt (footprint polygon of the whole sheet in the CRS), crs, score 0..1, matcher name, note with the numbers.
- An Evidence is evalcore.Evidence(name, value, source_kind in deterministic/model/person/record, family, note=...).
- Reference data available on this machine (read-only): OS Open Names sqlite at /data/reference/base-data/opname_csv_gb/os_open_names_uk.sqlite
  (table open_names: NAME1, TYPE, LOCAL_TYPE, GEOMETRY_X, GEOMETRY_Y in EPSG:27700); named road centrelines through
  `from e2e_plan_extract.s3_georef import plan; plan.roads_near(x, y, r)` -> dict NAME -> shapely geometry (sys.path needs /env/code/e2e-plan-extract),
  and fuzzy label-to-road assignment `plan.match_roads(labels, roads, near)` where labels are dicts with name, x, y, h.
- The test must run on synthetic data only (build a few shapely lines as roads and synthetic cues), no network, no real files,
  under one second: {py} -m pytest -q tests/generated/test_{name}.py
- Existing examples to imitate: ga/primitives/generic.py (pure numpy), ga/primitives/raster.py (cv2 distance transforms).
Start by reading ga/model.py, ga/primitives/__init__.py and ga/primitives/generic.py."""

CLS = {"cue": "Cue", "candidate": "Candidate", "hypothesis": "Hypothesis", "evidence": "Evidence", "layer": "Layer"}
FAMILIES = ("sheet-reader", "record-text", "gazetteer", "address-register", "road-network", "basemap", "geometry")


def family_of(spec: dict) -> str:
    """The evidence family a plan names for a missing primitive, normalised: planners write the knowledge card's id or a
    word ('landmark gazetteer') where the contract wants one of the seven families."""
    f = str(spec.get("family", "")).lower()
    if f in FAMILIES:
        return f
    blob = f + " " + str(spec.get("method", "")).lower() + " " + str(spec.get("name", "")).lower()
    for key, fam in (("address", "address-register"), ("gazetteer", "gazetteer"), ("landmark", "gazetteer"), ("place", "gazetteer"),
                     ("road", "road-network"), ("street", "road-network"), ("record", "record-text"),
                     ("reader", "sheet-reader"), ("ocr", "sheet-reader"), ("spotter", "sheet-reader"),
                     ("render", "basemap"), ("basemap", "basemap"), ("tile", "basemap"), ("raster", "basemap"), ("image match", "basemap")):
        if key in blob:
            return fam
    return "geometry"


def _worktree(name: str) -> Path:
    WT_ROOT.mkdir(parents=True, exist_ok=True)
    wt = WT_ROOT / f"{name}-{time.strftime('%Y%m%d-%H%M%S')}"
    subprocess.run(["git", "-C", str(REPO), "worktree", "add", "-q", "-b", f"build/{wt.name}", str(wt)], check=True)
    return wt


def build_primitive(spec: dict, knowledge: str, model: str = "claude-sonnet-5", max_turns: int = 40, timeout: int = 1500, log: Path | None = None) -> dict:
    name = re.sub(r"[^a-z0-9_]", "_", spec["name"].lower())
    consumes = tuple(spec.get("consumes") or ())
    produces = spec.get("produces", "evidence")
    wt = _worktree(name)
    task = TASK.format(name=name, why=spec.get("why", ""), consumes=list(consumes), produces=produces, family=family_of(spec),
                       method=spec.get("method", ""), knowledge=knowledge, produces_cls=CLS.get(produces, "Evidence"),
                       consumes_tuple=repr(consumes), py=PY)
    env = {"HOME": os.environ.get("HOME", ""), "PATH": os.environ.get("PATH", ""), "TERM": "xterm",
           "CLAUDE_CONFIG_DIR": os.environ.get("GA_CLAUDE_CONFIG", "/data/lab/projects/georeference-anything/claude-config")}
    cmd = ["claude", "-p", task, "--system-prompt", SYSTEM, "--output-format", "json", "--max-turns", str(max_turns), "--model", model,
           "--allowedTools", f"Read,Write,Edit,Glob,Grep,Bash({PY}*)"]
    t0 = time.time()
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env, cwd=str(wt))
    try:
        res = json.loads(out.stdout)
    except json.JSONDecodeError:
        res = {"is_error": True, "result": out.stdout[-500:] + out.stderr[-500:]}
    mod, test = wt / "ga/primitives/generated" / f"{name}.py", wt / "tests/generated" / f"test_{name}.py"
    rec = {"name": name, "worktree": str(wt), "seconds": round(time.time() - t0), "turns": res.get("num_turns"), "cost_usd": res.get("total_cost_usd"),
           "session_error": bool(res.get("is_error")), "module_written": mod.exists(), "test_written": test.exists(), "test_passed": False, "installed": False}
    if mod.exists() and test.exists():
        t = subprocess.run([PY, "-m", "pytest", "-q", str(test)], capture_output=True, text=True, cwd=str(wt), timeout=300)
        rec["test_passed"] = t.returncode == 0
        rec["test_output"] = (t.stdout + t.stderr)[-400:]
        if rec["test_passed"]:
            (REPO / "ga/primitives/generated").mkdir(exist_ok=True); (REPO / "tests/generated").mkdir(exist_ok=True)
            shutil.copy2(mod, REPO / "ga/primitives/generated" / mod.name); shutil.copy2(test, REPO / "tests/generated" / test.name)
            t2 = subprocess.run([PY, "-m", "pytest", "-q", f"tests/generated/test_{name}.py"], capture_output=True, text=True, cwd=str(REPO), timeout=300)
            rec["installed"] = t2.returncode == 0
            if rec["installed"]:
                import importlib
                importlib.import_module(f"ga.primitives.generated.{name}")
    subprocess.run(["git", "-C", str(wt), "add", "-A"], capture_output=True); subprocess.run(["git", "-C", str(wt), "commit", "-q", "-m", f"builder: {name}"], capture_output=True)
    if log:
        with open(log, "a") as f:
            f.write(json.dumps(rec) + "\n")
    return rec


def knowledge_for_build(spec: dict, k: int = 4) -> str:
    """The cards a builder reads: retrieved for the missing primitive's own name, family and method (the capability
    card that says how it is built comes first), plus the contract card."""
    from .knowledge import Index
    idx = Index()
    q = " ".join([str(spec.get("name", "")).replace("_", " "), str(spec.get("family", "")), str(spec.get("why", "")), str(spec.get("method", ""))])
    hits = [c for _, c in idx.retrieve(q, k=k)]
    contract = idx.by_id("build-a-primitive")
    if contract and contract not in hits:
        hits.append(contract)
    return "\n\n".join(f"[{c.id}] ({c.method})\n{c.text}" for c in hits)


def ensure_capabilities(plan, knowledge: str | None = None, log: Path | None = None) -> list[dict]:
    """Build every primitive the plan says is missing and that its recipe actually names; return the build records.
    `knowledge` None means: retrieve the cards for each primitive from the knowledge base."""
    from .primitives import LIBRARY
    wanted = {s.primitive for s in plan.recipe.steps}
    recs = []
    for m in plan.missing_primitives:
        nm = re.sub(r"[^a-z0-9_]", "_", str(m.get("name", "")).lower())
        if not nm or nm in LIBRARY or nm not in wanted:
            continue
        recs.append(build_primitive(dict(m, name=nm), knowledge if knowledge is not None else knowledge_for_build(m), log=log))
    return recs

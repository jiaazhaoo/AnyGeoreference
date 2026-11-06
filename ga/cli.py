"""ga: run one sheet, list kinds and primitives.

    python -m ga.cli kinds
    python -m ga.cli primitives
    python -m ga.cli run --kind soi_1inch --image sheet.tif --record '{"sheet_code": "053BSW"}' [--planner] [--trace out.jsonl]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.environ.get("GEO_EVAL_REPO", "/env/code/geo-eval"))


def main(argv=None) -> int:
    from . import kinds
    from .loop import FixedPlan, Planner, run
    from .model import Sheet, digest_bytes
    from .primitives import LIBRARY, table
    ap = argparse.ArgumentParser(prog="ga")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("kinds"); sub.add_parser("primitives")
    r = sub.add_parser("run")
    r.add_argument("--kind", required=True, choices=sorted(kinds.KINDS))
    r.add_argument("--image", required=True)
    r.add_argument("--record", default="{}", help="JSON: address, sheet_code, hint_xy ...")
    r.add_argument("--meta", default="{}", help="JSON: width, height, town_xy, ocr_jsonl, page, cpu_only ...")
    r.add_argument("--planner", action="store_true", help="let an LLM choose the tools (DEEPSEEK_BASE_URL / DEEPSEEK_API_KEY)")
    r.add_argument("--max-cost", type=float, default=0.5)
    r.add_argument("--trace", help="append the trace to this JSONL")
    st_ = sub.add_parser("step", help="advance a stepwise session: show options, or choose a tool")
    st_.add_argument("--session", required=True)
    st_.add_argument("--start-kind"); st_.add_argument("--image"); st_.add_argument("--id"); st_.add_argument("--record", default="{}"); st_.add_argument("--meta", default="{}")
    st_.add_argument("--choose"); st_.add_argument("--why", default=""); st_.add_argument("--chooser", default="person")
    pl = sub.add_parser("plan", help="profile 1-3 similar sheets and have the main agent write the plan")
    pl.add_argument("--kind", default="unknown", choices=sorted(kinds.KINDS) + ["unknown"], help="a recipe family as a hint, or 'unknown' for a blind batch")
    pl.add_argument("--images", nargs="+", required=True); pl.add_argument("--ids", nargs="*", default=[])
    pl.add_argument("--record", default="{}"); pl.add_argument("--meta", default="{}")
    pl.add_argument("--reads-dir"); pl.add_argument("--no-headless", action="store_true"); pl.add_argument("--model", default="claude-sonnet-5")
    pl.add_argument("--out")
    a = ap.parse_args(argv)
    if a.cmd == "plan":
        from .orchestrate import plan_batch, read_sheet
        record, meta = json.loads(a.record), json.loads(a.meta)
        sheets, readings = [], []
        for i, img in enumerate(a.images):
            m = dict(meta)
            try:
                from PIL import Image
                Image.MAX_IMAGE_PIXELS = None
                with Image.open(img) as im:
                    m.setdefault("width", im.width); m.setdefault("height", im.height)
            except Exception:                                               # noqa: BLE001
                pass
            with open(img, "rb") as f:
                head = f.read(1 << 20)
            sid = a.ids[i] if i < len(a.ids) else Path(img).stem
            sh = Sheet(sid, kinds.KINDS[a.kind].kind if a.kind in kinds.KINDS else "unknown", img, digest_bytes(head), record, m)
            sheets.append(sh); readings.append(read_sheet(sh, a.reads_dir, headless=not a.no_headless))
        plan, raw, ctx = plan_batch(sheets, readings, model=a.model, cache=(str(Path(a.out).with_suffix(".cache.jsonl")) if a.out else None))
        out = {"plan": plan.to_dict(), "context": ctx, "raw": raw}
        if a.out:
            Path(a.out).write_text(json.dumps(out, indent=1, ensure_ascii=False, default=str))
        print(json.dumps(out["plan"], indent=1, ensure_ascii=False, default=str)[:4000])
        return 0
    if a.cmd == "step":
        from .session import StepSession
        if a.start_kind:
            record, meta = json.loads(a.record), json.loads(a.meta)
            with open(a.image, "rb") as f:
                head = f.read(1 << 20)
            sheet = Sheet(a.id or Path(a.image).stem, kinds.KINDS[a.start_kind].kind, a.image, digest_bytes(head), record, meta)
            ses = StepSession.start(a.session, sheet, a.start_kind)
        else:
            ses = StepSession(a.session)
        reg = kinds.registry_for(ses.kind())
        if a.choose:
            print(json.dumps(ses.choose(reg, a.choose, a.why, a.chooser), default=str))
        opts = ses.options(reg)
        (Path(a.session) / "options.json").write_text(json.dumps(opts, default=str, ensure_ascii=False, indent=1))
        st = opts["state"]
        print(json.dumps({"cues": len(st["cues"]), "candidates": len(st["candidates"]),
                          "hypotheses": [(h["matcher"], round(h["score"], 2)) for h in st["hypotheses"]],
                          "evidence": [(e["name"], e["value"]) for e in st["evidence"]], "cost": st["cost"], "steps": st["steps"],
                          "options": [o["name"] for o in opts["options"]], "full": str(Path(a.session) / "options.json")}, default=str))
        return 0
    if a.cmd == "kinds":
        for k, rec in kinds.KINDS.items():
            miss = kinds.unavailable(k)
            print(f"{k:<20} {rec.kind:<18} steps {len(kinds.SPECS[k].steps):2d}  cues {','.join(rec.cues) or '-'}  "
                  f"unavailable here: {','.join(miss) or 'none'}")
        return 0
    if a.cmd == "primitives":
        print(table()); return 0
    record, meta = json.loads(a.record), json.loads(a.meta)
    if "width" not in meta or "height" not in meta:
        try:
            from PIL import Image
            Image.MAX_IMAGE_PIXELS = None
            with Image.open(a.image) as im:
                meta.setdefault("width", im.width); meta.setdefault("height", im.height)
        except Exception:                                                   # noqa: BLE001
            pass
    with open(a.image, "rb") as f:
        head = f.read(1 << 20)
    sheet = Sheet(Path(a.image).stem, kinds.KINDS[a.kind].kind, a.image, digest_bytes(head), record, meta)
    reg = kinds.registry_for(a.kind)
    if a.planner:
        from .planner_llm import LLMChooser
        driver = Planner(LLMChooser(cache=os.environ.get("GA_PLANNER_CACHE")), max_cost=a.max_cost)
    else:
        driver = FixedPlan(kinds.plan_for(a.kind))
    st = run(sheet, reg, driver, a.trace)
    print(json.dumps({"sheet": sheet.id, "kind": a.kind, "driver": type(driver).__name__,
                      "steps": [(t["tool"], t.get("produced", t.get("skipped", t.get("chose")))) for t in st.trace],
                      "cues": len(st.cues), "candidates": len(st.candidates),
                      "hypotheses": [{"matcher": h.matcher, "score": round(h.score, 3), "note": h.note[:100]} for h in st.hypotheses[:3]],
                      "evidence": [{"name": e.name, "value": e.value, "family": e.family} for e in st.evidence],
                      "cost": round(st.cost, 4), "seconds": round(st.seconds, 2)}, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

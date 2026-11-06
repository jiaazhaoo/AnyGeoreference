"""The georeferencing knowledge base: markdown cards with a small frontmatter, retrieved by a TF-IDF over the card
text plus filters on kind and cue types. Cards are curated: what a professional georeferencer knows (map families,
reading, reference data, geodesy, transforms, matchers, verification, truth, failure modes, cost, literature), our
own measured findings, and the primitive contracts. Retrieval is what the planner reads before it writes a plan; it
is deliberately simple and replaceable (an embedding index can take the same interface).

Frontmatter: id, kinds (recipe families or [any]), cues (cue kinds the card speaks to), method (one line),
tags (free words that help retrieval), see (related card ids), and for capability cards: primitives (library
names that implement the method), buildable (yes/no), effort (how long a session needs), ingredients (data and
libraries the build needs). The catalogue derived from the capability cards tells the planner which known methods
the library implements today and which are known to be buildable: a missing method is built, not abstained on."""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

CARDS = Path(__file__).with_name("cards")


@dataclass
class Card:
    id: str
    kinds: list[str]
    cues: list[str]
    method: str
    text: str
    path: str = ""
    tags: list[str] = field(default_factory=list)
    see: list[str] = field(default_factory=list)
    primitives: list[str] = field(default_factory=list)
    buildable: str = ""
    effort: str = ""
    ingredients: str = ""

    @property
    def section(self) -> str:
        return self.id.split("-", 1)[0]


def _parse(p: Path) -> Card:
    raw = p.read_text()
    m = re.match(r"---\n(.*?)\n---\n(.*)", raw, re.S)
    head, body = (m.group(1), m.group(2)) if m else ("", raw)
    meta = {}
    for line in head.splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            v = v.strip()
            if v.startswith("[") and v.endswith("]"):
                meta[k.strip()] = [x.strip() for x in v[1:-1].split(",") if x.strip()]
            else:
                meta[k.strip()] = v
    def lst(k):
        v = meta.get(k, [])
        return v if isinstance(v, list) else [x.strip() for x in str(v).split(",") if x.strip()]
    return Card(meta.get("id", p.stem), lst("kinds") or ["any"], lst("cues"), str(meta.get("method", "")), body.strip(), str(p),
                lst("tags"), lst("see"), lst("primitives"), str(meta.get("buildable", "")), str(meta.get("effort", "")), str(meta.get("ingredients", "")))


def load(dir: str | Path | None = None) -> list[Card]:
    return [_parse(p) for p in sorted(Path(dir or CARDS).glob("*.md"))]


STOP = set("a an the of and or is are was be to in on for with by it its as at from that this these those no not one".split())


def _tokens(s: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", s.lower()) if t not in STOP]


class Index:
    def __init__(self, cards: list[Card] | None = None):
        self.cards = cards if cards is not None else load()
        self.tf = []
        df: dict[str, int] = {}
        for c in self.cards:
            toks = _tokens(c.text + " " + c.method + " " + " ".join(c.kinds) + " " + " ".join(c.cues) + " " + " ".join(c.tags) * 2
                           + " " + c.id.replace("-", " ") * 2 + " " + " ".join(c.primitives))
            counts: dict[str, int] = {}
            for t in toks:
                counts[t] = counts.get(t, 0) + 1
            self.tf.append(counts)
            for t in counts:
                df[t] = df.get(t, 0) + 1
        n = max(1, len(self.cards))
        self.idf = {t: math.log((n + 1) / (d + 1)) + 1 for t, d in df.items()}

    def retrieve(self, query: str, kind: str | None = None, cues: list[str] | None = None, k: int = 5) -> list[tuple[float, Card]]:
        q = _tokens(query)
        out = []
        for c, tf in zip(self.cards, self.tf):
            if kind and c.kinds != ["any"] and kind not in c.kinds:
                continue
            s = sum(tf.get(t, 0) * self.idf.get(t, 0) for t in q) / (1 + math.sqrt(sum(tf.values())))
            if cues and c.cues and set(cues) & set(c.cues):
                s *= 1.5
            if c.kinds == ["any"]:
                s *= 1.1
            if s > 0:
                out.append((s, c))
        out.sort(key=lambda x: -x[0])
        return out[:k]

    def context(self, query: str, kind: str | None = None, cues: list[str] | None = None, k: int = 5) -> str:
        return "\n\n".join(f"[{c.id}] ({c.method})\n{c.text}" for _, c in self.retrieve(query, kind, cues, k))


    def by_id(self, id: str) -> Card | None:
        return next((c for c in self.cards if c.id == id), None)

    def capabilities(self) -> list[Card]:
        """Cards that describe a method the system can run or build (they name primitives or say buildable: yes)."""
        return [c for c in self.cards if c.primitives or c.buildable]

    def catalogue(self, library: Mapping[str, object] | None = None, hidden: set[str] | None = None) -> str:
        """One line per capability: the method, which library primitives implement it today, and whether a missing one
        is known to be buildable (effort, ingredients). The planner reads this next to the retrieved cards, so a method
        the knowledge names but the library lacks is seen as a build, not as a reason to abstain."""
        if library is None:
            from ..primitives import LIBRARY as library
        hidden = hidden or set()
        lines = []
        for c in self.capabilities():
            have = [p for p in c.primitives if p in library and p not in hidden]
            miss = [p for p in c.primitives if p not in library or p in hidden]
            status = "in library: " + ", ".join(have) if have else "NOT in library"
            if miss:
                status += f"; missing: {', '.join(miss)}"
            build = ""
            if c.buildable.lower().startswith("y"):
                build = f" | buildable: yes, effort {c.effort or '?'}, needs {c.ingredients or '?'}"
            elif c.buildable.lower().startswith("n"):
                build = " | not buildable here: " + (c.effort or "see card")
            lines.append(f"- {c.method} [{c.id}] -> {status}{build}")
        return "\n".join(lines)

    def sections(self) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {}
        for c in self.cards:
            out.setdefault(c.section, []).append(c.id)
        return out

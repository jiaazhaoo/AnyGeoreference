"""The georeferencing knowledge base: markdown cards with a small frontmatter (id, kinds, cues, method), retrieved
by a TF-IDF over the card text plus filters on kind and cue types. Cards are curated: our own findings, the
recipes, the primitive contracts and the literature's conclusions. Retrieval is what the planner reads before it
writes a plan; it is deliberately simple and replaceable (an embedding index can take the same interface)."""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from pathlib import Path

CARDS = Path(__file__).with_name("cards")


@dataclass
class Card:
    id: str
    kinds: list[str]
    cues: list[str]
    method: str
    text: str
    path: str = ""


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
    return Card(meta.get("id", p.stem), meta.get("kinds", ["any"]), meta.get("cues", []), meta.get("method", ""), body.strip(), str(p))


def load(dir: str | Path | None = None) -> list[Card]:
    return [_parse(p) for p in sorted(Path(dir or CARDS).glob("*.md"))]


def _tokens(s: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", s.lower())


class Index:
    def __init__(self, cards: list[Card] | None = None):
        self.cards = cards if cards is not None else load()
        self.tf = []
        df: dict[str, int] = {}
        for c in self.cards:
            toks = _tokens(c.text + " " + c.method + " " + " ".join(c.kinds) + " " + " ".join(c.cues))
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

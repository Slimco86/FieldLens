"""Page triage (AX-14): choose the pages worth reading, with no model call.

Two deterministic signals over the text layer: a printed table of contents (dotted-leader or
trailing page number lines whose title matches a topic keyword) and keyword scoring per page.
Printed page numbers can differ from PDF page indexes, so a table-of-contents hit only boosts the
page it names and its neighbours-by-offset; every selected page still has to score on its own
text. A document with no text layer cannot be scored: the result says so (``unscored_pages``) and
selects nothing unless an explicit blind sample is requested."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field

DEFAULT_MAX_PAGES = 12
TOC_SCAN_PAGES = 10
MAX_TOC_ENTRIES = 200
TEXT_LAYER_MIN_CHARS = 20

# (pattern, weight). Production/completion equipment and perforation vocabulary only.
KEYWORDS: tuple[tuple[re.Pattern[str], float], ...] = tuple(
    (re.compile(p, re.IGNORECASE), w)
    for p, w in (
        (r"completion (?:string|schematic|diagram|report|equipment)", 3.0),
        (r"\bschematic\b", 1.5),
        (r"production packer|\bpacker\b", 3.0),
        (r"\btubing\b", 2.0),
        (r"\bperforat\w*", 2.5),
        (r"\bliner(?: hanger)?\b", 2.0),
        (r"\bcasing\b", 1.0),
        (r"\bscssv\b|\bdhsv\b|safety valve|trscssv", 2.5),
        (r"gas lift|mandrel|side pocket", 2.0),
        (r"\besp\b|electric(?:al)? submersible|\bpump\b", 2.0),
        (r"\bbearing\w*", 1.0),
        (r"\bnipple\b|\bpbr\b|polished bore", 1.5),
        (r"tubing hanger|wellhead|x-?mas tree|xmt", 1.5),
        (r"\bas[- ]installed\b", 2.0),
    )
)
_TOC_LINE = re.compile(
    r"^\s*(?P<title>[A-Za-z][^\n]{2,90}?)\s*(?:\.{2,}|\s{3,}|\s)\s*(?P<page>\d{1,4})\s*$"
)


@dataclass(frozen=True)
class PageScore:
    page: int  # 1-based
    score: float
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class TriageResult:
    pages: list[PageScore]  # selected, best first, at most ``max_pages``
    pages_total: int
    pages_scored: int
    unscored_pages: int
    strategy: str  # keyword | toc+keyword | no_text_layer | blind_sample
    toc_entries: int
    max_pages: int
    elapsed_ms: float
    notes: list[str] = field(default_factory=list)

    @property
    def selected(self) -> list[int]:
        return [p.page for p in self.pages]


def _has_layer(text: str) -> bool:
    return len("".join(text.split())) >= TEXT_LAYER_MIN_CHARS


def keyword_score(text: str) -> tuple[float, list[str]]:
    score, hits = 0.0, []
    for pattern, weight in KEYWORDS:
        found = len(pattern.findall(text))
        if found:
            score += weight * min(found, 3)
            hits.append(pattern.pattern.split("|")[0][:24])
    return score, hits


def toc_pages(texts: list[str]) -> tuple[list[int], set[int]]:
    """Printed page numbers named by keyword-matching table-of-contents lines, and the 0-based
    indexes of the pages that are themselves contents pages (two or more such lines)."""
    named: list[int] = []
    toc_like: set[int] = set()
    for index, text in enumerate(texts[:TOC_SCAN_PAGES]):
        entries = 0
        for line in text.splitlines():
            m = _TOC_LINE.match(line)
            if m is None:
                continue
            entries += 1
            if entries > MAX_TOC_ENTRIES:
                break
            if keyword_score(m.group("title"))[0] > 0:
                named.append(int(m.group("page")))
        if entries >= 2:
            toc_like.add(index)
    return named, toc_like


def triage(
    texts: list[str],
    *,
    max_pages: int = DEFAULT_MAX_PAGES,
    min_score: float = 2.0,
    blind_sample: bool = False,
) -> TriageResult:
    started = time.perf_counter()
    total = len(texts)
    layered = [i for i, t in enumerate(texts) if _has_layer(t)]
    unscored = total - len(layered)
    if not layered:
        pages: list[PageScore] = []
        strategy, notes = "no_text_layer", ["no page has a text layer; triage cannot score pages"]
        if blind_sample and total:
            step = max(1, total // max_pages)
            picks = list(range(0, total, step))[:max_pages]
            pages = [PageScore(i + 1, 0.0, ("blind_sample",)) for i in picks]
            strategy = "blind_sample"
        return TriageResult(
            pages,
            total,
            0,
            unscored,
            strategy,
            0,
            max_pages,
            (time.perf_counter() - started) * 1000,
            notes,
        )
    named_list, toc_like = toc_pages(texts)
    named = set(named_list)
    scored: list[PageScore] = []
    for index in layered:
        if index in toc_like:  # a contents page names topics; it is not a page to read
            continue
        score, hits = keyword_score(texts[index])
        reasons = list(hits)
        if (index + 1) in named:
            score += 3.0
            reasons.append("toc")
        if score >= min_score:
            scored.append(PageScore(index + 1, round(score, 2), tuple(reasons)))
    scored.sort(key=lambda p: (-p.score, p.page))
    selected = scored[:max_pages]
    notes = []
    if unscored:
        notes.append(f"{unscored} page(s) have no text layer and were not scored")
    if len(scored) > max_pages:
        notes.append(f"{len(scored) - max_pages} further page(s) scored above the threshold")
    return TriageResult(
        selected,
        total,
        len(layered),
        unscored,
        "toc+keyword" if named else "keyword",
        len(named),
        max_pages,
        (time.perf_counter() - started) * 1000,
        notes,
    )

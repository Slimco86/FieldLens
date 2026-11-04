"""Parse and validate the model's final answer; materialize charts from stored series.

The model proposes typed blocks as JSON. Nothing in it is trusted:

* blocks are re-built from server-owned data (value blocks take value/unit from the tool result at
  ``result_path``; chart blocks accept only a declarative request, never points);
* every citation marker, tool call id, series, wellbore, document and page must have been produced by
  a tool call *in this turn* and exist in the project; otherwise the block is dropped with a reason;
* text carrying URLs/markdown links is dropped (links exist only as validated ``link`` blocks);
* numbers in free text that no tool result states are flagged, not silently accepted.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Sequence
from datetime import date
from typing import Any, Protocol
from uuid import UUID

import numpy as np
from pydantic import ValidationError

from fieldlens.chat.evidence_pool import TurnEvidence
from fieldlens.chat.tools import ProjectScope
from fieldlens.contracts.charts import (
    AxisKind,
    AxisPosition,
    ChartAxis,
    ChartEmptyReason,
    ChartEmptyState,
    ChartKey,
    ChartKind,
    ChartPoint,
    ChartScope,
    ChartSeries,
    ChartSeriesScope,
    ChartSpec,
    ChartWindow,
    DownsampleInfo,
    SeriesAggregates,
)
from fieldlens.contracts.chat import (
    MAX_BLOCKS,
    AnswerBlock,
    AnswerVerification,
    AppLink,
    ChartBlock,
    ChartLinkTarget,
    ChartRequest,
    ChatAnswer,
    ChatContext,
    DroppedBlock,
    DroppedBlockReason,
    ElementLinkTarget,
    FormationLinkTarget,
    GapBlock,
    SourceLinkTarget,
    TextBlock,
    WellboreLinkTarget,
)
from fieldlens.contracts.errors import ContractError
from fieldlens.contracts.series import (
    DOWNSAMPLING_ALGORITHM,
    IndexEncoding,
    IndexType,
    SeriesUnitStatus,
    SeriesWindow,
    WindowResolution,
)
from fieldlens.series.downsample import select_positions

MAX_ANSWER_CHARS = 60_000
CHART_DISPLAY_POINTS = 1000
MAX_CHART_SERIES = 12
_MARKER = re.compile(r"\[(\d{1,3})\]")
_UNSAFE_TEXT = re.compile(r"https?://|www\.|\]\(|javascript:|<\s*script|data:text", re.I)
_STRIP_FOR_NUMBERS = re.compile(
    r"\[\d{1,3}\]|[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
    r"|\d{4}-\d{2}-\d{2}"
)
_NUMBER = re.compile(r"(?<![\w.])-?\d+(?:\.\d+)?")


class MalformedAnswer(Exception):
    """The model output is not a usable typed answer."""


class SeriesReader(Protocol):
    def get_window(
        self,
        project_id: UUID,
        series_id: UUID,
        *,
        start: str | None = None,
        end: str | None = None,
        max_points: int = ...,
        resolution: WindowResolution = ...,
    ) -> SeriesWindow: ...


def parse_model_output(text: str) -> list[dict[str, Any]]:
    """Extract the ``blocks`` list from the model's JSON (optionally fenced)."""
    body = text.strip()
    if len(body) > MAX_ANSWER_CHARS:
        raise MalformedAnswer("answer is too large")
    if body.startswith("```"):
        body = re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", body)
    try:
        data = json.loads(body)
    except (ValueError, RecursionError) as exc:
        raise MalformedAnswer("answer is not valid JSON") from exc
    blocks = data.get("blocks") if isinstance(data, dict) else None
    if not isinstance(blocks, list) or not all(isinstance(b, dict) for b in blocks):
        raise MalformedAnswer("answer has no blocks list")
    return blocks


class _Drop(Exception):
    def __init__(self, reason: DroppedBlockReason, detail: str) -> None:
        self.reason, self.detail = reason, detail


# --- path resolution ------------------------------------------------------------------------


def resolve_path(root: Any, path: str) -> Any:
    """``a.b[0].c`` / ``a.b.0.c`` into a tool result; raises KeyError when absent."""
    node = root
    for token in re.findall(r"[^.\[\]]+", path):
        if isinstance(node, dict):
            node = node[token]
        elif isinstance(node, list) and token.isdigit():
            node = node[int(token)]
        else:
            raise KeyError(token)
    return node


def _value_from(root: Any, path: str) -> tuple[float | None, str | None, str | None]:
    """(value, unit, reason-if-unknown) from the tool result, never from the model."""
    node = resolve_path(root, path)
    unit: str | None = None
    if isinstance(node, dict) and "value" in node:
        unit = node.get("unit") if isinstance(node.get("unit"), str) else None
        node = node["value"]
    elif not isinstance(node, bool) and isinstance(node, int | float):
        parent_path = re.findall(r"[^.\[\]]+", path)[:-1]
        try:
            parent = resolve_path(root, ".".join(parent_path)) if parent_path else root
        except KeyError:
            parent = None
        if isinstance(parent, dict) and isinstance(parent.get("unit"), str):
            unit = parent["unit"]
    if node is None:
        return None, unit, "not available in the tool result"
    if isinstance(node, bool) or not isinstance(node, int | float) or not math.isfinite(node):
        raise KeyError(path)
    if unit is None:
        return None, None, "unit not stated in the tool result"
    return float(node), unit, None


# --- validator -------------------------------------------------------------------------------


class AnswerValidator:
    def __init__(
        self,
        *,
        project_id: UUID,
        evidence: TurnEvidence,
        scope: ProjectScope,
        series: SeriesReader | None,
        context: ChatContext,
        tool_calls_made: int,
    ) -> None:
        self._pid = project_id
        self._ev = evidence
        self._scope = scope
        self._series = series
        self._ctx = context
        self._tool_calls = tool_calls_made
        self.used_markers: set[str] = set()

    # -- shared checks
    def _markers(self, declared: Any, text: str | None = None) -> list[str]:
        found: list[str] = []
        if isinstance(declared, list):
            found.extend(str(x) for x in declared)
        if text is not None:
            found.extend(f"[{n}]" for n in _MARKER.findall(text))
        unique = list(dict.fromkeys(found))
        for marker in unique:
            if marker not in self._ev.citables:
                raise _Drop(DroppedBlockReason.UNKNOWN_CITATION, "citation not in tool results")
        return unique

    def _tool_call(self, call_id: Any) -> Any:
        try:
            uid = UUID(str(call_id))
        except ValueError:
            raise _Drop(DroppedBlockReason.UNKNOWN_TOOL_RESULT, "bad tool call id") from None
        record = self._ev.calls.get(uid)
        if record is None or not record.ok:
            raise _Drop(DroppedBlockReason.UNKNOWN_TOOL_RESULT, "no such tool result")
        return record

    # -- block kinds
    def _text(self, raw: dict[str, Any]) -> AnswerBlock:
        text = raw.get("text")
        if not isinstance(text, str) or not text.strip():
            raise _Drop(DroppedBlockReason.UNKNOWN_TARGET, "invalid text block")
        if _UNSAFE_TEXT.search(text):
            raise _Drop(DroppedBlockReason.INVALID_LINK, "text carries a URL or markdown link")
        markers = self._markers(raw.get("citation_markers"), text)
        stripped = _STRIP_FOR_NUMBERS.sub(" ", text)
        unverified = [
            n for n in dict.fromkeys(_NUMBER.findall(stripped)) if not self._ev.number_known(n)
        ]
        self.used_markers.update(markers)
        return AnswerBlock.model_validate(
            {
                "kind": "text",
                "text": text,
                "citation_markers": markers,
                "unverified_numbers": unverified[:20],
            }
        )

    def _value(self, raw: dict[str, Any]) -> AnswerBlock:
        record = self._tool_call(raw.get("tool_call_id"))
        path = raw.get("result_path")
        if not isinstance(path, str) or not path:
            raise _Drop(DroppedBlockReason.UNKNOWN_TOOL_RESULT, "missing result_path")
        try:
            value, unit, reason = _value_from(record.result, path)
        except (KeyError, IndexError):
            raise _Drop(DroppedBlockReason.UNVERIFIED_NUMBER, "path does not resolve") from None
        markers = self._markers(raw.get("citation_markers"))
        label = raw.get("label")
        if not isinstance(label, str) or not label.strip():
            raise _Drop(DroppedBlockReason.UNKNOWN_TARGET, "invalid value block")
        self.used_markers.update(markers)
        reference = raw.get("reference")
        return AnswerBlock.model_validate(
            {
                "kind": "value",
                "label": label[:200],
                "value": value,
                "unit": unit,
                "reference": reference[:200] if isinstance(reference, str) else None,
                "tool_call_id": str(record.call_id),
                "result_path": path[:256],
                "citation_markers": markers,
                "unknown_reason": reason,
            }
        )

    def _link_target(self, link: AppLink) -> None:
        target = link.target.root
        if link.tool_call_id is not None and link.tool_call_id not in self._ev.calls:
            raise _Drop(DroppedBlockReason.UNKNOWN_TOOL_RESULT, "link tool call unknown")
        if isinstance(target, SourceLinkTarget):
            doc = target.document_id
            if not self._scope.document_exists(doc):
                raise _Drop(DroppedBlockReason.OUT_OF_PROJECT, "document not in project")
            if doc not in self._ev.documents:
                raise _Drop(DroppedBlockReason.UNKNOWN_TARGET, "document not in tool results")
            if target.locator is not None:
                if not self._ev.has_locator(doc, target.locator.root.model_dump(mode="json")):
                    raise _Drop(DroppedBlockReason.UNKNOWN_TARGET, "locator not in tool results")
            elif target.page not in self._ev.pages.get(doc, set()):
                raise _Drop(DroppedBlockReason.UNKNOWN_TARGET, "page not in tool results")
        elif isinstance(target, WellboreLinkTarget):
            self._wellbore(target.wellbore_id)
        elif isinstance(target, ChartLinkTarget):
            if target.wellbore_id is not None:
                self._wellbore(target.wellbore_id)
        elif isinstance(target, ElementLinkTarget):
            owner = self._ev.element_wellbores.get(target.element_id)
            if target.element_id not in self._ev.elements or owner is None:
                raise _Drop(DroppedBlockReason.UNKNOWN_TARGET, "element not in tool results")
            self._wellbore(owner)
            if target.wellbore_id is not None and target.wellbore_id != owner:
                raise _Drop(
                    DroppedBlockReason.UNKNOWN_TARGET, "element belongs to another wellbore"
                )
        elif isinstance(target, FormationLinkTarget):
            self._formation(target)

    def _formation(self, target: FormationLinkTarget) -> None:
        wellbores = self._ev.surfaces.get(target.surface_key)
        if wellbores is None:
            raise _Drop(DroppedBlockReason.UNKNOWN_TARGET, "formation not in tool results")
        if target.wellbore_id is not None:
            self._wellbore(target.wellbore_id)
            if target.wellbore_id not in wellbores:
                raise _Drop(DroppedBlockReason.UNKNOWN_TARGET, "formation not seen on wellbore")
        if target.pick_id is not None:
            known = self._ev.picks.get(target.pick_id)
            if known is None or known[0] != target.surface_key:
                raise _Drop(DroppedBlockReason.UNKNOWN_TARGET, "pick not in tool results")
            self._wellbore(known[1])
            if target.wellbore_id is not None and target.wellbore_id != known[1]:
                raise _Drop(DroppedBlockReason.UNKNOWN_TARGET, "pick belongs to another wellbore")

    def _wellbore(self, wellbore_id: UUID) -> None:
        if not self._scope.wellbore_exists(wellbore_id):
            raise _Drop(DroppedBlockReason.OUT_OF_PROJECT, "wellbore not in project")
        if wellbore_id not in self._ev.wellbores:
            raise _Drop(DroppedBlockReason.UNKNOWN_TARGET, "wellbore not in tool results")

    def _link(self, raw: dict[str, Any]) -> AnswerBlock:
        try:
            link = AppLink.model_validate(raw.get("link"))
        except ValidationError:
            raise _Drop(
                DroppedBlockReason.INVALID_LINK, "link does not match a target type"
            ) from None
        self._link_target(link)
        return AnswerBlock.model_validate(
            {"kind": "link", "link": link.model_dump(mode="json", by_alias=True)}
        )

    def _gap(self, raw: dict[str, Any]) -> AnswerBlock:
        try:
            gap = GapBlock.model_validate(raw)
        except ValidationError:
            raise _Drop(DroppedBlockReason.UNKNOWN_TARGET, "invalid gap block") from None
        return AnswerBlock(gap)

    def _chart(self, raw: dict[str, Any]) -> AnswerBlock:
        try:
            request = ChartRequest.model_validate(raw.get("request"))
        except ValidationError:
            raise _Drop(DroppedBlockReason.INVALID_CHART, "chart request is invalid") from None
        markers = self._markers(raw.get("citation_markers"))
        for call_id in request.tool_call_ids:
            self._tool_call(call_id)
        if request.wellbore_id is not None:
            self._wellbore(request.wellbore_id)
        if self._series is None:
            raise _Drop(DroppedBlockReason.INVALID_CHART, "series data unavailable")
        try:
            spec = materialize_chart(self._series, self._pid, request, self._ev, self._ctx.as_of)
        except ChartError as exc:
            raise _Drop(DroppedBlockReason.INVALID_CHART, str(exc)) from None
        opened: AppLink | None = None
        if request.chart_key is not ChartKey.CUSTOM:
            opened = AppLink(
                label="Open in Charts",
                target=ChartLinkTarget(
                    chart_key=request.chart_key,
                    wellbore_id=request.wellbore_id,
                    window=request.window,
                ),
            )
        self.used_markers.update(markers)
        return AnswerBlock(
            ChartBlock(request=request, spec=spec, open_in_charts=opened, citation_markers=markers)
        )

    # -- whole answer
    def validate(self, raw_blocks: Sequence[dict[str, Any]]) -> ChatAnswer:
        handlers = {
            "text": self._text,
            "value": self._value,
            "chart": self._chart,
            "link": self._link,
            "gap": self._gap,
        }
        kept: list[AnswerBlock] = []
        dropped: list[DroppedBlock] = []
        for index, raw in enumerate(raw_blocks):
            kind = raw.get("kind") if isinstance(raw.get("kind"), str) else None
            handler = handlers.get(kind or "")
            try:
                if handler is None:
                    raise _Drop(DroppedBlockReason.UNKNOWN_TARGET, "unknown block kind")
                if len(kept) >= MAX_BLOCKS:
                    raise _Drop(DroppedBlockReason.UNKNOWN_TARGET, "block limit reached")
                kept.append(handler(raw))
            except _Drop as drop:
                dropped.append(
                    DroppedBlock(
                        index=index,
                        kind=(kind or "")[:32] or None,
                        reason=drop.reason,
                        detail=drop.detail,
                    )
                )
        if not kept:
            raise MalformedAnswer("no valid block survived validation")
        citations = [
            self._ev.citables[m].to_citation()
            for m in sorted(self.used_markers, key=lambda s: int(s[1:-1]))
        ]
        flagged = any(isinstance(b.root, TextBlock) and b.root.unverified_numbers for b in kept)
        has_text = any(isinstance(b.root, TextBlock) for b in kept)
        if self._tool_calls == 0 and has_text:
            verification = AnswerVerification.UNVERIFIED
        elif dropped or flagged:
            verification = AnswerVerification.PARTIALLY_VERIFIED
        else:
            verification = AnswerVerification.VERIFIED
        return ChatAnswer(
            blocks=kept, citations=citations, verification=verification, dropped_blocks=dropped
        )


# --- chart materialization -------------------------------------------------------------------


class ChartError(Exception):
    """The requested chart cannot be built from the stored series."""


_Y_POSITIONS = (AxisPosition.Y_LEFT, AxisPosition.Y_RIGHT, AxisPosition.Y_EXTRA)


def _window_for(
    request: ChartRequest, as_of: date | None, encoding: IndexEncoding
) -> tuple[str | None, str | None]:
    start = request.window.from_ if request.window else None
    end = request.window.to if request.window else None
    if as_of is not None and encoding is IndexEncoding.EPOCH_DAYS:
        cap = as_of.isoformat()
        if end is None or end > cap:
            end = cap
    return start, end


def _fetch(
    reader: SeriesReader, pid: UUID, sid: UUID, start: str | None, end: str | None
) -> tuple[SeriesWindow, list[float | None], list[Any], bool]:
    """(window, values, xs, exact). Exact aggregates need full resolution (<= 50k samples)."""
    try:
        w = reader.get_window(
            pid, sid, start=start, end=end, max_points=5000, resolution=WindowResolution.FULL
        )
        exact = True
    except ContractError as exc:
        if "full resolution" not in exc.message:
            raise ChartError(f"series window rejected: {exc.message[:120]}") from None
        w = reader.get_window(
            pid,
            sid,
            start=start,
            end=end,
            max_points=CHART_DISPLAY_POINTS,
            resolution=WindowResolution.DOWNSAMPLED,
        )
        exact = False
    xs: list[Any] = list(w.dates) if w.dates is not None else list(w.index)
    return w, list(w.values), xs, exact


def materialize_chart(
    reader: SeriesReader,
    project_id: UUID,
    request: ChartRequest,
    evidence: TurnEvidence,
    as_of: date | None,
) -> ChartSpec:
    if not request.series_refs:
        raise ChartError("a chart needs series_refs from this turn's tool results")
    if len(request.series_refs) > MAX_CHART_SERIES:
        raise ChartError("too many series")
    ids: list[UUID] = []
    for ref in dict.fromkeys(request.series_refs):
        try:
            uid = UUID(ref)
        except ValueError:
            raise ChartError("series_refs are series ids") from None
        if uid not in evidence.series:
            raise ChartError("series was not returned by a tool in this turn")
        ids.append(uid)

    fetched: list[tuple[SeriesWindow, list[float | None], list[Any], bool]] = []
    for uid in ids:
        encoding = IndexEncoding(evidence.series[uid].index_encoding)
        start, end = _window_for(request, as_of, encoding)
        fetched.append(_fetch(reader, project_id, uid, start, end))

    first = fetched[0][0].series
    x_key = (first.index.type, first.index.encoding, first.index.unit)
    for w, *_ in fetched:
        s = w.series
        if (s.index.type, s.index.encoding, s.index.unit) != x_key:
            raise ChartError("series do not share an index type/unit")
    if first.index.encoding is IndexEncoding.EPOCH_DAYS:
        x_kind = AxisKind.TIME
    elif first.index.type is IndexType.DEPTH:
        x_kind = AxisKind.DEPTH_MD
    else:
        x_kind = AxisKind.VALUE

    axes = [
        ChartAxis(
            axis_id="x",
            name=first.index.name[:128] or "index",
            kind=x_kind,
            position=AxisPosition.X,
            unit=first.index.unit,
            unit_status=first.index.unit_status,
            inverted=x_kind is AxisKind.DEPTH_MD,
        )
    ]
    y_axes: dict[tuple[str | None, SeriesUnitStatus], str] = {}
    for w, *_ in fetched:
        key = (w.series.unit, w.series.unit_status)
        if key not in y_axes:
            if len(y_axes) >= len(_Y_POSITIONS):
                raise ChartError("more than three distinct units")
            axis_id = f"y{len(y_axes) + 1}"
            y_axes[key] = axis_id
            axes.append(
                ChartAxis(
                    axis_id=axis_id,
                    name=(key[0] or w.series.measure)[:128],
                    kind=AxisKind.VALUE,
                    position=_Y_POSITIONS[len(y_axes) - 1],
                    unit=key[0],
                    unit_status=key[1],
                )
            )

    series_out: list[ChartSeries] = []
    cache_parts: list[str] = []
    for w, values, xs, exact in fetched:
        info = w.series
        cache_parts.append(w.cache_key)
        n = w.source_samples_in_window
        arr = np.array([np.nan if v is None else v for v in values], dtype=np.float64)
        omitted = w.gaps_omitted
        applied = w.downsampled
        if exact and len(values) > CHART_DISPLAY_POINTS:
            positions, omitted = select_positions(arr, CHART_DISPLAY_POINTS)
            values = [values[int(i)] for i in positions]
            xs = [xs[int(i)] for i in positions]
            applied = True
        valid_all = arr[~np.isnan(arr)]
        valid_idx = [i for i, v in enumerate(values) if v is not None]
        nulls = w.null_samples_in_window
        valid = n - nulls
        minimum = maximum = mean = last_value = None
        if valid > 0:
            if exact:
                minimum, maximum = float(valid_all.min()), float(valid_all.max())
                mean = min(max(float(valid_all.mean()), minimum), maximum)
                last_value = float(valid_all[-1])
            else:  # extrema survive downsampling; the mean and last value are not exact: omitted
                shown = [v for v in values if v is not None]
                minimum, maximum = min(shown), max(shown)
        points = [ChartPoint(x=x, y=v) for x, v in zip(xs, values, strict=True)]
        series_out.append(
            ChartSeries(
                series_key=str(info.series_id),
                name=f"{info.measure}"[:256],
                axis_id=y_axes[(info.unit, info.unit_status)],
                x_axis_id="x",
                unit=info.unit,
                unit_status=info.unit_status,
                scope=ChartSeriesScope(
                    scope=ChartScope.WELL,
                    scope_label="well-level",
                    well_name=info.well_name,
                    wellbore_label=info.wellbore_label,
                ),
                points=points,
                gap_count=sum(1 for p in points if p.y is None) + omitted,
                downsample=DownsampleInfo(
                    applied=applied,
                    algorithm=DOWNSAMPLING_ALGORITHM if applied else None,
                    max_points=CHART_DISPLAY_POINTS,
                    source_points=n,
                    returned_points=len(points),
                    gaps_omitted=omitted,
                ),
                aggregates=SeriesAggregates(
                    count=n,
                    valid_count=valid,
                    null_count=nulls,
                    minimum=minimum,
                    maximum=maximum,
                    mean=mean,
                    last_value=last_value,
                    first_valid_x=xs[valid_idx[0]] if valid_idx else None,
                    last_valid_x=xs[valid_idx[-1]] if valid_idx and exact else None,
                    unit=info.unit,
                ),
                source_series_id=info.series_id,
                series_revision=info.revision,
            )
        )

    notes = [
        "Assembled by the assistant from stored series; every value is server data.",
        "Series are well-level: not attributed to a wellbore.",
    ]
    notes += [
        f"Source: document {w.series.document_id}, run {w.series.run_id}" for w, *_ in fetched
    ][:10]
    cache_key = hashlib.sha256(
        "|".join(cache_parts + [str(as_of), request.title or "", request.chart_key.value]).encode()
    ).hexdigest()
    all_empty = all(not s.points for s in series_out)
    window = None
    if request.window is not None:
        window = ChartWindow.model_validate(request.window.model_dump(by_alias=True))
    try:
        return ChartSpec(
            chart_id=f"assistant-{cache_key[:16]}",
            key=ChartKey.CUSTOM,
            title=(request.title or "Assistant chart")[:256],
            kind=ChartKind.LINE,
            scope=ChartSeriesScope(scope=ChartScope.WELL, scope_label="well-level"),
            axes=axes,
            series=[] if all_empty else series_out,
            empty=ChartEmptyState(
                reason=ChartEmptyReason.NO_DATA_IN_WINDOW,
                message="The stored series have no samples in this window.",
            )
            if all_empty
            else None,
            window=window,
            as_of=as_of,
            cache_key=cache_key,
            notes=notes,
        )
    except ValidationError:
        raise ChartError("chart failed contract validation") from None

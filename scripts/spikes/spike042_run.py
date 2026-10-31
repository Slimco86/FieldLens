"""Live runner for TASK-042 (opt-in, spends capped credit). Sends ONLY the seven approved PDFs.

    env -u FIELDLENS_DATABASE_URL MODEL_API_KEY=... uv run --with pypdfium2 --with pillow \
        python scripts/spikes/spike042_run.py --tag A --pages PV-21:49 --mode image \
        --long-side 1800 --effort low

The key is read from the environment only and is never printed or stored. Results go to
``.local/spike042/runs/<tag>/`` (gitignored). The budget ledger period ``spike-042`` (cap USD 3)
lives in the lane database and enforces reservations in code.
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import os
import sys
import time
from decimal import Decimal
from typing import Any

import openai
import pypdfium2 as pdfium  # type: ignore[import-not-found,unused-ignore]
from spike042_common import DOCS, SCRATCH, doc_path
from spike042_gold import all_pages
from spike042_prompt import image_user_prompt, text_user_prompt
from sqlalchemy import create_engine

from fieldlens.assistant import errors
from fieldlens.assistant.budget import BudgetLedger
from fieldlens.assistant.messages import ImagePart, Message, TextPart
from fieldlens.assistant.meta import MetaProvider
from fieldlens.assistant.provider import Pricing, scrub
from fieldlens.assistant.runner import RequestLimits, WorkUnit
from fieldlens.config import Settings
from fieldlens.persistence.session import create_session_factory

CAP = Decimal("3.00")
PERIOD = "spike-042"
RATES = {"in": Decimal("5.00"), "out": Decimal("25.00")}
REVISION = "mi6-conservative-placeholder-1"


class UsageCapture:
    """Wraps ``client.responses`` to keep the raw usage block of each response (no content)."""

    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self.usage: list[dict[str, Any]] = []
        self.responses = self

    def create(self, **kwargs: Any) -> Any:
        response = self._inner.responses.create(**kwargs)
        raw = response.model_dump(mode="json")
        self.usage.append(
            {
                "usage": raw.get("usage"),
                "status": raw.get("status"),
                "incomplete": raw.get("incomplete_details"),
                "reasoning": raw.get("reasoning"),
            }
        )
        return response


def page_text(pv: str, page: int) -> str:
    from pypdf import PdfReader

    cache = SCRATCH / f"text_{pv}.json"
    if cache.exists():
        return str(json.loads(cache.read_text())[page - 1])
    return PdfReader(str(doc_path(pv))).pages[page - 1].extract_text() or ""


def page_jpeg(
    pv: str, page: int, long_side: int, rotate: int = 0, crop: tuple[float, ...] | None = None
) -> tuple[bytes, tuple[int, int]]:
    pdf = pdfium.PdfDocument(str(doc_path(pv)))
    try:
        pg = pdf[page - 1]
        w, h = pg.get_size()
        img = pg.render(scale=long_side / max(w, h)).to_pil().convert("RGB")
        if crop:
            cw, ch = img.size
            img = img.crop(
                (int(cw * crop[0]), int(ch * crop[1]), int(cw * crop[2]), int(ch * crop[3]))
            )
        if rotate:
            img = img.rotate(-rotate, expand=True)  # positive = clockwise
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        return buf.getvalue(), img.size
    finally:
        pdf.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", required=True)
    ap.add_argument("--pages", default="all")
    ap.add_argument("--mode", choices=["image", "text", "both"], default="image")
    ap.add_argument("--long-side", type=int, default=1800)
    ap.add_argument("--effort", choices=["minimal", "low", "medium", "high"], default="low")
    ap.add_argument("--rotate", type=int, default=0, choices=[0, 90, 180, 270])
    ap.add_argument("--crop", default="", help="x0,y0,x1,y1 fractions of the rendered page")
    ap.add_argument("--extra", default="", help="diagnostic sentence appended to the prompt")
    ap.add_argument("--max-out", type=int, default=4096)
    ap.add_argument("--reserve", default="0.30")
    ap.add_argument("--limit-usd", default="3.00", help="stop before the next call beyond this")
    args = ap.parse_args()

    key = os.environ.get("MODEL_API_KEY", "")
    if not key.strip():
        print("MODEL_API_KEY missing")
        return 2
    settings = Settings(MODEL_API_KEY=key)
    assert settings.database_url is not None
    url = settings.database_url.get_secret_value()
    assert "fieldlens_task_042_completion_spike" in url, "lane database only"
    engine = create_engine(url)
    ledger = BudgetLedger(create_session_factory(engine))
    period = ledger.ensure_period(
        PERIOD, ledger_cap_usd=CAP, warn_usd=Decimal("2.40"), unattended_block_usd=CAP
    )
    try:
        ledger.confirm_balance(period, CAP, "TASK-042 owner allowance USD 3 (placeholder rates)")
    except errors.ReservationStateError:
        pass
    pricing = Pricing(REVISION, settings.meta_model, RATES["in"], RATES["out"])
    pricing_id = ledger.register_pricing(
        pricing, "MI-6 conservative placeholder, not provider rates"
    )

    real = openai.OpenAI(api_key=key, base_url=settings.meta_base_url, max_retries=0, timeout=90.0)
    cap_client = UsageCapture(real)
    provider = MetaProvider(settings, client=cap_client)
    limits = RequestLimits(
        max_output_tokens=args.max_out, max_reserved_usd=Decimal(args.reserve), retry_backoff_s=2.0
    )

    if args.pages == "all":
        pages = all_pages()
    else:
        pages = [(x.split(":")[0], int(x.split(":")[1])) for x in args.pages.split(",")]
    crop = tuple(float(x) for x in args.crop.split(",")) if args.crop else None
    out_dir = SCRATCH / "runs" / args.tag
    out_dir.mkdir(parents=True, exist_ok=True)
    modes = ["image", "text"] if args.mode == "both" else [args.mode]
    stamp = int(time.time())
    limit = Decimal(args.limit_usd)

    for pv, page in pages:
        assert pv in DOCS
        for mode in modes:
            if mode == "text" and not page_text(pv, page).strip():
                continue
            status = ledger.status(period)
            if status.committed_usd >= limit:
                print(f"STOP committed {status.committed_usd} >= {limit}")
                return 0
            rec: dict[str, Any] = {
                "pv": pv,
                "page": page,
                "mode": mode,
                "effort": args.effort,
                "long_side": args.long_side if mode == "image" else None,
                "rotate": args.rotate,
                "crop": args.crop or None,
            }
            parts: list[Any]
            if mode == "image":
                raw_img, size = page_jpeg(pv, page, args.long_side, args.rotate, crop)
                rec["image_px"] = size
                rec["image_bytes"] = len(raw_img)
                parts = [
                    TextPart(text=image_user_prompt() + args.extra),
                    ImagePart(
                        media_type="image/jpeg", data_base64=base64.b64encode(raw_img).decode()
                    ),
                ]
            else:
                txt = page_text(pv, page)
                rec["text_chars"] = len(txt)
                rec["extra"] = args.extra
                parts = [TextPart(text=text_user_prompt(txt) + args.extra)]
            n0 = len(cap_client.usage)
            began = time.monotonic()
            try:
                with WorkUnit(
                    provider=provider,
                    ledger=ledger,
                    period_id=period,
                    pricing_id=pricing_id,
                    pricing=pricing,
                    model=settings.meta_model,
                    request_key=f"spike042-{stamp}-{args.tag}-{pv}-{page}-{mode}",
                    work_unit=f"spike042-{args.tag}",
                    limits=limits,
                    effort=args.effort,
                ) as unit:
                    try:
                        resp = unit.step([Message(role="user", parts=tuple(parts))])
                        rec["outcome"] = "ok"
                        rec["text"] = resp.text()
                        rec["model"] = resp.model
                    except errors.AssistantError as exc:
                        rec["outcome"] = type(exc).__name__
                        rec["error_code"] = exc.code
                        rec["error"] = scrub(str(exc), [key])
                    rec["attempts"] = unit.attempts
                closed = unit.closed
                rec["committed_usd"] = str(closed.committed_usd) if closed else None
                rec["reservation_state"] = closed.state if closed else None
            except errors.AssistantError as exc:
                rec["outcome"] = "before_dispatch:" + type(exc).__name__
                rec["error"] = scrub(str(exc), [key])
            rec["elapsed_s"] = round(time.monotonic() - began, 2)
            rec["usage"] = cap_client.usage[n0:]
            (out_dir / f"{pv}_p{page:03d}_{mode}.json").write_text(json.dumps(rec, indent=1))
            u = (rec["usage"][-1]["usage"] or {}) if rec["usage"] else {}
            rt = (u.get("output_tokens_details") or {}).get("reasoning_tokens")
            print(
                f"{pv} p{page} {mode} {rec['outcome']} in={u.get('input_tokens')} "
                f"out={u.get('output_tokens')} reason={rt} t={rec['elapsed_s']}s "
                f"cost={rec.get('committed_usd')}"
            )
            sys.stdout.flush()
            if rec["outcome"].startswith("before_dispatch"):
                print("STOP", rec.get("error"))
                return 1
    final = ledger.status(period)
    print(f"period committed={final.committed_usd} available={final.available_usd}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

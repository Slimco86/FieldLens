"""Run one OCR engine over the evaluation pages (TASK-030 phase A; offline, experiment only).

One process = one engine = sequential pages, so ``ru_maxrss`` is that engine's peak. Results are
JSON files under ``.local/ocr/res/<tag>/<dpi>/``; existing files are skipped (resumable).
Boxes are stored as axis-aligned ``[x0, y0, x1, y1]`` in upright page-render pixels, mapped back
from each rotated pass.
"""

from __future__ import annotations

import argparse
import json
import os
import resource
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np  # type: ignore[import-not-found,unused-ignore]
from ocr_common import ALL_PAGES, SCRATCH, render
from PIL import Image, ImageOps  # type: ignore[import-not-found,unused-ignore]

Token = dict[str, Any]
Engine = Callable[[Image.Image], list[Token]]


def rss_mb() -> float:
    with open("/proc/self/statm") as f:
        return int(f.read().split()[1]) * os.sysconf("SC_PAGE_SIZE") / 1e6


def make_rox(variant: str) -> Engine:
    import rapidocr_onnxruntime as r  # type: ignore[import-not-found,unused-ignore]

    pkg = Path(r.__file__).parent
    cfg = (pkg / "config.yaml").read_text()
    if variant == "full":
        cfg = cfg.replace("max_side_len: 2000", "max_side_len: 4200")
        cfg = cfg.replace("limit_side_len: 736", "limit_side_len: 4200")
        cfg = cfg.replace("limit_type: min", "limit_type: max")
    for m in ("ch_PP-OCRv4_det_infer", "ch_ppocr_mobile_v2.0_cls_infer", "ch_PP-OCRv4_rec_infer"):
        cfg = cfg.replace(f"models/{m}.onnx", str(pkg / "models" / f"{m}.onnx"))
    cpath = SCRATCH / f"cfg_rox_{variant}.yaml"
    cpath.write_text(cfg)
    ocr = r.RapidOCR(config_path=str(cpath))

    def run(img: Image.Image) -> list[Token]:
        res, _ = ocr(np.array(img)[:, :, ::-1])
        out: list[Token] = []
        for box, text, score in res or []:
            xs = [p[0] for p in box]
            ys = [p[1] for p in box]
            out.append(
                {
                    "t": text,
                    "c": float(score) * 100,
                    "b": [float(min(xs)), float(min(ys)), float(max(xs)), float(max(ys))],
                }
            )
        return out

    return run


def make_rapid3(variant: str) -> Engine:
    from rapidocr import RapidOCR  # type: ignore[import-not-found,unused-ignore]

    params: dict[str, Any] = {}
    if variant.startswith("full"):
        params = {
            "Global.max_side_len": 4200,
            "Det.limit_side_len": 4200,
            "Det.limit_type": "max",
        }
    threads = int(os.environ.get("OCR_THREADS", "-1"))  # onnxruntime intra-op threads (-1 = all)
    if threads > 0:
        params["EngineConfig.onnxruntime.intra_op_num_threads"] = threads
        params["EngineConfig.onnxruntime.inter_op_num_threads"] = 1
    wb = variant.endswith("wb")  # defwb / fullwb: one token per word with its own box
    if wb:
        params["Global.return_word_box"] = True
    ocr = RapidOCR(params=params)

    def run(img: Image.Image) -> list[Token]:
        res = ocr(np.array(img)[:, :, ::-1])
        out: list[Token] = []
        if res.boxes is None:
            return out
        if wb and res.word_results:
            for line in res.word_results:
                for word, score, box in line:
                    xs = [p[0] for p in box]
                    ys = [p[1] for p in box]
                    out.append(
                        {
                            "t": word,
                            "c": float(score) * 100,
                            "b": [float(min(xs)), float(min(ys)), float(max(xs)), float(max(ys))],
                        }
                    )
            return out
        for box, text, score in zip(res.boxes, res.txts, res.scores, strict=True):
            xs = [p[0] for p in box]
            ys = [p[1] for p in box]
            out.append(
                {
                    "t": text,
                    "c": float(score) * 100,
                    "b": [float(min(xs)), float(min(ys)), float(max(xs)), float(max(ys))],
                }
            )
        return out

    return run


def make_tess(kind: str, psm: str, dpi: int) -> Engine:
    from tesserocr import OEM, PSM, RIL, PyTessBaseAPI, iterate_level  # type: ignore[import-not-found,unused-ignore]

    api = PyTessBaseAPI(
        path=str(SCRATCH / "tessdata" / kind),
        lang="eng",
        psm={"11": PSM.SPARSE_TEXT, "6": PSM.SINGLE_BLOCK, "12": PSM.SPARSE_TEXT_OSD}.get(
            psm, PSM.AUTO
        ),
        oem=OEM.LSTM_ONLY,
    )
    api.SetVariable("user_defined_dpi", str(dpi))

    def run(img: Image.Image) -> list[Token]:
        api.SetImage(img)
        api.Recognize()
        out: list[Token] = []
        it = api.GetIterator()
        for w in iterate_level(it, RIL.WORD):
            text = w.GetUTF8Text(RIL.WORD)
            bb = w.BoundingBox(RIL.WORD)
            if text and text.strip() and bb:
                out.append(
                    {
                        "t": text.strip(),
                        "c": float(w.Confidence(RIL.WORD)),
                        "b": [bb[0], bb[1], bb[2], bb[3]],
                    }
                )
        return out

    return run


def unrotate(box: list[float], angle: int, w: int, h: int) -> list[float]:
    """Map a box from the image rotated CCW by ``angle`` (PIL expand) back to the upright image."""
    x0, y0, x1, y1 = box
    if angle == 0:
        return [x0, y0, x1, y1]
    pts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    if angle == 90:  # rotated x' = y, y' = w - x
        mapped = [(w - py, px) for px, py in pts]
    elif angle == 270:  # rotated x' = h - y, y' = x
        mapped = [(py, h - px) for px, py in pts]
    else:  # 180
        mapped = [(w - px, h - py) for px, py in pts]
    xs = [m[0] for m in mapped]
    ys = [m[1] for m in mapped]
    return [min(xs), min(ys), max(xs), max(ys)]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", required=True, help="rox|rapid3|tessbest|tessfast")
    ap.add_argument("--variant", default="def", help="rapidocr: def|full; tesseract: psm 3|11")
    ap.add_argument("--dpis", default="200")
    ap.add_argument("--angles", default="0")
    ap.add_argument("--prep", default="raw", help="raw|gray")
    ap.add_argument("--pages", default="all", help="all or PV-17:36,PV-21:49")
    ap.add_argument("--tag", required=True)
    a = ap.parse_args()
    pages = (
        ALL_PAGES
        if a.pages == "all"
        else [(p.split(":")[0], int(p.split(":")[1])) for p in a.pages.split(",")]
    )
    angles = [int(x) for x in a.angles.split(",")]
    meta_path = SCRATCH / "res" / a.tag / "meta.jsonl"
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    for dpi in [int(x) for x in a.dpis.split(",")]:
        t0 = time.time()
        if a.engine == "rox":
            eng = make_rox(a.variant)
        elif a.engine == "rapid3":
            eng = make_rapid3(a.variant)
        elif a.engine == "tessbest":
            eng = make_tess("best", a.variant, dpi)
        else:
            eng = make_tess("fast", a.variant, dpi)
        init_s = time.time() - t0
        for pv, page in pages:
            for ang in angles:
                out = SCRATCH / "res" / a.tag / str(dpi) / f"{pv}_p{page:03d}_a{ang}.json"
                if out.exists():
                    continue
                out.parent.mkdir(parents=True, exist_ok=True)
                img = render(pv, page, dpi)
                w, h = img.size
                if a.prep == "gray":
                    img = ImageOps.autocontrast(ImageOps.grayscale(img), cutoff=1).convert("RGB")
                rimg = img.rotate(ang, expand=True) if ang else img
                t1 = time.time()
                toks = eng(rimg)
                el = time.time() - t1
                for t in toks:
                    t["b"] = [round(v, 1) for v in unrotate(t["b"], ang, w, h)]
                    t["a"] = ang
                rec = {
                    "tag": a.tag,
                    "engine": a.engine,
                    "variant": a.variant,
                    "prep": a.prep,
                    "pv": pv,
                    "page": page,
                    "dpi": dpi,
                    "angle": ang,
                    "size": [w, h],
                    "elapsed_s": round(el, 2),
                    "rss_mb": round(rss_mb(), 0),
                    "n_tokens": len(toks),
                    "tokens": toks,
                }
                out.write_text(json.dumps(rec))
                print(
                    f"{a.tag} {dpi} {pv}:{page} a{ang} {el:.1f}s tokens={len(toks)} rss={rss_mb():.0f}MB",
                    flush=True,
                )
        with meta_path.open("a") as f:
            f.write(
                json.dumps(
                    {
                        "dpi": dpi,
                        "init_s": round(init_s, 2),
                        "maxrss_mb": round(
                            resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
                        ),
                    }
                )
                + "\n"
            )


if __name__ == "__main__":
    main()

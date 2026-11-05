# TASK-030 phase A: offline OCR, rendering and orientation evaluation for scanned completion pages

> **Note (0.56.2):** the one-off `scripts/spikes/` evaluation scripts were removed from the tree for the final submission; they remain in git history at commit `fc5e966` (`git show fc5e966:scripts/spikes/<file>`).

Date: 2026-10-31 (branch `feature/task-030-ocr-evaluation`, base 1f5e1a1, version 0.16.2, Alembic head 0006).
Class: **offline measurement only**. No provider/Meta call, no spend, no database, no migration, no contract or
lockfile change. Every accuracy figure is measured against the TASK-042 **agent-read** reference
(`scripts/eval/spike042_gold.py`), which is **not human verified** and not exhaustive; a few figures use a
native text layer as exact ground truth and say so. Evaluation set: 11 pages (8 reference pages: PV-17 p.4, 29,
30, 35, 36, PV-21 p.48, 49, PV-12 p.164; 3 pages without equipment: PV-21 p.13, 50, PV-17 p.48), 67 reference numbers.
**Selection caveat (QA finding F1):** the best configuration per engine was picked from about a dozen configurations scored on the same 67 numbers, so the best figure is optimistic (tuning data equal test data). The honest RapidOCR 3 range at 300 dpi is **63 to 66 of 67 (94 to 99%)** across raw/gray, line/word-box and pass choices; 99% appears only with gray plus a 270-degree pass. Scripts also read the local text layers and images of PV-11..14 (F-12 COMPLETION_REPORT_1/2/3, COMPLETION_LOG_MD_PLOT_2, including PV-12 p.164 and text-layer ground truth) as well as PV-17, PV-18 and PV-21, all within the seven owner-approved files, local read-only. This is a small sample: differences of one or two tokens (about 1.5 to 3 points) are noise. Nothing here
claims coverage of the other roughly 100 scanned pages of the two documents (I viewed only p.36 and p.49).
Scripts: `scripts/spikes/ocr_*.py` (spike only, not product code). Page renders, OCR dumps, model files and
downloads stay in gitignored `.local/ocr/`. Quotes are short.

## 1. Recommendation (summary)

| Question | Recommendation | Evidence |
|---|---|---|
| OCR engine | **RapidOCR 3.x (`rapidocr` + `onnxruntime`, PP-OCRv6 small det/rec, PP-OCRv4 mobile cls ONNX), default detector settings; line mode for text, word-box mode only where a token locator is needed** | **63 to 66 of 67 (94 to 99%)** at 300 dpi, best config selected on the test set. Line mode: raw pass 0 64, gray pass 0 63, gray 0+270 66. **Word-box mode (needed for token boxes): 63 pass 0, 62 with 0+270**, i.e. about 3 to 4 points below the best line-mode figure. About 1.0 GB peak RSS; deterministic |
| Fallback / second reader | **Tesseract 5.5.3 via the `tesserocr` manylinux wheel + `tessdata_fast` eng**, PSM 11, 300 dpi, two passes | 54 of 67 (81%); 0.38 GB RSS; 2.6 s/page; word-level boxes; 34 MB install. Fits the 1.5 GB bound with large margin; weaker on tiny annotation text and tables |
| Rendering | **pypdfium2 at 300 dpi (equals the native scan resolution), page /Rotate applied by pdfium, grayscale + autocontrast before OCR** | all scanned pages are 3507x2480 24-bit JPEG at 299.9 dpi inside a page marked `/Rotate 270`; render 0.1 to 0.4 s; deterministic |
| Orientation | pass 0 always; **additional 90/270 passes on pages flagged by tall-box count** | only p.36 (rotated schematic) needs it; tesseract 61% to 81% with a 270 pass, RapidOCR 12 of 13 to 13 of 13 on p.36 |
| Agreement rule ("OCR token must agree") | **workable with locality, but not as a page-level set test** | 95% of model-read numbers confirmed on the scanned set; all adjudicable real misreads rejected; short integers are weakly protected (section 5) |
| Legacy Word `.doc` | **include in phase B**, native text + embedded pictures first, OCR for the pictures | OLE parsed safely: 67.6k chars of native text, 12 embedded pictures (section 6) |

I excluded torch-based engines (EasyOCR, docTR, surya, Docling's default stack): `docling-slim[standard]` pulls
`docling-ibm-models`, which requires `torch`/`torchvision` (read from the wheel metadata); EasyOCR also requires torch.
That is a multi-GB install against a 7 GB shared host and a locked resource budget, and nothing measured here
needs it. Docling with an onnxruntime-only model extra exists but was not evaluated (no sample need). PaddleOCR
itself needs `paddlepaddle` (not evaluated, same reason).

## 2. Engines: licenses, footprint, download, speed, memory

All speeds are wall seconds per page on this WSL host (20 cores, other jobs running), one process at a time.

| Engine (version) | Library license | Model license | Install (venv, incl. numpy/pillow) | Model source | Notes |
|---|---|---|---|---|---|
| `rapidocr` 3.10.0 + `onnxruntime` 1.31.1 | Apache-2.0 | Apache-2.0 (PaddleOCR-derived; `MODEL_LICENSES.md` shipped in the wheel) | 343 MB (about 260 MB over pypdfium2+pillow+numpy) | **bundled in the wheel** (no separate download): `PP-OCRv6_det_small.onnx` sha256 `090f04ab...f94f`, `PP-OCRv6_rec_small.onnx` `6f327246...4884`, `ch_ppocr_mobile_v2.0_cls_mobile.onnx` `e47acedf...215c`; wheel sha256 `2fc34e26...c4ca` | needs `opencv-python-headless`, shapely, pyclipper, omegaconf, requests; the library can download other models if configured, so phase B must pin and disable downloads |
| `rapidocr-onnxruntime` 1.4.4 (legacy) | Apache-2.0 | upstream PaddleOCR Apache-2.0; the 1.4.4 wheel ships no model notice (not independently verified) | 359 MB | bundled PP-OCRv4 det/rec; wheel sha256 `971d7d5f...782cbf` | requires non-headless `opencv-python`; last release of that package line |
| Tesseract 5.5.3 via `tesserocr` 2.12.0 manylinux wheel | tesserocr MIT; Tesseract Apache-2.0; leptonica BSD-2 (bundled in wheel `.libs`) | `tessdata_fast`/`tessdata_best` eng: Apache-2.0 (repo license API: Apache-2.0) | 34 MB wheel stack (+4.1 MB fast / 15.4 MB best eng, 10.6 MB osd) | **explicit download**: `raw.githubusercontent.com/tesseract-ocr/tessdata_fast/87416418657359cb625c412a48b6e1d6d41c29bd/eng.traineddata` sha256 `7d4322bd...70b2`; best at commit `e12c65a9...0cec` sha256 `8280aed0...66ba`; `osd.traineddata` `9cf5d576...00ff`; into gitignored `.local/ocr/tessdata/` | no sudo/apt needed: the wheel bundles libtesseract + leptonica; tessdata is the only download |
| pypdfium2 5.14.0 | BSD-3-Clause and Apache-2.0 (PDFium); bundled third-party license files in the wheel (freetype, libjpeg-turbo, libpng, zlib, ICU, lcms, openjpeg, abseil, simdutf, ...) | n/a | 3.8 MB wheel | PyPI | confirmed from `METADATA`/`licenses/` |
| Pillow 13.0.0 | `MIT-CMU` (HPND-style; `License-Expression` in METADATA) | n/a | 7.1 MB wheel | PyPI | not "BSD/HPND" by SPDX name: it is MIT-CMU |
| olefile 0.47 | BSD (METADATA says `BSD`; upstream states BSD-2-Clause) | n/a | small | PyPI | used only for the `.doc` structure check |

Neither `pypdfium2`, `pillow`, `rapidocr`, `onnxruntime`, `tesserocr` nor `olefile` is in `uv.lock` today (only `pypdf` and
`numpy` are), so phase B adds new dependencies (`olefile`, `pypdfium2`, `pillow`, `rapidocr`, `onnxruntime`) and a lockfile change by one writer after owner approval. Per the orchestrator decision RapidOCR is the only engine; `tesserocr`/Tesseract is evaluation-only and not adopted.

**Third-party notices to record (QA finding F5; acceptable for a local demo, not yet a redistribution review):** the `tesserocr` wheel bundles `libjbig` (GPL-2.0-or-later) plus libtiff, libwebp, libpng, libjpeg and leptonica without notices (another reason it is evaluation-only); `opencv-python-headless` (required by `rapidocr`) bundles FFmpeg (LGPL) and OpenSSL 1.1.1k (end of life).

Speed, memory and determinism on the 11-page set (peak RSS is the process `ru_maxrss`, cumulative over the dpi
loop of that process; `time` includes render):

| Config | Time per page | Peak RSS | Note |
|---|---|---|---|
| RapidOCR 3 default, 300 dpi, one pass, all cores | 3.5 s wall (4.5 s with word boxes) | 1.07 GB | CPU time is large (the word-box run used 17 CPU-minutes for 22 passes): cap threads |
| same, `OCR_THREADS=4` / `2` (onnxruntime intra-op), word boxes, p.36/49/29 | 3.7 to 5.5 / 5.9 to 7.9 s | 0.97 / 0.99 GB (three pages, including render) | tokens identical to the all-core run |
| RapidOCR 3 with `max_side_len=4200` (no detector downsizing) | 6 to 10 s one pass | **2.35 GB** | rejected (over the 1.5 GB bound) |
| rapidocr-onnxruntime 1.4.4 default / full | 3.8 / 5.5 to 6.8 s | 0.9 to 1.15 GB | |
| Tesseract fast PSM 11, 300 dpi, one / two passes, 1 thread | 1.65 / 2.6 s | 0.38 GB | `OMP_THREAD_LIMIT=1` |
| Tesseract best PSM 11, 300 dpi, two passes | 4.9 s | 0.39 GB | not better than fast on this set |
| pdfium render, 150 / 200 / 300 dpi | 0.12 to 0.23 / 0.13 to 0.36 / 0.24 to 0.44 s | 0.18 GB | PNG 1.5 to 7.2 MB per page at 150 to 300 dpi |

Determinism: re-running Tesseract on p.36 and p.49 gave byte-identical token lists (text, boxes, confidence);
RapidOCR gave identical tokens at 2 threads, 4 threads and all cores; pdfium rendering is deterministic (identical
hash over two renders of the same page in one process, confirmed in two separate runs; not compared across processes). Not tested across hosts or library versions.

Capacity estimate (measured per-page, not run on the whole documents): F-14 (60 pages) plus F-5 (50 pages) is
about 110 pages, so about 7 to 14 minutes for RapidOCR with 2 to 4 threads and one pass (4 to 8 s per page), about 3
minutes for Tesseract two-pass. The speed varies with text density (470 words on p.29).

## 3. Accuracy against the agent-read reference

Metric definitions (`ocr_score.py`): a reference number is a **hit** when a normalized OCR numeric token equals
it (decimals by value, so `196.800` equals `196.8`; fractions as text; trailing units and `#` stripped). Reference
keys that are only the integer prefix of a longer reference number (`2615` for `2615.4`) are dropped as gold
artifacts (67 numbers after that fix). **Near miss** = a missed number for which OCR has a same-length token one
character away (a digit misread). **Extra** = distinct numeric tokens that are not in the reference; the reference is
not exhaustive (it lists equipment items, not every printed number), so extras are an upper bound on false numeric
tokens, not a false-token rate (about 300 distinct extras per 8 reference pages for every engine). **CER proxy** =
sum over reference numbers of the minimum edit distance to any OCR numeric token divided by reference characters
(optimistic; no free-text ground truth exists for the as-installed table). Classes: decimal (38), fraction (2),
integer of 3 or more digits (24), short integer (3).

Best configuration per engine, 300 dpi unless stated, confidence filter 0 (all tokens):

| Config | Numbers | decimal / fraction / int>=3 / int<3 | Words (30) | Near misses | CER proxy | Time per page |
|---|---|---|---|---|---|---|
| RapidOCR 3 default, gray+autocontrast, passes 0+270 | **66/67 (99%)** | 38/38, 2/2, 23/24, 3/3 | 30 | 1 | 1/319 (0.3%) | 7.1 s (3.6 s one pass) |
| RapidOCR 3 default, raw, pass 0 only | 64/67 (96%) | 37/38, 2/2, 22/24, 3/3 | 30 | 1 | 6/319 (1.9%) | 3.5 s |
| RapidOCR 3 default, raw, 200 dpi, pass 0 | 61/67 (91%) | 36/38, 2/2, 20/24, 3/3 | 30 | 2 | 12/319 | 3.6 s |
| RapidOCR 3 full-resolution detector, 300 dpi, 0+270 | 66/67 (99%) | 38/38, 2/2, 23/24, 3/3 | 30 | 1 | 1/319 | 20 s, 2.35 GB |
| rapidocr-onnxruntime 1.4.4 default, 200 dpi, pass 0 | 60/67 (90%) | 36/38, 2/2, 20/24, 2/3 | 27 | 1 | 13/319 | 3.8 s |
| Tesseract fast PSM 11, 300 dpi, passes 0+270 | 54/67 (81%) | 32/38, 1/2, 18/24, 3/3 | 30 | 7 | 18/319 (5.6%) | 2.6 s |
| Tesseract fast PSM 11, 300 dpi, pass 0 only | 41/67 (61%) | 29/38, 1/2, 10/24, 1/3 | 18 | 8 | 53/319 | 1.65 s |
| Tesseract best PSM 3, 300 dpi, 0+270 | 48/67 (72%) | 32/38, 0/2, 13/24, 3/3 | 30 | 6 | 31/319 | 7.0 s |
| Tesseract fast PSM 11, 150 dpi, 0+270 | 45/67 (67%) | 31/38, 0/2, 11/24, 3/3 | 28 | 3 | 42/319 | 1.3 s |

Findings:

* **Engine.** PP-OCRv6 small (RapidOCR 3) is clearly better than Tesseract on these pages and than the older
  PP-OCRv4 package, mainly on small table and annotation text. On PV-21 p.49 (the F-5 as-installed table plus
  small schematic annotations) RapidOCR 3 found 38 of 39 reference numbers in the raw default run and in gray alone (39 of 39 only with gray plus a 270-degree pass, which is meaningless for an upright page and is not a headline), including the tiny
  `Perf 3605.000-3608.000` lines; Tesseract 27 to 29 of 39 or 40 (digit errors in those perforation lines); PP-OCRv4 34 to 35 of 40.
* **Resolution.** 300 dpi is better than 200 for every engine and 150 is clearly worse for Tesseract
  (67% versus 81% with two passes). The scans are natively 299.9 dpi, so 300 dpi loses nothing and higher dpi adds
  nothing. RapidOCR's default pre-processing resizes the long side to 2000 px (about 170 dpi) for detection, so
  its dpi sensitivity is smaller (91% to 96%); I believe recognition crops are taken from the full-resolution image
  (not verified in the code), which would explain why 300 still beats 200.
* **Preprocessing.** Grayscale + autocontrast (cutoff 1) gave +1 to +2 reference numbers for RapidOCR (64 to 66 with
  the second pass) and +/-1 for Tesseract: within noise. Recommended because it is cheap, not because it is proven.
  No binarization or deskew was tried.
* **Confidence filter.** RapidOCR scores are saturated (about 96 to 100), so a 60% filter changes nothing; for Tesseract
  a 60% filter lowers recall (81% to 72%) and shows that its confidence is not a usable acceptance signal.
* **Where OCR fails** (RapidOCR 3 best config): the only miss is `4539` on PV-12 p.164 (an F-12 page whose picture is a
  609x876 embedded image at 119 dpi; a digit misread, and the page also has a 266-character partial text layer);
  one reference key (`9.625` on p.49, raw run) fixed by the gray run. Tesseract fails mostly on the tiny
  annotation text beside the p.49 schematic (`3605, 3608, 3622, 3670, 3682` are digit misreads) and on
  fractions (`6-3/8`, `13-5/8`). Not measured: handwriting, stamps, skewed or crumpled pages: none of the 11 pages is
  handwritten (I viewed two of them; the others only through counts), so this is **not tested, not "none occur"**.
  Show-through of the reverse side (visible as faint ghost text on p.36 and p.49) did not appear as obvious false tokens
  in the p.36 overlay, but a false-token rate was not measured.
* **Tables and schematics.** OCR returns words/lines with boxes, not cells. On p.49 the table cells come out as separate
  boxes (one number each), so a row/column reconstruction by y/x clustering is feasible but is phase B work to build and test
  (nothing here measures table-structure accuracy). On schematics OCR reads the labels (p.36: 13 of 13 numbers) but does not
  connect a label to the drawn component; that stays a model/validation task.
* **Orientation.** Every scanned page is stored as a 3507x2480 image in a page marked `/Rotate 270`; pdfium applies the flag, so
  renders are upright. Without it OCR would see every page sideways: use the pdfium render (or rotate the native image by
  the flag). The content-level rotation on p.36 (labels read bottom-to-top) is the hard case. Plain pass only: Tesseract
  recall 61% overall, RapidOCR 12 of 13 on p.36 (misses `2041`) because it rotates tall crops by itself; adding a pass of
  the image rotated by 270 degrees (PIL `rotate(270)`, i.e. clockwise) gives 13 of 13 on p.36 for both engines and
  raises Tesseract overall from 61% to 81%. A 90-degree pass added nothing measurable on this set (Tesseract +0, RapidOCR -1,
  noise) but costs a third pass; keep it only for flagged pages because the opposite rotation can occur on pages I did not see.
  Neither engine's page-level angle classifier is what handles p.36: RapidOCR's classifier is a 0/180 text-line classifier;
  Tesseract OSD is page-level and the page is upright overall, so I did not use OSD.
* **Boxes.** Both engines return a box per token (Tesseract per word; RapidOCR per line, per word with
  `return_word_box`). Visual check of p.36 (overlay in `.local/ocr/ov36.png`, not committed): word boxes sit on the rotated
  labels; for rotated text a box can end one or two characters early (`MD/1603.5` of `MD/1603.501m`), so evidence rectangles
  should be padded. Crop re-read test (`ocr_bbox.py`, self-consistency only): Tesseract word boxes re-read the number from the
  crop in 49 of 54 cases (91%); RapidOCR word boxes 51 of 62 (82%), where several failures are tiny crops (42x48 px) or
  vertical text re-read without the rotation the engine had applied, i.e. a limit of the test as much as of the box.
  Interpolating a token box inside a RapidOCR line box by character offsets is poor (17 of 38): use word boxes, never interpolation.

## 4. Rendering decision

* **Native image versus re-render.** The embedded scan is a `DCTDecode` (JPEG) 3507x2480 RGB image (0.09 s to decode via
  pypdfium2). Rendering the page at 300 dpi gives 2480x3509 upright pixels with the `/Rotate 270` applied; the rotated native
  image is the same content. Use the 300 dpi pdfium render: it also works for pages that mix text and image, it applies
  the rotation flag, and the box coordinates are in the same space PDF.js uses once the viewer applies the page rotation.
* **Hybrid pages exist.** PV-12 p.164 has 266 characters of text layer plus a 609x876 image: a per-page decision (text layer
  coverage, image coverage) is needed, not a per-document one.
* **Derived data.** Renders are deterministic and cheap (0.1 to 0.4 s), so do not store them durably; regenerate on demand
  (the evidence viewer should use PDF.js on the original, not the render).

## 5. The agreement rule (offline, no provider call)

Inputs: the saved TASK-042 model outputs (read-only, 21 image-mode run files on these pages, several with zero candidates: effort `minimal`/`low`,
1000 to 2400 px, plain and rotated), OCR from RapidOCR 3 default 300 dpi pass 0 (the simplest recommended
configuration). A model-read value is a numeric string from the candidate fields `od`, `id`, `length`, `depth.value` ("structured")
or numbers inside the candidate `name`/`quote`/`ident` ("descriptive"), unique per run file. Normalization as above.
**Sample is small and not independent (QA finding F3): the unconfirmed misreads are per-run instances of about 5 distinct values (`1386.79`, `2816`, `28`, `1367.06`, `631`); only 3 instances are gold-adjudicated structured misreads; four unconfirmed values were not judged; the gold is agent-read (partly circular). The only independent ground truth is the native-text set in 5.3.**

**5.1 Scanned pages with the agent-read reference** (`ocr_agree.py`; 178 structured + 100 descriptive values):

| Outcome | Structured | Descriptive |
|---|---|---|
| Confirmed by OCR (accepted) | 170 (96%) | 95 (95%) |
| Not confirmed, value is a reference number (false reject: OCR missed or misread) | 2 | 0 |
| Not confirmed, a reference number three or more digits long is one digit away (model misread, correctly rejected) | 3 (`1386.79`, `2816` twice) | 0 |
| Not confirmed, not a reference number (adjudicated where possible) | 3 | 5 |
| Confirmed but a known misread (false accept) | 0 | 0 |

The 8 unconfirmed non-reference values: `1367.06` (OCR has `1367.09`; the printed range end is 1367.090), `631` (OCR has
`831`; the page prints `(Size 831 x 600)`), `28` twice (OCR has `29`; the page prints `29#`) are model misreads
correctly rejected; `4.5` twice, `8.31` and `3896` have no OCR neighbor and were not adjudicated (likely
the model composing a value from `MMRG-4-5`/`831`; not verified). An earlier tesseract-based run also showed a false
reject class: `1367.09` (correct) not confirmed because Tesseract read `1367.08`.
So on the scanned set the rule accepted 95% of values and rejected the misreads that could be adjudicated (7 per-run instances of about 5 distinct values; 3 gold-adjudicated); four values (`4.5` twice, `8.31`, `3896`) were not judged, so "no false accepts" means none among the judged values only. Measured false-reject cost: 2 of 87 reference-number reads (2%) with RapidOCR; Tesseract 5 of 87 structured plus 1 descriptive.

**5.2 Coincidental confirmation (why page-level matching is not enough).** For every reference number, I generated
all one-digit substitutions that are not themselves reference numbers and counted how often such a *wrong* value occurs among the
page's OCR tokens (`ocr_agree.py`, RapidOCR): decimals 1 of 1516 (0.07%), integers of 3 or more digits 1 of 800 (0.12%),
fractions 0 of 61, **short integers 7 of 51 (13.7%)**. A page-level "token exists somewhere" test therefore protects
decimals and depths well but not 1 or 2 digit values (weights, sizes, quantities): require the OCR token to lie in
the same OCR line/row/cell or in the cited rectangle, which the box locators make possible (not measured here).

**5.3 Native text-layer ground truth** (`ocr_agree_native.py`): 10 pages with both a native text layer and a saved model
image read (PV-11 p.136, PV-12 p.17/39, PV-13 p.4/14/17/18/19/58, PV-14 p.1; clean digital pages rendered at 300 dpi, so OCR
recall here is an upper bound for scans). Truth = numbers in the text layer. OCR recall of the native numbers: RapidOCR 357 of
369 (97%; fractions 22 of 25), Tesseract 354 of 369 (96%; short integers 164 of 170, int>=3 110 of 117). 115 model values:

| | RapidOCR 3 | Tesseract fast PSM 11 |
|---|---|---|
| in native text and confirmed | 105 | 94 |
| in native text but OCR missed (false reject) | 3 (fraction fragments `5/8`, `3/4`: a normalization gap, see below) | 14 (e.g. `29`, `114`, `3100`, `1327`, `2780`, `53.5` on the busy PV-13 p.58) |
| not in native text and rejected | 6 (the documented misreads `8-3/8` twice, `55.7`; 3 are parse artifacts: `1358/1327`, `3/4` twice) | 5 |
| not in native text but confirmed (false accept) | 1 (`34`; it is not in the native text, so it is probably an OCR-produced `34`, e.g. from `3/4`, not a coincidence with a printed number) | 2 (`34`, `1358/1327` artifact) |

The two misreads the spike reported on text-layer pages (`6-3/8` as `8-3/8`, `65.7` as `55.7`) are both rejected by the OCR
agreement rule with either engine; the one false accept is a two-digit integer; its cause is probably OCR splitting `3/4`, which still shows short integers are the weak spot. Total independent misreads here: 8 value instances (including parse artifacts).

**5.4 Cost of the rule and conclusions.**
* Accepted fraction is about 95% on the scanned set and 91% (105 of 115) on clean text pages, or 94% once mixed fractions
  such as `10 3/4` are normalized as one token (see decisions: fraction policy). Roughly one model value in 20 needs a
  visible disagreement record, not silent acceptance.
* False rejects are almost all OCR misses on small or busy print; with RapidOCR they were 2 of 87 and 3 of 108 supported values.
* False accepts occur through short integers; require same-line/cell locality and, for short integers, a nearby label.
* Both readers can agree on a wrong value (shared misread); 0 such cases among judged values here, but the sample (3 real
  misreads on scans) cannot bound that rate. The rule is a strong filter for digit misreads, not proof of correctness.
* Because disagreements are real signals (the model misreads small digits, OCR misreads tiny digits), unconfirmed numeric
  values must become visible `ocr_disagreement` findings with both values and both locators, not silently dropped and not
  silently resolved.

## 6. Legacy Word `15_9_F_5_FWR_Completion.doc` (structure only, no model, no conversion tool)

`ocr_doc_inspect.py` (olefile + bounded `struct` parsing; no execution, no macro source read, no conversion):

* OLE2 compound file, 2.65 MB, creator "Microsoft Office Word", company Statoil, Word 97+ binary format, **not encrypted**.
  Summary information says 48 pages and about 10,000 words (declared, not verified).
* Streams: `WordDocument` 353 KB, `1Table` 28 KB, `Data` 2.18 MB, plus a `Macros/VBA` storage (**VBA macros are present**,
  `ThisDocument` 33 KB). Macros are never executed or read; the profile should record "contains macros" as a finding and the
  existing upload inspector already classifies OLE as `ole`/`pending_extraction`.
* **Native text is extractable** without a conversion tool: FIB to the piece table (CLX) gives 67,574 characters, with 3,395
  table-cell marks (real Word tables) and 100 picture-anchor characters. Keyword counts: tubing 27, packer 16, casing 48, liner
  40, perforat 14, pump 28, hanger 31, schematic 8, mandrel 0. It is the F-5 *Final Well Report: Completion* narrative (same
  template as the F-14 PDF), not the as-installed table: only 7 of the 39 PV-21 p.49 reference numbers occur in its text.
* **Embedded pictures** (scan of the Data stream for the PICF/OfficeArt records): 12 records: 9 PNG, 1 JPEG, 2 EMF (vector
  metafiles with a verified EMF signature; sizes 103 and 123 KB). Raster sizes: 1193x895 (1.4 MB), 611x553, 573x723, 928x721,
  1111x766, 960x720 (JPEG), 1620x682, and three 164x28 (logos). OCR of the raster pictures (RapidOCR, counts only, no text kept):
  pic03 (928x721, 28 tokens, 4 hits against the combined p.48/p.49 reference numbers, keywords tubing/packer/liner/hanger/valve) and **pic08 (1620x682, 210 tokens,
  124 numeric tokens, 12 hits against the combined PV-21 p.48/p.49 reference numbers (mixed, mostly numbers shared with the narrative, so not evidence that this is the as-installed table), keywords tubing x4, packer, hanger, valve)** are plausibly completion
  schematics or tables (unverified); pic00 (1.4 MB) yielded no text (a photo or text-free drawing). The two EMF records can carry text
  records (`EMR_EXTTEXTOUTW`) that a bounded EMF reader could extract without rendering; not evaluated.
* **Safety.** No unsafe parser was needed: bounded `struct` reads, length checks against stream size, depth-limited OfficeArt
  walk, bounded zlib decompression (1 MB) for EMF header verification only. Remaining risks for phase B: a hostile `.doc` with a forged piece
  table (bounds are checked but fuzzing was not done), huge picture records (cap sizes), JPEG/PNG decoding by Pillow
  (cap pixels, e.g. 50 Mpx; Pillow's default decompression-bomb guard is 89 Mpx), and macros (never run).
* **Recommendation.** Include in phase B as two sub-profiles: (a) native text + table cell marks with line/paragraph locators
  (OLE profile, no OCR); (b) embedded raster pictures extracted with their hash and index (the existing `EmbeddedImageLocator`
  has `container_item_index`, `image_sha256`, `region`) and OCR'd with the same engine. The two EMF records are a decision (skip, or
  a small bounded text-record reader). Other `.doc` files (Drilling_programme, Recommendation_to_Drill, FWR_Drilling) were not
  examined; they are drilling-side and outside the completion target.
* Caveat: `olefile` is BSD-licensed and not in the lockfile; the format parsing code I wrote is about 230 lines and untested beyond this file.

## 7. Phase B design (not implemented)

### 7.1 Profile interface
Add `ScannedPdfProfile` (`name="scanned_pdf_ocr"`, `families=("pdf",)`) and `WordOleProfile` (`families=("ole",)`) to
`backend/fieldlens/profiles/registry.py`. `detect()` must stay content-based and cheap (pypdf/pdfium page text and image coverage,
no OCR); `SurveyReportProfile` (text PDFs) and the scanned profile must be mutually exclusive per page, and a hybrid
document yields per-page decisions (PV-12 p.164 case). `parse()` is synchronous today and returns one `ProfileOutput`; a
110-page OCR run (7 to 14 minutes) is one blocking call. Correction after QA: the runner **already has a heartbeat thread** (`_process`/`beat`), so lease renewal during a long parse exists. The real gaps are (1) cancellation (the `lost` event is not passed to profiles) and (2) per-page commit and resume: `_execute` calls `profile.parse` once and `_finalize_ok` writes one `ProfileOutput`, so partial resume needs persisted intermediate state (the migration 0008 artifact table plus run-state semantics for a resumable run). Proposal: the profile does the per-page work through a small `OcrPageSource` interface and receives the cancel event; each finished page is committed (artifact + row) before the next. This is a runner extension (one writer), and it is larger than a callback.
Profile `version` includes nothing about the engine; the **engine fingerprint** (engine, version, model hashes, render dpi,
preprocess, passes, thresholds) is separate and recorded per page; changing it invalidates only OCR artifacts and their
derived records, in line with the existing "version bump supersedes the run" rule.

### 7.2 Records and locators
* Records: one `ocr_page` record per processed page (page number, token/line counts, mean confidence, orientation passes
  used, quality state) and, for the selected equipment pages, row/table candidates; **not one record per token** (about 60 to
  470 words per page, tens of thousands per document). Tokens live in the per-page OCR artifact.
* **No shared-contract change is needed for token locators, but there are two other contract points (below).** `PdfLocator` already has `page` and a normalized `rect`
  (`[x0,y0,x1,y1]`, top-left origin). `NormalizedRect` requires 0<=v<=1 and x0<x1, so padding must be clamped to the page. Rect-space convention: OCR boxes are in the **pdfium-rotated (displayed) page space**, whereas existing text-PDF locators may use the unrotated page space; the convention must be stated per locator source, and a **viewer test on a `/Rotate 270` page is required** before acceptance. Pad rectangles by about 2 to 3 px at 300 dpi for rotated text (clamped). The profile `Attr.locator` is a free `dict`, so the profile can emit
  `{"kind":"pdf","page":36,"rect":[...]}` today. Add to the claim's evidence list a second link, `ConvertedTextLocator`
  (`artifact_id`, `artifact_sha256`, `extractor_version`, `line_start`, `line_end`), pointing at the OCR text artifact line, which
  also records the engine fingerprint via `extractor_version`. Engine, confidence and pass angle go into the record/attr
  detail JSON, not the locator.
* **Contract change A (required if findings are first-class): `ocr_disagreement` is not an `IssueCode` in `contracts/quality.py`.** A new code means a contract change plus OpenAPI/`generated.ts` regeneration by a single writer after TASK-011 merges; alternatively reuse an existing code (for example `SUSPICIOUS_VALUE`) with a detail field until then.
* **Contract point B (orchestrator decision, no enum change): `EvidenceClass` has only `source_record`, `catalog_derived`, `derived`, `interpolated`, `generic`.** OCR-derived text and claims use `source_record` with extraction method `ocr` and the engine/version fingerprint in the locator/method fields; validation state is kept separate. Retrieval chunks use a chunk-level `ocr_text` label that is not an `EvidenceClass`.
* Optional additive contract change if the owner wants a self-contained OCR locator: `PdfLocator.ocr_artifact_id`
  and `token_index` (both optional, additive; OpenAPI regeneration; **single writer**; TASK-011 currently owns migration 0007 and
  the contract registry, so serialize after it merges). I do not recommend it for phase B.
* `.doc` pictures use the existing `EmbeddedImageLocator` plus the same artifact link. `.doc` native text needs a text/
  paragraph locator: `TextLocator` (lines) can address converted paragraphs only if a converted-text artifact is stored;
  decision below.

### 7.3 Storage of OCR artifacts and renders
* OCR output is derived data: one gzip JSON per page under a project-scoped derived area, e.g.
  `projects/<project>/derived/ocr/<content_sha256>/<engine_fingerprint>/p0036.json.gz` (about 30 to 150 KB per page),
  holding tokens (text, normalized value, box in pixels and normalized, confidence, pass angle), reading-order lines, page
  quality metrics. Render PNGs are not stored (regenerated in 0.1 to 0.4 s).
* Index/ownership: migration **0008** (after TASK-011's 0007) adding `ocr_artifact(artifact_id, project_id, document_id,
  source_revision_id, page, engine_fingerprint, sha256, status, quality jsonb, created_at)` with the existing
  project/document FK scope; this is the "derived copies" table the TASK-039 removal hook (IN-9) enumerates to delete
  files and rows with the document, and the cache key is (source_revision_id, page, engine_fingerprint), so a revised source or a changed
  engine never reuses stale pages. If the owner prefers no table, the filesystem layout plus `extraction_run.summary` is
  possible but cannot be enumerated reliably by the removal hook.
* Download of models: pin the wheel (hash in the lockfile) for RapidOCR; Tesseract needs a hash-pinned tessdata fetch step
  into a configured data directory. Disable library auto-download at runtime (offline, and "no private data leaves the host"
  is independent of model download, but unexpected network access must fail).

### 7.4 Job, memory and time bounds
* **Host-level coordination:** the OCR child (about 1 GB), the local embedding model and PostgreSQL share about 7 GB with other jobs; a host-level semaphore or run-state rule must prevent OCR and embedding indexing from running together.
* One OCR worker, run in a **child process** (isolation, RSS limit, kill on timeout), started by the extraction runner; one OCR
  process at a time across the host; threads capped (`intra_op_num_threads=4`, `OMP_THREAD_LIMIT=1` for Tesseract).
* Per-page timeout 60 s (measured worst 10 s), per-run page cap equal to `MAX_PDF_PAGES` (500), default selection cap of 120
  pages unless pages are selected; page render capped at 300 dpi and 12 Mpx (an A4 page is 8.7 Mpx); per-process RSS guard (kill
  at 1.5 GB). Measured: 0.97 to 1.07 GB (RapidOCR), 0.38 GB (Tesseract).
* Cancellation and lease renewal between pages; interrupted runs resume by skipping pages whose artifact exists for the same fingerprint.

### 7.5 Orientation and quality
* Pass 0 on the pdfium-rotated render; extra 270 and 90 passes (not a third pass everywhere) on pages where pass 0 reports more
  than N tall boxes (height > 1.5 x width), or low token yield for the page's image coverage; merge by overlap (keep the higher
  confidence), record the pass angle per token. Threshold N is untested: tune on the F-14/F-5 pages in phase B.
* Page quality states: `ok`, `low_quality` (mean confidence or token density below thresholds), `empty` (no tokens on a page with
  image coverage), `failed` (timeout/error), `skipped` (cap/not selected). Blank or low-quality pages never become `succeeded`:
  the run is `partial` with per-page coverage (processed/skipped/failed page ranges, as the existing `CoverageOut`) and an
  `EXTRACTION_PARTIAL` finding; a page with a table whose structure was not reconstructed is flagged.

### 7.6 AX-2 and retrieval
* **AX-2 quote-in-span for scans:** the span is the OCR text of the cited page region (lines in reading order with
  offsets back to token boxes). For text the model quote must match the span after whitespace/case normalization with a bounded
  edit tolerance (decision below); for numbers use the strict rule: the model's numeric value must equal an OCR numeric token
  (decimals by value, a single fraction normalization) located in the cited rectangle or the same OCR line/row, and a short
  integer needs a nearby label token. Failure creates an `ocr_disagreement` finding (both values, both locators, engine
  fingerprint) and the value stays quarantined/unverified (never "accepted", never silently replaced by the OCR value).
* **TASK-011 retrieval indexing:** feed per-page OCR text as chunks of bounded size (about 800 tokens, never splitting a number from its
  unit, per `RETRIEVAL_ASSISTANT.md`), each with `evidence_class="ocr_text"`, page, boxes of lines, engine fingerprint and mean confidence;
  tables as row strings from the clustering step when available. Chunks inherit invalidation from the OCR artifact. RAG owns chunk
  ranking and storage; ingestion only provides the normalized inputs and locators. Retrieval must label OCR-derived passages and
  must not cite an OCR digit as verified until the agreement rule has passed.

### 7.7 Failure modes to cover
Blank/low-quality page, rotated content, mixed text/image page, page above the cap, timeout of one page, worker kill mid-run,
revised source (new revision, old artifacts untouched but unreferenced), removal (artifacts deleted with the document),
OCR engine missing/model hash mismatch (explicit failure, not empty success), confidence-saturated wrong reads (digit misreads),
show-through noise, hostile PDF (existing 500-page and byte limits; pdfium/Pillow pixel caps), hostile `.doc`, macro presence.

### 7.8 Effort estimate (agent-days, implementer plus independent QA, excluding owner reviews)
| Slice | Content | Estimate |
|---|---|---|
| B1 | render + RapidOCR adapter (child process, bounds, fingerprint), artifact store, migration 0008 (after TASK-011), lock/dependency change | 2.0 |
| B2 | `ScannedPdfProfile` + runner cancellation pass-through and per-page commit/resume with persisted intermediate state (needs the 0008 table and run-state semantics), coverage/findings, orientation pass rule | 2.5 |
| B3 | span API for AX-2 (rect/line, numeric agreement rule with locality) and TASK-011 chunk feed (with RAG owner) | 1.5 |
| B4 | `.doc` native text profile + picture extraction + OCR of pictures (safety tests) | 1.5 |
| B5 | human-checked fixtures (F-14 p.29/30/35/36, F-5 p.48/49 attribute fixtures), row/table clustering for the as-installed table | 1.5 |
| QA | independent acceptance of each phase B increment | 1.5 |
Total about 10.5 agent-days (B2 raised from 1.5 after QA); the deadline is November 4, so the realistic cut is B1+B2+B5 for the selected F-14/F-5 pages first (about 5 days with
QA is already tight; B3 and B4 are the ones to defer or parallelize). That is a schedule risk for the owner to weigh, not a technical blocker.

### 7.9 Test plan (phase B)
Unit: normalization (decimals by value, fractions, units `#`/`m`), merge of passes, rect normalization/padding, fingerprint, quality states.
Fixture: exact tokens/locators on p.29, 30, 35, 36 (rotated), PV-21 p.48/49 (table) with human-checked expected values; blank page; low-quality page.
Negative: model misread (`8-3/8`, `55.7`, `631`) rejected; coincidental short-integer match outside the cited rect rejected; engine/model hash mismatch fails.
Resilience: kill the worker mid-document and resume (no duplicate artifacts, no partial success); per-page timeout; page cap; revised source invalidates;
removal deletes artifacts (TASK-039 hook). Resource: peak RSS under 1.5 GB and per-page time recorded on the real documents. Browser: evidence viewer
highlights the rect on a rotated page. All default tests offline, no provider call; PostgreSQL for artifact/run rows.

## 8. Decisions needed from the owner
1. **Engine**: approve RapidOCR 3 (Apache-2.0, bundled models) as the primary OCR, with Tesseract as an optional second reader/fallback, or primary only.
2. **Dependencies** (lockfile change in phase B): `pypdfium2`, `pillow`, `rapidocr`, `onnxruntime` (plus `opencv-python-headless`, shapely, pyclipper),
   optionally `tesserocr` and a pinned tessdata fetch; `olefile`. About 260 MB extra install for RapidOCR.
3. **Scope of pages**: all pages of the two documents (about 110, about 9 to 14 minutes once) or only owner/agent-selected pages; whether OCR runs at
   upload/extraction time or on demand for a selected page range.
4. **`.doc`**: include in phase B (native text + pictures OCR), and whether the two EMF drawings get a small text-record reader or are skipped.
5. **Acceptance policy**: confirm "unconfirmed numeric value is quarantined with an `ocr_disagreement` finding" and "short integers require same-line/cell locality".
6. **Number normalization**: decimals by value (`196.800` equals `196.8`) and mixed-fraction forms (`10 3/4`, `10-3/4`, `10.75`): treat as equal for agreement, or keep strictly textual.
7. **Schedule**: given the November 4 deadline, which slices to cut or defer (suggest B1, B2, B5 first).
8. **OCR artifact table** (migration 0008, after TASK-011) versus filesystem-only artifacts.
9. **Locator**: keep the existing `PdfLocator` + `ConvertedTextLocator` pair (recommended) or approve the optional additive `PdfLocator` fields (single writer after TASK-011).
10. **Retention**: keep OCR artifacts until the document is removed (recommended) or cache with expiry.

## 9. Reproduction and limits

Commands (each prefixed with `env -u MODEL_API_KEY -u FIELDLENS_DATABASE_URL uv run --no-project --python 3.12 --with ...`; evaluation-only dependencies, no lockfile change):
`ocr_run.py --engine {rapid3,rox,tessfast,tessbest} --variant ... --dpis ... --angles 0,90,270 --prep {raw,gray} --tag T`, `ocr_score.py [tags]`,
`ocr_agree.py TAG DPI ANGLES MINCONF`, `ocr_agree_native.py {rapid3,tess} VARIANT DPI`, `ocr_bbox.py TAG DPI ANGLES MINCONF`,
`ocr_doc_inspect.py FILE [PICDIR]`, `ocr_doc_images.py PICDIR`. Scores are reproducible from `.local/ocr/res/` (local only).

Limits stated plainly: 11 pages and 67 reference numbers; reference is agent-read; the pages' show-through, skew and any handwriting or stamps were not
quantified; no CER on free text; table-structure accuracy and token-locator accuracy against human-marked boxes were not measured (self-consistency and
one visual overlay only); hybrid-page behavior and the `.doc` parser were exercised on one file; cross-host determinism and the full 110 pages were not run;
the model outputs used for section 5 came from one spike (21 image-mode run files, one model, fixed prompts), so the agreement rates describe that
sample, not the live pipeline.

## 10. Proposed release note (orchestrator finalizes)
Patch bump (docs/scripts only): `0.16.2` to `0.16.3`. Proposed CHANGELOG entry: "**TASK-030 phase A (FL-005-C):** offline OCR/rendering/orientation
evaluation for scanned completion pages (RapidOCR 3 versus Tesseract, pdfium 300 dpi, rotated-schematic handling), the OCR-agreement-rule analysis against
saved model outputs and native text ground truth, a structure-only check of the legacy `.doc` (native text and 12 embedded pictures), and the phase B design and
owner decisions: `docs/evidence/TASK030_OCR_EVALUATION.md` and `scripts/spikes/ocr_*.py`. No product code, contract, migration or lockfile change."

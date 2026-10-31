# TASK-042 live feasibility spike: model reading of the real completion documents

Date: 2026-10-31 (lane `task-042-completion-spike`, base 1d1e3a5, version 0.16.0, Alembic head 0006).
Class: **live** (real `https://api.meta.ai/v1`, `muse-spark-1.3` Standard id, Responses API, existing
TASK-004/043 adapter and `WorkUnit`/ledger path) on **seven owner-approved PDFs only** (PV-11, 12, 13, 14, 17, 18, 21).
Every accuracy figure below is **live model output scored against an AGENT-READ reference that is NOT
human-verified**. Nothing here is production acceptance. No product code, no persistence of results
(except the budget ledger rows in the lane database), no UI, no contract or migration change.
Scripts: `scripts/spikes/spike042_*.py` (reviewable). Page images, text dumps and raw model outputs stay
in gitignored `.local/spike042/` (not committed). Quotes below are short (< 200 chars).

**Revision 2 (after independent QA, offline re-scoring only, no new calls, no new spend).** The reference was
corrected in three places where QA (and my own re-check) found it wrong: PV-13 perforation intervals #2 to #8
are on p.20, not p.19; PV-11 p.136 is a perforation table, not a no-equipment control; and PV-17 p.36 has
"Baker PBR 190-60" and plain TVD labels, so two of my "model misreads" there were reference errors (the model
read them correctly). All figures below are recomputed with the corrected reference
(`spike042_aggregate.py`). Lesson: a single-agent reference is itself fallible; roughly USD 0.065 was spent
chasing a "truncated perforation list" that was my page-assignment error.

## 1. Headline findings

1. **The model can read completion equipment from real pages, including scanned pages**, but the headline
   rate depends on how it is quoted. On the 15 reference pages with completion equipment or perforation
   tables (107 "sure" equipment items, 15 perforation intervals on pages that were run), image path at effort `low`:
   * **tuned composite 102 of 107 (0.95)**: a per-page best-of-tested-settings composite (PV-17 p.36 uses the
     rotate-upright 2400 px setting found after a 7-run sweep, PV-21 p.49 the 1400 px run, the rest 1600 px).
     **Tuning data equal test data** (same pages, same reference), so this is an upper bound, not a general rate.
   * **uniform low (p.36 plain at 1800 px, p.49 at 1400 px, rest 1600 px, no rotation): 90 of 107 (0.84)**;
     the whole gap is the rotated schematic (8 of 21 plain versus 20 of 21 after rotation).
   * Lenient matching (same closed type plus a printed key; 9 sure items have no key and 20 have only keys of
     3 or fewer characters) inflates these. **Strict matching** (key of 4+ characters, else the printed depth;
     83 eligible items): tuned 80 of 83, uniform 68 of 83. Per-setting table in section 6.
   Every response was strict JSON.
2. **None of the three "F-12 completion report" files is about F-12.** PV-11, PV-12 and PV-13 print wells
   `15/9-F-11`, `F-11 A`, `F-11 B` (PV-13 is the F-11 B completion report; its schematic is titled
   "Volve Completion Well F-11B IOR"). PV-14 is the only one with F-12 as its subject well, and it is a **geological
   summary** (cover plus a log strip), not equipment. (PV-11 and PV-12 print F-12 only as a neighbour/offset
   well: PV-11 text layer p.7, 31, 61, 64, 69, 70, 73, 136; PV-12 p.8, 84, 97. I did not visually sample the scanned PV-17/PV-21 pages or PV-14 p.1 for
   F-12 mentions.) So these seven documents contain **no F-12
   production/completion equipment at all** (they do contain an **F-11 B perforation table**, PV-11 p.74 and p.136); F-12 equipment needs another source (owner decision, section 9).
   F-14 (PV-17 completion FWR) and F-5 (PV-21: a drilling FWR that contains an as-installed completion table
   on p.49) do carry production-period equipment.
3. **Digit misreads happen on small print in the image path** (examples in section 6). Text-layer input
   removes them where a text layer exists (60 of 60 quotes verbatim in the layer). For scanned documents
   there is **no text layer to validate quotes against**, so AX-2's "quoted text is in the cited span"
   cannot be enforced without an OCR layer; this is the main design consequence for TASK-041/TASK-030.
4. **`reasoning.effort` is accepted** by the provider through our payload builder for `minimal`, `low`
   and `medium` (the response echoes `reasoning.effort`). `medium` is not usable here: one page
   truncated at 4,096 output tokens (3,794 reasoning tokens).
5. Cost at the placeholder rates is dominated by output (reasoning plus JSON): about USD 0.02 to 0.11
   per page; **USD 2.9036 of the USD 3.00 cap was committed** (50 provider responses).

## 2. Documents: what they actually are (free offline survey, no model)

| PV | Well printed (folder) | Content | Pages | Text layer | Scan | Notes |
|---|---|---|---|---|---|---|
| PV-11 | F-11, F-11 T2, F-11 A, F-11 B (F-12 folder) | Final well report, drilling/exploration; trailing geological "COMPLETION LOG" plots (p.108+) | 144 | all pages (median 1,742 chars) | 114 pages carry an image | no tubing/packer/schematic keyword hits; **p.74 "Table 6-1 Perforation intervals" and p.136 (geological log with a perforated-interval table, MD RKB) list the 8 F-11 B intervals**; "liner hanger" only as log legend (p.108/112/129/136) |
| PV-12 | F-11, F-11 A, F-11 B (F-12 folder) | Final well report "Drilling" | 168 | 167 (p.2 empty) | every page has an image | completion schematic p.164 (labels are raster only, text layer has the title only), wellhead/X-tree schematic p.165 not read |
| PV-13 | F-11 B (F-12 folder) | Final well report "Completion" | 64 | all | every page has an image | completion narrative p.14-21; schematic p.45 and p.58 (identical, glued label text in layer); 23 pages with >= 3 equipment keywords |
| PV-14 | F-12 | Geological summary cover plus log strip | 2 | p.2 only (axis numbers, 17.9k chars) | cover scanned | p.2 is 10661 x 826 pt; no equipment |
| PV-17 | F-14 | Final well report "Completion" (7 in monobore perforated liner) | 60 | **none** | all scanned | 842x595 pt with Rotate 270 (renders portrait); schematic p.36 is rotated inside the scan; show-through ghost text; BHA lists p.46-48 |
| PV-18 | F-14 | Geological summary cover plus strip (207 x 2387 pt) | 2 | p.2 only | cover scanned | no equipment |
| PV-21 | F-5 (filename says completion report) | Final well report "Drilling"; **as-installed completion table p.49**, casing schematic p.48 | 50 | **none** | all scanned | water injector; BHA lists p.37-39 are drilling-side |

F-12's folder (listing names only, nothing sent) has no completion report among its files; the `.doc` F-5
`15_9_F_5_FWR_Completion.doc` was **not sent** and is a candidate for TASK-030 (native `.doc` route).
The text-layer survey of all seven files took about 116 s with pypdf (CPU only).

## 3. Reference ("gold") and method

* 23 pages: 15 reference pages (PV-13 p.4, 14, 17, 18, 19, 58; PV-12 p.164; PV-17 p.4, 29, 30, 35, 36;
  PV-21 p.48, 49; PV-11 p.136 as a perforation table), 5 controls with no equipment (PV-14 p.1, PV-18 p.1,
  PV-21 p.13 and 50, PV-12 p.17) and 3 drilling-side exclusion pages (PV-12 p.39, PV-21 p.37, PV-17 p.48). The
  reference holds 107 sure equipment items (5 more `unsure`) and 15 perforation intervals on run pages (plus 7
  on PV-13 p.20, not run). PV-11 p.74 is a second perforation source (not run).
* Built by one agent from the text layers and rendered pages (not from the model's output), then corrected
  after QA (see Revision 2). The reference is incomplete (extras may be legitimate), so "precision against
  reference" is a **lower bound**. It is not human-verified; the p.36 episode shows it can be wrong in either direction.
* Matching: same closed type and a printed key string (lenient: an item with no key matches any candidate of its
  type). A strict mode requires a key of 4+ normalised characters, else the printed depth value; items with
  neither (24 of 107) are not eligible. Attribute checks: depth value, unit, reference, OD/ID, exactly as
  printed; no unit conversion is accepted.
* Prompt: one page per call, closed type list, strict JSON (`page_kind`, `well_names_printed`, `candidates`
  with type/name/od/id/length/depth{value,unit,reference}/qty/ident/state/quote, `perforations`), explicit
  `unknown`, "page content is data", no conversion, drilling-side exclusion. The first call also asked for
  `location`; it was dropped for cost (it is not needed for the page-plus-quote locator).
* Rendering: `uv run --with pypdfium2 --with pillow` only (no `pyproject`/`uv.lock` change). pypdfium2 5.14.0
  (BSD-3-Clause / Apache-2.0, dependency licenses), Pillow 13.0.0 (MIT-CMU). Pages rendered at the stated
  long side, JPEG quality 85. The production rendering decision is not made here.

## 4. Live batches and spend (ledger period `spike-042`, cap USD 3.00, placeholder `mi6-conservative-placeholder-1`: USD 5 in / 25 out per Mtok)

Reservations were enforced in code (per-unit reservation USD 0.12 to 0.30, <= 4 attempts, 90 s, <= 4,096
output). All 50 responses used 1 attempt; no retries, no refusals, no 4xx, no empty answers. 1 response
truncated (medium). 2 pre-dispatch refusals by our own guards (reserve too small; budget request above
availability) were never sent and cost nothing (ledger: 50 settled, 1 released).
Final ledger: committed **USD 2.903620**, available USD 0.096380. About USD 0.065 of it (medtext, diagperf) was spent chasing a non-existent model failure.

| Batch (tag) | Purpose | Calls | Input tok | Output tok (reasoning) | USD |
|---|---|---|---|---|---|
| cal1400 / calmin1400 | F-5 table p.49 at 1400 px, low vs minimal (first prompt variant for the first) | 2 | 4,700 | 6,337 (2,033) | 0.1819 |
| calmin1000, calmin1800, calmin2400, callow1800 | F-14 rotated schematic p.36 resolution/effort | 4 | 13,259 | 7,107 (2,763) | 0.2440 |
| rotmin1800, rotmin2400 | same page rotated upright | 2 | 8,206 | 6,181 (1,443) | 0.1956 |
| mainlow1600 | 21 pages, image, effort low | 21 | 62,412 | 32,094 (20,760) | 1.1144 |
| textlow | 10 native-text pages, text only, low | 10 | 13,244 | 18,258 (11,346) | 0.5227 |
| mainmin1600 | 6 pages, image, minimal | 6 | 17,832 | 9,050 (2,981) | 0.3154 |
| res1000low | F-14 p.29 at 1000 px, low | 1 | 1,469 | 3,605 (2,133) | 0.0975 |
| medtext, diagperf | PV-13 p.19 perforations, text medium / explicit instruction (**wasted: chasing a reference error**) | 2 | 2,402 | 2,107 (1,907) | 0.0647 |
| medimg1600 | p.58 image, medium (truncated) | 1 | 2,972 | 4,096 (3,794) | 0.1173 |
| cropperf | F-5 p.49 zoomed crop of perforation labels | 1 | 893 | 1,832 (1,334) | 0.0503 |
| **Total** | | **50** | **127,389** | **90,667 (50,494)** | **2.9036** |

Spend and tokens per document (placeholder rates; real cost is stated by the owner to be about 6x lower,
`[Assumed: not verified]`, so real spend is roughly USD 0.48):

| PV | Responses | Input tok | Output tok (reasoning) | USD placeholder |
|---|---|---|---|---|
| PV-11 (p.136 only, 3 calls: image low/minimal, text low) | 3 | 8,182 | 4,523 (2,505) | 0.1540 |
| PV-12 | 7 | 15,442 | 9,205 (7,151) | 0.3073 |
| PV-13 | 17 | 36,602 | 37,460 (22,228) | 1.1195 |
| PV-14 | 1 | 2,972 | 259 (215) | 0.0213 |
| PV-17 | 13 | 40,766 | 26,521 (11,864) | 0.8669 |
| PV-18 | 1 | 2,972 | 281 (237) | 0.0219 |
| PV-21 | 8 | 20,453 | 12,418 (6,294) | 0.4127 |
| **Total** | **50** | **127,389** | **90,667 (50,494)** | **2.9036** |

Output was about 78 percent of placeholder cost. The provider reported 11,592 cached input tokens in
total (repeated prompt prefix); the ledger applies no cached discount (no rate known).
Latency per call: min 1.2 s, median 5.7 s, max 14.9 s (all far below the 90 s unit limit).

## 5. Image tokens versus resolution; effort

Input tokens include a prompt of about 650 tokens (measured: a text-only call with a 130-character page
was 689). Image tokens measured, letter/A4 portrait pages:

| Long side (px) | Image size | Total input tok | Approx image tok | `round(w/28)*round(h/28)+2` |
|---|---|---|---|---|
| 1000 | 707 x 1000 | 1,469 | ~820 | ~900 |
| 1400 | 990 x 1400 | 2,356 | ~1,700 | ~1,750 |
| 1600 | ~1131 x 1600 | 2,972 | ~2,320 | ~2,280 |
| 1800 | 1273 x 1800 | 3,584 | ~2,930 | ~2,880 |
| 2400 | 1697 x 2400 | 4,622 | ~3,970 | ~5,250 (provider appears to downscale above ~4k tokens) |
| crop | 530 x 421 | 893 | ~240 | ~290 |

* The MI-6 formula holds up to about 1,800 px; the largest measured request was 4,622 input tokens, well
  below `provider_image_token_bound` 8192 (the bound stays safe, conservative by about 1.8x here).
* The MI-6 failure (no answer at 680 x 280, effort high) **did not recur**: 49 of 50 responses had text at
  `minimal`/`low`; the one failure was `medium` (reasoning 3,794 of 4,096 tokens, status `incomplete`,
  surfaced as `ProviderTruncated`).
* Reasoning tokens per page: `minimal` 143 to 782, `low` 173 to 2,133 (median about 1,100), `medium` 1,283 to
  3,794. Lower resolution did **not** lower cost on a dense narrative page (1000 px low: 3,605 output tok,
  USD 0.097 versus 2,777 at 1600) because reasoning grew.
* Resolution/reliability: rotated schematic p.36, effort minimal: 1000 px returned a **valid but empty**
  candidate list (silent false negative), 1800 px 5 of 21 "sure" items, 2400 px 11 of 21 (plain, low at 1800 px:
  8 of 21); after rotating the image 90 degrees clockwise (minimal) 1800 px found 15 of 21 and 2400 px 20 of 21. Narrative scan p.29: 1000 px
  10 of 12, 1600 px 11 of 12 (low) and 12 of 12 (minimal).
* **Recommended image setting: about 1600 px long side, upright, effort `low` (or `minimal` on tables);
  2000 to 2400 px with orientation correction for dense rotated schematics; crops for tiny label blocks.**

## 6. Accuracy on the agent-read reference (corrected reference, revision 2)

Per-setting results (reference items found / sure items on the pages of that run; strict = items eligible for
strict matching; perforation intervals hit / reference intervals). **Tuning data = test data** throughout.

| Setting (tag) | Pages | Lenient | Strict | Perforations |
|---|---|---|---|---|
| image low 1600 px (mainlow1600), 13 reference pages | 13 | 65 / 69 | 44 / 46 | 9 / 10 |
| image minimal 1600 px (mainmin1600), 5 reference pages | 5 | 39 / 42 | 32 / 33 | 7 / 8 |
| text-only low (textlow), 8 reference pages incl. PV-12 p.164 whose layer lacks the labels | 8 | 37 / 48 | 22 / 30 | 9 / 10 |
| F-5 p.49 image low 1400 px (cal1400) | 1 | 17 / 17 | 17 / 17 | 2 / 5 |
| F-5 p.49 image minimal 1400 px (calmin1400) | 1 | 15 / 17 | 15 / 17 | 0 / 5 |
| F-5 p.49 zoomed crop, low (cropperf) | crop | n/a | n/a | 4 / 5 |
| F-14 p.36 plain, minimal 1000 px | 1 | 0 / 21 | 0 / 20 | |
| F-14 p.36 plain, minimal 1800 px | 1 | 5 / 21 | 4 / 20 | |
| F-14 p.36 plain, minimal 2400 px | 1 | 11 / 21 | 10 / 20 | |
| F-14 p.36 plain, **low** 1800 px | 1 | 8 / 21 | 7 / 20 | |
| F-14 p.36 rotated upright, minimal 1800 px | 1 | 15 / 21 | 14 / 20 | |
| F-14 p.36 rotated upright, minimal 2400 px | 1 | 20 / 21 | 19 / 20 | |
| F-14 p.29 low 1000 px (res1000low) | 1 | 10 / 12 | 7 / 9 | |

Composites over 15 reference pages (107 sure items): **tuned 102 / 107 lenient, 80 / 83 strict, perforations
11 / 15**; **uniform low 90 / 107 lenient, 68 / 83 strict, perforations 11 / 15** (p.36 plain at 1800 px).
Perforations on the original seven intervals of PV-13 p.19, PV-21 p.49 and PV-12 p.164: 3 of 7; with the
PV-11 p.136 table (all 8 intervals read correctly at effort low) 11 of 15. PV-13 p.20 (7 intervals) was not run.

Tuned composite, other metrics:

| Metric | Value |
|---|---|
| Strict JSON parse rate | 49 of 49 completed responses (100 percent) |
| Schema valid (closed types, required keys, depth object) | 48 of 49; the failure is the first call of the earlier prompt variant (it lacked `qty`/`ident`) |
| Candidates matching a reference item | 102 of 136 (0.75); unmatched ones are mostly legitimate items missing from my reference (extra pup joints, control lines, spacer spool, BPV plug, riser, wellhead, casing/liner shoe marks on PV-11 p.136), so this is a lower bound |
| Depth value exactly as printed | 44 of 44 matched items |
| Depth unit | 44 of 44 (metres) |
| Depth reference | 39 of 44 plain; **5 of 44 are compound `MD/TVD` pairs** the model glued into one field (failure 2); no MD-as-TVD swap or unit conversion was observed |
| OD/ID (F-5 table) | 9 of 9 OD, 9 of 10 ID (1 missing) |
| `page_kind` right | 21 of 22 pages (PV-11 p.136, a geological log carrying a perforation table, was labelled `completion_table`) |
| Hallucination on the 8 control/exclusion pages | **0 invented items**; 2 items on PV-12 p.39 are real casing/hanger-seal mentions in a drilling narrative, not production-period equipment |
| Cross-well mixups | none by the model (every page's `well_names_printed` matches the page); the mix-up is in the dataset (F-11 files in the F-12 folder). On PV-12 p.164 it returned the three header wells, not the schematic's "F-11B IOR", so wellbore scope must be bound by validators |

Text-layer-only path (no image), effort low, native-text pages:

* PV-13 pages: 37 of 40 "sure" items (same as the image path on those pages; strict 22 of 23); **60 of 60 quotes
  verbatim in the text layer**, depth references 8 of 8 correct on the schematic.
* PV-12 p.164 (raster labels): text path returned nothing (the layer holds the title only): the layer is
  incomplete, the page still needs the image. Text path is not cheaper per page (output-dominated): USD 0.012
  to 0.080, average about 0.052.
* Image path quote check against the text layer on layer-bearing pages: 52 of 66 quotes verbatim; the misses are
  PV-12 p.164 (8, labels not in the layer), PV-13 p.58 (5: 2 real digit misreads plus 3 glyph/spacing differences
  from the glued schematic layer) and PV-13 p.14 (1). On PV-11 p.136 every perforation quote is the generic
  column header "Perforation top m MD RKB", which is verbatim in the layer but does not contain the numbers:
  a quote-in-span check is necessary, not sufficient (the numbers must be in the span).

Effort comparison on the same four equipment pages (PV-13 p.58, p.17, PV-17 p.29, PV-21 p.48):

| Effort | Sure items found | USD | Note |
|---|---|---|---|
| minimal | 39 of 42 | 0.2358 | no perforation intervals returned on the F-5 table page |
| low | 38 of 42 | 0.3124 | perforations returned |
| medium (1 page, p.58 image) | truncated | 0.1173 | unusable at max 4,096 output tokens |

Minimal was about 25 percent cheaper with equal recall on these pages; on the F-5 table it returned no
perforation intervals while low returned five (two correct). The sample is small.

### Failure modes (live model on agent-read reference)

1. **Digit misreads on small print** (image path): PV-13 p.58 "Vetco 6-3/8 in 6.5M XMT" read as 8-3/8 and
   "65.7#" as 55.7# (both at low and minimal; the text layer confirms 6-3/8 and 65.7). F-5 p.49 perforation
   labels at 1400 px: 3 of 5 wrong (3605 read as 3006, 3651.5-3670 as 3651-3702, 3682-3700.5 as 3692-3700); a
   zoomed crop (530 x 421 px, 3000 px render) fixed four of five but still read 3608 as 3606. PV-12 p.164 "Btm Perf
   4539 m" read as 4533 (the embedded raster is itself low resolution; my reading of it is `unsure`). A model-read
   depth is therefore never trustworthy without a second, independent check. (Correction: my earlier claim that
   the model misread "Baker PBR 190-80" as 190-60 on PV-17 p.36 was a reference error; the page prints 190-60.)
2. **Compound depth pairs**: "1358/ 1327m MD/ TVD" became value `1358/1327m` with reference `MDTVD`
   (5 of 44 depth statements); a validator must split the pair into one MD and one TVD value, or
   reject. `unit` and `reference` are otherwise copied faithfully; unknown stays `unknown`/`unspecified`
   (all narrative-only equipment kept depth unknown, including the F-14 run-in sequence on p.29).
3. **Silent empty answers** on a rotated or low-resolution page (valid JSON, zero candidates). Coverage reports
   must not treat "0 candidates" as "no equipment" without page-kind and orientation evidence.
4. **Type taxonomy drift**: tie-back adaptor, muleshoe, FLX-4 POTH, AVLDM fall into `other_completion`
   or a wrong closed type; a TBH was typed `wellhead` once. Closed vocabulary needs more members
   (annulus safety valve, PBR, muleshoe, sealstem, perforated stem, chemical injection sub).
5. **Not-in-service items listed**: BPV plug, spacer spool, Coflex flowline, HMV; state `installed` is assigned
   to events ("inflow tested HMV"). `state` and a temporary/permanent attribute are not reliable.
6. **Dataset effects**: show-through ghost text on PV-17/PV-21 scans did not visibly disturb results; the
   glued label text layer of schematic p.45/p.58 breaks naive quote matching.
7. **Source disagreements the validators must flag, not resolve** (live reads of the sources, not model
   errors): liner hanger 3095 m MD / 2742 m TVD on PV-12 p.164 versus 3094 / 2721 on PV-13 p.58 (and "3100 m MD"
   on p.58 itself); **TD 4707 / 3257 m MD/TVD (PV-12 p.164) versus 4770 / 3257 (PV-13 p.58)**; production packer
   3064.39 versus "app. 3064"; TRSCSSV 503.27 versus 503 m MD; F-5 TD 3793.0 m MD (p.48) versus TD 3791.99 /
   PB 3751.99 (p.49); **F-11 B perforation interval 7: 4065-4075 on PV-11 p.74 versus 4063-4075 on PV-11 p.136
   and PV-13 p.20** (the model read p.136 correctly; nobody compared p.74 before QA). The F-14 p.36 labels (for
   example 30 in at 196.800 m MD / 196.800 m TVD) read plainly at full resolution; the earlier "ambiguous"
   remark was my reading error. Items added to the p.36 reference after QA: 9.625 in at 2041.000 and 2355.000 m MD,
   gas lift valve 1366.790-1367.090 m MD, two 1/4 in control lines and the electrical cable.

## 7. What the AX validators would do with these results

* **AX-2** (locator exists, quote in cited span, unit parses and is dimensionally right, plausible range):
  text-path candidates pass the quote test 60 of 60; image-path candidates on layer-bearing pages fail 14 of 66
  strict checks (8 are PV-12 p.164 whose raster labels are not in the layer, 5 are on PV-13 p.58: 2 real
  misreads and 3 glyph/spacing differences, 1 is a PV-13 p.14 quote spanning two sentences); on **scanned pages
  (PV-17, PV-21) no quote can be checked at all without an OCR layer**. The units parsed in every case; the
  `MDTVD` pair and `unit: unknown` perforation labels would be rejected or flagged (perforation labels carry
  no unit; the F-5 table header gives MD [RKB] and the report text gives "All depths in metres RKB"
  as context, so inheriting page/document context is a validator design question).
* **AX-3** (disagrees with a deterministic value): the native perforation table (PV-03) and survey/WITSML
  values are the natural cross-check; the three wrong F-5 perforation reads above would all be flagged
  against PV-03 if it is loaded. Cross-source disagreements in failure 7 must become flagged conflicts (including PV-11 p.74 versus p.136).
* **AX-5** (subject identity, wrong folder, MD != TVD, nothing invented): the F-11-in-F-12-folder files are a
  ready real fixture; the model kept the printed well names, no MD/TVD swap was seen, but the validators must
  bind each candidate to a wellbore (PV-12 p.164 header lists three wells) and reject candidates whose subject
  is not an identity candidate in the project.
* **AX-11** (depth/datum fallback): relevant. Almost all depths lack an explicit datum on the page (only the F-5
  table states MD [RKB]; the F-5 report states "All depths in metres RKB unless stated otherwise" in general
  data, agent-read from a contact sheet, not verified at full resolution). Placement of equipment by depth
  therefore needs the reference from document context or must stay blocked/unlocated.

## 8. Recommendation for TASK-041 and TASK-030

1. **Paths.** (a) Native-text pages (PV-12, PV-13, PV-11): text-layer input with locator = page plus verified
   quote; add the page image only when the layer is a known-poor label layer (schematics). (b) Scanned
   documents (PV-17, PV-21, and the F-5 `.doc`): TASK-030 should produce an OCR/Docling text layer with
   page/bbox locators so that AX-2 is enforceable, then run the text prompt; keep the image prompt for schematic
   pages and for a second read of numbers (accept a number only when the OCR token and the image read agree,
   otherwise flag). (c) Embedded-image extraction is unnecessary: whole-page renders at 1600 px worked.
2. **Settings.** Whole page upright at about 1600 px, effort `low` (consider `minimal` for tables), max 4,096
   output; orientation detection/correction before the call (rotate 90 degrees for rotated schematics);
   crop-and-zoom second pass for small annotation blocks (about 240 image tokens, USD 0.05 placeholder);
   never `medium`/`high` for pages with more than about 15 rows. Per-row JSON is output-heavy: ask for compact
   fields and split dense tables by rows.
3. **Page triage first.** Keyword triage on text layers is free and found the right pages for PV-13/PV-12
   (23 and about 7 pages; PV-11 only p.74 and p.136 for the F-11 B perforation table). Scans have no layer; triage them by the printed table of contents (PV-17 and PV-21
   have one on p.3) or a cheap `page_kind`-only call; drop candidates from pages whose `page_kind` is not a
   completion kind (this removes the PV-12 p.39 and, if the label is right, geological-log hits; but the model
   called the geological "completion log" a completion table).
4. **Estimated cost of a full needed pass** (placeholder USD, then about /6 real, `[Assumed]`): targeted
   pages PV-13 about 23 (about 1.6 / 0.27), PV-17 about 11 (0.8 / 0.13), PV-21 about 4 (0.3 / 0.05), PV-12 about 7
   (0.4 / 0.07), PV-11 about 2 (0.15 / 0.03, perforation table only), PV-14/18 none: **about USD 3.2 placeholder
   (about 0.5 real) for 47 pages**. A blind pass
   over every page of the seven files (490 pages) would be about USD 17 placeholder (about 2.8 real).
5. **What cannot be done reliably.** Digits from tiny labels and tables without a second read; depth reference from a page that does not state it; wellbore scope from page
   headers; completeness (a zero or short list may be a silent miss, so coverage needs an independent check
   such as keyword/page-kind counts); anything for F-12 from these files.
6. **Validators to build first (AX-2/3/5)**: normalised quote-in-span with edit-distance tolerance for glued
   label layers; digit-level agreement between two reads; split of `A/B m MD/TVD`; unit/reference inheritance rules
   with explicit provenance; wellbore binding; closed vocabulary expansion; temporary/permanent state.
7. TASK-030 candidate: `15_9_F_5_FWR_Completion.doc` (not sent, not read in this spike).

## 9. Open owner decisions

1. **F-12 equipment source.** These files contain F-11-family completion data (F-11 B is a producer with a
   7 in monobore completion, packer at about 3064 m MD, DHSV, DHG). The project rule forbids automatic F-11
   substitution; the owner must either supply an F-12 completion document, accept an F-12 generic-display case
   without equipment candidates, or explicitly approve showing F-11 B as a separate, clearly labelled wellbore.
2. Whether OCR/Docling (TASK-030) is mandatory for scanned documents before any model reading (recommended by
   this spike), and whether model-read depths may ever be used without a deterministic or second-read check.
3. Real provider rates (to turn the estimates above into real spend) and the balance delta for this spike
   (USD 2.9036 placeholder committed; 50 billed responses expected, the 4xx rule did not trigger).
4. Whether the F-14 and F-5 completion tables should receive human verification of the agent-read reference
   (this spike's reference is not human-verified).

## 10. Reproduce / constraints honored

`env -u FIELDLENS_DATABASE_URL MODEL_API_KEY=... uv run --with pypdfium2 --with pillow python
scripts/spikes/spike042_run.py --live --tag T --pages PV-13:58 --effort low --long-side 1600` (opt-in; the key is read
from the environment only, never stored). Scoring: `spike042_score.py <tag>...`, `spike042_aggregate.py`, `spike042_report.py`. The runner now requires an explicit `--live` flag, checks the lane database name explicitly (no assert) and anchors its scratch directory to the repository root.
Only the seven approved PDFs are addressable by the scripts; no web search, no Contributor id, no other file
sent. Documents, page images and long text are not committed. The key was injected per command and never
printed or written. `ruff check`, `ruff format --check` and `mypy backend/fieldlens scripts` pass with the spike
scripts included; `backend/tests/assistant` (140 passed) unaffected; no tests were added.

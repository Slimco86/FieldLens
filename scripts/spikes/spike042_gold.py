"""AGENT-READ reference for the TASK-042 spike. NOT human verified.

Built by one agent from the text layers and rendered page images. Items marked unsure=True
are hard to read (rotated/small/scanned) and are excluded from precision/recall headline
numbers (reported separately). ``keys`` are strings as printed that identify an item;
``attrs`` hold per-attribute expectations as printed (no unit conversion).
"""

from __future__ import annotations

from typing import Any

GroupItem = dict[str, Any]


def it(
    group: str, name: str, keys: list[str] | None = None, unsure: bool = False, **attrs: str
) -> GroupItem:
    return {"group": group, "name": name, "keys": keys or [], "unsure": unsure, "attrs": attrs}


def perf(top: str, bottom: str, ref: str = "MD") -> GroupItem:
    return {"top": top, "bottom": bottom, "unit": "m", "ref": ref}


# kind: gold (has completion equipment), control (none expected), exclusion (drilling-side only)
GOLD: dict[str, dict[str, Any]] = {
    "PV-13:58": {
        "kind": "gold",
        "well": "F-11 B",
        "text_layer": True,
        "items": [
            it("xmas_tree", "Vetco 6-3/8 6.5M XMT", ["6-3/8"]),
            it("wellhead", "Vetco 13-5/8 6.5M Multibowl Wellhead", ["13-5/8"]),
            it("safety_valve", "7 TRSCSSV", ["503"], depth="503", ref="MD"),
            it("casing", "30 Conductor", ["202"], depth="202", ref="MD"),
            it("casing", "10 3/4 Casing 65.7# P110", ["65.7"]),
            it("crossover", "XO 10-3/4 x 9-5/8", ["600"], depth="600", ref="MD"),
            it("casing", "20 Casing", ["1358"], depth="1358", ref="MD"),
            it("casing", "14 Casing 114# Q-125VT", ["114"]),
            it("casing", "14 Casing 2570", ["2570"], depth="2570", ref="MD"),
            it("tubing", "7 Tubing 29# 13CRS110VT", ["29"]),
            it("casing", "9-5/8 Casing 53.5# P-110VT", ["53.5"]),
            it("gauge", "Down hole Gauge", ["3033"], depth="3033", ref="MD"),
            it("packer", "Production Packer", ["3064"], depth="3064", ref="MD"),
            it("hanger", "7x9-5/8 Liner Hanger c/w PBR", ["3094"], depth="3094", ref="MD"),
            it("casing", "9-5/8 Casing Shoe", ["3192"], depth="3192", ref="MD"),
            it("liner", "7 13Cr S110 VTHT Liner", ["VTHT"]),
            it("hanger", "Liner hanger 3100 m MD", ["3100"], depth="3100", ref="MD"),
            it("seal_assembly", "Vetco Tie back adaptor", ["Tie"]),
        ],
        "perforations": [],
    },
    "PV-12:164": {
        "kind": "gold",
        "well": "F-11 B",
        "text_layer": False,
        "items": [
            it("xmas_tree", "Vetco 6-3/8 6.5M XMT", ["6-3/8"]),
            it("wellhead", "Vetco 13-5/8 6.5M Multibowl Wellhead", ["13-5/8"]),
            it("safety_valve", "7 TRSCSSV", ["503.27"], depth="503.27", ref="MD"),
            it("crossover", "10 3/4 x 9 5/8 X-O", ["616"], depth="616", ref="MD"),
            it("tubing", "7 13Cr S110 VT tubing", ["13Cr"]),
            it("packer", "Production Packer", ["3064.39"], depth="3064.39", ref="MD"),
            it("hanger", "7x9-5/8 Liner Hanger c/w PBR", ["3095"], depth="3095", ref="MD"),
            it("liner", "7 13Cr S110 VTHT Liner", ["VTHT"]),
        ],
        "perforations": [perf("4031", "4539")],
    },
    "PV-13:4": {
        "kind": "gold",
        "well": "F-11 B",
        "text_layer": True,
        "items": [
            it("tubing", "7 production tubing"),
            it("liner", "7 cemented liner"),
            it("packer", "7 x 9 5/8 production packer", ["9 5/8"]),
            it("gauge", "single DHG"),
            it("safety_valve", "TRSCSSV down hole safety valve"),
            it("casing", "10 3/4 surface tie-back casing", ["10"]),
        ],
        "perforations": [],
    },
    "PV-13:14": {
        "kind": "gold",
        "well": "F-11 B",
        "text_layer": True,
        "items": [
            it("liner", "7 liner"),
            it("hanger", "liner hanger"),
            it("packer", "liner hanger packer"),
            it("seal_assembly", "7 liner PBR", ["PBR"]),
        ],
        "perforations": [],
    },
    "PV-13:17": {
        "kind": "gold",
        "well": "F-11 B",
        "text_layer": True,
        "items": [
            it("seal_assembly", "Self Aligning Mule shoe", ["Mule"]),
            it("plug", "EVO plug", ["EVO"]),
            it("tubing", "7 tubing joint"),
            it("packer", "BOT Granite packer", ["Granite"]),
            it("gauge", "DHPG downhole gauge", ["DHPG"]),
            it("safety_valve", "Baker DHSV", ["DHSV"]),
            it("control_line", "DHSV control line", ["control"]),
        ],
        "perforations": [],
    },
    "PV-13:18": {
        "kind": "gold",
        "well": "F-11 B",
        "text_layer": True,
        "items": [
            it("hanger", "tubing hanger", ["hanger"]),
            it("packer", "production packer", ["packer"]),
            it("plug", "EVO plug", ["EVO"]),
            it("safety_valve", "DHSV", ["DHSV"]),
            it("xmas_tree", "X-mas tree", ["tree"]),
        ],
        "perforations": [],
    },
    "PV-13:19": {
        "kind": "gold",
        "well": "F-11 B",
        "text_layer": True,
        "items": [],
        "perforations": [
            perf("4527", "4539"),
            perf("4488", "4500"),
            perf("4355", "4367"),
            perf("4304", "4316"),
            perf("4286", "4295"),
        ],
    },
    "PV-17:4": {
        "kind": "gold",
        "well": "F-14",
        "text_layer": False,
        "items": [it("liner", "7 monobore perforated liner", ["monobore"])],
        "perforations": [],
    },
    "PV-17:29": {
        "kind": "gold",
        "well": "F-14",
        "text_layer": False,
        "items": [
            it("packer", "Production packer", ["Production packer"]),
            it("seal_assembly", "Production PBR", ["PBR"]),
            it("gauge", "DHPG", ["DHPG"]),
            it("mandrel", "Chemical injector mandrel", ["Chemical"]),
            it("mandrel", "Gas Lift Mandrel", ["Gas Lift"]),
            it("packer", "FLX/AVLDM packer", ["FLX"]),
            it("safety_valve", "annulus safety valve", ["annulus"]),
            it("safety_valve", "DHSV", ["DHSV"]),
            it("seal_assembly", "Sealstem w/ratch muleshoe", ["Sealstem", "muleshoe"]),
            it("tubing", "7 tubing"),
            it("hanger", "Tubing hanger", ["anger"]),
            it("seal_assembly", "liner PBR 2615.4", ["2615"], depth="2615.4", ref="MD"),
        ],
        "perforations": [],
    },
    "PV-17:30": {
        "kind": "gold",
        "well": "F-14",
        "text_layer": False,
        "items": [
            it("xmas_tree", "XMT", ["XMT"]),
            it("other_completion", "Chemical Injection Sub", ["Chemical"]),
        ],
        "perforations": [],
    },
    "PV-17:35": {
        "kind": "gold",
        "well": "F-14",
        "text_layer": False,
        "items": [it("xmas_tree", "XMT", ["XMT"])],
        "perforations": [],
    },
    "PV-17:36": {
        "kind": "gold",
        "well": "F-14",
        "text_layer": False,
        "items": [
            it("safety_valve", "Baker TSM 7.5 Safety Valve", ["TSM"]),
            it("safety_valve", "BAKER AVLDM 10 3/4 x 7", ["AVLDM"], unsure=True),
            it("packer", "FLX-4 POTH 10 3/4 x 7", ["FLX"], unsure=True),
            it("mandrel", "7 x 1.5 Side Pocket Mandrel MMRG-4-5", ["MMRG"]),
            it("mandrel", "Chemical Injection Mandrel", ["Chemical"]),
            it("gauge", "Well Dynamic Gauge Carrier 29#", ["Gauge"]),
            it("seal_assembly", "Baker PBR size 190-80 20ft stroke", ["190-80"]),
            it("packer", "Granite Packer 9 5/8 x 7", ["Granite"]),
            it("seal_assembly", "Sealstem 15 ft w/4 A-Ryte Seal Units", ["Sealstem", "Ryte"]),
            it("seal_assembly", "190-75 Ratcheting Muleshoe", ["190-75"]),
            it("hanger", "VetcoGray Tubing Hanger", ["Hanger"], unsure=True),
            it("casing", "30 @ 196.800 m MD", ["196.8"], depth="196.800", ref="MD"),
            it("casing", "20 @ 1077.000 m MD", ["1077"], depth="1077.000", ref="MD"),
            it("casing", "10 3/4 @ 1604.000 m MD", ["1604"], depth="1604.000", ref="MD"),
            it("casing", "14 @ 2275.000 m MD", ["2275"], depth="2275.000", ref="MD"),
            it("casing", "9.625 @ 2783.000 m MD", ["2783"], depth="2783.000", ref="MD"),
            it("casing", "10.75 @ 140.780 m MD", ["140.78"], depth="140.780", ref="MD"),
            it("liner", "7 liner @ 2616.000-3695.000 m MD", ["2616"], unsure=True),
        ],
        "perforations": [],
    },
    "PV-21:49": {
        "kind": "gold",
        "well": "F-5",
        "text_layer": False,
        "items": [
            it("hanger", "7 TBH - Volve", ["20.440"], depth="20.440", ref="MD RKB"),
            it(
                "tubing",
                "7 29# Vam Top Tubing",
                ["27.480"],
                depth="27.480",
                ref="MD RKB",
                od="7.644",
                id="6.184",
            ),
            it(
                "safety_valve",
                "7 TSM 7,5 Safety Valve",
                ["508.770"],
                depth="508.770",
                ref="MD RKB",
                id="5.880",
            ),
            it(
                "tubing",
                "7 29# Vam Top Tubing",
                ["513.560"],
                depth="513.560",
                ref="MD RKB",
                od="7.644",
                id="6.184",
            ),
            it(
                "packer",
                "Granite Packer",
                ["2782.230"],
                depth="2782.230",
                ref="MD RKB",
                od="8.120",
                id="6.000",
            ),
            it(
                "tubing",
                "7 29# Vam Top Tubing",
                ["2785.320"],
                depth="2785.320",
                ref="MD RKB",
                od="7.644",
                id="6.184",
            ),
            it(
                "seal_assembly",
                "BOT_sealstem",
                ["2811.080"],
                depth="2811.080",
                ref="MD RKB",
                od="7.520",
                id="6.040",
            ),
            it(
                "seal_assembly",
                "190-75 Ratcheting Muleshoe",
                ["2814.500"],
                depth="2814.500",
                ref="MD RKB",
                od="7.450",
                id="5.994",
            ),
            it(
                "pup_joint",
                "7 29# Vam Top Pup Joint",
                ["20.640"],
                depth="20.640",
                ref="MD RKB",
                od="7.699",
                id="6.184",
            ),
            it(
                "pup_joint",
                "7 29# Vam Top Pup Joint",
                ["506.220"],
                depth="506.220",
                ref="MD RKB",
                od="7.699",
                id="6.184",
            ),
            it(
                "pup_joint",
                "7 29# Vam Top Pup Joint",
                ["2780.180"],
                depth="2780.180",
                ref="MD RKB",
                od="7.699",
                id="6.184",
            ),
            it("casing", "Casing 10.75 146.080-604.000", ["10.75"], unsure=True),
            it("casing", "Casing 9.625 604.000-2921.000", ["9.625"], unsure=True),
            it("casing", "Casing 7 2812.000-3791.000", ["2812.000"], unsure=True),
        ],
        "perforations": [
            perf("3605.000", "3608.000", "MD RKB"),
            perf("3619.000", "3622.000", "MD RKB"),
            perf("3651.500", "3670.000", "MD RKB"),
            perf("3682.000", "3700.500", "MD RKB"),
            perf("3704.000", "3712.000", "MD RKB"),
        ],
    },
    "PV-21:48": {
        "kind": "gold",
        "well": "F-5",
        "text_layer": False,
        "items": [
            it("casing", "Casing 30 @ 165.3 m MD", ["165.3"], depth="165.3", ref="MD"),
            it("casing", "Casing 30 @ 220.8 m MD", ["220.8"], depth="220.8", ref="MD"),
            it("casing", "Casing 10 3/4 @ 604.0 m MD", ["604"], depth="604.0", ref="MD"),
            it("casing", "Casing 13 3/8 @ 1404.7 m MD", ["1404.7"], depth="1404.7", ref="MD"),
            it("casing", "Casing 9 5/8 @ 2921.0 m MD", ["2921"], depth="2921.0", ref="MD"),
        ],
        "perforations": [],
    },
}

CONTROLS: dict[str, dict[str, Any]] = {
    "PV-14:1": {"kind": "control", "note": "cover sheet of a geological summary (F-12)"},
    "PV-18:1": {"kind": "control", "note": "cover sheet of a geological summary (F-14)"},
    "PV-21:13": {"kind": "control", "note": "time distribution table/chart"},
    "PV-21:50": {"kind": "control", "note": "contractors list"},
    "PV-12:17": {"kind": "control", "note": "drawworks incident, trap words motor/hanger/plug"},
    "PV-11:136": {
        "kind": "control",
        "note": "geological completion log text (liner hanger legend)",
    },
    "PV-12:39": {"kind": "exclusion", "note": "drilling 12 1/4 section narrative"},
    "PV-21:37": {"kind": "exclusion", "note": "drilling BHA list with OD/ID/length"},
    "PV-17:48": {"kind": "exclusion", "note": "BHA list incl. perforation tool strings"},
}


# Remaining pup joints of the F-5 as-installed table (read from the image, MD RKB, metres).
for _d in ("21.900", "23.430", "26.430", "511.000", "2783.770", "2808.530"):
    GOLD["PV-21:49"]["items"].append(it("pup_joint", f"pup {_d}", [_d], depth=_d, ref="MD RKB"))


def all_pages() -> list[tuple[str, int]]:
    out = []
    for key in list(GOLD) + list(CONTROLS):
        pv, page = key.split(":")
        out.append((pv, int(page)))
    return out

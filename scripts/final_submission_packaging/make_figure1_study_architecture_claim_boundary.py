#!/usr/bin/env python3
"""Build Figure 1 as a self-contained editable SVG schematic.

The deliverable intentionally uses only SVG primitives drawn in this script:
no downloaded icons, no embedded bitmaps, and no untracked external artwork.
"""

from __future__ import annotations

from pathlib import Path
from xml.sax.saxutils import escape
import csv
import hashlib
import json
import platform
import re
import shutil
import subprocess
from datetime import datetime, timezone


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "05_FIGURE1_STUDY_ARCHITECTURE_CLAIM_BOUNDARY"
OUT.mkdir(parents=True, exist_ok=True)

W, H = 1800, 1550

COLORS = {
    "navy": "#0B1F4D",
    "rna": "#E84A8A",
    "cytof": "#276FDB",
    "teal": "#00A99D",
    "red": "#D9435E",
    "purple": "#7B6FD6",
    "bg": "#F7FAFE",
    "ink": "#182033",
    "muted": "#516078",
    "line": "#B9C6D6",
    "card": "#FFFFFF",
    "soft_navy": "#EAF0FB",
    "soft_rna": "#FDEAF2",
    "soft_cytof": "#EAF1FE",
    "soft_teal": "#E6F8F6",
    "soft_red": "#FCEBF0",
    "soft_purple": "#F0EEFC",
    "pale": "#F9FBFF",
}

FONT = "Arial, Helvetica, Liberation Sans, Noto Sans, sans-serif"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def rel(path: Path) -> str:
    return str(path.relative_to(ROOT))


def cmd_version(cmd: str) -> str:
    exe = shutil.which(cmd)
    if not exe:
        return "not found"
    try:
        out = subprocess.run(
            [exe, "--version"],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=15,
        ).stdout.strip().splitlines()
        return out[0] if out else exe
    except Exception as exc:  # pragma: no cover - diagnostic only
        return f"{exe} ({exc.__class__.__name__})"


class SVG:
    def __init__(self) -> None:
        self.parts: list[str] = []

    def add(self, raw: str) -> None:
        self.parts.append(raw)

    def rect(
        self,
        x,
        y,
        w,
        h,
        fill="none",
        stroke="none",
        sw=0,
        rx=0,
        opacity=None,
        extra="",
    ):
        op = f' opacity="{opacity}"' if opacity is not None else ""
        self.add(
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="{sw}"{op} {extra}/>'
        )

    def circle(self, cx, cy, r, fill, stroke="none", sw=0, opacity=None, extra=""):
        op = f' opacity="{opacity}"' if opacity is not None else ""
        self.add(
            f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{fill}" '
            f'stroke="{stroke}" stroke-width="{sw}"{op} {extra}/>'
        )

    def line(self, x1, y1, x2, y2, stroke, sw=2, dash=None, opacity=None):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        op = f' opacity="{opacity}"' if opacity is not None else ""
        self.add(
            f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
            f'stroke="{stroke}" stroke-width="{sw}" stroke-linecap="round"{d}{op}/>'
        )

    def path(self, d, fill="none", stroke="none", sw=0, opacity=None, extra=""):
        op = f' opacity="{opacity}"' if opacity is not None else ""
        self.add(
            f'<path d="{d}" fill="{fill}" stroke="{stroke}" '
            f'stroke-width="{sw}" stroke-linecap="round" stroke-linejoin="round"{op} {extra}/>'
        )

    def polyline(self, points, fill="none", stroke="none", sw=0, opacity=None, extra=""):
        pts = " ".join(f"{x},{y}" for x, y in points)
        op = f' opacity="{opacity}"' if opacity is not None else ""
        self.add(
            f'<polyline points="{pts}" fill="{fill}" stroke="{stroke}" '
            f'stroke-width="{sw}" stroke-linecap="round" stroke-linejoin="round"{op} {extra}/>'
        )

    def polygon(self, points, fill="none", stroke="none", sw=0, opacity=None, extra=""):
        pts = " ".join(f"{x},{y}" for x, y in points)
        op = f' opacity="{opacity}"' if opacity is not None else ""
        self.add(
            f'<polygon points="{pts}" fill="{fill}" stroke="{stroke}" '
            f'stroke-width="{sw}" stroke-linejoin="round"{op} {extra}/>'
        )

    def text(
        self,
        x,
        y,
        lines,
        size=24,
        weight=400,
        fill=None,
        anchor="start",
        line_height=None,
        opacity=None,
        cls=None,
        extra="",
    ):
        if isinstance(lines, str):
            lines = lines.split("\n")
        fill = fill or COLORS["ink"]
        line_height = line_height or round(size * 1.23, 1)
        op = f' opacity="{opacity}"' if opacity is not None else ""
        c = f' class="{cls}"' if cls else ""
        self.add(
            f'<text x="{x}" y="{y}" font-family="{FONT}" font-size="{size}" '
            f'font-weight="{weight}" fill="{fill}" text-anchor="{anchor}"{op}{c} {extra}>'
        )
        for i, line in enumerate(lines):
            dy = 0 if i == 0 else line_height
            self.add(f'<tspan x="{x}" dy="{dy}">{escape(str(line))}</tspan>')
        self.add("</text>")


def add_defs(svg: SVG) -> None:
    svg.add(
        f"""<defs>
  <linearGradient id="gradDecouple" x1="0%" y1="0%" x2="100%" y2="0%">
    <stop offset="0%" stop-color="{COLORS['cytof']}"/>
    <stop offset="50%" stop-color="{COLORS['purple']}"/>
    <stop offset="100%" stop-color="{COLORS['rna']}"/>
  </linearGradient>
  <linearGradient id="gradStatement" x1="0%" y1="0%" x2="100%" y2="100%">
    <stop offset="0%" stop-color="#E8FAF7"/>
    <stop offset="100%" stop-color="#DFF2FF"/>
  </linearGradient>
</defs>"""
    )


def add_tube_icon(svg: SVG, x: float, y: float, scale: float = 1.0) -> None:
    svg.rect(x + 12 * scale, y + 4 * scale, 70 * scale, 18 * scale, COLORS["navy"], rx=7 * scale)
    svg.path(
        f"M{x+23*scale},{y+22*scale} L{x+31*scale},{y+94*scale} "
        f"Q{x+47*scale},{y+108*scale} {x+63*scale},{y+94*scale} L{x+70*scale},{y+22*scale} Z",
        fill="#FFFFFF",
        stroke=COLORS["navy"],
        sw=3 * scale,
    )
    svg.path(
        f"M{x+31*scale},{y+77*scale} Q{x+47*scale},{y+66*scale} {x+63*scale},{y+77*scale} "
        f"L{x+61*scale},{y+92*scale} Q{x+47*scale},{y+101*scale} {x+33*scale},{y+92*scale} Z",
        fill=COLORS["soft_rna"],
        stroke="none",
    )
    pts = [
        (x + 93 * scale, y + 35 * scale),
        (x + 106 * scale, y + 25 * scale),
        (x + 119 * scale, y + 45 * scale),
        (x + 132 * scale, y + 35 * scale),
        (x + 145 * scale, y + 55 * scale),
    ]
    svg.polyline(pts, stroke=COLORS["rna"], sw=4 * scale)
    for r in range(3):
        for c in range(4):
            fill = [COLORS["soft_rna"], COLORS["rna"], COLORS["navy"], COLORS["soft_navy"]][(r + c) % 4]
            svg.rect(
                x + (93 + c * 16) * scale,
                y + (70 + r * 13) * scale,
                11 * scale,
                8 * scale,
                fill=fill,
                rx=2 * scale,
                opacity=0.9,
            )


def add_gradient_icon(svg: SVG, x: float, y: float, scale: float = 1.0) -> None:
    svg.rect(x + 4 * scale, y + 36 * scale, 170 * scale, 34 * scale, "url(#gradDecouple)", rx=17 * scale)
    for xx in [60, 116]:
        svg.line(x + xx * scale, y + 34 * scale, x + xx * scale, y + 74 * scale, "#FFFFFF", sw=2.5 * scale, dash="5 7", opacity=0.85)
    for xx, rr, col in [(24, 7, COLORS["cytof"]), (49, 5, COLORS["navy"]), (88, 7, COLORS["purple"]), (134, 6, COLORS["rna"]), (158, 8, COLORS["red"])]:
        svg.circle(x + xx * scale, y + (53 + (xx % 3 - 1) * 7) * scale, rr * scale, "#FFFFFF", stroke=col, sw=3 * scale)


def add_cytometry_icon(svg: SVG, x: float, y: float, scale: float = 1.0) -> None:
    svg.rect(x + 14 * scale, y + 10 * scale, 125 * scale, 103 * scale, "#FFFFFF", stroke=COLORS["cytof"], sw=3 * scale, rx=14 * scale)
    svg.line(x + 34 * scale, y + 92 * scale, x + 116 * scale, y + 92 * scale, COLORS["navy"], sw=3 * scale)
    svg.line(x + 34 * scale, y + 92 * scale, x + 34 * scale, y + 29 * scale, COLORS["navy"], sw=3 * scale)
    dots = [(52, 74, 5, COLORS["cytof"]), (69, 61, 4, COLORS["cytof"]), (84, 49, 5, COLORS["rna"]), (99, 38, 4, COLORS["rna"]), (104, 72, 4, COLORS["purple"]), (63, 39, 3, COLORS["purple"])]
    for dx, dy, r, col in dots:
        svg.circle(x + dx * scale, y + dy * scale, r * scale, col, opacity=0.78)
    svg.path(
        f"M{x+127*scale},{y+62*scale} L{x+153*scale},{y+72*scale} L{x+153*scale},{y+100*scale} "
        f"Q{x+140*scale},{y+115*scale} {x+127*scale},{y+120*scale} "
        f"Q{x+114*scale},{y+115*scale} {x+101*scale},{y+100*scale} L{x+101*scale},{y+72*scale} Z",
        fill=COLORS["soft_teal"],
        stroke=COLORS["teal"],
        sw=3 * scale,
    )
    svg.path(f"M{x+113*scale},{y+90*scale} L{x+123*scale},{y+101*scale} L{x+143*scale},{y+80*scale}", stroke=COLORS["teal"], sw=4 * scale)


def add_bridge_icon(svg: SVG, x: float, y: float, scale: float = 1.0) -> None:
    svg.circle(x + 43 * scale, y + 58 * scale, 34 * scale, COLORS["soft_rna"], stroke=COLORS["rna"], sw=3 * scale)
    svg.circle(x + 157 * scale, y + 58 * scale, 34 * scale, COLORS["soft_cytof"], stroke=COLORS["cytof"], sw=3 * scale)
    for i, cx in enumerate([84, 101, 118]):
        svg.rect(x + cx * scale, y + (45 + (i % 2) * 12) * scale, 26 * scale, 14 * scale, "#FFFFFF", stroke=COLORS["navy"], sw=2.5 * scale, rx=7 * scale)
    svg.line(x + 76 * scale, y + 58 * scale, x + 124 * scale, y + 58 * scale, COLORS["line"], sw=3 * scale, dash="6 8")


def add_context_icon(svg: SVG, x: float, y: float, scale: float = 1.0) -> None:
    for dx, dy, r, col in [
        (30, 54, 19, COLORS["purple"]),
        (62, 35, 15, COLORS["cytof"]),
        (70, 74, 18, COLORS["teal"]),
        (101, 53, 17, COLORS["rna"]),
    ]:
        svg.circle(x + dx * scale, y + dy * scale, r * scale, col, opacity=0.82)
        svg.circle(x + dx * scale, y + dy * scale, 5.5 * scale, "#FFFFFF", opacity=0.9)
    svg.rect(x + 125 * scale, y + 22 * scale, 47 * scale, 66 * scale, "#FFFFFF", stroke=COLORS["navy"], sw=3 * scale, rx=7 * scale)
    svg.rect(x + 137 * scale, y + 14 * scale, 23 * scale, 15 * scale, COLORS["soft_purple"], stroke=COLORS["purple"], sw=2 * scale, rx=5 * scale)
    svg.line(x + 137 * scale, y + 44 * scale, x + 160 * scale, y + 44 * scale, COLORS["line"], sw=2.5 * scale)
    svg.line(x + 137 * scale, y + 59 * scale, x + 160 * scale, y + 59 * scale, COLORS["line"], sw=2.5 * scale)
    svg.circle(x + 149 * scale, y + 102 * scale, 16 * scale, "#FFFFFF", stroke=COLORS["red"], sw=3 * scale)
    svg.line(x + 149 * scale, y + 102 * scale, x + 157 * scale, y + 92 * scale, COLORS["red"], sw=3 * scale)
    svg.line(x + 149 * scale, y + 102 * scale, x + 141 * scale, y + 108 * scale, COLORS["red"], sw=2.5 * scale)


def add_lock_icon(svg: SVG, x: float, y: float, scale: float = 1.0, stroke=None) -> None:
    stroke = stroke or COLORS["teal"]
    svg.path(f"M{x+18*scale},{y+39*scale} V{y+27*scale} Q{x+18*scale},{y+8*scale} {x+38*scale},{y+8*scale} Q{x+58*scale},{y+8*scale} {x+58*scale},{y+27*scale} V{y+39*scale}", stroke=stroke, sw=4 * scale)
    svg.rect(x + 9 * scale, y + 37 * scale, 58 * scale, 48 * scale, "#FFFFFF", stroke=stroke, sw=4 * scale, rx=12 * scale)
    svg.circle(x + 38 * scale, y + 60 * scale, 5 * scale, stroke)
    svg.line(x + 38 * scale, y + 64 * scale, x + 38 * scale, y + 74 * scale, stroke, sw=4 * scale)


def add_card(svg: SVG, idx: int, x: float, y: float, w: float, h: float, accent: str, soft: str, title: str, lines: list[str], icon_fn) -> None:
    svg.rect(x + 7, y + 10, w - 14, h - 4, "#D8E2EF", stroke="none", rx=24, opacity=0.35)
    svg.rect(x, y, w, h, COLORS["card"], stroke="#DDE5EF", sw=2.2, rx=24)
    svg.rect(x, y, w, 16, accent, rx=8, opacity=0.96)
    svg.circle(x + 38, y + 48, 24, soft, stroke=accent, sw=2.8)
    svg.text(x + 38, y + 58, str(idx), 30, 800, accent, anchor="middle")
    svg.text(x + 76, y + 72, title, 30, 800, COLORS["navy"], line_height=34)
    icon_fn(svg, x + 56, y + 170, 0.82)
    # Label strip preserves meaning in grayscale as well as color.
    svg.rect(x + 28, y + 300, w - 56, 2.5, accent, rx=1.5, opacity=0.9)
    yy = y + 345
    for line in lines:
        svg.circle(x + 46, yy - 7, 5, accent, opacity=0.82)
        svg.text(x + 63, yy, line, 28.5, 650, COLORS["ink"], line_height=31)
        yy += 31 * max(1, line.count("\n") + 1) + 8


def add_panel_c_item(svg: SVG, x: float, y: float, label: str, color: str, kind: str) -> None:
    if kind == "allowed":
        svg.circle(x, y - 7, 10, COLORS["soft_teal"], stroke=COLORS["teal"], sw=2.5)
        svg.path(f"M{x-5},{y-7} L{x-1},{y-2} L{x+7},{y-13}", stroke=COLORS["teal"], sw=2.8)
    else:
        svg.circle(x, y - 7, 10, COLORS["soft_red"], stroke=COLORS["red"], sw=2.5)
        svg.line(x - 5, y - 12, x + 5, y - 2, COLORS["red"], sw=2.8)
        svg.line(x + 5, y - 12, x - 5, y - 2, COLORS["red"], sw=2.8)
    svg.text(x + 22, y, label, 28.5, 650, COLORS["ink"])


def add_panel_label(svg: SVG, x: float, y: float, letter: str, label: str, color: str) -> None:
    svg.text(x, y, letter, 36, 900, color, anchor="start")
    svg.text(x + 40, y, label, 30, 850, COLORS["navy"], anchor="start")


def build_svg() -> str:
    svg = SVG()
    svg.add(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="180mm" height="155mm" '
        f'viewBox="0 0 {W} {H}" role="img" aria-label="Study architecture and claim-boundary map">'
    )
    add_defs(svg)
    svg.rect(0, 0, W, H, COLORS["bg"])
    svg.rect(28, 28, W - 56, H - 56, "none", stroke="#E1EAF4", sw=2.2, rx=28)

    svg.text(82, 116, "Study architecture and claim-boundary map", 42, 800, COLORS["ink"])
    svg.text(82, 158, "Association and sensitivity evidence; no causal or predictive modeling.", 30, 500, COLORS["muted"])

    add_panel_label(svg, 68, 205, "A", "Evidence hierarchy", COLORS["navy"])

    card_y, card_w, card_h, gap, start_x = 232, 310, 560, 20, 75
    cards = [
        (
            1,
            COLORS["rna"],
            COLORS["soft_rna"],
            "Public bulk\nRNA recurrence",
            ["7 public cohorts", "660 samples;\n499 sepsis", "MHC-II/CD74 and\nHLA-DR inverse\ncoupling"],
            add_tube_icon,
        ),
        (
            2,
            COLORS["purple"],
            COLORS["soft_purple"],
            "Case-only\nimmune\nspectrum",
            ["499 complete\nsepsis cases", "Continuous\ngradient", "k=3 descriptive;\n221 cases"],
            add_gradient_icon,
        ),
        (
            3,
            COLORS["cytof"],
            COLORS["soft_cytof"],
            "Representative\nresidual\nco-event signal",
            ["Prespecified\npair readout", "Frequency vs\nmarker state", "Pair specificity\nunresolved"],
            add_cytometry_icon,
        ),
        (
            4,
            COLORS["teal"],
            COLORS["soft_teal"],
            "Paired COMBAT\nRNA-CyTOF\nbridge",
            ["129 matched rows", "40 sepsis-only\nrows", "34 participants"],
            add_bridge_icon,
        ),
        (
            5,
            COLORS["purple"],
            COLORS["soft_purple"],
            "Context /\nexploratory\nanchor",
            ["Donor-level\nsingle-cell\ncontext", "Death28\nexploratory anchor", "40 rows; 11 events;\nexploratory only"],
            add_context_icon,
        ),
    ]
    for i, card in enumerate(cards):
        x = start_x + i * (card_w + gap)
        add_card(svg, card[0], x, card_y, card_w, card_h, card[1], card[2], card[3], card[4], card[5])
        if i < 4:
            x2 = x + card_w
            nx = x + card_w + gap
            svg.line(x2 + 8, card_y + 190, nx - 8, card_y + 190, COLORS["line"], sw=3.2, dash="10 9")
            svg.circle(x2 + gap / 2, card_y + 190, 7, COLORS["card"], stroke=COLORS["line"], sw=2.5)

    # Panel B: locked interpretation
    add_panel_label(svg, 68, 855, "B", "Locked interpretation", COLORS["teal"])
    bx, by, bw, bh = 220, 880, 1360, 220
    svg.rect(bx + 8, by + 10, bw - 16, bh - 4, "#CDE6ED", stroke="none", rx=30, opacity=0.4)
    svg.rect(bx, by, bw, bh, "url(#gradStatement)", stroke=COLORS["teal"], sw=3.5, rx=30)
    add_lock_icon(svg, bx + 48, by + 35, 0.9)
    svg.text(
        bx + bw / 2,
        by + 52,
        [
            "Inflammatory/MHC-II decoupling is associated with",
            "a representative residual co-event signal",
            "within a broader marker-pair background",
        ],
        30,
        850,
        COLORS["navy"],
        anchor="middle",
        line_height=36,
    )
    svg.text(bx + bw / 2, by + 188, "Association-only, artifact-aware, non-predictive interpretation", 29, 650, COLORS["teal"], anchor="middle")
    svg.line(bx + 170, by + 24, bx + bw - 170, by + 24, COLORS["teal"], sw=2.2, dash="8 10", opacity=0.65)

    # Panel C: claim boundary strip
    add_panel_label(svg, 68, 1175, "C", "Claim boundaries", COLORS["red"])
    cx, cy, cw, ch = 120, 1195, 1560, 310
    svg.rect(cx + 8, cy + 10, cw - 16, ch - 4, "#EED5DC", stroke="none", rx=26, opacity=0.35)
    svg.rect(cx, cy, cw, ch, "#FFFFFF", stroke=COLORS["red"], sw=3.3, rx=26)
    svg.rect(cx, cy, cw, 18, COLORS["red"], rx=9, opacity=0.94)
    svg.line(cx + cw / 2, cy + 34, cx + cw / 2, cy + ch - 26, "#E5B1BC", sw=2.8, dash="9 8")
    svg.rect(cx + 42, cy + 46, 252, 38, COLORS["soft_teal"], stroke=COLORS["teal"], sw=2.2, rx=19)
    svg.text(cx + 168, cy + 72, "Allowed", 30, 850, COLORS["teal"], anchor="middle")
    svg.rect(cx + cw / 2 + 42, cy + 46, 252, 38, COLORS["soft_red"], stroke=COLORS["red"], sw=2.2, rx=19)
    svg.text(cx + cw / 2 + 168, cy + 72, "Excluded", 30, 850, COLORS["red"], anchor="middle")

    allowed = [
        "Cross-cohort\nrecurrence",
        "Paired RNA-CyTOF\nbridge",
        "Marker-state\nheterogeneity",
        "Computational\nsensitivity",
    ]
    excluded = [
        "Causal\nmechanism",
        "Physical CD3/CD14\ncomplex",
        "Validated\nendotype",
        "Clinical prediction\nmodel",
        "Therapeutic\nrecommendation",
    ]
    for row, item in enumerate(allowed):
        add_panel_c_item(svg, cx + 72 + (row % 2) * 342, cy + 126 + (row // 2) * 90, item, COLORS["teal"], "allowed")
    for row, item in enumerate(excluded):
        add_panel_c_item(svg, cx + cw / 2 + 72 + (row % 2) * 342, cy + 112 + (row // 2) * 72, item, COLORS["red"], "excluded")

    svg.add("</svg>")
    return "\n".join(svg.parts)


def write_attribution() -> Path:
    path = OUT / "Figure1_attribution.csv"
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "asset_name",
                "source_url",
                "creator",
                "license",
                "license_url",
                "modified_or_not",
                "used_in_panel",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "asset_name": "All icons and schematic elements",
                "source_url": "self-drawn SVG primitives in project script",
                "creator": "Codex-generated for this project",
                "license": "Project-internal original vector drawing; no third-party asset",
                "license_url": "not applicable",
                "modified_or_not": "not applicable",
                "used_in_panel": "Panels A-C",
            }
        )
    return path


def write_manifest(paths: list[Path]) -> Path:
    manifest = {
        "figure": "Figure 1",
        "title": "Study architecture and claim-boundary map",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "project_root": str(ROOT),
        "output_directory": rel(OUT),
        "canvas": {
            "viewBox": f"0 0 {W} {H}",
            "physical_size": "180 mm x 155 mm",
            "target_width_for_submission": "180 mm",
            "minimum_planned_text_size_at_180mm": ">=8 pt equivalent for all visible text",
            "minimum_line_width": "2.2 pt equivalent or thicker",
        },
        "inputs_checked": [
            "00_FINAL_WORD/Frontiers_Immunology_V17_FINAL_TEXT_ONLY.docx",
            "03_TRACEABLE_RESULTS/stage_outputs_tables/03_REPRODUCIBLE_RESULTS/stage2_signature_state_heterogeneity/stage2_immune_state_counts.csv",
            "03_TRACEABLE_RESULTS/stage_outputs_tables/03_REPRODUCIBLE_RESULTS/stage7_review_hardening/stage7_claim_boundary_matrix.csv",
            "03_TRACEABLE_RESULTS/stage_outputs_tables/03_REPRODUCIBLE_RESULTS/stage7_review_hardening/stage7_combat_pairing_flow_source_data.csv",
            "03_TRACEABLE_RESULTS/stage_outputs_tables/03_REPRODUCIBLE_RESULTS/stage7_review_hardening/stage7_combat_sepsis_paired_robustness.csv",
            "03_TRACEABLE_RESULTS/stage_outputs_tables/03_REPRODUCIBLE_RESULTS/stage7_review_hardening/stage7_clinical_anchor_map.csv",
        ],
        "reference_svg_status": "The requested Figure1_highend_SCI_vector(2).svg and Figure6_compartment_aware_model(1).svg were not found under the active project root.",
        "data_anchors": {
            "public_bulk_rna": "7 public sepsis transcriptomic cohorts; 660 samples; 499 sepsis cases",
            "case_only_layer": "499 complete sepsis cases; continuous gradient; k=3 descriptive; 221 decoupled inflammatory/MHC-II-low cases",
            "cytometry_layer": "representative residual co-event signal; frequency and marker-state context separated; pair specificity unresolved",
            "combat_bridge": "129 matched biological RNA-CyTOF participant-timepoint rows; 40 sepsis-only rows; 34 participants",
            "single_cell_context": "donor-level contextual support only",
            "death28": "exploratory clinical anchor only; 40 sepsis-only rows; 11 events",
        },
        "font_handling": {
            "editable_source": "Live text using Arial, Helvetica, Liberation Sans, Noto Sans fallback stack",
            "final_svg_pdf_eps": "Exported from Inkscape with text converted to paths where supported",
        },
        "external_assets": "None; all artwork is self-drawn SVG geometry.",
        "software_versions": {
            "python": platform.python_version(),
            "inkscape": cmd_version("inkscape"),
            "pdffonts": cmd_version("pdffonts"),
        },
        "outputs": [
            {
                "path": rel(p),
                "bytes": p.stat().st_size if p.exists() else None,
                "sha256": sha256(p) if p.exists() else None,
            }
            for p in paths
        ],
    }
    path = OUT / "Figure1_manifest.json"
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def main() -> None:
    editable = OUT / "Figure1_editable_source.svg"
    final_live = OUT / "Figure1_study_architecture_claim_boundary.live-text.svg"
    svg_text = build_svg()
    editable.write_text(svg_text, encoding="utf-8")
    final_live.write_text(svg_text, encoding="utf-8")
    attribution = write_attribution()
    manifest = write_manifest([editable, final_live, attribution])
    print(f"Wrote {rel(editable)}")
    print(f"Wrote {rel(final_live)}")
    print(f"Wrote {rel(attribution)}")
    print(f"Wrote {rel(manifest)}")


if __name__ == "__main__":
    main()

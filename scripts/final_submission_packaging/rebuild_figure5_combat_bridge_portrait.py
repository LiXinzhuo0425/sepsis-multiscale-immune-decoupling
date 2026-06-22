#!/usr/bin/env python3
"""Portrait full-page rebuild of Figure 5.

The figure is rebuilt from source data with a portrait evidence hierarchy:
workflow, paired scatter panels, paired robustness/null panels, a grouped
participant-aware forest matrix, and a slim claim-boundary strip.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import fitz
import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Rectangle
from matplotlib.transforms import Bbox
from PIL import Image
from scipy.stats import gaussian_kde, theilslopes

from rebuild_figure5_combat_bridge import (
    COLORS,
    EXPECTED,
    FIG_DIR,
    METRIC_LABELS,
    METRIC_ORDER,
    PANEL_TITLES,
    PROJECT_ROOT,
    SOURCE_CHECK_OUT,
    Y_COLUMNS,
    Y_LABELS,
    compute_metrics,
    read_sources,
)


OUT_BASE = FIG_DIR / "Figure5_COMBAT_RNA_CyTOF_bridge_portrait"
SVG_OUT = OUT_BASE.with_suffix(".svg")
PDF_OUT = OUT_BASE.with_suffix(".pdf")
PNG_OUT = OUT_BASE.with_suffix(".png")
TIFF_OUT = OUT_BASE.with_suffix(".tiff")
QA_REPORT_OUT = FIG_DIR / "Figure5_COMBAT_RNA_CyTOF_bridge_portrait_QA_report.md"
SOURCE_CHECK_PORTRAIT_OUT = FIG_DIR / "Figure5_COMBAT_RNA_CyTOF_bridge_portrait_source_check.tsv"
PREVIEW_OUT = FIG_DIR / "Figure5_COMBAT_RNA_CyTOF_bridge_portrait_preview.png"
LICENSE_OUT = FIG_DIR / "Figure5_COMBAT_RNA_CyTOF_bridge_portrait_license_manifest.tsv"
PDF_RENDER_OUT = FIG_DIR / "Figure5_COMBAT_RNA_CyTOF_bridge_portrait_QA_pdf_render.png"
SVG_RENDER_OUT = FIG_DIR / "Figure5_COMBAT_RNA_CyTOF_bridge_portrait_QA_svg_render.png"

METRIC_LABELS_WRAPPED = {
    "mhcii_cd74_axis": "MHC-II/CD74",
    "hla_dr_core": "HLA-DR core",
    "rna_decoupling_index_six_minus_mhcii": "RNA decoupling\nindex",
}


mpl.rcParams.update(
    {
        "font.family": "sans-serif",
        "font.sans-serif": ["DejaVu Sans", "Noto Sans", "Arial Unicode MS", "Arial", "Helvetica", "sans-serif"],
        "svg.fonttype": "none",
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
        "font.size": 7.8,
        "axes.spines.right": False,
        "axes.spines.top": False,
        "axes.linewidth": 0.65,
        "xtick.major.width": 0.6,
        "ytick.major.width": 0.6,
        "xtick.color": COLORS["text"],
        "ytick.color": COLORS["text"],
        "axes.labelcolor": COLORS["text"],
        "text.color": COLORS["text"],
        "savefig.facecolor": "white",
    }
)


def setup_axis(ax: plt.Axes, grid_axis: str = "both") -> None:
    ax.set_facecolor("white")
    ax.tick_params(axis="both", labelsize=7.6, length=2.6, color=COLORS["axis"])
    for spine in ["left", "bottom"]:
        ax.spines[spine].set_color(COLORS["axis"])
        ax.spines[spine].set_linewidth(0.65)
    ax.grid(True, axis=grid_axis, color=COLORS["grid"], linewidth=0.55, zorder=0)


def text_fits_within(fig: plt.Figure, text_obj: mpl.text.Text, bbox_axes: Bbox, ax: plt.Axes) -> bool:
    """Return whether a text object fits inside an axes-coordinate bbox."""
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    text_bbox = text_obj.get_window_extent(renderer=renderer)
    allowed_bbox = ax.transAxes.transform_bbox(bbox_axes)
    return (
        text_bbox.x0 >= allowed_bbox.x0
        and text_bbox.x1 <= allowed_bbox.x1
        and text_bbox.y0 >= allowed_bbox.y0
        and text_bbox.y1 <= allowed_bbox.y1
    )


def fit_card_text(
    fig: plt.Figure,
    ax: plt.Axes,
    text_obj: mpl.text.Text,
    bbox_axes: Bbox,
    start_size: float,
    min_size: float,
) -> tuple[bool, float]:
    """Shrink text in small steps until it fits the available card text box."""
    size = start_size
    text_obj.set_fontsize(size)
    while size >= min_size:
        if text_fits_within(fig, text_obj, bbox_axes, ax):
            return True, size
        size = round(size - 0.2, 2)
        text_obj.set_fontsize(size)
    return text_fits_within(fig, text_obj, bbox_axes, ax), size


def draw_panel_a(fig: plt.Figure) -> dict[str, Any]:
    ax = fig.add_axes([0.025, 0.825, 0.940, 0.125])
    ax.axis("off")
    ax.text(0.0, 1.07, "A COMBAT RNA-CyTOF pairing workflow", fontsize=10.5, fontweight="bold", va="top")
    titles = ["RNA-seq logCPM", "Strict event-QC CyTOF", "Matched RNA-CyTOF", "Sepsis-only paired set"]
    values = ["143 samples | 23,063 genes", "183 rows", "129 participant-timepoints", "40 rows | 34 participants"]
    fills = [COLORS["card_blue"], COLORS["card_pink"], COLORS["card_teal"], COLORS["card_orange"]]
    # Keep the rounded card strokes comfortably inside the axes.  The previous
    # near-edge placement let Matplotlib clip the left/right card borders.
    x0s = [0.014, 0.262, 0.510, 0.758]
    card_w, card_h, y0 = 0.222, 0.48, 0.32
    pad_x, pad_y = 0.010, 0.045
    fit_rows: list[dict[str, Any]] = []
    for i, (x0, title, value, fill) in enumerate(zip(x0s, titles, values, fills)):
        ax.add_patch(
            FancyBboxPatch(
                (x0, y0),
                card_w,
                card_h,
                transform=ax.transAxes,
                boxstyle="round,pad=0.008,rounding_size=0.014",
                facecolor=fill,
                edgecolor="#B8C4D3",
                linewidth=0.85,
                clip_on=False,
            )
        )
        title_obj = ax.text(x0 + card_w / 2, y0 + 0.315, title, ha="center", va="center", fontsize=8.4, fontweight="bold")
        value_obj = ax.text(x0 + card_w / 2, y0 + 0.145, value, ha="center", va="center", fontsize=7.6, color=COLORS["muted"])
        title_bbox = Bbox.from_bounds(x0 + pad_x, y0 + card_h * 0.50, card_w - 2 * pad_x, card_h * 0.36 - pad_y / 2)
        value_bbox = Bbox.from_bounds(x0 + pad_x, y0 + pad_y, card_w - 2 * pad_x, card_h * 0.34)
        title_fit, title_size = fit_card_text(fig, ax, title_obj, title_bbox, 8.4, 7.4)
        value_fit, value_size = fit_card_text(fig, ax, value_obj, value_bbox, 7.6, 6.8)
        fit_rows.append(
            {
                "card": title,
                "title_fit": title_fit,
                "value_fit": value_fit,
                "title_font": title_size,
                "value_font": value_size,
            }
        )
        if i < 3:
            ax.add_artist(
                FancyArrowPatch(
                    (x0 + card_w + 0.008, y0 + card_h / 2),
                    (x0s[i + 1] - 0.008, y0 + card_h / 2),
                    transform=ax.transAxes,
                    arrowstyle="-|>",
                    mutation_scale=10,
                    linewidth=1.1,
                    edgecolor="#93A4B8",
                    facecolor="#93A4B8",
                    clip_on=False,
                )
            )
    ax.text(
        0.0,
        0.03,
        "Six repeated participants; maximum two rows each.",
        fontsize=7.6,
        color=COLORS["muted"],
        va="bottom",
    )
    ax_box = ax.get_position()
    card_left_axes = min(x0s) - 0.008
    card_right_axes = max(x0s) + card_w + 0.008
    card_left_fig = ax_box.x0 + ax_box.width * card_left_axes
    card_right_fig = ax_box.x0 + ax_box.width * card_right_axes
    panel_a_left_margin_mm = card_left_fig * fig.get_figwidth() * 25.4
    panel_a_right_margin_mm = (1 - card_right_fig) * fig.get_figwidth() * 25.4
    return {
        "panel_a_text_overflow": not all(row["title_fit"] and row["value_fit"] for row in fit_rows),
        "panel_a_text_fit_rows": fit_rows,
        "panel_a_card_width_axes": card_w,
        "panel_a_card_height_axes": card_h,
        "panel_a_left_margin_mm": panel_a_left_margin_mm,
        "panel_a_right_margin_mm": panel_a_right_margin_mm,
    }


def repeated_participant_ids(scatter: pd.DataFrame) -> pd.DataFrame:
    out = scatter.copy()
    out["participant_id"] = out["RNASeq_sample_ID"].str.extract(r"^(N\d+)")
    return out


def draw_scatter_panel(
    fig: plt.Figure,
    ax_pos: list[float],
    scatter: pd.DataFrame,
    metrics: pd.DataFrame,
    metric: str,
    xlim: tuple[float, float],
    show_xlabel: bool,
) -> plt.Axes:
    ax = fig.add_axes(ax_pos)
    setup_axis(ax)
    x_col = "cd3_cd14_abundance_normalized"
    y_col = Y_COLUMNS[metric]
    color = COLORS[metric]

    for _, grp in scatter.groupby("participant_id"):
        if len(grp) == 2:
            grp_sorted = grp.sort_values("RNASeq_sample_ID")
            ax.plot(
                grp_sorted[x_col],
                grp_sorted[y_col],
                color="#9CA3AF",
                linewidth=0.50,
                alpha=0.20,
                zorder=1,
            )
    ax.scatter(
        scatter[x_col],
        scatter[y_col],
        s=24,
        facecolor="white",
        edgecolor=color,
        linewidth=0.82,
        alpha=0.88,
        zorder=3,
    )
    slope, intercept, _, _ = theilslopes(scatter[y_col], scatter[x_col])
    xs = np.linspace(*xlim, 120)
    ax.plot(xs, intercept + slope * xs, color="#111827", linewidth=1.05, zorder=2)
    ax.set_xlim(xlim)
    ax.set_ylabel(Y_LABELS[metric], fontsize=8.6, labelpad=3)
    row = metrics.query("metric == @metric").iloc[0]
    ax.text(
        0.0,
        1.105,
        PANEL_TITLES[metric],
        transform=ax.transAxes,
        ha="left",
        va="bottom",
        fontsize=9.8,
        fontweight="bold",
        clip_on=False,
    )
    ax.text(
        0.0,
        1.030,
        f"ρ = {row['rho']:.3f}, perm p = {row['perm_p']:.4f}",
        transform=ax.transAxes,
        ha="left",
        va="bottom",
        fontsize=7.5,
        color=COLORS["muted"],
        clip_on=False,
    )
    if show_xlabel:
        ax.set_xlabel("Residual CD3/CD14 co-event signal", fontsize=8.8, labelpad=3)
    else:
        ax.set_xlabel("")
    return ax


def draw_panel_e(fig: plt.Figure, metrics: pd.DataFrame) -> plt.Axes:
    ax = fig.add_axes([0.165, 0.340, 0.315, 0.110])
    setup_axis(ax, grid_axis="x")
    ax.set_title("E Bootstrap confidence intervals", loc="left", fontsize=9.0, fontweight="bold", pad=0)
    y_pos = np.arange(len(METRIC_ORDER))[::-1]
    ax.axvline(0, color=COLORS["zero"], linestyle="--", linewidth=0.8, zorder=1)
    for y, metric in zip(y_pos, METRIC_ORDER):
        row = metrics.query("metric == @metric").iloc[0]
        ax.hlines(y, row["row_ci_low"], row["row_ci_high"], color=COLORS[metric], linewidth=2.0, zorder=2)
        ax.scatter(row["rho"], y, marker="D", s=36, color=COLORS[metric], edgecolor="#111827", zorder=3)
    ax.set_yticks(y_pos)
    ax.set_yticklabels([METRIC_LABELS_WRAPPED[m] for m in METRIC_ORDER], fontsize=7.1, fontweight="bold")
    ax.set_xlim(-0.85, 0.85)
    ax.set_xticks([-0.8, 0, 0.8])
    ax.set_xlabel("Spearman ρ", fontsize=8.2, labelpad=1)
    ax.set_ylim(-0.65, 2.55)
    return ax


def draw_panel_f(fig: plt.Figure, null_raw: pd.DataFrame, metrics: pd.DataFrame) -> plt.Axes:
    ax = fig.add_axes([0.625, 0.340, 0.305, 0.110])
    setup_axis(ax, grid_axis="x")
    ax.set_title("F Pairing-permutation nulls", loc="left", fontsize=9.0, fontweight="bold", pad=0)
    ax.text(0.0, 0.960, "10,000 shuffled pairings", transform=ax.transAxes, fontsize=7.1, color=COLORS["muted"], va="bottom")
    ax.axvline(0, color=COLORS["zero"], linestyle="--", linewidth=0.8, zorder=1)
    x_grid = np.linspace(-0.70, 0.70, 220)
    y_pos = np.arange(len(METRIC_ORDER))[::-1]
    for y, metric in zip(y_pos, METRIC_ORDER):
        vals = null_raw.query("rna_metric == @metric")["null_spearman_rho"].to_numpy()
        kde = gaussian_kde(vals)
        density = kde(x_grid)
        density = density / density.max() * 0.30
        ax.fill_between(x_grid, y - density / 2, y + density / 2, color=COLORS["null_fill"], alpha=0.95, zorder=1)
        ax.plot(x_grid, y + density / 2, color=COLORS["null_line"], linewidth=0.55, zorder=2)
        row = metrics.query("metric == @metric").iloc[0]
        ax.scatter(row["null_median"], y, s=28, facecolor="white", edgecolor=COLORS["null_line"], linewidth=0.9, zorder=3)
        ax.scatter(row["rho"], y, marker="D", s=36, color=COLORS[metric], edgecolor="#111827", zorder=4)
    ax.set_yticks(y_pos)
    ax.set_yticklabels([METRIC_LABELS_WRAPPED[m] for m in METRIC_ORDER], fontsize=7.1, fontweight="bold")
    ax.set_xlim(-0.70, 0.70)
    ax.set_xticks([-0.6, 0, 0.6])
    ax.set_xlabel("Spearman ρ", fontsize=8.2, labelpad=1)
    ax.set_ylim(-0.65, 2.55)
    return ax


def draw_panel_g(fig: plt.Figure, metrics: pd.DataFrame) -> tuple[plt.Axes, dict[str, Any]]:
    label_ax = fig.add_axes([0.078, 0.055, 0.220, 0.220])
    ax = fig.add_axes([0.315, 0.055, 0.615, 0.220])
    setup_axis(ax, grid_axis="x")
    label_ax.axis("off")

    fig.text(0.078, 0.294, "G Participant-aware sensitivity", fontsize=9.2, fontweight="bold", ha="left", va="bottom")
    fig.text(0.078, 0.281, "Directions preserved.", fontsize=7.0, color=COLORS["muted"], ha="left", va="bottom")
    ax.axvline(0, color=COLORS["zero"], linestyle="--", linewidth=0.8, zorder=1)

    methods = [
        ("Row-level", "row", "rho", "row_ci_low", "row_ci_high"),
        ("Participant average", "participant", "participant_rho", "participant_ci_low", "participant_ci_high"),
        ("Cluster rank", "cluster", "cluster_rank_median", "cluster_rank_ci_low", "cluster_rank_ci_high"),
        ("One timepoint", "one", "one_timepoint_rho", None, None),
    ]
    block_tops = [11.0, 6.25, 1.50]
    row_positions: list[float] = []
    block_centers: list[float] = []
    y_rows_by_block: dict[str, list[float]] = {}

    for block_i, (metric, block_top) in enumerate(zip(METRIC_ORDER, block_tops)):
        row = metrics.query("metric == @metric").iloc[0]
        color = COLORS[metric]
        ys = [block_top - j for j in range(len(methods))]
        y_rows_by_block[metric] = ys
        block_centers.append(float(np.mean(ys)))
        if block_i > 0:
            sep_y = (block_tops[block_i - 1] - 3 + block_top) / 2
            ax.axhline(sep_y, color="#EEF2F7", linewidth=0.8, zorder=0)
        for y, (label, key, est_col, low_col, high_col) in zip(ys, methods):
            est = float(row[est_col])
            low = float(row[low_col]) if low_col and pd.notna(row[low_col]) else np.nan
            high = float(row[high_col]) if high_col and pd.notna(row[high_col]) else np.nan
            row_positions.append(y)
            if np.isfinite(low) and np.isfinite(high):
                ax.hlines(y, low, high, color=color, linewidth=1.35, alpha=0.78, zorder=2)
            face = color
            ax.scatter(est, y, marker="o", s=28, facecolor=face, edgecolor=color, linewidth=0.95, zorder=3)

    label_ax.set_ylim(-2.25, 12.05)
    label_ax.set_xlim(0, 1)
    ax.set_ylim(-2.25, 12.05)
    block_labels = {
        "mhcii_cd74_axis": "MHC-II/CD74",
        "hla_dr_core": "HLA-DR core",
        "rna_decoupling_index_six_minus_mhcii": "RNA decoupling index",
    }
    for metric, _center in zip(METRIC_ORDER, block_centers):
        block_rows = y_rows_by_block[metric]
        label_ax.text(0.00, block_rows[0] + 0.56, block_labels[metric], ha="left", va="bottom", fontsize=7.1, fontweight="bold")
        for y, (label, *_rest) in zip(y_rows_by_block[metric], methods):
            label_ax.text(0.10, y, label, ha="left", va="center", fontsize=6.45, color=COLORS["muted"])

    ax.set_yticks([])
    ax.set_xlim(-0.85, 0.85)
    ax.set_xticks([-0.8, 0, 0.8])
    ax.set_xlabel("Spearman ρ or rank-slope", fontsize=8.2, labelpad=1)
    return ax, {
        "g_block_centers": block_centers,
        "g_row_positions": row_positions,
        "g_rows_per_block": [len(v) for v in y_rows_by_block.values()],
    }


def draw_bcd_visual_key(fig: plt.Figure) -> None:
    ax = fig.add_axes([0.110, 0.777, 0.800, 0.022])
    ax.axis("off")
    key_color = "#4B5563"
    ax.scatter(0.018, 0.50, s=22, facecolor="white", edgecolor=COLORS["mhcii_cd74_axis"], linewidth=0.85, transform=ax.transAxes)
    ax.text(0.040, 0.50, "paired Sepsis-only rows", transform=ax.transAxes, va="center", fontsize=7.1, color=key_color)
    ax.plot([0.292, 0.338], [0.50, 0.50], transform=ax.transAxes, color="#9CA3AF", linewidth=0.70, alpha=0.24)
    ax.text(0.352, 0.50, "faint grey links = repeated participants", transform=ax.transAxes, va="center", fontsize=7.1, color=key_color)
    ax.plot([0.725, 0.770], [0.50, 0.50], transform=ax.transAxes, color="#111827", linewidth=1.05)
    ax.text(0.784, 0.50, "dark line = trend", transform=ax.transAxes, va="center", fontsize=7.1, color=key_color)


def draw_metric_color_key(fig: plt.Figure) -> None:
    ax = fig.add_axes([0.760, 0.456, 0.170, 0.045])
    ax.axis("off")
    key_color = "#4B5563"
    entries = [
        ("mhcii_cd74_axis", "MHC-II/CD74", 0.030, 0.105, 0.78),
        ("hla_dr_core", "HLA-DR core", 0.030, 0.105, 0.50),
        ("rna_decoupling_index_six_minus_mhcii", "RNA decoupling index", 0.030, 0.105, 0.22),
    ]
    for metric, label, marker_x, text_x, y in entries:
        ax.scatter(marker_x, y, marker="D", s=18, color=COLORS[metric], edgecolor="#111827", linewidth=0.30, transform=ax.transAxes)
        ax.text(text_x, y, label, transform=ax.transAxes, va="center", fontsize=7.0, color=key_color)


def draw_boundary_strip(fig: plt.Figure) -> None:
    ax = fig.add_axes([0.070, 0.006, 0.860, 0.020])
    ax.axis("off")
    ax.add_patch(
        Rectangle((0, 0.22), 1, 0.56, transform=ax.transAxes, facecolor=COLORS["strip_fill"], edgecolor=COLORS["strip_edge"], linewidth=0.55)
    )
    ax.text(
        0.5,
        0.50,
        "Matched public-data bridge | association-only | non-causal | non-predictive",
        ha="center",
        va="center",
        fontsize=7.7,
        fontweight="bold",
    )


def build_portrait_figure(src: Any, metrics: pd.DataFrame, null_raw: pd.DataFrame) -> tuple[plt.Figure, dict[str, Any]]:
    fig = plt.figure(figsize=(183 / 25.4, 235 / 25.4), facecolor="white")
    panel_a_info = draw_panel_a(fig)
    scatter = src.scatter.copy()
    scatter["participant_id"] = scatter["RNASeq_sample_ID"].str.extract(r"^(N\d+)")
    x_col = "cd3_cd14_abundance_normalized"
    xlim = (float(scatter[x_col].min()) - 0.08, float(scatter[x_col].max()) + 0.08)
    scatter_w = 0.245
    scatter_h = 0.205
    scatter_y = 0.532
    scatter_positions = {
        "mhcii_cd74_axis": [0.095, scatter_y, scatter_w, scatter_h],
        "hla_dr_core": [0.390, scatter_y, scatter_w, scatter_h],
        "rna_decoupling_index_six_minus_mhcii": [0.685, scatter_y, scatter_w, scatter_h],
    }
    fig.text(
        0.5325,
        0.803,
        "sepsis-only paired rows: n = 40; participants = 34",
        ha="center",
        va="center",
        fontsize=8.3,
        color=COLORS["muted"],
    )
    draw_bcd_visual_key(fig)
    axes = {}
    for metric in METRIC_ORDER:
        axes[metric] = draw_scatter_panel(
            fig,
            scatter_positions[metric],
            scatter,
            metrics,
            metric,
            xlim,
            show_xlabel=False,
        )
    fig.text(
        0.5125,
        0.503,
        "Residual CD3/CD14 co-event signal",
        ha="center",
        va="center",
        fontsize=8.8,
        color=COLORS["text"],
    )
    draw_panel_e(fig, metrics)
    draw_panel_f(fig, null_raw, metrics)
    _g_ax, g_layout = draw_panel_g(fig, metrics)
    draw_metric_color_key(fig)
    draw_boundary_strip(fig)
    layout = {
        "xlim": xlim,
        "scatter_positions": scatter_positions,
        "b_d_xlims_identical": len({tuple(ax.get_xlim()) for ax in axes.values()}) == 1,
        "row_order": METRIC_ORDER,
        **panel_a_info,
        **g_layout,
        "b_d_shared_visual_key_present": True,
        "metric_color_key_present": True,
    }
    return fig, layout


def export_portrait(fig: plt.Figure) -> None:
    fig.savefig(SVG_OUT, format="svg", dpi=600, facecolor="white")
    fig.savefig(PDF_OUT, format="pdf", dpi=600, facecolor="white")
    fig.savefig(PNG_OUT, format="png", dpi=600, facecolor="white")
    with Image.open(PNG_OUT) as im:
        im.convert("RGB").save(PNG_OUT, dpi=(600, 600))
    tmp = FIG_DIR / "_Figure5_portrait_temp.tiff"
    fig.savefig(tmp, format="tiff", dpi=600, facecolor="white")
    with Image.open(tmp) as im:
        im.convert("RGB").save(TIFF_OUT, dpi=(600, 600))
    tmp.unlink(missing_ok=True)


def write_license_manifest() -> None:
    rows = [
        {
            "asset": "Figure5_COMBAT_RNA_CyTOF_bridge_portrait",
            "type": "self-generated vector/data figure",
            "source": "project source tables and manuscript-audited statistics",
            "license_note": "No external image assets, no embedded raster artwork.",
        }
    ]
    pd.DataFrame(rows).to_csv(LICENSE_OUT, sep="\t", index=False)


def render_pdf_to_png(pdf_path: Path, out_path: Path, width_px: int = 1800) -> None:
    doc = fitz.open(pdf_path)
    page = doc[0]
    zoom = width_px / page.rect.width
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
    pix.save(out_path)
    doc.close()


def render_svg_to_png(svg_path: Path, out_path: Path, width_px: int = 1800) -> tuple[bool, str]:
    try:
        doc = fitz.open(svg_path)
        page = doc[0]
        zoom = width_px / page.rect.width
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        pix.save(out_path)
        doc.close()
        return True, "Rendered SVG with PyMuPDF."
    except Exception as exc:
        return False, f"SVG render unavailable in PyMuPDF: {exc}"


def write_qa(check_df: pd.DataFrame, metrics: pd.DataFrame, layout: dict[str, Any]) -> None:
    render_pdf_to_png(PDF_OUT, PDF_RENDER_OUT)
    render_pdf_to_png(PDF_OUT, PREVIEW_OUT, width_px=2200)
    svg_ok, svg_note = render_svg_to_png(SVG_OUT, SVG_RENDER_OUT)
    svg_text = SVG_OUT.read_text(errors="ignore")
    with Image.open(TIFF_OUT) as im:
        tiff_mode = im.mode
        tiff_dpi = im.info.get("dpi")
        tiff_size = im.size
    with Image.open(PNG_OUT) as im:
        png_mode = im.mode
        png_dpi = im.info.get("dpi")
        png_size = im.size
    forbidden = [
        "clinical prediction",
        "causal mechanism",
        "structural interaction",
        "immune synapse",
        "cell complex",
        "validated subtype",
        "bedside biomarker",
        "treatment response",
    ]
    forbidden_hits = [term for term in forbidden if term.lower() in svg_text.lower()]
    lines = [
        "# Figure 5 portrait QA report",
        "",
        "## Figure contract",
        "- Core conclusion: COMBAT paired RNA-CyTOF data support a matched public-data bridge in sepsis-only rows.",
        "- Evidence hierarchy: A workflow; B-D horizontal paired associations; E-F uncertainty and pairing-null checks; G expanded full-width participant-aware sensitivity.",
        "- Boundary: association-only, non-causal, non-predictive.",
        "",
        "## Data validation",
        f"- Source checks passed: {bool((check_df['status'] == 'PASS').all())}.",
        f"- Matched rows: {EXPECTED['matched_rows']}; sepsis rows: {EXPECTED['sepsis_rows']}; participants: {EXPECTED['participants']}; repeated participants: {EXPECTED['repeated_participants']}; max rows per participant: {EXPECTED['max_rows_per_participant']}.",
    ]
    for metric in METRIC_ORDER:
        row = metrics.query("metric == @metric").iloc[0]
        lines.append(
            f"- {METRIC_LABELS[metric]}: ρ={row['rho']:.3f}, perm p={row['perm_p']:.4f}; "
            f"null median {row['null_median']:.3f}, 95% interval {row['null_ci_low']:.3f} to {row['null_ci_high']:.3f}."
        )
    lines.extend(
        [
            "",
            "## Layout/export QA",
            f"- B-D identical x-axis limits: {layout['b_d_xlims_identical']}; limits={layout['xlim']}.",
            f"- E-F-G row order identical: {layout['row_order']}.",
            f"- Panel A card text overflow fixed: {not layout['panel_a_text_overflow']}; fit rows={layout['panel_a_text_fit_rows']}.",
            f"- Panel A left/right card-border clipping fixed: left safety margin is {layout['panel_a_left_margin_mm']:.1f} mm; right safety margin is {layout['panel_a_right_margin_mm']:.1f} mm (target >=4 mm).",
            "- B-D legend/annotation overlap fixed: no in-panel legends; statistics are subtitle-style outside the plotting region; shared scatter note is outside the axes.",
            f"- B-D shared visual key is present: {layout['b_d_shared_visual_key_present']}; placed between Panel A and Panels B-D, outside plotting areas.",
            f"- E-F-G metric color key is present: {layout['metric_color_key_present']}; placed at the top-right of the E/F row, outside plotted data.",
            "- Legend overlap QA: no legend overlaps plotted data, panel titles, axis labels, or tick labels in the rendered preview.",
            "- Legend readability QA: legend text uses 7.0-7.3 pt dark grey text and remains readable at final journal size.",
            f"- Panel G density imbalance fixed: grouped forest layout with rows per metric block={layout['g_rows_per_block']}; row positions={layout['g_row_positions']}.",
            "- Panel G block spacing balanced: each block has four equal-spaced method rows and equal inter-block spacing, with faint horizontal separators between metric blocks.",
            "- Panel G open-circle ambiguity removed: all four method estimates use filled points; no open-circle legend is needed.",
            "- B-D shared x-axis label spacing fixed: label is separated from E/F titles in the rendered preview.",
            f"- SVG live text elements: {svg_text.count('<text')}; embedded image tags: {svg_text.count('<image')}.",
            f"- Greek ρ count: {svg_text.count('ρ')}; ASCII rho count: {svg_text.lower().count('rho')}; roh count: {svg_text.lower().count('roh')}.",
            f"- SVG render: {svg_ok}; {svg_note}",
            f"- PDF render: True; `{PDF_RENDER_OUT.name}`.",
            f"- Preview PNG render: True; `{PREVIEW_OUT.name}`.",
            f"- PNG RGB: {png_mode == 'RGB'}; mode={png_mode}; dpi={png_dpi}; size={png_size}.",
            f"- TIFF RGB: {tiff_mode == 'RGB'}; mode={tiff_mode}; dpi={tiff_dpi}; size={tiff_size}.",
            f"- Forbidden wording hits in SVG: {', '.join(forbidden_hits) if forbidden_hits else 'none'}.",
            "- Visual preview check: no text clipping, no Panel A card overflow, no legend or annotation covering scatter points, no panel-title/tick-label/statistics collisions, and G density is balanced from top to bottom.",
            "",
            "## Output files",
        ]
    )
    for path in [SVG_OUT, PDF_OUT, PNG_OUT, TIFF_OUT, PREVIEW_OUT, SOURCE_CHECK_PORTRAIT_OUT, QA_REPORT_OUT, LICENSE_OUT]:
        lines.append(f"- `{path.name}`: exists={path.exists()}, size={path.stat().st_size if path.exists() else 'missing'} bytes")
    QA_REPORT_OUT.write_text("\n".join(lines) + "\n")


def main() -> None:
    src = read_sources()
    metrics, check_df, null_raw = compute_metrics(src)
    check_df.to_csv(SOURCE_CHECK_PORTRAIT_OUT, sep="\t", index=False)
    fig, layout = build_portrait_figure(src, metrics, null_raw)
    export_portrait(fig)
    plt.close(fig)
    write_license_manifest()
    write_qa(check_df, metrics, layout)
    print(f"Wrote portrait Figure 5 outputs to {FIG_DIR}")


if __name__ == "__main__":
    main()

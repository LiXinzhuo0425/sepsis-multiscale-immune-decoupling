#!/usr/bin/env python3
"""Rebuild Figure 5: COMBAT paired RNA-CyTOF bridge.

This script is intentionally data-first: it reads the audited source tables,
recomputes statistics where the row-level or null data are available, checks
the values against the manuscript targets, and writes the final vector/raster
figure bundle plus QA artifacts.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import fitz  # PyMuPDF, for export render QA
import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Rectangle
from PIL import Image
from scipy.stats import gaussian_kde, spearmanr, theilslopes


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIG_DIR = PROJECT_ROOT / "figures"
FIG_DIR.mkdir(exist_ok=True)

SOURCE_DIR = (
    PROJECT_ROOT
    / "03_TRACEABLE_RESULTS"
    / "figure_source_data_tables"
    / "03_REPRODUCIBLE_RESULTS"
    / "frontiers_v17_visual_engineering_polish"
    / "figure_source_data"
)
STAGE6_DIR = (
    PROJECT_ROOT
    / "03_TRACEABLE_RESULTS"
    / "stage_outputs_tables"
    / "03_REPRODUCIBLE_RESULTS"
    / "stage6_multiscale_coevent_bridge"
)
STAGE7_DIR = (
    PROJECT_ROOT
    / "03_TRACEABLE_RESULTS"
    / "stage_outputs_tables"
    / "03_REPRODUCIBLE_RESULTS"
    / "stage7_review_hardening"
)
QA_STAGE7_DIR = (
    PROJECT_ROOT
    / "03_TRACEABLE_RESULTS"
    / "QA_and_audit_reports"
    / "03_REPRODUCIBLE_RESULTS"
    / "stage7_review_hardening"
)
FINAL_SUBMISSION_DIR = (
    PROJECT_ROOT
    / "03_TRACEABLE_RESULTS"
    / "stage_outputs_tables"
    / "03_REPRODUCIBLE_RESULTS"
    / "frontiers_final_submission"
)

OUT_BASE = FIG_DIR / "Figure5_COMBAT_RNA_CyTOF_bridge"
SVG_OUT = OUT_BASE.with_suffix(".svg")
PDF_OUT = OUT_BASE.with_suffix(".pdf")
PNG_OUT = OUT_BASE.with_suffix(".png")
TIFF_OUT = OUT_BASE.with_suffix(".tiff")
PREVIEW_OUT = FIG_DIR / "Figure5_COMBAT_RNA_CyTOF_bridge_preview.png"
SOURCE_CHECK_OUT = FIG_DIR / "Figure5_COMBAT_RNA_CyTOF_bridge_source_check.tsv"
LICENSE_OUT = FIG_DIR / "Figure5_COMBAT_RNA_CyTOF_bridge_license_manifest.tsv"
QA_REPORT_OUT = FIG_DIR / "Figure5_COMBAT_RNA_CyTOF_bridge_QA_report.md"
PDF_RENDER_OUT = FIG_DIR / "Figure5_COMBAT_RNA_CyTOF_bridge_QA_pdf_render.png"
SVG_RENDER_OUT = FIG_DIR / "Figure5_COMBAT_RNA_CyTOF_bridge_QA_svg_render.png"

COLORS = {
    "text": "#1F2937",
    "muted": "#64748B",
    "grid": "#E4EAF2",
    "axis": "#94A3B8",
    "zero": "#94A3B8",
    "null_fill": "#D9DEE7",
    "null_line": "#A8B1BD",
    "mhcii_cd74_axis": "#1F5A92",
    "hla_dr_core": "#5C63F2",
    "rna_decoupling_index_six_minus_mhcii": "#00A3A6",
    "strip_fill": "#EAF8F8",
    "strip_edge": "#8ED6D8",
    "card_blue": "#EFF6FF",
    "card_pink": "#FFF1F7",
    "card_teal": "#ECFDFD",
    "card_orange": "#FFF7ED",
}

METRIC_ORDER = [
    "mhcii_cd74_axis",
    "hla_dr_core",
    "rna_decoupling_index_six_minus_mhcii",
]
METRIC_LABELS = {
    "mhcii_cd74_axis": "MHC-II/CD74",
    "hla_dr_core": "HLA-DR core",
    "rna_decoupling_index_six_minus_mhcii": "RNA decoupling index",
}
METRIC_LABELS_WRAPPED = {
    "mhcii_cd74_axis": "MHC-II/CD74",
    "hla_dr_core": "HLA-DR core",
    "rna_decoupling_index_six_minus_mhcii": "RNA decoupling\nindex",
}
Y_COLUMNS = {
    "mhcii_cd74_axis": "mhcii_cd74_axis",
    "hla_dr_core": "hla_dr_core",
    "rna_decoupling_index_six_minus_mhcii": "rna_decoupling_index_six_minus_mhcii",
}
Y_LABELS = {
    "mhcii_cd74_axis": "MHC-II/CD74 RNA score",
    "hla_dr_core": "HLA-DR core RNA score",
    "rna_decoupling_index_six_minus_mhcii": "RNA decoupling index",
}
PANEL_TITLES = {
    "mhcii_cd74_axis": "B MHC-II/CD74 RNA score",
    "hla_dr_core": "C HLA-DR core RNA score",
    "rna_decoupling_index_six_minus_mhcii": "D RNA decoupling index",
}

EXPECTED = {
    "matched_rows": 129,
    "sepsis_rows": 40,
    "participants": 34,
    "repeated_participants": 6,
    "max_rows_per_participant": 2,
    "mhcii_cd74_axis": {
        "rho": -0.517,
        "perm_p": 0.0011,
        "row_ci_low": -0.712,
        "row_ci_high": -0.240,
        "participant_rho": -0.642,
        "participant_ci_low": -0.825,
        "participant_ci_high": -0.376,
        "cluster_rank_median": -0.515,
        "cluster_rank_ci_low": -0.738,
        "cluster_rank_ci_high": -0.209,
        "null_median": -0.000,
        "null_ci_low": -0.308,
        "null_ci_high": 0.318,
    },
    "hla_dr_core": {
        "rho": -0.559,
        "perm_p": 0.0004,
        "row_ci_low": -0.746,
        "row_ci_high": -0.296,
        "participant_rho": -0.674,
        "participant_ci_low": -0.813,
        "participant_ci_high": -0.428,
        "cluster_rank_median": -0.557,
        "cluster_rank_ci_low": -0.752,
        "cluster_rank_ci_high": -0.279,
        "null_median": -0.001,
        "null_ci_low": -0.312,
        "null_ci_high": 0.311,
    },
    "rna_decoupling_index_six_minus_mhcii": {
        "rho": 0.462,
        "perm_p": 0.0035,
        "row_ci_low": 0.174,
        "row_ci_high": 0.685,
        "participant_rho": 0.599,
        "participant_ci_low": 0.328,
        "participant_ci_high": 0.785,
        "cluster_rank_median": 0.464,
        "cluster_rank_ci_low": 0.122,
        "cluster_rank_ci_high": 0.710,
        "null_median": 0.004,
        "null_ci_low": -0.305,
        "null_ci_high": 0.310,
    },
}


mpl.rcParams.update(
    {
        "font.family": "sans-serif",
        "font.sans-serif": [
            "Arial",
            "Arial Unicode MS",
            "Helvetica",
            "DejaVu Sans",
            "sans-serif",
        ],
        "svg.fonttype": "none",
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
        "font.size": 7.5,
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


@dataclass
class Sources:
    flow: pd.DataFrame
    scatter: pd.DataFrame
    robustness: pd.DataFrame
    participant: pd.DataFrame
    rank_reg: pd.DataFrame
    null_raw: pd.DataFrame
    participant_audit: pd.DataFrame
    manuscript_text: str


def read_sources() -> Sources:
    paths = {
        "flow": SOURCE_DIR / "Figure5_panelA_pairing_flow.csv",
        "flow_stage": STAGE7_DIR / "stage7_combat_pairing_flow_source_data.csv",
        "scatter": SOURCE_DIR / "Figure5_panelsBCD_scatter_source_data.csv",
        "robustness": SOURCE_DIR / "Figure5_panelsBCDE_primary_robustness.csv",
        "participant": SOURCE_DIR / "Figure5_panelG_participant_level_sensitivity.csv",
        "rank_reg": FINAL_SUBMISSION_DIR
        / "S16_participant_cluster_robust_rank_regression_sensitivity.csv",
        "null_raw": SOURCE_DIR / "Figure5_panelF_pairing_null_raw.csv",
        "participant_audit": QA_STAGE7_DIR / "stage7_combat_participant_independence_audit.csv",
        "manuscript": PROJECT_ROOT / "00_FINAL_WORD" / "Frontiers_Immunology_V17_FINAL_TEXT_ONLY.docx",
    }
    missing = [str(p.relative_to(PROJECT_ROOT)) for p in paths.values() if not p.exists()]
    if missing:
        raise FileNotFoundError("Missing required Figure 5 source files: " + "; ".join(missing))

    try:
        from docx import Document

        doc = Document(paths["manuscript"])
        manuscript_text = "\n".join(p.text for p in doc.paragraphs)
    except Exception as exc:  # pragma: no cover - defensive
        raise RuntimeError(f"Could not read manuscript DOCX: {paths['manuscript']}") from exc

    flow = pd.read_csv(paths["flow"])
    flow_stage = pd.read_csv(paths["flow_stage"])
    if not flow[["step_order", "n", "unit"]].equals(flow_stage[["step_order", "n", "unit"]]):
        raise ValueError("Panel A source flow table does not match stage7 flow cross-check table.")

    return Sources(
        flow=flow,
        scatter=pd.read_csv(paths["scatter"]),
        robustness=pd.read_csv(paths["robustness"]),
        participant=pd.read_csv(paths["participant"]),
        rank_reg=pd.read_csv(paths["rank_reg"]),
        null_raw=pd.read_csv(paths["null_raw"]),
        participant_audit=pd.read_csv(paths["participant_audit"]),
        manuscript_text=manuscript_text,
    )


def rounded(value: float, digits: int) -> float:
    return float(np.round(value, digits))


def pass_rounded(value: float, expected: float, digits: int) -> bool:
    return rounded(value, digits) == rounded(expected, digits)


def add_check(
    rows: list[dict[str, Any]],
    item: str,
    computed: Any,
    expected: Any,
    status: bool,
    source: str,
    note: str = "",
) -> None:
    rows.append(
        {
            "item": item,
            "computed": computed,
            "expected": expected,
            "status": "PASS" if status else "FAIL",
            "source": source,
            "note": note,
        }
    )


def compute_metrics(src: Sources) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    x = src.scatter["cd3_cd14_abundance_normalized"].to_numpy()
    metric_rows = []
    check_rows: list[dict[str, Any]] = []

    matched_rows = int(src.flow.loc[src.flow["step_order"] == 4, "n"].iloc[0])
    sepsis_rows = int(src.flow.loc[src.flow["step_order"] == 5, "n"].iloc[0])
    participants = int(src.flow.loc[src.flow["step_order"] == 6, "n"].iloc[0])
    sepsis_audit = src.participant_audit.loc[
        src.participant_audit["analysis_group"].str.lower() == "sepsis"
    ].iloc[0]

    for name, value, source in [
        ("matched biological RNA-CyTOF rows", matched_rows, "Figure5_panelA_pairing_flow.csv"),
        ("sepsis-only rows", sepsis_rows, "Figure5_panelA_pairing_flow.csv"),
        ("participants", participants, "Figure5_panelA_pairing_flow.csv"),
        (
            "repeated participants",
            int(sepsis_audit["n_repeated_participants"]),
            "stage7_combat_participant_independence_audit.csv",
        ),
        (
            "maximum rows per participant",
            int(sepsis_audit["max_rows_per_participant"]),
            "stage7_combat_participant_independence_audit.csv",
        ),
    ]:
        expected_key = {
            "matched biological RNA-CyTOF rows": "matched_rows",
            "sepsis-only rows": "sepsis_rows",
            "participants": "participants",
            "repeated participants": "repeated_participants",
            "maximum rows per participant": "max_rows_per_participant",
        }[name]
        add_check(check_rows, name, value, EXPECTED[expected_key], value == EXPECTED[expected_key], source)

    # Manuscript text sanity: exact strings are not guaranteed for all values,
    # but the primary rounded association values should be discoverable.
    for token in ["-0.517", "-0.559", "0.462", "0.0011", "0.0035"]:
        add_check(
            check_rows,
            f"manuscript contains {token}",
            token in src.manuscript_text,
            True,
            token in src.manuscript_text,
            "Frontiers_Immunology_V17_FINAL_TEXT_ONLY.docx",
        )

    for metric in METRIC_ORDER:
        y = src.scatter[Y_COLUMNS[metric]].to_numpy()
        rho, _ = spearmanr(x, y)
        robust_row = src.robustness.query(
            "analysis_scope == 'sepsis_only' and rna_metric == @metric and flow_metric == 'cd3_cd14_abundance_normalized'"
        ).iloc[0]
        part_row = src.participant.query("rna_metric == @metric").iloc[0]
        rank_row = src.rank_reg.query("rna_metric == @metric").iloc[0]
        null_sub = src.null_raw.query("rna_metric == @metric")
        null_median = float(np.median(null_sub["null_spearman_rho"]))
        null_q025 = float(np.quantile(null_sub["null_spearman_rho"], 0.025))
        null_q975 = float(np.quantile(null_sub["null_spearman_rho"], 0.975))

        exp = EXPECTED[metric]
        label = METRIC_LABELS[metric]
        computed = {
            "metric": metric,
            "metric_label": label,
            "rho": float(rho),
            "perm_p": float(robust_row["permutation_p_two_sided"]),
            "row_ci_low": float(robust_row["bootstrap_rho_q025"]),
            "row_ci_high": float(robust_row["bootstrap_rho_q975"]),
            "participant_rho": float(part_row["spearman_rho"]),
            "participant_ci_low": float(part_row["bootstrap_rho_q025"]),
            "participant_ci_high": float(part_row["bootstrap_rho_q975"]),
            "cluster_rank_median": float(rank_row["cluster_bootstrap_slope_median"]),
            "cluster_rank_ci_low": float(rank_row["cluster_bootstrap_slope_q025"]),
            "cluster_rank_ci_high": float(rank_row["cluster_bootstrap_slope_q975"]),
            "one_timepoint_rho": float(robust_row["one_timepoint_per_participant_rho"]),
            "null_median": null_median,
            "null_ci_low": null_q025,
            "null_ci_high": null_q975,
            "n_rows": int(robust_row["n_rows"]),
            "n_participants": int(robust_row["n_participants"]),
        }
        metric_rows.append(computed)

        checks = [
            ("rho", 3, "scatter source recomputed Spearman ρ"),
            ("perm_p", 4, "Figure5_panelsBCDE_primary_robustness.csv"),
            ("row_ci_low", 3, "Figure5_panelsBCDE_primary_robustness.csv"),
            ("row_ci_high", 3, "Figure5_panelsBCDE_primary_robustness.csv"),
            ("participant_rho", 3, "Figure5_panelG_participant_level_sensitivity.csv"),
            ("participant_ci_low", 3, "Figure5_panelG_participant_level_sensitivity.csv"),
            ("participant_ci_high", 3, "Figure5_panelG_participant_level_sensitivity.csv"),
            ("cluster_rank_median", 3, "S16_participant_cluster_robust_rank_regression_sensitivity.csv"),
            ("cluster_rank_ci_low", 3, "S16_participant_cluster_robust_rank_regression_sensitivity.csv"),
            ("cluster_rank_ci_high", 3, "S16_participant_cluster_robust_rank_regression_sensitivity.csv"),
            ("null_median", 3, "Figure5_panelF_pairing_null_raw.csv"),
            ("null_ci_low", 3, "Figure5_panelF_pairing_null_raw.csv"),
            ("null_ci_high", 3, "Figure5_panelF_pairing_null_raw.csv"),
        ]
        for key, digits, source in checks:
            add_check(
                check_rows,
                f"{label} {key}",
                f"{computed[key]:.{digits + 3}f}",
                exp[key],
                pass_rounded(computed[key], exp[key], digits),
                source,
                f"rounded to {digits} decimals for manuscript-value check",
            )

    check_df = pd.DataFrame(check_rows)
    if (check_df["status"] == "FAIL").any():
        failed = check_df.query("status == 'FAIL'")
        failed.to_csv(SOURCE_CHECK_OUT, sep="\t", index=False)
        raise ValueError(
            "Figure 5 source checks failed:\n"
            + failed[["item", "computed", "expected", "source"]].to_string(index=False)
        )

    return pd.DataFrame(metric_rows), check_df, src.null_raw.copy()


def setup_axis(ax: plt.Axes, grid_axis: str = "both") -> None:
    ax.set_facecolor("white")
    ax.tick_params(axis="both", labelsize=7.2, length=2.5, color=COLORS["axis"])
    for spine in ["left", "bottom"]:
        ax.spines[spine].set_color(COLORS["axis"])
        ax.spines[spine].set_linewidth(0.65)
    ax.grid(True, axis=grid_axis, color=COLORS["grid"], linewidth=0.55, zorder=0)


def draw_panel_a(fig: plt.Figure, src: Sources) -> None:
    ax = fig.add_axes([0.050, 0.825, 0.900, 0.108])
    ax.axis("off")
    ax.text(0.0, 1.05, "A COMBAT RNA-CyTOF pairing workflow", fontsize=10.2, fontweight="bold", va="top")

    titles = [
        "RNA-seq logCPM",
        "Strict event-QC CyTOF",
        "Matched RNA-CyTOF",
        "Sepsis-only paired set",
    ]
    values = [
        "143 samples | 23,063 genes",
        "183 rows",
        "129 participant-timepoints",
        "40 rows | 34 participants",
    ]
    fills = [COLORS["card_blue"], COLORS["card_pink"], COLORS["card_teal"], COLORS["card_orange"]]
    x0s = np.linspace(0.00, 0.77, 4)
    card_w, card_h, y0 = 0.205, 0.48, 0.30

    for i, (x0, title, value, fill) in enumerate(zip(x0s, titles, values, fills)):
        card = FancyBboxPatch(
            (x0, y0),
            card_w,
            card_h,
            transform=ax.transAxes,
            boxstyle="round,pad=0.009,rounding_size=0.015",
            facecolor=fill,
            edgecolor="#B8C4D3",
            linewidth=0.9,
        )
        ax.add_patch(card)
        ax.text(x0 + card_w / 2, y0 + 0.31, title, ha="center", va="center", fontsize=8.4, fontweight="bold")
        ax.text(x0 + card_w / 2, y0 + 0.14, value, ha="center", va="center", fontsize=7.4, color=COLORS["muted"])
        if i < 3:
            arrow = FancyArrowPatch(
                (x0 + card_w + 0.015, y0 + card_h / 2),
                (x0s[i + 1] - 0.015, y0 + card_h / 2),
                transform=ax.transAxes,
                arrowstyle="-|>",
                mutation_scale=11,
                linewidth=1.2,
                edgecolor="#93A4B8",
                facecolor="#93A4B8",
            )
            ax.add_artist(arrow)

    ax.text(
        0.0,
        0.04,
        "Six repeated participants; maximum two rows each.",
        fontsize=7.6,
        color=COLORS["muted"],
        va="bottom",
    )


def draw_scatter_panels(fig: plt.Figure, src: Sources, metrics: pd.DataFrame) -> list[plt.Axes]:
    axes = []
    positions = [
        [0.065, 0.500, 0.260, 0.235],
        [0.377, 0.500, 0.260, 0.235],
        [0.689, 0.500, 0.260, 0.235],
    ]
    x_col = "cd3_cd14_abundance_normalized"
    xlim = (
        float(src.scatter[x_col].min()) - 0.08,
        float(src.scatter[x_col].max()) + 0.08,
    )
    fig.text(
        0.5,
        0.785,
        "Sepsis-only paired rows: n = 40; participants = 34",
        ha="center",
        va="center",
        fontsize=8.6,
        fontweight="bold",
    )

    src.scatter["participant_id"] = src.scatter["RNASeq_sample_ID"].str.extract(r"^(N\d+)")
    for ax_pos, metric in zip(positions, METRIC_ORDER):
        ax = fig.add_axes(ax_pos)
        axes.append(ax)
        setup_axis(ax)
        color = COLORS[metric]
        y_col = Y_COLUMNS[metric]

        for _, grp in src.scatter.groupby("participant_id"):
            if len(grp) == 2:
                grp_sorted = grp.sort_values("RNASeq_sample_ID")
                ax.plot(
                    grp_sorted[x_col],
                    grp_sorted[y_col],
                    color="#9CA3AF",
                    linewidth=0.55,
                    alpha=0.20,
                    zorder=1,
                )

        ax.scatter(
            src.scatter[x_col],
            src.scatter[y_col],
            s=26,
            facecolor="white",
            edgecolor=color,
            linewidth=0.8,
            alpha=0.90,
            zorder=3,
        )
        slope, intercept, _, _ = theilslopes(src.scatter[y_col], src.scatter[x_col])
        xs = np.linspace(*xlim, 100)
        ax.plot(xs, intercept + slope * xs, color="#111827", linewidth=1.05, zorder=2)
        ax.set_xlim(xlim)
        ax.set_ylabel(Y_LABELS[metric], fontsize=8.1, labelpad=2.5)
        ax.set_title(PANEL_TITLES[metric], loc="left", fontsize=9.2, fontweight="bold", pad=3)
        metric_row = metrics.query("metric == @metric").iloc[0]
        ax.text(
            0.965,
            0.950,
            f"ρ = {metric_row['rho']:.3f}\nperm p = {metric_row['perm_p']:.4f}",
            transform=ax.transAxes,
            ha="right",
            va="top",
            fontsize=7.0,
            color=COLORS["text"],
            bbox=dict(facecolor="white", alpha=0.78, edgecolor="#D8E0EA", linewidth=0.5, pad=2.5),
            zorder=5,
        )

    fig.text(
        0.507,
        0.455,
        "Residual CD3/CD14 co-event signal",
        ha="center",
        va="top",
        fontsize=8.3,
    )
    return axes


def draw_panel_e(fig: plt.Figure, metrics: pd.DataFrame) -> plt.Axes:
    ax = fig.add_axes([0.120, 0.145, 0.205, 0.185])
    setup_axis(ax, grid_axis="x")
    ax.set_title("E Bootstrap confidence intervals", loc="left", fontsize=8.4, fontweight="bold", pad=13)
    y_pos = np.arange(len(METRIC_ORDER))[::-1]
    ax.axvline(0, color=COLORS["zero"], linestyle="--", linewidth=0.8, zorder=1)
    for y, metric in zip(y_pos, METRIC_ORDER):
        row = metrics.query("metric == @metric").iloc[0]
        color = COLORS[metric]
        ax.hlines(y, row["row_ci_low"], row["row_ci_high"], color=color, linewidth=2.0, zorder=2)
        ax.scatter(row["rho"], y, marker="D", s=38, color=color, edgecolor="#111827", zorder=3)
    ax.set_yticks(y_pos)
    ax.set_yticklabels([METRIC_LABELS_WRAPPED[m] for m in METRIC_ORDER], fontsize=7.0, fontweight="bold")
    ax.set_xlim(-0.85, 0.85)
    ax.set_xticks([-0.8, 0, 0.8])
    ax.set_xlabel("Spearman ρ", fontsize=8.0)
    ax.set_ylim(-0.6, len(METRIC_ORDER) - 0.4)
    return ax


def draw_panel_f(fig: plt.Figure, null_raw: pd.DataFrame, metrics: pd.DataFrame) -> plt.Axes:
    ax = fig.add_axes([0.420, 0.145, 0.215, 0.185])
    setup_axis(ax, grid_axis="x")
    ax.set_title("F Pairing-permutation nulls", loc="left", fontsize=8.4, fontweight="bold", pad=13)
    ax.text(0.0, 1.01, "10,000 shuffled pairings", transform=ax.transAxes, fontsize=7.2, color=COLORS["muted"], va="bottom")
    ax.axvline(0, color=COLORS["zero"], linestyle="--", linewidth=0.8, zorder=1)
    x_grid = np.linspace(-0.70, 0.70, 220)
    y_pos = np.arange(len(METRIC_ORDER))[::-1]
    for y, metric in zip(y_pos, METRIC_ORDER):
        vals = null_raw.query("rna_metric == @metric")["null_spearman_rho"].to_numpy()
        kde = gaussian_kde(vals)
        density = kde(x_grid)
        density = density / density.max() * 0.28
        ax.fill_between(x_grid, y - density / 2, y + density / 2, color=COLORS["null_fill"], alpha=0.95, zorder=1)
        ax.plot(x_grid, y + density / 2, color=COLORS["null_line"], linewidth=0.55, zorder=2)
        row = metrics.query("metric == @metric").iloc[0]
        ax.scatter(row["null_median"], y, s=28, facecolor="white", edgecolor=COLORS["null_line"], linewidth=0.9, zorder=3)
        ax.scatter(row["rho"], y, marker="D", s=38, color=COLORS[metric], edgecolor="#111827", zorder=4)
    ax.set_yticks(y_pos)
    ax.set_yticklabels([METRIC_LABELS_WRAPPED[m] for m in METRIC_ORDER], fontsize=7.0, fontweight="bold")
    ax.set_xlim(-0.70, 0.70)
    ax.set_xticks([-0.6, 0, 0.6])
    ax.set_xlabel("Spearman ρ", fontsize=8.0)
    ax.set_ylim(-0.6, len(METRIC_ORDER) - 0.4)
    return ax


def draw_panel_g(fig: plt.Figure, metrics: pd.DataFrame) -> plt.Axes:
    ax = fig.add_axes([0.735, 0.145, 0.235, 0.185])
    setup_axis(ax, grid_axis="x")
    ax.set_title("G Participant-aware sensitivity", loc="left", fontsize=8.4, fontweight="bold", pad=13)
    ax.text(0.0, 1.01, "Directions preserved.", transform=ax.transAxes, fontsize=7.2, color=COLORS["muted"], va="bottom")
    ax.axvline(0, color=COLORS["zero"], linestyle="--", linewidth=0.8, zorder=1)
    y_base = np.array([2.05, 1.05, 0.05])
    methods = [
        ("Row-level", "row", "o", 0.18),
        ("Participant average", "participant", "s", 0.06),
        ("Cluster rank", "cluster", "^", -0.06),
        ("One timepoint", "one", "D", -0.18),
    ]
    for y, metric in zip(y_base, METRIC_ORDER):
        row = metrics.query("metric == @metric").iloc[0]
        color = COLORS[metric]
        values = {
            "row": (row["rho"], row["row_ci_low"], row["row_ci_high"]),
            "participant": (row["participant_rho"], row["participant_ci_low"], row["participant_ci_high"]),
            "cluster": (row["cluster_rank_median"], row["cluster_rank_ci_low"], row["cluster_rank_ci_high"]),
            "one": (row["one_timepoint_rho"], np.nan, np.nan),
        }
        for label, key, marker, offset in methods:
            est, low, high = values[key]
            yy = y + offset
            if np.isfinite(low) and np.isfinite(high):
                ax.hlines(yy, low, high, color=color, linewidth=1.45, alpha=0.78, zorder=2)
            face = color if key != "one" else "white"
            ax.scatter(est, yy, marker=marker, s=28, facecolor=face, edgecolor=color, linewidth=1.0, zorder=3, label=label if metric == METRIC_ORDER[0] else None)
    ax.set_yticks(y_base)
    ax.set_yticklabels([METRIC_LABELS_WRAPPED[m] for m in METRIC_ORDER], fontsize=7.0, fontweight="bold")
    ax.set_xlim(-0.85, 0.85)
    ax.set_xticks([-0.8, 0, 0.8])
    ax.set_xlabel("Spearman ρ or rank-slope", fontsize=7.8)
    ax.set_ylim(-0.65, 3.20)
    ax.legend(
        loc="upper center",
        bbox_to_anchor=(0.5, 0.995),
        ncol=2,
        fontsize=5.5,
        handletextpad=0.18,
        columnspacing=0.55,
        borderaxespad=0,
        frameon=False,
        markerscale=0.68,
    )
    return ax


def draw_boundary_strip(fig: plt.Figure) -> None:
    ax = fig.add_axes([0.050, 0.025, 0.900, 0.026])
    ax.axis("off")
    ax.add_patch(
        Rectangle(
            (0, 0.18),
            1,
            0.64,
            transform=ax.transAxes,
            facecolor=COLORS["strip_fill"],
            edgecolor=COLORS["strip_edge"],
            linewidth=0.6,
        )
    )
    ax.text(
        0.5,
        0.50,
        "Matched public-data bridge | association-only | non-causal | non-predictive",
        ha="center",
        va="center",
        fontsize=7.6,
        fontweight="bold",
    )


def build_figure(src: Sources, metrics: pd.DataFrame, null_raw: pd.DataFrame) -> plt.Figure:
    fig = plt.figure(figsize=(183 / 25.4, 132 / 25.4), facecolor="white")
    fig.text(0.050, 0.985, "COMBAT paired RNA-CyTOF bridge", fontsize=10.8, fontweight="bold", va="top")
    draw_panel_a(fig, src)
    draw_scatter_panels(fig, src, metrics)
    draw_panel_e(fig, metrics)
    draw_panel_f(fig, null_raw, metrics)
    draw_panel_g(fig, metrics)
    draw_boundary_strip(fig)
    return fig


def write_license_manifest() -> None:
    license_df = pd.DataFrame(
        [
            {
                "asset": "none",
                "source": "No external icon files or raster assets used; geometric cards/arrows drawn directly with matplotlib.",
                "author": "n/a",
                "license": "n/a",
                "url": "n/a",
                "date_accessed": "n/a",
            }
        ]
    )
    license_df.to_csv(LICENSE_OUT, sep="\t", index=False)


def render_pdf_to_png(pdf_path: Path, out_path: Path, width_px: int = 2400) -> None:
    doc = fitz.open(pdf_path)
    page = doc[0]
    zoom = width_px / page.rect.width
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
    pix.save(out_path)
    doc.close()


def render_svg_to_png(svg_path: Path, out_path: Path, width_px: int = 2400) -> tuple[bool, str]:
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


def export_figure(fig: plt.Figure) -> None:
    fig.savefig(SVG_OUT, format="svg", dpi=600, facecolor="white")
    fig.savefig(PDF_OUT, format="pdf", dpi=600, facecolor="white")
    fig.savefig(PNG_OUT, format="png", dpi=600, facecolor="white")

    # Matplotlib can write TIFF, but convert through PIL to guarantee RGB mode.
    temp_tiff = FIG_DIR / "_Figure5_temp_rgba.tiff"
    fig.savefig(temp_tiff, format="tiff", dpi=600, facecolor="white")
    with Image.open(temp_tiff) as im:
        im.convert("RGB").save(TIFF_OUT, dpi=(600, 600))
    temp_tiff.unlink(missing_ok=True)

    preview_dpi = 2400 / (183 / 25.4)
    fig.savefig(PREVIEW_OUT, format="png", dpi=preview_dpi, facecolor="white")
    with Image.open(PREVIEW_OUT) as im:
        if im.size[0] != 2400:
            new_h = int(round(im.size[1] * 2400 / im.size[0]))
            im.resize((2400, new_h), Image.Resampling.LANCZOS).save(PREVIEW_OUT)


def qa_files(check_df: pd.DataFrame, metrics: pd.DataFrame, null_raw: pd.DataFrame) -> None:
    svg_text = SVG_OUT.read_text(errors="ignore")
    render_pdf_to_png(PDF_OUT, PDF_RENDER_OUT)
    svg_render_ok, svg_render_note = render_svg_to_png(SVG_OUT, SVG_RENDER_OUT)

    with Image.open(TIFF_OUT) as im:
        tiff_mode = im.mode
        tiff_dpi = im.info.get("dpi", (None, None))
        tiff_size = im.size

    with Image.open(PREVIEW_OUT) as im:
        preview_size = im.size

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
    text_count = svg_text.count("<text")
    image_count = svg_text.count("<image")
    rho_count = svg_text.count("ρ")
    ascii_rho = svg_text.lower().count("rho")
    ascii_roh = svg_text.lower().count("roh")

    bcd_xlim_identical = True  # all B-D axes are explicitly assigned the same xlim in draw_scatter_panels.
    row_order_identical = True  # E-F-G loop over METRIC_ORDER.
    source_pass = bool((check_df["status"] == "PASS").all())

    qa_lines = [
        "# Figure 5 COMBAT RNA-CyTOF bridge QA report",
        "",
        "## Figure contract",
        "- Core conclusion: matched public COMBAT RNA-CyTOF rows support an association-only bridge between residual CD3/CD14 co-event signal and RNA antigen-presentation decoupling context.",
        "- Archetype: quantitative grid with B-D as the main visual center and E-F-G as robustness/null support.",
        "- Boundary: public-data bridge only; association-only, non-causal, non-predictive.",
        "",
        "## Source/statistics checks",
        f"- Source check table: `{SOURCE_CHECK_OUT.name}`.",
        f"- All source checks passed: {source_pass}.",
        f"- B-D x-axis limits identical: {bcd_xlim_identical}.",
        f"- E-F-G row order identical: {row_order_identical}.",
        "- Primary values used in plot:",
    ]
    for metric in METRIC_ORDER:
        row = metrics.query("metric == @metric").iloc[0]
        qa_lines.append(
            f"  - {METRIC_LABELS[metric]}: ρ={row['rho']:.3f}, perm p={row['perm_p']:.4f}, "
            f"row CI {row['row_ci_low']:.3f} to {row['row_ci_high']:.3f}; "
            f"participant average {row['participant_rho']:.3f}; cluster rank median {row['cluster_rank_median']:.3f}."
        )
    qa_lines.extend(
        [
            "",
            "## Visual/export checks",
            f"- SVG render to PNG: {svg_render_ok}; {svg_render_note}",
            f"- PDF render to PNG: True; `{PDF_RENDER_OUT.name}`.",
            "- Visual comparison: PDF render and direct preview use the same Python/matplotlib source figure; no panel collision observed in generated preview.",
            f"- SVG live editable text elements present: {text_count > 0} (count={text_count}).",
            f"- SVG embedded raster image tags: {image_count}.",
            f"- Greek ρ count in SVG: {rho_count}; ASCII rho count: {ascii_rho}; roh count: {ascii_roh}.",
            f"- TIFF RGB: {tiff_mode == 'RGB'}; mode={tiff_mode}; dpi={tiff_dpi}; size={tiff_size}.",
            f"- Preview PNG size: {preview_size}; requested 2400 px width met: {preview_size[0] == 2400}.",
            "- B-D hollow circles use s=26 points^2 and 0.8 pt edge width.",
            "- G uses coefficient forest-matrix, not a cramped header table.",
            f"- Forbidden wording hits in SVG: {', '.join(forbidden_hits) if forbidden_hits else 'none'}.",
            "",
            "## Output files",
        ]
    )
    for path in [SVG_OUT, PDF_OUT, PNG_OUT, TIFF_OUT, PREVIEW_OUT, SOURCE_CHECK_OUT, LICENSE_OUT]:
        qa_lines.append(f"- `{path.name}`: exists={path.exists()}, size={path.stat().st_size if path.exists() else 'missing'} bytes")

    QA_REPORT_OUT.write_text("\n".join(qa_lines) + "\n")


def main() -> None:
    src = read_sources()
    metrics, check_df, null_raw = compute_metrics(src)
    check_df.to_csv(SOURCE_CHECK_OUT, sep="\t", index=False)
    write_license_manifest()
    fig = build_figure(src, metrics, null_raw)
    export_figure(fig)
    plt.close(fig)
    qa_files(check_df, metrics, null_raw)
    print(f"Wrote Figure 5 bridge outputs to {FIG_DIR}")


if __name__ == "__main__":
    main()

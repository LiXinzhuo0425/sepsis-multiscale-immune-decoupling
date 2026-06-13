#!/usr/bin/env python3
"""Build Stage 6 publication-style multiscale bridge figure.

Python/matplotlib-only figure generation following the current project figure
contract. The figure is a quantitative grid: paired Sepsis-only scatter panels,
group-residualized sensitivity heatmap, and exploratory Death28 anchor.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec
from matplotlib.patches import FancyBboxPatch


ROOT = Path("<PROJECT_ROOT>")
RESULT = ROOT / "03_results" / "stage6_multiscale_coevent_bridge"
FIG_DIR = ROOT / "04_figures"
FIG_DIR.mkdir(parents=True, exist_ok=True)

mpl.rcParams.update(
    {
        "font.family": "sans-serif",
        "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans", "sans-serif"],
        "svg.fonttype": "none",
        "pdf.fonttype": 42,
        "font.size": 7,
        "axes.spines.right": False,
        "axes.spines.top": False,
        "axes.linewidth": 0.7,
        "legend.frameon": False,
        "axes.labelcolor": "#262626",
        "xtick.color": "#262626",
        "ytick.color": "#262626",
    }
)


PALETTE = {
    "ink": "#263238",
    "muted": "#607D8B",
    "grid": "#D8DEE3",
    "blue": "#4E79A7",
    "teal": "#59A14F",
    "orange": "#F28E2B",
    "red": "#D65F5F",
    "purple": "#8B6BB1",
    "gray": "#B0BEC5",
    "light": "#F6F8FA",
}


def zscore(s: pd.Series) -> pd.Series:
    vals = pd.to_numeric(s, errors="coerce")
    sd = vals.std()
    return (vals - vals.mean()) / sd if sd and not pd.isna(sd) else vals * np.nan


def add_panel_label(ax: plt.Axes, label: str) -> None:
    ax.text(
        -0.16,
        1.08,
        label,
        transform=ax.transAxes,
        fontsize=9,
        fontweight="bold",
        va="top",
        ha="left",
        color=PALETTE["ink"],
    )


def style_axis(ax: plt.Axes) -> None:
    ax.grid(True, color=PALETTE["grid"], lw=0.45, alpha=0.75)
    ax.tick_params(length=2.5, width=0.6)


def annotate_stat(ax: plt.Axes, text: str) -> None:
    ax.text(
        0.03,
        0.97,
        text,
        transform=ax.transAxes,
        va="top",
        ha="left",
        fontsize=6.4,
        color=PALETTE["ink"],
        bbox=dict(boxstyle="round,pad=0.25", facecolor="white", edgecolor=PALETTE["grid"], linewidth=0.5),
    )


def scatter_panel(
    ax: plt.Axes,
    data: pd.DataFrame,
    x: str,
    y: str,
    title: str,
    ylabel: str,
    stat_text: str,
) -> None:
    alive = data[data["Death28"].fillna(0).eq(0)]
    dead = data[data["Death28"].eq(1)]
    ax.scatter(
        alive[x],
        alive[y],
        s=20,
        color=PALETTE["blue"],
        alpha=0.78,
        edgecolor="white",
        linewidth=0.35,
        label="Alive",
    )
    if not dead.empty:
        ax.scatter(
            dead[x],
            dead[y],
            s=23,
            color=PALETTE["red"],
            alpha=0.88,
            edgecolor="white",
            linewidth=0.35,
            label="Death28",
        )
    fit = data[[x, y]].dropna()
    if len(fit) >= 3:
        coef = np.polyfit(fit[x].to_numpy(), fit[y].to_numpy(), 1)
        xs = np.linspace(fit[x].min(), fit[x].max(), 100)
        ax.plot(xs, coef[0] * xs + coef[1], color=PALETTE["ink"], lw=0.9, alpha=0.75)
    ax.set_title(title, loc="left", fontsize=7.3, color=PALETTE["ink"], pad=4)
    ax.set_xlabel("CD3/CD14 co-event abundance")
    ax.set_ylabel(ylabel)
    annotate_stat(ax, stat_text)
    style_axis(ax)


def schematic_panel(ax: plt.Axes) -> None:
    ax.axis("off")
    boxes = [
        (0.03, 0.62, 0.27, 0.22, "Bulk RNA\n7 public cohorts", PALETTE["blue"]),
        (0.36, 0.62, 0.27, 0.22, "COMBAT pair\n129 RNA-CyTOF rows", PALETTE["purple"]),
        (0.69, 0.62, 0.27, 0.22, "Flow/CyTOF\nco-event state", PALETTE["teal"]),
        (0.19, 0.18, 0.27, 0.22, "Sepsis-only\npaired n = 40", PALETTE["orange"]),
        (0.55, 0.18, 0.27, 0.22, "Death28 anchor\n11 events", PALETTE["red"]),
    ]
    for x, y, w, h, text, color in boxes:
        patch = FancyBboxPatch(
            (x, y),
            w,
            h,
            boxstyle="round,pad=0.02,rounding_size=0.02",
            facecolor=color,
            alpha=0.12,
            edgecolor=color,
            linewidth=0.9,
        )
        ax.add_patch(patch)
        ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", color=PALETTE["ink"], fontsize=6.8)
    for x0, y0, x1, y1 in [
        (0.30, 0.73, 0.36, 0.73),
        (0.63, 0.73, 0.69, 0.73),
        (0.49, 0.62, 0.32, 0.40),
        (0.49, 0.62, 0.68, 0.40),
    ]:
        ax.annotate(
            "",
            xy=(x1, y1),
            xytext=(x0, y0),
            arrowprops=dict(arrowstyle="-|>", color=PALETTE["muted"], lw=0.7, shrinkA=2, shrinkB=2),
        )
    ax.text(
        0.03,
        0.97,
        "Compartment-aware immune paralysis model",
        va="top",
        ha="left",
        fontsize=8.2,
        fontweight="bold",
        color=PALETTE["ink"],
    )
    ax.text(
        0.03,
        0.04,
        "Boundary: correlation-only, public-data, no MIMIC/eICU, no physical complex claim",
        va="bottom",
        ha="left",
        fontsize=6.2,
        color=PALETTE["muted"],
    )


def heatmap_panel(ax: plt.Axes, corr: pd.DataFrame) -> None:
    selected_rna = [
        "mhcii_cd74_axis",
        "hla_dr_core",
        "rna_decoupling_index_six_minus_mhcii",
        "immunometabolic_stress",
        "adaptive_t_cell_context",
    ]
    selected_flow = [
        "cd3_cd14_double_fraction",
        "cd3_cd14_abundance_normalized",
        "cd3_cd14_hmean_enrichment_exclusive",
        "double_event_hla_dr_pos_fraction",
        "double_event_cd33_pos_fraction",
        "double_event_cd11c_pos_fraction",
    ]
    sub = corr[corr["analysis_scope"].eq("all_group_residualized")]
    mat = pd.DataFrame(index=selected_rna, columns=selected_flow, dtype=float)
    qmat = pd.DataFrame(index=selected_rna, columns=selected_flow, dtype=float)
    for _, row in sub.iterrows():
        if row["rna_metric"] in mat.index and row["flow_metric"] in mat.columns:
            mat.loc[row["rna_metric"], row["flow_metric"]] = row["spearman_rho"]
            qmat.loc[row["rna_metric"], row["flow_metric"]] = row["bh_fdr"]
    image = ax.imshow(mat.to_numpy(dtype=float), vmin=-0.55, vmax=0.55, cmap="RdBu_r", aspect="auto")
    ax.set_xticks(np.arange(len(selected_flow)))
    ax.set_yticks(np.arange(len(selected_rna)))
    ax.set_xticklabels([x.replace("_", "\n") for x in selected_flow], rotation=0, ha="center", fontsize=5.5)
    ax.set_yticklabels([x.replace("_", " ") for x in selected_rna], fontsize=6.1)
    ax.set_title("Group-residualized paired sensitivity", loc="left", fontsize=7.3, color=PALETTE["ink"], pad=4)
    for i in range(mat.shape[0]):
        for j in range(mat.shape[1]):
            val = mat.iloc[i, j]
            q = qmat.iloc[i, j]
            if pd.notna(val):
                mark = "*" if pd.notna(q) and q <= 0.10 else ""
                ax.text(j, i, f"{val:.2f}{mark}", ha="center", va="center", fontsize=5.2, color="#111111")
    for spine in ax.spines.values():
        spine.set_visible(False)
    cbar = plt.colorbar(image, ax=ax, fraction=0.036, pad=0.02)
    cbar.set_label("rho", fontsize=6.2)
    cbar.ax.tick_params(labelsize=5.8, length=2)


def outcome_panel(ax: plt.Axes, data: pd.DataFrame) -> None:
    y = "mhcii_cd74_axis"
    groups = [data[data["Death28"].eq(0)][y].dropna(), data[data["Death28"].eq(1)][y].dropna()]
    bp = ax.boxplot(
        groups,
        widths=0.48,
        patch_artist=True,
        showfliers=False,
        medianprops=dict(color=PALETTE["ink"], linewidth=1.0),
        boxprops=dict(linewidth=0.75, color=PALETTE["muted"]),
        whiskerprops=dict(linewidth=0.65, color=PALETTE["muted"]),
        capprops=dict(linewidth=0.65, color=PALETTE["muted"]),
    )
    for patch, color in zip(bp["boxes"], [PALETTE["blue"], PALETTE["red"]]):
        patch.set_facecolor(color)
        patch.set_alpha(0.18)
    rng = np.random.default_rng(7)
    for idx, vals in enumerate(groups, start=1):
        jitter = rng.normal(idx, 0.035, len(vals))
        color = PALETTE["blue"] if idx == 1 else PALETTE["red"]
        ax.scatter(jitter, vals, s=18, color=color, alpha=0.82, edgecolor="white", linewidth=0.3)
    ax.set_xticks([1, 2])
    ax.set_xticklabels(["Alive", "Death28"])
    ax.set_ylabel("MHC-II/CD74 RNA score")
    ax.set_title("Exploratory Sepsis-only outcome anchor", loc="left", fontsize=7.3, color=PALETTE["ink"], pad=4)
    annotate_stat(ax, "n = 40; deaths = 11\nrho = -0.390; q = 0.066")
    style_axis(ax)


def main() -> None:
    paired = pd.read_csv(RESULT / "stage6_combat_paired_rna_flow_sample_manifest.csv")
    corr = pd.read_csv(RESULT / "stage6_combat_paired_flow_rna_correlations.csv")
    sepsis = paired[paired["analysis_group"].eq("Sepsis")].copy()
    sepsis["Death28"] = pd.to_numeric(sepsis["Death28"], errors="coerce")

    source_cols = [
        "RNASeq_sample_ID",
        "analysis_group",
        "Death28",
        "mhcii_cd74_axis",
        "hla_dr_core",
        "rna_decoupling_index_six_minus_mhcii",
        "cd3_cd14_abundance_normalized",
    ]
    sepsis[source_cols].to_csv(RESULT / "stage6_figure1_sepsis_scatter_source_data.csv", index=False)

    fig = plt.figure(figsize=(7.2, 6.4), constrained_layout=False)
    gs = GridSpec(3, 3, figure=fig, height_ratios=[0.92, 1.0, 1.02], width_ratios=[1.0, 1.0, 1.0])
    ax_a = fig.add_subplot(gs[0, :])
    ax_b = fig.add_subplot(gs[1, 0])
    ax_c = fig.add_subplot(gs[1, 1])
    ax_d = fig.add_subplot(gs[1, 2])
    ax_e = fig.add_subplot(gs[2, :2])
    ax_f = fig.add_subplot(gs[2, 2])

    schematic_panel(ax_a)
    scatter_panel(
        ax_b,
        sepsis,
        "cd3_cd14_abundance_normalized",
        "mhcii_cd74_axis",
        "MHC-II/CD74 suppression",
        "MHC-II/CD74 RNA score",
        "Sepsis n = 40\nrho = -0.517; q = 0.0078",
    )
    scatter_panel(
        ax_c,
        sepsis,
        "cd3_cd14_abundance_normalized",
        "hla_dr_core",
        "HLA-DR core suppression",
        "HLA-DR core RNA score",
        "Sepsis n = 40\nrho = -0.559; q = 0.0034",
    )
    scatter_panel(
        ax_d,
        sepsis,
        "cd3_cd14_abundance_normalized",
        "rna_decoupling_index_six_minus_mhcii",
        "Inflammatory/MHC-II decoupling",
        "RNA decoupling index",
        "Sepsis n = 40\nrho = 0.462; q = 0.0199",
    )
    heatmap_panel(ax_e, corr)
    outcome_panel(ax_f, sepsis)

    for ax, label in zip([ax_a, ax_b, ax_c, ax_d, ax_e, ax_f], list("ABCDEF")):
        add_panel_label(ax, label)

    handles, labels = ax_b.get_legend_handles_labels()
    ax_d.legend(handles, labels, loc="lower right", fontsize=6.2, handletextpad=0.25)
    fig.subplots_adjust(left=0.08, right=0.98, top=0.96, bottom=0.08, hspace=0.55, wspace=0.34)

    out_base = FIG_DIR / "stage6_multiscale_bridge_figure1"
    fig.savefig(f"{out_base}.pdf", bbox_inches="tight")
    fig.savefig(f"{out_base}.svg", bbox_inches="tight")
    fig.savefig(f"{out_base}.png", dpi=450, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote={out_base}.pdf")
    print(f"wrote={out_base}.svg")
    print(f"wrote={out_base}.png")


if __name__ == "__main__":
    main()

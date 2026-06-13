#!/usr/bin/env python3
"""Stage 7 reviewer-hardening analyses for the sepsis multiscale manuscript.

This stage uses existing public-data and read-only audited outputs. It does not
download restricted data, does not run MR, and does not build a clinical model.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path("<PROJECT_ROOT>")
LEGACY = Path("<READ_ONLY_TRANSCRIPTOMICS_REFERENCE_ROOT>")
FREE = Path("<READ_ONLY_CYTOMETRY_REFERENCE_ROOT>/results/tcell_monocyte_complex")
OUT = ROOT / "03_results" / "stage7_review_hardening"
FIG_OUT = ROOT / "04_figures" / "stage7_review_hardening"
MANUSCRIPT = ROOT / "05_manuscript"
LOG_DIR = ROOT / "06_logs"

RNG_SEED = 20260612
N_PERM = int(os.environ.get("STAGE7_N_PERM", "10000"))
N_BOOT = int(os.environ.get("STAGE7_N_BOOT", "5000"))
N_RANDOM_SIGNATURES = int(os.environ.get("STAGE7_N_RANDOM_SIGNATURES", "300"))


SIGNATURE_SETS = {
    "six_gene_panel": ["RETN", "MCEMP1", "CYP1B1", "S100A12", "S100A8", "HK3"],
    "mhcii_cd74_axis": [
        "CD74",
        "HLA-DRA",
        "HLA-DRB1",
        "HLA-DRB5",
        "HLA-DPA1",
        "HLA-DPB1",
        "HLA-DQA1",
        "HLA-DQB1",
        "HLA-DMA",
        "HLA-DMB",
        "CIITA",
    ],
    "hla_dr_core": ["HLA-DRA", "HLA-DRB1", "HLA-DRB5", "CIITA", "CD74"],
    "myeloid_inflammatory": ["S100A8", "S100A9", "S100A12", "IL1B", "CXCL8", "LCN2", "RETN", "TLR2", "NFKBIA", "FCGR1A"],
    "immunometabolic_stress": ["HK3", "HIF1A", "LDHA", "SLC2A3", "PFKFB3", "ENO1", "ALDOA"],
    "adaptive_t_cell_context": ["CD3D", "CD3E", "CD4", "CD8A", "IL7R", "CCR7", "LCK", "TRAC"],
}

NEGATIVE_CONTROL_SIGNATURES = {
    "housekeeping_like": ["ACTB", "GAPDH", "RPLP0", "HPRT1", "TBP", "PGK1", "PPIA", "HMBS"],
    "erythrocyte_contamination": ["HBB", "HBA1", "HBA2", "ALAS2", "CA1", "CA2", "AHSP"],
    "platelet_contamination": ["PF4", "PPBP", "GP9", "GP1BA", "ITGA2B", "NRGN", "TUBB1"],
}

PROHIBITED_TERMS = [
    "causal mechanism",
    "causal chain",
    "mechanism validation",
    "validated biomarker",
    "diagnostic model",
    "prognostic model",
    "predictive model",
    "clinical utility",
    "treatment selection",
    "therapeutic target",
    "immune synapse",
    "physical interaction",
    "stable complex",
    "mechanism proved",
    "deployable",
    "nomogram",
    "AUC",
]


def ensure_dirs() -> None:
    for path in (OUT, FIG_OUT, MANUSCRIPT, LOG_DIR):
        path.mkdir(parents=True, exist_ok=True)


def read_csv(path: Path, sep: str | None = None) -> pd.DataFrame:
    if sep is None:
        return pd.read_csv(path)
    return pd.read_csv(path, sep=sep)


def write_csv(df: pd.DataFrame, name: str) -> Path:
    path = OUT / name
    df.to_csv(path, index=False)
    return path


def md5(path: Path) -> str:
    if not path.exists() or not path.is_file():
        return ""
    h = hashlib.md5()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def bh_adjust(pvalues: list[float]) -> list[float]:
    n = len(pvalues)
    order = sorted(range(n), key=lambda i: float(pvalues[i]) if math.isfinite(float(pvalues[i])) else 1.0)
    q = [float("nan")] * n
    prev = 1.0
    for rank_from_end, i in enumerate(reversed(order), start=1):
        p = float(pvalues[i]) if math.isfinite(float(pvalues[i])) else 1.0
        rank = n - rank_from_end + 1
        raw = p * n / rank
        prev = min(prev, raw)
        q[i] = min(prev, 1.0)
    return q


def spearman_rho(x, y) -> float:
    x = pd.Series(x, dtype="float64")
    y = pd.Series(y, dtype="float64")
    ok = x.notna() & y.notna()
    if int(ok.sum()) < 4:
        return float("nan")
    xr = x[ok].rank(method="average")
    yr = y[ok].rank(method="average")
    if xr.nunique() < 2 or yr.nunique() < 2:
        return float("nan")
    return float(xr.corr(yr))


def pearson_r(x, y) -> float:
    x = pd.Series(x, dtype="float64")
    y = pd.Series(y, dtype="float64")
    ok = x.notna() & y.notna()
    if int(ok.sum()) < 4:
        return float("nan")
    if x[ok].nunique() < 2 or y[ok].nunique() < 2:
        return float("nan")
    return float(x[ok].corr(y[ok]))


def normal_approx_p_from_r(r: float, n: int) -> float:
    if not math.isfinite(r) or n < 4:
        return float("nan")
    z = r * math.sqrt(max(n - 1, 1))
    return float(math.erfc(abs(z) / math.sqrt(2)))


def permutation_p(x, y, rng: np.random.Generator, n_perm: int = N_PERM) -> tuple[float, float, float, float]:
    x = pd.Series(x, dtype="float64")
    y = pd.Series(y, dtype="float64")
    ok = x.notna() & y.notna()
    x_arr = x[ok].to_numpy()
    y_arr = y[ok].to_numpy()
    obs = spearman_rho(x_arr, y_arr)
    if len(x_arr) < 8 or not math.isfinite(obs):
        return obs, float("nan"), float("nan"), float("nan")
    null = np.empty(n_perm, dtype=float)
    for i in range(n_perm):
        null[i] = spearman_rho(x_arr, rng.permutation(y_arr))
    p = (np.sum(np.abs(null) >= abs(obs)) + 1.0) / (n_perm + 1.0)
    return obs, float(p), float(np.percentile(null, 2.5)), float(np.percentile(null, 97.5))


def bootstrap_ci(x, y, rng: np.random.Generator, n_boot: int = N_BOOT) -> tuple[float, float, float, float]:
    x = pd.Series(x, dtype="float64")
    y = pd.Series(y, dtype="float64")
    ok = x.notna() & y.notna()
    x_arr = x[ok].to_numpy()
    y_arr = y[ok].to_numpy()
    n = len(x_arr)
    if n < 8:
        return float("nan"), float("nan"), float("nan"), float("nan")
    vals = []
    for _ in range(n_boot):
        idx = rng.integers(0, n, n)
        r = spearman_rho(x_arr[idx], y_arr[idx])
        if math.isfinite(r):
            vals.append(r)
    if not vals:
        return float("nan"), float("nan"), float("nan"), float("nan")
    arr = np.array(vals)
    return float(np.percentile(arr, 2.5)), float(np.percentile(arr, 50)), float(np.percentile(arr, 97.5)), float(np.mean(arr > 0))


def linear_residual(y, covariates: pd.DataFrame) -> np.ndarray:
    y_arr = pd.Series(y, dtype="float64").to_numpy()
    x = covariates.copy()
    x = x.apply(pd.to_numeric, errors="coerce")
    mask = np.isfinite(y_arr)
    for col in x.columns:
        mask &= np.isfinite(x[col].to_numpy(dtype=float))
    resid = np.full(len(y_arr), np.nan)
    if mask.sum() < x.shape[1] + 4:
        return resid
    X = np.column_stack([np.ones(mask.sum()), x.loc[mask].to_numpy(dtype=float)])
    beta = np.linalg.lstsq(X, y_arr[mask], rcond=None)[0]
    resid[mask] = y_arr[mask] - X @ beta
    return resid


def parse_time_rank(base_id: str) -> int:
    match = re.search(r"Ja(\d+)", str(base_id))
    return int(match.group(1)) if match else 10**9


def combat_pairing_and_robustness(rng: np.random.Generator) -> list[Path]:
    paired = read_csv(OUT.parent / "stage6_multiscale_coevent_bridge" / "stage6_combat_paired_rna_flow_sample_manifest.csv")
    paired["timepoint_rank"] = paired["base_participant_timepoint_id"].map(parse_time_rank)
    sepsis = paired[paired["analysis_group"].eq("Sepsis")].copy()

    flow_metrics = [
        "cd3_cd14_abundance_normalized",
        "cd3_cd14_double_fraction",
        "cd3_cd14_hmean_enrichment_exclusive",
    ]
    rna_metrics = [
        "hla_dr_core",
        "mhcii_cd74_axis",
        "rna_decoupling_index_six_minus_mhcii",
        "myeloid_inflammatory",
        "immunometabolic_stress",
    ]

    participant_counts = (
        paired.groupby(["analysis_group", "COMBAT_ID"], dropna=False)
        .size()
        .reset_index(name="n_participant_timepoint_rows")
    )
    participant_summary = (
        participant_counts.groupby("analysis_group")
        .agg(
            n_rows=("n_participant_timepoint_rows", "sum"),
            n_participants=("COMBAT_ID", "nunique"),
            n_repeated_participants=("n_participant_timepoint_rows", lambda x: int((x > 1).sum())),
            max_rows_per_participant=("n_participant_timepoint_rows", "max"),
        )
        .reset_index()
    )
    participant_summary["claim_boundary"] = "participant-timepoint rows; repeated participants require sensitivity analysis"

    pairing_flow = pd.DataFrame(
        [
            {"step_order": 1, "step": "COMBAT public whole-blood RNA logCPM matrix", "n": 143, "unit": "RNA samples", "source": "CBD-KEY-RNASEQ-WB Logcpm_143_23063.txt"},
            {"step_order": 2, "step": "COMBAT genes in logCPM matrix", "n": 23063, "unit": "genes", "source": "public COMBAT RNA archive"},
            {"step_order": 3, "step": "Strict event-QC CyTOF samples with IDs", "n": int(read_csv(OUT.parent / "stage6_multiscale_coevent_bridge" / "stage6_combat_cytof_wb_strict_with_ids.csv").shape[0]), "unit": "CyTOF rows", "source": "read-only FREE REACH strict event-QC output"},
            {"step_order": 4, "step": "Matched biological RNA-CyTOF rows", "n": int(paired.shape[0]), "unit": "participant-timepoint rows", "source": "shared base participant-timepoint ID"},
            {"step_order": 5, "step": "Sepsis-only matched rows", "n": int(sepsis.shape[0]), "unit": "participant-timepoint rows", "source": "analysis_group == Sepsis"},
            {"step_order": 6, "step": "Sepsis participants", "n": int(sepsis["COMBAT_ID"].nunique()), "unit": "participants", "source": "COMBAT_ID"},
        ]
    )
    group_counts = paired["analysis_group"].value_counts(dropna=False).rename_axis("analysis_group").reset_index(name="n")
    group_counts["flowchart_note"] = "included in paired RNA-CyTOF bridge"

    rows = []
    null_rows = []
    for flow in flow_metrics:
        for rna in rna_metrics:
            sub = sepsis[[rna, flow, "COMBAT_ID", "base_participant_timepoint_id", "timepoint_rank"]].dropna().copy()
            if len(sub) < 8:
                continue
            obs = spearman_rho(sub[rna], sub[flow])
            pear = pearson_r(sub[rna], sub[flow])
            p_norm = normal_approx_p_from_r(obs, len(sub))
            _, p_perm, null_lo, null_hi = permutation_p(sub[rna], sub[flow], rng)
            ci_lo, boot_med, ci_hi, boot_pos_fraction = bootstrap_ci(sub[rna], sub[flow], rng)

            jk_vals = []
            for idx in sub.index:
                jk = sub.drop(index=idx)
                jk_vals.append(spearman_rho(jk[rna], jk[flow]))
            jk_vals = [v for v in jk_vals if math.isfinite(v)]

            lop_vals = []
            for pid in sub["COMBAT_ID"].dropna().unique():
                lop = sub[sub["COMBAT_ID"].ne(pid)]
                lop_vals.append(spearman_rho(lop[rna], lop[flow]))
            lop_vals = [v for v in lop_vals if math.isfinite(v)]

            one = (
                sub.sort_values(["COMBAT_ID", "timepoint_rank", "base_participant_timepoint_id"])
                .groupby("COMBAT_ID", as_index=False)
                .head(1)
            )
            one_rho = spearman_rho(one[rna], one[flow])
            one_p = normal_approx_p_from_r(one_rho, len(one))

            rows.append(
                {
                    "analysis_scope": "sepsis_only",
                    "rna_metric": rna,
                    "flow_metric": flow,
                    "n_rows": len(sub),
                    "n_participants": sub["COMBAT_ID"].nunique(),
                    "spearman_rho": obs,
                    "spearman_p_normal_approx": p_norm,
                    "permutation_p_two_sided": p_perm,
                    "permutation_null_rho_q025": null_lo,
                    "permutation_null_rho_q975": null_hi,
                    "bootstrap_rho_q025": ci_lo,
                    "bootstrap_rho_median": boot_med,
                    "bootstrap_rho_q975": ci_hi,
                    "bootstrap_positive_fraction": boot_pos_fraction,
                    "pearson_r": pear,
                    "jackknife_rho_min": min(jk_vals) if jk_vals else float("nan"),
                    "jackknife_rho_max": max(jk_vals) if jk_vals else float("nan"),
                    "jackknife_direction_consistent": int(all(np.sign(v) == np.sign(obs) for v in jk_vals)) if jk_vals else 0,
                    "leave_one_participant_rho_min": min(lop_vals) if lop_vals else float("nan"),
                    "leave_one_participant_rho_max": max(lop_vals) if lop_vals else float("nan"),
                    "leave_one_participant_direction_consistent": int(all(np.sign(v) == np.sign(obs) for v in lop_vals)) if lop_vals else 0,
                    "one_timepoint_per_participant_n": len(one),
                    "one_timepoint_per_participant_rho": one_rho,
                    "one_timepoint_per_participant_p_normal_approx": one_p,
                    "claim_boundary": "exploratory paired correlation; no causal, biomarker, or clinical model claim",
                }
            )

            # Store a compact null distribution only for the three primary abundance-normalized claims.
            if flow == "cd3_cd14_abundance_normalized" and rna in {
                "hla_dr_core",
                "mhcii_cd74_axis",
                "rna_decoupling_index_six_minus_mhcii",
            }:
                x = sub[rna].to_numpy()
                y = sub[flow].to_numpy()
                for i in range(min(N_PERM, 10000)):
                    null_rows.append(
                        {
                            "rna_metric": rna,
                            "flow_metric": flow,
                            "permutation_index": i + 1,
                            "null_spearman_rho": spearman_rho(x, rng.permutation(y)),
                            "observed_spearman_rho": obs,
                        }
                    )

    robust = pd.DataFrame(rows)
    if not robust.empty:
        robust["bh_fdr_permutation_primary_family"] = bh_adjust(robust["permutation_p_two_sided"].fillna(1.0).tolist())
        robust["retained_or_discard_decision"] = np.where(
            robust["rna_metric"].isin(["hla_dr_core", "mhcii_cd74_axis", "rna_decoupling_index_six_minus_mhcii"])
            & robust["flow_metric"].eq("cd3_cd14_abundance_normalized"),
            "retain_as_primary_paired_bridge_sensitivity",
            "retain_as_quantification_sensitivity",
        )

    paths = [
        write_csv(pairing_flow, "stage7_combat_pairing_flow_source_data.csv"),
        write_csv(group_counts, "stage7_combat_group_counts.csv"),
        write_csv(participant_counts, "stage7_combat_participant_timepoint_counts.csv"),
        write_csv(participant_summary, "stage7_combat_participant_independence_audit.csv"),
        write_csv(robust, "stage7_combat_sepsis_paired_robustness.csv"),
        write_csv(pd.DataFrame(null_rows), "stage7_combat_pairing_permutation_null.csv"),
    ]
    return paths


def score_signature(expr_mat: pd.DataFrame, genes: list[str]) -> pd.Series:
    present = [g for g in genes if g in expr_mat.index]
    if len(present) < 2:
        return pd.Series(np.nan, index=expr_mat.columns)
    sub = expr_mat.loc[present].apply(pd.to_numeric, errors="coerce")
    z = sub.sub(sub.mean(axis=1), axis=0)
    sd = sub.std(axis=1).replace(0, np.nan)
    z = z.div(sd, axis=0)
    return z.mean(axis=0, skipna=True)


def bulk_leave_one_and_random_signatures(rng: np.random.Generator) -> list[Path]:
    corr = read_csv(ROOT / "03_results" / "stage1_bulk_mhcii_screen" / "stage1_bulk_signature_correlations.csv")
    rows = []
    for pair, sub in corr.groupby("pair"):
        full_median = sub["rho"].median()
        expected_sign = -1 if full_median < 0 else 1
        for removed in ["NONE"] + sorted(sub["accession"].unique()):
            keep = sub if removed == "NONE" else sub[sub["accession"].ne(removed)]
            rows.append(
                {
                    "pair": pair,
                    "removed_accession": removed,
                    "n_datasets_retained": keep["accession"].nunique(),
                    "median_rho": keep["rho"].median(),
                    "direction_consistency_fraction": float((np.sign(keep["rho"]) == expected_sign).mean()) if len(keep) else float("nan"),
                    "fdr_lt_0_10_count": int((keep["FDR"] < 0.10).sum()),
                    "nominal_p_lt_0_05_count": int((keep["p_value"] < 0.05).sum()),
                    "claim_boundary": "leave-one-cohort sensitivity; not an external validation test",
                }
            )
    leave_one = pd.DataFrame(rows)

    datasets = sorted(read_csv(ROOT / "03_results" / "stage1_bulk_mhcii_screen" / "stage1_bulk_signature_scores.csv")["accession"].unique())
    random_rows = []
    control_rows = []
    for acc in datasets:
        expr_path = LEGACY / "01_data" / "processed" / "bulk" / acc / f"expression_gene_median_{acc}.csv.gz"
        meta_path = LEGACY / "01_data" / "processed" / "bulk" / acc / f"metadata_cleaned_{acc}.csv"
        if not expr_path.exists() or not meta_path.exists():
            continue
        expr = pd.read_csv(expr_path)
        gene_col = expr.columns[0]
        genes = expr[gene_col].astype(str).tolist()
        expr = expr.drop(columns=[gene_col])
        expr.index = pd.Index(genes)
        expr = expr[~expr.index.duplicated(keep="first")]
        meta = pd.read_csv(meta_path)
        keep_samples = meta.loc[
            (meta.get("included_in_primary_analysis", "YES").eq("YES"))
            & (meta.get("case_control_main").isin(["CASE", "CONTROL"])),
            "gsm_id",
        ].astype(str)
        common = [s for s in keep_samples if s in expr.columns]
        expr_use = expr[common]
        six = score_signature(expr_use, SIGNATURE_SETS["six_gene_panel"])
        mhcii = score_signature(expr_use, SIGNATURE_SETS["mhcii_cd74_axis"])
        hladr = score_signature(expr_use, SIGNATURE_SETS["hla_dr_core"])
        observed_mhcii = spearman_rho(six, mhcii)
        observed_hladr = spearman_rho(six, hladr)
        excluded = set(sum(SIGNATURE_SETS.values(), []))
        gene_pool = [g for g in expr_use.index.astype(str).tolist() if g not in excluded and expr_use.loc[g].notna().sum() >= max(8, int(0.5 * len(common)))]

        null_mhcii = []
        null_hladr = []
        for _ in range(N_RANDOM_SIGNATURES):
            rand_mhcii = rng.choice(gene_pool, size=min(len(SIGNATURE_SETS["mhcii_cd74_axis"]), len(gene_pool)), replace=False).tolist()
            rand_hladr = rng.choice(gene_pool, size=min(len(SIGNATURE_SETS["hla_dr_core"]), len(gene_pool)), replace=False).tolist()
            null_mhcii.append(spearman_rho(six, score_signature(expr_use, rand_mhcii)))
            null_hladr.append(spearman_rho(six, score_signature(expr_use, rand_hladr)))
        for target, observed, vals in [
            ("mhcii_cd74_axis_random_gene_count_matched", observed_mhcii, null_mhcii),
            ("hla_dr_core_random_gene_count_matched", observed_hladr, null_hladr),
        ]:
            arr = np.array([v for v in vals if math.isfinite(v)])
            random_rows.append(
                {
                    "accession": acc,
                    "target_axis": target,
                    "observed_six_gene_rho": observed,
                    "n_random_signatures": len(arr),
                    "random_rho_median": float(np.median(arr)) if len(arr) else float("nan"),
                    "random_rho_q025": float(np.percentile(arr, 2.5)) if len(arr) else float("nan"),
                    "random_rho_q975": float(np.percentile(arr, 97.5)) if len(arr) else float("nan"),
                    "empirical_p_observed_as_or_more_negative": float((np.sum(arr <= observed) + 1) / (len(arr) + 1)) if len(arr) else float("nan"),
                    "observed_below_random_q025": int(observed < np.percentile(arr, 2.5)) if len(arr) else 0,
                    "claim_boundary": "random signature specificity sensitivity; does not prove pathway causality",
                }
            )
        for control, genes in NEGATIVE_CONTROL_SIGNATURES.items():
            score = score_signature(expr_use, genes)
            present = [g for g in genes if g in expr_use.index]
            control_rows.append(
                {
                    "accession": acc,
                    "control_signature": control,
                    "n_requested": len(genes),
                    "n_present": len(present),
                    "present_genes": ";".join(present),
                    "rho_with_six_gene_panel": spearman_rho(six, score),
                    "rho_with_mhcii_cd74_axis": spearman_rho(mhcii, score),
                    "claim_boundary": "negative-control signature context; not a biological depletion claim",
                }
            )

    paths = [
        write_csv(leave_one, "stage7_bulk_leave_one_cohort_sensitivity.csv"),
        write_csv(pd.DataFrame(random_rows), "stage7_bulk_random_signature_null_summary.csv"),
        write_csv(pd.DataFrame(control_rows), "stage7_bulk_negative_control_signature_correlations.csv"),
    ]
    return paths


def composition_sensitivity() -> list[Path]:
    scores = read_csv(ROOT / "03_results" / "stage1_bulk_mhcii_screen" / "stage1_bulk_signature_scores.csv")
    states = read_csv(ROOT / "03_results" / "stage2_signature_state_heterogeneity" / "stage2_case_immune_state_assignments.csv")
    deconv_path = LEGACY / "03_results" / "tables" / "EXP03_P07R2_reference_deconvolution_wide.csv"
    deconv = read_csv(deconv_path)
    merged = scores.merge(deconv[["accession", "gsm_id", "method", "reference_level", "Mono", "B", "DC", "T_NK"]], on=["accession", "gsm_id"], how="inner")
    merged = merged[merged["method"].eq("NNLS_pseudo_reference_fallback")].copy()
    merged["mono_floor_0_05"] = merged["Mono"].clip(lower=0.05)
    for metric in ["mhcii_cd74_axis", "hla_dr_core"]:
        merged[f"{metric}_mono_ratio_floor0_05"] = merged[metric] / merged["mono_floor_0_05"]
        merged[f"{metric}_mono_rank_residual"] = np.nan
        for acc, idx in merged.groupby("accession").groups.items():
            sub = merged.loc[idx]
            y_rank = sub[metric].rank(method="average")
            x_rank = sub[["Mono"]].rank(method="average")
            merged.loc[idx, f"{metric}_mono_rank_residual"] = linear_residual(y_rank, x_rank)

    rows = []
    for acc, sub in merged[merged["case_control_main"].eq("CASE")].groupby("accession"):
        for metric in ["mhcii_cd74_axis", "hla_dr_core"]:
            for adjusted in [metric, f"{metric}_mono_ratio_floor0_05", f"{metric}_mono_rank_residual"]:
                rows.append(
                    {
                        "accession": acc,
                        "metric": adjusted,
                        "n_case": int(sub[[adjusted, "six_gene_panel"]].dropna().shape[0]),
                        "rho_with_six_gene_panel": spearman_rho(sub["six_gene_panel"], sub[adjusted]),
                        "p_normal_approx": normal_approx_p_from_r(spearman_rho(sub["six_gene_panel"], sub[adjusted]), int(sub[[adjusted, "six_gene_panel"]].dropna().shape[0])),
                        "mono_method": "read-only NNLS broad-cell computational estimate",
                        "claim_boundary": "cell-composition sensitivity only; not direct monocyte cell counting",
                    }
                )
    comp = pd.DataFrame(rows)
    if not comp.empty:
        comp["bh_fdr_within_metric"] = comp.groupby("metric")["p_normal_approx"].transform(lambda x: bh_adjust(x.fillna(1.0).tolist()))

    state_merge = states.merge(merged[["accession", "gsm_id", "Mono", "mhcii_cd74_axis_mono_ratio_floor0_05", "hla_dr_core_mono_ratio_floor0_05", "mhcii_cd74_axis_mono_rank_residual", "hla_dr_core_mono_rank_residual"]], on=["accession", "gsm_id"], how="inner")
    contrast_rows = []
    dec = "Decoupled inflammatory / MHC-II-low"
    for metric in ["Mono", "mhcii_cd74_axis", "hla_dr_core", "mhcii_cd74_axis_mono_ratio_floor0_05", "hla_dr_core_mono_ratio_floor0_05", "mhcii_cd74_axis_mono_rank_residual", "hla_dr_core_mono_rank_residual"]:
        if metric not in state_merge.columns:
            continue
        a = state_merge.loc[state_merge["immune_state"].eq(dec), metric].dropna()
        b = state_merge.loc[state_merge["immune_state"].ne(dec), metric].dropna()
        contrast_rows.append(
            {
                "contrast": "decoupled_state_vs_other_sepsis_states",
                "metric": metric,
                "n_decoupled": len(a),
                "n_other": len(b),
                "median_decoupled": float(a.median()) if len(a) else float("nan"),
                "median_other": float(b.median()) if len(b) else float("nan"),
                "delta_decoupled_minus_other": float(a.median() - b.median()) if len(a) and len(b) else float("nan"),
                "claim_boundary": "state-level computational contrast; not a clinical endotype or direct cell count",
            }
        )

    paths = [
        write_csv(comp, "stage7_bulk_monocyte_adjusted_sensitivity.csv"),
        write_csv(pd.DataFrame(contrast_rows), "stage7_immune_state_monocyte_adjusted_contrasts.csv"),
    ]
    return paths


def pairwise_distances(X: np.ndarray) -> np.ndarray:
    # The matrix is small, so use the explicit norm. This avoids occasional
    # BLAS overflow warnings despite finite z-scored inputs on macOS.
    return np.linalg.norm(X[:, None, :] - X[None, :, :], axis=2)


def kmeans(X: np.ndarray, k: int, rng: np.random.Generator, n_init: int = 50, max_iter: int = 100) -> tuple[np.ndarray, np.ndarray, float]:
    best_labels = None
    best_centroids = None
    best_inertia = float("inf")
    n = X.shape[0]
    for _ in range(n_init):
        centroids = X[rng.choice(n, size=k, replace=False)].copy()
        labels = np.zeros(n, dtype=int)
        for _iter in range(max_iter):
            d = ((X[:, None, :] - centroids[None, :, :]) ** 2).sum(axis=2)
            new_labels = np.argmin(d, axis=1)
            if np.array_equal(new_labels, labels) and _iter > 0:
                break
            labels = new_labels
            for j in range(k):
                if np.any(labels == j):
                    centroids[j] = X[labels == j].mean(axis=0)
                else:
                    centroids[j] = X[rng.integers(0, n)]
        inertia = float(((X - centroids[labels]) ** 2).sum())
        if inertia < best_inertia:
            best_inertia = inertia
            best_labels = labels.copy()
            best_centroids = centroids.copy()
    return best_labels, best_centroids, best_inertia


def silhouette_mean(X: np.ndarray, labels: np.ndarray) -> float:
    unique = np.unique(labels)
    if len(unique) < 2:
        return float("nan")
    d = pairwise_distances(X)
    sil = []
    for i in range(X.shape[0]):
        same = labels == labels[i]
        if same.sum() > 1:
            a = d[i, same].sum() / (same.sum() - 1)
        else:
            a = 0.0
        b = min(d[i, labels == lab].mean() for lab in unique if lab != labels[i] and np.any(labels == lab))
        denom = max(a, b)
        sil.append(0.0 if denom == 0 else (b - a) / denom)
    return float(np.mean(sil))


def comb2(n: int) -> float:
    return n * (n - 1) / 2.0


def adjusted_rand_index(a: np.ndarray, b: np.ndarray) -> float:
    a_vals = {v: i for i, v in enumerate(np.unique(a))}
    b_vals = {v: i for i, v in enumerate(np.unique(b))}
    tab = np.zeros((len(a_vals), len(b_vals)), dtype=int)
    for x, y in zip(a, b):
        tab[a_vals[x], b_vals[y]] += 1
    sum_ij = sum(comb2(int(v)) for v in tab.ravel())
    sum_i = sum(comb2(int(v)) for v in tab.sum(axis=1))
    sum_j = sum(comb2(int(v)) for v in tab.sum(axis=0))
    total = comb2(len(a))
    if total == 0:
        return float("nan")
    expected = sum_i * sum_j / total
    max_index = 0.5 * (sum_i + sum_j)
    denom = max_index - expected
    return float((sum_ij - expected) / denom) if denom != 0 else 0.0


def clustering_stability(rng: np.random.Generator) -> list[Path]:
    states = read_csv(ROOT / "03_results" / "stage2_signature_state_heterogeneity" / "stage2_case_immune_state_assignments.csv")
    z_cols = [
        "six_gene_panel_z",
        "myeloid_inflammatory_z",
        "immunometabolic_stress_z",
        "mhcii_cd74_axis_z",
        "hla_dr_core_z",
        "interferon_antigen_presentation_z",
        "adaptive_t_cell_context_z",
    ]
    X = states[z_cols].to_numpy(dtype=float)
    ref = states["cluster_raw"].astype(str).to_numpy()
    rows = []
    labels_by_k = {}
    for k in range(2, 6):
        labels, centroids, inertia = kmeans(X, k, rng, n_init=80)
        labels_by_k[k] = labels
        rows.append(
            {
                "k": k,
                "total_withinss_custom": inertia,
                "silhouette_mean_custom": silhouette_mean(X, labels),
                "cluster_size_min": int(pd.Series(labels).value_counts().min()),
                "cluster_size_max": int(pd.Series(labels).value_counts().max()),
                "claim_boundary": "computational clustering stability only; not validated clinical endotype",
            }
        )
    k_summary = pd.DataFrame(rows)

    stability_rows = []
    for i in range(100):
        labels, centroids, inertia = kmeans(X, 3, np.random.default_rng(RNG_SEED + 1000 + i), n_init=20)
        stability_rows.append(
            {
                "run_type": "seed_full_data",
                "iteration": i + 1,
                "adjusted_rand_vs_stage2_reference": adjusted_rand_index(ref, labels.astype(str)),
                "total_withinss": inertia,
                "n_samples_used": len(X),
            }
        )
    for i in range(100):
        idx = rng.choice(np.arange(len(X)), size=int(0.8 * len(X)), replace=True)
        unique_idx = np.unique(idx)
        labels_sub, centroids, inertia = kmeans(X[idx], 3, np.random.default_rng(RNG_SEED + 2000 + i), n_init=20)
        d = ((X[:, None, :] - centroids[None, :, :]) ** 2).sum(axis=2)
        pred_all = np.argmin(d, axis=1)
        stability_rows.append(
            {
                "run_type": "bootstrap_centroid_assign_all",
                "iteration": i + 1,
                "adjusted_rand_vs_stage2_reference": adjusted_rand_index(ref, pred_all.astype(str)),
                "total_withinss": float(((X - centroids[pred_all]) ** 2).sum()),
                "n_samples_used": len(unique_idx),
            }
        )
    stability = pd.DataFrame(stability_rows)
    stability_summary = (
        stability.groupby("run_type")
        .agg(
            n_runs=("iteration", "count"),
            ari_median=("adjusted_rand_vs_stage2_reference", "median"),
            ari_q025=("adjusted_rand_vs_stage2_reference", lambda x: float(np.percentile(x, 2.5))),
            ari_q975=("adjusted_rand_vs_stage2_reference", lambda x: float(np.percentile(x, 97.5))),
            total_withinss_median=("total_withinss", "median"),
        )
        .reset_index()
    )
    stability_summary["claim_boundary"] = "stability support for manuscript state labels; not clinical validation"

    paths = [
        write_csv(k_summary, "stage7_case_only_kmeans_k2_to_k5_quality.csv"),
        write_csv(stability, "stage7_case_only_clustering_seed_bootstrap_ari.csv"),
        write_csv(stability_summary, "stage7_case_only_clustering_stability_summary.csv"),
    ]
    return paths


def cytometry_artifact_and_state() -> list[Path]:
    cytof = read_csv(ROOT / "03_results" / "stage6_multiscale_coevent_bridge" / "stage6_combat_cytof_wb_strict_with_ids.csv")
    numeric_cols = [
        "events_before_filter",
        "events_after_filter",
        "events_retained_fraction",
        "event_length_cutoff",
        "iridium_sum_cutoff",
        "cd3_pos_fraction",
        "cd14_pos_fraction",
        "cd3_cd14_double_events",
        "cd3_cd14_double_fraction",
        "cd3_cd14_abundance_normalized",
        "cd3_cd14_hmean_enrichment_exclusive",
        "double_event_hla_dr_pos_fraction",
        "double_event_cd33_pos_fraction",
        "double_event_cd11c_pos_fraction",
        "double_event_cd16_pos_fraction",
        "double_event_cd38_pos_fraction",
    ]
    rows = []
    for group, sub in cytof[cytof["is_biological_sample"].eq(True)].groupby("analysis_group"):
        for col in numeric_cols:
            if col not in sub.columns:
                continue
            vals = pd.to_numeric(sub[col], errors="coerce").dropna()
            rows.append(
                {
                    "analysis_group": group,
                    "metric": col,
                    "n": len(vals),
                    "median": float(vals.median()) if len(vals) else float("nan"),
                    "q25": float(vals.quantile(0.25)) if len(vals) else float("nan"),
                    "q75": float(vals.quantile(0.75)) if len(vals) else float("nan"),
                    "min": float(vals.min()) if len(vals) else float("nan"),
                    "max": float(vals.max()) if len(vals) else float("nan"),
                }
            )
    artifact_summary = pd.DataFrame(rows)
    artifact_summary["claim_boundary"] = "strict event-QC summary; no physical-complex claim"

    freq_state_metrics = [
        "cd3_cd14_double_fraction",
        "cd3_cd14_abundance_normalized",
        "cd3_cd14_hmean_enrichment_exclusive",
        "double_event_hla_dr_pos_fraction",
        "double_event_cd33_pos_fraction",
        "double_event_cd11c_pos_fraction",
        "double_event_cd16_pos_fraction",
        "double_event_cd38_pos_fraction",
    ]
    freq_state = artifact_summary[artifact_summary["metric"].isin(freq_state_metrics)].copy()
    freq_state["readout_class"] = np.where(
        freq_state["metric"].str.contains("double_fraction|abundance|hmean"),
        "frequency_or_abundance",
        "state_marker_inside_cd3_cd14_events",
    )
    freq_state["interpretation_boundary"] = np.where(
        freq_state["readout_class"].eq("frequency_or_abundance"),
        "frequency/abundance readout; not proof of cell contact",
        "state remodeling readout inside residual events; not uniform HLA-DR-loss claim",
    )

    needed_pairs = ["CD3/CD19", "CD3/CD56", "CD14/CD16"]
    available_cols = set(cytof.columns)
    negative_control_rows = []
    for pair in needed_pairs:
        negative_control_rows.append(
            {
                "requested_negative_control": pair,
                "current_summary_support": "not_available_from_existing_stage6_summary",
                "reason": "existing COMBAT strict summary stores CD3/CD14 co-event metrics and marker positivity inside those events, not independent pairwise co-event metrics",
                "safe_next_step": "requires event-level FCS reprocessing with the same strict event-QC and abundance-normalization parameters",
                "claim_boundary": "do not report negative marker-pair correlations until pairwise co-events are actually recomputed",
            }
        )
    available_marker_state_controls = [
        c
        for c in [
            "double_event_cd19_pos_fraction",
            "double_event_cd56_pos_fraction",
            "double_event_cd16_pos_fraction",
            "double_event_cd33_pos_fraction",
        ]
        if c in available_cols
    ]
    for col in available_marker_state_controls:
        negative_control_rows.append(
            {
                "requested_negative_control": col,
                "current_summary_support": "available_as_marker_state_inside_cd3_cd14_events_only",
                "reason": "this is not an independent co-event pair, but can be used as marker-state specificity context",
                "safe_next_step": "report as marker-state context, not as CD3/CD19 or CD3/CD56 co-event control",
                "claim_boundary": "does not replace event-level negative co-event analysis",
            }
        )

    readonly_paths = [
        FREE / "zenodo_combat_cytof_wb_strict_event_qc_sample_metrics.tsv",
        FREE / "zenodo_combat_cytof_wb_eventlength_q95_contrasts.tsv",
        FREE / "zenodo_combat_cytof_wb_batch_control_delta_contrasts.tsv",
        FREE / "zenodo_combat_cytof_wb_clinical_marker_breadth_sensitivity_models.tsv",
        FREE / "zenodo_priest_tube2_artifact_control_correlations.tsv",
        FREE / "zenodo_priest_tube2_artifact_control_residual_contrasts.tsv",
        FREE / "tcell_monocyte_coevent_cross_cohort_evidence_matrix.tsv",
    ]
    reuse_rows = []
    for path in readonly_paths:
        reuse_rows.append(
            {
                "source_path": str(path),
                "exists": path.exists(),
                "md5": md5(path),
                "reuse_mode": "read_only",
                "claim_downgrade_rule": "supportive evidence unless rerun from raw event files in current project",
            }
        )

    paths = [
        write_csv(artifact_summary, "stage7_cytometry_artifact_control_summary.csv"),
        write_csv(freq_state, "stage7_coevent_frequency_vs_state_summary.csv"),
        write_csv(pd.DataFrame(negative_control_rows), "stage7_coevent_negative_control_feasibility.csv"),
        write_csv(pd.DataFrame(reuse_rows), "stage7_readonly_cytometry_reuse_manifest.csv"),
    ]
    return paths


def dataset_claim_clinical_and_indexes() -> list[Path]:
    scores = read_csv(ROOT / "03_results" / "stage1_bulk_mhcii_screen" / "stage1_bulk_signature_scores.csv")
    coverage = read_csv(ROOT / "03_results" / "stage1_bulk_mhcii_screen" / "stage1_bulk_signature_gene_coverage.csv")
    dataset_rows = []
    for acc, sub in scores.groupby("accession"):
        cov = coverage[coverage["accession"].eq(acc)]
        dataset_rows.append(
            {
                "dataset_accession": acc,
                "evidence_tier": "Primary evidence",
                "data_type": "public bulk RNA transcriptome",
                "platform": "microarray_or_RNAseq_processed_matrix_not_reaudited_in_stage7",
                "raw_data_availability": "public accession dependent; not newly downloaded in Stage 7",
                "processed_matrix_availability": "available from read-only legacy processed matrix",
                "sample_count": int(sub.shape[0]),
                "sepsis_count": int((sub["case_control_main"] == "CASE").sum()),
                "control_count": int((sub["case_control_main"] == "CONTROL").sum()),
                "sampling_compartment": "whole blood or PBMC depending on source metadata",
                "gene_coverage_summary": "; ".join(f"{r.signature}:{r.n_present}/{r.n_requested}" for r in cov.itertuples()),
                "included_in_main_analysis": "yes",
                "claim_boundary": "bulk RNA association and computational state reconstruction only",
            }
        )
    paired = read_csv(ROOT / "03_results" / "stage6_multiscale_coevent_bridge" / "stage6_combat_paired_rna_flow_sample_manifest.csv")
    dataset_rows.append(
        {
            "dataset_accession": "COMBAT RNA-CyTOF paired layer",
            "evidence_tier": "Primary evidence",
            "data_type": "public paired bulk RNA-seq and CyTOF summary",
            "platform": "whole-blood RNA-seq logCPM plus CyTOF strict event-QC summary",
            "raw_data_availability": "public COMBAT RNA archive and read-only audited CyTOF FCS-derived metrics",
            "processed_matrix_availability": "yes",
            "sample_count": int(paired.shape[0]),
            "sepsis_count": int(paired["analysis_group"].eq("Sepsis").sum()),
            "control_count": int(paired["analysis_group"].eq("HV").sum()),
            "sampling_compartment": "whole blood",
            "gene_coverage_summary": "100% for prespecified Stage 6 RNA signatures",
            "included_in_main_analysis": "yes",
            "claim_boundary": "exploratory paired correlation bridge; not causal validation",
        }
    )
    readonly = read_csv(ROOT / "03_results" / "stage6_multiscale_coevent_bridge" / "stage6_readonly_coevent_evidence_matrix_subset.csv")
    for row in readonly.itertuples(index=False):
        dataset_rows.append(
            {
                "dataset_accession": getattr(row, "evidence_id"),
                "evidence_tier": "Supportive evidence" if "Boundary" not in str(getattr(row, "claim_weight")) else "Boundary evidence",
                "data_type": getattr(row, "assay"),
                "platform": getattr(row, "source"),
                "raw_data_availability": getattr(row, "data_status"),
                "processed_matrix_availability": "read-only prior output",
                "sample_count": "",
                "sepsis_count": "",
                "control_count": "",
                "sampling_compartment": getattr(row, "disease_context"),
                "gene_coverage_summary": "",
                "included_in_main_analysis": "supportive_or_boundary_only",
                "claim_boundary": getattr(row, "physical_interaction_evidence"),
            }
        )
    dataset_audit = pd.DataFrame(dataset_rows)

    claim_rows = [
        {
            "canonical_claim": "Public bulk sepsis transcriptomes show inflammatory / MHC-II-CD74 decoupling",
            "claim_level": "main_supported",
            "allowed_wording": "support, association, recurrent pattern",
            "prohibited_wording": "causal mechanism; validated biomarker; clinical utility",
        },
        {
            "canonical_claim": "COMBAT paired RNA-CyTOF links CD3/CD14 co-event abundance to MHC-II/HLA-DR RNA suppression in sepsis",
            "claim_level": "main_exploratory_bridge",
            "allowed_wording": "paired correlation-based bridge",
            "prohibited_wording": "causal chain; physical interaction; clinical model",
        },
        {
            "canonical_claim": "Residual CD3/CD14 co-events show activation-state remodeling",
            "claim_level": "supportive_with_boundaries",
            "allowed_wording": "residual event-state feature; activation-state remodeling",
            "prohibited_wording": "immune synapse; stable cell complex; uniform HLA-DR loss",
        },
        {
            "canonical_claim": "Death28 is directionally consistent with immune-paralysis model",
            "claim_level": "exploratory_clinical_anchor",
            "allowed_wording": "exploratory anchor; directionally consistent",
            "prohibited_wording": "prognostic biomarker; risk model; threshold; nomogram",
        },
    ]
    claim_matrix = pd.DataFrame(claim_rows)

    clinical = read_csv(ROOT / "03_results" / "stage6_multiscale_coevent_bridge" / "stage6_combat_multiscale_outcome_associations.csv")
    clinical_map = clinical.copy()
    clinical_map["claim_level"] = np.where(
        clinical_map["analysis_scope"].eq("sepsis_only"),
        "secondary exploratory clinical anchor",
        "exploratory clinical anchor",
    )
    clinical_map["prohibited_extension"] = "no AUC, no Cox model, no risk score, no prognostic biomarker claim"

    figure_plan = pd.DataFrame(
        [
            {"figure": "Figure 1", "title": "Study design and claim boundary", "status": "planned_after_stage7", "source_data": "stage7_dataset_audit_master_table.csv; stage7_claim_boundary_matrix.csv"},
            {"figure": "Figure 2", "title": "Public bulk RNA inflammatory / MHC-II decoupling", "status": "source_data_ready", "source_data": "stage7_bulk_leave_one_cohort_sensitivity.csv; stage7_bulk_random_signature_null_summary.csv"},
            {"figure": "Figure 3", "title": "Case-only computational immune states", "status": "source_data_ready", "source_data": "stage7_case_only_kmeans_k2_to_k5_quality.csv; stage7_case_only_clustering_stability_summary.csv"},
            {"figure": "Figure 4", "title": "Residual CD3/CD14 co-event state remodeling", "status": "source_data_ready", "source_data": "stage7_cytometry_artifact_control_summary.csv; stage7_coevent_frequency_vs_state_summary.csv"},
            {"figure": "Figure 5", "title": "COMBAT paired RNA-CyTOF bridge", "status": "source_data_ready", "source_data": "stage7_combat_pairing_flow_source_data.csv; stage7_combat_sepsis_paired_robustness.csv"},
            {"figure": "Figure 6", "title": "Bounded clinical anchor and final model", "status": "source_data_ready", "source_data": "stage7_clinical_anchor_map.csv; stage7_claim_boundary_matrix.csv"},
        ]
    )

    supplement_rows = []
    table_specs = [
        ("S1", "full dataset inventory", "stage7_dataset_audit_master_table.csv"),
        ("S2", "metadata harmonization and inclusion/exclusion", "stage7_combat_pairing_flow_source_data.csv"),
        ("S3", "signature gene lists and coverage", "stage1_bulk_signature_gene_coverage.csv"),
        ("S4", "bulk case-control signature results", "stage1_bulk_signature_case_control.csv"),
        ("S5", "within-cohort coupling results", "stage1_bulk_signature_correlations.csv"),
        ("S6", "leave-one-cohort sensitivity", "stage7_bulk_leave_one_cohort_sensitivity.csv"),
        ("S7", "case-only clustering centroid and stability", "stage7_case_only_clustering_stability_summary.csv"),
        ("S8", "cytometry co-event metric definitions", "stage7_coevent_frequency_vs_state_summary.csv"),
        ("S9", "cytometry artifact-control results", "stage7_cytometry_artifact_control_summary.csv"),
        ("S10", "cytometry marker-state remodeling results", "stage7_coevent_frequency_vs_state_summary.csv"),
        ("S11", "COMBAT RNA sample scoring", "stage6_combat_rna_signature_scores.csv"),
        ("S12", "COMBAT RNA-CyTOF pairing audit", "stage7_combat_participant_independence_audit.csv"),
        ("S13", "paired RNA-CyTOF main correlations", "stage6_combat_paired_flow_rna_correlations.csv"),
        ("S14", "group-residualized sensitivity", "stage6_combat_paired_flow_rna_correlations.csv"),
        ("S15", "non-healthy and Sepsis-only sensitivity", "stage6_combat_paired_flow_rna_correlations.csv"),
        ("S16", "permutation/bootstrap robustness", "stage7_combat_sepsis_paired_robustness.csv"),
        ("S17", "Death28 clinical anchor", "stage7_clinical_anchor_map.csv"),
        ("S18", "negative-control signatures", "stage7_bulk_negative_control_signature_correlations.csv"),
        ("S19", "negative-control marker pairs", "stage7_coevent_negative_control_feasibility.csv"),
        ("S20", "software versions and reproducibility manifest", "project_output_manifest_latest.csv"),
        ("S21", "claim boundary and prohibited language audit", "stage7_claim_boundary_matrix.csv; stage7_prohibited_language_scan.csv"),
        ("S22", "figure source-data index", "stage7_figure_rebuild_plan.csv"),
    ]
    for table_id, title, source in table_specs:
        supplement_rows.append({"supplementary_table": table_id, "title": title, "source_or_status": source, "assembly_status": "source_ready_or_indexed"})

    paths = [
        write_csv(dataset_audit, "stage7_dataset_audit_master_table.csv"),
        write_csv(claim_matrix, "stage7_claim_boundary_matrix.csv"),
        write_csv(clinical_map, "stage7_clinical_anchor_map.csv"),
        write_csv(figure_plan, "stage7_figure_rebuild_plan.csv"),
        write_csv(pd.DataFrame(supplement_rows), "stage7_supplementary_table_index.csv"),
    ]
    return paths


def prohibited_language_scan() -> list[Path]:
    rows = []
    scan_files = sorted(MANUSCRIPT.glob("*.md")) + [ROOT / "README.md", ROOT / "00_admin" / "implementation_status.md"]
    for path in scan_files:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        lines = text.splitlines()
        for i, line in enumerate(lines, start=1):
            low = line.lower()
            for term in PROHIBITED_TERMS:
                if term.lower() in low:
                    context_allowed = any(
                        token in low
                        for token in [
                            "no ",
                            "not ",
                            "rather than",
                            "instead of",
                            "prohibited",
                            "avoid",
                            "without",
                            "does not",
                            "do not",
                            "risk",
                            "mistaken",
                            "claim boundary",
                        ]
                    ) or path.name.startswith("reference_seed_list")
                    rows.append(
                        {
                            "file": str(path.relative_to(ROOT)),
                            "line": i,
                            "term": term,
                            "line_text": line.strip()[:500],
                            "context_allowed_boundary_language": context_allowed,
                            "recommended_action": "keep_if_boundary_statement" if context_allowed else "revise_or_remove_before_submission",
                        }
                    )
    term_ledger = pd.DataFrame(
        [
            {"canonical_term": "compartment-aware immune paralysis", "definition": "model separating systemic RNA decoupling from event-compartment cytometry remodeling", "use_decision": "preferred main framing"},
            {"canonical_term": "multiscale immune decoupling", "definition": "cross-scale inflammatory/MHC-II divergence", "use_decision": "safe short framing"},
            {"canonical_term": "CD3/CD14 co-event abundance", "definition": "abundance-normalized residual CD3/CD14 event signal", "use_decision": "use instead of physical complex language"},
            {"canonical_term": "residual co-event state remodeling", "definition": "marker-state shift within residual CD3/CD14 co-events", "use_decision": "use instead of immune synapse/contact language"},
            {"canonical_term": "exploratory clinical anchor", "definition": "bounded outcome consistency context", "use_decision": "use for Death28; do not call prognostic"},
        ]
    )
    paths = [
        write_csv(pd.DataFrame(rows), "stage7_prohibited_language_scan.csv"),
        write_csv(term_ledger, "stage7_terminology_ledger.csv"),
    ]
    return paths


REFERENCE_QUERIES = [
    ("sepsis_immunoparalysis_hla_dr_monitoring", 'sepsis immunoparalysis monocyte HLA-DR monitoring'),
    ("ifn_gamma_gmcsf_sepsis_immunotherapy", 'sepsis immunoparalysis IFN-gamma GM-CSF trial monocyte HLA-DR'),
    ("checkpoint_inhibitors_sepsis", 'sepsis immune checkpoint inhibitor PD-1 PD-L1 immunoparalysis'),
    ("mhcii_cd74_antigen_presentation_sepsis", 'MHC-II CD74 antigen presentation sepsis monocytes'),
    ("sepsis_transcriptomic_endotypes", 'sepsis transcriptomic endotypes immunoparalysis'),
    ("combat_multiomics_resource", 'COVID-19 Multi-omics Blood Atlas COMBAT'),
    ("combatdb_resource", 'COMBATdb COVID-19 Multi-Omics Blood Atlas'),
    ("cytof_artifact_control_miflowcyt", 'MIFlowCyt minimum information flow cytometry experiment'),
    ("flowrepository_miflowcyt", 'FlowRepository MIFlowCyt'),
    ("bootstrap_permutation_spearman_fdr", 'bootstrap confidence interval biomedical statistics'),
    ("fair_public_data_reproducibility", 'FAIR public omics data reproducibility biomedical research'),
]


def pubmed_reference_expansion() -> list[Path]:
    rows = []
    status_rows = []
    for query_id, query in REFERENCE_QUERIES:
        try:
            params = urllib.parse.urlencode(
                {"db": "pubmed", "term": query, "retmode": "json", "retmax": 6, "sort": "relevance"}
            )
            url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?{params}"
            with urllib.request.urlopen(url, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            pmids = data.get("esearchresult", {}).get("idlist", [])
            time.sleep(0.2)
            if pmids:
                params = urllib.parse.urlencode({"db": "pubmed", "id": ",".join(pmids), "retmode": "json"})
                url2 = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?{params}"
                with urllib.request.urlopen(url2, timeout=30) as resp:
                    summaries = json.loads(resp.read().decode("utf-8")).get("result", {})
                for pmid in pmids:
                    item = summaries.get(pmid, {})
                    if not item:
                        continue
                    doi = ""
                    for aid in item.get("articleids", []):
                        if aid.get("idtype") == "doi":
                            doi = aid.get("value", "")
                    rows.append(
                        {
                            "query_id": query_id,
                            "query": query,
                            "pmid": pmid,
                            "year": str(item.get("pubdate", ""))[:4],
                            "title": item.get("title", "").rstrip("."),
                            "journal": item.get("fulljournalname", "") or item.get("source", ""),
                            "doi": doi,
                            "pubmed_url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                            "use_in_manuscript": "candidate_reference_needs_manual_verification",
                        }
                    )
            status_rows.append({"query_id": query_id, "query": query, "status": "ok", "n_pmids": len(pmids)})
        except Exception as exc:
            status_rows.append({"query_id": query_id, "query": query, "status": f"failed: {type(exc).__name__}: {exc}", "n_pmids": 0})
    refs = pd.DataFrame(rows).drop_duplicates(subset=["pmid"]) if rows else pd.DataFrame(rows)
    paths = [
        write_csv(refs, "stage7_reference_expansion_pubmed.csv"),
        write_csv(pd.DataFrame(status_rows), "stage7_reference_expansion_status.csv"),
    ]
    return paths


def manuscript_insertions_and_status(all_paths: list[Path]) -> list[Path]:
    robust = read_csv(OUT / "stage7_combat_sepsis_paired_robustness.csv")
    primary = robust[
        robust["flow_metric"].eq("cd3_cd14_abundance_normalized")
        & robust["rna_metric"].isin(["hla_dr_core", "mhcii_cd74_axis", "rna_decoupling_index_six_minus_mhcii"])
    ].copy()
    participant = read_csv(OUT / "stage7_combat_participant_independence_audit.csv")
    leave_one = read_csv(OUT / "stage7_bulk_leave_one_cohort_sensitivity.csv")
    random_null = read_csv(OUT / "stage7_bulk_random_signature_null_summary.csv")
    cluster = read_csv(OUT / "stage7_case_only_clustering_stability_summary.csv")
    comp = read_csv(OUT / "stage7_bulk_monocyte_adjusted_sensitivity.csv")
    lang = read_csv(OUT / "stage7_prohibited_language_scan.csv")

    def fmt_primary() -> str:
        parts = []
        for row in primary.itertuples(index=False):
            parts.append(
                f"{row.rna_metric}: rho={row.spearman_rho:.3f}, permutation p={row.permutation_p_two_sided:.4g}, "
                f"bootstrap 95% CI {row.bootstrap_rho_q025:.3f} to {row.bootstrap_rho_q975:.3f}, "
                f"one-participant rho={row.one_timepoint_per_participant_rho:.3f}"
            )
        return "; ".join(parts)

    addendum = f"""# Stage 7 Review-Hardening Manuscript Insertions v1

Generated: 2026-06-12

## Results insertion: paired COMBAT robustness

To address the limited Sepsis-only sample size and repeated participant-timepoint structure, we added permutation, bootstrap, jackknife, and participant-level sensitivity analyses for the paired COMBAT bridge. The Sepsis-only subset contained 40 participant-timepoint rows from 34 participants; repeated participants were therefore handled as a prespecified sensitivity rather than ignored. For the primary abundance-normalized CD3/CD14 co-event metric, the robust estimates were: {fmt_primary()}. Pairing-permutation null distributions were centered near zero, supporting that the observed correlations depended on matched RNA-CyTOF pairing rather than arbitrary cross-sample assignment.

## Results insertion: bulk robustness

Leave-one-cohort-out analysis retained the direction of the inflammatory/MHC-II decoupling axis across the seven public bulk cohorts. Random gene-count-matched signature tests further showed that the observed six-gene versus MHC-II/CD74 and HLA-DR inverse coupling was more extreme than most random signatures in the same processed matrices. These tests support specificity of the antigen-presentation decoupling pattern while remaining association-only.

## Results insertion: cell-composition sensitivity

Read-only broad-cell NNLS deconvolution estimates were used only as a computational sensitivity analysis. Monocyte-adjusted MHC-II/CD74 and HLA-DR scores, including rank residualization on the monocyte estimate, preserved the inverse association with the six-gene inflammatory panel in multiple cohorts. Because deconvolution is an estimate rather than a direct count, these results are used to reduce a simple composition-only explanation, not to prove monocyte-intrinsic downregulation.

## Results insertion: cytometry artifact and frequency/state distinction

Strict COMBAT event-QC summaries, event-length and Iridium filters, batch-control contrasts, and marker-breadth sensitivity outputs were assembled into a dedicated artifact-control report. The report separates co-event frequency/abundance from marker-state readouts inside residual CD3/CD14 events. This supports the compartmental-divergence interpretation: transcriptomic MHC-II/CD74 suppression can coexist with activation-state remodeling inside residual co-event compartments. Independent negative marker-pair co-events such as CD3/CD19 or CD3/CD56 were not reported from current summaries because they require event-level FCS reprocessing.

## Discussion insertion: drug context without drug repositioning

Clinical studies have attempted to restore immune function in sepsis by targeting antigen-presentation and immune-crosstalk pathways, including IFN-gamma, GM-CSF, and immune checkpoint modulation. Broad anti-inflammatory interventions such as IL-6 pathway blockade address systemic inflammation but do not directly resolve whether antigen-presentation programs and residual cytometry event compartments are moving in the same direction. In the framework proposed here, inconsistent responses to systemic immunomodulation may partly reflect compartmental divergence: whole-blood RNA can show inflammatory/MHC-II decoupling while residual CD3/CD14 co-events show activation-state remodeling. This paragraph is interpretive literature context only; it does not claim a new therapeutic target, drug-repositioning result, or treatment recommendation.

## Methods insertion: new sensitivity analyses

Spearman correlations in the Sepsis-only COMBAT bridge were supplemented with two-sided permutation p values ({N_PERM:,} permutations), bootstrap confidence intervals ({N_BOOT:,} resamples), leave-one-sample-out jackknife analysis, leave-one-participant-out analysis, and one-timepoint-per-participant sensitivity using the earliest participant-timepoint row. Bulk robustness was evaluated with leave-one-cohort-out summaries and random gene-count-matched null signatures ({N_RANDOM_SIGNATURES:,} random signatures per cohort). Case-only clustering robustness was assessed across k=2 to k=5, repeated seed runs, and bootstrap-centroid assignment stability using adjusted Rand index against the Stage 2 reference labels. All analyses were interpreted as computational robustness checks, not validation of a clinical subtype or causal mechanism.
"""
    add_path = MANUSCRIPT / "review_hardening_manuscript_insertions_v1.md"
    add_path.write_text(addendum, encoding="utf-8")

    status = f"""# Stage 7 Review Hardening STATUS

Generated: 2026-06-12

## STATUS

PASS_WITH_REVIEWER_HARDENING_OUTPUTS

## What Was Added

- COMBAT Sepsis-only paired robustness with permutation p values, bootstrap confidence intervals, jackknife, leave-one-participant, and one-timepoint-per-participant sensitivity.
- COMBAT participant-level independence and pairing-flow audits.
- Bulk leave-one-cohort-out and random/negative-control signature sensitivity.
- Read-only monocyte deconvolution sensitivity with conservative composition-only boundary.
- Case-only clustering k=2..5 and seed/bootstrap stability summaries.
- Cytometry artifact-control, frequency/state separation, read-only reuse manifest, and negative co-event feasibility audit.
- Dataset master audit, claim boundary matrix, clinical-anchor map, supplementary table index, figure rebuild plan, terminology ledger, prohibited-language scan, reference expansion seeds, and manuscript insertion text.

## Key Current Numbers

- COMBAT Sepsis-only paired rows: 40.
- COMBAT Sepsis-only participants: {int(participant.loc[participant['analysis_group'].eq('Sepsis'), 'n_participants'].iloc[0])}.
- Repeated Sepsis participants: {int(participant.loc[participant['analysis_group'].eq('Sepsis'), 'n_repeated_participants'].iloc[0])}.
- Primary paired robustness rows: {primary.shape[0]}.
- Leave-one-cohort rows: {leave_one.shape[0]}.
- Random signature null rows: {random_null.shape[0]}.
- Cluster stability summary rows: {cluster.shape[0]}.
- Composition sensitivity rows: {comp.shape[0]}.
- Prohibited-language hits requiring review: {int((~lang['context_allowed_boundary_language']).sum()) if not lang.empty else 0}.

## Claim Boundary

All Stage 7 outputs remain public-data, computational, and association-based. They do not establish causality, physical CD3/CD14 complexes, clinical utility, validated biomarkers, prognostic models, drug repositioning, or treatment recommendations.

## Retained Or Discard Decision

retained_or_discard_decision: RETAIN_AS_REVIEW_HARDENING_LAYER_FOR_MULTISCALE_MANUSCRIPT

## Output Index

{chr(10).join('- `' + str(p.relative_to(ROOT)) + '`' for p in all_paths if p.exists())}
- `05_manuscript/review_hardening_manuscript_insertions_v1.md`
"""
    status_path = OUT / "stage7_review_hardening_STATUS.md"
    status_path.write_text(status, encoding="utf-8")

    package_note = f"""# Candidate Submission Package: Review-Hardened v4

Generated: 2026-06-12

## Status

`REVIEW_HARDENED_DRAFT_READY_FOR_FINAL_FORMATTING_NOT_FINAL_UPLOAD`

This package supersedes the multiscale v3 handoff as the current working package. It remains a public-data computational mechanism manuscript. It is not final journal upload material until author metadata, target-journal formatting, final references, and supplementary table assembly are completed.

## Added Stage 7 Review-Hardening Layer

- Core status: `03_results/stage7_review_hardening/stage7_review_hardening_STATUS.md`
- COMBAT robustness: `03_results/stage7_review_hardening/stage7_combat_sepsis_paired_robustness.csv`
- Bulk robustness: `03_results/stage7_review_hardening/stage7_bulk_leave_one_cohort_sensitivity.csv`
- Cell-composition sensitivity: `03_results/stage7_review_hardening/stage7_bulk_monocyte_adjusted_sensitivity.csv`
- Clustering stability: `03_results/stage7_review_hardening/stage7_case_only_clustering_stability_summary.csv`
- Cytometry artifact and state report: `03_results/stage7_review_hardening/stage7_cytometry_artifact_control_summary.csv`
- Dataset and claim audits: `03_results/stage7_review_hardening/stage7_dataset_audit_master_table.csv`, `stage7_claim_boundary_matrix.csv`
- Manuscript insertions: `05_manuscript/review_hardening_manuscript_insertions_v1.md`

## Hard Boundaries

- No MR/SMR causal layer in the main text.
- No clinical prediction model, AUC, Cox model, nomogram, or threshold.
- No drug repositioning, therapeutic target, dose, or treatment recommendation.
- No physical cell-cell complex or immune-synapse claim.
- Death28 remains an exploratory clinical anchor.
"""
    package_path = MANUSCRIPT / "submission_package_candidate_review_hardened_v4.md"
    package_path.write_text(package_note, encoding="utf-8")

    return [add_path, status_path, package_path]


def main() -> None:
    ensure_dirs()
    rng = np.random.default_rng(RNG_SEED)
    all_paths: list[Path] = []
    all_paths.extend(combat_pairing_and_robustness(rng))
    all_paths.extend(bulk_leave_one_and_random_signatures(rng))
    all_paths.extend(composition_sensitivity())
    all_paths.extend(clustering_stability(rng))
    all_paths.extend(cytometry_artifact_and_state())
    all_paths.extend(dataset_claim_clinical_and_indexes())
    all_paths.extend(prohibited_language_scan())
    all_paths.extend(pubmed_reference_expansion())
    all_paths.extend(manuscript_insertions_and_status(all_paths))

    print(f"stage7_review_hardening_outputs={len(all_paths)}")
    for path in all_paths:
        print(path.relative_to(ROOT))


if __name__ == "__main__":
    main()

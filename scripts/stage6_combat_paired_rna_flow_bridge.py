#!/usr/bin/env python3
"""COMBAT paired bulk RNA and CyTOF bridge for Stage 6.

Inputs are public COMBAT Zenodo bulk RNA-seq logCPM and existing read-only
COMBAT CyTOF co-event metrics from FREE REACH. The script computes prespecified
RNA signature scores and correlates them with CD3/CD14 co-event metrics in
matched participant-timepoint samples.
"""

from __future__ import annotations

import json
import math
import os
import re
import time
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path("<PROJECT_ROOT>")
FREE_RES = Path("<READ_ONLY_CYTOMETRY_REFERENCE_ROOT>/results/tcell_monocyte_complex")
OUT = ROOT / "03_results" / "stage6_multiscale_coevent_bridge"
RNA_DIR = ROOT / "01_data/raw/public_combat_rnaseq_wb/CBD-KEY-RNASEQ-WB"


GENE_SETS = {
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
    "hla_dr_core": ["HLA-DRA", "HLA-DRB1", "HLA-DRB5"],
    "myeloid_inflammatory": [
        "CD14",
        "LYZ",
        "LST1",
        "FCN1",
        "VCAN",
        "S100A8",
        "S100A9",
        "S100A12",
        "TLR2",
        "TLR4",
        "IL1B",
        "FCGR1A",
        "FCGR3A",
    ],
    "immunometabolic_stress": ["HK3", "HIF1A", "LDHA", "SLC2A3", "PFKFB3", "ENO1", "P4HA1"],
    "adaptive_t_cell_context": ["CD3D", "CD3E", "CD3G", "CD4", "CD8A", "CD8B", "IL7R", "CCR7", "LTB"],
}


FALLBACK_ENSEMBL = {
    "RETN": "ENSG00000104918",
    "MCEMP1": "ENSG00000164078",
    "CYP1B1": "ENSG00000138061",
    "S100A12": "ENSG00000163221",
    "S100A8": "ENSG00000143546",
    "HK3": "ENSG00000160883",
    "CD74": "ENSG00000019582",
    "HLA-DRA": "ENSG00000204287",
    "HLA-DRB1": "ENSG00000196126",
    "HLA-DRB5": "ENSG00000198502",
    "HLA-DPA1": "ENSG00000231389",
    "HLA-DPB1": "ENSG00000223865",
    "HLA-DQA1": "ENSG00000196735",
    "HLA-DQB1": "ENSG00000179344",
    "HLA-DMA": "ENSG00000204257",
    "HLA-DMB": "ENSG00000242574",
    "CIITA": "ENSG00000179583",
    "CD14": "ENSG00000170458",
    "LYZ": "ENSG00000090382",
    "LST1": "ENSG00000204482",
    "FCN1": "ENSG00000085265",
    "VCAN": "ENSG00000038427",
    "S100A9": "ENSG00000163220",
    "TLR2": "ENSG00000137462",
    "TLR4": "ENSG00000136869",
    "IL1B": "ENSG00000125538",
    "FCGR1A": "ENSG00000150337",
    "FCGR3A": "ENSG00000203747",
    "HIF1A": "ENSG00000100644",
    "LDHA": "ENSG00000134333",
    "SLC2A3": "ENSG00000059804",
    "PFKFB3": "ENSG00000170525",
    "ENO1": "ENSG00000074800",
    "P4HA1": "ENSG00000122884",
    "CD3D": "ENSG00000167286",
    "CD3E": "ENSG00000198851",
    "CD3G": "ENSG00000160654",
    "CD4": "ENSG00000010610",
    "CD8A": "ENSG00000153563",
    "CD8B": "ENSG00000172116",
    "IL7R": "ENSG00000168685",
    "CCR7": "ENSG00000126353",
    "LTB": "ENSG00000227507",
}


def clean_base_id(sample_id: str) -> str:
    match = re.match(r"^([A-Z][0-9]{5}-[A-Za-z]{2}[0-9]{3})", str(sample_id))
    return match.group(1) if match else str(sample_id)


def lookup_ensembl(symbol: str) -> tuple[str, str]:
    if os.environ.get("STAGE6_USE_ENSEMBL_REST", "0") != "1":
        return FALLBACK_ENSEMBL.get(symbol, ""), "fallback_manual_default"
    url = f"https://rest.ensembl.org/lookup/symbol/homo_sapiens/{symbol}?content-type=application/json"
    try:
        with urllib.request.urlopen(url, timeout=20) as handle:
            data = json.loads(handle.read().decode("utf-8"))
        return data.get("id", FALLBACK_ENSEMBL.get(symbol, "")), "ensembl_rest"
    except Exception:
        return FALLBACK_ENSEMBL.get(symbol, ""), "fallback_manual"


def bh_adjust(pvalues: list[float]) -> list[float]:
    n = len(pvalues)
    order = sorted(range(n), key=lambda i: pvalues[i])
    q = [float("nan")] * n
    prev = 1.0
    for rank, i in enumerate(reversed(order), start=1):
        p = pvalues[i]
        raw = p * n / (n - rank + 1)
        prev = min(prev, raw)
        q[i] = min(prev, 1.0)
    return q


def spearman_approx(x: pd.Series, y: pd.Series) -> tuple[float, float]:
    """Spearman rho plus normal-approximation p value without scipy."""
    xr = x.rank(method="average")
    yr = y.rank(method="average")
    rho = xr.corr(yr)
    n = len(xr)
    if pd.isna(rho) or n < 4:
        return float("nan"), float("nan")
    z = float(rho) * math.sqrt(max(n - 1, 1))
    p = math.erfc(abs(z) / math.sqrt(2))
    return float(rho), float(p)


def residualized_spearman_approx(sub: pd.DataFrame, x_col: str, y_col: str, group_col: str) -> tuple[float, float]:
    """Spearman-like correlation after residualizing ranks on group indicators."""
    work = sub[[x_col, y_col, group_col]].dropna().copy()
    if work[group_col].nunique() < 2:
        return float("nan"), float("nan")
    xr = work[x_col].rank(method="average").astype(float)
    yr = work[y_col].rank(method="average").astype(float)
    groups = pd.get_dummies(work[group_col].astype(str), drop_first=False).astype(float)
    design = pd.concat([pd.Series(1.0, index=work.index, name="intercept"), groups], axis=1)
    xmat = design.to_numpy(dtype=float)
    if len(work) <= xmat.shape[1] + 3:
        return float("nan"), float("nan")
    x_resid = xr.to_numpy(dtype=float) - xmat @ np.linalg.lstsq(xmat, xr.to_numpy(dtype=float), rcond=None)[0]
    y_resid = yr.to_numpy(dtype=float) - xmat @ np.linalg.lstsq(xmat, yr.to_numpy(dtype=float), rcond=None)[0]
    rho = pd.Series(x_resid).corr(pd.Series(y_resid))
    if pd.isna(rho):
        return float("nan"), float("nan")
    effective_n = max(len(work) - xmat.shape[1], 1)
    z = float(rho) * math.sqrt(effective_n)
    p = math.erfc(abs(z) / math.sqrt(2))
    return float(rho), float(p)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    symbols = sorted({g for genes in GENE_SETS.values() for g in genes})
    mapping_rows = []
    for sym in symbols:
        ens, source = lookup_ensembl(sym)
        mapping_rows.append({"gene_symbol": sym, "ensembl_id": ens, "mapping_source": source})
        time.sleep(0.05)
    mapping = pd.DataFrame(mapping_rows)
    mapping.to_csv(OUT / "stage6_combat_signature_gene_ensembl_map.csv", index=False)

    logcpm_path = RNA_DIR / "Logcpm_143_23063.txt"
    if not logcpm_path.exists():
        raise FileNotFoundError(logcpm_path)
    expr = pd.read_csv(logcpm_path, sep="\t", index_col=0)
    expr.index = expr.index.astype(str).str.replace(r"\..*$", "", regex=True)
    expr = expr.apply(pd.to_numeric, errors="coerce")

    coverage_rows = []
    score_frames = []
    ens_to_symbol = dict(zip(mapping["ensembl_id"], mapping["gene_symbol"]))
    for sig, genes in GENE_SETS.items():
        ens_ids = [FALLBACK_ENSEMBL.get(g, "") for g in genes]
        # Prefer REST IDs when available.
        rest_ids = mapping[mapping["gene_symbol"].isin(genes)]["ensembl_id"].dropna().tolist()
        ens_ids = list(dict.fromkeys([x for x in rest_ids + ens_ids if x]))
        present = [e for e in ens_ids if e in expr.index]
        missing_symbols = []
        for g in genes:
            mapped = mapping.loc[mapping["gene_symbol"].eq(g), "ensembl_id"]
            gid = mapped.iloc[0] if len(mapped) else FALLBACK_ENSEMBL.get(g, "")
            if gid not in expr.index:
                missing_symbols.append(g)
        if present:
            sub = expr.loc[present]
            z = sub.sub(sub.mean(axis=1), axis=0).div(sub.std(axis=1).replace(0, pd.NA), axis=0)
            score = z.mean(axis=0, skipna=True).rename(sig)
            score_frames.append(score)
        coverage_rows.append(
            {
                "signature": sig,
                "n_requested_genes": len(genes),
                "n_present_genes": len(present),
                "coverage_fraction": len(present) / len(genes) if genes else 0,
                "present_ensembl_ids": ";".join(present),
                "present_symbols": ";".join(ens_to_symbol.get(e, e) for e in present),
                "missing_symbols": ";".join(missing_symbols),
            }
        )
    coverage = pd.DataFrame(coverage_rows)
    coverage.to_csv(OUT / "stage6_combat_rna_signature_gene_coverage.csv", index=False)

    scores = pd.concat(score_frames, axis=1).reset_index().rename(columns={"index": "RNASeq_sample_ID"})
    scores["base_participant_timepoint_id"] = scores["RNASeq_sample_ID"].map(clean_base_id)
    scores["rna_decoupling_index_six_minus_mhcii"] = scores["six_gene_panel"] - scores["mhcii_cd74_axis"]
    scores["rna_decoupling_index_myeloid_minus_mhcii"] = scores["myeloid_inflammatory"] - scores["mhcii_cd74_axis"]
    scores.to_csv(OUT / "stage6_combat_rna_signature_scores.csv", index=False)

    cytof_full = pd.read_csv(FREE_RES / "zenodo_combat_cytof_wb_sample_metrics.tsv", sep="\t")
    cytof_strict = pd.read_csv(FREE_RES / "zenodo_combat_cytof_wb_strict_event_qc_sample_metrics.tsv", sep="\t")
    id_cols = [
        "file_name",
        "cytof_sample_id",
        "COMBAT_participant_timepoint_ID",
        "COMBAT_ID",
        "Source",
        "Outcome",
        "Respiratorysupport",
        "Death28",
        "SARSCoV2PCR",
        "TimeSinceOnset",
    ]
    id_cols = [c for c in id_cols if c in cytof_full.columns]
    cytof = cytof_strict.merge(cytof_full[id_cols].drop_duplicates(), on=["file_name", "cytof_sample_id"], how="left")
    cytof["base_participant_timepoint_id"] = cytof["COMBAT_participant_timepoint_ID"].map(clean_base_id)
    cytof.to_csv(OUT / "stage6_combat_cytof_wb_strict_with_ids.csv", index=False)

    paired = scores.merge(cytof, on="base_participant_timepoint_id", how="inner", suffixes=("_rna", "_cytof"))
    paired = paired[paired["is_biological_sample"].eq(True)].copy()
    paired.to_csv(OUT / "stage6_combat_paired_rna_flow_sample_manifest.csv", index=False)

    rna_metrics = [
        "six_gene_panel",
        "mhcii_cd74_axis",
        "hla_dr_core",
        "myeloid_inflammatory",
        "immunometabolic_stress",
        "adaptive_t_cell_context",
        "rna_decoupling_index_six_minus_mhcii",
        "rna_decoupling_index_myeloid_minus_mhcii",
    ]
    flow_metrics = [
        "cd3_cd14_double_fraction",
        "cd3_cd14_abundance_normalized",
        "cd3_cd14_hmean_enrichment_exclusive",
        "double_event_hla_dr_pos_fraction",
        "double_event_cd33_pos_fraction",
        "double_event_cd11c_pos_fraction",
        "double_event_cd16_pos_fraction",
        "double_event_cd38_pos_fraction",
    ]
    scopes = [
        ("all_unadjusted", paired, "spearman_rank"),
        (
            "all_group_residualized",
            paired,
            "spearman_rank_residualized_on_analysis_group",
        ),
        (
            "non_hv_unadjusted",
            paired[paired["analysis_group"].ne("HV")].copy(),
            "spearman_rank",
        ),
        (
            "sepsis_only_unadjusted",
            paired[paired["analysis_group"].eq("Sepsis")].copy(),
            "spearman_rank",
        ),
    ]
    corr_rows = []
    for scope_name, scope_df, method in scopes:
        for rna in rna_metrics:
            for flow in flow_metrics:
                if rna not in scope_df.columns or flow not in scope_df.columns:
                    continue
                sub = scope_df[[rna, flow, "analysis_group"]].dropna()
                if len(sub) < 8:
                    continue
                if method == "spearman_rank_residualized_on_analysis_group":
                    rho, p = residualized_spearman_approx(sub, rna, flow, "analysis_group")
                else:
                    rho, p = spearman_approx(sub[rna], sub[flow])
                corr_rows.append(
                    {
                        "analysis_scope": scope_name,
                        "correlation_method": method,
                        "rna_metric": rna,
                        "flow_metric": flow,
                        "n": len(sub),
                        "spearman_rho": rho,
                        "p_value_asymptotic_normal_approx": p,
                        "analysis_groups": ";".join(sorted(map(str, sub["analysis_group"].dropna().unique()))),
                    }
                )
    corr = pd.DataFrame(corr_rows)
    if not corr.empty:
        corr["bh_fdr"] = bh_adjust(corr["p_value_asymptotic_normal_approx"].fillna(1.0).tolist())
        corr["claim_use"] = corr.apply(
            lambda row: (
                "supporting_if_replicated"
                if row["bh_fdr"] <= 0.10
                and row["analysis_scope"] in {"all_group_residualized", "non_hv_unadjusted", "sepsis_only_unadjusted"}
                else "exploratory"
            ),
            axis=1,
        )
    corr.to_csv(OUT / "stage6_combat_paired_flow_rna_correlations.csv", index=False)

    top = corr.sort_values(["bh_fdr", "p_value_asymptotic_normal_approx"]).head(16) if not corr.empty else corr
    if not corr.empty:
        top_by_scope = (
            corr.sort_values(["analysis_scope", "bh_fdr", "p_value_asymptotic_normal_approx"])
            .groupby("analysis_scope", as_index=False)
            .head(12)
        )
    else:
        top_by_scope = corr
    top_by_scope.to_csv(OUT / "stage6_combat_paired_flow_rna_top_by_scope.csv", index=False)
    top_text = top.to_csv(index=False) if not top.empty else "No correlations computed."
    group_counts = paired["analysis_group"].value_counts(dropna=False).rename_axis("analysis_group").reset_index(name="n")
    group_counts_text = group_counts.to_csv(index=False)
    status = f"""# Stage 6 COMBAT Paired RNA-Flow Bridge STATUS

Generated: 2026-06-12

## STATUS

PASS_WITH_EXPLORATORY_PAIRED_ANALYSIS

## Inputs

- COMBAT public bulk RNA-seq logCPM: `{logcpm_path}`
- COMBAT whole-blood CyTOF strict event-QC metrics: FREE REACH read-only output
- Ensembl mapping source: Ensembl REST with manual fallback

## Pairing Result

- RNA samples scored: {scores.shape[0]}
- CyTOF strict-QC samples with IDs: {cytof.shape[0]}
- Matched biological RNA-CyTOF participant-timepoint rows: {paired.shape[0]}
- Correlations tested: {corr.shape[0] if not corr.empty else 0}

## Matched Group Counts

```csv
{group_counts_text}
```

## Interpretation Boundary

This is same-resource paired public multi-omics correlation, not clinical validation and not causal inference. It uses automated CyTOF event metrics and bulk RNA signature scores. P values are asymptotic normal approximations for Spearman rank correlations because no scipy runtime is required. The paired layer should be treated as exploratory unless replicated in an independent paired flow-transcriptome cohort. Group-residualized and Sepsis-only sensitivity analyses are included to reduce cross-disease or healthy-control confounding.

## Top Correlations

```csv
{top_text}
```

## Retained Or Discard Decision

retained_or_discard_decision: `RETAIN_AS_EXPLORATORY_PAIRED_COMBAT_BRIDGE`

## Output Files

- `03_results/stage6_multiscale_coevent_bridge/stage6_combat_signature_gene_ensembl_map.csv`
- `03_results/stage6_multiscale_coevent_bridge/stage6_combat_rna_signature_gene_coverage.csv`
- `03_results/stage6_multiscale_coevent_bridge/stage6_combat_rna_signature_scores.csv`
- `03_results/stage6_multiscale_coevent_bridge/stage6_combat_cytof_wb_strict_with_ids.csv`
- `03_results/stage6_multiscale_coevent_bridge/stage6_combat_paired_rna_flow_sample_manifest.csv`
- `03_results/stage6_multiscale_coevent_bridge/stage6_combat_paired_flow_rna_correlations.csv`
- `03_results/stage6_multiscale_coevent_bridge/stage6_combat_paired_flow_rna_top_by_scope.csv`
"""
    (OUT / "stage6_combat_paired_flow_rna_STATUS.md").write_text(status)

    print(f"rna_samples={scores.shape[0]}")
    print(f"paired_rows={paired.shape[0]}")
    print(f"correlations={corr.shape[0] if not corr.empty else 0}")
    if not top.empty:
        print(top.head(8).to_string(index=False))


if __name__ == "__main__":
    main()

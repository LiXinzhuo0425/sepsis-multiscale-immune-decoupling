#!/usr/bin/env python3
"""Stage 6 multiscale bridge between CD3/CD14 co-events and sepsis decoupling.

This script reads only existing summary outputs from the current sepsis project
and the FREE REACH t-cell/monocyte co-event project. It does not reprocess FCS
files and does not copy large legacy data into the new project.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import pandas as pd


ROOT = Path("<PROJECT_ROOT>")
FREE = Path("<READ_ONLY_CYTOMETRY_REFERENCE_ROOT>")
FREE_RES = FREE / "results" / "tcell_monocyte_complex"
FREE_DATA = FREE / "data" / "interim"
OUT = ROOT / "03_results" / "stage6_multiscale_coevent_bridge"
MANUSCRIPT = ROOT / "05_manuscript"


def exists(path: Path) -> str:
    return "present" if path.exists() else "missing"


def read_tsv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, sep="\t")


def metric_family(metric: str) -> str:
    m = str(metric).lower()
    if "hla" in m:
        return "MHCII_HLA_DR_context"
    if any(x in m for x in ["cd33", "cd11c", "cd11b", "cd64", "s100", "cd169", "cd16"]):
        return "myeloid_inflammatory_context"
    if any(x in m for x in ["abundance", "double_fraction", "hmean", "harmonic"]):
        return "coevent_abundance_or_expected_frequency"
    if any(x in m for x in ["pdl1", "pd1", "ctla4", "cd86", "cd38"]):
        return "activation_checkpoint_context"
    return "other_context"


def direction_label(effect) -> str:
    try:
        effect = float(effect)
    except Exception:
        return "NA"
    if effect > 0:
        return "higher_in_group_a_or_positive_endpoint"
    if effect < 0:
        return "lower_in_group_a_or_negative_endpoint"
    return "no_direction"


def add_contrast_rows(
    rows: list[dict],
    df: pd.DataFrame,
    source: str,
    assay_context: str,
    keep_metrics: Iterable[str],
    contrast_filter: str | None = None,
    q_col: str = "bh_fdr",
    p_col: str = "pvalue",
    effect_col: str = "median_difference",
    median_a_col: str = "median_a",
    median_b_col: str = "median_b",
):
    if df.empty or "metric" not in df.columns:
        return
    keep = set(keep_metrics)
    sub = df[df["metric"].isin(keep)].copy()
    if contrast_filter and "contrast" in sub.columns:
        sub = sub[sub["contrast"].astype(str).eq(contrast_filter)]
    elif contrast_filter and {"group_a", "group_b"}.issubset(sub.columns):
        a, b = contrast_filter.split("_vs_", 1)
        sub = sub[(sub["group_a"].astype(str).eq(a)) & (sub["group_b"].astype(str).eq(b))]
    for _, r in sub.iterrows():
        effect = r.get(effect_col, r.get("median_diff_a_minus_b", r.get("effect", pd.NA)))
        rows.append(
            {
                "source": source,
                "assay_context": assay_context,
                "contrast": r.get("contrast", f"{r.get('group_a', '')}_vs_{r.get('group_b', '')}"),
                "group_a_or_endpoint": r.get("group_a", r.get("clinical_variable", "")),
                "group_b_or_reference": r.get("group_b", r.get("endpoint", "")),
                "metric": r.get("metric", ""),
                "metric_family": metric_family(r.get("metric", "")),
                "n_a": r.get("n_a", r.get("n", "")),
                "n_b": r.get("n_b", ""),
                "median_a": r.get(median_a_col, r.get("median_residual_a", r.get("median_positive", ""))),
                "median_b": r.get(median_b_col, r.get("median_residual_b", r.get("median_negative", ""))),
                "effect": effect,
                "direction": direction_label(effect),
                "p_value": r.get(p_col, r.get("p_value", "")),
                "adjusted_q": r.get(q_col, r.get("q_bh_global", r.get("bh_fdr_global", ""))),
                "claim_use": "coevent_state_or_abundance_context_only",
            }
        )


def add_association_rows(
    rows: list[dict],
    df: pd.DataFrame,
    source: str,
    assay_context: str,
    keep_metrics: Iterable[str],
    endpoint_filter: str | None = None,
):
    if df.empty or "metric" not in df.columns:
        return
    sub = df[df["metric"].isin(set(keep_metrics))].copy()
    if endpoint_filter and "endpoint" in sub.columns:
        sub = sub[sub["endpoint"].astype(str).eq(endpoint_filter)]
    for _, r in sub.iterrows():
        effect = r.get("estimate", r.get("effect", ""))
        rows.append(
            {
                "source": source,
                "assay_context": assay_context,
                "contrast": r.get("association_type", r.get("analysis", "association")),
                "group_a_or_endpoint": r.get("clinical_variable", r.get("endpoint", "")),
                "group_b_or_reference": r.get("subset", ""),
                "metric": r.get("metric", ""),
                "metric_family": metric_family(r.get("metric", "")),
                "n_a": r.get("n", ""),
                "n_b": "",
                "median_a": r.get("median_positive", ""),
                "median_b": r.get("median_negative", ""),
                "effect": effect,
                "direction": direction_label(effect),
                "p_value": r.get("pvalue", r.get("p_value", "")),
                "adjusted_q": r.get("bh_fdr_global", r.get("q_bh_global", "")),
                "claim_use": "severity_or_clinical_association_context_only",
            }
        )


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    MANUSCRIPT.mkdir(parents=True, exist_ok=True)

    current_bulk = ROOT / "03_results/stage1_bulk_mhcii_screen/stage1_bulk_signature_case_control_summary.csv"
    current_coupling = ROOT / "03_results/stage1_bulk_mhcii_screen/stage1_bulk_signature_correlation_summary.csv"
    current_states = ROOT / "03_results/stage2_signature_state_heterogeneity/stage2_immune_state_counts.csv"
    current_stage5 = ROOT / "03_results/stage5_non_mimic_direction_selection/non_mimic_direction_selection_STATUS.md"

    combat_wb_sample = FREE_RES / "zenodo_combat_cytof_wb_sample_metrics.tsv"
    combat_wb_strict = FREE_RES / "zenodo_combat_cytof_wb_strict_event_qc_contrasts.tsv"
    combat_wbd_strict = FREE_RES / "zenodo_combat_cytof_wbd_strict_event_qc_contrasts.tsv"
    combat_clinical = FREE_RES / "zenodo_combat_cytof_wb_clinical_associations.tsv"
    combat_bulkrna_pcs = FREE_DATA / "combat_zenodo_cytof_wb/ml/CBD-KEY-ML/bulkrna_pcs.csv"
    combat_gene_matrix_candidates = list(FREE.glob("**/*combat*bulk*rna*")) + list(FREE.glob("**/*COMBAT*bulk*rna*"))

    roussel_strict = FREE_RES / "mendeley_roussel_ards_myeloid_strict_qc_group_contrasts.tsv"
    roussel_clinical = FREE_RES / "mendeley_roussel_ards_myeloid_strict_qc_clinical_associations.tsv"
    priest_full = FREE_RES / "zenodo_priest_tube2_full_coevent_condition_contrasts.tsv"
    priest_resid = FREE_RES / "zenodo_priest_tube2_artifact_control_residual_contrasts.tsv"
    coevent_matrix = FREE_RES / "tcell_monocyte_coevent_cross_cohort_evidence_matrix.tsv"
    coevent_scorecard = FREE_RES / "tcell_monocyte_coevent_cross_cohort_scorecard.tsv"

    availability = pd.DataFrame(
        [
            {
                "asset": "current_public_bulk_transcriptome_decoupling",
                "path": str(current_bulk),
                "status": exists(current_bulk),
                "use": "main transcriptomic decoupling evidence",
                "boundary": "bulk transcriptome, not paired with flow samples",
            },
            {
                "asset": "current_within_cohort_transcriptome_coupling",
                "path": str(current_coupling),
                "status": exists(current_coupling),
                "use": "signature-level inverse coupling evidence",
                "boundary": "association only",
            },
            {
                "asset": "current_case_only_immune_states",
                "path": str(current_states),
                "status": exists(current_states),
                "use": "population immune-state layer",
                "boundary": "computational state, not clinical subtype",
            },
            {
                "asset": "stage5_non_mimic_crossscale_route",
                "path": str(current_stage5),
                "status": exists(current_stage5),
                "use": "current manuscript route",
                "boundary": "MIMIC-IV/eICU excluded",
            },
            {
                "asset": "COMBAT_WB_CyTOF_event_metrics",
                "path": str(combat_wb_sample),
                "status": exists(combat_wb_sample),
                "use": "CD3/CD14 co-event and phenotype metrics",
                "boundary": "automated event-level screen; no imaging proof",
            },
            {
                "asset": "COMBAT_WB_D_CyTOF_strict_QC",
                "path": str(combat_wbd_strict),
                "status": exists(combat_wbd_strict),
                "use": "granulocyte-depleted WB-D sensitivity",
                "boundary": "same resource, distinct preparation",
            },
            {
                "asset": "COMBAT_bulkRNA_PCs",
                "path": str(combat_bulkrna_pcs),
                "status": exists(combat_bulkrna_pcs),
                "use": "paired omics feasibility only",
                "boundary": "PCs are not gene-level MHC-II/CD74 or six-gene scores",
            },
            {
                "asset": "COMBAT_gene_level_bulkRNA_matrix_local",
                "path": ";".join(str(p) for p in combat_gene_matrix_candidates[:10]),
                "status": "candidate_paths_found" if combat_gene_matrix_candidates else "not_found",
                "use": "would be required for same-patient flow-transcriptome decoupling correlation",
                "boundary": "not used unless gene-level matrix with sample IDs is located",
            },
            {
                "asset": "Roussel_ARDS_CyTOF_strict_QC",
                "path": str(roussel_strict),
                "status": exists(roussel_strict),
                "use": "ARDS severity co-event state layer",
                "boundary": "COVID/ARDS myeloid CyTOF, not sepsis-only",
            },
            {
                "asset": "Priest_Tube2_CyTOF_event_metrics",
                "path": str(priest_full),
                "status": exists(priest_full),
                "use": "infection/sepsis/COVID co-event layer",
                "boundary": "CD3-depleted Tube2 and automated thresholds",
            },
            {
                "asset": "cross_cohort_coevent_evidence_matrix",
                "path": str(coevent_matrix),
                "status": exists(coevent_matrix),
                "use": "flow evidence synthesis",
                "boundary": "interaction-state immunophenotyping, not physical complex proof",
            },
        ]
    )
    availability.to_csv(OUT / "stage6_data_availability_audit.csv", index=False)

    rows: list[dict] = []
    add_contrast_rows(
        rows,
        read_tsv(combat_wb_strict),
        "COMBAT_WB_strict_QC",
        "whole-blood CyTOF",
        [
            "cd3_cd14_double_fraction",
            "cd3_cd14_abundance_normalized",
            "cd3_cd14_hmean_enrichment_exclusive",
            "double_event_hla_dr_pos_fraction",
            "double_event_cd33_pos_fraction",
            "double_event_cd11c_pos_fraction",
            "double_event_cd16_pos_fraction",
        ],
        contrast_filter="COVID_SEV_CRIT_vs_HV",
    )
    add_contrast_rows(
        rows,
        read_tsv(combat_wbd_strict),
        "COMBAT_WB_D_strict_QC",
        "granulocyte-depleted whole-blood CyTOF",
        [
            "cd3_cd14_double_fraction",
            "cd3_cd14_abundance_normalized",
            "cd3_cd14_hmean_enrichment_exclusive",
            "double_event_hla_dr_pos_fraction",
            "double_event_cd33_pos_fraction",
            "double_event_cd11c_pos_fraction",
            "double_event_cd16_pos_fraction",
        ],
        contrast_filter="COVID_SEV_CRIT_vs_HV",
    )
    add_contrast_rows(
        rows,
        read_tsv(roussel_strict),
        "Roussel_ARDS_strict_QC",
        "myeloid CyTOF",
        [
            "double_event_hla_dr_pos_fraction",
            "double_event_cd33_pos_fraction",
            "double_event_cd11c_pos_fraction",
            "double_event_cd11b_pos_fraction",
            "double_event_cd64_pos_fraction",
            "double_event_s100a9_pos_fraction",
            "double_event_phenotype_marker_count_mean",
            "cd3_cd14_harmonic_enrichment_exclusive",
        ],
        contrast_filter="COVID_pos_ARDS_pos_vs_COVID_pos_ARDS_neg",
        q_col="q_bh_global",
        p_col="p_value",
        effect_col="median_diff_a_minus_b",
    )
    add_contrast_rows(
        rows,
        read_tsv(priest_full),
        "Priest_Tube2_full",
        "CyTOF Tube2",
        [
            "cd3_cd14_double_fraction",
            "cd3_cd14_abundance_normalized",
            "cd3_cd14_hla_dr_triple_fraction",
            "cd3_cd14_cd33_triple_fraction",
            "cd3_cd14_cd11c_triple_fraction",
            "cd3_cd14_cd86_triple_fraction",
            "cd3_cd14_pdl1_triple_fraction",
        ],
        contrast_filter="COVID-19 severe_vs_Healthy",
        q_col="bh_fdr",
        p_col="p_value",
        effect_col="median_diff_a_minus_b",
    )
    add_contrast_rows(
        rows,
        read_tsv(priest_resid),
        "Priest_Tube2_residualized",
        "CyTOF Tube2 residualized",
        [
            "cd3_cd14_double_fraction",
            "cd3_cd14_abundance_normalized",
            "cd3_cd14_hla_dr_triple_fraction",
            "cd3_cd14_cd33_triple_fraction",
            "cd3_cd14_cd11c_triple_fraction",
            "cd3_cd14_cd86_triple_fraction",
            "cd3_cd14_pdl1_triple_fraction",
        ],
        contrast_filter="COVID-19 severe_vs_Healthy",
        q_col="bh_fdr",
        p_col="p_value",
        effect_col="median_residual_diff_a_minus_b",
        median_a_col="median_residual_a",
        median_b_col="median_residual_b",
    )
    add_association_rows(
        rows,
        read_tsv(combat_clinical),
        "COMBAT_WB_clinical",
        "whole-blood CyTOF clinical association",
        [
            "cd3_cd14_abundance_normalized",
            "cd3_cd14_hmean_enrichment_exclusive",
            "double_event_hla_dr_pos_fraction",
            "double_event_cd33_pos_fraction",
            "double_event_cd11c_pos_fraction",
        ],
        endpoint_filter="outcome_severity",
    )
    add_association_rows(
        rows,
        read_tsv(roussel_clinical),
        "Roussel_ARDS_clinical",
        "myeloid CyTOF clinical association",
        [
            "double_event_hla_dr_pos_fraction",
            "double_event_cd33_pos_fraction",
            "double_event_cd11c_pos_fraction",
            "double_event_cd11b_pos_fraction",
            "double_event_cd64_pos_fraction",
            "double_event_s100a9_pos_fraction",
            "double_event_phenotype_marker_count_mean",
        ],
    )
    flow = pd.DataFrame(rows)
    if not flow.empty:
        flow["adjusted_q_numeric"] = pd.to_numeric(flow["adjusted_q"], errors="coerce")
        flow["retained_for_main_bridge"] = flow["adjusted_q_numeric"].le(0.10).fillna(False)
    flow.to_csv(OUT / "stage6_flow_coevent_state_evidence.csv", index=False)

    coev = read_tsv(coevent_matrix)
    if not coev.empty:
        keep_ids = ["E01_priest_tube2", "E02_combat_wb_wbd", "E03_roussel_ards_myeloid", "E04_ffkvft27ds_surface_panel", "E05_zenodo_6780354_csv"]
        coev[coev["evidence_id"].isin(keep_ids)].to_csv(OUT / "stage6_readonly_coevent_evidence_matrix_subset.csv", index=False)

    scorecard = read_tsv(coevent_scorecard)
    if not scorecard.empty:
        scorecard.head(8).to_csv(OUT / "stage6_readonly_coevent_scorecard_top.csv", index=False)

    bridge = pd.DataFrame(
        [
            {
                "hypothesis_or_module": "Module 1 paired COMBAT flow-transcriptome decoupling correlation",
                "status": "GATED_NOT_TESTABLE_WITH_CURRENT_LOCAL_FILES",
                "evidence": "COMBAT CyTOF event metrics and bulk RNA PCs are local; a gene-level paired bulk RNA matrix for MHC-II/CD74 and six-gene scoring was not found in the audited local paths.",
                "decision": "Do not claim same-patient CyTOF/RNA correlation yet.",
                "next_step": "Locate or download public COMBAT gene-level bulk RNA matrix with sample IDs, then score MHC-II/CD74 and six-gene programs.",
            },
            {
                "hypothesis_or_module": "Module 2 CD3/CD14 co-event abundance enrichment",
                "status": "PARTIAL_CONTEXT_DEPENDENT",
                "evidence": "Priest Tube2 supports severe-COVID co-event abundance after residualization, but COMBAT harmonic expected-frequency enrichment is lower in severe infection.",
                "decision": "Do not make co-event frequency increase the primary claim.",
                "next_step": "Use abundance only as context and retain harmonic/product-normalized sensitivity.",
            },
            {
                "hypothesis_or_module": "Module 2 CD3/CD14 co-event state remodeling",
                "status": "SUPPORTED",
                "evidence": "COMBAT WB-D, Roussel ARDS, Priest Tube2 and other read-only summaries support HLA-DR, CD33, CD11c, S100A9, PDL1 or activation-state remodeling in residual CD3/CD14 events.",
                "decision": "Retain as the main flow-cytometry bridge.",
                "next_step": "Integrate as interaction-state immunophenotyping, not physical complex validation.",
            },
            {
                "hypothesis_or_module": "HLA-DR-low immunoparalysis specifically enriched in CD3/CD14 co-events",
                "status": "NOT_SUPPORTED_AS_WRITTEN",
                "evidence": "The strongest local flow evidence often shows higher HLA-DR among CD3/CD14 events in severe COVID/ARDS or with severity, not lower HLA-DR.",
                "decision": "Reframe as compartmental divergence: population transcriptomes show MHC-II/CD74 decline while residual CD3/CD14 events show antigen-presentation/myeloid-state remodeling.",
                "next_step": "Do not write co-events as an HLA-DR-low compartment unless new event-level analysis proves it.",
            },
            {
                "hypothesis_or_module": "Bulk transcriptomic inflammatory / MHC-II-CD74 decoupling",
                "status": "SUPPORTED",
                "evidence": "Current sepsis project shows six-gene vs MHC-II/CD74 inverse coupling in 7/7 cohorts and a 221/499 inflammatory / MHC-II-low state.",
                "decision": "Keep as the population transcriptomic layer.",
                "next_step": "Use flow evidence as a cell-interaction-state context layer.",
            },
            {
                "hypothesis_or_module": "Module 3 multiscale immunoparalysis subtyping",
                "status": "GATED_FOR_TRUE_PATIENT_LEVEL_SUBTYPING",
                "evidence": "The current local bridge is evidence-level rather than same-patient paired feature-level.",
                "decision": "Do not claim validated multiscale subtype. A computational state model can be proposed.",
                "next_step": "Requires paired patient-level flow and gene-expression features or a clearly harmonized external dataset.",
            },
            {
                "hypothesis_or_module": "Module 4 MR and causal mediation",
                "status": "GATED_NOT_STARTED",
                "evidence": "No MR instruments for co-event frequency, event-state markers, or transcriptomic decoupling index have been extracted.",
                "decision": "No causal inference claim.",
                "next_step": "Only start after a well-defined genetically proxied exposure exists.",
            },
            {
                "hypothesis_or_module": "Module 5 drug repositioning",
                "status": "OPTIONAL_FUTURE_EXTENSION",
                "evidence": "No severe-decoupling paired expression profile has been finalized for LINCS reversal.",
                "decision": "Do not include in current manuscript unless the profile and validation gates are clear.",
                "next_step": "Use transcriptomic decoupling candidate genes only as hypothesis-generation if added.",
            },
        ]
    )
    bridge.to_csv(OUT / "stage6_hypothesis_gate_decisions.csv", index=False)

    claim = pd.DataFrame(
        [
            {
                "claim": "Public bulk sepsis transcriptomes show inflammatory / MHC-II-CD74 decoupling",
                "status": "allowed",
                "basis": "Current Stage 1-3 sepsis outputs",
                "prohibited_extension": "Do not call it clinical validation or causal direction.",
            },
            {
                "claim": "Residual CD3/CD14 co-events show severe-infection state remodeling",
                "status": "allowed_with_boundaries",
                "basis": "FREE REACH co-event evidence matrix and strict-QC contrasts",
                "prohibited_extension": "Do not claim physical T cell-monocyte complexes or immune synapses.",
            },
            {
                "claim": "CD3/CD14 co-events are an HLA-DR-low immunoparalysis compartment",
                "status": "prohibited_currently",
                "basis": "Local flow evidence often points to HLA-DR-high remodeling in co-events",
                "prohibited_extension": "Do not force the proposed model against the data.",
            },
            {
                "claim": "Flow and transcriptome are paired in COMBAT for same-patient decoupling correlation",
                "status": "prohibited_currently",
                "basis": "Gene-level paired RNA matrix not located locally",
                "prohibited_extension": "Do not report Pearson correlations until scores are computed from matched samples.",
            },
            {
                "claim": "Multiscale immune paralysis subtype is clinically validated",
                "status": "prohibited",
                "basis": "No same-patient paired subtype validation and no restricted EHR outcomes",
                "prohibited_extension": "Use computational immune state only.",
            },
        ]
    )
    claim.to_csv(OUT / "stage6_claim_boundary_matrix.csv", index=False)

    n_flow = len(flow)
    n_retained = int(flow["retained_for_main_bridge"].sum()) if not flow.empty else 0
    status = f"""# Stage 6 Multiscale CD3/CD14 Co-Event Bridge STATUS

Generated: 2026-06-12

## STATUS

PASS_WITH_REFRAMED_CORE_CLAIM

## Executive Decision

The integrated scheme is feasible, but the central claim should be reframed.

The current data support a multiscale bridge between:

1. population-level public sepsis transcriptomic inflammatory / MHC-II-CD74 decoupling, and
2. residual CD3/CD14 co-event state remodeling in public CyTOF/flow datasets.

The current data do **not** support writing the CD3/CD14 co-event compartment as an HLA-DR-low immunoparalysis compartment. In several high-value flow datasets, HLA-DR or myeloid activation markers are higher inside residual CD3/CD14 events in severe disease or ARDS comparisons.

## What Was Audited

- Current public sepsis transcriptomic decoupling outputs.
- FREE REACH COMBAT whole-blood and WB-D CyTOF co-event outputs.
- FREE REACH Priest Tube2 CyTOF co-event outputs.
- FREE REACH Roussel ARDS/COVID myeloid CyTOF strict-QC outputs.
- Cross-cohort co-event evidence matrix and scorecard.
- Local availability of COMBAT bulk RNA resources for same-patient scoring.

## Key Result

Flow/CyTOF bridge rows extracted: {n_flow}

Rows retained at adjusted q <= 0.10 for main bridge context: {n_retained}

The most reviewer-safe flow conclusion is **CD3/CD14 co-event state remodeling**, not simple co-event abundance increase and not HLA-DR-low co-event immunoparalysis.

## Current Paired-Omics Gate

COMBAT CyTOF event metrics are local, and COMBAT bulk RNA PCs are local. A gene-level paired COMBAT bulk RNA matrix with sample IDs was not located in the audited local paths. Therefore same-patient flow-transcriptome Pearson correlation is gated and not claimed.

## Claim Allowed

- Public sepsis bulk transcriptomes show inflammatory / MHC-II-CD74 decoupling.
- CD3/CD14 co-event compartments in public flow/CyTOF datasets show severe-infection state remodeling.
- Roussel ARDS strict-QC data support higher HLA-DR, CD33, CD11b/CD64, S100A9, and phenotype-marker burden inside CD3/CD14 events in ARDS-positive samples.
- COMBAT supports severity-linked CD3/CD14 event-state remodeling with harmonic expected-frequency sensitivity.
- Priest Tube2 supports residualized severe-COVID co-event abundance and activation-state context.
- These layers can be integrated as interaction-state immunophenotyping plus population transcriptomic decoupling.

## Claim Prohibited

- No physical T cell-monocyte complex proof.
- No immune synapse or antigen-specific interaction claim.
- No same-patient flow-RNA decoupling correlation until gene-level paired RNA scores are computed.
- No HLA-DR-low CD3/CD14 co-event compartment claim with current evidence.
- No clinically validated multiscale subtype.
- No MR causal chain.
- No drug-repositioning therapeutic recommendation.

## Retained Or Discard Decision

retained_or_discard_decision: `GO_STAGE6_REFRAMED_INTERACTION_STATE_BRIDGE`

## Output Files

- `03_results/stage6_multiscale_coevent_bridge/stage6_data_availability_audit.csv`
- `03_results/stage6_multiscale_coevent_bridge/stage6_flow_coevent_state_evidence.csv`
- `03_results/stage6_multiscale_coevent_bridge/stage6_hypothesis_gate_decisions.csv`
- `03_results/stage6_multiscale_coevent_bridge/stage6_claim_boundary_matrix.csv`
- `03_results/stage6_multiscale_coevent_bridge/stage6_readonly_coevent_evidence_matrix_subset.csv`
- `03_results/stage6_multiscale_coevent_bridge/stage6_readonly_coevent_scorecard_top.csv`
- `05_manuscript/integrated_multiscale_immunoparalysis_scheme_v1.md`
"""
    (OUT / "stage6_multiscale_coevent_bridge_STATUS.md").write_text(status)

    plan = """# Integrated Multiscale Sepsis Immunoparalysis Scheme v1

Generated: 2026-06-12

## Working Title

Compartmental divergence between CD3/CD14 co-event remodeling and MHC-II/CD74 transcriptomic decoupling in sepsis and severe infection

## Revised Scientific Question

Do public sepsis and severe-infection datasets support a multiscale immune-dysfunction architecture in which population-level transcriptomes show inflammatory / MHC-II-CD74 decoupling, while residual CD3/CD14 co-event compartments show a distinct antigen-presentation and myeloid activation state?

This is stronger and safer than claiming that the CD3/CD14 compartment is simply HLA-DR-low. The current flow evidence does not support that wording.

## Revised Core Logic

1. Public sepsis bulk transcriptomes define the population layer: inflammatory and immunometabolic programs rise while MHC-II/CD74 and HLA-DR programs fall.
2. Public flow/CyTOF datasets define the interaction-state layer: residual CD3/CD14 events are remodeled in severe infection and ARDS, often with higher HLA-DR and myeloid activation markers.
3. The combined model is compartmental divergence, not a linear causal chain.
4. The manuscript should argue that immune paralysis cannot be reduced to a single HLA-DR measurement. Different measurement compartments can carry opposite MHC-II signals.

## Module Status

| Module | Status | Decision |
|---|---|---|
| Cross-platform paired COMBAT flow/RNA validation | Gated | Requires gene-level paired COMBAT RNA matrix. |
| CD3/CD14 co-event state analysis | Supported | Use as the main added innovation layer. |
| Co-event frequency enrichment | Partial | Keep as context only because COMBAT harmonic enrichment weakens frequency claims. |
| Multiscale immune-state subtyping | Gated | Requires matched patient-level multiscale features. |
| MR/causal mediation | Gated | No instruments or harmonized exposure definition yet. |
| Drug repositioning | Future optional | Do not add until the expression profile is finalized. |

## Recommended Manuscript Upgrade

The next manuscript should not claim "cell-cell contact -> intracellular reprogramming -> clinical outcome" as a proven chain. It should claim a public-data, cross-scale reconstruction of immune-dysfunction compartmental divergence.

Suggested main conclusion:

Public sepsis transcriptomes and public flow/CyTOF co-event analyses converge on a non-uniform immune paralysis model: population-level blood transcriptomes show inflammatory / MHC-II-CD74 decoupling, while residual CD3/CD14 co-events carry a remodeled antigen-presentation and myeloid activation state. This supports a hypothesis-generating framework in which sepsis immune dysfunction depends on measurement compartment and cellular interaction state.

## Next Executable Step

Locate or retrieve a gene-level COMBAT bulk RNA expression matrix with sample IDs. If available, compute per-sample six-gene, myeloid, MHC-II/CD74, and HLA-DR scores and join them to the COMBAT CyTOF sample metrics through COMBAT participant/timepoint IDs. Only then run the proposed same-patient correlation and multiscale clustering.
"""
    (MANUSCRIPT / "integrated_multiscale_immunoparalysis_scheme_v1.md").write_text(plan)

    print(f"wrote={OUT}")
    print(f"flow_rows={n_flow}")
    print(f"retained_q_le_0.10={n_retained}")


if __name__ == "__main__":
    main()

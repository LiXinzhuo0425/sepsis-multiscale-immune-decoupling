# Stage 7 Review Hardening STATUS

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
- COMBAT Sepsis-only participants: 34.
- Repeated Sepsis participants: 6.
- Primary paired robustness rows: 3.
- Leave-one-cohort rows: 48.
- Random signature null rows: 14.
- Cluster stability summary rows: 2.
- Composition sensitivity rows: 42.
- Prohibited-language hits requiring review: 0.

## Claim Boundary

All Stage 7 outputs remain public-data, computational, and association-based. They do not establish causality, physical CD3/CD14 complexes, clinical utility, validated biomarkers, prognostic models, drug repositioning, or treatment recommendations.

## Retained Or Discard Decision

retained_or_discard_decision: RETAIN_AS_REVIEW_HARDENING_LAYER_FOR_MULTISCALE_MANUSCRIPT

## Output Index

- `03_results/stage7_review_hardening/stage7_combat_pairing_flow_source_data.csv`
- `03_results/stage7_review_hardening/stage7_combat_group_counts.csv`
- `03_results/stage7_review_hardening/stage7_combat_participant_timepoint_counts.csv`
- `03_results/stage7_review_hardening/stage7_combat_participant_independence_audit.csv`
- `03_results/stage7_review_hardening/stage7_combat_sepsis_paired_robustness.csv`
- `03_results/stage7_review_hardening/stage7_combat_pairing_permutation_null.csv`
- `03_results/stage7_review_hardening/stage7_bulk_leave_one_cohort_sensitivity.csv`
- `03_results/stage7_review_hardening/stage7_bulk_random_signature_null_summary.csv`
- `03_results/stage7_review_hardening/stage7_bulk_negative_control_signature_correlations.csv`
- `03_results/stage7_review_hardening/stage7_bulk_monocyte_adjusted_sensitivity.csv`
- `03_results/stage7_review_hardening/stage7_immune_state_monocyte_adjusted_contrasts.csv`
- `03_results/stage7_review_hardening/stage7_case_only_kmeans_k2_to_k5_quality.csv`
- `03_results/stage7_review_hardening/stage7_case_only_clustering_seed_bootstrap_ari.csv`
- `03_results/stage7_review_hardening/stage7_case_only_clustering_stability_summary.csv`
- `03_results/stage7_review_hardening/stage7_cytometry_artifact_control_summary.csv`
- `03_results/stage7_review_hardening/stage7_coevent_frequency_vs_state_summary.csv`
- `03_results/stage7_review_hardening/stage7_coevent_negative_control_feasibility.csv`
- `03_results/stage7_review_hardening/stage7_readonly_cytometry_reuse_manifest.csv`
- `03_results/stage7_review_hardening/stage7_dataset_audit_master_table.csv`
- `03_results/stage7_review_hardening/stage7_claim_boundary_matrix.csv`
- `03_results/stage7_review_hardening/stage7_clinical_anchor_map.csv`
- `03_results/stage7_review_hardening/stage7_figure_rebuild_plan.csv`
- `03_results/stage7_review_hardening/stage7_supplementary_table_index.csv`
- `03_results/stage7_review_hardening/stage7_prohibited_language_scan.csv`
- `03_results/stage7_review_hardening/stage7_terminology_ledger.csv`
- `03_results/stage7_review_hardening/stage7_reference_expansion_pubmed.csv`
- `03_results/stage7_review_hardening/stage7_reference_expansion_status.csv`
- `05_manuscript/review_hardening_manuscript_insertions_v1.md`

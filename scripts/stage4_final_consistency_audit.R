suppressPackageStartupMessages({
  library(data.table)
})

project_root <- "<PROJECT_ROOT>"
out_dir <- file.path(project_root, "03_results", "stage4_final_audit")
log_dir <- file.path(project_root, "06_logs")
dir.create(out_dir, recursive = TRUE, showWarnings = FALSE)
dir.create(log_dir, recursive = TRUE, showWarnings = FALSE)

log_file <- file.path(log_dir, paste0("stage4_final_consistency_audit_", format(Sys.time(), "%Y%m%d_%H%M%S"), ".log"))
sink(log_file, split = TRUE)
cat("stage4_final_consistency_audit_start=", format(Sys.time(), "%Y-%m-%dT%H:%M:%S%z"), "\n", sep = "")

read_text <- function(rel_path) {
  path <- file.path(project_root, rel_path)
  if (!file.exists(path)) return("")
  paste(readLines(path, warn = FALSE), collapse = "\n")
}

exists_rel <- function(rel_path) file.exists(file.path(project_root, rel_path))
contains <- function(text, pattern) grepl(pattern, text, fixed = TRUE)

bulk_cc <- fread(file.path(project_root, "03_results/stage1_bulk_mhcii_screen/stage1_bulk_signature_case_control_summary.csv"))
bulk_cor <- fread(file.path(project_root, "03_results/stage1_bulk_mhcii_screen/stage1_bulk_signature_correlation_summary.csv"))
stage2_counts <- fread(file.path(project_root, "03_results/stage2_signature_state_heterogeneity/stage2_immune_state_counts.csv"))
stage2_presence <- fread(file.path(project_root, "03_results/stage2_signature_state_heterogeneity/stage2_immune_state_cross_dataset_presence.csv"))
stage3_candidates <- fread(file.path(project_root, "03_results/stage3_gene_level_decoupling_prioritization/stage3_gene_decoupling_candidate_summary.csv"))
mr_gate <- fread(file.path(project_root, "03_results/stage1_mr_gate_audit/stage1_mr_gate_resource_audit.csv"))
manifest <- fread(file.path(project_root, "01_data_manifest/project_output_manifest_latest.csv"))

report_text <- read_text("03_results/stage1_final/STAGE1_FINAL_REPORT.md")
draft_text <- read_text("05_manuscript/manuscript_draft_v0.md")
legend_text <- read_text("05_manuscript/figure_legends_v0.md")
readiness_text <- read_text("03_results/stage1_final/stage4_submission_readiness_checklist.md")

six <- bulk_cc[signature == "six_gene_panel"][1]
mhcii <- bulk_cc[signature == "mhcii_cd74_axis"][1]
six_mhcii <- bulk_cor[pair == "six_vs_mhcii"][1]
myeloid_mhcii <- bulk_cor[pair == "myeloid_vs_mhcii"][1]
immunomet_myeloid <- bulk_cor[pair == "immunometabolic_vs_myeloid"][1]
dec <- stage2_counts[immune_state == "Decoupled inflammatory / MHC-II-low"][1]
dec_presence <- stage2_presence[immune_state == "Decoupled inflammatory / MHC-II-low", n_datasets_present]
top_pos <- stage3_candidates[priority_direction == "positive_decoupling_candidate" & seed_signature_gene == FALSE][order(-median_rho, min_p)][1:6, gene]
top_neg <- stage3_candidates[priority_direction == "negative_antigen_presentation_candidate" & seed_signature_gene == FALSE][order(median_rho, min_p)][1:6, gene]

required_files <- c(
  "README.md",
  "00_admin/implementation_status.md",
  "03_results/stage1_final/STAGE1_FINAL_REPORT.md",
  "03_results/stage1_final/stage1_QC_checklist.md",
  "03_results/stage1_final/stage4_reviewer_risk_response_map.csv",
  "03_results/stage1_final/stage4_submission_readiness_checklist.md",
  "03_results/stage1_bulk_mhcii_screen/stage1_bulk_signature_case_control_summary.csv",
  "03_results/stage1_bulk_mhcii_screen/stage1_bulk_signature_correlation_summary.csv",
  "03_results/stage1_multilayer_mechanism_context/stage1_multilayer_mechanism_evidence_matrix.csv",
  "03_results/stage1_mr_gate_audit/stage1_mr_gate_resource_audit.csv",
  "03_results/stage2_signature_state_heterogeneity/stage2_case_immune_state_assignments.csv",
  "03_results/stage3_gene_level_decoupling_prioritization/stage3_gene_decoupling_candidate_summary.csv",
  "04_figures/stage1_decoupling_axis/stage1_decoupling_axis_mechanism_figure.pdf",
  "04_figures/stage1_decoupling_axis/stage1_decoupling_axis_mechanism_figure.svg",
  "04_figures/stage2_signature_state_heterogeneity/stage2_signature_state_heterogeneity.pdf",
  "04_figures/stage2_signature_state_heterogeneity/stage2_signature_state_heterogeneity.svg",
  "04_figures/stage3_gene_level_decoupling_prioritization/stage3_gene_level_decoupling_candidates.pdf",
  "04_figures/stage3_gene_level_decoupling_prioritization/stage3_gene_level_decoupling_candidates.svg",
  "05_manuscript/manuscript_draft_v0.md",
  "05_manuscript/manuscript_scaffold_v0.md",
  "05_manuscript/figure_legends_v0.md",
  "05_manuscript/data_availability_and_reproducibility_v0.md",
  "05_manuscript/reference_seed_list_v0.csv",
  "05_manuscript/reference_seed_list_v0.md",
  "01_data_manifest/project_output_manifest_latest.csv"
)

checks <- rbindlist(list(
  data.table(
    requirement = "Core files exist",
    evidence = paste(required_files, collapse = "; "),
    status = ifelse(all(vapply(required_files, exists_rel, logical(1))), "PASS", "FAIL"),
    detail = paste(required_files[!vapply(required_files, exists_rel, logical(1))], collapse = "; ")
  ),
  data.table(
    requirement = "Manifest contains required files",
    evidence = "01_data_manifest/project_output_manifest_latest.csv",
    status = ifelse(all(required_files %in% manifest$rel_path), "PASS", "FAIL"),
    detail = paste(setdiff(required_files, manifest$rel_path), collapse = "; ")
  ),
  data.table(
    requirement = "Bulk positive results are internally consistent",
    evidence = "stage1_bulk_signature_case_control_summary.csv and report/draft text",
    status = ifelse(
      six$n_fdr == 5 && mhcii$n_fdr == 4 &&
        contains(report_text, "FDR-significant in 5/7 datasets") &&
        contains(report_text, "MHC-II/CD74 axis: median case-control effect -0.56") &&
        contains(draft_text, "FDR-significant in 5/7 cohorts"),
      "PASS", "FAIL"
    ),
    detail = paste0("six n_fdr=", six$n_fdr, "; mhcii n_fdr=", mhcii$n_fdr)
  ),
  data.table(
    requirement = "Decoupling correlation results are internally consistent",
    evidence = "stage1_bulk_signature_correlation_summary.csv and report/draft text",
    status = ifelse(
      six_mhcii$n_fdr == 7 && myeloid_mhcii$n_fdr == 6 && immunomet_myeloid$n_fdr == 7 &&
        contains(report_text, "median Spearman rho -0.60") &&
        contains(draft_text, "median rho 0.79"),
      "PASS", "FAIL"
    ),
    detail = paste0("six_vs_mhcii=", six_mhcii$n_fdr, "; myeloid_vs_mhcii=", myeloid_mhcii$n_fdr, "; immunomet_vs_myeloid=", immunomet_myeloid$n_fdr)
  ),
  data.table(
    requirement = "Signature-derived immune-state result is represented consistently",
    evidence = "stage2 counts/presence and report/draft text",
    status = ifelse(
      dec$N == 221 && abs(dec$fraction - 0.4428858) < 1e-6 && dec_presence == 7 &&
        contains(report_text, "221 cases (44.3%)") &&
        contains(draft_text, "221 of 499 complete sepsis cases"),
      "PASS", "FAIL"
    ),
    detail = paste0("decoupled N=", dec$N, "; fraction=", round(dec$fraction, 4), "; datasets=", dec_presence)
  ),
  data.table(
    requirement = "Gene-level prioritization is present and bounded",
    evidence = "stage3 candidate table, report, draft, and figure legend",
    status = ifelse(
      nrow(stage3_candidates) >= 1000 &&
        all(c("ST6GALNAC3", "GYG1", "CKAP4") %in% top_pos) &&
        all(c("ST3GAL5", "APOL3") %in% top_neg) &&
        contains(legend_text, "not validated upstream regulators") &&
        contains(report_text, "No causal gene or validated upstream regulator claim"),
      "PASS", "FAIL"
    ),
    detail = paste0("candidate rows=", nrow(stage3_candidates), "; top_pos=", paste(top_pos, collapse = ","), "; top_neg=", paste(top_neg, collapse = ","))
  ),
  data.table(
    requirement = "MR is gated and not overclaimed",
    evidence = "stage1_mr_gate_resource_audit.csv and report/draft text",
    status = ifelse(
      all(mr_gate$head_status == 200) &&
        all(mr_gate$rest_association_count == 0) &&
        all(mr_gate$opengwas_jwt_available == "NO") &&
        contains(report_text, "No MR causal claim") &&
        contains(draft_text, "makes no MR causal claim"),
      "PASS", "FAIL"
    ),
    detail = paste(paste(mr_gate$accession, mr_gate$gate_decision, sep = "="), collapse = "; ")
  ),
  data.table(
    requirement = "Figure files are vector artifacts",
    evidence = "PDF/SVG files exist for Figures 1-3",
    status = ifelse(all(vapply(required_files[grepl("^04_figures", required_files)], exists_rel, logical(1))), "PASS", "FAIL"),
    detail = "PDF and SVG presence checked by path; file type checked separately with shell `file` during verification."
  ),
  data.table(
    requirement = "MIMIC/eICU excluded from analysis",
    evidence = "manuscript draft and data availability text",
    status = ifelse(
      contains(draft_text, "excluding MIMIC-IV and eICU") &&
        contains(read_text("05_manuscript/data_availability_and_reproducibility_v0.md"), "MIMIC-IV and eICU were excluded"),
      "PASS", "FAIL"
    ),
    detail = "Restricted clinical databases are excluded from current analyses."
  ),
  data.table(
    requirement = "Submission readiness stance is honest",
    evidence = "stage4_submission_readiness_checklist.md",
    status = ifelse(
      contains(readiness_text, "Computational mechanism manuscript: feasible") &&
        contains(readiness_text, "Clinical validation manuscript: not supported") &&
        contains(readiness_text, "MR causal manuscript: not supported yet"),
      "PASS", "FAIL"
    ),
    detail = "Readiness checklist preserves claim boundaries."
  )
), fill = TRUE)

fwrite(checks, file.path(out_dir, "stage4_final_consistency_audit.csv"))

all_pass <- all(checks$status == "PASS")
status_lines <- c(
  "# Stage 4 Final Consistency Audit STATUS",
  "",
  "## STATUS",
  "",
  if (all_pass) "PASS_WITH_COMPUTATIONAL_MECHANISM_PACKAGE_READY" else "FAIL_REQUIRES_PATCH",
  "",
  "## Decision",
  "",
  if (all_pass) "retained_or_discard_decision: FINAL_PACKAGE_READY_WITH_MR_AND_CLINICAL_VALIDATION_GATED" else "retained_or_discard_decision: FINAL_PACKAGE_NOT_READY",
  "",
  "## Summary",
  "",
  paste0("- Checks run: ", nrow(checks), "."),
  paste0("- Checks passed: ", sum(checks$status == "PASS"), "."),
  paste0("- Checks failed: ", sum(checks$status != "PASS"), "."),
  "",
  "## Claim Boundary",
  "",
  "- Ready: public-data computational mechanism manuscript package.",
  "- Not ready/claimed: clinical validation, MIMIC/eICU validation, MR causal manuscript, wet-lab mechanism.",
  "",
  "## Output Files",
  "",
  "- `stage4_final_consistency_audit.csv`"
)
writeLines(status_lines, file.path(out_dir, "stage4_final_consistency_audit_STATUS.md"))

cat("checks=", nrow(checks), "\n", sep = "")
cat("passed=", sum(checks$status == "PASS"), "\n", sep = "")
cat("failed=", sum(checks$status != "PASS"), "\n", sep = "")
cat("stage4_final_consistency_audit_end=", format(Sys.time(), "%Y-%m-%dT%H:%M:%S%z"), "\n", sep = "")
sink()

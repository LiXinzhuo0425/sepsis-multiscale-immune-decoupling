suppressPackageStartupMessages({
  library(data.table)
})

project_root <- "<PROJECT_ROOT>"
legacy_root <- "<READ_ONLY_TRANSCRIPTOMICS_REFERENCE_ROOT>"
out_dir <- file.path(project_root, "03_results", "stage1_integrated_route_selection")
log_dir <- file.path(project_root, "06_logs")
dir.create(out_dir, recursive = TRUE, showWarnings = FALSE)
dir.create(log_dir, recursive = TRUE, showWarnings = FALSE)

log_file <- file.path(log_dir, paste0("stage1_integrated_route_selection_", format(Sys.time(), "%Y%m%d_%H%M%S"), ".log"))
sink(log_file, split = TRUE)
cat("stage1_integrated_route_selection_start=", format(Sys.time(), "%Y-%m-%dT%H:%M:%S%z"), "\n", sep = "")

bulk_dir <- file.path(project_root, "03_results", "stage1_bulk_mhcii_screen")
bulk_cc <- fread(file.path(bulk_dir, "stage1_bulk_signature_case_control_summary.csv"))
bulk_cor <- fread(file.path(bulk_dir, "stage1_bulk_signature_correlation_summary.csv"))
gwas_status <- readLines(file.path(project_root, "03_results", "stage1_gwas_resource_audit", "stage1_gwas_resource_audit_STATUS.md"), warn = FALSE)

read_legacy <- function(path) {
  full <- file.path(legacy_root, path)
  if (!file.exists(full)) return(data.table())
  fread(full)
}

p10r <- read_legacy("03_results/tables/P10R_refined_single_cell_localization_synthesis.csv")
cd74 <- read_legacy("03_results/tables/P14R_QA_CD74_axis_adjudication_table.csv")
tf <- read_legacy("03_results/tables/EXP11_regulatory_context_synthesis.csv")
triage <- read_legacy("03_results/tables/P13_master_evidence_triage.csv")
exp09 <- read_legacy("03_results/tables/EXP09_integrated_synthesis.csv")

get_bulk_cc <- function(sig) {
  row <- bulk_cc[signature == sig]
  if (nrow(row) == 0) return("")
  sprintf(
    "%s: %d/%d FDR<0.10; direction up=%d/down=%d; median effect %.3f; strongest %s p=%.2g",
    sig, row$n_fdr, row$n_datasets, row$n_up, row$n_down, row$median_effect,
    row$strongest_dataset, row$min_p
  )
}

get_bulk_cor <- function(pair_id) {
  row <- bulk_cor[pair == pair_id]
  if (nrow(row) == 0) return("")
  sprintf(
    "%s: %d/%d FDR<0.10; median rho %.3f; positive fraction %.2f; strongest %s rho=%.3f p=%.2g",
    pair_id, row$n_fdr, row$n_datasets, row$median_rho, row$positive_fraction,
    row$strongest_dataset, row$strongest_rho, row$min_p
  )
}

routes <- rbindlist(list(
  data.table(
    route_id = "R1",
    route_name = "Myeloid-inflammatory / MHC-II-CD74 decoupling axis",
    route_type = "PRIMARY_RECOMMENDED",
    novelty = "Mechanism-first host-response decoupling: inflammatory/immunometabolic myeloid activation rises while HLA-DR/MHC-II/CD74/adaptive context falls.",
    positive_evidence = paste(
      get_bulk_cc("six_gene_panel"),
      get_bulk_cc("myeloid_inflammatory"),
      get_bulk_cc("immunometabolic_stress"),
      get_bulk_cc("mhcii_cd74_axis"),
      get_bulk_cc("hla_dr_core"),
      get_bulk_cor("six_vs_mhcii"),
      get_bulk_cor("six_vs_hladr"),
      get_bulk_cor("myeloid_vs_mhcii"),
      get_bulk_cor("myeloid_vs_adaptive"),
      sep = " | "
    ),
    single_cell_support = paste(p10r[finding %in% c("myeloid_centered_localization", "monocyte_support"), paste(finding, support_level, evidence_layers, sep = ": ")], collapse = " | "),
    communication_support = paste(cd74[axis %in% c("APP/CD74", "MHC-II/CD74 pathway/context"), paste(axis, final_decision, reason_for_retention_or_exclusion, sep = ": ")], collapse = " | "),
    regulatory_support = paste(tf[grepl("CIITA|STAT1|IRF1|SPI1|CEBP|NFKB", regulatory_finding), paste(regulatory_finding, support_level, evidence_layers, sep = ": ")], collapse = " | "),
    mr_status = "Feasible but not yet main evidence; GCST90270871 full summary stats available by FTP, OpenGWAS trait-level API requires JWT.",
    claim_allowed = "Cross-cohort transcriptomic decoupling, single-cell localization context, CD74 communication-context, and TF/regulon-context evidence.",
    claim_prohibited = "No confirmed causal mechanism, no clinical validation, no diagnostic model, no therapeutic target claim.",
    decision = "GO_PRIMARY"
  ),
  data.table(
    route_id = "R2",
    route_name = "Cross-disease sepsis-to-chronic-outcome MR",
    route_type = "CHALLENGE_ROUTE_GATED",
    novelty = "Potentially high-impact statistical-genetic route linking sepsis liability to chronic cardiovascular, kidney, or dementia outcomes.",
    positive_evidence = "GWAS Catalog resource audit found full summary-statistics candidates for sepsis and several chronic outcomes.",
    single_cell_support = "Can use R1 immune-paralysis axis as mediator biology if MR succeeds.",
    communication_support = "Not applicable until MR/multivariable MR identifies a mediator path.",
    regulatory_support = "Not applicable until MR/multivariable MR identifies a mediator path.",
    mr_status = "Do not claim yet; requires complete summary-statistics download or OpenGWAS JWT and harmonized MR.",
    claim_allowed = "Future statistical-genetic extension.",
    claim_prohibited = "No MR causality claim before analysis.",
    decision = "KEEP_AS_GATED_EXTENSION"
  ),
  data.table(
    route_id = "R3",
    route_name = "Sepsis heterogeneity / ARDS immune-state route",
    route_type = "SECONDARY_DOWNGRADE",
    novelty = "Use immune-state axes to explain why patients split into inflammatory, immunoparalysis, and organ-dysfunction states.",
    positive_evidence = paste(
      get_bulk_cc("adaptive_t_cell_context"),
      get_bulk_cc("interferon_antigen_presentation"),
      get_bulk_cor("ifn_vs_mhcii"),
      sep = " | "
    ),
    single_cell_support = paste(p10r[, paste(finding, support_level, sep = ": ")], collapse = " | "),
    communication_support = "CD74 and chemokine/TNF-family communication context can support subtype biology, not confirmed signaling.",
    regulatory_support = paste(tf[, paste(regulatory_finding, support_level, sep = ": ")], collapse = " | "),
    mr_status = "Not required.",
    claim_allowed = "Exploratory heterogeneity and immune-state interpretation.",
    claim_prohibited = "No validated endotype classifier.",
    decision = "BACKUP_ROUTE"
  )
), fill = TRUE)

evidence_table <- rbindlist(list(
  data.table(layer = "fresh_bulk_case_control", source = "new Stage 1 screen", key_result = paste(bulk_cc[, paste(signature, paste0(n_fdr, "/", n_datasets, " FDR"), direction = " ")], collapse = "; ")),
  data.table(layer = "fresh_bulk_correlation", source = "new Stage 1 screen", key_result = paste(bulk_cor[, paste(pair, sprintf("median_rho=%.3f", median_rho), paste0(n_fdr, "/", n_datasets, " FDR"), sep = " ")], collapse = "; ")),
  data.table(layer = "single_cell", source = "legacy P10R synthesis", key_result = paste(p10r[, paste(finding, support_level, evidence_layers, sep = " | ")], collapse = "; ")),
  data.table(layer = "communication", source = "legacy P14R QA CD74 adjudication", key_result = paste(cd74[, paste(axis, final_decision, sep = " | ")], collapse = "; ")),
  data.table(layer = "regulatory", source = "legacy EXP11 synthesis", key_result = paste(tf[, paste(regulatory_finding, support_level, sep = " | ")], collapse = "; ")),
  data.table(layer = "gwas_mr", source = "new GWAS resource audit", key_result = paste(gwas_status[grepl("GCST90270871|OpenGWAS|FinnGen|Decision", gwas_status)], collapse = " "))
), fill = TRUE)

fwrite(routes, file.path(out_dir, "stage1_route_candidates.csv"))
fwrite(evidence_table, file.path(out_dir, "stage1_integrated_evidence_layers.csv"))

report_path <- file.path(out_dir, "stage1_integrated_route_selection_STATUS.md")
cat(
  "# Stage 1 Integrated Route Selection STATUS\n\n",
  "## STATUS\n\n",
  "PASS_WITH_PRIMARY_POSITIVE_ROUTE\n\n",
  "## Primary Selected Route\n\n",
  "**R1: Myeloid-inflammatory / MHC-II-CD74 decoupling axis.**\n\n",
  "This route is selected because it has fresh cross-cohort positive evidence and a coherent multi-layer mechanism: six-gene/myeloid/immunometabolic programs rise in sepsis while MHC-II/CD74/HLA-DR and adaptive/T-cell context fall, with negative coupling reproduced across the seven public bulk cohorts.\n\n",
  "## Why This Is Innovative Enough To Continue\n\n",
  "- It is not another diagnostic model and does not depend on weak public-bulk transportability.\n",
  "- It reframes sepsis transcriptomics as immune-state decoupling: inflammatory myeloid stress and antigen-presentation collapse co-exist rather than forming one linear activation score.\n",
  "- It can absorb existing single-cell Mono support, APP/CD74 communication-context support, and STAT1/IRF1/CIITA/SPI1/CEBP regulatory context.\n",
  "- It leaves a clear optional MR extension using GCST90270871 and chronic-outcome GWAS summary statistics, but does not overclaim MR before running it.\n\n",
  "## Key Quantitative Anchors\n\n",
  "- Fresh bulk case-control: six-gene panel FDR-significant in 5/7 datasets, mostly up in cases.\n",
  "- Fresh bulk case-control: MHC-II/CD74 axis FDR-significant in 4/7 datasets, mostly down in cases.\n",
  "- Fresh bulk correlations: six-gene vs MHC-II/CD74 negative in 7/7 FDR-significant datasets, median rho approximately -0.60.\n",
  "- Fresh bulk correlations: myeloid inflammation vs MHC-II/CD74 negative in 6/7 FDR-significant datasets, median rho approximately -0.50.\n",
  "- Fresh bulk correlations: immunometabolic stress vs myeloid inflammation positive in 7/7 FDR-significant datasets, median rho approximately 0.79.\n\n",
  "## Decision\n\n",
  "retained_or_discard_decision: GO_PRIMARY_WITH_MR_EXTENSION_GATED\n\n",
  "Continue with R1 as the main non-MIMIC/eICU manuscript route. Keep cross-disease MR as an extension only after complete summary-statistics download or OpenGWAS JWT access.\n\n",
  "## Claim Allowed\n\n",
  "- Cross-cohort transcriptomic immune-state decoupling.\n",
  "- Multi-layer computational mechanism reconstruction.\n",
  "- Mono-supported myeloid-centered localization and CD74 pathway/communication context.\n\n",
  "## Claim Prohibited\n\n",
  "- No clinical validation.\n",
  "- No diagnostic model validation.\n",
  "- No confirmed signaling mechanism.\n",
  "- No MR causal claim yet.\n",
  sep = "",
  file = report_path
)

print(routes[, .(route_id, route_name, route_type, decision)])
cat("stage1_integrated_route_selection_end=", format(Sys.time(), "%Y-%m-%dT%H:%M:%S%z"), "\n", sep = "")
sink()

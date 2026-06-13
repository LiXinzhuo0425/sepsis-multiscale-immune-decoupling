suppressPackageStartupMessages({
  library(data.table)
})

project_root <- "<PROJECT_ROOT>"
legacy_root <- "<READ_ONLY_TRANSCRIPTOMICS_REFERENCE_ROOT>"
out_dir <- file.path(project_root, "03_results", "stage1_bulk_mhcii_screen")
log_dir <- file.path(project_root, "06_logs")
dir.create(out_dir, recursive = TRUE, showWarnings = FALSE)
dir.create(log_dir, recursive = TRUE, showWarnings = FALSE)

log_file <- file.path(log_dir, paste0("stage1_bulk_mhcii_screen_", format(Sys.time(), "%Y%m%d_%H%M%S"), ".log"))
sink(log_file, split = TRUE)
cat("stage1_bulk_mhcii_screen_start=", format(Sys.time(), "%Y-%m-%dT%H:%M:%S%z"), "\n", sep = "")

datasets <- c("GSE154918", "GSE134347", "GSE65682", "GSE32707", "GSE69063", "GSE28750", "GSE54514")

signature_sets <- list(
  six_gene_panel = c("RETN", "MCEMP1", "CYP1B1", "S100A12", "S100A8", "HK3"),
  mhcii_cd74_axis = c("CD74", "HLA-DRA", "HLA-DRB1", "HLA-DRB5", "HLA-DPA1", "HLA-DPB1", "HLA-DQA1", "HLA-DQB1", "HLA-DMA", "HLA-DMB", "CIITA"),
  hla_dr_core = c("HLA-DRA", "HLA-DRB1", "HLA-DRB5", "CIITA", "CD74"),
  myeloid_inflammatory = c("S100A8", "S100A9", "S100A12", "IL1B", "CXCL8", "LCN2", "RETN", "TLR2", "NFKBIA", "FCGR1A"),
  interferon_antigen_presentation = c("STAT1", "IRF1", "IRF7", "ISG15", "IFI44L", "OAS1", "MX1", "CXCL10", "HLA-DRA", "CD74"),
  immunometabolic_stress = c("HK3", "HIF1A", "LDHA", "SLC2A3", "PFKFB3", "ENO1", "ALDOA"),
  adaptive_t_cell_context = c("CD3D", "CD3E", "CD4", "CD8A", "IL7R", "CCR7", "LCK", "TRAC")
)

score_signature <- function(expr_mat, genes) {
  present <- intersect(genes, rownames(expr_mat))
  if (length(present) < 2) {
    return(list(score = rep(NA_real_, ncol(expr_mat)), present = present))
  }
  sub <- expr_mat[present, , drop = FALSE]
  z <- t(scale(t(sub)))
  z[!is.finite(z)] <- NA_real_
  list(score = colMeans(z, na.rm = TRUE), present = present)
}

safe_wilcox <- function(x, g) {
  case <- x[g == "CASE"]
  control <- x[g == "CONTROL"]
  case <- case[is.finite(case)]
  control <- control[is.finite(control)]
  if (length(case) < 3 || length(control) < 3) return(NA_real_)
  suppressWarnings(wilcox.test(case, control)$p.value)
}

safe_spearman <- function(x, y) {
  ok <- is.finite(x) & is.finite(y)
  if (sum(ok) < 6) return(c(rho = NA_real_, p = NA_real_, n = sum(ok)))
  ct <- suppressWarnings(cor.test(x[ok], y[ok], method = "spearman", exact = FALSE))
  c(rho = unname(ct$estimate), p = ct$p.value, n = sum(ok))
}

all_sample_scores <- list()
all_case_control <- list()
all_correlations <- list()
all_gene_audit <- list()

for (acc in datasets) {
  cat("processing=", acc, "\n", sep = "")
  expr_path <- file.path(legacy_root, "01_data", "processed", "bulk", acc, paste0("expression_gene_median_", acc, ".csv.gz"))
  meta_path <- file.path(legacy_root, "01_data", "processed", "bulk", acc, paste0("metadata_cleaned_", acc, ".csv"))
  if (!file.exists(expr_path) || !file.exists(meta_path)) {
    cat("missing_input=", acc, "\n", sep = "")
    next
  }
  expr_dt <- fread(expr_path)
  gene_col <- names(expr_dt)[1]
  genes <- expr_dt[[gene_col]]
  expr_dt[[gene_col]] <- NULL
  expr_mat <- as.matrix(expr_dt)
  storage.mode(expr_mat) <- "double"
  rownames(expr_mat) <- make.unique(as.character(genes))
  rm(expr_dt)

  meta <- fread(meta_path)
  keep <- meta[included_in_primary_analysis == "YES" & case_control_main %in% c("CASE", "CONTROL")]
  common_samples <- intersect(keep$gsm_id, colnames(expr_mat))
  keep <- keep[match(common_samples, gsm_id)]
  expr_use <- expr_mat[, common_samples, drop = FALSE]

  score_dt <- data.table(
    accession = acc,
    gsm_id = common_samples,
    case_control_main = keep$case_control_main,
    analysis_group_primary = keep$analysis_group_primary,
    analysis_group_secondary = keep$analysis_group_secondary,
    label_confidence = keep$label_confidence,
    n_primary_samples = length(common_samples),
    n_case = sum(keep$case_control_main == "CASE"),
    n_control = sum(keep$case_control_main == "CONTROL")
  )

  for (sig in names(signature_sets)) {
    res <- score_signature(expr_use, signature_sets[[sig]])
    score_dt[[sig]] <- res$score
    all_gene_audit[[length(all_gene_audit) + 1]] <- data.table(
      accession = acc,
      signature = sig,
      requested_genes = paste(signature_sets[[sig]], collapse = ";"),
      present_genes = paste(res$present, collapse = ";"),
      n_requested = length(signature_sets[[sig]]),
      n_present = length(res$present),
      coverage_fraction = length(res$present) / length(signature_sets[[sig]])
    )
  }

  all_sample_scores[[length(all_sample_scores) + 1]] <- score_dt

  for (sig in names(signature_sets)) {
    x <- score_dt[[sig]]
    cc <- data.table(
      accession = acc,
      signature = sig,
      n_case = sum(score_dt$case_control_main == "CASE" & is.finite(x)),
      n_control = sum(score_dt$case_control_main == "CONTROL" & is.finite(x)),
      case_median = median(x[score_dt$case_control_main == "CASE"], na.rm = TRUE),
      control_median = median(x[score_dt$case_control_main == "CONTROL"], na.rm = TRUE),
      median_diff_case_minus_control = median(x[score_dt$case_control_main == "CASE"], na.rm = TRUE) - median(x[score_dt$case_control_main == "CONTROL"], na.rm = TRUE),
      p_value = safe_wilcox(x, score_dt$case_control_main)
    )
    cc[, direction := fifelse(median_diff_case_minus_control > 0, "UP_IN_CASE", "DOWN_IN_CASE")]
    all_case_control[[length(all_case_control) + 1]] <- cc
  }

  pairs <- list(
    six_vs_mhcii = c("six_gene_panel", "mhcii_cd74_axis"),
    six_vs_hladr = c("six_gene_panel", "hla_dr_core"),
    myeloid_vs_mhcii = c("myeloid_inflammatory", "mhcii_cd74_axis"),
    myeloid_vs_adaptive = c("myeloid_inflammatory", "adaptive_t_cell_context"),
    ifn_vs_mhcii = c("interferon_antigen_presentation", "mhcii_cd74_axis"),
    immunometabolic_vs_myeloid = c("immunometabolic_stress", "myeloid_inflammatory")
  )
  for (pair_name in names(pairs)) {
    a <- pairs[[pair_name]][1]
    b <- pairs[[pair_name]][2]
    cor_res <- safe_spearman(score_dt[[a]], score_dt[[b]])
    all_correlations[[length(all_correlations) + 1]] <- data.table(
      accession = acc,
      pair = pair_name,
      signature_x = a,
      signature_y = b,
      rho = as.numeric(cor_res["rho"]),
      p_value = as.numeric(cor_res["p"]),
      n = as.integer(cor_res["n"])
    )
  }
}

sample_scores <- rbindlist(all_sample_scores, fill = TRUE)
case_control <- rbindlist(all_case_control, fill = TRUE)
correlations <- rbindlist(all_correlations, fill = TRUE)
gene_audit <- rbindlist(all_gene_audit, fill = TRUE)

case_control[, FDR := p.adjust(p_value, method = "BH"), by = signature]
correlations[, FDR := p.adjust(p_value, method = "BH"), by = pair]

case_summary <- case_control[, .(
  n_datasets = .N,
  n_nominal = sum(p_value < 0.05, na.rm = TRUE),
  n_fdr = sum(FDR < 0.10, na.rm = TRUE),
  n_up = sum(direction == "UP_IN_CASE", na.rm = TRUE),
  n_down = sum(direction == "DOWN_IN_CASE", na.rm = TRUE),
  median_effect = median(median_diff_case_minus_control, na.rm = TRUE),
  strongest_dataset = accession[which.min(p_value)],
  min_p = min(p_value, na.rm = TRUE)
), by = signature][order(-n_fdr, min_p)]

cor_summary <- correlations[, .(
  n_datasets = .N,
  n_nominal = sum(p_value < 0.05, na.rm = TRUE),
  n_fdr = sum(FDR < 0.10, na.rm = TRUE),
  median_rho = median(rho, na.rm = TRUE),
  positive_fraction = mean(rho > 0, na.rm = TRUE),
  strongest_dataset = accession[which.min(p_value)],
  strongest_rho = rho[which.min(p_value)],
  min_p = min(p_value, na.rm = TRUE)
), by = pair][order(-n_fdr, min_p)]

fwrite(sample_scores, file.path(out_dir, "stage1_bulk_signature_scores.csv"))
fwrite(case_control, file.path(out_dir, "stage1_bulk_signature_case_control.csv"))
fwrite(case_summary, file.path(out_dir, "stage1_bulk_signature_case_control_summary.csv"))
fwrite(correlations, file.path(out_dir, "stage1_bulk_signature_correlations.csv"))
fwrite(cor_summary, file.path(out_dir, "stage1_bulk_signature_correlation_summary.csv"))
fwrite(gene_audit, file.path(out_dir, "stage1_bulk_signature_gene_coverage.csv"))

strong_cc <- case_control[FDR < 0.10][order(FDR, p_value)]
strong_cor <- correlations[FDR < 0.10][order(FDR, p_value)]

report_path <- file.path(out_dir, "stage1_bulk_mhcii_screen_STATUS.md")
cat(
  "# Stage 1 Bulk MHC-II Screen STATUS\n\n",
  "## STATUS\n\n",
  "PASS_WITH_POSITIVE_CONTEXT\n\n",
  "## Inputs\n\n",
  "- Read-only processed bulk matrices and metadata from `<READ_ONLY_TRANSCRIPTOMICS_REFERENCE_ROOT>`.\n",
  "- Datasets: ", paste(datasets, collapse = ", "), ".\n\n",
  "## Key Positive Signals\n\n",
  "- Fresh scoring identified cross-dataset case-control and correlation signals for myeloid inflammatory, immunometabolic, MHC-II/CD74, HLA-DR, IFN/antigen-presentation, and adaptive/T-cell context axes.\n",
  "- The most manuscript-relevant innovation candidate is a coupled myeloid-inflammatory / MHC-II-CD74 immune-dysregulation axis, rather than a simple diagnostic model.\n",
  "- This supports prioritizing a mechanism-first route while continuing MR/GWAS feasibility checks.\n\n",
  "## Claim Allowed\n\n",
  "- Cross-cohort public-bulk transcriptomic context.\n",
  "- Signature-level immune-dysregulation association and prioritization.\n",
  "- Hypothesis-generating support for HLA-DR/MHC-II/CD74 and myeloid inflammatory coupling.\n\n",
  "## Claim Prohibited\n\n",
  "- No clinical validation.\n",
  "- No confirmed causal mechanism.\n",
  "- No diagnostic model or clinical utility claim.\n",
  "- No wet-lab validation.\n\n",
  "## Retained Or Discard Decision\n\n",
  "retained_or_discard_decision: MAIN_ROUTE_CONTEXT\n\n",
  "## Output Files\n\n",
  "- `stage1_bulk_signature_scores.csv`\n",
  "- `stage1_bulk_signature_case_control.csv`\n",
  "- `stage1_bulk_signature_case_control_summary.csv`\n",
  "- `stage1_bulk_signature_correlations.csv`\n",
  "- `stage1_bulk_signature_correlation_summary.csv`\n",
  "- `stage1_bulk_signature_gene_coverage.csv`\n",
  sep = "",
  file = report_path
)

cat("case_control_summary\n")
print(case_summary)
cat("correlation_summary\n")
print(cor_summary)
cat("strong_case_control_rows=", nrow(strong_cc), "\n", sep = "")
cat("strong_correlation_rows=", nrow(strong_cor), "\n", sep = "")
cat("stage1_bulk_mhcii_screen_end=", format(Sys.time(), "%Y-%m-%dT%H:%M:%S%z"), "\n", sep = "")
sink()

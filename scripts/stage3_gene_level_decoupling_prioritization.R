suppressPackageStartupMessages({
  library(data.table)
  library(ggplot2)
})

project_root <- "<PROJECT_ROOT>"
legacy_root <- "<READ_ONLY_TRANSCRIPTOMICS_REFERENCE_ROOT>"
score_file <- file.path(project_root, "03_results", "stage1_bulk_mhcii_screen", "stage1_bulk_signature_scores.csv")
out_dir <- file.path(project_root, "03_results", "stage3_gene_level_decoupling_prioritization")
fig_dir <- file.path(project_root, "04_figures", "stage3_gene_level_decoupling_prioritization")
log_dir <- file.path(project_root, "06_logs")
dir.create(out_dir, recursive = TRUE, showWarnings = FALSE)
dir.create(fig_dir, recursive = TRUE, showWarnings = FALSE)
dir.create(log_dir, recursive = TRUE, showWarnings = FALSE)

log_file <- file.path(log_dir, paste0("stage3_gene_level_decoupling_prioritization_", format(Sys.time(), "%Y%m%d_%H%M%S"), ".log"))
sink(log_file, split = TRUE)
cat("stage3_gene_level_decoupling_prioritization_start=", format(Sys.time(), "%Y-%m-%dT%H:%M:%S%z"), "\n", sep = "")

datasets <- c("GSE154918", "GSE134347", "GSE65682", "GSE32707", "GSE69063", "GSE28750", "GSE54514")
signature_cols <- c(
  "six_gene_panel",
  "myeloid_inflammatory",
  "immunometabolic_stress",
  "mhcii_cd74_axis",
  "hla_dr_core",
  "interferon_antigen_presentation",
  "adaptive_t_cell_context"
)
inflammatory_cols <- c("six_gene_panel", "myeloid_inflammatory", "immunometabolic_stress")
antigen_cols <- c("mhcii_cd74_axis", "hla_dr_core", "interferon_antigen_presentation", "adaptive_t_cell_context")

seed_signature_genes <- unique(c(
  "RETN", "MCEMP1", "CYP1B1", "S100A12", "S100A8", "HK3",
  "CD74", "HLA-DRA", "HLA-DRB1", "HLA-DRB5", "HLA-DPA1", "HLA-DPB1", "HLA-DQA1", "HLA-DQB1", "HLA-DMA", "HLA-DMB", "CIITA",
  "S100A9", "IL1B", "CXCL8", "LCN2", "TLR2", "NFKBIA", "FCGR1A",
  "STAT1", "IRF1", "IRF7", "ISG15", "IFI44L", "OAS1", "MX1", "CXCL10",
  "HIF1A", "LDHA", "SLC2A3", "PFKFB3", "ENO1", "ALDOA",
  "CD3D", "CD3E", "CD4", "CD8A", "IL7R", "CCR7", "LCK", "TRAC"
))

scores <- fread(score_file)
zscore_vec <- function(x) {
  s <- sd(x, na.rm = TRUE)
  if (!is.finite(s) || s == 0) return(rep(NA_real_, length(x)))
  (x - mean(x, na.rm = TRUE)) / s
}

safe_cor <- function(mat, index) {
  ok <- is.finite(index)
  index <- index[ok]
  mat <- mat[, ok, drop = FALSE]
  n <- length(index)
  if (n < 8) {
    return(data.table(gene = rownames(mat), rho = NA_real_, p_value = NA_real_, n = n))
  }
  ranked_index <- rank(index, ties.method = "average")
  ranked_mat <- t(apply(mat, 1, rank, ties.method = "average"))
  ranked_index <- as.numeric(scale(ranked_index))
  ranked_mat <- t(scale(t(ranked_mat)))
  ranked_mat[!is.finite(ranked_mat)] <- NA_real_
  rho <- as.numeric((ranked_mat %*% ranked_index) / (n - 1))
  rho[!is.finite(rho)] <- NA_real_
  rho_clamped <- pmax(pmin(rho, 0.999999), -0.999999)
  t_stat <- rho_clamped * sqrt((n - 2) / pmax(1e-12, 1 - rho_clamped^2))
  p_value <- 2 * pt(-abs(t_stat), df = n - 2)
  data.table(gene = rownames(mat), rho = rho, p_value = p_value, n = n)
}

dataset_results <- list()
input_manifest <- list()

for (acc in datasets) {
  cat("processing=", acc, "\n", sep = "")
  expr_path <- file.path(legacy_root, "01_data", "processed", "bulk", acc, paste0("expression_gene_median_", acc, ".csv.gz"))
  meta_path <- file.path(legacy_root, "01_data", "processed", "bulk", acc, paste0("metadata_cleaned_", acc, ".csv"))
  if (!file.exists(expr_path) || !file.exists(meta_path)) {
    cat("missing_input=", acc, "\n", sep = "")
    next
  }
  input_manifest[[length(input_manifest) + 1]] <- data.table(
    accession = acc,
    expr_path = expr_path,
    meta_path = meta_path,
    expr_size_bytes = file.info(expr_path)$size,
    meta_size_bytes = file.info(meta_path)$size
  )

  expr_dt <- fread(expr_path)
  gene_col <- names(expr_dt)[1]
  gene_ids <- as.character(expr_dt[[gene_col]])
  expr_dt[[gene_col]] <- NULL
  expr_mat <- as.matrix(expr_dt)
  storage.mode(expr_mat) <- "double"
  rownames(expr_mat) <- make.unique(gene_ids)
  rm(expr_dt)

  sample_scores <- scores[accession == acc & case_control_main == "CASE"]
  case_samples <- intersect(sample_scores$gsm_id, colnames(expr_mat))
  sample_scores <- sample_scores[match(case_samples, gsm_id)]
  expr_case <- expr_mat[, case_samples, drop = FALSE]
  rm(expr_mat)

  for (col in signature_cols) {
    sample_scores[, paste0(col, "_z") := zscore_vec(get(col))]
  }
  sample_scores[, inflammatory_index := rowMeans(.SD, na.rm = TRUE), .SDcols = paste0(inflammatory_cols, "_z")]
  sample_scores[, antigen_presentation_index := rowMeans(.SD, na.rm = TRUE), .SDcols = paste0(antigen_cols, "_z")]
  sample_scores[, decoupling_index := inflammatory_index - antigen_presentation_index]

  keep_samples <- is.finite(sample_scores$decoupling_index)
  expr_case <- expr_case[, keep_samples, drop = FALSE]
  index <- sample_scores$decoupling_index[keep_samples]

  gene_sd <- apply(expr_case, 1, sd, na.rm = TRUE)
  keep_genes <- is.finite(gene_sd) & gene_sd > 0
  expr_case <- expr_case[keep_genes, , drop = FALSE]

  res <- safe_cor(expr_case, index)
  res[, accession := acc]
  res[, fdr := p.adjust(p_value, method = "BH")]
  res[, direction := fifelse(rho > 0, "positive_with_decoupling", "negative_with_decoupling")]
  res[, abs_rho := abs(rho)]
  setcolorder(res, c("accession", "gene", "rho", "p_value", "fdr", "n", "direction", "abs_rho"))
  dataset_results[[length(dataset_results) + 1]] <- res
}

gene_dataset <- rbindlist(dataset_results, fill = TRUE)
gene_dataset[, seed_signature_gene := gene %in% seed_signature_genes]
fwrite(gene_dataset, file.path(out_dir, "stage3_gene_decoupling_correlations_by_dataset.csv"))
fwrite(rbindlist(input_manifest, fill = TRUE), file.path(out_dir, "stage3_gene_decoupling_input_manifest.csv"))

gene_summary <- gene_dataset[is.finite(rho), .(
  n_datasets = uniqueN(accession),
  n_positive = sum(rho > 0, na.rm = TRUE),
  n_negative = sum(rho < 0, na.rm = TRUE),
  n_nominal_positive = sum(rho > 0 & p_value < 0.05, na.rm = TRUE),
  n_nominal_negative = sum(rho < 0 & p_value < 0.05, na.rm = TRUE),
  n_fdr_positive = sum(rho > 0 & fdr < 0.10, na.rm = TRUE),
  n_fdr_negative = sum(rho < 0 & fdr < 0.10, na.rm = TRUE),
  median_rho = median(rho, na.rm = TRUE),
  mean_rho = mean(rho, na.rm = TRUE),
  min_p = min(p_value, na.rm = TRUE),
  max_abs_rho = max(abs_rho, na.rm = TRUE),
  seed_signature_gene = any(seed_signature_gene)
), by = gene]

gene_summary[, positive_fraction := n_positive / n_datasets]
gene_summary[, negative_fraction := n_negative / n_datasets]
gene_summary[, fisher_z := atanh(pmax(pmin(median_rho, 0.999999), -0.999999))]
gene_summary[, priority_direction := fifelse(
  n_datasets >= 4 & positive_fraction >= 0.70 & median_rho >= 0.25,
  "positive_decoupling_candidate",
  fifelse(n_datasets >= 4 & negative_fraction >= 0.70 & median_rho <= -0.25,
          "negative_antigen_presentation_candidate",
          "not_prioritized")
)]
gene_summary[, priority_tier := fifelse(
  priority_direction != "not_prioritized" & n_datasets >= 6 & (n_nominal_positive >= 3 | n_nominal_negative >= 3) & abs(median_rho) >= 0.35,
  "Tier1_cross_dataset",
  fifelse(priority_direction != "not_prioritized" & n_datasets >= 5 & (n_nominal_positive >= 2 | n_nominal_negative >= 2),
          "Tier2_supportive",
          fifelse(priority_direction != "not_prioritized", "Tier3_context", "not_prioritized"))
)]
gene_summary[, abs_median_rho := abs(median_rho)]
setorder(gene_summary, priority_tier, -abs_median_rho, min_p)
fwrite(gene_summary, file.path(out_dir, "stage3_gene_decoupling_priority_summary.csv"))

candidate_summary <- gene_summary[priority_tier != "not_prioritized"]
setorder(candidate_summary, -abs_median_rho, min_p)
fwrite(candidate_summary, file.path(out_dir, "stage3_gene_decoupling_candidate_summary.csv"))

top_pos <- gene_summary[priority_direction == "positive_decoupling_candidate"][order(-median_rho, min_p)][1:20]
top_neg <- gene_summary[priority_direction == "negative_antigen_presentation_candidate"][order(median_rho, min_p)][1:20]
plot_dt <- rbindlist(list(top_pos, top_neg), fill = TRUE)
plot_dt <- plot_dt[!is.na(gene)]
plot_dt[, plot_label := paste0(gene, ifelse(seed_signature_gene, " *", ""))]
plot_dt[, plot_label := factor(plot_label, levels = rev(plot_label[order(priority_direction, median_rho)]))]

if (nrow(plot_dt) > 0) {
  p <- ggplot(plot_dt, aes(x = plot_label, y = median_rho, fill = priority_direction)) +
    geom_col(width = 0.72, color = "grey20", linewidth = 0.18) +
    geom_hline(yintercept = 0, color = "grey35", linewidth = 0.35) +
    geom_text(aes(label = paste0(n_positive, "/", n_datasets, " +")), hjust = ifelse(plot_dt$median_rho >= 0, -0.05, 1.05), size = 2.8) +
    coord_flip(clip = "off") +
    scale_fill_manual(values = c(
      positive_decoupling_candidate = "#b4473a",
      negative_antigen_presentation_candidate = "#2f6f95"
    )) +
    labs(
      title = "Gene-level correlates of the sepsis immune-state decoupling index",
      subtitle = "Asterisk marks genes already present in seed signatures; candidates are prioritization results, not causal targets",
      x = NULL,
      y = "Median within-cohort Spearman rho with decoupling index",
      fill = NULL
    ) +
    theme_minimal(base_size = 10) +
    theme(
      panel.grid.minor = element_blank(),
      legend.position = "bottom",
      plot.title = element_text(face = "bold"),
      plot.margin = margin(8, 28, 8, 8)
    )
  pdf_path <- file.path(fig_dir, "stage3_gene_level_decoupling_candidates.pdf")
  svg_path <- file.path(fig_dir, "stage3_gene_level_decoupling_candidates.svg")
  ggsave(pdf_path, p, width = 10.5, height = 8.0, device = cairo_pdf)
  ggsave(svg_path, p, width = 10.5, height = 8.0)
} else {
  pdf_path <- NA_character_
  svg_path <- NA_character_
}

top_nonseed_pos <- candidate_summary[priority_direction == "positive_decoupling_candidate" & seed_signature_gene == FALSE][order(-median_rho, min_p)][1:15]
top_nonseed_neg <- candidate_summary[priority_direction == "negative_antigen_presentation_candidate" & seed_signature_gene == FALSE][order(median_rho, min_p)][1:15]

decision <- if (nrow(candidate_summary) >= 20 && nrow(top_nonseed_pos) >= 5 && nrow(top_nonseed_neg) >= 5) {
  "RETAIN_AS_STAGE3_UPSTREAM_PRIORITIZATION"
} else if (nrow(candidate_summary) >= 10) {
  "RETAIN_AS_SUPPLEMENTARY_GENE_CONTEXT"
} else {
  "DISCARD_AS_UNSTABLE_GENE_LEVEL_RESULT"
}

status <- c(
  "# Stage 3 Gene-Level Decoupling Prioritization STATUS",
  "",
  "## STATUS",
  "",
  if (grepl("DISCARD", decision)) "PASS_WITH_WEAK_GENE_LEVEL_CONTEXT" else "PASS_WITH_POSITIVE_GENE_LEVEL_CONTEXT",
  "",
  "## Method",
  "",
  "Within each public bulk cohort, case samples were assigned a dataset-centered immune-state decoupling index: inflammatory/myeloid/immunometabolic score minus MHC-II/CD74/HLA-DR/interferon/adaptive score. Gene expression was correlated with this index using within-cohort Spearman correlations, then summarized across cohorts.",
  "",
  "## Key Result",
  "",
  paste0("- Tested genes with finite variance across ", length(unique(gene_dataset$accession)), " datasets."),
  paste0("- Prioritized candidate rows: ", nrow(candidate_summary), "."),
  paste0("- Top non-seed positive candidates: ", ifelse(nrow(top_nonseed_pos) > 0, paste(head(top_nonseed_pos$gene, 10), collapse = ", "), "none"), "."),
  paste0("- Top non-seed negative candidates: ", ifelse(nrow(top_nonseed_neg) > 0, paste(head(top_nonseed_neg$gene, 10), collapse = ", "), "none"), "."),
  "",
  "## Decision",
  "",
  paste0("retained_or_discard_decision: ", decision),
  "",
  "## Claim Allowed",
  "",
  "- Cross-cohort gene-level prioritization linked to the transcriptomic decoupling index.",
  "- Candidate upstream/context genes for follow-up computational or experimental work.",
  "",
  "## Claim Prohibited",
  "",
  "- No causal gene claim.",
  "- No validated upstream regulator claim.",
  "- No therapeutic target claim.",
  "- No MR/eQTL claim unless separate genetic analyses are completed.",
  "",
  "## Output Files",
  "",
  "- `stage3_gene_decoupling_correlations_by_dataset.csv`",
  "- `stage3_gene_decoupling_priority_summary.csv`",
  "- `stage3_gene_decoupling_candidate_summary.csv`",
  "- `stage3_gene_decoupling_input_manifest.csv`",
  "- `04_figures/stage3_gene_level_decoupling_prioritization/stage3_gene_level_decoupling_candidates.pdf`",
  "- `04_figures/stage3_gene_level_decoupling_prioritization/stage3_gene_level_decoupling_candidates.svg`"
)
writeLines(status, file.path(out_dir, "stage3_gene_level_decoupling_prioritization_STATUS.md"))

cat("candidate_rows=", nrow(candidate_summary), "\n", sep = "")
cat("top_nonseed_positive=", paste(head(top_nonseed_pos$gene, 10), collapse = ","), "\n", sep = "")
cat("top_nonseed_negative=", paste(head(top_nonseed_neg$gene, 10), collapse = ","), "\n", sep = "")
cat("retained_or_discard_decision=", decision, "\n", sep = "")
cat("wrote=", file.path(out_dir, "stage3_gene_decoupling_candidate_summary.csv"), "\n", sep = "")
if (!is.na(pdf_path)) cat("wrote=", pdf_path, "\n", sep = "")
if (!is.na(svg_path)) cat("wrote=", svg_path, "\n", sep = "")
cat("stage3_gene_level_decoupling_prioritization_end=", format(Sys.time(), "%Y-%m-%dT%H:%M:%S%z"), "\n", sep = "")
sink()

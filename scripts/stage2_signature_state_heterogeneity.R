suppressPackageStartupMessages({
  library(data.table)
  library(ggplot2)
  library(patchwork)
})

project_root <- "<PROJECT_ROOT>"
score_file <- file.path(project_root, "03_results", "stage1_bulk_mhcii_screen", "stage1_bulk_signature_scores.csv")
out_dir <- file.path(project_root, "03_results", "stage2_signature_state_heterogeneity")
fig_dir <- file.path(project_root, "04_figures", "stage2_signature_state_heterogeneity")
log_dir <- file.path(project_root, "06_logs")
dir.create(out_dir, recursive = TRUE, showWarnings = FALSE)
dir.create(fig_dir, recursive = TRUE, showWarnings = FALSE)
dir.create(log_dir, recursive = TRUE, showWarnings = FALSE)

log_file <- file.path(log_dir, paste0("stage2_signature_state_heterogeneity_", format(Sys.time(), "%Y%m%d_%H%M%S"), ".log"))
sink(log_file, split = TRUE)
cat("stage2_signature_state_heterogeneity_start=", format(Sys.time(), "%Y-%m-%dT%H:%M:%S%z"), "\n", sep = "")

scores <- fread(score_file)
signature_cols <- c(
  "six_gene_panel",
  "myeloid_inflammatory",
  "immunometabolic_stress",
  "mhcii_cd74_axis",
  "hla_dr_core",
  "interferon_antigen_presentation",
  "adaptive_t_cell_context"
)

missing_cols <- setdiff(signature_cols, names(scores))
if (length(missing_cols) > 0) {
  stop("Missing signature columns: ", paste(missing_cols, collapse = ", "))
}

z_dt <- copy(scores)
for (col in signature_cols) {
  z_col <- paste0(col, "_z")
  z_dt[, (z_col) := {
    mu <- mean(get(col), na.rm = TRUE)
    s <- sd(get(col), na.rm = TRUE)
    if (is.na(s) || s == 0) rep(NA_real_, .N) else (get(col) - mu) / s
  }, by = accession]
}
z_cols <- paste0(signature_cols, "_z")

case_dt <- z_dt[case_control_main == "CASE"]
case_complete <- case_dt[complete.cases(case_dt[, ..z_cols])]
cat("n_case_complete=", nrow(case_complete), "\n", sep = "")
cat("n_datasets=", length(unique(case_complete$accession)), "\n", sep = "")

set.seed(20260611)
k_values <- 2:4
cluster_quality <- rbindlist(lapply(k_values, function(k) {
  km <- kmeans(as.matrix(case_complete[, ..z_cols]), centers = k, nstart = 100, iter.max = 100)
  sil_mean <- NA_real_
  if (requireNamespace("cluster", quietly = TRUE)) {
    d <- dist(as.matrix(case_complete[, ..z_cols]))
    sil <- cluster::silhouette(km$cluster, d)
    sil_mean <- mean(sil[, "sil_width"])
  }
  data.table(k = k, total_withinss = km$tot.withinss, betweenss = km$betweenss, silhouette_mean = sil_mean)
}))
fwrite(cluster_quality, file.path(out_dir, "stage2_kmeans_cluster_quality.csv"))

selected_k <- 3
km <- kmeans(as.matrix(case_complete[, ..z_cols]), centers = selected_k, nstart = 200, iter.max = 100)
case_complete[, cluster_raw := paste0("C", km$cluster)]

centroids <- case_complete[, lapply(.SD, mean, na.rm = TRUE), by = cluster_raw, .SDcols = z_cols]
centroids[, inflammatory_index := rowMeans(.SD, na.rm = TRUE), .SDcols = paste0(c("six_gene_panel", "myeloid_inflammatory", "immunometabolic_stress"), "_z")]
centroids[, antigen_presentation_index := rowMeans(.SD, na.rm = TRUE), .SDcols = paste0(c("mhcii_cd74_axis", "hla_dr_core", "interferon_antigen_presentation", "adaptive_t_cell_context"), "_z")]
centroids[, decoupling_index := inflammatory_index - antigen_presentation_index]
setorder(centroids, -decoupling_index)
centroids[, immune_state := c("Decoupled inflammatory / MHC-II-low", "Intermediate mixed", "MHC-II/adaptive preserved")[seq_len(.N)]]
label_map <- centroids[, .(cluster_raw, immune_state)]
case_complete <- merge(case_complete, label_map, by = "cluster_raw", all.x = TRUE)

centroids_labeled <- merge(centroids, label_map, by = c("cluster_raw", "immune_state"), all.x = TRUE)
fwrite(centroids_labeled, file.path(out_dir, "stage2_immune_state_centroids.csv"))
fwrite(case_complete[, c("accession", "gsm_id", "analysis_group_primary", "analysis_group_secondary", "label_confidence", "cluster_raw", "immune_state", signature_cols, z_cols), with = FALSE],
       file.path(out_dir, "stage2_case_immune_state_assignments.csv"))

state_counts <- case_complete[, .N, by = .(immune_state)]
state_counts[, fraction := N / sum(N)]
setorder(state_counts, -N)
fwrite(state_counts, file.path(out_dir, "stage2_immune_state_counts.csv"))

dataset_distribution <- case_complete[, .N, by = .(accession, immune_state)]
dataset_distribution[, dataset_n_case_complete := sum(N), by = accession]
dataset_distribution[, fraction := N / dataset_n_case_complete]
setorder(dataset_distribution, accession, immune_state)
fwrite(dataset_distribution, file.path(out_dir, "stage2_immune_state_dataset_distribution.csv"))

state_by_dataset_presence <- dataset_distribution[N > 0, .(n_datasets_present = uniqueN(accession), n_cases = sum(N)), by = immune_state]
fwrite(state_by_dataset_presence, file.path(out_dir, "stage2_immune_state_cross_dataset_presence.csv"))

centroid_long <- melt(
  centroids_labeled,
  id.vars = c("cluster_raw", "immune_state", "inflammatory_index", "antigen_presentation_index", "decoupling_index"),
  measure.vars = z_cols,
  variable.name = "signature",
  value.name = "mean_z"
)
centroid_long[, signature := sub("_z$", "", signature)]
signature_labels <- c(
  six_gene_panel = "Six-gene",
  myeloid_inflammatory = "Myeloid",
  immunometabolic_stress = "Immunometabolic",
  mhcii_cd74_axis = "MHC-II/CD74",
  hla_dr_core = "HLA-DR",
  interferon_antigen_presentation = "IFN/AP",
  adaptive_t_cell_context = "Adaptive/T"
)
centroid_long[, signature_label := signature_labels[signature]]
centroid_long[, signature_label := factor(signature_label, levels = signature_labels[signature_cols])]
centroid_long[, immune_state := factor(immune_state, levels = centroids_labeled$immune_state)]

p_heat <- ggplot(centroid_long, aes(x = signature_label, y = immune_state, fill = mean_z)) +
  geom_tile(color = "white", linewidth = 0.35) +
  geom_text(aes(label = sprintf("%.2f", mean_z)), size = 3.0) +
  scale_fill_gradient2(low = "#2f6f95", mid = "white", high = "#b4473a", midpoint = 0) +
  labs(title = "A. Signature-derived immune states in public sepsis cases", x = NULL, y = NULL, fill = "Mean z") +
  theme_minimal(base_size = 10) +
  theme(panel.grid = element_blank(), plot.title = element_text(face = "bold"), axis.text.x = element_text(angle = 35, hjust = 1))

dataset_distribution[, immune_state := factor(immune_state, levels = centroids_labeled$immune_state)]
p_bar <- ggplot(dataset_distribution, aes(x = accession, y = fraction, fill = immune_state)) +
  geom_col(width = 0.78, color = "grey25", linewidth = 0.15) +
  scale_fill_manual(values = c(
    "Decoupled inflammatory / MHC-II-low" = "#b4473a",
    "Intermediate mixed" = "#d9b44a",
    "MHC-II/adaptive preserved" = "#2f6f95"
  )) +
  labs(title = "B. Immune-state distribution by cohort", x = NULL, y = "Fraction of sepsis cases", fill = NULL) +
  theme_minimal(base_size = 10) +
  theme(panel.grid.minor = element_blank(), plot.title = element_text(face = "bold"), axis.text.x = element_text(angle = 35, hjust = 1), legend.position = "bottom")

fig <- p_heat / p_bar
pdf_path <- file.path(fig_dir, "stage2_signature_state_heterogeneity.pdf")
svg_path <- file.path(fig_dir, "stage2_signature_state_heterogeneity.svg")
ggsave(pdf_path, fig, width = 10.5, height = 7.0, device = cairo_pdf)
ggsave(svg_path, fig, width = 10.5, height = 7.0)

decoupled_presence <- state_by_dataset_presence[immune_state == "Decoupled inflammatory / MHC-II-low", n_datasets_present]
decoupled_cases <- state_counts[immune_state == "Decoupled inflammatory / MHC-II-low", N]
decoupled_fraction <- state_counts[immune_state == "Decoupled inflammatory / MHC-II-low", fraction]
if (length(decoupled_presence) == 0) decoupled_presence <- 0
if (length(decoupled_cases) == 0) decoupled_cases <- 0
if (length(decoupled_fraction) == 0) decoupled_fraction <- 0

decision <- if (decoupled_presence >= 4 && decoupled_cases >= 20) {
  "RETAIN_AS_MAIN_TEXT_HETEROGENEITY_SUPPORT"
} else if (decoupled_presence >= 2 && decoupled_cases >= 10) {
  "RETAIN_AS_SUPPLEMENTARY_CONTEXT"
} else {
  "DISCARD_AS_UNDERPOWERED_HETEROGENEITY_RESULT"
}

status <- c(
  "# Stage 2 Signature-State Heterogeneity STATUS",
  "",
  "## STATUS",
  "",
  if (grepl("DISCARD", decision)) "PASS_WITH_NEGATIVE_OR_WEAK_CONTEXT" else "PASS_WITH_POSITIVE_HETEROGENEITY_CONTEXT",
  "",
  "## Method",
  "",
  "Dataset-centered signature scores from public sepsis bulk cohorts were clustered among case samples only. This is a signature-derived immune-state analysis, not a validated clinical subtype analysis.",
  "",
  "## Key Result",
  "",
  paste0("- Complete case samples: ", nrow(case_complete), " across ", length(unique(case_complete$accession)), " datasets."),
  paste0("- Decoupled inflammatory / MHC-II-low state: ", decoupled_cases, " cases, ", sprintf("%.1f", 100 * decoupled_fraction), "% of complete cases, present in ", decoupled_presence, " datasets."),
  "",
  "## Decision",
  "",
  paste0("retained_or_discard_decision: ", decision),
  "",
  "## Claim Allowed",
  "",
  "- Signature-derived sepsis immune-state heterogeneity context.",
  "- Support that the decoupling axis is represented at the patient/sample-state level.",
  "",
  "## Claim Prohibited",
  "",
  "- No clinically validated subtype claim.",
  "- No ARDS-specific or outcome-specific claim.",
  "- No treatment-response claim.",
  "- No causal claim.",
  "",
  "## Output Files",
  "",
  "- `stage2_kmeans_cluster_quality.csv`",
  "- `stage2_case_immune_state_assignments.csv`",
  "- `stage2_immune_state_centroids.csv`",
  "- `stage2_immune_state_counts.csv`",
  "- `stage2_immune_state_dataset_distribution.csv`",
  "- `stage2_immune_state_cross_dataset_presence.csv`",
  "- `04_figures/stage2_signature_state_heterogeneity/stage2_signature_state_heterogeneity.pdf`",
  "- `04_figures/stage2_signature_state_heterogeneity/stage2_signature_state_heterogeneity.svg`"
)
writeLines(status, file.path(out_dir, "stage2_signature_state_heterogeneity_STATUS.md"))

cat("selected_k=", selected_k, "\n", sep = "")
cat("retained_or_discard_decision=", decision, "\n", sep = "")
cat("wrote=", file.path(out_dir, "stage2_case_immune_state_assignments.csv"), "\n", sep = "")
cat("wrote=", pdf_path, "\n", sep = "")
cat("wrote=", svg_path, "\n", sep = "")
cat("stage2_signature_state_heterogeneity_end=", format(Sys.time(), "%Y-%m-%dT%H:%M:%S%z"), "\n", sep = "")
sink()

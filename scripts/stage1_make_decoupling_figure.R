suppressPackageStartupMessages({
  library(data.table)
  library(ggplot2)
  library(patchwork)
  library(grid)
})

project_root <- "<PROJECT_ROOT>"
bulk_dir <- file.path(project_root, "03_results", "stage1_bulk_mhcii_screen")
out_dir <- file.path(project_root, "04_figures", "stage1_decoupling_axis")
log_dir <- file.path(project_root, "06_logs")
dir.create(out_dir, recursive = TRUE, showWarnings = FALSE)
dir.create(log_dir, recursive = TRUE, showWarnings = FALSE)

log_file <- file.path(log_dir, paste0("stage1_make_decoupling_figure_", format(Sys.time(), "%Y%m%d_%H%M%S"), ".log"))
sink(log_file, split = TRUE)
cat("stage1_make_decoupling_figure_start=", format(Sys.time(), "%Y-%m-%dT%H:%M:%S%z"), "\n", sep = "")

cc <- fread(file.path(bulk_dir, "stage1_bulk_signature_case_control_summary.csv"))
cor <- fread(file.path(bulk_dir, "stage1_bulk_signature_correlation_summary.csv"))

sig_labels <- c(
  six_gene_panel = "Six-gene panel",
  myeloid_inflammatory = "Myeloid inflammatory",
  immunometabolic_stress = "Immunometabolic stress",
  mhcii_cd74_axis = "MHC-II/CD74 axis",
  hla_dr_core = "HLA-DR core",
  adaptive_t_cell_context = "Adaptive/T-cell context",
  interferon_antigen_presentation = "IFN/antigen presentation"
)

pair_labels <- c(
  immunometabolic_vs_myeloid = "Immunometabolic vs myeloid",
  ifn_vs_mhcii = "IFN/AP vs MHC-II",
  six_vs_mhcii = "Six-gene vs MHC-II",
  six_vs_hladr = "Six-gene vs HLA-DR",
  myeloid_vs_mhcii = "Myeloid vs MHC-II",
  myeloid_vs_adaptive = "Myeloid vs adaptive/T-cell"
)

cc[, label := sig_labels[signature]]
cc[, direction_class := ifelse(median_effect >= 0, "Higher in cases", "Lower in cases")]
cc[, label := factor(label, levels = rev(sig_labels[cc$signature]))]

p1 <- ggplot(cc, aes(x = label, y = median_effect, fill = direction_class)) +
  geom_col(width = 0.72, color = "grey20", linewidth = 0.2) +
  geom_hline(yintercept = 0, color = "grey35", linewidth = 0.35) +
  geom_text(aes(label = paste0(n_fdr, "/", n_datasets, " FDR")), hjust = ifelse(cc$median_effect >= 0, -0.08, 1.08), size = 3.0) +
  coord_flip(clip = "off") +
  scale_fill_manual(values = c("Higher in cases" = "#b4473a", "Lower in cases" = "#2f6f95")) +
  labs(title = "A. Case-control signal across public bulk cohorts", x = NULL, y = "Median case-control score difference") +
  theme_minimal(base_size = 10) +
  theme(
    panel.grid.minor = element_blank(),
    legend.position = "bottom",
    plot.title = element_text(face = "bold", size = 11),
    axis.text.y = element_text(size = 9),
    plot.margin = margin(6, 22, 6, 6)
  )

cor[, label := pair_labels[pair]]
cor[, direction_class := ifelse(median_rho >= 0, "Positive coupling", "Negative coupling")]
cor[, label := factor(label, levels = rev(pair_labels[cor$pair]))]

p2 <- ggplot(cor, aes(x = label, y = median_rho, fill = direction_class)) +
  geom_col(width = 0.72, color = "grey20", linewidth = 0.2) +
  geom_hline(yintercept = 0, color = "grey35", linewidth = 0.35) +
  geom_text(aes(label = paste0(n_fdr, "/", n_datasets, " FDR")), hjust = ifelse(cor$median_rho >= 0, -0.08, 1.08), size = 3.0) +
  coord_flip(clip = "off") +
  scale_fill_manual(values = c("Positive coupling" = "#556b2f", "Negative coupling" = "#6f4a8e")) +
  labs(title = "B. Cross-axis coupling within cohorts", x = NULL, y = "Median Spearman rho") +
  theme_minimal(base_size = 10) +
  theme(
    panel.grid.minor = element_blank(),
    legend.position = "bottom",
    plot.title = element_text(face = "bold", size = 11),
    axis.text.y = element_text(size = 9),
    plot.margin = margin(6, 22, 6, 6)
  )

nodes <- data.table(
  node = c(
    "Six-gene panel",
    "Myeloid inflammatory\nprogram",
    "Immunometabolic\nstress",
    "MHC-II/CD74/HLA-DR\naxis",
    "Adaptive/T-cell\ncontext",
    "Mono-supported\nsingle-cell localization",
    "APP/CD74 communication\ncontext",
    "STAT1/IRF1/CIITA\nregulatory context"
  ),
  x = c(0.15, 0.18, 0.18, 0.70, 0.72, 0.16, 0.72, 0.70),
  y = c(0.56, 0.78, 0.34, 0.62, 0.34, 0.92, 0.82, 0.94),
  group = c("panel", "up", "up", "down", "down", "context", "context", "context")
)

edges <- data.table(
  x = c(0.18, 0.18, 0.30, 0.30, 0.30, 0.70, 0.70, 0.16),
  y = c(0.34, 0.78, 0.56, 0.78, 0.78, 0.82, 0.94, 0.92),
  xend = c(0.18, 0.15, 0.70, 0.70, 0.72, 0.70, 0.70, 0.18),
  yend = c(0.78, 0.56, 0.62, 0.62, 0.34, 0.62, 0.62, 0.78),
  edge_type = c("positive", "positive", "negative", "negative", "negative", "context", "context", "context"),
  label = c("rho +0.79", "case up", "rho -0.60", "rho -0.50", "rho -0.47", "APP/CD74", "TF context", "Mono")
)

p3 <- ggplot() +
  geom_segment(
    data = edges,
    aes(x = x, y = y, xend = xend, yend = yend, color = edge_type),
    linewidth = 0.8,
    arrow = arrow(length = unit(0.14, "inches"), type = "closed")
  ) +
  geom_text(data = edges, aes(x = (x + xend) / 2, y = (y + yend) / 2, label = label), size = 2.8, color = "grey20") +
  geom_label(
    data = nodes,
    aes(x = x, y = y, label = node, fill = group),
    color = "grey10",
    linewidth = 0.25,
    label.r = unit(0.05, "lines"),
    size = 3.0,
    lineheight = 0.95
  ) +
  scale_fill_manual(values = c(panel = "#f0e6cf", up = "#f2b6a6", down = "#b7d5e8", context = "#d5d9a7")) +
  scale_color_manual(values = c(positive = "#556b2f", negative = "#6f4a8e", context = "#5f6c72")) +
  coord_cartesian(xlim = c(0, 0.95), ylim = c(0.20, 1.02), expand = FALSE) +
  labs(title = "C. Working mechanism: inflammatory stress and antigen-presentation decoupling") +
  theme_void(base_size = 10) +
  theme(
    legend.position = "none",
    plot.title = element_text(face = "bold", size = 11, hjust = 0)
  )

combined <- (p1 | p2) / p3 + plot_layout(heights = c(1.05, 1.0)) +
  plot_annotation(
    title = "Sepsis myeloid-inflammatory / MHC-II-CD74 decoupling axis",
    subtitle = "Public bulk screen plus computational context; not clinical validation or confirmed signaling",
    theme = theme(
      plot.title = element_text(face = "bold", size = 14),
      plot.subtitle = element_text(size = 10)
    )
  )

pdf_path <- file.path(out_dir, "stage1_decoupling_axis_mechanism_figure.pdf")
svg_path <- file.path(out_dir, "stage1_decoupling_axis_mechanism_figure.svg")
ggsave(pdf_path, combined, width = 11, height = 7.5, device = cairo_pdf)
ggsave(svg_path, combined, width = 11, height = 7.5)

fig_manifest <- data.table(
  figure = c("stage1_decoupling_axis_mechanism_figure.pdf", "stage1_decoupling_axis_mechanism_figure.svg"),
  path = c(pdf_path, svg_path),
  format = c("PDF", "SVG"),
  vector = TRUE,
  claim_boundary = "Computational context only; no clinical validation, no confirmed signaling, no MR causal claim."
)
fwrite(fig_manifest, file.path(out_dir, "stage1_decoupling_axis_figure_manifest.csv"))

cat("wrote=", pdf_path, "\n", sep = "")
cat("wrote=", svg_path, "\n", sep = "")
cat("stage1_make_decoupling_figure_end=", format(Sys.time(), "%Y-%m-%dT%H:%M:%S%z"), "\n", sep = "")
sink()

# Run this only when starting the analysis stage that needs these packages.
# It is intentionally not executed during project scaffolding.

cran_pkgs <- c(
  "MendelianRandomization",
  "mediation",
  "CMAverse",
  "bnlearn",
  "mixOmics",
  "WGCNA",
  "randomForest",
  "data.table",
  "remotes"
)

missing_cran <- setdiff(cran_pkgs, rownames(installed.packages()))
if (length(missing_cran) > 0) {
  install.packages(missing_cran, repos = "https://cloud.r-project.org")
}

if (!requireNamespace("BiocManager", quietly = TRUE)) {
  install.packages("BiocManager", repos = "https://cloud.r-project.org")
}

bioc_pkgs <- c("MOFA2", "SingleCellExperiment", "GEOquery", "limma")
missing_bioc <- setdiff(bioc_pkgs, rownames(installed.packages()))
if (length(missing_bioc) > 0) {
  BiocManager::install(missing_bioc, ask = FALSE, update = FALSE)
}

if (!requireNamespace("TwoSampleMR", quietly = TRUE)) {
  remotes::install_github("MRCIEU/TwoSampleMR")
}

if (!requireNamespace("MRPRESSO", quietly = TRUE)) {
  remotes::install_github("rondolab/MR-PRESSO")
}

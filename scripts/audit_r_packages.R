pkgs <- c(
  "TwoSampleMR",
  "MendelianRandomization",
  "MRPRESSO",
  "mediation",
  "CMAverse",
  "bnlearn",
  "MOFA2",
  "mixOmics",
  "Seurat",
  "SingleCellExperiment",
  "GEOquery",
  "limma",
  "WGCNA",
  "randomForest",
  "data.table"
)

installed <- rownames(installed.packages())
status <- data.frame(
  package = pkgs,
  installed = pkgs %in% installed,
  stringsAsFactors = FALSE
)

status$version <- vapply(pkgs, function(pkg) {
  if (!pkg %in% installed) return(NA_character_)
  as.character(utils::packageVersion(pkg))
}, character(1))

out <- "<PROJECT_ROOT>/01_data_manifest/legacy_index/software_package_status.tsv"
utils::write.table(status, out, sep = "\t", quote = FALSE, row.names = FALSE)
print(status)

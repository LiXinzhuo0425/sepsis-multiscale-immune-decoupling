suppressPackageStartupMessages({
  library(data.table)
})

project_root <- "<PROJECT_ROOT>"
manifest_dir <- file.path(project_root, "01_data_manifest")
log_dir <- file.path(project_root, "06_logs")
dir.create(manifest_dir, recursive = TRUE, showWarnings = FALSE)
dir.create(log_dir, recursive = TRUE, showWarnings = FALSE)

log_file <- file.path(log_dir, paste0("refresh_project_manifest_", format(Sys.time(), "%Y%m%d_%H%M%S"), ".log"))
sink(log_file, split = TRUE)
cat("refresh_project_manifest_start=", format(Sys.time(), "%Y-%m-%dT%H:%M:%S%z"), "\n", sep = "")

files <- c(
  file.path(project_root, "README.md"),
  file.path(project_root, ".gitignore"),
  list.files(file.path(project_root, "00_admin"), full.names = TRUE, recursive = TRUE),
  list.files(file.path(project_root, "01_data_manifest"), full.names = TRUE, recursive = TRUE),
  list.files(file.path(project_root, "02_scripts"), full.names = TRUE, recursive = TRUE),
  list.files(file.path(project_root, "03_results"), full.names = TRUE, recursive = TRUE),
  list.files(file.path(project_root, "04_figures"), full.names = TRUE, recursive = TRUE),
  list.files(file.path(project_root, "05_manuscript"), full.names = TRUE, recursive = TRUE),
  list.files(file.path(project_root, "06_logs"), full.names = TRUE, recursive = TRUE),
  list.files(file.path(project_root, "07_access"), full.names = TRUE, recursive = TRUE),
  list.files(file.path(project_root, "08_protocols"), full.names = TRUE, recursive = TRUE)
)
files <- sort(unique(files[file.exists(files)]))
manifest <- data.table(path = files)
manifest[, rel_path := sub(paste0("^", project_root, "/"), "", path)]
manifest[, size_bytes := file.info(path)$size]
manifest[, modified_time := as.character(file.info(path)$mtime)]
manifest[, artifact_class := fifelse(grepl("^03_results|^04_figures|^05_manuscript", rel_path), "analysis_or_manuscript_output",
                              fifelse(grepl("^02_scripts", rel_path), "reproducibility_script",
                              fifelse(grepl("^01_data_manifest|^00_admin|^08_protocols|^README|^\\.gitignore", rel_path), "governance_or_manifest",
                              fifelse(grepl("^07_access", rel_path), "access_packet", "log_or_other"))))]
manifest[, md5 := vapply(path, function(p) {
  if (file.info(p)$size > 50 * 1024 * 1024) return(NA_character_)
  as.character(tools::md5sum(p))
}, character(1))]

fwrite(manifest[, .(rel_path, size_bytes, modified_time, artifact_class, md5)], file.path(manifest_dir, "project_output_manifest_latest.csv"))

cat("manifest_rows=", nrow(manifest), "\n", sep = "")
cat("wrote=", file.path(manifest_dir, "project_output_manifest_latest.csv"), "\n", sep = "")
cat("refresh_project_manifest_end=", format(Sys.time(), "%Y-%m-%dT%H:%M:%S%z"), "\n", sep = "")
sink()

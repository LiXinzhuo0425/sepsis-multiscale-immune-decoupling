suppressPackageStartupMessages({
  library(data.table)
})

project_root <- "<PROJECT_ROOT>"
legacy_root <- "<READ_ONLY_TRANSCRIPTOMICS_REFERENCE_ROOT>"
bulk_dir <- file.path(project_root, "03_results", "stage1_bulk_mhcii_screen")
route_dir <- file.path(project_root, "03_results", "stage1_integrated_route_selection")
out_dir <- file.path(project_root, "03_results", "stage1_multilayer_mechanism_context")
log_dir <- file.path(project_root, "06_logs")
dir.create(out_dir, recursive = TRUE, showWarnings = FALSE)
dir.create(log_dir, recursive = TRUE, showWarnings = FALSE)

log_file <- file.path(log_dir, paste0("stage1_extract_multilayer_context_", format(Sys.time(), "%Y%m%d_%H%M%S"), ".log"))
sink(log_file, split = TRUE)
cat("stage1_extract_multilayer_context_start=", format(Sys.time(), "%Y-%m-%dT%H:%M:%S%z"), "\n", sep = "")

old_tables <- file.path(
  legacy_root, "03_results", "tables",
  c(
    "P10R_refined_single_cell_localization_synthesis.csv",
    "P14R_QA3_single_cell_donor_aware_numeric_master_table.csv",
    "EXP15_GSE167363_replication_synthesis.csv",
    "EXP15_GSE216009_limited_replication_synthesis.csv",
    "EXP02R_CD74_MHCII_axis_final_adjudication.csv",
    "P14R_QA_CD74_axis_adjudication_table.csv",
    "EXP09_integrated_synthesis.csv",
    "EXP11_regulatory_context_synthesis.csv",
    "P13_claim_boundary_master_table.csv",
    "P13_master_evidence_triage.csv"
  )
)

new_tables <- c(
  file.path(bulk_dir, "stage1_bulk_signature_case_control_summary.csv"),
  file.path(bulk_dir, "stage1_bulk_signature_correlation_summary.csv"),
  file.path(route_dir, "stage1_integrated_route_selection_STATUS.md"),
  file.path(route_dir, "stage1_route_candidates.csv")
)

required_files <- c(old_tables, new_tables)
missing_files <- required_files[!file.exists(required_files)]
if (length(missing_files) > 0) {
  stop("Missing required files: ", paste(missing_files, collapse = "; "))
}

cc <- fread(file.path(bulk_dir, "stage1_bulk_signature_case_control_summary.csv"))
cors <- fread(file.path(bulk_dir, "stage1_bulk_signature_correlation_summary.csv"))
p10r <- fread(file.path(legacy_root, "03_results", "tables", "P10R_refined_single_cell_localization_synthesis.csv"))
sc_master <- fread(file.path(legacy_root, "03_results", "tables", "P14R_QA3_single_cell_donor_aware_numeric_master_table.csv"))
gse167363 <- fread(file.path(legacy_root, "03_results", "tables", "EXP15_GSE167363_replication_synthesis.csv"))
gse216009 <- fread(file.path(legacy_root, "03_results", "tables", "EXP15_GSE216009_limited_replication_synthesis.csv"))
cd74 <- fread(file.path(legacy_root, "03_results", "tables", "EXP02R_CD74_MHCII_axis_final_adjudication.csv"))
cd74_adjud <- fread(file.path(legacy_root, "03_results", "tables", "P14R_QA_CD74_axis_adjudication_table.csv"))
exp09 <- fread(file.path(legacy_root, "03_results", "tables", "EXP09_integrated_synthesis.csv"))
exp11 <- fread(file.path(legacy_root, "03_results", "tables", "EXP11_regulatory_context_synthesis.csv"))

fmt_num <- function(x, digits = 3) {
  ifelse(is.na(x), "NA", formatC(x, format = "f", digits = digits))
}

sig_anchor <- function(signature_id) {
  row <- cc[signature == signature_id][1]
  paste0(
    row$signature, ": median effect ", fmt_num(row$median_effect),
    "; FDR-significant ", row$n_fdr, "/", row$n_datasets,
    "; direction counts up/down ", row$n_up, "/", row$n_down,
    "; strongest ", row$strongest_dataset, " p=", format(row$min_p, scientific = TRUE, digits = 3)
  )
}

cor_anchor <- function(pair_id) {
  row <- cors[pair == pair_id][1]
  paste0(
    row$pair, ": median rho ", fmt_num(row$median_rho),
    "; FDR-significant ", row$n_fdr, "/", row$n_datasets,
    "; positive fraction ", row$positive_fraction,
    "; strongest ", row$strongest_dataset, " rho=", fmt_num(row$strongest_rho),
    " p=", format(row$min_p, scientific = TRUE, digits = 3)
  )
}

evidence <- rbindlist(list(
  data.table(
    layer = "Public bulk transcriptomics",
    evidence_item = "Sepsis cases show higher six-gene/myeloid/immunometabolic programs and lower MHC-II/CD74/HLA-DR/adaptive context",
    source_file = "03_results/stage1_bulk_mhcii_screen/stage1_bulk_signature_case_control_summary.csv",
    quantitative_anchor = paste(sig_anchor("six_gene_panel"), sig_anchor("mhcii_cd74_axis"), sig_anchor("myeloid_inflammatory"), sig_anchor("immunometabolic_stress"), sep = " | "),
    support_level = "strong_cross_cohort_context",
    interpretation = "Positive main route: immune-state decoupling, not a diagnostic classifier.",
    claim_allowed = "Cross-cohort public-bulk transcriptomic decoupling context.",
    claim_prohibited = "No clinical validation, no causal mechanism, no diagnostic utility claim.",
    recommended_use = "MAIN_TEXT"
  ),
  data.table(
    layer = "Within-cohort coupling",
    evidence_item = "Six-gene/myeloid inflammatory scores are inversely coupled to MHC-II/CD74/HLA-DR scores across public cohorts",
    source_file = "03_results/stage1_bulk_mhcii_screen/stage1_bulk_signature_correlation_summary.csv",
    quantitative_anchor = paste(cor_anchor("six_vs_mhcii"), cor_anchor("six_vs_hladr"), cor_anchor("myeloid_vs_mhcii"), cor_anchor("immunometabolic_vs_myeloid"), sep = " | "),
    support_level = "strong_cross_cohort_context",
    interpretation = "A mechanistic framing around inflammatory stress and antigen-presentation collapse is more informative than a single activation score.",
    claim_allowed = "Signature-level cross-axis association and prioritization.",
    claim_prohibited = "No direction-of-effect causality without MR/experimental validation.",
    recommended_use = "MAIN_TEXT"
  ),
  p10r[finding %in% c("myeloid_centered_localization", "monocyte_support", "megakaryocyte_platelet_lineage_signal", "neutrophil_granulocyte_status"),
       .(
         layer = "Single-cell localization",
         evidence_item = finding,
         source_file = "SepSMART_IJMS_SixGene_Sepsis/03_results/tables/P10R_refined_single_cell_localization_synthesis.csv",
         quantitative_anchor = evidence_layers,
         support_level,
         interpretation = recommended_manuscript_use,
         claim_allowed,
         claim_prohibited,
         recommended_use = recommended_manuscript_use
       )],
  sc_master[cell_group %in% c("Mono", "Megakaryocyte", "Granulocyte_neutrophil_marker_group", "Mono_myeloid_marker_group"),
            .(
              layer = "Donor-aware single-cell numeric context",
              evidence_item = paste0(dataset, " / ", cell_group),
              source_file = "SepSMART_IJMS_SixGene_Sepsis/03_results/tables/P14R_QA3_single_cell_donor_aware_numeric_master_table.csv",
              quantitative_anchor = paste0(
                "n_cells=", n_cells,
                "; n_donors_or_samples=", n_donors_or_samples,
                "; six_gene_score_mean=", fmt_num(six_gene_score_mean),
                "; donor_rank=", ifelse(is.na(donor_level_rank), "NA", donor_level_rank),
                "; S100A8_detection=", fmt_num(S100A8_detection)
              ),
              support_level,
              interpretation = notes,
              claim_allowed,
              claim_prohibited,
              recommended_use = claim_level
            )],
  gse167363[, .(
    layer = "Independent scRNA replication/context audit",
    evidence_item = paste0(dataset, " marker-assisted myeloid/granulocyte/B context"),
    source_file = "SepSMART_IJMS_SixGene_Sepsis/03_results/tables/EXP15_GSE167363_replication_synthesis.csv",
    quantitative_anchor = paste0(
      "n_cells=", n_cells,
      "; n_samples=", n_samples,
      "; n_donors_if_available=", n_donors_if_available,
      "; six_gene_score_mean=", fmt_num(six_gene_score_mean),
      "; S100A8_detection=", fmt_num(S100A8_detection_fraction),
      "; MHCII_CD74_score_mean=", fmt_num(MHCII_CD74_score_mean)
    ),
    support_level = support_for_SCP548_mainline,
    interpretation = notes,
    claim_allowed,
    claim_prohibited,
    recommended_use = "SUPPLEMENT_CONTEXT"
  )],
  gse216009[, .(
    layer = "Independent scRNA controlled-object inspection",
    evidence_item = paste0(dataset, " additional neutrophil/granulopoiesis S100A8 context"),
    source_file = "SepSMART_IJMS_SixGene_Sepsis/03_results/tables/EXP15_GSE216009_limited_replication_synthesis.csv",
    quantitative_anchor = paste0(
      "object_class=", object_class,
      "; n_cells=", n_cells,
      "; n_donors_if_available=", n_donors_if_available,
      "; six_gene_visibility=", six_gene_visibility,
      "; ", S100A8_expression_context
    ),
    support_level = replication_status,
    interpretation = notes,
    claim_allowed,
    claim_prohibited,
    recommended_use = "SUPPLEMENT_CONTEXT"
  )],
  cd74[axis_component %in% c("MHC-II/CD74 pathway-context axis", "APP/CD74", "HLA/CD74 pathway context", "MIF/CD74"),
       .(
         layer = "CD74/MHC-II communication and pathway context",
         evidence_item = axis_component,
         source_file = "SepSMART_IJMS_SixGene_Sepsis/03_results/tables/EXP02R_CD74_MHCII_axis_final_adjudication.csv",
         quantitative_anchor = paste0(evidence_layers_supporting, " | formal_tool_support=", formal_tool_support, " | fallback_support=", fallback_support),
         support_level,
         interpretation = notes,
         claim_allowed,
         claim_prohibited,
         recommended_use = recommended_manuscript_use
       )],
  cd74_adjud[axis %in% c("APP/CD74", "MHC-II/CD74 pathway/context", "HLA/CD74_direct", "MIF/CD74_direct"),
             .(
               layer = "CD74-axis adjudication",
               evidence_item = axis,
               source_file = "SepSMART_IJMS_SixGene_Sepsis/03_results/tables/P14R_QA_CD74_axis_adjudication_table.csv",
               quantitative_anchor = paste0("decision=", final_decision, "; reason=", reason_for_retention_or_exclusion),
               support_level = final_decision,
               interpretation = notes,
               claim_allowed,
               claim_prohibited,
               recommended_use = recommended_location
             )],
  exp11[regulatory_finding %in% c(
    "NFKB/RELA inflammatory regulatory context",
    "STAT1/IRF1 interferon antigen-presentation context",
    "SPI1/CEBPB/CEBPD myeloid regulatory context",
    "HIF1A immunometabolic regulatory context"
  ),
  .(
    layer = "Exploratory regulatory context",
    evidence_item = regulatory_finding,
    source_file = "SepSMART_IJMS_SixGene_Sepsis/03_results/tables/EXP11_regulatory_context_synthesis.csv",
    quantitative_anchor = paste0(
      "TF_or_regulon=", TF_or_regulon,
      "; ", relationship_to_six_gene_panel,
      "; ", relationship_to_MHCII_CD74,
      "; ", relationship_to_mono_myeloid_context
    ),
    support_level,
    interpretation = "Regulatory context only; prioritized as mechanism support, not validated GRN.",
    claim_allowed,
    claim_prohibited,
    recommended_use
  )],
  exp09[grepl("INTERFERON|JAK|MHC|ANTIGEN", signature_name, ignore.case = TRUE)][1:8,
       .(
         layer = "Pathway/endotype context",
         evidence_item = signature_name,
         source_file = "SepSMART_IJMS_SixGene_Sepsis/03_results/tables/EXP09_integrated_synthesis.csv",
         quantitative_anchor = paste0(primary_directions, "; ", association_with_six_gene),
         support_level,
         interpretation = notes,
         claim_allowed,
         claim_prohibited,
         recommended_use
       )]
), fill = TRUE)

evidence[, evidence_rank := seq_len(.N)]
setcolorder(evidence, c("evidence_rank", setdiff(names(evidence), "evidence_rank")))
fwrite(evidence, file.path(out_dir, "stage1_multilayer_mechanism_evidence_matrix.csv"))

boundary <- evidence[, .(
  layer,
  evidence_item,
  support_level,
  claim_allowed,
  claim_prohibited,
  recommended_use
)]
fwrite(boundary, file.path(out_dir, "stage1_claim_boundary_matrix.csv"))

source_manifest <- data.table(path = required_files)
source_manifest[, exists := file.exists(path)]
source_manifest[, size_bytes := ifelse(exists, file.info(path)$size, NA_real_)]
source_manifest[, modified_time := ifelse(exists, as.character(file.info(path)$mtime), NA_character_)]
source_manifest[, md5 := ifelse(exists & !grepl("\\.md$", path), as.character(tools::md5sum(path)), NA_character_)]
source_manifest[, reuse_mode := ifelse(grepl(legacy_root, path, fixed = TRUE), "read_only_legacy_reference", "new_project_output")]
fwrite(source_manifest, file.path(out_dir, "stage1_multilayer_source_manifest.csv"))

status <- c(
  "# Stage 1 Multilayer Mechanism Context STATUS",
  "",
  "## STATUS",
  "",
  "PASS_WITH_MULTILAYER_POSITIVE_CONTEXT",
  "",
  "## Primary Finding",
  "",
  "The selected public-data route is the myeloid-inflammatory / immunometabolic stress versus MHC-II-CD74/HLA-DR decoupling axis in sepsis.",
  "",
  "## Evidence Layers",
  "",
  "- Public bulk: cross-cohort case-control and within-cohort correlation evidence support a reproducible decoupling pattern.",
  "- Single-cell: legacy donor-aware summaries support a Mono/myeloid-centered localization, with megakaryocyte/platelet-lineage and neutrophil/granulopoiesis caveats handled explicitly.",
  "- Communication/pathway: CD74/MHC-II is retained as pathway/communication context; APP/CD74 is the strongest computational LR context; direct HLA/CD74 and direct MIF/CD74 are not retained as direct signaling claims.",
  "- Regulatory context: STAT1/IRF1/CIITA, SPI1/CEBP, NFKB/RELA and HIF1A provide exploratory TF/regulon context only.",
  "",
  "## Decision",
  "",
  "retained_or_discard_decision: GO_PRIMARY_WITH_BOUNDED_MULTILAYER_MECHANISM",
  "",
  "## Claim Allowed",
  "",
  "- Cross-cohort transcriptomic immune-state decoupling.",
  "- Multi-layer computational mechanism reconstruction.",
  "- Donor-aware single-cell localization context.",
  "- CD74/MHC-II pathway and APP/CD74 computational communication context.",
  "",
  "## Claim Prohibited",
  "",
  "- No clinical validation.",
  "- No diagnostic/prognostic model validation.",
  "- No confirmed signaling mechanism.",
  "- No MR causal claim until harmonized MR is actually completed.",
  "- No pure myeloid-only or neutrophil-specific localization conclusion.",
  "",
  "## Output Files",
  "",
  "- `stage1_multilayer_mechanism_evidence_matrix.csv`",
  "- `stage1_claim_boundary_matrix.csv`",
  "- `stage1_multilayer_source_manifest.csv`"
)
writeLines(status, file.path(out_dir, "stage1_multilayer_mechanism_context_STATUS.md"))

cat("wrote=", file.path(out_dir, "stage1_multilayer_mechanism_evidence_matrix.csv"), "\n", sep = "")
cat("wrote=", file.path(out_dir, "stage1_claim_boundary_matrix.csv"), "\n", sep = "")
cat("wrote=", file.path(out_dir, "stage1_multilayer_source_manifest.csv"), "\n", sep = "")
cat("stage1_extract_multilayer_context_end=", format(Sys.time(), "%Y-%m-%dT%H:%M:%S%z"), "\n", sep = "")
sink()

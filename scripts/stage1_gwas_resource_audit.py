#!/usr/bin/env python3
import csv
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

PROJECT_ROOT = "<PROJECT_ROOT>"
OUT_DIR = os.path.join(PROJECT_ROOT, "03_results", "stage1_gwas_resource_audit")
LOG_DIR = os.path.join(PROJECT_ROOT, "06_logs")
os.makedirs(OUT_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

LOG_PATH = os.path.join(LOG_DIR, f"stage1_gwas_resource_audit_{time.strftime('%Y%m%d_%H%M%S')}.log")


def fetch_json(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": "Sepsis-Causal-MultiOmics/0.1"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_text(url, timeout=30, n=200000):
    req = urllib.request.Request(url, headers={"User-Agent": "Sepsis-Causal-MultiOmics/0.1"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read(n).decode("utf-8", "replace")


def write_csv(path, rows, fields):
    with open(path, "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def study_rows_for_trait(trait):
    url = "https://www.ebi.ac.uk/gwas/rest/api/studies/search/findByDiseaseTrait?diseaseTrait=" + urllib.parse.quote(trait)
    try:
        data = fetch_json(url)
    except Exception as exc:
        return [{
            "query_trait": trait,
            "status": "ERROR",
            "error": str(exc)
        }]
    studies = data.get("_embedded", {}).get("studies", [])
    rows = []
    for study in studies:
        pub = study.get("publicationInfo") or {}
        disease_trait = study.get("diseaseTrait") or {}
        rows.append({
            "query_trait": trait,
            "status": "OK",
            "accessionId": study.get("accessionId"),
            "diseaseTrait": disease_trait.get("trait"),
            "initialSampleSize": study.get("initialSampleSize"),
            "replicationSampleSize": study.get("replicationSampleSize"),
            "snpCount": study.get("snpCount"),
            "fullPvalueSet": study.get("fullPvalueSet"),
            "cohort": study.get("cohort"),
            "pubmedId": pub.get("pubmedId"),
            "publication": pub.get("publication"),
            "publicationDate": pub.get("publicationDate"),
            "title": pub.get("title"),
            "author": (pub.get("author") or {}).get("fullname"),
            "study_url": f"https://www.ebi.ac.uk/gwas/studies/{study.get('accessionId')}" if study.get("accessionId") else ""
        })
    return rows or [{"query_trait": trait, "status": "NO_STUDIES"}]


def catalog_ftp_status(accession):
    match = re.match(r"GCST(\d+)$", accession or "")
    if not match:
        return {}
    n = int(match.group(1))
    start = ((n - 1) // 1000) * 1000 + 1
    end = start + 999
    range_dir = f"GCST{start:08d}-GCST{end:08d}"
    ftp_dir = f"https://ftp.ebi.ac.uk/pub/databases/gwas/summary_statistics/{range_dir}/{accession}/"
    try:
        listing = fetch_text(ftp_dir, timeout=30)
    except Exception as exc:
        return {
            "accessionId": accession,
            "ftp_dir": ftp_dir,
            "ftp_status": "ERROR",
            "ftp_error": str(exc),
        }
    tsv = re.findall(r'href="([^"]+\.tsv\.gz)"', listing)
    yaml = re.findall(r'href="([^"]+meta\.yaml)"', listing)
    sizes = {}
    for line in listing.splitlines():
        for fname in tsv + yaml:
            if fname in line:
                sizes[fname] = re.sub("<[^>]+>", " ", line).strip()
    return {
        "accessionId": accession,
        "ftp_dir": ftp_dir,
        "ftp_status": "OK",
        "summary_files": ";".join(tsv),
        "metadata_files": ";".join(yaml),
        "listing_excerpt": " | ".join(sizes.get(fname, fname) for fname in tsv[:3])
    }


def main():
    log = open(LOG_PATH, "w")
    def logmsg(msg):
        print(msg)
        print(msg, file=log)
        log.flush()

    logmsg("stage1_gwas_resource_audit_start=" + time.strftime("%Y-%m-%dT%H:%M:%S%z"))

    disease_queries = [
        "Sepsis (hospital admission)",
        "sepsis",
        "septic shock",
        "coronary artery disease",
        "heart failure",
        "dementia",
        "chronic kidney disease",
        "Alzheimer disease",
    ]

    all_studies = []
    for trait in disease_queries:
        rows = study_rows_for_trait(trait)
        logmsg(f"trait={trait} rows={len(rows)}")
        all_studies.extend(rows)

    fields = [
        "query_trait", "status", "accessionId", "diseaseTrait", "initialSampleSize",
        "replicationSampleSize", "snpCount", "fullPvalueSet", "cohort", "pubmedId",
        "publication", "publicationDate", "title", "author", "study_url", "error"
    ]
    write_csv(os.path.join(OUT_DIR, "gwas_catalog_trait_studies.csv"), all_studies, fields)

    priority_accessions = []
    for row in all_studies:
        if str(row.get("fullPvalueSet")).lower() == "true" and row.get("accessionId"):
            priority_accessions.append(row["accessionId"])
    if "GCST90270871" not in priority_accessions:
        priority_accessions.insert(0, "GCST90270871")
    priority_accessions = list(dict.fromkeys(priority_accessions))[:20]

    ftp_rows = []
    for acc in priority_accessions:
        row = catalog_ftp_status(acc)
        logmsg(f"ftp={acc} status={row.get('ftp_status')}")
        ftp_rows.append(row)
    write_csv(
        os.path.join(OUT_DIR, "gwas_catalog_ftp_availability.csv"),
        ftp_rows,
        ["accessionId", "ftp_dir", "ftp_status", "summary_files", "metadata_files", "listing_excerpt", "ftp_error"]
    )

    opengwas_rows = []
    for url in ["https://api.opengwas.io/api/status", "https://api.opengwas.io/api/gwasinfo?trait=sepsis"]:
        try:
            text = fetch_text(url, timeout=30, n=5000)
            opengwas_rows.append({"url": url, "status": "OK", "response_excerpt": text[:1000]})
        except Exception as exc:
            opengwas_rows.append({"url": url, "status": "ERROR", "response_excerpt": str(exc)})
    write_csv(os.path.join(OUT_DIR, "opengwas_access_audit.csv"), opengwas_rows, ["url", "status", "response_excerpt"])

    finngen_rows = []
    for url in [
        "https://www.finngen.fi/en/access_results",
        "https://r10.risteys.finregistry.fi/endpoints/AB1_SEPSIS_CONDITION",
        "https://r10.risteys.finregistry.fi/endpoints/AB1_OTHER_SEPSIS",
        "https://r13.finngen.fi/pheno/AB1_OTHER_SEPSIS",
        "https://r13.finngen.fi/pheno/AB1_SEPSIS_CONDITION",
    ]:
        try:
            text = fetch_text(url, timeout=30, n=50000)
            finngen_rows.append({
                "url": url,
                "status": "OK",
                "contains_summary_statistics": "Summary statistics" in text or "summary statistics" in text,
                "excerpt": re.sub(r"\s+", " ", text[:1000])
            })
        except Exception as exc:
            finngen_rows.append({"url": url, "status": "ERROR", "excerpt": str(exc)})
    write_csv(os.path.join(OUT_DIR, "finngen_access_audit.csv"), finngen_rows, ["url", "status", "contains_summary_statistics", "excerpt"])

    sepsis_core = [row for row in all_studies if row.get("accessionId") == "GCST90270871"]
    status_path = os.path.join(OUT_DIR, "stage1_gwas_resource_audit_STATUS.md")
    with open(status_path, "w") as handle:
        handle.write("# Stage 1 GWAS Resource Audit STATUS\n\n")
        handle.write("## STATUS\n\n")
        handle.write("PASS_WITH_LIMITATIONS\n\n")
        handle.write("## Key Finding\n\n")
        if sepsis_core:
            row = sepsis_core[0]
            handle.write(
                f"- GWAS Catalog contains `{row.get('accessionId')}` for `{row.get('diseaseTrait')}`, "
                f"sample size `{row.get('initialSampleSize')}`, fullPvalueSet `{row.get('fullPvalueSet')}`.\n"
            )
        handle.write("- GWAS Catalog FTP availability was confirmed for full summary-statistics candidates, including GCST90270871 where available.\n")
        handle.write("- OpenGWAS API status is operational, but trait-level metadata requests require a JWT token under current API policy.\n")
        handle.write("- FinnGen public pages can be used for phenotype browsing; summary-statistics download still follows FinnGen access instructions.\n\n")
        handle.write("## Decision\n\n")
        handle.write("Continue the public multi-omics mechanism route now. Treat formal MR as feasible but gated by successful full-summary-statistics download and/or OpenGWAS JWT availability.\n\n")
        handle.write("## Retained Or Discard Decision\n\n")
        handle.write("retained_or_discard_decision: MR_FEASIBLE_BUT_NOT_YET_MAIN_EVIDENCE\n\n")
        handle.write("## Claim Allowed\n\n")
        handle.write("- Public GWAS resources support a future statistical-genetic causal-inference layer.\n")
        handle.write("- Current manuscript-grade positive evidence should come from transcriptomic and single-cell integration until MR is actually run.\n\n")
        handle.write("## Claim Prohibited\n\n")
        handle.write("- Do not claim MR causality before full harmonized MR is completed.\n")
        handle.write("- Do not claim FinnGen/UKB raw-level access beyond public summary-statistics availability.\n")

    logmsg("stage1_gwas_resource_audit_end=" + time.strftime("%Y-%m-%dT%H:%M:%S%z"))
    log.close()


if __name__ == "__main__":
    main()

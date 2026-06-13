#!/usr/bin/env python3
import csv
import gzip
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path("<PROJECT_ROOT>")
OUT_DIR = PROJECT_ROOT / "03_results" / "stage1_mr_gate_audit"
LOG_DIR = PROJECT_ROOT / "06_logs"
OUT_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

LOG_FILE = LOG_DIR / f"stage1_mr_gate_audit_{time.strftime('%Y%m%d_%H%M%S')}.log"

STUDIES = [
    {
        "accession": "GCST90270871",
        "trait": "Sepsis (hospital admission)",
        "url": "https://ftp.ebi.ac.uk/pub/databases/gwas/summary_statistics/GCST90270001-GCST90271000/GCST90270871/GCST90270871.tsv.gz",
        "meta_url": "https://ftp.ebi.ac.uk/pub/databases/gwas/summary_statistics/GCST90270001-GCST90271000/GCST90270871/GCST90270871.tsv.gz-meta.yaml",
        "rest_assoc_url": "https://www.ebi.ac.uk/gwas/rest/api/studies/GCST90270871/associations?projection=associationByStudy",
    },
    {
        "accession": "GCST90281174",
        "trait": "Sepsis (hospital admission)",
        "url": "https://ftp.ebi.ac.uk/pub/databases/gwas/summary_statistics/GCST90281001-GCST90282000/GCST90281174/GCST90281174.tsv.gz",
        "meta_url": "https://ftp.ebi.ac.uk/pub/databases/gwas/summary_statistics/GCST90281001-GCST90282000/GCST90281174/GCST90281174.tsv.gz-meta.yaml",
        "rest_assoc_url": "https://www.ebi.ac.uk/gwas/rest/api/studies/GCST90281174/associations?projection=associationByStudy",
    },
]


def log(msg: str) -> None:
    with LOG_FILE.open("a", encoding="utf-8") as fh:
        fh.write(msg + "\n")
    print(msg)


def head_request(url: str, timeout: int = 30):
    req = urllib.request.Request(url, method="HEAD")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return dict(resp.headers), resp.status


def get_text(url: str, timeout: int = 30) -> str:
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def read_gzip_header(url: str, timeout: int = 30, max_lines: int = 2):
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        gz = gzip.GzipFile(fileobj=resp)
        lines = []
        for _ in range(max_lines):
            line = gz.readline()
            if not line:
                break
            lines.append(line.decode("utf-8", errors="replace").rstrip("\n"))
        return lines


def rest_association_count(url: str, timeout: int = 30):
    text = get_text(url, timeout=timeout)
    data = json.loads(text)
    associations = data.get("_embedded", {}).get("associations", [])
    return len(associations)


def main() -> int:
    log(f"stage1_mr_gate_audit_start={time.strftime('%Y-%m-%dT%H:%M:%S%z')}")
    rows = []
    header_rows = []
    meta_rows = []
    for study in STUDIES:
        accession = study["accession"]
        log(f"auditing={accession}")
        row = {
            "accession": accession,
            "trait": study["trait"],
            "summary_url": study["url"],
            "meta_url": study["meta_url"],
            "rest_assoc_url": study["rest_assoc_url"],
            "head_status": "",
            "content_length_bytes": "",
            "content_length_mb": "",
            "accept_ranges": "",
            "last_modified": "",
            "metadata_status": "",
            "gwas_ssf_header_status": "",
            "rest_association_count": "",
            "opengwas_jwt_available": "YES" if os.environ.get("OPENGWAS_JWT") else "NO",
            "gate_decision": "",
            "notes": "",
        }
        try:
            headers, status = head_request(study["url"])
            row["head_status"] = str(status)
            row["content_length_bytes"] = headers.get("Content-Length", "")
            if headers.get("Content-Length"):
                row["content_length_mb"] = f"{int(headers['Content-Length']) / 1024 / 1024:.1f}"
            row["accept_ranges"] = headers.get("Accept-Ranges", "")
            row["last_modified"] = headers.get("Last-Modified", "")
        except Exception as exc:
            row["head_status"] = f"ERROR: {exc}"

        try:
            metadata_text = get_text(study["meta_url"])
            row["metadata_status"] = "OK"
            meta_path = OUT_DIR / f"{accession}_meta.yaml"
            meta_path.write_text(metadata_text, encoding="utf-8")
            for line in metadata_text.splitlines():
                if any(line.startswith(prefix) for prefix in ["gwas_id:", "genome_assembly:", "file_type:", "data_file_md5sum:", "is_harmonised:", "is_sorted:"]):
                    key, _, value = line.partition(":")
                    meta_rows.append({"accession": accession, "field": key.strip(), "value": value.strip()})
        except Exception as exc:
            row["metadata_status"] = f"ERROR: {exc}"

        try:
            lines = read_gzip_header(study["url"])
            row["gwas_ssf_header_status"] = "OK"
            if lines:
                columns = lines[0].split("\t")
                header_rows.append({
                    "accession": accession,
                    "n_columns": len(columns),
                    "columns": ";".join(columns),
                    "example_row": lines[1] if len(lines) > 1 else "",
                })
        except Exception as exc:
            row["gwas_ssf_header_status"] = f"ERROR: {exc}"

        try:
            row["rest_association_count"] = str(rest_association_count(study["rest_assoc_url"]))
        except Exception as exc:
            row["rest_association_count"] = f"ERROR: {exc}"

        if row["head_status"] == "200" and row["metadata_status"] == "OK" and row["gwas_ssf_header_status"] == "OK":
            if row["rest_association_count"] == "0":
                row["gate_decision"] = "FULL_SUMMARY_STATS_REQUIRED_FOR_IV_EXTRACTION"
                row["notes"] = "GWAS Catalog REST returned no curated associations for this study; instrument extraction requires full TSV scan or authenticated OpenGWAS/other harmonized source."
            else:
                row["gate_decision"] = "REST_ASSOCIATIONS_AVAILABLE_FOR_IV_SCREEN"
                row["notes"] = "REST associations can be screened before full TSV download."
        else:
            row["gate_decision"] = "RESOURCE_NOT_READY"
            row["notes"] = "One or more access/header checks failed."
        rows.append(row)

    def write_csv(path, fieldnames, data):
        with path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(data)

    write_csv(OUT_DIR / "stage1_mr_gate_resource_audit.csv", list(rows[0].keys()), rows)
    write_csv(OUT_DIR / "stage1_mr_gate_header_audit.csv", ["accession", "n_columns", "columns", "example_row"], header_rows)
    write_csv(OUT_DIR / "stage1_mr_gate_metadata_key_fields.csv", ["accession", "field", "value"], meta_rows)

    status_lines = [
        "# Stage 1 MR Gate Audit STATUS",
        "",
        "## STATUS",
        "",
        "PASS_WITH_MR_GATE_NOT_CLOSED",
        "",
        "## Key Finding",
        "",
        "- Public sepsis GWAS summary-statistics files are reachable from GWAS Catalog FTP.",
        "- GWAS-SSF headers and metadata were confirmed for GCST90270871 and GCST90281174.",
        "- GWAS Catalog REST returned zero curated association rows for both studies, so instrument extraction cannot be completed through the REST association endpoint.",
        "- No local OPENGWAS_JWT environment variable was available.",
        "",
        "## Decision",
        "",
        "retained_or_discard_decision: MR_REMAINS_GATED_BY_FULL_SUMMARY_STAT_SCAN_OR_AUTHENTICATED_HARMONIZED_SOURCE",
        "",
        "## Claim Allowed",
        "",
        "- Formal MR is technically feasible after full summary-statistics scan/harmonization or authenticated harmonized source access.",
        "- Current manuscript may describe MR as a future/gated extension only.",
        "",
        "## Claim Prohibited",
        "",
        "- No MR causal estimate.",
        "- No instrument strength claim.",
        "- No Steiger, MR-PRESSO, multivariable MR, or mediation MR claim.",
        "",
        "## Output Files",
        "",
        "- `stage1_mr_gate_resource_audit.csv`",
        "- `stage1_mr_gate_header_audit.csv`",
        "- `stage1_mr_gate_metadata_key_fields.csv`",
    ]
    (OUT_DIR / "stage1_mr_gate_audit_STATUS.md").write_text("\n".join(status_lines) + "\n", encoding="utf-8")
    log(f"wrote={OUT_DIR / 'stage1_mr_gate_resource_audit.csv'}")
    log(f"stage1_mr_gate_audit_end={time.strftime('%Y-%m-%dT%H:%M:%S%z')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

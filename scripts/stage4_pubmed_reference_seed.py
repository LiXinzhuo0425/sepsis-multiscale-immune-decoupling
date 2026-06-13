#!/usr/bin/env python3
import csv
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path("<PROJECT_ROOT>")
OUT_DIR = PROJECT_ROOT / "05_manuscript"
LOG_DIR = PROJECT_ROOT / "06_logs"
OUT_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / f"stage4_pubmed_reference_seed_{time.strftime('%Y%m%d_%H%M%S')}.log"

QUERIES = [
    ("sepsis_immune_paralysis_hla_dr", 'sepsis immunoparalysis monocyte HLA-DR'),
    ("sepsis_antigen_presentation_mhcii", 'sepsis antigen presentation MHC-II CD74 monocytes'),
    ("sepsis_transcriptomic_endotypes", 'sepsis transcriptomic endotypes immune suppression'),
    ("sepsis_single_cell", 'sepsis single cell RNA sequencing monocytes'),
    ("sepsis_mendelian_randomization_gwas", 'sepsis Mendelian randomization GWAS'),
    ("sepsis_immunometabolism_myeloid", 'sepsis immunometabolism myeloid inflammation transcriptomics'),
]


def log(msg):
    with LOG_FILE.open("a", encoding="utf-8") as fh:
        fh.write(msg + "\n")
    print(msg)


def get_json(url, timeout=30):
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def esearch(term, retmax=8):
    params = urllib.parse.urlencode({
        "db": "pubmed",
        "term": term,
        "retmode": "json",
        "retmax": retmax,
        "sort": "relevance",
    })
    url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?{params}"
    data = get_json(url)
    return data.get("esearchresult", {}).get("idlist", [])


def esummary(pmids):
    if not pmids:
        return {}
    params = urllib.parse.urlencode({
        "db": "pubmed",
        "id": ",".join(pmids),
        "retmode": "json",
    })
    url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?{params}"
    return get_json(url).get("result", {})


def extract_doi(articleids):
    for item in articleids or []:
        if item.get("idtype") == "doi":
            return item.get("value", "")
    return ""


def main():
    log(f"stage4_pubmed_reference_seed_start={time.strftime('%Y-%m-%dT%H:%M:%S%z')}")
    rows = []
    seen = set()
    for query_id, query in QUERIES:
        log(f"query={query_id}")
        pmids = esearch(query, retmax=8)
        time.sleep(0.4)
        summaries = esummary(pmids)
        time.sleep(0.4)
        for pmid in pmids:
            item = summaries.get(pmid, {})
            if not item or pmid in seen:
                continue
            seen.add(pmid)
            pubdate = item.get("pubdate", "")
            year = pubdate[:4] if pubdate else ""
            rows.append({
                "query_id": query_id,
                "query": query,
                "pmid": pmid,
                "year": year,
                "title": item.get("title", "").rstrip("."),
                "journal": item.get("fulljournalname", "") or item.get("source", ""),
                "authors": "; ".join([a.get("name", "") for a in item.get("authors", [])[:6]]),
                "doi": extract_doi(item.get("articleids", [])),
                "pubmed_url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                "use_in_manuscript": "candidate_reference_seed_needs_manual_curation",
            })

    csv_path = OUT_DIR / "reference_seed_list_v0.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        fieldnames = ["query_id", "query", "pmid", "year", "title", "journal", "authors", "doi", "pubmed_url", "use_in_manuscript"]
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    md_lines = [
        "# Reference Seed List v0",
        "",
        "Source: PubMed E-utilities query on 2026-06-12. This is a seed list for manual citation curation, not a final bibliography.",
        "",
    ]
    by_query = {}
    for row in rows:
        by_query.setdefault(row["query_id"], []).append(row)
    for query_id, items in by_query.items():
        md_lines.extend([f"## {query_id}", ""])
        for row in items[:8]:
            doi = f" doi: {row['doi']}." if row["doi"] else ""
            md_lines.append(f"- PMID {row['pmid']} ({row['year']}), {row['journal']}: {row['title']}.{doi} {row['pubmed_url']}")
        md_lines.append("")
    md_path = OUT_DIR / "reference_seed_list_v0.md"
    md_path.write_text("\n".join(md_lines), encoding="utf-8")

    log(f"references={len(rows)}")
    log(f"wrote={csv_path}")
    log(f"wrote={md_path}")
    log(f"stage4_pubmed_reference_seed_end={time.strftime('%Y-%m-%dT%H:%M:%S%z')}")


if __name__ == "__main__":
    main()

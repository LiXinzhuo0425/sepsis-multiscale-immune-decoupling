#!/usr/bin/env python3
"""Repair FI figure raster exports after detecting live-text font risk.

The user-approved desktop SVGs remain untouched. This script regenerates the
project-package copies so all upload and Word-embedded raster images are made
from text-to-path SVGs after stable font-name normalization.
"""

from __future__ import annotations

import csv
import json
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts import align_fi_manuscript_and_suppfigs_20260620 as supp
from scripts import finalize_fi_submission_20260620 as main


ROOT = main.ROOT
OUT = main.OUT
UPLOAD = main.UPLOAD
VECTOR = main.VECTOR
QA = main.QA


def write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str] | None = None) -> None:
    if fieldnames is None:
        fieldnames = []
        for row in rows:
            for key in row:
                if key not in fieldnames:
                    fieldnames.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def regenerate_main_figures() -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    figure_rows: list[dict[str, object]] = []
    qa_rows: list[dict[str, object]] = []
    previews: list[Path] = []

    with tempfile.TemporaryDirectory(prefix="fi_text_path_repair_") as tmp:
        tmpdir = Path(tmp)
        for spec in main.FIGURES:
            stats = main.svg_stats(spec.desktop_path)
            normalized = tmpdir / f"{spec.upload_stem}.normalized.svg"
            main.normalized_svg(spec.desktop_path, normalized, stats)

            export_dir = VECTOR / f"{spec.upload_stem}_canonical"
            export_dir.mkdir(parents=True, exist_ok=True)
            outputs = main.export_figure(spec, normalized, export_dir)
            main.mirror_outputs(spec, export_dir, outputs)
            main.copy_upload_files(spec, outputs)

            tiff = Path(outputs["tiff_600dpi"])
            pdf = Path(outputs["pdf"])
            outlined = Path(outputs["outlined_svg"])
            preview = Path(outputs["preview_png"])
            previews.append(UPLOAD / f"{spec.upload_stem}_preview.png")
            tinfo = main.tiff_info(tiff)
            outlined_text = main.outlined_text_count(outlined)
            qa = {
                "figure": spec.upload_stem,
                "desktop_source": str(spec.desktop_path),
                "title": spec.title,
                **stats,
                "pdf_page_size": main.pdf_page_size(pdf),
                "pdf_font_rows": main.pdf_font_rows(pdf),
                "outlined_svg_text_elements": outlined_text,
                "tiff_mode": tinfo["mode"],
                "tiff_width_px": tinfo["width_px"],
                "tiff_height_px": tinfo["height_px"],
                "tiff_dpi_x": tinfo["dpi_x"],
                "tiff_dpi_y": tinfo["dpi_y"],
                "preview_nonblank": main.image_nonblank(preview),
                "frontiers_min_dpi_pass": bool(
                    tinfo["mode"] == "RGB"
                    and (tinfo["dpi_x"] or 0) >= 300
                    and (tinfo["dpi_y"] or 0) >= 300
                ),
                "outlined_text_to_path_pass": outlined_text == 0,
                "embedded_raster_count": stats["image_elements"],
                "raster_export_source": "outlined_svg_after_font_normalization",
            }
            qa_rows.append(qa)
            for role, path_str in outputs.items():
                path = Path(path_str)
                figure_rows.append(
                    {
                        "figure": spec.upload_stem,
                        "role": role,
                        "path": main.rel(path),
                        "size_bytes": path.stat().st_size,
                        "sha256": main.sha256(path),
                    }
                )

    write_csv(QA / "figure_export_manifest.csv", figure_rows, ["figure", "role", "path", "size_bytes", "sha256"])
    write_csv(QA / "figure_QA_summary.csv", qa_rows)
    main.write_upload_figure_manifest()
    main.make_contact_sheet(previews)
    return figure_rows, qa_rows


def regenerate_supplementary_figures() -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    vector_rows, qa_rows = supp.export_supplementary_figures()
    for row in qa_rows:
        row["raster_export_source"] = "outlined_svg_after_text_to_path"
    write_csv(QA / "supplementary_figure_export_manifest.csv", vector_rows, ["asset", "role", "path", "size_bytes", "sha256"])
    write_csv(QA / "supplementary_figure_QA_summary.csv", qa_rows)
    supp.make_supp_contact_sheet()
    supp.update_media_manifest()
    return vector_rows, qa_rows


def update_final_report(main_qa: list[dict[str, object]], supp_qa: list[dict[str, object]]) -> None:
    report_path = QA / "final_QA_report.json"
    report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.exists() else {}
    report["updated_at"] = datetime.now().isoformat(timespec="seconds")
    report["figures"] = main_qa
    report["supplementary_figures"] = supp_qa
    report["font_rendering_risk_repair_20260622"] = {
        "reason": "Desktop SVGs contain live text with Illustrator/PostScript font names such as ArialMT and Arial-BoldMT.",
        "desktop_sources_modified": False,
        "project_svg_font_names_normalized": True,
        "main_raster_exports_from_outlined_svg": True,
        "supplementary_raster_exports_from_outlined_svg": True,
        "all_main_outlined_svgs_have_no_live_text": all(row["outlined_text_to_path_pass"] for row in main_qa),
        "all_supplementary_outlined_svgs_have_no_live_text": all(row["outlined_text_to_path_pass"] for row in supp_qa),
        "all_main_pdfs_have_no_live_fonts": all(row["pdf_font_rows"] == 0 for row in main_qa),
        "all_supplementary_pdfs_have_no_live_fonts": all(row["pdf_font_rows"] == 0 for row in supp_qa),
        "all_tiffs_rgb_600dpi": all(
            row["tiff_mode"] == "RGB"
            and float(row["tiff_dpi_x"]) >= 600
            and float(row["tiff_dpi_y"]) >= 600
            for row in [*main_qa, *supp_qa]
        ),
    }
    report.setdefault("frontiers_upload_checklist", {})
    report["frontiers_upload_checklist"].update(
        {
            "six_individual_tiff_files": all((UPLOAD / f"Figure_{i:02d}.tiff").exists() for i in range(1, 7)),
            "all_tiffs_rgb": all(row["tiff_mode"] == "RGB" for row in main_qa),
            "all_tiffs_at_least_300_dpi": all(row["frontiers_min_dpi_pass"] for row in main_qa),
            "outlined_svgs_have_no_live_text": all(row["outlined_text_to_path_pass"] for row in main_qa),
        }
    )
    report.setdefault("frontiers_upload_checklist_update", {})
    report["frontiers_upload_checklist_update"].update(
        {
            "two_supplementary_tiff_files_present": all((UPLOAD / f"{spec.stem}.tiff").exists() for spec in supp.SUPP_FIGS),
            "supplementary_tiffs_rgb": all(row["tiff_mode"] == "RGB" for row in supp_qa),
            "supplementary_tiffs_at_least_300_dpi": all(row["frontiers_min_dpi_pass"] for row in supp_qa),
            "supplementary_outlined_svgs_have_no_live_text": all(row["outlined_text_to_path_pass"] for row in supp_qa),
        }
    )
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")


def main_cli() -> None:
    QA.mkdir(parents=True, exist_ok=True)
    UPLOAD.mkdir(parents=True, exist_ok=True)
    VECTOR.mkdir(parents=True, exist_ok=True)
    main_rows, main_qa = regenerate_main_figures()
    supp_rows, supp_qa = regenerate_supplementary_figures()
    update_final_report(main_qa, supp_qa)
    supp.write_package_manifest()
    print(
        json.dumps(
            {
                "main_figures_regenerated": len(main_qa),
                "supplementary_figures_regenerated": len(supp_qa),
                "main_vector_assets": len(main_rows),
                "supplementary_vector_assets": len(supp_rows),
                "all_main_outlined_no_live_text": all(row["outlined_text_to_path_pass"] for row in main_qa),
                "all_main_pdf_font_rows_zero": all(row["pdf_font_rows"] == 0 for row in main_qa),
                "all_tiffs_rgb_600dpi": all(
                    row["tiff_mode"] == "RGB"
                    and float(row["tiff_dpi_x"]) >= 600
                    and float(row["tiff_dpi_y"]) >= 600
                    for row in [*main_qa, *supp_qa]
                ),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main_cli()

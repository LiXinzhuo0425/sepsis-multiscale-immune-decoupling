# Code Availability

Analysis and provenance scripts are available in `scripts/`. The public release
copy removes local absolute paths and does not include target-journal formatting
builders, cover letters, or internal submission drafts.

The scripts were written for an audited local workflow. To rerun the full
analysis, update the placeholder roots in the scripts or adapt them to your own
public-data cache:

- `<PROJECT_ROOT>`
- `<READ_ONLY_TRANSCRIPTOMICS_REFERENCE_ROOT>`
- `<READ_ONLY_PRIOR_WORKFLOW_ROOT>`
- `<READ_ONLY_CYTOMETRY_REFERENCE_ROOT>`

The release is intended to support transparency, table/figure provenance, and
reviewer inspection. It should not be interpreted as a turnkey clinical model,
diagnostic pipeline, or restricted-data analysis package.

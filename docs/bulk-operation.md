# Bulk intake and corpus-derived investigation scope

## The operating model

The user supplies a consolidated collection. FULCRUM performs:

1. Inventory and hash files, inspect optional metadata, and report unsupported/invalid inputs.
2. Persist an intake manifest and claim files with leases through up to eight concurrent workers.
3. Preserve originals as immutable evidence; extract searchable passages or structured rows.
4. Organize explicit entity fields, imported subject/predicate/object assertions, citation URLs, scope fields, and date mentions.
5. Produce a scope report spanning every imported universe/topic/geography/period represented in the collection.
6. Prepare prioritized investigation packets and a deduplicated retrieval frontier from the corpus's own citations.
7. Run bounded public-source retrieval when initiated, then re-index and update scope.
8. Use ChatGPT to interpret source passages, resolve identities, classify unstructured topics, evaluate contradictions, and verify claims.

The acquisition and organization stages are mechanical. The system does not equate a row match or a large file count with verified historical knowledge. There is no built-in Rockefeller, Colorado, or other single-target scope.

## Collection preparation

Keep your existing subfolders and filenames. Point intake at a dedicated collection folder outside the operating database folder. Do not reorganize files one at a time for FULCRUM.

| Input | Extraction unit | Current assumptions |
| --- | --- | --- |
| CSV / TSV | Data row, preserving column names | First nonempty row is the header; comma/tab delimiter |
| XLSX | Sheet and data row | First nonempty row on each sheet is its header; formulas are preserved, never executed; cached values used when present |
| JSON | Object or array element | Object keys preserved as fields; nested objects remain JSON text |
| JSONL | Object per nonblank line | Each line must be valid JSON |
| PDF | Page/chunk | Text extraction; scanned pages need a separate OCR stage |
| DOCX | Paragraph | Text from the main document body, including table-cell paragraphs; no semantic table reconstruction |
| HTML | Visible-text chunks and outbound-link list | Scripts/styles excluded; no JavaScript execution |
| TXT / Markdown | Text chunk | UTF-8 or BOM-marked UTF-16; original bytes retained |

ZIP, legacy DOC/XLS, images, audio, and video are reported as unsupported rather than silently imported as searchable evidence. Office files exceeding 512 MiB expanded size, XLSX sheets exceeding 512 columns, files above 128 MiB, and excessively large extracted documents are reported for splitting or conversion. No extraction is advertised as OCR. PDF pages without a text layer may require a separate completeness review even if other pages contain text.

Optional metadata lives beside a file, named `filename.ext.fulcrum.json`:

```json
{
  "title": "Existing source title",
  "source_url": "https://archive.example.org/source",
  "source_type": "primary_source",
  "universe": ["Science", "Education"],
  "geography": ["Europe"],
  "column_map": {
    "Historical Person": "person",
    "Research Branch": "universe",
    "From Entity": "subject",
    "Relationship": "predicate",
    "To Entity": "object"
  }
}
```

Metadata is optional and records source declarations, not independent verification. It allows heterogeneous existing records to be mapped without rewriting the originals. No URL means source identity falls back to the file content hash; therefore source-level independence cannot be inferred from file count alone.

## Commands

```powershell
# Preview only: no research records imported.
.\scripts\fulcrum.ps1 --output data/reports/inventory.json intake-plan 'D:\Research collection'

# Execute an entire batch and save the result.
.\scripts\fulcrum.ps1 --output data/reports/intake.json intake 'D:\Research collection' --collection 'Main corpus' --workers 4

# Resume by the BAT-... ID from the intake report.
.\scripts\fulcrum.ps1 resume-intake BAT_ID --workers 4
.\scripts\fulcrum.ps1 batch-status BAT_ID

# Build the broad work plan from this collection's current indexed contents.
.\scripts\fulcrum.ps1 --output data/reports/production.json production-plan 'Main corpus'
.\scripts\fulcrum.ps1 investigation-packet INV_ID
.\scripts\fulcrum.ps1 scope 'Main corpus'
.\scripts\fulcrum.ps1 search 'search terms' --collection 'Main corpus'
.\scripts\fulcrum.ps1 document-units DOC_ID --offset 0 --limit 100
.\scripts\fulcrum.ps1 connections 'Main corpus' --limit 100

# Populate citation candidates without making network requests.
.\scripts\fulcrum.ps1 plan-retrieval 'Main corpus'

# Explicitly bounded public retrieval from those candidates.
.\scripts\fulcrum.ps1 --output data/reports/retrieval.json retrieve 'Main corpus' --allow-domain archive.example.org --max-items 100 --workers 4
```

The retrieval domain above is an example. Domains must be explicitly selected from the collection's citations. Retrieval does not search an external search engine automatically. ChatGPT can use the generated packets to discover additional source URLs; subsequent acquisitions can be added through the existing intake interfaces. No model API credentials or recurring schedules are installed.

## Scope awareness and connections

The report includes documents, indexed rows/passages, named nodes, relationship types, citation domains, rows with/without HTTP citations, corpus-defined scope dimensions, frequent candidate terms, and potentially conflicting dates. Priorities cover citation recovery, independent corroboration, identity verification, competing accounts, and scope classification.

Named nodes currently come from explicit structured fields, including mapped fields. Unstructured prose is searchable and contributes date mentions and frequent-term hints; it does not undergo automatic semantic entity extraction or reliable topic classification. ChatGPT receives bounded source samples and can retrieve full records for that reasoning stage. This is a deliberate boundary between deterministic processing and reasoning.

Subject/predicate/object rows produce `explicit_import` edges. Multiple named fields in one row produce `same_record` edges. Both remain `UNREVIEWED`. Name matching is candidate grouping, not a verified identity merge. Repeated birth/death/founding values can flag candidate conflicts, including false positives from ambiguous identities or different date precision; no competing value is overwritten.

Preserved versions remain in the collection and report counts. Multiple copies, revisions, files, or URLs do not establish independent sources. The report describes coverage of the imported material, not a percentage of all history or an assertion that the corpus is complete.

## Reliability and throughput

Repeated identical folder manifests resume the same batch. Completed items are skipped. Changed files create new captures while existing evidence remains intact. A changed file after planning fails its fingerprint check. Leases expire after one hour; a new run recovers expired items. Three unsuccessful attempts leave the item failed for investigation. Parser failures publish no partial document index; the preserved raw evidence may still exist.

Retrieval limits concurrency, file count, bytes, request timeouts, and per-domain pacing. Robots rules are checked. Access denials, rate limits, credentials, and cross-domain redirects are reported for supervised acquisition; the worker does not use Edge cookies or bypass access controls. Private, loopback, link-local, and reserved destinations are rejected. Retrieval is at-least-once and content-addressed ingestion is idempotent.

The automated load fixture contains 10,000 structured rows across ten CSV files and twelve distinct scopes. It verifies counts, search, entity organization, and scope retention. This measures structured local ingestion, not PDF OCR, web throughput, or semantic reasoning speed. Real production throughput depends on file types, sizes, hardware, and source limits.

No user corpus has to be loaded to prepare this machinery. The actual intake starts only when the consolidated collection is ready.

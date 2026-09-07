# FULCRUM

## Scheduled reasoning (v0.3)

Use the included Codex task scheduler to run the research coordinator without a separate paid model API. Local workers perform bulk intake and retrieval; scheduled turns interpret evidence and checkpoint results into SQLite. See [scheduled operation](docs/scheduled-operation.md) for the runbook, commands, limits, and pause/resume behavior. The app schedule is configured separately and stays paused until the user's consolidated collection is ready.

Local-first research operations with SQLite state, immutable evidence, deterministic workers, and explicit reasoning reviews.

**Primary workflow: bulk collection intake.** Gather the material into a folder. FULCRUM inventories it, imports it as a resumable batch, indexes document passages and structured rows, derives scope from the collection, and prepares retrieval and reasoning work across multiple areas. No default historical subject is baked in. Edge Capture remains available for occasional additions.

## Bulk operation

```powershell
.\scripts\fulcrum.ps1 intake-plan 'D:\Research collection'
.\scripts\fulcrum.ps1 --output data/reports/intake.json intake 'D:\Research collection' --collection 'Main corpus' --workers 4
.\scripts\fulcrum.ps1 --output data/reports/production-plan.json production-plan 'Main corpus'
.\scripts\fulcrum.ps1 search 'search terms' --collection 'Main corpus'
```

The folder above is an example. Use the actual consolidated collection. Supported inputs: PDF with readable text, DOCX, XLSX, CSV, TSV, JSON, JSONL, HTML, Markdown, and UTF-8/UTF-16 text. Originals remain unchanged. Optional `.fulcrum.json` sidecars preserve source URLs and declare column mappings. See [bulk intake and scope planning](docs/bulk-operation.md) for format assumptions, resume commands, retrieval, and limits.

## Architecture

Edge selection / local file → intake → SHA-256 + provenance + deduplication → SQLite + local evidence spool → Google Drive evidence vault.

ChatGPT receives evidence packets for reasoning and verification. Local workers handle mechanical operations only. No model API, API key, cloud database, or paid service is required. The bulk document parsers use pypdf and openpyxl, pinned in requirements.txt.

The authoritative codebase is [lexluethor023-maker/FULCRUM](https://github.com/lexluethor023-maker/FULCRUM). Keep the checkout and live SQLite database outside Google Drive and OneDrive. The Drive folder receives immutable evidence and consistent database snapshots, never the live database.

## Start on Windows

Python 3.12+ is required. The setup script installs the pinned document parsers in the project virtual environment.

```powershell
# From this checkout; provide the full Python path if it is not on PATH.
.\scripts\setup.ps1 -Python python
.\scripts\fulcrum.ps1 doctor
.\scripts\fulcrum.ps1 serve
```

The intake service binds only to `127.0.0.1:8745`. [Health check](http://127.0.0.1:8745/health) is public on loopback; all evidence endpoints require a local bearer token. Stop the foreground service with Ctrl+C. The scripts resolve paths relative to the checkout, regardless of your starting folder. If PowerShell script execution is restricted, use `.venv\Scripts\python.exe -m app` with the same arguments from the checkout.

`init` creates `config/local.json` with a random pairing token. Keep this file private; it is ignored by Git. Initialization is repeatable and does not reset evidence. The virtual environment depends on its base Python installation, which must remain installed.

## First capture

1. In a dedicated FULCRUM Edge profile, open `edge://extensions`, enable Developer mode, and load this repository's `edge` folder as an unpacked extension.
2. Copy its 32-letter extension ID and run `.\scripts\fulcrum.ps1 pair-edge EXTENSION_ID`.
3. Restart the intake service. Open the extension popup and save the token from your local configuration in **Connect to local FULCRUM**. The token is stored only in that profile's local extension storage.
4. Open an HTTP(S) source page, select a passage, enter a citation location, and click **Capture selection**.
5. A successful popup reports **verified locally** only after a separate API readback matches the exact selected text and hash. Repeating a capture returns the same record. Cloud archival is separate.

The extension captures the main frame selection. Built-in PDF viewers, restricted browser pages, cross-origin frames, and pages that prohibit extension scripting are outside this first version. It does not automatically browse, click third-party actions, or ingest an entire page. Capture browser fragments and citation locators to retain location context.

For manual intake, create a UTF-8 JSON file:

```json
{
  "url": "https://example.org/report#page=2",
  "title": "Report title",
  "text": "The exact passage, preserving spacing and newlines.",
  "locator": "page 2",
  "acquired_via": "manual"
}
```

```powershell
.\scripts\fulcrum.ps1 capture C:\path\to\capture.json
.\scripts\fulcrum.ps1 list
.\scripts\fulcrum.ps1 get CAP_ID
.\scripts\fulcrum.ps1 import-file C:\path\to\source.pdf --url https://example.org/source.pdf
```

Browser text intake is limited to 4 MiB per item; file intake supports up to 128 MiB. The individual `import-file` command stores exact bytes and provenance. The bulk `intake` command additionally extracts and indexes supported formats. Neither command automatically verifies historical assertions.

## Drive evidence and backups

Install/sign in to Google Drive for desktop separately, then choose an existing synced FULCRUM folder outside this checkout. Existing archives are preserved; the worker uses content-addressed filenames.

```powershell
.\scripts\fulcrum.ps1 configure-drive 'G:\My Drive\FULCRUM'
.\scripts\fulcrum.ps1 worker
.\scripts\fulcrum.ps1 backup
```

The path above is an example, not an assumed location. A worker invocation processes at most one eligible archival job. With no configured Drive folder, it reports blocked without consuming retries. It reads back destination bytes before recording `staged_locally`. This means the file reached the local synced folder; **it does not prove Google Drive finished uploading it**. Cloud file IDs and remote verification timestamps are reserved for a future connected Drive reconciliation step. Drive scanning/import and cloud confirmation are not implemented yet.

Snapshots use SQLite's backup API and pass integrity and foreign-key checks. A SHA-256 manifest accompanies each snapshot. A database snapshot does not contain evidence blobs; retain the source vault as well. No scheduled job, recurring automation, or background worker is installed automatically.

## Reasoning and verification

```powershell
.\scripts\fulcrum.ps1 claim CAP_ID 'Candidate statement' --entity-name 'Person name'
.\scripts\fulcrum.ps1 packet CLM_ID
.\scripts\fulcrum.ps1 review CLM_ID CONFLICT 'Explain the competing evidence' --reviewer 'Reviewer name'
```

Claims are immutable and begin `OPEN`. Each review appends a verdict, reviewer, rationale, and timestamp; it never silently replaces a competing account. Packets preserve the original claim and every review rather than selecting a consensus automatically. The reasoning queue is reserved for supervised work; the mechanical worker never processes it. This foundation provides the handoff format, not an autonomous ChatGPT integration. Entity IDs are unique; name matching and identity merges require later explicit reconciliation. Relationships have a schema but no authoring interface yet.

## Verification

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -v
node --test tests/edge.test.cjs
.\scripts\fulcrum.ps1 doctor
```

Python tests use isolated temporary databases and real loopback HTTP sockets. They cover byte preservation, concurrent deduplication, corruption detection, transactions, append-only records, stale leases, dead-letter retries, Drive staging, snapshot readback, input validation, authentication, hostile browser origins, schema upgrades, batch resume, mixed file parsing, collection isolation, scope derivation, and a 10,000-record load check. Public retrieval is exercised with controlled responses and address/domain guards; tests do not crawl real websites. The optional Node tests exercise extension success/failure behavior with mocked browser APIs.

## Project layout

| Location | Purpose |
| --- | --- |
| `app/` | SQLite schema, intake, CLI, jobs, backups, reasoning packets |
| `edge/` | Manifest V3 capture extension |
| `scripts/` | Repeatable Windows setup and launcher |
| `tests/` | Isolated core, HTTP, and extension checks |
| `config/example.json` | Public configuration shape |
| `config/local.json` | Private runtime settings and pairing token; ignored |
| `database/` | Local operating database; ignored |
| `data/evidence/` | Content-addressed local evidence spool; ignored |
| `backups/` | Verified snapshots and manifests; ignored |
| `docs/` | Architecture, recovery, build scope |

See [architecture and next milestones](docs/architecture.md) and [recovery](docs/recovery.md).

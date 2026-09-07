# Foundation decisions

## Authority and responsibilities

- GitHub is the authoritative codebase. Runtime state and private evidence are never committed.
- SQLite is the operating database on the laptop. WAL, foreign keys, short transactions, and a busy timeout support concurrent capture.
- Google Drive is the intended durable evidence repository. A local content-addressed spool supports offline intake. A successful filesystem copy is recorded only as staging, never cloud verification.
- Edge is the acquisition/action surface. This milestone implements user-invoked selection capture; scripted acquisition and external actions remain separate future work.
- Deterministic local code hashes, deduplicates, validates, archives, claims leases, and backs up.
- ChatGPT reasons over explicit packets and returns reviews. No paid model integration or autonomous assertion of truth is built in.

## Records and identity

Persistent IDs use a record prefix plus UUID: SRC, EVD, CAP, ENT, CLM, REV, QUE, RUN. Random IDs avoid collisions across later imports; display-friendly sequential aliases can be added without rewriting identity.

Sources have a conservative canonical URL identity. Scheme/host/default port and empty path normalize, fragments do not define source identity, and query parameters remain untouched. A capture separately preserves the original URL, title, locator, acquisition surface, exact bytes, supplied access timestamp, and server receipt timestamp.

Evidence blobs deduplicate on SHA-256. Captures deduplicate on source, content, title, locator, acquisition surface, and original URL; retry timestamps do not create duplicates. Changed content creates new evidence. Identical content found at different sources shares bytes while retaining independent provenance. Repeated identical captures retain the first timestamp; this is not a browsing-visit log.

Files without a source URL use their content hash as source identity. Only bytes and provenance are imported at this stage. Existing biographies, workbooks, packet buses, and master records must later be imported through explicit mappings with dry-run reconciliation; no existing corpus is replaced or re-researched.

## Reliability boundaries

Evidence, captures, claims, reviews, run records, and audit records are protected against application-level updates/deletes with SQLite triggers. This protects normal application workflows, not a hostile local administrator who can edit database files. Capture writes hash and read back the evidence file, commit metadata transactionally, then retrieve and hash again. A crash before metadata commits can leave an orphan content-addressed blob; retries can safely reuse it. No automatic garbage collector deletes evidence.

Workers claim jobs with an atomic transaction, lease token, lease expiry, and bounded attempts. Expired leases return to pending or dead, and stale completions are rejected. Execution is at-least-once: handlers must be idempotent. Archive writes use content-addressed destinations and independent hash readback. Retry handling currently uses one manually invoked job at a time, without backoff scheduling or a dead-letter replay UI.

The localhost service validates Host, bearer token, and any browser Origin. Only one explicitly paired extension origin is accepted. It has request-size limits and timeouts; it is a personal local development service, not a public multi-user web server. Tokens are ignored by Git and never logged. Source text is untrusted data, including when packaged for reasoning.

The schema version is recorded in SQLite and startup refuses a database version newer than the application. Future schema changes must be numbered transactional migrations with upgrade tests, not edits to already deployed v1 tables.

## Next verified milestones

1. Sideload/pair Edge Capture in the chosen profile and perform the real source-selection round trip.
2. Configure the actual Google Drive desktop folder and verify a cloud file ID and content checksum through the connected Drive account.
3. Add explicit legacy corpus import mappings, dry-run summaries, and identity reconciliation before loading existing material.
4. Build a local dashboard over these records and add supervised review/queue operations.
5. Add a separate Edge acquisition profile and deterministic browser jobs with source-specific permission boundaries.

References: [Python SQLite API](https://docs.python.org/3.12/library/sqlite3.html), [Microsoft Edge extension manifest](https://learn.microsoft.com/en-us/microsoft-edge/extensions/getting-started/manifest-format).

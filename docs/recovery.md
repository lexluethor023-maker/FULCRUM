# Recovery and operation

Run `scripts\fulcrum.ps1 doctor` before and after an import batch. A healthy report verifies SQLite integrity, foreign keys, and every registered local evidence hash. It also reports queued jobs and whether Drive and Edge pairing are configured. Configuration is not proof of a running sync client or installed extension.

Run `scripts\fulcrum.ps1 backup` before schema upgrades or significant imports. Backups are consistent SQLite snapshots, even in WAL mode. Retain the adjacent JSON hash manifest and evidence vault. Never copy only the live `.db` file while the server is writing, and never place its `.db`, `-wal`, or `-shm` files in a sync folder.

To recover, stop the intake service and workers first. Preserve the current database folder intact for investigation. Verify the selected backup's SHA-256 against its manifest and run SQLite `PRAGMA integrity_check` and `PRAGMA foreign_key_check`. Restore the selected snapshot as `database/FULCRUM_Master.db` into a fresh recovery root, alongside `config/local.json` and the corresponding `data/evidence/` tree. Do not reuse WAL/SHM files from the previous database. Run `python -m app --root RECOVERY_ROOT doctor` against that explicit recovery root before switching operations. The automated suite checks snapshot reopening and row readback; it does not automatically restore over a live database.

If an evidence hash fails, preserve both the suspect file and the known good copy. Investigate provenance and restore the exact expected bytes from the vault. The application refuses to overwrite a conflicting evidence file. Do not change a stored hash to make a corrupt file appear valid.

If a worker crashes, the next claim recovers an expired lease. After three unsuccessful claims the job becomes dead. Keep its run history and investigate the cause before implementing an explicit replay action. An absent Drive configuration blocks archival without consuming retries.

The supplied worker and backup commands are manual. A later scheduler must prevent overlapping runs, preserve the same lease rules, and expose failures. No scheduled automation is installed by this foundation.

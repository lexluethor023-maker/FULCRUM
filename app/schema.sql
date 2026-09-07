BEGIN IMMEDIATE;
CREATE TABLE IF NOT EXISTS schema_migrations(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sources(
 id TEXT PRIMARY KEY, identity TEXT NOT NULL UNIQUE, url TEXT, title TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS evidence(
 id TEXT PRIMARY KEY, sha256 TEXT NOT NULL UNIQUE CHECK(length(sha256)=64),
 byte_size INTEGER NOT NULL CHECK(byte_size>=0), local_path TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS captures(
 id TEXT PRIMARY KEY, source_id TEXT NOT NULL REFERENCES sources(id),
 evidence_id TEXT NOT NULL REFERENCES evidence(id), capture_key TEXT NOT NULL UNIQUE,
 title TEXT NOT NULL, locator TEXT NOT NULL, original_url TEXT, acquired_via TEXT NOT NULL,
 captured_at TEXT NOT NULL, recorded_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS entities(
 id TEXT PRIMARY KEY, kind TEXT NOT NULL, name TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS claims(
 id TEXT PRIMARY KEY, entity_id TEXT REFERENCES entities(id), capture_id TEXT NOT NULL REFERENCES captures(id),
 statement TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'OPEN'
 CHECK(status IN ('OPEN','VERIFIED','INFERENCE','HYPOTHESIS','ALLEGATION','CONFLICT')), created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS relationships(
 id TEXT PRIMARY KEY, subject_id TEXT NOT NULL REFERENCES entities(id), predicate TEXT NOT NULL,
 object_id TEXT NOT NULL REFERENCES entities(id), claim_id TEXT NOT NULL REFERENCES claims(id), created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS reviews(
 id TEXT PRIMARY KEY, claim_id TEXT NOT NULL REFERENCES claims(id), verdict TEXT NOT NULL
 CHECK(verdict IN ('OPEN','VERIFIED','INFERENCE','HYPOTHESIS','ALLEGATION','CONFLICT')),
 rationale TEXT NOT NULL, reviewer TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS jobs(
 id TEXT PRIMARY KEY, kind TEXT NOT NULL, payload TEXT NOT NULL, dedup_key TEXT NOT NULL UNIQUE,
 status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','running','done','dead')),
 attempts INTEGER NOT NULL DEFAULT 0, max_attempts INTEGER NOT NULL DEFAULT 3 CHECK(max_attempts>0),
 lease_token TEXT, lease_until REAL, last_error TEXT, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS jobs_eligible ON jobs(status,created_at);
CREATE TABLE IF NOT EXISTS runs(
 id TEXT PRIMARY KEY, job_id TEXT NOT NULL REFERENCES jobs(id), lease_token TEXT NOT NULL,
 outcome TEXT NOT NULL, detail TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit(
 id INTEGER PRIMARY KEY, event TEXT NOT NULL, record_id TEXT NOT NULL, detail TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS evidence_locations(
 evidence_id TEXT PRIMARY KEY REFERENCES evidence(id), staged_path TEXT NOT NULL,
 staged_at TEXT NOT NULL, drive_file_id TEXT, cloud_verified_at TEXT
);
CREATE TRIGGER IF NOT EXISTS evidence_no_update BEFORE UPDATE ON evidence BEGIN SELECT RAISE(ABORT,'immutable evidence'); END;
CREATE TRIGGER IF NOT EXISTS evidence_no_delete BEFORE DELETE ON evidence BEGIN SELECT RAISE(ABORT,'immutable evidence'); END;
CREATE TRIGGER IF NOT EXISTS captures_no_update BEFORE UPDATE ON captures BEGIN SELECT RAISE(ABORT,'immutable capture'); END;
CREATE TRIGGER IF NOT EXISTS captures_no_delete BEFORE DELETE ON captures BEGIN SELECT RAISE(ABORT,'immutable capture'); END;
CREATE TRIGGER IF NOT EXISTS audit_no_update BEFORE UPDATE ON audit BEGIN SELECT RAISE(ABORT,'append-only audit'); END;
CREATE TRIGGER IF NOT EXISTS audit_no_delete BEFORE DELETE ON audit BEGIN SELECT RAISE(ABORT,'append-only audit'); END;
CREATE TRIGGER IF NOT EXISTS runs_no_update BEFORE UPDATE ON runs BEGIN SELECT RAISE(ABORT,'append-only runs'); END;
CREATE TRIGGER IF NOT EXISTS runs_no_delete BEFORE DELETE ON runs BEGIN SELECT RAISE(ABORT,'append-only runs'); END;
CREATE TRIGGER IF NOT EXISTS reviews_no_update BEFORE UPDATE ON reviews BEGIN SELECT RAISE(ABORT,'append-only reviews'); END;
CREATE TRIGGER IF NOT EXISTS reviews_no_delete BEFORE DELETE ON reviews BEGIN SELECT RAISE(ABORT,'append-only reviews'); END;
CREATE TRIGGER IF NOT EXISTS claims_no_update BEFORE UPDATE ON claims BEGIN SELECT RAISE(ABORT,'immutable claim; append a review'); END;
CREATE TRIGGER IF NOT EXISTS claims_no_delete BEFORE DELETE ON claims BEGIN SELECT RAISE(ABORT,'immutable claim'); END;
INSERT OR IGNORE INTO schema_migrations VALUES(1,strftime('%Y-%m-%dT%H:%M:%fZ','now'));
PRAGMA user_version=1;
COMMIT;

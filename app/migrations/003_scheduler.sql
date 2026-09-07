BEGIN IMMEDIATE;
CREATE TABLE scheduler_runs(
 id TEXT PRIMARY KEY, month TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN ('open','closed','expired')),
 started_at TEXT NOT NULL, lease_until REAL NOT NULL, finished_at TEXT, summary TEXT
);
CREATE UNIQUE INDEX scheduler_one_open ON scheduler_runs(status) WHERE status='open';
CREATE TABLE reasoning_work(
 id TEXT PRIMARY KEY, collection_id TEXT NOT NULL REFERENCES collections(id),
 work_key TEXT NOT NULL UNIQUE, kind TEXT NOT NULL, priority INTEGER NOT NULL, packet TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','running','done','superseded')),
 run_id TEXT REFERENCES scheduler_runs(id), created_at TEXT NOT NULL
);
CREATE INDEX reasoning_pending ON reasoning_work(status,priority,collection_id);
CREATE TABLE reasoning_results(
 id TEXT PRIMARY KEY, work_id TEXT NOT NULL UNIQUE REFERENCES reasoning_work(id),
 run_id TEXT NOT NULL REFERENCES scheduler_runs(id), result TEXT NOT NULL,
 result_hash TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TRIGGER reasoning_results_no_update BEFORE UPDATE ON reasoning_results BEGIN SELECT RAISE(ABORT,'Reasoning results are append-only'); END;
CREATE TRIGGER reasoning_results_no_delete BEFORE DELETE ON reasoning_results BEGIN SELECT RAISE(ABORT,'Reasoning results are append-only'); END;
CREATE TABLE research_followups(
 id TEXT PRIMARY KEY, collection_id TEXT NOT NULL REFERENCES collections(id),
 result_id TEXT NOT NULL REFERENCES reasoning_results(id), kind TEXT NOT NULL CHECK(kind IN ('scope','query','url')),
 payload TEXT NOT NULL, dedup_key TEXT NOT NULL UNIQUE,
 status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','done','blocked')),
 outcome TEXT, updated_at TEXT NOT NULL
);
INSERT INTO schema_migrations VALUES(3,strftime('%Y-%m-%dT%H:%M:%fZ','now'));
PRAGMA user_version=3;
COMMIT;

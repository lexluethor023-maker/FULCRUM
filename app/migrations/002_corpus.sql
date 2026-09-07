BEGIN IMMEDIATE;
CREATE TABLE collections(
 id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL
);
CREATE TABLE intake_batches(
 id TEXT PRIMARY KEY, collection_id TEXT NOT NULL REFERENCES collections(id),
 root_path TEXT NOT NULL, manifest_key TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL
);
CREATE TABLE intake_items(
 id TEXT PRIMARY KEY, batch_id TEXT NOT NULL REFERENCES intake_batches(id), relative_path TEXT NOT NULL,
 expected_sha256 TEXT NOT NULL, metadata TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending'
 CHECK(status IN ('pending','running','done','failed')), attempts INTEGER NOT NULL DEFAULT 0,
 lease_token TEXT, lease_until REAL, document_id TEXT, error TEXT, updated_at TEXT NOT NULL,
 UNIQUE(batch_id,relative_path)
);
CREATE INDEX intake_eligible ON intake_items(batch_id,status,attempts);
CREATE TABLE corpus_documents(
 id TEXT PRIMARY KEY, capture_id TEXT NOT NULL REFERENCES captures(id), parser_version TEXT NOT NULL,
 title TEXT NOT NULL, format TEXT NOT NULL, metadata TEXT NOT NULL, unit_count INTEGER NOT NULL,
 created_at TEXT NOT NULL, UNIQUE(capture_id,parser_version,metadata)
);
CREATE TABLE collection_documents(
 collection_id TEXT NOT NULL REFERENCES collections(id), document_id TEXT NOT NULL REFERENCES corpus_documents(id),
 PRIMARY KEY(collection_id,document_id)
);
CREATE TABLE corpus_units(
 id INTEGER PRIMARY KEY, document_id TEXT NOT NULL REFERENCES corpus_documents(id), ordinal INTEGER NOT NULL,
 locator TEXT NOT NULL, text TEXT NOT NULL, fields TEXT NOT NULL, UNIQUE(document_id,ordinal)
);
CREATE VIRTUAL TABLE corpus_fts USING fts5(text,content='corpus_units',content_rowid='id');
CREATE TRIGGER corpus_units_insert AFTER INSERT ON corpus_units BEGIN
 INSERT INTO corpus_fts(rowid,text) VALUES(new.id,new.text);
END;
CREATE TABLE corpus_nodes(
 id TEXT PRIMARY KEY, node_key TEXT NOT NULL UNIQUE, label TEXT NOT NULL, kind TEXT NOT NULL
);
CREATE TABLE node_mentions(
 node_id TEXT NOT NULL REFERENCES corpus_nodes(id), unit_id INTEGER NOT NULL REFERENCES corpus_units(id),
 field TEXT NOT NULL, PRIMARY KEY(node_id,unit_id,field)
);
CREATE TABLE corpus_edges(
 id TEXT PRIMARY KEY, subject_id TEXT NOT NULL REFERENCES corpus_nodes(id), predicate TEXT NOT NULL,
 object_id TEXT NOT NULL REFERENCES corpus_nodes(id), unit_id INTEGER NOT NULL REFERENCES corpus_units(id),
 basis TEXT NOT NULL CHECK(basis IN ('explicit_import','same_record')), status TEXT NOT NULL DEFAULT 'UNREVIEWED',
 UNIQUE(subject_id,predicate,object_id,unit_id,basis)
);
CREATE TABLE scope_mentions(
 unit_id INTEGER NOT NULL REFERENCES corpus_units(id), dimension TEXT NOT NULL, label TEXT NOT NULL,
 basis TEXT NOT NULL CHECK(basis IN ('explicit_field','declared_metadata','text_year')),
 PRIMARY KEY(unit_id,dimension,label)
);
CREATE TABLE citation_links(
 unit_id INTEGER NOT NULL REFERENCES corpus_units(id), url TEXT NOT NULL, PRIMARY KEY(unit_id,url)
);
CREATE TABLE corpus_conflicts(
 id TEXT PRIMARY KEY, node_id TEXT NOT NULL REFERENCES corpus_nodes(id), field TEXT NOT NULL,
 values_json TEXT NOT NULL, unit_ids_json TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'REVIEW',
 UNIQUE(node_id,field,values_json,unit_ids_json)
);
CREATE TABLE scope_snapshots(
 id TEXT PRIMARY KEY, collection_id TEXT NOT NULL REFERENCES collections(id),
 report TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE investigation_tasks(
 id TEXT PRIMARY KEY, collection_id TEXT NOT NULL REFERENCES collections(id), task_key TEXT NOT NULL UNIQUE,
 kind TEXT NOT NULL, subject TEXT NOT NULL, priority INTEGER NOT NULL,
 status TEXT NOT NULL DEFAULT 'pending', packet TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE retrieval_frontier(
 id TEXT PRIMARY KEY, collection_id TEXT NOT NULL REFERENCES collections(id), url TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'candidate' CHECK(status IN ('candidate','pending','running','done','failed','browser_required')),
 reason TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, capture_id TEXT REFERENCES captures(id), error TEXT,
 lease_token TEXT, lease_until REAL,
 UNIQUE(collection_id,url)
);
INSERT INTO schema_migrations VALUES(2,strftime('%Y-%m-%dT%H:%M:%fZ','now'));
PRAGMA user_version=2;
COMMIT;

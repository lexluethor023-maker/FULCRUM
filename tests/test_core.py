import concurrent.futures
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.core import Store, canonical_url


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / 'app'
        self.store = Store(self.root)
        self.store.initialize()
        self.payload = {'url': 'https://example.org/report#page=2', 'title': 'Report',
                        'text': 'Exact evidence — two  spaces\nSecond line.', 'locator': 'page 2'}

    def tearDown(self):
        self.temp.cleanup()

    def test_round_trip_dedup_changed_content_and_provenance(self):
        first = self.store.capture(self.payload)
        self.assertEqual(first['text'], self.payload['text'])
        self.assertEqual(first['original_url'], self.payload['url'])
        self.assertEqual(first['id'], self.store.capture(self.payload)['id'])
        second = self.store.capture({**self.payload, 'text': 'Changed'})
        other = self.store.capture({**self.payload, 'url': 'https://elsewhere.org/'})
        self.assertNotEqual(first['id'], second['id'])
        self.assertEqual(first['evidence_id'], other['evidence_id'])
        self.assertNotEqual(first['source_id'], other['source_id'])
        self.assertEqual(self.store.doctor()['counts']['evidence'], 2)

    def test_concurrent_capture_is_idempotent(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _: self.store.capture(self.payload), range(12)))
        self.assertEqual(len({r['id'] for r in results}), 1)
        self.assertEqual(self.store.doctor()['counts']['jobs'], 1)

    def test_transaction_rollback(self):
        with self.assertRaises(sqlite3.IntegrityError):
            with self.store.connection() as db:
                db.execute("INSERT INTO entities VALUES('ENT-test','person','Name','now')")
                db.execute("INSERT INTO claims VALUES('CLM-bad','ENT-test','CAP-missing','claim','OPEN','now')")
        self.assertEqual(self.store.doctor()['counts']['entities'], 0)

    def test_schema_idempotent_immutable_and_append_only(self):
        capture = self.store.capture(self.payload)
        self.store.initialize()
        claim = self.store.add_claim(capture['id'], 'Candidate claim')
        self.store.review_claim(claim['claim_id'], 'CONFLICT', 'A second account differs.', 'local reviewer')
        packet = self.store.packet(claim['claim_id'])
        self.assertEqual(packet['claim']['status'], 'OPEN')
        self.assertEqual(packet['reviews'][0]['verdict'], 'CONFLICT')
        for table in ('captures', 'evidence', 'audit', 'claims', 'reviews'):
            with self.subTest(table=table), self.assertRaises(sqlite3.IntegrityError):
                with self.store.connection() as db:
                    db.execute(f'DELETE FROM {table}')

    def test_hash_detects_corruption(self):
        capture = self.store.capture(self.payload)
        path = self.root / 'data/evidence' / capture['sha256'][:2] / capture['sha256']
        path.write_bytes(b'tampered')
        with self.assertRaises(ValueError):
            self.store.get_capture(capture['id'])
        with self.assertRaises(ValueError):
            self.store.capture(self.payload)
        self.assertFalse(self.store.doctor()['ok'])

    def test_jobs_lock_retry_dead_letter_and_stale_worker(self):
        self.store.capture(self.payload)
        first = self.store.claim_job()
        self.assertIsNone(self.store.claim_job())
        with self.store.connection() as db:
            db.execute('UPDATE jobs SET lease_until=0 WHERE id=?', (first['id'],))
        second = self.store.claim_job()
        with self.assertRaises(ValueError):
            self.store.finish_job(first)
        self.store.finish_job(second, 'simulated failure')
        third = self.store.claim_job()
        self.store.finish_job(third, 'simulated failure')
        self.assertIsNone(self.store.claim_job())
        self.assertEqual(self.store.doctor()['queue'], {'dead': 1})
        self.assertEqual(self.store.doctor()['counts']['runs'], 3)

    def test_unconfigured_drive_does_not_burn_retries(self):
        self.store.capture(self.payload)
        self.assertEqual(self.store.work_once()['state'], 'blocked')
        with self.store.connection() as db:
            self.assertEqual(db.execute('SELECT attempts FROM jobs').fetchone()[0], 0)

    def test_drive_stage_and_backup_restore(self):
        drive = Path(self.temp.name) / 'drive'
        drive.mkdir()
        settings = self.store.settings()
        settings['drive_root'] = str(drive)
        (self.root / 'config/local.json').write_text(json.dumps(settings), encoding='utf-8')
        capture = self.store.capture(self.payload)
        result = self.store.work_once()
        self.assertFalse(result['cloud_verified'])
        self.assertEqual(self.store.doctor()['queue'], {'done': 1})
        archived = drive / '02_SOURCE_VAULT' / capture['sha256'][:2] / capture['sha256']
        self.assertEqual(archived.read_text(encoding='utf-8'), self.payload['text'])
        backup = self.store.backup()
        db = sqlite3.connect(self.root / 'backups' / backup['file'])
        try:
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
            self.assertEqual(db.execute('SELECT count(*) FROM captures').fetchone()[0], 1)
        finally:
            db.close()
        self.assertEqual((drive / '01_DATABASE_BACKUPS' / backup['file']).read_bytes(),
                         (self.root / 'backups' / backup['file']).read_bytes())

    def test_file_import_preserves_bytes(self):
        path = Path(self.temp.name) / 'evidence.bin'
        raw = b'\x00\xff\x01binary'
        path.write_bytes(raw)
        first = self.store.import_file(path)
        self.assertEqual(first['byte_size'], len(raw))
        self.assertEqual(first['id'], self.store.import_file(path)['id'])

    def test_validation(self):
        for updates in ({'url': 'file:///secrets'}, {'url': 'https://user:pass@example.org/'},
                        {'text': ''}, {'text': 17}, {'captured_at': '2026-01-01'}, {'acquired_via': 'unknown'}):
            with self.subTest(updates=updates), self.assertRaises(ValueError):
                self.store.capture({**self.payload, **updates})
        self.assertEqual(canonical_url('https://EXAMPLE.org:443/a?b=2&a=1#section'), 'https://example.org/a?b=2&a=1')


if __name__ == '__main__':
    unittest.main()

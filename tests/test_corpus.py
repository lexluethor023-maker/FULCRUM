import csv
import json
import sqlite3
import tempfile
import time
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from app.core import Store
from app.corpus import Corpus
from app.parsers import extract
from app.retrieval import Retriever, validate_public_url


class CorpusTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.folder = self.base / 'collection'
        self.folder.mkdir()
        self.store = Store(self.base / 'runtime')
        self.store.initialize()
        self.corpus = Corpus(self.store)

    def tearDown(self):
        self.temp.cleanup()

    def fixture(self):
        (self.folder / 'people.csv').write_text(
            'person,organization,universe,birth_date,source_url\n'
            'Ada Example,Harbor College,Education,1800-01-01,https://example.org/a\n'
            'Ada Example,Harbor College,Education,1801-01-01,https://example.org/b\n'
            'Ben Example,Valley Bank,Finance,1820-01-01,\n', encoding='utf-8')
        (self.folder / 'connections.jsonl').write_text(json.dumps({'subject': 'Harbor College',
            'predicate': 'received grant from', 'object': 'Example Trust', 'topic': 'Philanthropy'}) + '\n', encoding='utf-8')
        (self.folder / 'notes.md').write_text('Regional history\n\nA discussion of transport and education in 1910.', encoding='utf-8')

    def test_inventory_bulk_scope_search_and_repeat(self):
        self.fixture()
        plan = self.corpus.plan_folder(self.folder)
        self.assertEqual(plan['file_count'], 3)
        self.assertEqual(self.store.doctor()['counts']['captures'], 0)
        batch = self.corpus.create_batch(self.folder, 'Whole collection')
        result = self.corpus.run_batch(batch)
        self.assertTrue(result['complete'])
        self.assertEqual(result['scope']['documents'], 3)
        self.assertEqual(result['scope']['records_or_passages'], 5)
        labels = {d['label'] for d in result['scope']['scope_dimensions']}
        self.assertTrue({'Education', 'Finance', 'Philanthropy'} <= labels)
        self.assertEqual(len(result['scope']['candidate_conflicts']), 1)
        self.assertTrue(self.corpus.search('Harbor College'))
        self.assertEqual(self.corpus.create_batch(self.folder, 'Whole collection'), batch)
        self.corpus.run_batch(batch)
        self.assertEqual(self.store.doctor()['counts']['captures'], 3)
        self.assertEqual(self.corpus.seed_frontier('Whole collection')['distinct_citation_urls'], 2)
        production = self.corpus.production_plan('Whole collection')
        self.assertGreater(len(production['investigation_tasks']), 3)
        count = len(production['investigation_tasks'])
        self.assertEqual(len(self.corpus.production_plan('Whole collection')['investigation_tasks']), count)
        packet = self.corpus.investigation_packet(production['investigation_tasks'][0]['id'])
        self.assertTrue(packet['packet']['evidence_sample'])
        edges = self.corpus.connections('Whole collection')
        self.assertTrue(any(x['basis'] == 'explicit_import' for x in edges))
        self.assertTrue(all(x['status'] == 'UNREVIEWED' for x in edges))
        missing_task = next(x for x in production['investigation_tasks'] if x['kind'] == 'citation_recovery')
        missing_packet = self.corpus.investigation_packet(missing_task['id'])
        self.assertTrue(all('https://' not in x['text'] for x in missing_packet['packet']['evidence_sample']))

    def test_resume_and_changed_file_preserve_old_evidence(self):
        self.fixture()
        batch = self.corpus.create_batch(self.folder, 'Archive')
        claimed = self.corpus._claim(batch)
        with self.store.connection() as db:
            db.execute('UPDATE intake_items SET lease_until=0 WHERE id=?', (claimed['id'],))
        self.assertTrue(self.corpus.run_batch(batch)['complete'])
        old_captures = self.store.doctor()['counts']['captures']
        (self.folder / 'notes.md').write_text('A new version with additional evidence.', encoding='utf-8')
        new_batch = self.corpus.create_batch(self.folder, 'Archive')
        self.assertNotEqual(batch, new_batch)
        result = self.corpus.run_batch(new_batch)
        self.assertTrue(result['complete'])
        self.assertEqual(self.store.doctor()['counts']['captures'], old_captures + 1)
        self.assertEqual(result['scope']['documents'], 4)

    def test_changed_after_manifest_and_invalid_json_are_reported(self):
        path = self.folder / 'bad.json'
        path.write_text('{broken', encoding='utf-8')
        batch = self.corpus.create_batch(self.folder, 'Bad input')
        result = self.corpus.run_batch(batch)
        self.assertFalse(result['complete'])
        self.assertEqual(result['scope']['records_or_passages'], 0)
        self.assertEqual(result['errors'][0]['attempts'], 3)
        path.write_text('{}', encoding='utf-8')
        changed_batch = self.corpus.create_batch(self.folder, 'Changed input')
        path.write_text('{"name":"Changed"}', encoding='utf-8')
        result = self.corpus.run_batch(changed_batch)
        self.assertIn('changed after planning', result['errors'][0]['error'])

    def test_sidecar_mapping_and_collection_isolation(self):
        path = self.folder / 'data.csv'
        path.write_text('Subject Full Name,Research Branch\nExample Person,Astronomy\n', encoding='utf-8')
        Path(str(path) + '.fulcrum.json').write_text(json.dumps({'column_map': {
            'Subject Full Name': 'person', 'Research Branch': 'universe'}, 'geography': ['Europe']}), encoding='utf-8')
        batch = self.corpus.create_batch(self.folder, 'Sky')
        result = self.corpus.run_batch(batch)
        self.assertEqual(result['scope']['named_nodes'], 1)
        self.assertIn('Astronomy', {x['label'] for x in result['scope']['scope_dimensions']})
        self.assertEqual(self.corpus.search('finance', 'Sky'), [])

    def test_parsers_xlsx_docx_json_csv_and_html(self):
        from openpyxl import Workbook
        book = Workbook()
        sheet = book.active
        sheet.title = 'Institutions'
        sheet.append(['name', 'topic'])
        sheet.append(['Example College', 'Education'])
        book.save(self.folder / 'table.xlsx')
        with zipfile.ZipFile(self.folder / 'text.docx', 'w') as archive:
            archive.writestr('word/document.xml', '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Original paragraph</w:t></w:r></w:p></w:body></w:document>')
        (self.folder / 'page.html').write_text('<h1>History</h1><script>do not index</script><p>Public evidence</p><a href="https://example.org/a">Source</a>', encoding='utf-8')
        (self.folder / 'rows.json').write_text('[{"name":"A"},{"name":"B"}]', encoding='utf-8')
        result = self.corpus.run_batch(self.corpus.create_batch(self.folder, 'Formats'))
        self.assertTrue(result['complete'])
        self.assertEqual(result['scope']['documents'], 4)
        self.assertFalse(self.corpus.search('do not index'))
        self.assertEqual(list(extract(self.folder / 'table.xlsx'))[0].locator, 'Institutions!row 2')

    def test_large_batch_10000_records(self):
        for file_number in range(10):
            with (self.folder / f'volume-{file_number}.csv').open('w', encoding='utf-8', newline='') as stream:
                writer = csv.writer(stream)
                writer.writerow(['entity_id', 'entity_name', 'universe', 'year', 'source_url'])
                writer.writerows((f'ID-{i}', f'Entity {i}', f'Domain {i % 12}', 1800 + i % 200, f'https://example.org/source/{i}')
                                for i in range(file_number * 1000, (file_number + 1) * 1000))
        started = time.monotonic()
        result = self.corpus.run_batch(self.corpus.create_batch(self.folder, 'Load check'), workers=4)
        self.assertTrue(result['complete'])
        self.assertEqual(result['scope']['records_or_passages'], 10000)
        self.assertEqual(result['scope']['named_nodes'], 10000)
        self.assertEqual(len([x for x in result['scope']['scope_dimensions'] if x['dimension'] == 'universe']), 12)
        self.assertEqual(result['scope']['records_with_url'], 10000)
        print(f'\nBulk verification: 10,000 records, 12 scopes, {time.monotonic() - started:.2f}s')

    def test_public_retrieval_guards_and_mocked_bulk(self):
        public_dns = [(2, 1, 6, '', ('93.184.216.34', 443))]
        with patch('socket.getaddrinfo', return_value=public_dns):
            self.assertEqual(validate_public_url('https://example.org/a', {'example.org'}), 'https://example.org/a')
            with self.assertRaises(ValueError):
                validate_public_url('https://other.example/a', {'example.org'})
            with self.assertRaises(ValueError):
                validate_public_url('https://example.org/?access_token=secret', {'example.org'})
        with patch('socket.getaddrinfo', return_value=[(2, 1, 6, '', ('127.0.0.1', 80))]):
            with self.assertRaises(ValueError):
                validate_public_url('http://example.org/', {'example.org'})
        self.fixture()
        self.corpus.run_batch(self.corpus.create_batch(self.folder, 'Retrieval'))
        self.corpus.seed_frontier('Retrieval')
        retriever = Retriever(self.corpus, ['example.org'])
        def fake_read(url, limit=None):
            if url.endswith('/robots.txt'):
                return b'User-agent: *\nAllow: /', 'text/plain', url
            return b'<h1>Retrieved original</h1><p>Local test response.</p>', 'text/html', url
        with patch('socket.getaddrinfo', return_value=public_dns), patch.object(retriever, '_read', side_effect=fake_read):
            result = retriever.run('Retrieval', max_items=2)
        self.assertEqual(result['attempted'], 2)
        self.assertTrue(all(x['status'] == 'done' for x in result['results']))
        self.assertTrue(self.corpus.search('Retrieved original'))
        self.assertEqual(retriever.run('Retrieval', max_items=2)['attempted'], 0)

    def test_scanned_pdf_and_unsupported_files_are_visible(self):
        from pypdf import PdfWriter
        writer = PdfWriter()
        writer.add_blank_page(width=100, height=100)
        writer.write(self.folder / 'scan.pdf')
        (self.folder / 'unsupported.bin').write_bytes(b'bytes')
        plan = self.corpus.plan_folder(self.folder)
        self.assertEqual(len(plan['skipped']), 1)
        result = self.corpus.run_batch(self.corpus.create_batch(self.folder, 'Scans'))
        self.assertFalse(result['complete'])
        self.assertIn('require OCR', result['errors'][0]['error'])
        self.assertEqual(len(result['skipped']), 1)

    def test_invalid_sidecar_and_operating_root_are_rejected(self):
        (self.folder / 'text.txt').write_text('Evidence', encoding='utf-8')
        (self.folder / 'text.txt.fulcrum.json').write_text('[]', encoding='utf-8')
        self.assertEqual(len(self.corpus.plan_folder(self.folder)['errors']), 1)
        with self.assertRaises(ValueError):
            self.corpus.create_batch(self.folder, 'Invalid')
        with self.assertRaises(ValueError):
            self.corpus.plan_folder(self.store.root)


class MigrationTests(unittest.TestCase):
    def test_v1_upgrade_preserves_capture_and_repeated_initialization(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'database').mkdir()
            store = Store(root)
            with store.connection() as db:
                db.executescript((Path(__file__).parents[1] / 'app/schema.sql').read_text(encoding='utf-8'))
            capture = store.capture({'url': 'https://example.org/old', 'title': 'Existing evidence', 'text': 'Keep exact original.'})
            self.assertEqual(store.initialize()['schema_version'], 3)
            self.assertEqual(store.initialize()['counts']['captures'], 1)
            self.assertEqual(store.get_capture(capture['id'])['text'], 'Keep exact original.')


if __name__ == '__main__':
    unittest.main()

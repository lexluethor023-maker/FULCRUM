import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from app.core import Store
from app.corpus import Corpus
from app.coordinator import Coordinator


class CoordinatorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = Store(self.root / 'runtime')
        self.store.initialize()
        self.coordinator = Coordinator(self.store)
        self.corpus = Corpus(self.store)

    def tearDown(self):
        self.temp.cleanup()

    def seed(self, name='Collection'):
        folder = self.root / name
        folder.mkdir(exist_ok=True)
        (folder / 'evidence.json').write_text(json.dumps([
            {'person':'Ada Example','topic':'Education','notes':'College teaching in 1900 ' + name},
            {'person':'Ben Example','topic':'Transport','notes':'Rail expansion in 1901'}]), encoding='utf-8')
        self.corpus.run_batch(self.corpus.create_batch(folder, name))
        return folder

    def answer(self, packet):
        unit = packet['packet']['evidence_sample'][0]['id']
        return {'summary':'Examined the supplied passages; independent corroboration remains outstanding.',
                'findings':[{'statement':'The collection discusses institutions.', 'basis':'inference','unit_ids':[unit]}],
                'scope_areas':[{'title':'Institutional development','rationale':'Institutions occur in the cited material.','unit_ids':[unit]}],
                'next_queries':[{'query':'institutional development archival records','rationale':'Find independent corroboration.','unit_ids':[unit]}],
                'source_urls':[{'url':'https://example.org/archive','rationale':'Synthetic test candidate.','unit_ids':[unit]}]}

    def test_empty_collection_does_not_consume_local_run_budget(self):
        self.assertEqual(self.coordinator.start()['state'], 'awaiting_collection')
        self.assertEqual(self.coordinator.status()['local_runs_started'], 0)

    def test_batch_checkpoint_followup_and_unchanged_work(self):
        self.seed()
        run = self.coordinator.start()['run_id']
        packets = self.coordinator.next(run)['packets']
        self.assertGreater(len(packets), 1)
        self.assertTrue(any(p['kind'] == 'broad_scope_scan' for p in packets))
        for p in packets:
            result = self.answer(p)
            self.coordinator.complete(run, p['id'], result)
            self.assertTrue(self.coordinator.complete(run, p['id'], result)['deduplicated'])
        self.coordinator.finish(run, 'Fixture review complete.')
        second = self.coordinator.start()['run_id']
        self.assertEqual(self.coordinator.next(second)['state'], 'idle')
        self.coordinator.finish(second, 'No new reasoning work.')
        followups = self.coordinator.followups()
        self.assertEqual({f['kind'] for f in followups}, {'scope','query','url'})
        self.coordinator.resolve_followup(followups[0]['id'],'done','Reviewed test follow-up.')
        self.assertEqual(len(self.coordinator.followups()), len(followups)-1)
        self.assertTrue(self.coordinator.report()['proposed_scope_areas'])
        with self.store.connection() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM retrieval_frontier WHERE url='https://example.org/archive'").fetchone()[0],1)

    def test_foreign_or_fabricated_evidence_is_rejected_atomically(self):
        self.seed('First')
        self.seed('Second')
        run = self.coordinator.start()['run_id']
        packet = self.coordinator.next(run,1)['packets'][0]
        bad = self.answer(packet)
        bad['scope_areas'][0]['unit_ids'] = [999999]
        with self.assertRaises(ValueError):
            self.coordinator.complete(run, packet['id'], bad)
        with self.store.connection() as db:
            foreign = db.execute('''SELECT u.id FROM corpus_units u JOIN collection_documents cd
                ON cd.document_id=u.document_id WHERE cd.collection_id<>? LIMIT 1''',(packet['collection_id'],)).fetchone()[0]
        bad['scope_areas'][0]['unit_ids'] = [foreign]
        with self.assertRaises(ValueError):
            self.coordinator.complete(run, packet['id'], bad)
        self.assertFalse(self.coordinator.report()['recent_results'])
        self.assertFalse(self.coordinator.followups())

    def test_expired_and_overlapping_runs_preserve_checkpoints(self):
        self.seed()
        run = self.coordinator.start()['run_id']
        packets = self.coordinator.next(run)['packets']
        self.coordinator.complete(run,packets[0]['id'],self.answer(packets[0]))
        self.assertEqual(self.coordinator.start()['state'],'busy')
        with self.store.connection() as db:
            db.execute('UPDATE scheduler_runs SET lease_until=0 WHERE id=?',(run,))
        replacement = self.coordinator.start()['run_id']
        recovered = self.coordinator.next(replacement)['packets']
        self.assertNotIn(packets[0]['id'], {p['id'] for p in recovered})
        self.assertIn(packets[1]['id'], {p['id'] for p in recovered})
        with self.assertRaises(ValueError):
            self.coordinator.complete(run,packets[1]['id'],self.answer(packets[1]))

    def test_new_evidence_gets_new_work_without_overwriting_results(self):
        folder = self.seed()
        run = self.coordinator.start()['run_id']
        packets = self.coordinator.next(run)['packets']
        for p in packets:
            self.coordinator.complete(run,p['id'],self.answer(p))
        self.coordinator.finish(run,'Saved first generation.')
        (folder/'new.txt').write_text('A new investigation area: agricultural history in 1850.',encoding='utf-8')
        self.corpus.run_batch(self.corpus.create_batch(folder,'Collection'))
        run2 = self.coordinator.start()['run_id']
        self.assertEqual(self.coordinator.next(run2)['state'],'work')
        self.assertEqual(len(self.coordinator.report()['recent_results']), len(packets))

    def test_concurrent_starts_allow_one_owner(self):
        self.seed()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: self.coordinator.start(), range(2)))
        self.assertEqual(sorted(r['state'] for r in results),['busy','started'])

    def test_monthly_limit_and_partial_finish(self):
        self.seed()
        with patch('app.coordinator.MONTHLY_RUN_CAP',1):
            run = self.coordinator.start()['run_id']
            packet = self.coordinator.next(run,1)['packets'][0]
            self.coordinator.finish(run,'Checkpoint and leave remaining work pending.')
            self.assertEqual(self.coordinator.start()['state'],'budget_exhausted')
        run2 = self.coordinator.start()['run_id']
        self.assertIn(packet['id'],{p['id'] for p in self.coordinator.next(run2)['packets']})

    def test_result_contract_and_immutability(self):
        self.seed()
        run = self.coordinator.start()['run_id']
        p = self.coordinator.next(run,1)['packets'][0]
        bad = self.answer(p)
        bad['findings'][0]['basis'] = 'VERIFIED'
        with self.assertRaises(ValueError):
            self.coordinator.complete(run,p['id'],bad)
        good = self.answer(p)
        self.coordinator.complete(run,p['id'],good)
        good['summary'] = 'Attempted overwrite'
        with self.assertRaises(ValueError):
            self.coordinator.complete(run,p['id'],good)


if __name__ == '__main__':
    unittest.main()

import argparse
import json
import re
import sys
import sqlite3
from pathlib import Path

from app.core import ROOT, Store, VERDICTS
from app.server import make_server


def main():
    parser = argparse.ArgumentParser(description='FULCRUM local evidence foundation')
    parser.add_argument('--root', type=Path, default=ROOT, help='Explicit alternate runtime root (testing/recovery)')
    parser.add_argument('--output', type=Path, help='Save the result as a JSON report')
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('init', 'doctor', 'backup', 'worker', 'list'):
        sub.add_parser(name)
    serve = sub.add_parser('serve')
    serve.add_argument('--port', type=int)
    capture = sub.add_parser('capture')
    capture.add_argument('json_file', type=Path)
    file = sub.add_parser('import-file')
    file.add_argument('path', type=Path)
    file.add_argument('--url')
    file.add_argument('--title')
    get = sub.add_parser('get')
    get.add_argument('capture_id')
    pair = sub.add_parser('pair-edge')
    pair.add_argument('extension_id')
    drive = sub.add_parser('configure-drive')
    drive.add_argument('folder', type=Path)
    claim = sub.add_parser('claim')
    claim.add_argument('capture_id')
    claim.add_argument('statement')
    claim.add_argument('--entity-name')
    claim.add_argument('--entity-kind', default='person')
    packet = sub.add_parser('packet')
    packet.add_argument('claim_id')
    review = sub.add_parser('review')
    review.add_argument('claim_id')
    review.add_argument('verdict', choices=sorted(VERDICTS))
    review.add_argument('rationale')
    review.add_argument('--reviewer', required=True)
    intake_plan = sub.add_parser('intake-plan', help='Read-only inventory of a consolidated folder')
    intake_plan.add_argument('folder', type=Path)
    intake_plan.add_argument('--limit', type=int, default=50000)
    intake = sub.add_parser('intake', help='Import, index, connect, and scope an entire collection')
    intake.add_argument('folder', type=Path)
    intake.add_argument('--collection', required=True)
    intake.add_argument('--workers', type=int, default=4)
    intake.add_argument('--limit', type=int, default=50000)
    resume = sub.add_parser('resume-intake')
    resume.add_argument('batch_id')
    resume.add_argument('--workers', type=int, default=4)
    batch_status = sub.add_parser('batch-status')
    batch_status.add_argument('batch_id')
    sub.add_parser('collections')
    search = sub.add_parser('search')
    search.add_argument('query')
    search.add_argument('--collection')
    search.add_argument('--limit', type=int, default=30)
    for name in ('scope', 'organize', 'plan-retrieval', 'production-plan'):
        scope = sub.add_parser(name)
        scope.add_argument('collection')
    retrieve = sub.add_parser('retrieve')
    retrieve.add_argument('collection')
    retrieve.add_argument('--allow-domain', action='append', required=True)
    retrieve.add_argument('--max-items', type=int, default=100)
    retrieve.add_argument('--workers', type=int, default=4)
    investigation = sub.add_parser('investigation-packet')
    investigation.add_argument('task_id')
    units = sub.add_parser('document-units')
    units.add_argument('document_id')
    units.add_argument('--offset', type=int, default=0)
    units.add_argument('--limit', type=int, default=100)
    connections = sub.add_parser('connections')
    connections.add_argument('collection')
    connections.add_argument('--limit', type=int, default=100)
    args = parser.parse_args()
    store = Store(args.root)
    command = args.command
    try:
        if command == 'init':
            result = store.initialize()
        elif command in ('intake-plan', 'intake', 'resume-intake', 'batch-status', 'collections', 'search', 'scope', 'organize', 'plan-retrieval', 'production-plan', 'retrieve', 'investigation-packet', 'document-units', 'connections'):
            from app.corpus import Corpus
            corpus = Corpus(store)
            if command == 'intake-plan':
                result = corpus.plan_folder(args.folder, args.limit)
            elif command == 'intake':
                batch_id = corpus.create_batch(args.folder, args.collection, args.limit)
                result = corpus.run_batch(batch_id, args.workers)
                result['retrieval_frontier'] = corpus.seed_frontier(result['collection_id'])
            elif command == 'resume-intake':
                result = corpus.run_batch(args.batch_id, args.workers)
            elif command == 'batch-status':
                result = corpus.batch_status(args.batch_id)
            elif command == 'collections':
                with store.connection() as db:
                    result = [dict(r) for r in db.execute('SELECT * FROM collections ORDER BY created_at')]
            elif command == 'search':
                result = corpus.search(args.query, args.collection, args.limit)
            elif command == 'scope':
                result = corpus.save_scope(args.collection)
            elif command == 'organize':
                result = corpus.organize(corpus.collection(args.collection)['id'])
            elif command == 'plan-retrieval':
                result = corpus.seed_frontier(args.collection)
            elif command == 'production-plan':
                result = corpus.production_plan(args.collection)
            elif command == 'investigation-packet':
                result = corpus.investigation_packet(args.task_id)
            elif command == 'document-units':
                result = corpus.document_units(args.document_id, args.offset, args.limit)
            elif command == 'connections':
                result = corpus.connections(args.collection, args.limit)
            else:
                from app.retrieval import Retriever
                result = Retriever(corpus, args.allow_domain).run(args.collection, args.max_items, args.workers)
        elif command == 'serve':
            server = make_server(store, args.port)
            print(f'FULCRUM intake listening at http://127.0.0.1:{server.server_port}', flush=True)
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass
            finally:
                server.server_close()
            return 0
        elif command == 'capture':
            result = store.capture(json.loads(args.json_file.read_text(encoding='utf-8-sig')))
        elif command == 'import-file':
            result = store.import_file(args.path, args.title, args.url)
        elif command == 'get':
            result = store.get_capture(args.capture_id)
        elif command == 'list':
            result = store.list_captures()
        elif command == 'worker':
            result = store.work_once()
        elif command in ('doctor', 'backup'):
            result = getattr(store, command)()
        elif command == 'claim':
            result = store.add_claim(args.capture_id, args.statement, args.entity_name, args.entity_kind)
        elif command == 'packet':
            result = store.packet(args.claim_id)
        elif command == 'review':
            result = store.review_claim(args.claim_id, args.verdict, args.rationale, args.reviewer)
        elif command in ('pair-edge', 'configure-drive'):
            settings = store.settings()
            if not settings.get('token'):
                raise ValueError('Initialize FULCRUM first.')
            if command == 'pair-edge':
                if not re.fullmatch('[a-p]{32}', args.extension_id):
                    raise ValueError('Expected the 32-letter ID shown by Edge Extensions.')
                settings['extension_origin'] = f'chrome-extension://{args.extension_id}'
            else:
                folder = args.folder.resolve()
                if not folder.is_dir():
                    raise ValueError('Select an existing Google Drive synced folder.')
                if folder == store.root or folder in store.db_path.parents or store.root in folder.parents:
                    raise ValueError('Drive folder must be outside the operating checkout.')
                settings['drive_root'] = str(folder)
            (store.root / 'config/local.json').write_text(json.dumps(settings, indent=2), encoding='utf-8')
            result = {'configured': command, 'restart_intake_service': True}
        else:
            raise ValueError('Unsupported command.')
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
            print(json.dumps({'report': str(args.output.resolve())}))
        else:
            print(json.dumps(result, indent=2, ensure_ascii=True))
        return 1 if isinstance(result, dict) and (result.get('ok') is False or result.get('complete') is False or result.get('state') in ('failed', 'blocked')) else 0
    except (ValueError, KeyError, OSError, sqlite3.Error) as exc:
        print(f'FULCRUM: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())

import argparse
import json
import re
import sys
from pathlib import Path

from app.core import ROOT, Store, VERDICTS
from app.server import make_server


def main():
    parser = argparse.ArgumentParser(description='FULCRUM local evidence foundation')
    parser.add_argument('--root', type=Path, default=ROOT, help='Explicit alternate runtime root (testing/recovery)')
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
    args = parser.parse_args()
    store = Store(args.root)
    command = args.command
    try:
        if command == 'init':
            result = store.initialize()
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
        print(json.dumps(result, indent=2, ensure_ascii=True))
        return 1 if isinstance(result, dict) and (result.get('ok') is False or result.get('state') in ('failed', 'blocked')) else 0
    except (ValueError, KeyError, OSError) as exc:
        print(f'FULCRUM: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())

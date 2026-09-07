"""Bounded public retrieval from the corpus citation frontier; no credentials or browser bypasses."""
import concurrent.futures
import ipaddress
import json
import mimetypes
import socket
import secrets
import threading
import time
import urllib.error
import urllib.request
import urllib.robotparser
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import parse_qs, urljoin, urlsplit

from app.core import MAX_FILE_BYTES, canonical_url, digest, ident, now
from app.parsers import SUPPORTED

USER_AGENT = 'FULCRUMResearch/0.2'


def validate_public_url(url, allowed_domains):
    url = canonical_url(url)
    parts = urlsplit(url)
    host = parts.hostname
    if host not in allowed_domains:
        raise ValueError('Destination is outside the declared domain scope.')
    if parts.port not in (None, 80, 443):
        raise ValueError('Only standard public HTTP(S) ports are supported.')
    if set(k.lower() for k in parse_qs(parts.query)) & {'token', 'access_token', 'api_key', 'signature', 'authorization', 'password'}:
        raise ValueError('Credential-bearing URLs require supervised acquisition.')
    addresses = socket.getaddrinfo(host, parts.port or (443 if parts.scheme == 'https' else 80), type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(row[4][0]).is_global for row in addresses):
        raise ValueError('Private, loopback, link-local, or reserved destinations are not retrievable.')
    return url


class RedirectGuard(urllib.request.HTTPRedirectHandler):
    def __init__(self, domains):
        self.domains = domains

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_public_url(newurl, self.domains)
        if urlsplit(req.full_url).hostname != urlsplit(newurl).hostname:
            raise ValueError('Cross-domain redirect requires supervised source selection and a separate robots check.')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class Retriever:
    def __init__(self, corpus, allowed_domains):
        self.corpus = corpus
        self.store = corpus.store
        self.domains = {x.lower().strip() for x in allowed_domains}
        if not self.domains:
            raise ValueError('Declare allowed public domains for the retrieval run.')
        self.locks = {domain: threading.Lock() for domain in self.domains}
        self.last_request = {}
        self.robots = {}

    def _read(self, url, limit=MAX_FILE_BYTES):
        url = validate_public_url(url, self.domains)
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), RedirectGuard(self.domains))
        request = urllib.request.Request(url, headers={'User-Agent': USER_AGENT, 'Accept-Encoding': 'identity'})
        with opener.open(request, timeout=30) as response:
            length = response.headers.get('Content-Length')
            if length and int(length) > limit:
                raise ValueError('Response exceeds retrieval byte limit.')
            raw = response.read(limit + 1)
            if len(raw) > limit:
                raise ValueError('Response exceeds retrieval byte limit.')
            return raw, response.headers.get_content_type(), response.geturl()

    def _allowed_by_robots(self, url):
        host = urlsplit(url).hostname
        if host not in self.robots:
            robots_url = urljoin(url, '/robots.txt')
            parser = urllib.robotparser.RobotFileParser()
            try:
                raw, _, _ = self._read(robots_url, 1024 * 1024)
                parser.parse(raw.decode('utf-8', errors='replace').splitlines())
            except urllib.error.HTTPError as exc:
                if exc.code == 404:
                    parser.parse(['User-agent: *', 'Allow: /'])
                else:
                    raise ValueError('Robots policy unavailable; use supervised browser acquisition.') from exc
            self.robots[host] = parser
        parser = self.robots[host]
        return parser.can_fetch(USER_AGENT, url), max(1, parser.crawl_delay(USER_AGENT) or 1)

    def _retrieve(self, row):
        host = urlsplit(row['url']).hostname
        capture_id = None
        error = None
        status = 'done'
        try:
            validate_public_url(row['url'], self.domains)
            with self.locks[host]:
                allowed, delay = self._allowed_by_robots(row['url'])
                if not allowed or delay > 30:
                    raise ValueError('Automated retrieval is restricted by robots policy; use supervised acquisition.')
                pause = delay - (time.monotonic() - self.last_request.get(host, 0))
                if pause > 0:
                    time.sleep(pause)
                try:
                    raw, mime, final_url = self._read(row['url'])
                finally:
                    self.last_request[host] = time.monotonic()
            suffix = { 'text/html': '.html', 'text/plain': '.txt', 'application/pdf': '.pdf',
                       'application/json': '.json', 'text/csv': '.csv',
                       'application/vnd.openxmlformats-officedocument.wordprocessingml.document': '.docx',
                       'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': '.xlsx'}.get(mime)
            if not suffix:
                candidate = Path(urlsplit(final_url).path).suffix.lower()
                suffix = candidate if candidate in SUPPORTED else None
            if not suffix:
                raise ValueError(f'Unsupported retrieved format: {mime}')
            with TemporaryDirectory(prefix='fulcrum-retrieve-') as temporary:
                path = Path(temporary) / (digest(raw) + suffix)
                path.write_bytes(raw)
                capture = self.store.import_file(path, title=final_url, url=final_url)
                capture_id = capture['id']
                self.corpus._store_document(capture, path, {'source_url': final_url, 'requested_url': row['url'],
                    'source_type': 'retrieved_unreviewed', 'retrieved_at': now()}, row['collection_id'])
        except urllib.error.HTTPError as exc:
            status = 'browser_required' if exc.code in (401, 403, 429) else 'failed'
            error = f'HTTP {exc.code}; no access bypass attempted.'
        except (ValueError, OSError) as exc:
            status = 'browser_required' if 'robots' in str(exc).lower() or 'supervised' in str(exc).lower() else 'failed'
            error = str(exc)[:2000]
        except Exception as exc:
            status, error = 'failed', f'{type(exc).__name__}: {exc}'[:2000]
        with self.store.connection() as db:
            updated = db.execute('''UPDATE retrieval_frontier SET status=?,capture_id=?,error=?,lease_token=NULL,lease_until=NULL
                WHERE id=? AND status='running' AND lease_token=? AND lease_until>?''',
                (status, capture_id, error, row['id'], row['lease_token'], time.time()))
            if updated.rowcount != 1:
                raise ValueError('Stale retrieval lease; completion rejected.')
            self.store.audit(db, 'retrieval.finished', row['id'], {'status': status, 'error': error, 'capture_id': capture_id})
        return {'id': row['id'], 'url': row['url'], 'status': status, 'error': error}

    def run(self, collection, max_items=100, workers=4):
        if not 1 <= max_items <= 10000 or not 1 <= workers <= 8:
            raise ValueError('Use 1–10,000 retrieval items and 1–8 workers per run.')
        collection_id = self.corpus.collection(collection)['id']
        budget_lock = threading.Lock()
        remaining = max_items
        results = []
        def work():
            nonlocal remaining
            while True:
                with budget_lock:
                    if remaining <= 0:
                        return
                    remaining -= 1
                with self.store.connection() as db:
                    db.execute('BEGIN IMMEDIATE')
                    db.execute("UPDATE retrieval_frontier SET status='failed',error='Lease expired',lease_token=NULL WHERE collection_id=? AND status='running' AND lease_until<=?", (collection_id, time.time()))
                    candidates = db.execute("SELECT * FROM retrieval_frontier WHERE collection_id=? AND status IN ('candidate','pending','failed') AND attempts<3 ORDER BY attempts,id", (collection_id,)).fetchall()
                    row = next((dict(r) for r in candidates if urlsplit(r['url']).hostname in self.domains), None)
                    if row is None:
                        return
                    row['lease_token'] = secrets.token_hex(24)
                    db.execute("UPDATE retrieval_frontier SET status='running',attempts=attempts+1,lease_token=?,lease_until=? WHERE id=?", (row['lease_token'], time.time() + 3600, row['id']))
                result = self._retrieve(row)
                with budget_lock:
                    results.append(result)
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(work) for _ in range(workers)]
            for future in futures:
                future.result()
        self.corpus.organize(collection_id)
        return {'collection_id': collection_id, 'attempted': len(results), 'results': results,
                'scope': self.corpus.save_scope(collection_id)}

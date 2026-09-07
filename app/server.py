import hmac
import json
import sqlite3
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from app.core import MAX_BYTES


def make_server(store, port=None):
    settings = store.settings()
    token = settings.get('token', '')
    if len(token) < 32:
        raise ValueError('Run init before starting the intake service.')
    selected_port = settings.get('port', 8745) if port is None else port
    allowed_origin = settings.get('extension_origin')

    class Handler(BaseHTTPRequestHandler):
        server_version = 'FULCRUM/0.1'

        def setup(self):
            super().setup()
            self.connection.settimeout(15)

        def log_message(self, *_):
            # No evidence, authorization headers, or URLs in HTTP logs.
            pass

        def respond(self, code, payload):
            raw = json.dumps(payload, ensure_ascii=False).encode('utf-8')
            self.send_response(code)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(raw)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Connection', 'close')
            origin = self.headers.get('Origin')
            if origin and origin == allowed_origin:
                self.send_header('Access-Control-Allow-Origin', origin)
                self.send_header('Vary', 'Origin')
                self.send_header('Access-Control-Allow-Headers', 'Authorization, Content-Type')
                self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
            self.end_headers()
            self.wfile.write(raw)
            self.close_connection = True

        def guarded(self, action, auth=True):
            host = self.headers.get('Host')
            actual_port = self.server.server_port
            if host not in (f'127.0.0.1:{actual_port}', f'localhost:{actual_port}'):
                return self.respond(403, {'error': 'Invalid local host.'})
            origin = self.headers.get('Origin')
            if origin and origin != allowed_origin:
                return self.respond(403, {'error': 'Browser origin is not paired.'})
            supplied = self.headers.get('Authorization', '')
            if auth and not hmac.compare_digest(supplied.encode('utf-8'), f'Bearer {token}'.encode('utf-8')):
                return self.respond(401, {'error': 'Local pairing token required.'})
            try:
                action()
            except (ValueError, TypeError, UnicodeError, json.JSONDecodeError):
                self.respond(400, {'error': 'Invalid input or evidence integrity failure.'})
            except KeyError:
                self.respond(404, {'error': 'Record not found.'})
            except (OSError, sqlite3.Error):
                self.respond(503, {'error': 'Local storage unavailable; retry after running doctor.'})

        def do_OPTIONS(self):
            self.guarded(lambda: self.respond(200, {'ok': True}), auth=False)

        def do_GET(self):
            route = urlsplit(self.path).path
            if route == '/health':
                return self.guarded(lambda: self.respond(200, {'service': 'FULCRUM', 'status': 'running'}), auth=False)

            def get():
                if route == '/api/captures':
                    self.respond(200, store.list_captures())
                elif route.startswith('/api/captures/'):
                    self.respond(200, store.get_capture(route.removeprefix('/api/captures/')))
                elif route == '/api/status':
                    result = store.doctor()
                    self.respond(200 if result['ok'] else 503, result)
                else:
                    self.respond(404, {'error': 'Unknown route.'})
            self.guarded(get)

        def do_POST(self):
            def post():
                if urlsplit(self.path).path != '/api/captures':
                    return self.respond(404, {'error': 'Unknown route.'})
                if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                    return self.respond(415, {'error': 'Use application/json.'})
                if self.headers.get('Transfer-Encoding'):
                    return self.respond(400, {'error': 'Chunked intake is unsupported.'})
                length = int(self.headers.get('Content-Length', '0'))
                if length <= 0 or length > MAX_BYTES + 65536:
                    return self.respond(413, {'error': 'Capture request size is invalid.'})
                body = self.rfile.read(length)
                if len(body) != length:
                    raise ValueError('Incomplete request.')
                result = store.capture(json.loads(body.decode('utf-8')))
                self.respond(200 if result['deduplicated'] else 201, result)
            self.guarded(post)

    class LocalServer(ThreadingHTTPServer):
        allow_reuse_address = False

        def server_bind(self):
            if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
                self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            super().server_bind()

    server = LocalServer(('127.0.0.1', selected_port), Handler)
    server.daemon_threads = True
    return server

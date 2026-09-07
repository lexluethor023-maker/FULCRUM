import http.client
import json
import tempfile
import threading
import unittest

from app.core import MAX_BYTES, Store
from app.server import make_server


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(self.temp.name)
        self.store.initialize()
        settings = self.store.settings()
        self.origin = 'chrome-extension://' + 'a' * 32
        settings['extension_origin'] = self.origin
        (self.store.root / 'config/local.json').write_text(json.dumps(settings), encoding='utf-8')
        self.token = settings['token']
        self.server = make_server(self.store, port=0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def request(self, method, route, body=None, headers=None, authenticate=True):
        h = {'Content-Type': 'application/json'}
        if authenticate:
            h['Authorization'] = f'Bearer {self.token}'
        h.update(headers or {})
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        try:
            connection.request(method, route, body, h)
            response = connection.getresponse()
            return response.status, json.loads(response.read()), dict(response.getheaders())
        finally:
            connection.close()

    def test_live_socket_capture_and_exact_readback(self):
        payload = {'url': 'https://example.org/', 'title': 'Source', 'text': 'Exact Ω\n  evidence', 'acquired_via': 'edge'}
        status, capture, headers = self.request('POST', '/api/captures', json.dumps(payload), {'Origin': self.origin})
        self.assertEqual(status, 201)
        self.assertEqual(headers['Access-Control-Allow-Origin'], self.origin)
        self.assertEqual(self.request('GET', '/api/captures/' + capture['id'])[1]['text'], payload['text'])
        self.assertEqual(self.request('POST', '/api/captures', json.dumps(payload))[0], 200)
        self.assertTrue(self.request('GET', '/api/status')[1]['ok'])

    def test_auth_origin_host_and_input_boundary(self):
        self.assertEqual(self.request('GET', '/health', authenticate=False)[0], 200)
        self.assertEqual(self.request('GET', '/api/captures', authenticate=False)[0], 401)
        self.assertEqual(self.request('GET', '/api/captures', headers={'Authorization': 'Bearer wrong'})[0], 401)
        self.assertEqual(self.request('GET', '/api/captures', headers={'Origin': 'https://evil.example'})[0], 403)
        self.assertEqual(self.request('GET', '/health', headers={'Host': 'evil.example'})[0], 403)
        self.assertEqual(self.request('OPTIONS', '/api/captures', headers={'Origin': self.origin}, authenticate=False)[0], 200)
        self.assertEqual(self.request('POST', '/api/captures', 'no JSON')[0], 400)
        self.assertEqual(self.request('POST', '/api/captures', 'null')[0], 400)
        self.assertEqual(self.request('POST', '/api/captures', '{}', {'Content-Type': 'text/plain'})[0], 415)
        self.assertEqual(self.request('POST', '/api/captures', '{}', {'Content-Length': str(MAX_BYTES + 65537)})[0], 413)
        self.assertEqual(self.request('GET', '/api/captures/CAP-missing')[0], 404)
        self.assertEqual(self.request('GET', '/api/status')[1]['counts']['captures'], 0)

    def test_second_intake_service_cannot_share_the_port(self):
        with self.assertRaises(OSError):
            make_server(self.store, port=self.server.server_port)


if __name__ == '__main__':
    unittest.main()

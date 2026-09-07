const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../edge/popup.js'), 'utf8');

function harness({ text = 'Exact Ω\n  evidence', mismatch = false, reject = false, token = 't'.repeat(32) } = {}) {
  const elements = Object.fromEntries(['status', 'extension-id', 'save-token', 'token', 'capture', 'locator'].map(id =>
    [id, { value: '', textContent: '', disabled: false, addEventListener(event, callback) { this[event] = callback; } }]));
  const calls = [];
  vm.runInNewContext(source, {
    document: { getElementById: id => elements[id] }, AbortSignal,
    chrome: {
      runtime: { id: 'a'.repeat(32) },
      storage: { local: { get: async () => ({ token }), set: async () => {} } },
      tabs: { query: async () => [{ id: 1, url: 'https://example.org/' }] },
      scripting: { executeScript: async () => [{ result: { url: 'https://example.org/', title: 'Source', text } }] }
    },
    fetch: async (url, options) => {
      calls.push({ url, options });
      return { ok: !reject, status: reject ? 401 : 200, json: async () =>
        ({ id: 'CAP-test', sha256: 'known-hash', integrity: 'verified', text: mismatch ? 'wrong text' : text }) };
    }
  });
  return { elements, calls, capture: () => elements.capture.click() };
}

test('successful capture requires a separate matching readback', async () => {
  const h = harness();
  await h.capture();
  assert.equal(h.calls.length, 2);
  assert.equal(JSON.parse(h.calls[0].options.body).acquired_via, 'edge');
  assert.match(h.elements.status.textContent, /verified locally/);
  assert.equal(h.elements.capture.disabled, false);
});
test('mismatched readback is never reported as success', async () => {
  const h = harness({ mismatch: true });
  await h.capture();
  assert.match(h.elements.status.textContent, /did not match/);
});
test('empty selection and missing connection never send evidence', async () => {
  for (const options of [{ text: '' }, { token: null }]) {
    const h = harness(options);
    await h.capture();
    assert.equal(h.calls.length, 0);
    assert.equal(h.elements.capture.disabled, false);
  }
});
test('rejected intake does not proceed to readback', async () => {
  const h = harness({ reject: true });
  await h.capture();
  assert.equal(h.calls.length, 1);
  assert.match(h.elements.status.textContent, /rejected \(401\)/);
});

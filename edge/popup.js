'use strict';
const endpoint = 'http://127.0.0.1:8745';
const status = document.getElementById('status');
document.getElementById('extension-id').textContent = chrome.runtime.id;

document.getElementById('save-token').addEventListener('click', async () => {
  const token = document.getElementById('token').value.trim();
  if (token.length < 32) {
    status.textContent = 'Enter the complete local pairing token.';
    return;
  }
  await chrome.storage.local.set({ token });
  document.getElementById('token').value = '';
  status.textContent = 'Token saved. Pair this extension ID in FULCRUM, then restart the intake service.';
});

document.getElementById('capture').addEventListener('click', async () => {
  const button = document.getElementById('capture');
  button.disabled = true;
  status.textContent = 'Capturing and checking readback…';
  try {
    const { token } = await chrome.storage.local.get('token');
    if (!token) throw new Error('Connect to local FULCRUM first.');
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab || !/^https?:\/\//.test(tab.url || '')) {
      throw new Error('Open an HTTP or HTTPS source page to capture evidence.');
    }
    const [injection] = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: () => ({ url: location.href, title: document.title,
        text: window.getSelection().toString(), captured_at: new Date().toISOString() })
    });
    const payload = injection.result;
    if (!payload.text || !payload.text.trim()) throw new Error('Select a passage on the page first.');
    payload.acquired_via = 'edge';
    payload.locator = document.getElementById('locator').value;
    const headers = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };
    const response = await fetch(`${endpoint}/api/captures`, {
      method: 'POST', headers, body: JSON.stringify(payload), signal: AbortSignal.timeout(20000)
    });
    if (!response.ok) throw new Error(`Capture rejected (${response.status}). Check pairing and the local service.`);
    const saved = await response.json();
    const readback = await fetch(`${endpoint}/api/captures/${encodeURIComponent(saved.id)}`, {
      headers: { Authorization: `Bearer ${token}` }, signal: AbortSignal.timeout(20000)
    });
    if (!readback.ok) throw new Error('Capture saved, but readback failed. Retry to verify; duplicates are safe.');
    const verified = await readback.json();
    if (verified.text !== payload.text || verified.sha256 !== saved.sha256 || verified.integrity !== 'verified') {
      throw new Error('Readback did not match. Evidence requires inspection.');
    }
    status.textContent = `${saved.deduplicated ? 'Existing capture' : 'Captured'} and verified locally. ${saved.id}. Drive archival is tracked separately.`;
  } catch (error) {
    status.textContent = error.message;
  } finally {
    button.disabled = false;
  }
});

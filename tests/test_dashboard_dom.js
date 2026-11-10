const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const root = path.join(__dirname, '..');
test('dashboard IDs match JavaScript element lookups', () => {
    const html = fs.readFileSync(path.join(root, 'Dashboard.html'), 'utf8');
    const js = fs.readFileSync(path.join(root, 'script.js'), 'utf8');
    const ids = new Set([...html.matchAll(/\bid="([^"]+)"/g)].map(m => m[1]));
    const requested = new Set([...js.matchAll(/\$\("([^"]+)"\)/g)].map(m => m[1]));
    for (const id of requested) assert.ok(ids.has(id), `Missing dashboard element: ${id}`);
    assert.match(html, /script\.js\?v=dual-assessments-3/);
    assert.match(html, /styles\.css\?v=dual-assessments-3/);
});

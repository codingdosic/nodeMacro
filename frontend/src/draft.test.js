import assert from 'node:assert/strict';
import test from 'node:test';

import { graphFingerprint, makeDraft, parseDraft } from './draft.js';

test('selection changes do not mark a graph as changed', () => {
  const graph = { nodes: [{ id: 'a', selected: false }], edges: [] };
  const selected = { nodes: [{ id: 'a', selected: true }], edges: [] };
  assert.equal(graphFingerprint(graph), graphFingerprint(selected));
});

test('draft round-trip preserves the graph', () => {
  const graph = { nodes: [{ id: 'a' }], edges: [{ id: 'e', source: 'a', target: 'b' }] };
  assert.deepEqual(parseDraft(JSON.stringify(makeDraft(graph))).graph, graph);
});

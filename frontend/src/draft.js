export const DRAFT_KEY = 'd5macro-unsaved-draft';
export const DRAFT_VERSION = 1;

export function normalizeGraph(graph = {}) {
  return {
    nodes: (graph.nodes || []).map(({ selected: _selected, ...node }) => node),
    edges: (graph.edges || []).map(({ selected: _selected, ...edge }) => edge),
  };
}

export const graphFingerprint = (graph) => JSON.stringify(normalizeGraph(graph));

export function makeDraft(graph) {
  return {
    format: 'd5macro-draft',
    version: DRAFT_VERSION,
    saved_at: new Date().toISOString(),
    graph: normalizeGraph(graph),
  };
}

export function parseDraft(raw) {
  const draft = JSON.parse(raw);
  if (
    draft?.format !== 'd5macro-draft'
    || draft.version !== DRAFT_VERSION
    || !Array.isArray(draft.graph?.nodes)
    || !Array.isArray(draft.graph?.edges)
  ) {
    throw new Error('Invalid D5 Macro draft');
  }
  return draft;
}

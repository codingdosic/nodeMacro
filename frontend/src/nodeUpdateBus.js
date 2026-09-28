/** WebSocket 등 외부 갱신을 React Flow memo 우회로 노드에 전달 */
const listeners = new Map();

export function subscribeNodeUpdate(nodeId, handler) {
  if (!nodeId) {
    return () => {};
  }
  const set = listeners.get(nodeId) || new Set();
  set.add(handler);
  listeners.set(nodeId, set);
  return () => {
    const current = listeners.get(nodeId);
    if (!current) {
      return;
    }
    current.delete(handler);
    if (current.size === 0) {
      listeners.delete(nodeId);
    }
  };
}

export function emitNodeUpdate(nodeId, payload) {
  const set = listeners.get(nodeId);
  if (!set) {
    return;
  }
  set.forEach((handler) => {
    try {
      handler(payload);
    } catch (e) {
      console.error(e);
    }
  });
}

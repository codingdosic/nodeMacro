import React, { useState, useCallback, useRef, useEffect } from 'react';
import {
  ReactFlow,
  addEdge,
  useNodesState,
  useEdgesState,
  Controls,
  MiniMap,
  Background,
  SelectionMode,
} from '@xyflow/react';
import axios from 'axios';
import GenericNode from './GenericNode';
import { emitNodeUpdate } from './nodeUpdateBus';

const nodeTypes = {
  customNode: GenericNode,
};

let id = 0;
const getId = () => `dndnode_${id++}`;

const syncIdCounter = (nodeList) => {
  let next = id;
  nodeList.forEach((node) => {
    const match = /^dndnode_(\d+)$/.exec(node.id);
    if (match) {
      next = Math.max(next, Number(match[1]) + 1);
    }
  });
  id = next;
};

const isEditableTarget = (target) => {
  if (!target || !(target instanceof Element)) {
    return false;
  }
  return Boolean(target.closest('input, textarea, select, [contenteditable="true"]'));
};

const MAX_HISTORY = 40;

const cloneConfig = (config) => {
  try {
    return structuredClone(config || {});
  } catch {
    return JSON.parse(JSON.stringify(config || {}));
  }
};

const cloneGraph = (nodeList, edgeList) => {
  const stripNode = (node) => ({
    id: node.id,
    type: node.type,
    position: { ...node.position },
    selected: Boolean(node.selected),
    data: {
      id: node.data?.id ?? node.id,
      type: node.data?.type,
      label: node.data?.label,
      configSchema: node.data?.configSchema,
      config: cloneConfig(node.data?.config),
      revision: node.data?.revision,
    },
  });
  const stripEdge = (edge) => ({
    id: edge.id,
    source: edge.source,
    target: edge.target,
    sourceHandle: edge.sourceHandle,
    targetHandle: edge.targetHandle,
    selected: Boolean(edge.selected),
  });
  try {
    return {
      nodes: nodeList.map(stripNode),
      edges: edgeList.map(stripEdge),
    };
  } catch {
    return JSON.parse(JSON.stringify({
      nodes: nodeList.map(stripNode),
      edges: edgeList.map(stripEdge),
    }));
  }
};

const sanitizeMacroPayload = (nodeList, edgeList) => cloneGraph(nodeList, edgeList);

const findEdgeIdAtPoint = (clientX, clientY) => {
  const elements = document.elementsFromPoint(clientX, clientY);
  for (const el of elements) {
    if (!(el instanceof Element)) {
      continue;
    }
    if (
      el.classList.contains('react-flow__edge-interaction')
      || el.classList.contains('react-flow__edge-path')
      || el.classList.contains('react-flow__edge')
    ) {
      const edgeEl = el.closest('.react-flow__edge');
      if (edgeEl?.dataset?.id) {
        return edgeEl.dataset.id;
      }
    }
  }
  return null;
};

const getHandleContext = (target) => {
  if (!target || !(target instanceof Element)) {
    return null;
  }
  const handleEl = target.closest('.react-flow__handle');
  if (!handleEl) {
    return null;
  }
  const nodeEl = handleEl.closest('.react-flow__node');
  const nodeId = nodeEl?.dataset?.id;
  if (!nodeId) {
    return null;
  }
  const handleId = handleEl.getAttribute('data-handleid');
  const isSource = handleEl.classList.contains('source');
  return { nodeId, handleId, isSource };
};

const edgesForHandle = (edgeList, handleInfo) => {
  if (!handleInfo) {
    return [];
  }
  const { nodeId, handleId, isSource } = handleInfo;
  return edgeList.filter((edge) => {
    if (isSource) {
      if (edge.source !== nodeId) {
        return false;
      }
      const edgeHandle = edge.sourceHandle || 'output_pin';
      const clicked = handleId || 'output_pin';
      return edgeHandle === clicked;
    }
    if (edge.target !== nodeId) {
      return false;
    }
    const edgeHandle = edge.targetHandle || 'input_pin';
    const clicked = handleId || 'input_pin';
    return edgeHandle === clicked;
  });
};

const NodeEditor = () => {
  const reactFlowWrapper = useRef(null);
  const clipboardRef = useRef({ nodes: [], edges: [] });
  const nodesRef = useRef([]);
  const edgesRef = useRef([]);
  const undoStackRef = useRef([]);
  const redoStackRef = useRef([]);
  const isRestoringRef = useRef(false);
  const historyLockRef = useRef(false);
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const [reactFlowInstance, setReactFlowInstance] = useState(null);
  const [status, setStatus] = useState('Idle');
  const [contextMenu, setContextMenu] = useState(null);
  const [saveDialog, setSaveDialog] = useState(null); // { name, overwriteConfirm }
  const [loadDialog, setLoadDialog] = useState(null); // { files, selected }

  useEffect(() => {
    nodesRef.current = nodes;
  }, [nodes]);

  useEffect(() => {
    edgesRef.current = edges;
  }, [edges]);

  const pushHistory = useCallback(() => {
    if (isRestoringRef.current || historyLockRef.current) {
      return;
    }
    historyLockRef.current = true;
    const snap = cloneGraph(nodesRef.current, edgesRef.current);
    undoStackRef.current.push(snap);
    if (undoStackRef.current.length > MAX_HISTORY) {
      undoStackRef.current.shift();
    }
    redoStackRef.current = [];
    queueMicrotask(() => {
      historyLockRef.current = false;
    });
  }, []);

  // onNodeConfigChange is defined below — bind via ref to avoid circular dep
  const onNodeConfigChangeRef = useRef(null);

  const applySnapshot = useCallback((snapshot) => {
    isRestoringRef.current = true;
    const restoredNodes = (snapshot.nodes || []).map((node) => ({
      ...node,
      data: {
        ...node.data,
        id: node.data?.id ?? node.id,
        config: cloneConfig(node.data?.config),
        onChange: onNodeConfigChangeRef.current,
      },
    }));
    syncIdCounter(restoredNodes);
    setNodes(restoredNodes);
    setEdges((snapshot.edges || []).map((edge) => ({ ...edge })));
    queueMicrotask(() => {
      isRestoringRef.current = false;
    });
  }, [setNodes, setEdges]);

  const undo = useCallback(() => {
    if (!undoStackRef.current.length) {
      return;
    }
    const current = cloneGraph(nodesRef.current, edgesRef.current);
    const prev = undoStackRef.current.pop();
    redoStackRef.current.push(current);
    applySnapshot(prev);
  }, [applySnapshot]);

  const redo = useCallback(() => {
    if (!redoStackRef.current.length) {
      return;
    }
    const current = cloneGraph(nodesRef.current, edgesRef.current);
    const next = redoStackRef.current.pop();
    undoStackRef.current.push(current);
    applySnapshot(next);
  }, [applySnapshot]);

  useEffect(() => {
    const ws = new WebSocket('ws://127.0.0.1:8000/ws');
    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.type === 'status') {
        setStatus(data.message);
      } else if (data.type === 'execution') {
        setNodes((nds) => nds.map((node) => {
          if (data.phase === 'reset') {
            return { ...node, data: { ...node.data, executionState: null, executionMessage: null } };
          }
          if (node.id === data.node_id) {
            return {
              ...node,
              data: {
                ...node.data,
                executionState: data.phase,
                executionMessage: data.message || null,
              },
            };
          }
          return node;
        }));
      } else if (data.type === 'capture_complete') {
        const stamp = Date.now();
        const patch = {
          image_path: data.file_path,
          image_url: `http://127.0.0.1:8000${data.url}?t=${stamp}`,
        };
        emitNodeUpdate(data.node_id, {
          revision: stamp,
          config: patch,
          hint: '캡처 완료',
        });
        setNodes((nds) =>
          nds.map((node) => {
            if (node.id !== data.node_id) {
              return node;
            }
            return {
              ...node,
              data: {
                ...node.data,
                revision: stamp,
                config: {
                  ...node.data.config,
                  ...patch,
                },
              },
            };
          })
        );
      } else if (data.type === 'region_complete') {
        const stamp = Date.now();
        const patch = { search_region: data.search_region };
        emitNodeUpdate(data.node_id, {
          revision: stamp,
          config: patch,
          hint: '탐색 영역이 설정되었습니다.',
        });
        setNodes((nds) =>
          nds.map((node) => {
            if (node.id !== data.node_id) {
              return node;
            }
            return {
              ...node,
              data: {
                ...node.data,
                revision: stamp,
                config: {
                  ...node.data.config,
                  ...patch,
                },
              },
            };
          })
        );
      } else if (data.type === 'coordinate_complete') {
        const stamp = Date.now();
        const patch = { x: data.x, y: data.y };
        emitNodeUpdate(data.node_id, {
          revision: stamp,
          lastCoordPickId: stamp,
          config: patch,
          pickingCoordinate: false,
          hint: `좌표 저장됨: (${data.x}, ${data.y})`,
        });
        setNodes((nds) =>
          nds.map((node) => {
            if (node.id !== data.node_id) {
              return node;
            }
            return {
              ...node,
              data: {
                ...node.data,
                revision: stamp,
                lastCoordPickId: stamp,
                config: {
                  ...node.data.config,
                  ...patch,
                },
              },
            };
          })
        );
      } else if (data.type === 'coordinate_cancelled') {
        emitNodeUpdate(data.node_id, {
          pickingCoordinate: false,
          hint: '좌표 선택 취소됨',
        });
      }
    };
    return () => ws.close();
  }, [setNodes]);

  const closeContextMenu = useCallback(() => setContextMenu(null), []);

  const onConnect = useCallback((params) => {
    pushHistory();
    setEdges((eds) => addEdge(params, eds));
  }, [setEdges, pushHistory]);

  const onDragOver = useCallback((event) => {
    event.preventDefault();
    event.dataTransfer.dropEffect = 'move';
  }, []);

  const onNodeConfigChange = useCallback((nodeId, keyOrPatch, value) => {
    const patch = typeof keyOrPatch === 'object' && keyOrPatch !== null
      ? keyOrPatch
      : { [keyOrPatch]: value };
    setNodes((nds) =>
      nds.map((node) => {
        if (node.id !== nodeId) {
          return node;
        }
        return {
          ...node,
          data: {
            ...node.data,
            config: {
              ...node.data.config,
              ...patch,
            },
          },
        };
      })
    );
  }, [setNodes]);

  useEffect(() => {
    onNodeConfigChangeRef.current = onNodeConfigChange;
  }, [onNodeConfigChange]);

  const handleNodesChange = useCallback((changes) => {
    if (changes.some((change) => change.type === 'remove')) {
      pushHistory();
    }
    onNodesChange(changes);
  }, [onNodesChange, pushHistory]);

  const handleEdgesChange = useCallback((changes) => {
    if (changes.some((change) => change.type === 'remove')) {
      pushHistory();
    }
    onEdgesChange(changes);
  }, [onEdgesChange, pushHistory]);

  const deleteNodesByIds = useCallback((nodeIds) => {
    if (!nodeIds.length) {
      return;
    }
    pushHistory();
    const idSet = new Set(nodeIds);
    setNodes((nds) => nds.filter((node) => !idSet.has(node.id)));
    setEdges((eds) => eds.filter((edge) => !idSet.has(edge.source) && !idSet.has(edge.target)));
  }, [setNodes, setEdges, pushHistory]);

  const deleteEdgesByIds = useCallback((edgeIds) => {
    if (!edgeIds.length) {
      return;
    }
    pushHistory();
    const idSet = new Set(edgeIds);
    setEdges((eds) => eds.filter((edge) => !idSet.has(edge.id)));
  }, [setEdges, pushHistory]);

  const copySelection = useCallback(() => {
    const selectedNodes = nodes.filter((node) => node.selected);
    if (selectedNodes.length === 0) {
      return false;
    }
    const selectedIds = new Set(selectedNodes.map((node) => node.id));
    const selectedEdges = edges.filter(
      (edge) => selectedIds.has(edge.source) && selectedIds.has(edge.target)
    );
    clipboardRef.current = {
      nodes: selectedNodes.map((node) => ({
        ...node,
        selected: false,
        data: {
          ...node.data,
          config: cloneConfig(node.data.config),
          configSchema: node.data.configSchema,
        },
      })),
      edges: selectedEdges.map((edge) => ({
        ...edge,
        selected: false,
      })),
    };
    return true;
  }, [nodes, edges]);

  const getPasteAnchor = useCallback((screenPoint) => {
    if (!reactFlowInstance || !reactFlowWrapper.current) {
      return { x: 0, y: 0 };
    }
    if (screenPoint) {
      return reactFlowInstance.screenToFlowPosition(screenPoint);
    }
    const bounds = reactFlowWrapper.current.getBoundingClientRect();
    return reactFlowInstance.screenToFlowPosition({
      x: bounds.left + bounds.width / 2,
      y: bounds.top + bounds.height / 2,
    });
  }, [reactFlowInstance]);

  const pasteClipboard = useCallback((screenPoint) => {
    const { nodes: clipNodes, edges: clipEdges } = clipboardRef.current;
    if (!clipNodes.length) {
      return;
    }

    pushHistory();
    const anchor = getPasteAnchor(screenPoint);
    const xs = clipNodes.map((node) => node.position.x);
    const ys = clipNodes.map((node) => node.position.y);
    const sourceCenter = {
      x: (Math.min(...xs) + Math.max(...xs)) / 2,
      y: (Math.min(...ys) + Math.max(...ys)) / 2,
    };

    const idMap = {};
    const newNodes = clipNodes.map((node) => {
      const newId = getId();
      idMap[node.id] = newId;
      return {
        ...node,
        id: newId,
        position: {
          x: node.position.x - sourceCenter.x + anchor.x,
          y: node.position.y - sourceCenter.y + anchor.y,
        },
        selected: true,
        data: {
          ...node.data,
          id: newId,
          config: cloneConfig(node.data.config),
          onChange: onNodeConfigChange,
        },
      };
    });

    const stamp = Date.now();
    const newEdges = clipEdges
      .filter((edge) => idMap[edge.source] && idMap[edge.target])
      .map((edge, index) => ({
        ...edge,
        id: `e_${idMap[edge.source]}_${idMap[edge.target]}_${edge.sourceHandle || 'out'}_${edge.targetHandle || 'in'}_${stamp}_${index}`,
        source: idMap[edge.source],
        target: idMap[edge.target],
        selected: false,
      }));

    setNodes((nds) => [
      ...nds.map((node) => ({ ...node, selected: false })),
      ...newNodes,
    ]);
    setEdges((eds) => [
      ...eds.map((edge) => ({ ...edge, selected: false })),
      ...newEdges,
    ]);
  }, [getPasteAnchor, onNodeConfigChange, setNodes, setEdges, pushHistory]);

  useEffect(() => {
    const onKeyDown = (event) => {
      if (isEditableTarget(event.target)) {
        return;
      }
      const mod = event.ctrlKey || event.metaKey;
      if (mod && event.key.toLowerCase() === 'z' && !event.shiftKey) {
        event.preventDefault();
        undo();
        return;
      }
      if (mod && (event.key.toLowerCase() === 'y' || (event.key.toLowerCase() === 'z' && event.shiftKey))) {
        event.preventDefault();
        redo();
        return;
      }
      if (mod && event.key.toLowerCase() === 'c') {
        if (copySelection()) {
          event.preventDefault();
        }
        return;
      }
      if (mod && event.key.toLowerCase() === 'v') {
        if (clipboardRef.current.nodes.length > 0) {
          event.preventDefault();
          pasteClipboard();
        }
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [copySelection, pasteClipboard, undo, redo]);

  const onDrop = useCallback(
    (event) => {
      event.preventDefault();

      const type = event.dataTransfer.getData('application/reactflow');
      const label = event.dataTransfer.getData('application/reactflow/label');
      const schemaRaw = event.dataTransfer.getData('application/reactflow/schema');
      let schema = {};
      try {
        schema = JSON.parse(schemaRaw);
      } catch (e) {
        /* ignore */
      }

      if (typeof type === 'undefined' || !type) {
        return;
      }

      pushHistory();
      const position = reactFlowInstance.screenToFlowPosition({
        x: event.clientX,
        y: event.clientY,
      });

      const newNodeId = getId();
      const initialConfig = {};
      Object.entries(schema || {}).forEach(([key, field]) => {
        if (field && field.default !== undefined) {
          initialConfig[key] = field.default;
        }
      });
      const newNode = {
        id: newNodeId,
        type: 'customNode',
        position,
        data: {
          id: newNodeId,
          type: type,
          label: label,
          configSchema: schema,
          config: initialConfig,
          onChange: onNodeConfigChange,
        },
      };

      setNodes((nds) => nds.concat(newNode));
    },
    [reactFlowInstance, onNodeConfigChange, setNodes, pushHistory]
  );

  const openEdgeContextMenu = useCallback((event, edgeIds) => {
    event.preventDefault();
    event.stopPropagation();
    if (!edgeIds.length) {
      return;
    }
    setContextMenu({
      kind: 'edge',
      x: event.clientX,
      y: event.clientY,
      ids: edgeIds,
    });
  }, []);

  const onNodeContextMenu = useCallback((event, node) => {
    // 핸들(연결부) 우클릭 → 그 핀에 연결된 엣지 해제
    const handleInfo = getHandleContext(event.target);
    if (handleInfo) {
      const connected = edgesForHandle(edges, handleInfo);
      if (connected.length > 0) {
        openEdgeContextMenu(event, connected.map((edge) => edge.id));
        return;
      }
    }

    event.preventDefault();
    const selectedIds = nodes.filter((n) => n.selected).map((n) => n.id);
    const ids = selectedIds.includes(node.id) && selectedIds.length > 0
      ? selectedIds
      : [node.id];
    setContextMenu({
      kind: 'node',
      x: event.clientX,
      y: event.clientY,
      ids,
    });
  }, [nodes, edges, openEdgeContextMenu]);

  const onEdgeContextMenu = useCallback((event, edge) => {
    const selectedIds = edges.filter((e) => e.selected).map((e) => e.id);
    const ids = selectedIds.includes(edge.id) && selectedIds.length > 0
      ? selectedIds
      : [edge.id];
    openEdgeContextMenu(event, ids);
  }, [edges, openEdgeContextMenu]);

  const onPaneContextMenu = useCallback((event) => {
    const edgeIdAtPoint = findEdgeIdAtPoint(event.clientX, event.clientY);
    if (edgeIdAtPoint && edges.some((edge) => edge.id === edgeIdAtPoint)) {
      openEdgeContextMenu(event, [edgeIdAtPoint]);
      return;
    }
    event.preventDefault();
    setContextMenu({
      kind: 'pane',
      x: event.clientX,
      y: event.clientY,
      ids: [],
    });
  }, [edges, openEdgeContextMenu]);

  const handleContextAction = (action) => {
    if (!contextMenu) {
      return;
    }
    if (action === 'delete-nodes') {
      deleteNodesByIds(contextMenu.ids);
    } else if (action === 'delete-edges') {
      deleteEdgesByIds(contextMenu.ids);
    } else if (action === 'copy') {
      const selectedNodes = nodes.filter((node) => contextMenu.ids.includes(node.id));
      const selectedIds = new Set(contextMenu.ids);
      const selectedEdges = edges.filter(
        (edge) => selectedIds.has(edge.source) && selectedIds.has(edge.target)
      );
      clipboardRef.current = {
        nodes: selectedNodes.map((node) => ({
          ...node,
          selected: false,
          data: {
            ...node.data,
            config: cloneConfig(node.data.config),
            configSchema: node.data.configSchema,
          },
        })),
        edges: selectedEdges.map((edge) => ({ ...edge, selected: false })),
      };
    } else if (action === 'paste') {
      // Ctrl+V는 뷰포트 중앙. 패널 우클릭 붙여넣기도 동일하게 중앙 기준.
      pasteClipboard();
    }
    closeContextMenu();
  };

  const handleRun = async () => {
    const formattedNodes = {};
    nodes.forEach((n) => {
      formattedNodes[n.id] = {
        type: n.data.type,
        config: n.data.config,
      };
    });

    const formattedLinks = edges.map((e) => ({
      source: e.source,
      sourceHandle: e.sourceHandle || 'output_pin',
      target: e.target,
      targetHandle: e.targetHandle || 'input_pin',
    }));

    try {
      const res = await axios.post('http://127.0.0.1:8000/api/macro/run', {
        nodes: formattedNodes,
        links: formattedLinks,
      });
      if (res.data.status === 'error') {
        alert(res.data.message || '실행 실패');
      }
    } catch (e) {
      console.error(e);
      alert('Failed to start macro');
    }
  };

  const handleStop = async () => {
    try {
      await axios.post('http://127.0.0.1:8000/api/macro/stop');
    } catch (e) {
      console.error(e);
    }
  };

  const applyLoadedMacro = useCallback((macroData) => {
    pushHistory();
    const loadedNodes = (macroData.nodes || []).map((node) => ({
      ...node,
      data: {
        ...node.data,
        id: node.id,
        config: cloneConfig(node.data?.config),
        onChange: onNodeConfigChange,
      },
    }));
    syncIdCounter(loadedNodes);
    setNodes(loadedNodes);
    setEdges(macroData.edges || []);
  }, [onNodeConfigChange, setNodes, setEdges, pushHistory]);

  const performSave = useCallback(async (name, overwrite = false, generateBatch = false) => {
    const trimmed = (name || '').trim();
    if (!trimmed) {
      return;
    }
    try {
      const res = await axios.post('http://127.0.0.1:8000/api/scripts/save', {
        name: trimmed,
        overwrite,
        generate_batch: generateBatch,
        macro_data: sanitizeMacroPayload(nodesRef.current, edgesRef.current),
      });
      if (res.data.status === 'exists') {
        setSaveDialog({
          name: res.data.name || trimmed,
          overwriteConfirm: true,
          generateBatch,
        });
        return;
      }
      if (res.data.status === 'saved') {
        const macro = res.data.macro_data;
        if (macro?.nodes) {
          const synced = (macro.nodes || []).map((node) => ({
            ...node,
            data: {
              ...node.data,
              id: node.id,
              config: cloneConfig(node.data?.config),
              onChange: onNodeConfigChange,
            },
          }));
          setNodes(synced);
          setEdges(macro.edges || edgesRef.current);
        }
        setSaveDialog(null);
        setStatus(`저장됨: ${res.data.name || trimmed}`);
      } else {
        alert(res.data.message || '저장 실패');
      }
    } catch (e) {
      console.error(e);
      alert('저장 실패');
    }
  }, [onNodeConfigChange, setNodes, setEdges]);

  const openSaveDialog = () => {
    setSaveDialog({ name: 'macro_1', overwriteConfirm: false, generateBatch: false });
  };

  const openLoadDialog = async () => {
    try {
      const res = await axios.get('http://127.0.0.1:8000/api/scripts');
      const files = (res.data || []).filter((f) => typeof f === 'string');
      if (files.length === 0) {
        alert('저장된 매크로가 없습니다.');
        return;
      }
      setLoadDialog({ files, selected: files[0] });
    } catch (e) {
      console.error(e);
      alert('목록을 불러오지 못했습니다.');
    }
  };

  const confirmLoad = async () => {
    if (!loadDialog?.selected) {
      return;
    }
    try {
      const loadRes = await axios.post('http://127.0.0.1:8000/api/scripts/load', {
        path: loadDialog.selected,
      });
      if (loadRes.data.status === 'success') {
        applyLoadedMacro(loadRes.data.macro_data);
        setLoadDialog(null);
        setStatus(`불러옴: ${loadDialog.selected}`);
      } else {
        alert(loadRes.data.message || '불러오기 실패');
      }
    } catch (e) {
      console.error(e);
      alert('불러오기 실패');
    }
  };

  return (
    <div className="editor-container" ref={reactFlowWrapper}>
      <div className="topbar">
        <button type="button" className="action-button play" onClick={handleRun}>▶ Run</button>
        <button type="button" className="action-button stop" onClick={handleStop}>■ Stop</button>
        <button type="button" className="action-button" style={{ fontSize: '0.8rem', padding: '4px 10px' }} onClick={openSaveDialog}>💾 Save</button>
        <button type="button" className="action-button" style={{ fontSize: '0.8rem', padding: '4px 10px' }} onClick={openLoadDialog}>📂 Load</button>
        <div className="status-text">{status}</div>
      </div>

      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={handleNodesChange}
        onEdgesChange={handleEdgesChange}
        onConnect={onConnect}
        onInit={setReactFlowInstance}
        onDrop={onDrop}
        onDragOver={onDragOver}
        onPaneClick={closeContextMenu}
        onMoveStart={closeContextMenu}
        onNodeContextMenu={onNodeContextMenu}
        onEdgeContextMenu={onEdgeContextMenu}
        onPaneContextMenu={onPaneContextMenu}
        nodeTypes={nodeTypes}
        connectionRadius={36}
        deleteKeyCode={['Backspace', 'Delete']}
        multiSelectionKeyCode="Shift"
        selectionOnDrag
        selectionMode={SelectionMode.Partial}
        panOnDrag={[1]}
        selectNodesOnDrag={false}
        edgesFocusable
        edgesSelectable
        defaultEdgeOptions={{
          selectable: true,
          focusable: true,
          interactionWidth: 40,
        }}
        fitView
      >
        <Controls />
        <MiniMap
          pannable
          zoomable
          nodeColor={() => 'rgba(59, 130, 246, 0.5)'}
          maskColor="rgba(15, 23, 42, 0.8)"
          style={{ backgroundColor: 'rgba(30, 41, 59, 0.8)' }}
        />
        <Background variant="dots" gap={20} size={1} color="rgba(255,255,255,0.1)" />
      </ReactFlow>

      {contextMenu && (
        <div
          className="editor-context-menu"
          style={{ top: contextMenu.y, left: contextMenu.x }}
          onMouseDown={(event) => event.stopPropagation()}
        >
          {contextMenu.kind === 'node' && (
            <>
              <button type="button" onClick={() => handleContextAction('copy')}>복사</button>
              <button type="button" className="danger" onClick={() => handleContextAction('delete-nodes')}>삭제</button>
            </>
          )}
          {contextMenu.kind === 'edge' && (
            <button type="button" className="danger" onClick={() => handleContextAction('delete-edges')}>연결 해제</button>
          )}
          {contextMenu.kind === 'pane' && (
            <button
              type="button"
              disabled={clipboardRef.current.nodes.length === 0}
              onClick={() => handleContextAction('paste')}
            >
              붙여넣기
            </button>
          )}
        </div>
      )}

      {saveDialog && (
        <div className="editor-modal-backdrop" onMouseDown={() => setSaveDialog(null)}>
          <div
            className="editor-modal"
            onMouseDown={(event) => event.stopPropagation()}
            role="dialog"
            aria-label="매크로 저장"
          >
            {saveDialog.overwriteConfirm ? (
              <>
                <h3>덮어쓰기 확인</h3>
                <p>
                  <strong>{saveDialog.name}</strong> 매크로가 이미 있습니다. 덮어쓸까요?
                </p>
                <div className="editor-modal-actions">
                  <button type="button" onClick={() => setSaveDialog(null)}>취소</button>
                  <button
                    type="button"
                    className="primary"
                    onClick={() => performSave(saveDialog.name, true, saveDialog.generateBatch)}
                  >
                    덮어쓰기
                  </button>
                </div>
              </>
            ) : (
              <>
                <h3>매크로 저장</h3>
                <label className="editor-modal-field">
                  <span>이름</span>
                  <input
                    type="text"
                    value={saveDialog.name}
                    onChange={(event) => setSaveDialog({ ...saveDialog, name: event.target.value })}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter') {
                        performSave(saveDialog.name, false, saveDialog.generateBatch);
                      }
                    }}
                    autoFocus
                  />
                </label>
                <label className="editor-modal-check">
                  <input
                    type="checkbox"
                    checked={Boolean(saveDialog.generateBatch)}
                    onChange={(event) => setSaveDialog({ ...saveDialog, generateBatch: event.target.checked })}
                  />
                  <span>실행용 배치 파일 생성</span>
                </label>
                <p className="editor-modal-hint">
                  scripts/&lt;이름&gt;/&lt;이름&gt;.json + imgs/
                </p>
                <div className="editor-modal-actions">
                  <button type="button" onClick={() => setSaveDialog(null)}>취소</button>
                  <button type="button" className="primary" onClick={() => performSave(saveDialog.name, false, saveDialog.generateBatch)}>
                    저장
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}

      {loadDialog && (
        <div className="editor-modal-backdrop" onMouseDown={() => setLoadDialog(null)}>
          <div
            className="editor-modal"
            onMouseDown={(event) => event.stopPropagation()}
            role="dialog"
            aria-label="매크로 불러오기"
          >
            <h3>매크로 불러오기</h3>
            <label className="editor-modal-field">
              <span>파일</span>
              <select
                value={loadDialog.selected}
                onChange={(event) => setLoadDialog({ ...loadDialog, selected: event.target.value })}
                size={Math.min(8, Math.max(3, loadDialog.files.length))}
              >
                {loadDialog.files.map((file) => (
                  <option key={file} value={file}>{file}</option>
                ))}
              </select>
            </label>
            <div className="editor-modal-actions">
              <button type="button" onClick={() => setLoadDialog(null)}>취소</button>
              <button type="button" className="primary" onClick={confirmLoad}>불러오기</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default NodeEditor;

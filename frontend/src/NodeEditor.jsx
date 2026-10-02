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
import { api, websocketUrl } from './api';
import GenericNode from './GenericNode';
import { emitNodeUpdate } from './nodeUpdateBus';
import { fieldLabel, nodeLabel, t } from './i18n';
import { DRAFT_KEY, graphFingerprint, makeDraft, parseDraft } from './draft';

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

const formatTemplate = (message, params = {}) => Object.entries(params).reduce(
  (text, [key, value]) => text.replaceAll(`{${key}}`, String(value)),
  message,
);

const isEditableTarget = (target) => {
  if (!target || !(target instanceof Element)) {
    return false;
  }
  return Boolean(target.closest('input, textarea, select, [contenteditable="true"]'));
};

const MAX_HISTORY = 40;
const TUTORIAL_KEY = 'd5macro-tutorial-v1';
const DEFAULT_APP_SETTINGS = {
  record_stop_key: 'f8',
  panic_stop_key: 'esc',
  hotkey_choices: ['esc', 'pause', ...Array.from({ length: 12 }, (_, index) => `f${index + 1}`)],
};

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

const NodeEditor = ({ currentLanguage, onLanguageChange }) => {
  const reactFlowWrapper = useRef(null);
  const clipboardRef = useRef({ nodes: [], edges: [] });
  const nodesRef = useRef([]);
  const edgesRef = useRef([]);
  const undoStackRef = useRef([]);
  const redoStackRef = useRef([]);
  const isRestoringRef = useRef(false);
  const historyLockRef = useRef(false);
  const logIdRef = useRef(0);
  const draftTimerRef = useRef(null);
  const isLockedRef = useRef(false);
  const settingsRef = useRef(DEFAULT_APP_SETTINGS);
  const cleanGraphRef = useRef(graphFingerprint({ nodes: [], edges: [] }));
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const [reactFlowInstance, setReactFlowInstance] = useState(null);
  const [status, setStatus] = useState(t('idle'));
  const [contextMenu, setContextMenu] = useState(null);
  const [saveDialog, setSaveDialog] = useState(null); // { name, overwriteConfirm }
  const [loadDialog, setLoadDialog] = useState(null); // { files, selected }
  const [logs, setLogs] = useState([]);
  const [showLogs, setShowLogs] = useState(false);
  const [draftReady, setDraftReady] = useState(false);
  const [isDirty, setIsDirty] = useState(false);
  const [isRunning, setIsRunning] = useState(false);
  const [recordingPhase, setRecordingPhase] = useState('idle');
  const [recordingResult, setRecordingResult] = useState(null);
  const [tutorialPage, setTutorialPage] = useState(null);
  const [appSettings, setAppSettings] = useState(DEFAULT_APP_SETTINGS);
  const [settingsDialog, setSettingsDialog] = useState(null);
  const isLocked = isRunning || recordingPhase !== 'idle';

  const formatHotkeys = (message) => message
    .replace('{recordStop}', appSettings.record_stop_key.toUpperCase())
    .replace('{panicStop}', appSettings.panic_stop_key.toUpperCase());

  const localizeBackendMessage = useCallback((message) => {
    if (!message || currentLanguage !== 'en') return message;
    const exact = {
      "창 기준 좌표에 필요한 '창 선택' 노드가 실행되지 않았습니다.": 'A Select window node must run before using window-relative coordinates.',
      '마우스 이동 기록이 비어 있습니다.': 'The recorded mouse movement is empty.',
      '마우스 이동 기록이 너무 깁니다.': 'The recorded mouse movement is too long.',
      '마우스 이동 기록 형식이 올바르지 않습니다.': 'The recorded mouse movement has an invalid format.',
      '마우스 이동 기록에 잘못된 수치가 있습니다.': 'The recorded mouse movement contains an invalid value.',
    };
    if (exact[message]) return exact[message];
    let match = /^프로그램 또는 파일을 실행하지 못했습니다: (.+)$/.exec(message);
    if (match) return `Could not launch the program or file: ${match[1]}`;
    match = /^(\S+)초 안에 창을 찾을 수 없습니다: (.*)$/.exec(message);
    if (match) return `Could not find the window within ${match[1]}s: ${match[2]}`;
    match = /^이미지 탐색 오류: (.+)$/.exec(message);
    if (match) return `Image search error: ${match[1]}`;
    return message;
  }, [currentLanguage]);

  const localizeValidationIssue = useCallback((issue) => {
    if (currentLanguage !== 'en') return issue.message;
    const [code, field] = String(issue.code || '').split(':');
    const fieldName = field ? fieldLabel(field, field) : '';
    const translations = {
      unsupported_node: 'This node type is not supported.', invalid_config: 'The node configuration is invalid.',
      invalid_option: `The selected value for '${fieldName}' is invalid.`, invalid_number: `'${fieldName}' must be a number.`,
      number_min: `'${fieldName}' is below its minimum value.`, number_max: `'${fieldName}' is above its maximum value.`,
      window_title: 'Enter a window title.', launch_path: 'Enter a file, document, or URL to launch.',
      launch_missing: 'The file or document to launch could not be found.', image_required: 'Capture or select an image to find.',
      image_missing: 'The image file could not be found.', empty_keyboard: 'The key or text input is empty.',
      empty_mouse_sequence: 'The recorded mouse movement is empty.', mouse_sequence_too_long: 'The recorded mouse movement is too long.',
      invalid_mouse_sequence: 'The recorded mouse movement is invalid.', start_count: 'A macro must contain exactly one Start node.',
      invalid_link: 'The connection data is invalid.', broken_link: 'A connection points to a missing node.',
      invalid_output: 'An output connection does not match its node type.', duplicate_output: 'An output pin has more than one connection.',
      unreachable: 'This node cannot be reached from the Start node.', empty_macro: 'The Start node is not connected to another node.',
      missing_position: 'No preceding coordinate or image is set, so the previous pointer position may be used.',
      missing_window: 'A Select window node is required before window-relative coordinates.',
      cycle_without_loop: 'A cycle without a Loop node may run indefinitely.',
    };
    return translations[code] || issue.message;
  }, [currentLanguage]);

  const tutorialPages = [
    { title: t('tutorialCreateTitle'), body: t('tutorialCreateBody'), items: [t('tutorialCreateRecord'), t('tutorialCreateNodes')] },
    { title: t('tutorialFlowTitle'), body: t('tutorialFlowBody'), items: [t('tutorialFlowExample'), t('tutorialFlowHint')] },
    { title: t('tutorialRunTitle'), body: t('tutorialRunBody'), items: [t('tutorialRunStart'), formatHotkeys(t('tutorialRunStop')), t('tutorialRunLog')] },
    { title: t('tutorialSaveTitle'), body: t('tutorialSaveBody'), items: [t('tutorialSaveScript'), t('tutorialSaveBatch')] },
    { title: t('tutorialPracticeTitle'), body: t('tutorialPracticeBody'), items: [t('tutorialPracticeOne'), formatHotkeys(t('tutorialPracticeTwo')), t('tutorialPracticeThree'), t('tutorialPracticeFour')] },
  ];

  useEffect(() => {
    if (!localStorage.getItem(TUTORIAL_KEY)) {
      setTutorialPage(0);
    }
  }, []);

  const closeTutorial = () => {
    localStorage.setItem(TUTORIAL_KEY, 'done');
    setTutorialPage(null);
  };

  useEffect(() => {
    isLockedRef.current = isLocked;
  }, [isLocked]);

  useEffect(() => {
    settingsRef.current = appSettings;
  }, [appSettings]);

  useEffect(() => {
    api.get('/health')
      .then((res) => {
        setIsRunning(Boolean(res.data.running));
        if (res.data.recording) setRecordingPhase('recording');
      })
      .catch(() => {});
    api.get('/settings')
      .then((res) => setAppSettings({ ...DEFAULT_APP_SETTINGS, ...res.data }))
      .catch(() => {});
  }, []);

  const appendLog = useCallback((message, level = 'info') => {
    if (!message) return;
    const entry = {
      id: ++logIdRef.current,
      time: new Date().toLocaleTimeString(),
      message,
      level,
    };
    setLogs((items) => [...items.slice(-299), entry]);
  }, []);

  const markClean = useCallback((graph) => {
    clearTimeout(draftTimerRef.current);
    cleanGraphRef.current = graphFingerprint(sanitizeMacroPayload(graph.nodes, graph.edges));
    setIsDirty(false);
    localStorage.removeItem(DRAFT_KEY);
  }, []);

  useEffect(() => {
    nodesRef.current = nodes;
  }, [nodes]);

  useEffect(() => {
    edgesRef.current = edges;
  }, [edges]);

  useEffect(() => {
    if (!draftReady) return undefined;
    const graph = sanitizeMacroPayload(nodes, edges);
    const dirty = graphFingerprint(graph) !== cleanGraphRef.current;
    setIsDirty(dirty);
    clearTimeout(draftTimerRef.current);
    if (!dirty) {
      localStorage.removeItem(DRAFT_KEY);
      return undefined;
    }
    draftTimerRef.current = setTimeout(() => {
      localStorage.setItem(DRAFT_KEY, JSON.stringify(makeDraft(graph)));
    }, 500);
    return () => clearTimeout(draftTimerRef.current);
  }, [nodes, edges, draftReady]);

  useEffect(() => {
    const warnBeforeClose = (event) => {
      if (!isDirty) return;
      event.preventDefault();
      event.returnValue = '';
    };
    window.addEventListener('beforeunload', warnBeforeClose);
    return () => window.removeEventListener('beforeunload', warnBeforeClose);
  }, [isDirty]);

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
    let ws;
    let reconnectTimer;
    let disposed = false;
    const connect = () => {
      ws = new WebSocket(websocketUrl());
      ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.type === 'status') {
        const params = { ...data.params };
        if (params.node_type) params.node = nodeLabel(params.node_type, params.node_type);
        if (params.error) params.error = localizeBackendMessage(params.error);
        const message = data.key ? formatTemplate(t(data.key), params) : localizeBackendMessage(data.message);
        setStatus(message);
        if (!['status_running_node', 'status_window_waiting', 'status_next_action'].includes(data.key)) {
          appendLog(message, data.key === 'status_macro_error' ? 'error' : 'info');
        }
      } else if (data.type === 'execution') {
        if (data.phase === 'reset') {
          setLogs([]);
          setIsRunning(true);
          setContextMenu(null);
        } else if (data.phase === 'finished') {
          setIsRunning(false);
        } else {
          const node = nodesRef.current.find((item) => item.id === data.node_id);
          const label = nodeLabel(node?.data?.type, node?.data?.label || data.node_id);
          appendLog(`${label}: ${t(`phase_${data.phase}`)}${data.message ? ` — ${localizeBackendMessage(data.message)}` : ''}`, data.phase === 'error' ? 'error' : data.phase);
        }
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
                executionMessage: localizeBackendMessage(data.message) || null,
              },
            };
          }
          return node;
        }));
      } else if (data.type === 'recorder') {
        if (data.phase === 'countdown') {
          setRecordingPhase('countdown');
          setStatus(t('recordCountdownValue').replace('{seconds}', Math.ceil(Number(data.seconds) || 0)));
          setContextMenu(null);
        } else if (data.phase === 'started') {
          setRecordingPhase('recording');
          setStatus(t('recordingF8').replace('{key}', settingsRef.current.record_stop_key.toUpperCase()));
        } else if (data.phase === 'complete') {
          setRecordingPhase('idle');
          setRecordingResult(data);
          setStatus(t('recordComplete'));
        } else if (data.phase === 'cancelled') {
          setRecordingPhase('idle');
          setStatus(t('recordCancelled'));
        }
      } else if (data.type === 'capture_complete') {
        const stamp = Date.now();
        const patch = {
          image_path: data.file_path,
          image_url: `${data.url}?t=${stamp}`,
        };
        emitNodeUpdate(data.node_id, {
          revision: stamp,
          config: patch,
          hint: t('captureDone'),
          capturePending: false,
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
          hint: t('regionDone'),
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
          hint: `${t('coordinateSaved')}: (${data.x}, ${data.y})`,
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
          hint: t('coordinateCancelled'),
        });
      }
      };
      ws.onclose = (event) => {
        if (disposed) return;
        if (event.code === 1008 && !sessionStorage.getItem('d5macro-auth-reload')) {
          sessionStorage.setItem('d5macro-auth-reload', '1');
          window.location.replace(`/?refresh=${Date.now()}`);
          return;
        }
        reconnectTimer = window.setTimeout(connect, 1000);
      };
    };
    connect();
    return () => {
      disposed = true;
      window.clearTimeout(reconnectTimer);
      ws?.close();
    };
  }, [setNodes, appendLog, localizeBackendMessage]);

  const handleLanguageChange = (event) => {
    const wasIdle = status === t('idle');
    onLanguageChange(event.target.value);
    if (wasIdle) setStatus(t('idle'));
    setNodes((items) => items.map((node) => ({ ...node, data: { ...node.data } })));
  };

  const closeContextMenu = useCallback(() => setContextMenu(null), []);

  const onConnect = useCallback((params) => {
    if (isLockedRef.current) return;
    pushHistory();
    setEdges((eds) => addEdge(params, eds));
  }, [setEdges, pushHistory]);

  const onDragOver = useCallback((event) => {
    event.preventDefault();
    event.dataTransfer.dropEffect = 'move';
  }, []);

  const onNodeConfigChange = useCallback((nodeId, keyOrPatch, value) => {
    if (isLockedRef.current) return;
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

  useEffect(() => {
    try {
      const raw = localStorage.getItem(DRAFT_KEY);
      if (raw) {
        const draft = parseDraft(raw);
        const savedAt = new Date(draft.saved_at).toLocaleString();
        if (window.confirm(`${t('recoverDraft')}\n${savedAt}`)) {
          applySnapshot(draft.graph);
          setStatus(t('draftRestored'));
        } else {
          localStorage.removeItem(DRAFT_KEY);
        }
      }
    } catch (error) {
      console.warn('Discarding invalid draft', error);
      localStorage.removeItem(DRAFT_KEY);
    } finally {
      setDraftReady(true);
    }
  }, [applySnapshot]);

  const handleNodesChange = useCallback((changes) => {
    if (isLocked) return;
    if (changes.some((change) => change.type === 'remove')) {
      pushHistory();
    }
    onNodesChange(changes);
  }, [isLocked, onNodesChange, pushHistory]);

  const handleEdgesChange = useCallback((changes) => {
    if (isLocked) return;
    if (changes.some((change) => change.type === 'remove')) {
      pushHistory();
    }
    onEdgesChange(changes);
  }, [isLocked, onEdgesChange, pushHistory]);

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
      if (isLocked) return;
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
  }, [isLocked, copySelection, pasteClipboard, undo, redo]);

  const onDrop = useCallback(
    (event) => {
      event.preventDefault();
      if (isLocked) return;

      const type = event.dataTransfer.getData('application/reactflow');
      const label = event.dataTransfer.getData('application/reactflow/label');
      const schemaRaw = event.dataTransfer.getData('application/reactflow/schema');
      let schema = {};
      try {
        schema = JSON.parse(schemaRaw);
      } catch {
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
    [isLocked, reactFlowInstance, onNodeConfigChange, setNodes, pushHistory]
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
      nodeId: node.id,
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
    if (isLocked) {
      event.preventDefault();
      return;
    }
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
  }, [isLocked, edges, openEdgeContextMenu]);

  const handleContextAction = (action) => {
    if (isLocked || !contextMenu) {
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

  const handleRun = async (startNodeId = null) => {
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

    const payload = { nodes: formattedNodes, links: formattedLinks, start_node_id: startNodeId };
    const showValidationIssues = (issues) => {
      const issueByNode = new Map();
      (issues || []).forEach((issue) => {
        appendLog(`${issue.level === 'error' ? t('validationError') : t('validationWarning')}: ${localizeValidationIssue(issue)}`, issue.level);
        if (issue.node_id && (issue.level === 'error' || !issueByNode.has(issue.node_id))) {
          issueByNode.set(issue.node_id, issue);
        }
      });
      setNodes((current) => current.map((node) => {
        const issue = issueByNode.get(node.id);
        return {
          ...node,
          data: {
            ...node.data,
            executionState: issue?.level || null,
            executionMessage: issue ? localizeValidationIssue(issue) : null,
          },
        };
      }));
      setShowLogs(true);
    };

    try {
      let res = await api.post('/macro/run', payload);
      if (res.data.status === 'started') setIsRunning(true);
      if (res.data.status === 'validation_error') {
        showValidationIssues(res.data.issues);
        setStatus(t('validationFailed'));
        alert(t('validationFailed'));
      } else if (res.data.status === 'validation_warning') {
        showValidationIssues(res.data.issues);
        setStatus(t('validationWarning'));
        if (window.confirm(t('validationWarningConfirm'))) {
          res = await api.post('/macro/run', { ...payload, allow_warnings: true });
          if (res.data.status === 'started') setIsRunning(true);
          if (res.data.status === 'error') {
            alert(res.data.message || t('runFailed'));
          }
        }
      } else if (res.data.status === 'error') {
        alert(res.data.message || t('runFailed'));
      }
    } catch (e) {
      console.error(e);
      alert(t('runFailed'));
    }
  };

  const handleStop = async () => {
    try {
      await api.post('/macro/stop');
    } catch (e) {
      console.error(e);
    }
  };

  const handleResetEditor = () => {
    if (isLocked || (!nodes.length && !edges.length) || !window.confirm(t('resetEditorConfirm'))) {
      return;
    }
    pushHistory();
    setNodes([]);
    setEdges([]);
    setContextMenu(null);
    setStatus(t('idle'));
  };

  const handleRecord = async () => {
    try {
      if (recordingPhase !== 'idle') {
        await api.post('/recorder/stop');
        return;
      }
      setRecordingResult(null);
      const res = await api.post('/recorder/start');
      if (res.data.status === 'error') {
        alert(res.data.message || t('recordFailed'));
        return;
      }
      setRecordingPhase('countdown');
      setStatus(t('recordCountdown'));
    } catch (error) {
      console.error(error);
      setRecordingPhase('idle');
      alert(t('recordFailed'));
    }
  };

  const saveAppSettings = async () => {
    if (!settingsDialog) return;
    if (settingsDialog.record_stop_key === settingsDialog.panic_stop_key) {
      alert(t('hotkeySettingsHint'));
      return;
    }
    try {
      const res = await api.post('/settings', {
        record_stop_key: settingsDialog.record_stop_key,
        panic_stop_key: settingsDialog.panic_stop_key,
      });
      setAppSettings({ ...DEFAULT_APP_SETTINGS, ...res.data });
      setSettingsDialog(null);
    } catch (error) {
      console.error(error);
      alert(error.response?.data?.message || t('settingsSaveFailed'));
    }
  };

  const applyRecording = async () => {
    const steps = recordingResult?.steps || [];
    try {
      const res = await api.get('/nodes/types');
      const definitions = new Map(res.data.map((item) => [item.type, item]));
      pushHistory();
      const recordedNodes = steps.map((step, index) => {
        const definition = definitions.get(step.type) || {};
        const nodeId = getId();
        const defaults = {};
        Object.entries(definition.schema || {}).forEach(([key, field]) => {
          if (field?.default !== undefined) defaults[key] = field.default;
        });
        return {
          id: nodeId,
          type: 'customNode',
          position: { x: 120, y: 80 + index * 240 },
          data: {
            id: nodeId,
            type: step.type,
            label: nodeLabel(step.type, definition.label || step.type),
            configSchema: definition.schema || {},
            config: { ...defaults, ...(step.config || {}) },
            onChange: onNodeConfigChange,
          },
        };
      });
      const recordedEdges = recordedNodes.slice(1).map((node, index) => ({
        id: `e_recorded_${recordedNodes[index].id}_${node.id}`,
        source: recordedNodes[index].id,
        sourceHandle: 'output_pin',
        target: node.id,
        targetHandle: 'input_pin',
      }));
      setNodes(recordedNodes);
      setEdges(recordedEdges);
      setRecordingResult(null);
      setStatus(t('recordApplied'));
      requestAnimationFrame(() => reactFlowInstance?.fitView({ padding: 0.2 }));
    } catch (error) {
      console.error(error);
      alert(t('recordApplyFailed'));
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
    const loadedEdges = macroData.edges || [];
    setEdges(loadedEdges);
    markClean({ nodes: loadedNodes, edges: loadedEdges });
  }, [onNodeConfigChange, setNodes, setEdges, pushHistory, markClean]);

  const performSave = useCallback(async (name, overwrite = false, generateBatch = false) => {
    const trimmed = (name || '').trim();
    if (!trimmed) {
      return;
    }
    try {
      const res = await api.post('/scripts/save', {
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
          const syncedEdges = macro.edges || edgesRef.current;
          setNodes(synced);
          setEdges(syncedEdges);
          markClean({ nodes: synced, edges: syncedEdges });
        }
        setSaveDialog(null);
        setStatus(`${t('saved')}: ${res.data.name || trimmed}`);
      } else {
        alert(res.data.message || t('saveFailed'));
      }
    } catch (e) {
      console.error(e);
      alert(t('saveFailed'));
    }
  }, [onNodeConfigChange, setNodes, setEdges, markClean]);

  const openSaveDialog = () => {
    setSaveDialog({ name: 'macro_1', overwriteConfirm: false, generateBatch: false });
  };

  const openLoadDialog = async () => {
    try {
      const res = await api.get('/scripts');
      const files = (res.data || []).filter((f) => typeof f === 'string');
      if (files.length === 0) {
        alert(t('noScripts'));
        return;
      }
      setLoadDialog({ files, selected: files[0] });
    } catch (e) {
      console.error(e);
      alert(t('loadListFailed'));
    }
  };

  const openScriptsFolder = async () => {
    try {
      await api.post('/scripts/open-folder');
    } catch (error) {
      console.error(error);
      alert(t('openFolderFailed'));
    }
  };

  const confirmLoad = async () => {
    if (!loadDialog?.selected) {
      return;
    }
    if (isDirty && !window.confirm(t('discardUnsaved'))) {
      return;
    }
    try {
      let loadRes = await api.post('/scripts/load', {
        path: loadDialog.selected,
      });
      if (loadRes.data.status === 'warning' && window.confirm(loadRes.data.message)) {
        loadRes = await api.post('/scripts/load', { path: loadDialog.selected, force: true });
      }
      if (loadRes.data.status === 'success') {
        applyLoadedMacro(loadRes.data.macro_data);
        setLoadDialog(null);
        setStatus(`${t('loaded')}: ${loadDialog.selected}`);
      } else {
        alert(loadRes.data.message || t('loadFailed'));
      }
    } catch (e) {
      console.error(e);
      alert(t('loadFailed'));
    }
  };

  const deleteSelectedScript = async () => {
    const selected = loadDialog?.selected;
    if (!selected || !window.confirm(t('deleteScriptConfirm').replace('{name}', selected))) {
      return;
    }
    try {
      const res = await api.post('/scripts/delete', { path: selected });
      if (res.data.status !== 'deleted') {
        alert(res.data.message || t('deleteScriptFailed'));
        return;
      }
      const files = loadDialog.files.filter((file) => file !== selected);
      setStatus(`${t('deleted')}: ${selected}`);
      setLoadDialog(files.length ? { files, selected: files[0] } : null);
    } catch (error) {
      console.error(error);
      alert(error.response?.data?.message || t('deleteScriptFailed'));
    }
  };

  return (
    <div className={`editor-container${isLocked ? ' graph-locked' : ''}`} ref={reactFlowWrapper}>
      <div className="topbar">
        <button type="button" className="action-button play" onClick={() => handleRun()} disabled={isLocked}>▶ {t('run')}</button>
        <button type="button" className="action-button stop" onClick={handleStop}>■ {t('stop')}</button>
        <button type="button" className={`action-button record${recordingPhase !== 'idle' ? ' is-active' : ''}`} onClick={handleRecord} disabled={isRunning}>● {recordingPhase === 'idle' ? t('record') : t('recordStop')}</button>
        <button type="button" className="action-button" title={isDirty ? t('unsavedChanges') : ''} style={{ fontSize: '0.8rem', padding: '4px 10px' }} onClick={openSaveDialog} disabled={isLocked}>💾 {t('save')}{isDirty ? ' *' : ''}</button>
        <button type="button" className="action-button" style={{ fontSize: '0.8rem', padding: '4px 10px' }} onClick={openLoadDialog} disabled={isLocked}>📂 {t('load')}</button>
        <button type="button" className="action-button compact" onClick={openScriptsFolder}>📁 {t('openFolder')}</button>
        <button type="button" className="action-button compact" onClick={handleResetEditor} disabled={isLocked}>↺ {t('resetEditor')}</button>
        <div className="status-text">{status}</div>
        <button type="button" className="action-button compact" onClick={() => setShowLogs((value) => !value)}>📋 {t('logs')} ({logs.length})</button>
        <button type="button" className="action-button compact" onClick={() => setTutorialPage(0)}>❓ {t('help')}</button>
        <button type="button" className="action-button compact" onClick={() => setSettingsDialog({ ...appSettings })} disabled={isLocked}>⚙ {t('settings')}</button>
        <select
          className="language-select"
          aria-label="Language"
          value={currentLanguage}
          onChange={handleLanguageChange}
        >
          <option value="ko">한국어</option>
          <option value="en">English</option>
        </select>
      </div>

      {showLogs && (
        <section className="execution-log" aria-label={t('logs')}>
          <header>
            <strong>{t('executionLog')}</strong>
            <button type="button" onClick={() => setLogs([])}>{t('clear')}</button>
          </header>
          <div className="execution-log-list">
            {logs.length === 0 && <div className="execution-log-empty">{t('noLogs')}</div>}
            {logs.map((entry) => (
              <div key={entry.id} className={`execution-log-entry ${entry.level}`}>
                <time>{entry.time}</time>
                <span>{entry.message}</span>
              </div>
            ))}
          </div>
        </section>
      )}

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
        deleteKeyCode={isLocked ? null : ['Backspace', 'Delete']}
        nodesDraggable={!isLocked}
        nodesConnectable={!isLocked}
        elementsSelectable={!isLocked}
        multiSelectionKeyCode="Shift"
        selectionOnDrag
        selectionMode={SelectionMode.Partial}
        panOnDrag={[1]}
        selectNodesOnDrag={false}
        edgesFocusable={!isLocked}
        edgesSelectable={!isLocked}
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
              <button
                type="button"
                onClick={() => {
                  const nodeId = contextMenu.nodeId;
                  closeContextMenu();
                  handleRun(nodeId);
                }}
              >
                ▶ {t('runFromHere')}
              </button>
              <button type="button" onClick={() => handleContextAction('copy')}>{t('copy')}</button>
              <button type="button" className="danger" onClick={() => handleContextAction('delete-nodes')}>{t('delete')}</button>
            </>
          )}
          {contextMenu.kind === 'edge' && (
            <button type="button" className="danger" onClick={() => handleContextAction('delete-edges')}>{t('disconnect')}</button>
          )}
          {contextMenu.kind === 'pane' && (
            <button
              type="button"
              disabled={clipboardRef.current.nodes.length === 0}
              onClick={() => handleContextAction('paste')}
            >
              {t('paste')}
            </button>
          )}
        </div>
      )}

      {settingsDialog && (
        <div className="editor-modal-backdrop" onMouseDown={() => setSettingsDialog(null)}>
          <div className="editor-modal" onMouseDown={(event) => event.stopPropagation()} role="dialog" aria-label={t('hotkeySettings')}>
            <h3>{t('hotkeySettings')}</h3>
            <label className="editor-modal-field">
              <span>{t('recordStopKey')}</span>
              <select value={settingsDialog.record_stop_key} onChange={(event) => setSettingsDialog({ ...settingsDialog, record_stop_key: event.target.value })}>
                {settingsDialog.hotkey_choices.map((key) => <option key={key} value={key}>{key.toUpperCase()}</option>)}
              </select>
            </label>
            <label className="editor-modal-field">
              <span>{t('panicStopKey')}</span>
              <select value={settingsDialog.panic_stop_key} onChange={(event) => setSettingsDialog({ ...settingsDialog, panic_stop_key: event.target.value })}>
                {settingsDialog.hotkey_choices.map((key) => <option key={key} value={key}>{key.toUpperCase()}</option>)}
              </select>
            </label>
            <p className="editor-modal-hint">{t('hotkeySettingsHint')}</p>
            <p className="editor-modal-hint">
              {t('developerContact')}: <a href="mailto:yanche2990@gmail.com">yanche2990@gmail.com</a>
            </p>
            <div className="editor-modal-actions">
              <button type="button" onClick={() => setSettingsDialog(null)}>{t('cancel')}</button>
              <button type="button" className="primary" onClick={saveAppSettings}>{t('save')}</button>
            </div>
          </div>
        </div>
      )}

      {tutorialPage !== null && (
        <div className="editor-modal-backdrop">
          <div className="editor-modal tutorial-modal" role="dialog" aria-label={t('tutorialTitle')}>
            <div className="tutorial-progress">
              {tutorialPages.map((_, index) => (
                <span key={index} className={index === tutorialPage ? 'active' : ''} />
              ))}
            </div>
            <div className="tutorial-step">{tutorialPage + 1} / {tutorialPages.length}</div>
            <h3>{tutorialPages[tutorialPage].title}</h3>
            <p>{tutorialPages[tutorialPage].body}</p>
            <ul className="tutorial-list">
              {tutorialPages[tutorialPage].items.map((item) => <li key={item}>{item}</li>)}
            </ul>
            <p className="editor-modal-hint">{t('tutorialNodeHelpHint')}</p>
            <div className="editor-modal-actions tutorial-actions">
              <button type="button" onClick={closeTutorial}>{t('skip')}</button>
              {tutorialPage > 0 && <button type="button" onClick={() => setTutorialPage((page) => page - 1)}>{t('previous')}</button>}
              {tutorialPage < tutorialPages.length - 1 ? (
                <button type="button" className="primary" onClick={() => setTutorialPage((page) => page + 1)}>{t('next')}</button>
              ) : (
                <button type="button" className="primary" onClick={closeTutorial}>{t('tryIt')}</button>
              )}
            </div>
          </div>
        </div>
      )}

      {saveDialog && (
        <div className="editor-modal-backdrop" onMouseDown={() => setSaveDialog(null)}>
          <div
            className="editor-modal"
            onMouseDown={(event) => event.stopPropagation()}
            role="dialog"
            aria-label={t('saveTitle')}
          >
            {saveDialog.overwriteConfirm ? (
              <>
                <h3>{t('overwriteTitle')}</h3>
                <p>
                  <strong>{saveDialog.name}</strong> {t('overwriteQuestion')}
                </p>
                <div className="editor-modal-actions">
                  <button type="button" onClick={() => setSaveDialog(null)}>{t('cancel')}</button>
                  <button
                    type="button"
                    className="primary"
                    onClick={() => performSave(saveDialog.name, true, saveDialog.generateBatch)}
                  >
                    {t('overwrite')}
                  </button>
                </div>
              </>
            ) : (
              <>
                <h3>{t('saveTitle')}</h3>
                <label className="editor-modal-field">
                  <span>{t('name')}</span>
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
                  <span>{t('createBatch')}</span>
                </label>
                <p className="editor-modal-hint">
                  scripts/&lt;이름&gt;/&lt;이름&gt;.json + imgs/
                </p>
                <div className="editor-modal-actions">
                  <button type="button" onClick={() => setSaveDialog(null)}>{t('cancel')}</button>
                  <button type="button" className="primary" onClick={() => performSave(saveDialog.name, false, saveDialog.generateBatch)}>
                    {t('save')}
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
            aria-label={t('loadTitle')}
          >
            <h3>{t('loadTitle')}</h3>
            <label className="editor-modal-field">
              <span>{t('file')}</span>
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
              <button type="button" className="danger" onClick={deleteSelectedScript}>{t('delete')}</button>
              <button type="button" onClick={() => setLoadDialog(null)}>{t('cancel')}</button>
              <button type="button" className="primary" onClick={confirmLoad}>{t('load')}</button>
            </div>
          </div>
        </div>
      )}

      {recordingResult && (
        <div className="editor-modal-backdrop">
          <div className="editor-modal" role="dialog" aria-label={t('recordResultTitle')}>
            <h3>{t('recordResultTitle')}</h3>
            <p>{t('recordResultSummary')
              .replace('{seconds}', recordingResult.duration)
              .replace('{events}', recordingResult.event_count)
              .replace('{nodes}', recordingResult.steps?.length || 0)}</p>
            <p className="editor-modal-hint">{t('recordReplaceWarning')}</p>
            <div className="editor-modal-actions">
              <button type="button" onClick={() => setRecordingResult(null)}>{t('discard')}</button>
              <button type="button" className="primary" onClick={applyRecording}>{t('apply')}</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default NodeEditor;

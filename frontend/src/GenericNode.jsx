import React, { useEffect, useRef, useState } from 'react';
import { Handle, Position } from '@xyflow/react';
import { api } from './api';
import { subscribeNodeUpdate } from './nodeUpdateBus';
import { fieldLabel, nodeLabel, optionLabel, t } from './i18n';

const FieldControl = ({ field, keyName, value, onChange }) => {
  const [draftValue, setDraftValue] = useState(value);
  const [isFocused, setIsFocused] = useState(false);
  const composingRef = useRef(false);

  useEffect(() => {
    if (!isFocused && !composingRef.current) {
      setDraftValue(value);
    }
  }, [value, isFocused]);

  const updateValue = (nextValue) => {
    setDraftValue(nextValue);
    onChange(keyName, nextValue);
  };

  const stopPropagation = (event) => event.stopPropagation();

  const compositionProps = {
    onCompositionStart: () => {
      composingRef.current = true;
    },
    onCompositionEnd: (event) => {
      composingRef.current = false;
      updateValue(event.target.value);
    },
  };

  if (field.type === 'select') {
    return (
      <select
        className="node-select nodrag"
        value={draftValue ?? ''}
        onMouseDown={stopPropagation}
        onChange={(e) => updateValue(e.target.value)}
      >
        {(field.options || []).map((opt) => (
          <option key={opt} value={opt}>{optionLabel(opt)}</option>
        ))}
      </select>
    );
  }

  if (field.type === 'checkbox' || field.type === 'boolean') {
    return (
      <label className="node-checkbox nodrag" onMouseDown={stopPropagation}>
        <input
          type="checkbox"
          checked={Boolean(draftValue)}
          onChange={(e) => updateValue(e.target.checked)}
        />
        <span>{t('enabled')}</span>
      </label>
    );
  }

  if (field.type === 'number') {
    const fallback = field.default !== undefined && field.default !== null
      ? Number(field.default)
      : 0;

    const commitNumber = () => {
      const raw = String(draftValue ?? '').trim();
      let next = raw === '' || Number.isNaN(Number(raw)) ? fallback : Number(raw);
      if (field.min !== undefined && !Number.isNaN(Number(field.min))) {
        next = Math.max(Number(field.min), next);
      }
      if (field.max !== undefined && !Number.isNaN(Number(field.max))) {
        next = Math.min(Number(field.max), next);
      }
      setDraftValue(next);
      onChange(keyName, next);
    };

    const displayValue = isFocused
      ? (draftValue === null || draftValue === undefined ? '' : draftValue)
      : (value ?? fallback);

    return (
      <input
        type="number"
        inputMode="decimal"
        step={field.step ?? 1}
        className="node-input nodrag"
        value={displayValue}
        onMouseDown={stopPropagation}
        onFocus={() => {
          setIsFocused(true);
          setDraftValue(value ?? fallback);
        }}
        onBlur={() => {
          commitNumber();
          setIsFocused(false);
        }}
        onKeyDown={(event) => {
          stopPropagation(event);
          if (event.key === 'Enter') {
            event.currentTarget.blur();
          }
        }}
        onChange={(e) => {
          // 타이핑 중에는 문자열 draft만 유지. blur/Enter에서 숫자 커밋.
          setDraftValue(e.target.value);
        }}
      />
    );
  }

  if (field.type === 'text' && field.multiline) {
    return (
      <textarea
        className="node-textarea nodrag nowheel"
        value={draftValue ?? ''}
        onMouseDown={stopPropagation}
        onKeyDown={stopPropagation}
        rows={4}
        {...compositionProps}
        onChange={(e) => {
          setDraftValue(e.target.value);
          // 한글 IME 조합 중에는 부모로 올리지 않아 글자가 깨지지 않게 함
          if (!composingRef.current) {
            onChange(keyName, e.target.value);
          }
        }}
        onBlur={() => {
          composingRef.current = false;
          onChange(keyName, draftValue ?? '');
          setIsFocused(false);
        }}
        onFocus={() => setIsFocused(true)}
      />
    );
  }

  return (
    <input
      type={field.type || 'text'}
      className="node-input nodrag"
      value={draftValue ?? ''}
      onMouseDown={stopPropagation}
      onKeyDown={stopPropagation}
      {...compositionProps}
      onChange={(e) => {
        setDraftValue(e.target.value);
        if (!composingRef.current) {
          onChange(keyName, e.target.value);
        }
      }}
      onBlur={() => {
        composingRef.current = false;
        onChange(keyName, draftValue ?? '');
        setIsFocused(false);
      }}
      onFocus={() => setIsFocused(true)}
    />
  );
};

const GenericNode = ({ id, data, isConnectable, selected }) => {
  const nodeId = id || data.id;
  const schema = data.configSchema || {};
  const [config, setConfig] = useState(data.config || {});
  const [meta, setMeta] = useState({
    lastCoordPickId: data.lastCoordPickId,
    revision: data.revision,
  });
  const [recordingKeys, setRecordingKeys] = useState(false);
  const [recordHint, setRecordHint] = useState('');
  const [pickingCoordinate, setPickingCoordinate] = useState(false);
  const [capturePending, setCapturePending] = useState(null);
  const [showHelp, setShowHelp] = useState(false);
  const pickBaselineRef = useRef(null);
  const pickPollRef = useRef(null);
  const captureTimerRef = useRef(null);
  const previewImgRef = useRef(null);

  const stopCoordinatePoll = () => {
    if (pickPollRef.current) {
      clearInterval(pickPollRef.current);
      pickPollRef.current = null;
    }
  };

  // props로 내려오는 config 동기화 (직접 입력 등)
  useEffect(() => {
    setConfig(data.config || {});
    setMeta({
      lastCoordPickId: data.lastCoordPickId,
      revision: data.revision,
    });
  }, [data.config, data.lastCoordPickId, data.revision]);

  // WebSocket 갱신: React Flow memo와 무관하게 즉시 반영
  useEffect(() => {
    return subscribeNodeUpdate(nodeId, (payload) => {
      if (payload.config) {
        setConfig((prev) => ({ ...prev, ...payload.config }));
      }
      if (payload.lastCoordPickId !== undefined || payload.revision !== undefined) {
        setMeta((prev) => ({
          ...prev,
          lastCoordPickId: payload.lastCoordPickId ?? prev.lastCoordPickId,
          revision: payload.revision ?? prev.revision,
        }));
      }
      if (payload.hint) {
        setRecordHint(payload.hint);
      }
      if (payload.pickingCoordinate === false) {
        stopCoordinatePoll();
        setPickingCoordinate(false);
        pickBaselineRef.current = null;
      }
      if (payload.capturePending === false) {
        setCapturePending(null);
      }
    });
  }, [nodeId]);

  useEffect(() => () => {
    stopCoordinatePoll();
    clearTimeout(captureTimerRef.current);
  }, []);

  useEffect(() => {
    if (!pickingCoordinate || !pickBaselineRef.current) {
      return;
    }
    const pickId = meta.lastCoordPickId;
    if (!pickId || pickId === pickBaselineRef.current.pickId) {
      return;
    }
    pickBaselineRef.current = null;
    stopCoordinatePoll();
    setPickingCoordinate(false);
    setRecordHint(`${t('coordinateSaved')}: (${config.x}, ${config.y})`);
  }, [meta.lastCoordPickId, config.x, config.y, pickingCoordinate]);

  const onChange = (key, value) => {
    setConfig((prev) => ({ ...prev, [key]: value }));
    if (data.onChange) {
      data.onChange(nodeId, key, value);
    }
  };

  const getFieldValue = (key, field) => {
    if (config[key] !== undefined && config[key] !== null) {
      return config[key];
    }
    if (field.default !== undefined) {
      return field.default;
    }
    if (field.type === 'number') {
      return 0;
    }
    return '';
  };

  useEffect(() => {
    if (!recordingKeys) {
      return undefined;
    }

    const normalizeKey = (event) => {
      if (event.key === ' ') return 'space';
      if (event.key === 'Enter') return 'enter';
      if (event.key === 'Shift') return 'shift';
      if (event.key === 'Control') return 'ctrl';
      if (event.key === 'Alt') return 'alt';
      if (event.key === 'Meta') return 'win';
      if (event.key === 'Tab') return 'tab';
      if (event.key === 'Backspace') return 'backspace';
      if (event.key === 'Escape') return 'esc';
      if (event.key === 'ArrowUp') return 'up';
      if (event.key === 'ArrowDown') return 'down';
      if (event.key === 'ArrowLeft') return 'left';
      if (event.key === 'ArrowRight') return 'right';
      if (event.key.length === 1) return event.key.toLowerCase();
      return event.key.toLowerCase();
    };

    const onKeyDown = (event) => {
      // Esc는 녹화 취소(확정은 버튼 재클릭). 키 목록에 esc를 넣지 않음.
      if (event.key === 'Escape') {
        event.preventDefault();
        event.stopPropagation();
        setRecordingKeys(false);
        setRecordHint(t('keyCancelled'));
        return;
      }
      if (event.repeat) {
        return;
      }

      const normalized = normalizeKey(event);
      if (!normalized) {
        return;
      }
      event.preventDefault();
      event.stopPropagation();
      setConfig((prev) => {
        const currentKeys = Array.isArray(prev.keys)
          ? prev.keys
          : String(prev.keys || '').split(',').map((item) => item.trim()).filter(Boolean);
        // 같은 modifier 중복 방지, 조합 순서는 유지
        if (currentKeys.includes(normalized)) {
          setRecordHint(`${t('recording')}: ${currentKeys.join(' + ')}`);
          return prev;
        }
        const nextKeys = [...currentKeys, normalized].filter(Boolean);
        if (data.onChange) {
          data.onChange(nodeId, 'keys', nextKeys);
        }
        setRecordHint(`${t('recording')}: ${nextKeys.join(' + ')}`);
        return { ...prev, keys: nextKeys };
      });
    };

    window.addEventListener('keydown', onKeyDown, true);
    return () => window.removeEventListener('keydown', onKeyDown, true);
  }, [recordingKeys, data, nodeId]);

  const handleCapture = async (delay = 0) => {
    const pending = delay > 0 ? 'delayed' : 'instant';
    setCapturePending(pending);
    setRecordHint(delay > 0 ? `${delay}${t('secondsUntilCapture')}` : t('captureStarting'));
    clearTimeout(captureTimerRef.current);
    captureTimerRef.current = setTimeout(() => setCapturePending(null), delay * 1000 + 1000);
    try {
      await api.post('/capture/start', { node_id: nodeId, delay });
    } catch {
      setCapturePending(null);
      alert(t('captureFailed'));
    }
  };

  const handleImageReset = () => {
    const patch = {
      image_path: null,
      image_url: null,
      img_size: null,
      search_region: null,
      offset_x: 0,
      offset_y: 0,
    };
    setConfig((prev) => ({ ...prev, ...patch }));
    data.onChange?.(nodeId, patch);
    setRecordHint('');
  };

  const handleRegionSelect = async () => {
    try {
      await api.post('/region/start', { node_id: nodeId });
    } catch {
      alert(t('regionFailed'));
    }
  };

  const handleCoordinatePick = async () => {
    pickBaselineRef.current = {
      pickId: meta.lastCoordPickId ?? null,
    };
    setPickingCoordinate(true);
    setRecordHint(t('coordinatePickHint'));
    try {
      await api.post('/coordinate/start', { node_id: nodeId });
    } catch {
      pickBaselineRef.current = null;
      setPickingCoordinate(false);
      setRecordHint('');
      alert(t('coordinateFailed'));
      return;
    }

    // WS가 백그라운드에서 늦을 수 있어 폴링으로도 수신
    stopCoordinatePoll();
    const startedAt = Date.now();
    pickPollRef.current = setInterval(async () => {
      if (Date.now() - startedAt > 120000) {
        stopCoordinatePoll();
        setPickingCoordinate(false);
        setRecordHint(t('coordinateTimeout'));
        return;
      }
      try {
        const res = await api.get(`/coordinate/poll/${nodeId}`);
        if (!res.data?.done) {
          return;
        }
        stopCoordinatePoll();
        const { x, y, cancelled } = res.data;
        if (cancelled || x === undefined || y === undefined) {
          pickBaselineRef.current = null;
          setPickingCoordinate(false);
          setRecordHint(t('coordinateCancelled'));
          return;
        }
        setConfig((prev) => ({ ...prev, x, y }));
        if (data.onChange) {
          data.onChange(nodeId, { x, y });
        }
        pickBaselineRef.current = null;
        setPickingCoordinate(false);
        setRecordHint(`${t('coordinateSaved')}: (${x}, ${y})`);
      } catch {
        // 폴링 실패는 무시 (WS 경로가 있을 수 있음)
      }
    }, 200);
  };

  const getImageNaturalSize = () => {
    const img = previewImgRef.current;
    if (img?.naturalWidth && img?.naturalHeight) {
      return { w: img.naturalWidth, h: img.naturalHeight };
    }
    if (Array.isArray(config.img_size) && config.img_size.length >= 2) {
      return { w: Number(config.img_size[0]) || 1, h: Number(config.img_size[1]) || 1 };
    }
    return { w: 1, h: 1 };
  };

  const handlePreviewClick = (event) => {
    if (data.type !== 'image') {
      return;
    }
    const img = previewImgRef.current;
    if (!img?.naturalWidth || !img?.naturalHeight) {
      return;
    }
    const rect = event.currentTarget.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) {
      return;
    }
    const nw = img.naturalWidth;
    const nh = img.naturalHeight;
    // 실행 엔진과 동일: (0,0) = 이미지 중앙, 클릭 위치는 중앙 대비 상대값
    const clickX = ((event.clientX - rect.left) / rect.width) * nw;
    const clickY = ((event.clientY - rect.top) / rect.height) * nh;
    const ox = Math.round(clickX - nw / 2);
    const oy = Math.round(clickY - nh / 2);
    const patch = {
      offset_x: ox,
      offset_y: oy,
      img_size: [nw, nh],
    };
    setConfig((prev) => ({ ...prev, ...patch }));
    if (data.onChange) {
      data.onChange(nodeId, patch);
    }
  };

  const handleImageLoad = (event) => {
    const w = event.currentTarget.naturalWidth;
    const h = event.currentTarget.naturalHeight;
    if (!w || !h) {
      return;
    }
    const prev = config.img_size;
    if (!Array.isArray(prev) || prev[0] !== w || prev[1] !== h) {
      onChange('img_size', [w, h]);
    }
  };

  const toggleKeyRecording = () => {
    if (recordingKeys) {
      setRecordingKeys(false);
      const keys = Array.isArray(config.keys)
        ? config.keys
        : String(config.keys || '').split(',').map((item) => item.trim()).filter(Boolean);
      setRecordHint(keys.length ? `${t('saved')}: ${keys.join(' + ')}` : t('noKeys'));
      return;
    }
    const emptyKeys = [];
    setConfig((prev) => ({ ...prev, keys: emptyKeys }));
    if (data.onChange) {
      data.onChange(nodeId, 'keys', emptyKeys);
    }
    setRecordingKeys(true);
    setRecordHint(t('keyStartHint'));
  };

  const hasSchema = Object.keys(schema).length > 0;
  const isImageNode = data.type === 'image' || data.type === 'if';
  const isCoordinateNode = data.type === 'click';
  const isKeyboardNode = data.type === 'keyboard';
  const isWindowNode = data.type === 'window';
  const isMouseSequenceNode = data.type === 'mouse_sequence';
  const keyboardMode = config.mode ?? schema?.mode?.default ?? 'hotkey';
  const showOffsetPicker = data.type === 'image' && Boolean(config.image_url);
  const recordedKeys = Array.isArray(config.keys)
    ? config.keys
    : String(config.keys || '').split(',').map((item) => item.trim()).filter(Boolean);
  const mouseSequenceSteps = Array.isArray(config.steps) ? config.steps : [];
  const mouseSequenceMoves = mouseSequenceSteps.filter((step) => step?.op === 'move').length;
  const mouseSequenceWaitMs = mouseSequenceSteps
    .filter((step) => step?.op === 'wait')
    .reduce((total, step) => total + (Number(step.ms) || 0), 0);

  const naturalSize = getImageNaturalSize();
  const markerStyle = showOffsetPicker
    ? {
      left: `${(0.5 + (Number(config.offset_x) || 0) / Math.max(1, naturalSize.w)) * 100}%`,
      top: `${(0.5 + (Number(config.offset_y) || 0) / Math.max(1, naturalSize.h)) * 100}%`,
    }
    : { left: '50%', top: '50%' };

  return (
    <div
      className={`custom-node ${selected ? 'selected' : ''} ${data.executionState ? `execution-${data.executionState}` : ''}`}
      title={data.executionMessage || ''}
    >
      <Handle type="target" position={Position.Left} isConnectable={isConnectable} id="input_pin" />

      <div className="node-header">
        <span>{nodeLabel(data.type, data.label)}</span>
        <div className="node-header-actions">
          <button
            type="button"
            className="node-help-button nodrag"
            title={t('nodeHelp')}
            aria-expanded={showHelp}
            onPointerDown={(event) => event.stopPropagation()}
            onClick={(event) => {
              event.stopPropagation();
              setShowHelp((value) => !value);
            }}
          >?</button>
          <span className="node-chip">{data.type}</span>
        </div>
      </div>

      <div className="node-body nodrag nowheel">
        {showHelp && (
          <div className="node-help-panel">
            <strong>{t('usage')}</strong>
            <span>{t(`help_${data.type}`)}</span>
            {Object.keys(schema).length > 0 && (
              <small>
                {t('defaults')}: {Object.entries(schema).map(([key, field]) => (
                  `${fieldLabel(key, field.label || key)}=${optionLabel(field.default ?? '-')}`
                )).join(' · ')}
              </small>
            )}
          </div>
        )}
        {hasSchema && (
          <div className="node-section">
            <div className="node-section-title">{t('settings')}</div>
            {Object.keys(schema).map((key) => {
              const field = schema[key];
              if (isKeyboardNode && key === 'keys') {
                return null;
              }
              if (isKeyboardNode && key === 'hangul_typewrite' && keyboardMode !== 'text') {
                return null;
              }
              if (isKeyboardNode && (key === 'string' || key === 'interval') && keyboardMode !== 'text') {
                return null;
              }
              return (
                <div key={key} className="node-field">
                  <div className="node-label">{fieldLabel(key, field.label || key)}</div>
                  <FieldControl field={field} keyName={key} value={getFieldValue(key, field)} onChange={onChange} />
                </div>
              );
            })}
          </div>
        )}

        {isWindowNode && <div className="node-hint">{t('windowNodeHint')}</div>}

        {isMouseSequenceNode && (
          <div className="node-hint">
            {t('mouseSequenceSummary')
              .replace('{moves}', mouseSequenceMoves)
              .replace('{seconds}', (mouseSequenceWaitMs / 1000).toFixed(1))}
          </div>
        )}

        {isCoordinateNode && (
          <div className="node-section">
            <div className="node-section-title">{t('coordinates')}</div>
            <button type="button" className="node-button nodrag" onClick={handleCoordinatePick}>
              📍 {t('coordinateRecord')}
            </button>
            {pickingCoordinate && (
              <div className="node-hint">
                {t('coordinatePickHint')}
              </div>
            )}
            {recordHint && <div className="node-hint">{recordHint}</div>}
          </div>
        )}

        {isKeyboardNode && (
          <div className="node-section">
            <div className="node-section-title">{t('keyboard')}</div>
            {keyboardMode === 'hotkey' && (
              <>
                <button
                  type="button"
                  className="node-button nodrag"
                  style={{ background: recordingKeys ? '#dc2626' : '#8b5cf6' }}
                  onClick={toggleKeyRecording}
                >
                  {recordingKeys ? `⏹ ${t('keyConfirm')}` : `🎹 ${t('keyRecord')}`}
                </button>
                <div className="node-hint">
                  {recordingKeys
                    ? t('keyRecordingHint')
                    : t('keyRecordHint')}
                </div>
                {recordedKeys.length > 0 && (
                  <div className="node-hint">Keys: {recordedKeys.join(' + ')}</div>
                )}
                {recordHint && <div className="node-hint">{recordHint}</div>}
              </>
            )}
            {keyboardMode === 'text' && (
              <div className="node-hint">
                {config.hangul_typewrite
                  ? t('koreanTypingOn')
                  : t('textTyping')}
              </div>
            )}
          </div>
        )}

        {isImageNode && (
          <div className="node-section">
            <div className="node-section-title">{t('image')}</div>
            <div className="button-row">
              <button type="button" disabled={Boolean(capturePending)} className={`node-button nodrag ${capturePending === 'instant' ? 'is-active' : ''}`} style={{ background: '#eab308' }} onClick={() => handleCapture(0)}>
                📷 {t('capture')}
              </button>
              <button type="button" disabled={Boolean(capturePending)} className={`node-button nodrag ${capturePending === 'delayed' ? 'is-active' : ''}`} style={{ background: '#f97316' }} onClick={() => handleCapture(5)}>
                ⏱ {t('captureDelayed')}
              </button>
            </div>
            <div className="button-row">
              <button type="button" className="node-button nodrag" style={{ background: '#14b8a6' }} onClick={handleRegionSelect}>
                🎯 {t('setRegion')}
              </button>
              <button type="button" className="node-button nodrag" style={{ background: '#64748b' }} onClick={handleImageReset}>
                🔄 {t('reset')}
              </button>
            </div>
            {config.image_url && (
              <div
                className={`image-preview-box nodrag ${showOffsetPicker ? '' : 'no-offset'}`}
                onClick={showOffsetPicker ? handlePreviewClick : undefined}
              >
                <img
                  ref={previewImgRef}
                  key={config.image_url}
                  src={config.image_url}
                  alt="captured"
                  className="image-preview"
                  draggable={false}
                  onLoad={handleImageLoad}
                />
                {showOffsetPicker && (
                  <div className="offset-marker" style={markerStyle}>
                    <span className="offset-marker-dot" />
                  </div>
                )}
              </div>
            )}
            {showOffsetPicker && (
              <div className="node-hint">{t('imageOffsetHint')}</div>
            )}
            {showOffsetPicker && (
              <div className="node-hint">
                {t('offset')}: ({Number(config.offset_x) || 0}, {Number(config.offset_y) || 0})
                {Array.isArray(config.img_size) ? ` / ${config.img_size[0]}×${config.img_size[1]}` : ''}
              </div>
            )}
            {config.search_region && (
              <div className="node-hint">{t('region')}: {JSON.stringify(config.search_region)}</div>
            )}
            {!config.image_url && (
              <div className="node-hint">{t('imageEmptyHint')}</div>
            )}
            {recordHint && <div className="node-hint">{recordHint}</div>}
          </div>
        )}

        {!hasSchema && !isImageNode && !isCoordinateNode && !isKeyboardNode && !isMouseSequenceNode && (
          <div className="node-label" style={{ textAlign: 'center', color: '#64748b' }}>
            {t('noConfiguration')}
          </div>
        )}
      </div>

      {data.type !== 'if' && data.type !== 'loop' && (
        <Handle type="source" position={Position.Right} id="output_pin" isConnectable={isConnectable}>
          <span className="handle-label handle-label-right">Out</span>
        </Handle>
      )}
      {data.type === 'if' && (
        <>
          <Handle
            type="source"
            position={Position.Right}
            id="true_out_pin"
            className="handle-branch"
            style={{ top: '30%', background: '#10b981' }}
            isConnectable={isConnectable}
          >
            <span className="handle-label handle-label-right">True</span>
          </Handle>
          <Handle
            type="source"
            position={Position.Right}
            id="false_out_pin"
            className="handle-branch"
            style={{ top: '70%', background: '#ef4444' }}
            isConnectable={isConnectable}
          >
            <span className="handle-label handle-label-right">False</span>
          </Handle>
        </>
      )}
      {data.type === 'loop' && (
        <>
          <Handle
            type="source"
            position={Position.Right}
            id="loop_out_pin"
            className="handle-branch"
            style={{ top: '30%', background: '#3b82f6' }}
            isConnectable={isConnectable}
          >
            <span className="handle-label handle-label-right">Loop</span>
          </Handle>
          <Handle
            type="source"
            position={Position.Right}
            id="exit_out_pin"
            className="handle-branch"
            style={{ top: '70%', background: '#8b5cf6' }}
            isConnectable={isConnectable}
          >
            <span className="handle-label handle-label-right">Exit</span>
          </Handle>
        </>
      )}
    </div>
  );
};

export default GenericNode;

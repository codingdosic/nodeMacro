import React, { useEffect, useState } from 'react';
import { api } from './api';
import { nodeLabel, t } from './i18n';

const NodePalette = ({ uiLanguage }) => {
  const [nodeTypes, setNodeTypes] = useState([]);

  useEffect(() => {
    api.get('/nodes/types')
      .then(res => setNodeTypes(res.data))
      .catch(err => console.error("Failed to load node types", err));
  }, []);

  const onDragStart = (event, nodeType, nodeLabel, nodeSchema) => {
    event.dataTransfer.setData('application/reactflow', nodeType);
    event.dataTransfer.setData('application/reactflow/label', nodeLabel);
    event.dataTransfer.setData('application/reactflow/schema', JSON.stringify(nodeSchema || {}));
    event.dataTransfer.effectAllowed = 'move';
  };

  return (
    <div className="palette-container" data-language={uiLanguage}>
      <div className="palette-title">{t('nodes')}</div>
      {nodeTypes.map((node) => (
        <div
          key={node.type}
          className="node-item"
          onDragStart={(event) => onDragStart(event, node.type, nodeLabel(node.type, node.label), node.schema)}
          draggable
        >
          {nodeLabel(node.type, node.label)}
        </div>
      ))}
    </div>
  );
};

export default NodePalette;

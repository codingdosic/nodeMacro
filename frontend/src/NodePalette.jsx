import React, { useEffect, useState } from 'react';
import axios from 'axios';

const NodePalette = () => {
  const [nodeTypes, setNodeTypes] = useState([]);

  useEffect(() => {
    axios.get('http://127.0.0.1:8000/api/nodes/types')
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
    <div className="palette-container">
      <div className="palette-title">Nodes</div>
      {nodeTypes.map((node) => (
        <div
          key={node.type}
          className="node-item"
          onDragStart={(event) => onDragStart(event, node.type, node.label, node.schema)}
          draggable
        >
          {node.label}
        </div>
      ))}
    </div>
  );
};

export default NodePalette;

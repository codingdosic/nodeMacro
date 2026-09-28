import React from 'react';
import { ReactFlowProvider } from '@xyflow/react';
import NodePalette from './NodePalette';
import NodeEditor from './NodeEditor';
import './index.css';
import '@xyflow/react/dist/style.css';

function App() {
  return (
    <div className="app-container">
      <ReactFlowProvider>
        <NodePalette />
        <NodeEditor />
      </ReactFlowProvider>
    </div>
  );
}

export default App;

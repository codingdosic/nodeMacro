import React, { useState } from 'react';
import { ReactFlowProvider } from '@xyflow/react';
import NodePalette from './NodePalette';
import NodeEditor from './NodeEditor';
import './index.css';
import '@xyflow/react/dist/style.css';
import { language, setLanguage } from './i18n';

function App() {
  const [uiLanguage, setUiLanguage] = useState(language());

  const changeLanguage = (value) => {
    setLanguage(value);
    setUiLanguage(value);
  };

  return (
    <div className="app-container">
      <ReactFlowProvider>
        <NodePalette uiLanguage={uiLanguage} />
        <NodeEditor currentLanguage={uiLanguage} onLanguageChange={changeLanguage} />
      </ReactFlowProvider>
    </div>
  );
}

export default App;

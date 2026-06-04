import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import App from '@/App';
import { GameProvider } from '@/state/GameContext';
import { ToastProvider } from '@/state/ToastProvider';
import '@/index.css';

const rootElement = document.getElementById('root');
if (!rootElement) {
  throw new Error('Root element #root not found in index.html');
}

createRoot(rootElement).render(
  <StrictMode>
    <ToastProvider>
      <GameProvider>
        <App />
      </GameProvider>
    </ToastProvider>
  </StrictMode>,
);

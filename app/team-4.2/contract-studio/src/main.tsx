import { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import App from './App.tsx';
import DossierStudio from './DossierStudio.tsx';
import './index.css';

// #ho-so: soát hồ sơ nhiều văn bản; còn lại: soát một hợp đồng.
function Root() {
  const [hash, setHash] = useState(window.location.hash);
  useEffect(() => {
    const on = () => setHash(window.location.hash);
    window.addEventListener('hashchange', on);
    return () => window.removeEventListener('hashchange', on);
  }, []);
  return hash === '#ho-so' ? <DossierStudio onExit={() => { window.location.hash = ''; }} /> : <App />;
}

createRoot(document.getElementById('root')!).render(<Root />);

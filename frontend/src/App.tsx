import { BrowserRouter as Router, Routes, Route, Link, useLocation } from 'react-router-dom'
import { LayoutDashboard, FileSearch, Power } from 'lucide-react'

// Importando as páginas que acabamos de separar
import Dashboard from './pages/Dashboard'
import Acompanhamento from './pages/Acompanhamento'

function LayoutPrincipal() {
  const location = useLocation();

  return (
    <div className="app-layout">
      <aside className="sidebar">
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '3rem', paddingLeft: '8px' }}>
          <div style={{ width: '32px', height: '32px', display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'white', borderRadius: '8px', padding: '2px' }}>
            <img src="/triabot.png" alt="TriaBot" style={{ maxWidth: '100%', maxHeight: '100%', objectFit: 'contain' }} />
          </div>
          <h1 style={{ fontSize: '1.25rem', fontWeight: 'bold', color: 'white' }}>TRIAGEM</h1>
        </div>
        
        <nav style={{ display: 'flex', flexDirection: 'column', flex: 1, gap: '4px' }}>
          <Link to="/" className={`nav-item ${location.pathname === '/' ? 'active' : ''}`}>
            <LayoutDashboard size={18} /> Painel Executivo
          </Link>
          <Link to="/acompanhamento" className={`nav-item ${location.pathname === '/acompanhamento' ? 'active' : ''}`}>
            <FileSearch size={18} /> Auditoria OS
          </Link>
        </nav>
        
        <button className="nav-item" style={{ color: '#f87171', border: 'none', background: 'none', width: '100%', cursor: 'pointer', marginTop: 'auto' }}>
          <Power size={18} /> Sair do Sistema
        </button>
      </aside>

      <main className="main-content">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/acompanhamento" element={<Acompanhamento />} />
        </Routes>
      </main>
    </div>
  )
}

export default function App() {
  return (
    <Router>
      <LayoutPrincipal />
    </Router>
  )
}
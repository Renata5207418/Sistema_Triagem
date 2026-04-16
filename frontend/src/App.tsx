import React, { useState } from 'react';
import { BrowserRouter as Router, Routes, Route, Link, useLocation, Navigate } from 'react-router-dom';
import { LayoutDashboard, FileSearch, Power, Menu, ChevronLeft, Database } from 'lucide-react'; 
import { AuthProvider, useAuth } from './context/AuthContext';
import Dashboard from './pages/Dashboard';
import Acompanhamento from './pages/Acompanhamento';
import { Login } from './pages/Login'
import { ResetPassword } from './pages/ResetPassword'
import MalhaFiscal from './pages/MalhaFiscal';


// --- RotaProtegida (Sem alterações aqui) ---
const RotaProtegida = ({ children }: { children: React.ReactNode }) => {
  const { isAuthenticated, loading } = useAuth();
  if (loading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh', background: '#f3f4f6', color: 'var(--primary)', fontWeight: 'bold' }}>
        Verificando sessão...
      </div>
    );
  }
  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }
  return <>{children}</>;
};

function LayoutPrincipal() {
  const location = useLocation();
  const { logout, user } = useAuth();
  
  const [isCollapsed, setIsCollapsed] = useState(false);

  const toggleSidebar = () => {
    setIsCollapsed(!isCollapsed);
  };

  const getPageTitle = () => {
    if (location.pathname === '/') return 'Dashboard';
    if (location.pathname === '/acompanhamento') return 'Auditoria de OS';
    return 'Sistema';
  };

  // --- NOVA FUNÇÃO: Saudação Dinâmica ---
  const getGreeting = () => {
    const hour = new Date().getHours();
    if (hour >= 5 && hour < 12) return 'Bom dia,';
    if (hour >= 12 && hour < 18) return 'Boa tarde,';
    return 'Boa noite,';
  };

  return (
    <div className="app-layout">
      
      {/* 1. SIDEBAR (Sem alterações aqui) */}
      <aside className={`sidebar ${isCollapsed ? 'collapsed' : ''}`}>
        <div className="sidebar-logo-container">
          <div className="logo-box">
            <img src="/triabot.png" alt="TriaBot" className="logo-img" />
          </div>
          {!isCollapsed && <h1 className="logo-text">SISTEMA TRIAGEM</h1>}
        </div>
        
        <nav className="sidebar-nav">
          <Link to="/" className={`nav-item ${location.pathname === '/' ? 'active' : ''}`}>
            <LayoutDashboard size={20} />
            {!isCollapsed && <span>Painel Executivo</span>}
          </Link>
          <Link to="/acompanhamento" className={`nav-item ${location.pathname === '/acompanhamento' ? 'active' : ''}`}>
            <FileSearch size={20} />
            {!isCollapsed && <span>Auditoria OS</span>}
          </Link>
          <Link to="/malha-fiscal" className={`nav-item ${location.pathname === '/malha-fiscal' ? 'active' : ''}`}>
            <Database size={20} />
            {!isCollapsed && <span>Auditoria Tomados</span>}
          </Link>
        </nav>
        
        <button onClick={logout} className="nav-item logout-btn">
          <Power size={20} />
          {!isCollapsed && <span>Logout</span>}
        </button>
      </aside>

      {/* 2. ÁREA DA DIREITA: Header Refinado */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', height: '100vh', overflow: 'hidden' }}>
        
        <header className="top-header">
          <div className="header-left">
            <button onClick={toggleSidebar} className="toggle-sidebar-btn">
                {isCollapsed ? <Menu size={20} /> : <ChevronLeft size={20} />}
            </button>
            <div className="breadcrumb-box">
                <span className="breadcrumb-current">{getPageTitle()}</span>
            </div>
          </div>

          <div className="header-right">
            <div className="user-text-info">
              <span className="welcome-text">{getGreeting()}</span>
              <span className="user-name">{user?.full_name?.split(' ')[0] || 'Usuário'}</span>
            </div>

            <div className="premium-avatar">
              {user?.full_name?.charAt(0).toUpperCase() || 'U'}
              <div className="status-dot online"></div>
            </div>
          </div>
        </header>

        <main className="main-content">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/acompanhamento" element={<Acompanhamento />} />
            <Route path="/malha-fiscal" element={<MalhaFiscal />} />
          </Routes>
        </main>
      </div>
    </div>
  )
}

// --- APP PRINCIPAL ---
export default function App() {
  return (
    <AuthProvider>
      <Router>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/reset-password" element={<ResetPassword />} />

          <Route 
            path="/*" 
            element={
              <RotaProtegida>
                <LayoutPrincipal />
              </RotaProtegida>
            } 
          />
        </Routes>
      </Router>
    </AuthProvider>
  )
}

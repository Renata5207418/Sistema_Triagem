import { useState, useEffect, useMemo } from 'react'
import { BrowserRouter as Router, Routes, Route, Link, useLocation } from 'react-router-dom'
import axios from 'axios'
import { LayoutDashboard, FileSearch, Power, HardDrive, MessageSquare, Download, X, ChevronDown, ChevronUp, ChevronLeft, ChevronRight } from 'lucide-react'

// --- TELA 1: DASHBOARD ---
function TelaDashboard() {
  const [resumo, setResumo] = useState({ total_processado: 0, sucesso_triagem: 0, erros_atencao: 0, pendente_senha: 0 })

  useEffect(() => {
    axios.get('http://127.0.0.1:8000/api/resumo')
      .then(res => setResumo(res.data))
      .catch(err => console.error("API falhou", err))
  }, [])

  return (
    <div>
      <header style={{ marginBottom: '2.5rem' }}>
        <h2 style={{ fontSize: '1.8rem', fontWeight: 'bold' }}>Painel Executivo</h2>
        <p style={{ color: 'var(--text-muted)' }}>Controle mensal da esteira (Março 2026).</p>
      </header>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '1.5rem' }}>
        <div className="card" style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
          <div style={{ padding: '12px', background: 'var(--primary-light)', color: 'var(--primary)', borderRadius: '12px' }}><HardDrive size={24} /></div>
          <div><p style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>Solicitações (Mês)</p><p style={{ fontSize: '1.8rem', fontWeight: 'bold' }}>{resumo.total_processado}</p></div>
        </div>
        <div className="card" style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
           <div style={{ padding: '12px', background: '#dcfce7', color: '#166534', borderRadius: '12px' }}><FileSearch size={24} /></div>
           <div><p style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>Sucesso Triagem</p><p style={{ fontSize: '1.8rem', fontWeight: 'bold' }}>{resumo.sucesso_triagem}</p></div>
        </div>
        <div className="card" style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
           <div style={{ padding: '12px', background: '#fee2e2', color: '#991b1b', borderRadius: '12px' }}><FileSearch size={24} /></div>
           <div><p style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>Pendências/Erros</p><p style={{ fontSize: '1.8rem', fontWeight: 'bold' }}>{resumo.erros_atencao}</p></div>
        </div>
        <div className="card" style={{ display: 'flex', alignItems: 'center', gap: '1rem', borderLeft: '4px solid var(--primary)' }}>
           <div><p style={{ fontSize: '0.85rem', color: 'var(--primary)', fontWeight: 'bold' }}>EMPRESAS ATIVAS</p><p style={{ fontSize: '1.8rem', fontWeight: 'bold' }}>86</p></div>
        </div>
      </div>
    </div>
  )
}

// --- TELA 2: ACOMPANHAMENTO OS (Agrupado com Inteligência) ---
function TelaAcompanhamento() {
  const [documentosFlat, setDocumentosFlat] = useState<any[]>([])
  const [modalMsg, setModalMsg] = useState<string | null>(null)
  
  const [expandedOS, setExpandedOS] = useState<number | null>(null)
  const [currentPage, setCurrentPage] = useState(1)
  const itemsPerPage = 10

  useEffect(() => {
    axios.get('http://127.0.0.1:8000/api/triagem/auditoria')
      .then(res => setDocumentosFlat(res.data))
      .catch(err => console.error("API falhou", err))
  }, [])

  // Agrupa os dados e calcula os status da OS (Pai) com base nos arquivos (Filhos)
  const agrupadosPorOS = useMemo(() => {
    const mapa = documentosFlat.reduce((acc: any, doc: any) => {
      if (!acc[doc.os]) {
        acc[doc.os] = {
          os: doc.os,
          cod_empresa: doc.cod_empresa,
          nome_empresa: doc.nome_empresa,
          status_download: doc.status_download,
          mensagem: doc.mensagem,
          arquivos: [],
          temErroTriagem: false // Flag para sabermos se a OS inteira tem problema
        }
      }
      
      acc[doc.os].arquivos.push(doc)
      
      // Se qualquer arquivo der erro, a OS inteira fica com alerta de erro
      if (doc.status_triagem !== 'SUCESSO') {
        acc[doc.os].temErroTriagem = true;
      }

      return acc
    }, {})

    // Converte o objeto em array e define os status finais da OS
    return Object.values(mapa).map((grupo: any) => ({
      ...grupo,
      status_triagem_geral: grupo.temErroTriagem ? 'ERRO' : 'SUCESSO',
      // Provisório: Libera a planilha da OS se não houver erro na triagem
      status_tomados_geral: grupo.temErroTriagem ? 'PENDENTE' : 'LIBERADO' 
    })) as any[]

  }, [documentosFlat])

  const totalPages = Math.ceil(agrupadosPorOS.length / itemsPerPage)
  const currentItems = agrupadosPorOS.slice((currentPage - 1) * itemsPerPage, currentPage * itemsPerPage)

  const toggleExpand = (os: number) => {
    setExpandedOS(expandedOS === os ? null : os)
  }

  return (
    <div>
      <header style={{ marginBottom: '2.5rem' }}>
        <h2 style={{ fontSize: '1.8rem', fontWeight: 'bold' }}>Acompanhamento de OS</h2>
        <p style={{ color: 'var(--text-muted)' }}>Auditoria detalhada agrupada por solicitação.</p>
      </header>

      <div className="table-container">
        <table className="custom-table">
          <thead>
            <tr>
              <th style={{ width: '50px' }}></th>
              <th>OS # <input type="text" placeholder="Buscar..." className="column-search" /></th>
              <th>Cód / Empresa <input type="text" placeholder="Buscar..." className="column-search" /></th>
              <th style={{ textAlign: 'center' }}>Qtd. Arquivos</th>
              <th style={{ textAlign: 'center' }}>Download</th>
              <th style={{ textAlign: 'center' }}>Triagem</th>
              <th style={{ textAlign: 'center' }}>Tomados</th>
              <th style={{ textAlign: 'center' }}>Mensagem</th>
            </tr>
          </thead>
          <tbody>
            {currentItems.map((grupo) => (
              <>
                {/* LINHA PAI (A Capa da OS) */}
                <tr key={`parent-${grupo.os}`} style={{ background: expandedOS === grupo.os ? '#f3e8ff' : 'transparent' }}>
                  <td style={{ textAlign: 'center' }}>
                    <button onClick={() => toggleExpand(grupo.os)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--primary)' }}>
                      {expandedOS === grupo.os ? <ChevronUp size={20} /> : <ChevronDown size={20} />}
                    </button>
                  </td>
                  <td style={{ fontWeight: 700 }}>#{grupo.os}</td>
                  <td>
                    <div><span style={{ fontWeight: 700, fontSize: '0.75rem', color: 'var(--primary)' }}>{grupo.cod_empresa}</span></div>
                    <div style={{ fontWeight: 600 }}>{grupo.nome_empresa}</div>
                  </td>
                  <td style={{ textAlign: 'center', fontWeight: 'bold', color: 'var(--text-muted)' }}>
                    {grupo.arquivos.length}
                  </td>
                  <td style={{ textAlign: 'center' }}>
                    <span className={`status-badge ${grupo.status_download === 'SUCESSO' ? 'status-ok' : 'status-erro'}`}>
                      {grupo.status_download}
                    </span>
                  </td>
                  
                  {/* Status Triagem GERAL da OS */}
                  <td style={{ textAlign: 'center' }}>
                    <span className={`status-badge ${grupo.status_triagem_geral === 'SUCESSO' ? 'status-ok' : 'status-erro'}`}>
                      {grupo.status_triagem_geral}
                    </span>
                  </td>

                  {/* Ação de Tomados Mapeada para a OS inteira */}
                  <td style={{ textAlign: 'center' }}>
                    {grupo.status_tomados_geral === 'LIBERADO' ? (
                      <button className="btn-primary" style={{ padding: '6px 14px' }}>
                        <Download size={14} /> Planilha
                      </button>
                    ) : (
                      <span className="status-badge status-pendente">{grupo.status_tomados_geral}</span>
                    )}
                  </td>

                  <td style={{ textAlign: 'center' }}>
                    {grupo.mensagem ? (
                      <button onClick={() => setModalMsg(grupo.mensagem)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--primary)' }}>
                        <MessageSquare size={20} />
                      </button>
                    ) : <span style={{ color: 'var(--border)' }}>-</span>}
                  </td>
                </tr>

                {/* LINHA FILHA (Arquivos limpos) */}
                {expandedOS === grupo.os && (
                  <tr key={`child-${grupo.os}`} className="sub-table-row">
                    <td colSpan={8} style={{ padding: '1rem 3rem' }}>
                      <table className="sub-table">
                        <thead>
                          <tr>
                            <th>Nome do Arquivo Original</th>
                            <th style={{ width: '150px' }}>Classificação IA</th>
                            <th style={{ width: '150px' }}>Status Triagem</th>
                          </tr>
                        </thead>
                        <tbody>
                          {grupo.arquivos.map((arquivo: any) => (
                            <tr key={arquivo.id}>
                              <td style={{ color: 'var(--text-muted)' }}>{arquivo.arquivo}</td>
                              <td><span className="status-badge" style={{ background: '#e2e8f0', color: '#475569' }}>{arquivo.categoria_ia || 'N/A'}</span></td>
                              <td>
                                <span className={`status-badge ${arquivo.status_triagem === 'SUCESSO' ? 'status-ok' : 'status-erro'}`}>
                                  {arquivo.status_triagem}
                                </span>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </td>
                  </tr>
                )}
              </>
            ))}
          </tbody>
        </table>

        {/* PAGINAÇÃO */}
        <div className="pagination-container">
          <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
            Mostrando página <strong>{currentPage}</strong> de <strong>{totalPages || 1}</strong>
          </span>
          <div style={{ display: 'flex', gap: '8px' }}>
            <button className="page-btn" onClick={() => setCurrentPage(prev => Math.max(prev - 1, 1))} disabled={currentPage === 1}>
              <ChevronLeft size={16} /> Anterior
            </button>
            <button className="page-btn" onClick={() => setCurrentPage(prev => Math.min(prev + 1, totalPages))} disabled={currentPage === totalPages || totalPages === 0}>
              Próxima <ChevronRight size={16} />
            </button>
          </div>
        </div>
      </div>

      {/* MODAL MENSAGEM */}
      {modalMsg && (
        <div className="modal-backdrop" onClick={() => setModalMsg(null)}>
          <div className="modal-box" onClick={e => e.stopPropagation()}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
              <h3 style={{ color: 'var(--primary)' }}>Mensagem da OS</h3>
              <button onClick={() => setModalMsg(null)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)' }}><X size={20} /></button>
            </div>
            <p style={{ lineHeight: 1.6 }}>{modalMsg}</p>
          </div>
        </div>
      )}
    </div>
  )
}

// --- ESTRUTURA PRINCIPAL ---
function LayoutPrincipal() {
  const location = useLocation();

  return (
    <div className="app-layout">
      <aside className="sidebar">
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '3rem', paddingLeft: '8px' }}>
          
          {/* LOGO TRIABOT INTEGRADAS */}
          <div style={{ width: '32px', height: '32px', display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'white', borderRadius: '8px', padding: '2px' }}>
            <img src="/triabot.png" alt="TriaBot" style={{ maxWidth: '100%', maxHeight: '100%', objectFit: 'contain' }} />
          </div>
          
          <h1 style={{ fontSize: '1.25rem', fontWeight: 'bold', color: 'white' }}>Triagem Cloud</h1>
        </div>
        
        <nav style={{ display: 'flex', flexDirection: 'column', flex: 1, gap: '4px' }}>
          <Link to="/" className={`nav-item ${location.pathname === '/' ? 'active' : ''}`}>
            <LayoutDashboard size={18} /> Painel Executivo
          </Link>
          <Link to="/acompanhamento" className={`nav-item ${location.pathname === '/acompanhamento' ? 'active' : ''}`}>
            <FileSearch size={18} /> Acompanhamento OS
          </Link>
        </nav>
        
        <button className="nav-item" style={{ color: '#f87171', border: 'none', background: 'none', width: '100%', cursor: 'pointer', marginTop: 'auto' }}>
          <Power size={18} /> Sair do Sistema
        </button>
      </aside>

      <main className="main-content">
        <Routes>
          <Route path="/" element={<TelaDashboard />} />
          <Route path="/acompanhamento" element={<TelaAcompanhamento />} />
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
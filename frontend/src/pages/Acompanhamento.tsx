import React, { useState, useEffect, useMemo } from 'react'
import axios from 'axios'
import { Download, ChevronDown, ChevronUp, ChevronLeft, ChevronRight, CheckCircle, Circle, FileText, Calendar, UserCheck } from 'lucide-react'
import DatePicker, { registerLocale } from "react-datepicker";
import "react-datepicker/dist/react-datepicker.css";
import { ptBR } from "date-fns/locale"; 
import { useAuth } from '../context/AuthContext';

registerLocale("pt-BR", ptBR);

// --- COMPONENTE INTERNO: Paginação dos Arquivos (Sub-tabela) ---
const SubTable = ({ arquivos }: { arquivos: any[] }) => {
  const [page, setPage] = useState(1);
  const itemsPerPage = 10;
  const totalPages = Math.ceil(arquivos.length / itemsPerPage);
  const current = arquivos.slice((page - 1) * itemsPerPage, page * itemsPerPage);

  return (
    <div style={{ padding: '16px 24px 24px 64px', background: '#f8fafc', borderBottom: '1px solid var(--border)' }}>
      <div style={{ borderLeft: '2px solid var(--border)', paddingLeft: '24px' }}>
        
        {/* Adicionado tableLayout: fixed para forçar as larguras e não deixar o XML estourar a tela */}
        <table className="sub-table" style={{ width: '100%', tableLayout: 'fixed' }}>
          <thead>
            <tr>
              <th style={{ textAlign: 'left', width: '55%', padding: '8px 16px' }}>Nome do Arquivo Original</th>
              <th style={{ textAlign: 'left', width: '25%', padding: '8px 16px' }}>Classificação IA</th>
              <th style={{ textAlign: 'right', width: '20%', padding: '8px 16px' }}>Status</th>
            </tr>
          </thead>
          <tbody>
            {current.map((arquivo: any) => (
              <tr key={arquivo.id} className="sub-table-row">
                
                {/* Célula com reticências (...) para nomes muito grandes */}
                <td style={{ padding: '8px 16px', color: 'var(--text-muted)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <FileText size={14} style={{ opacity: 0.5, flexShrink: 0 }} />
                    <span style={{ overflow: 'hidden', textOverflow: 'ellipsis' }} title={arquivo.arquivo}>
                      {arquivo.arquivo}
                    </span>
                  </div>
                </td>

                <td style={{ padding: '8px 16px' }}>
                  <span style={{ padding: '4px 10px', background: 'white', color: '#475569', borderRadius: '6px', fontSize: '0.7rem', fontWeight: 600, border: '1px solid #e2e8f0' }}>
                    {arquivo.categoria_ia || 'N/A'}
                  </span>
                </td>

                <td style={{ textAlign: 'right', padding: '8px 16px' }}>
                  <span className={`status-badge ${arquivo.status_triagem === 'SUCESSO' ? 'status-ok' : 'status-erro'}`}>
                    {arquivo.status_triagem}
                  </span>
                </td>

              </tr>
            ))}
          </tbody>
        </table>
        
        {totalPages > 1 && (
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '16px' }}>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Página {page} de {totalPages}</span>
            <div style={{ display: 'flex', gap: '8px' }}>
              <button 
                className="page-btn" 
                onClick={() => setPage(p => Math.max(p - 1, 1))} 
                disabled={page === 1} 
                style={{ padding: '4px 12px', fontSize: '0.75rem' }} 
              >
                <ChevronLeft size={14} /> Anterior
              </button>
              <button 
                className="page-btn" 
                onClick={() => setPage(p => Math.min(p + 1, totalPages))} 
                disabled={page === totalPages} 
                style={{ padding: '4px 12px', fontSize: '0.75rem' }} 
              >
                Próxima <ChevronRight size={14} />
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

export default function Acompanhamento() {
  const [documentosFlat, setDocumentosFlat] = useState<any[]>([])
  const [expandedOS, setExpandedOS] = useState<number | null>(null)
  
  const [activeTab, setActiveTab] = useState<'pendentes' | 'concluidas'>('pendentes')
  const [searchTerm, setSearchTerm] = useState('')
  
  const [mesFiltro, setMesFiltro] = useState(() => {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
  });

  const [currentPage, setCurrentPage] = useState(1)
  const itemsPerPage = 15

  const [sortConfig, setSortConfig] = useState<{ key: string, direction: 'asc' | 'desc' }>({ key: 'os', direction: 'desc' });

  // Pega o usuário logado do contexto
  const { user } = useAuth();

  const carregarDados = () => {
    axios.get('http://127.0.0.1:8000/api/triagem/auditoria')
      .then(res => setDocumentosFlat(res.data))
      .catch(err => console.error("API falhou", err))
  }

  useEffect(() => { carregarDados() }, [])

  // Função atualizada para enviar o nome do auditor
  const toggleValidacao = async (osId: number, atualVerificado: number) => {
    if (atualVerificado === 1) {
      try {
        await axios.put(`http://127.0.0.1:8000/api/os/${osId}/desmarcar`);
        carregarDados();
      } catch (err) {
        alert("Erro ao desmarcar OS.");
      }
    } else {
      try {
        await axios.put(`http://127.0.0.1:8000/api/os/${osId}/verificar`, {
          usuario: user?.full_name || 'Sistema'
        });
        carregarDados();
      } catch (err) {
        alert("Erro ao validar OS.");
      }
    }
  }

  const requestSort = (key: string) => {
    let direction: 'asc' | 'desc' = 'asc';
    if (sortConfig.key === key && sortConfig.direction === 'asc') {
      direction = 'desc';
    }
    setSortConfig({ key, direction });
  };

  const agrupadosPorOS = useMemo(() => {
    const mapa = documentosFlat.reduce((acc: any, doc: any) => {
      if (!acc[doc.os]) {
        const dataMes = doc.data_os ? doc.data_os.substring(0, 7) : '';
        acc[doc.os] = {
          os: doc.os,
          cod_empresa: doc.cod_empresa,
          nome_empresa: doc.nome_empresa,
          status_download: doc.status_download,
          verificado: doc.verificado || 0,
          data_os: doc.data_os,
          mes_ano: dataMes, 
          auditado_por: doc.auditado_por, 
          data_auditoria: doc.data_auditoria,
          arquivos: [],
          temErroTriagem: false,
          temTomadosPendente: false,
          temTomadosProcessado: false
        }
      }
      acc[doc.os].arquivos.push(doc)
      if (doc.status_triagem !== 'SUCESSO') acc[doc.os].temErroTriagem = true;
      if (doc.categoria_ia === 'nota_servico') {
         if (doc.status_tomados === 'PENDENTE') acc[doc.os].temTomadosPendente = true;
         if (doc.status_tomados === 'PROCESSADO') acc[doc.os].temTomadosProcessado = true;
      }
      return acc
    }, {})

    return Object.values(mapa).map((grupo: any) => {
      let status_tomados = 'N/A';
      if (grupo.temTomadosPendente) status_tomados = 'PROCESSANDO';
      else if (grupo.temTomadosProcessado) status_tomados = 'CONCLUIDO';

      return {
        ...grupo,
        status_triagem_geral: grupo.temErroTriagem ? 'ERRO' : 'SUCESSO',
        status_tomados_geral: status_tomados,
        total_arquivos: grupo.arquivos.length
      }
    }) as any[]
  }, [documentosFlat])

  const filtrados = useMemo(() => {
    let filtered = agrupadosPorOS.filter(grupo => {
      const abaMatch = activeTab === 'pendentes' ? grupo.verificado === 0 : grupo.verificado === 1;
      const mesMatch = mesFiltro ? grupo.mes_ano === mesFiltro : true;
      const lowerSearch = searchTerm.toLowerCase();
      const textMatch = !searchTerm || 
        String(grupo.os).includes(lowerSearch) || 
        (grupo.nome_empresa && grupo.nome_empresa.toLowerCase().includes(lowerSearch)) ||
        (grupo.cod_empresa && String(grupo.cod_empresa).includes(lowerSearch));

      return abaMatch && mesMatch && textMatch;
    });

    filtered.sort((a, b) => {
      if (a[sortConfig.key] < b[sortConfig.key]) {
        return sortConfig.direction === 'asc' ? -1 : 1;
      }
      if (a[sortConfig.key] > b[sortConfig.key]) {
        return sortConfig.direction === 'asc' ? 1 : -1;
      }
      return 0;
    });

    return filtered;
  }, [agrupadosPorOS, activeTab, searchTerm, mesFiltro, sortConfig]);

  useEffect(() => { setCurrentPage(1); }, [searchTerm, activeTab, mesFiltro])

  const totalPages = Math.ceil(filtrados.length / itemsPerPage)
  const currentItems = filtrados.slice((currentPage - 1) * itemsPerPage, currentPage * itemsPerPage)

  const getSortIcon = (colName: string) => {
    if (sortConfig.key !== colName) return null;
    return sortConfig.direction === 'asc' ? <ChevronUp size={14} className="inline ml-1" /> : <ChevronDown size={14} className="inline ml-1" />;
  };

  return (
    <div className="page-container">
      
      {/* HEADER DA PÁGINA */}
      <div className="page-header-row">
        <div>
          <h1 className="page-title">Auditoria de Solicitações</h1>
          <p className="page-subtitle">Valide e libere as OS processadas pela inteligência artificial.</p>
        </div>
      </div>

      {/* ABAS (TABS) MODERNAS */}
      <div className="tabs-container">
        <button 
          className={`tab-item ${activeTab === 'pendentes' ? 'active' : ''}`}
          onClick={() => setActiveTab('pendentes')}
        >
          Pendentes de Validação
        </button>
        <button 
          className={`tab-item ${activeTab === 'concluidas' ? 'active' : ''}`}
          onClick={() => setActiveTab('concluidas')}
        >
          Validadas / Concluídas
        </button>
      </div>

      {/* FILTROS E PESQUISA */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
        <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
          Mostrando <strong>{filtrados.length}</strong> resultados
        </div>
        
        <div style={{ display: 'flex', gap: '12px' }}>
          <div style={{ display: 'flex', alignItems: 'center', background: 'white', padding: '0 12px', borderRadius: '10px', border: '1px solid var(--border)', height: '42px' }}>
            <Calendar size={16} style={{ color: 'var(--primary)', marginRight: '8px' }} />
            <DatePicker
              selected={new Date(parseInt(mesFiltro.split('-')[0]), parseInt(mesFiltro.split('-')[1]) - 1, 1)}
              onChange={(date: Date | null) => {
                if (date) {
                  setMesFiltro(`${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`);
                }
              }}
              dateFormat="MMMM yyyy"
              showMonthYearPicker
              locale="pt-BR"
              className="bg-transparent border-none font-bold text-sm text-[#3a3a3a] focus:ring-0 cursor-pointer uppercase outline-none w-32"
            />
          </div>

          <div style={{ position: 'relative' }}>
            <input 
              type="text" 
              placeholder="Buscar OS, Cód ou Empresa..." 
              className="login-input"
              style={{ width: '280px', height: '42px', paddingLeft: '16px', paddingRight: '16px', fontSize: '0.85rem' }}
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
            />
          </div>
        </div>
      </div>

      {/* TABELA DE AUDITORIA */}
      <div className="table-card">
        <table className="modern-table">
          <thead>
            <tr>
              <th style={{ width: '48px' }}></th>
              <th style={{ width: '80px', textAlign: 'center' }}>Validar</th>
              <th style={{ width: '160px', cursor: 'pointer' }} onClick={() => requestSort('os')}>
                Solicitação {getSortIcon('os')}
              </th>
              <th style={{ cursor: 'pointer' }} onClick={() => requestSort('nome_empresa')}>
                Cliente {getSortIcon('nome_empresa')}
              </th>
              <th style={{ textAlign: 'center', width: '100px', cursor: 'pointer' }} onClick={() => requestSort('total_arquivos')}>
                Arquivos {getSortIcon('total_arquivos')}
              </th>
              <th style={{ textAlign: 'center', width: '120px' }}>Download</th>
              <th style={{ textAlign: 'center', width: '120px' }}>Triagem</th>
              <th style={{ textAlign: 'center', width: '140px', cursor: 'pointer' }} onClick={() => requestSort('status_tomados_geral')}>
                Tomados {getSortIcon('status_tomados_geral')}
              </th>
            </tr>
          </thead>
          <tbody>
            {currentItems.length === 0 ? (
              <tr><td colSpan={7} style={{ textAlign: 'center', padding: '4rem', color: 'var(--text-muted)' }}>Nenhuma solicitação encontrada na competência selecionada.</td></tr>
            ) : currentItems.map((grupo) => (
              <React.Fragment key={`group-${grupo.os}`}>
                <tr style={{ background: 'white', borderBottom: expandedOS === grupo.os ? 'none' : '1px solid #f1f5f9', transition: 'background 0.2s' }}>
                  
                  <td style={{ textAlign: 'center' }}>
                    <button className="btn-expand" onClick={() => setExpandedOS(expandedOS === grupo.os ? null : grupo.os)}>
                      {expandedOS === grupo.os ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
                    </button>
                  </td>
                  
                  <td style={{ textAlign: 'center' }}>
                    <button 
                      onClick={() => toggleValidacao(grupo.os, grupo.verificado)}
                      className={`check-btn ${grupo.verificado ? 'checked' : ''}`}
                      style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', width: '100%' }}
                    >
                      {grupo.verificado ? <CheckCircle size={26} fill="#dcfce7" /> : <Circle size={26} />}
                    </button>
                  </td>

                  <td>
                    <div className="os-info">
                      <span className="os-number">#{grupo.os}</span>
                      <span className="os-date">
                        {grupo.data_os ? new Date(grupo.data_os).toLocaleDateString('pt-BR') : '--/--/----'}
                      </span>
                    </div>
                    
                    {grupo.verificado === 1 && grupo.auditado_por && (
                        <div style={{ marginTop: '8px', display: 'flex', flexDirection: 'column', gap: '2px', whiteSpace: 'nowrap' }}>
                            <span style={{ display: 'flex', alignItems: 'center', gap: '4px', fontSize: '0.7rem', color: '#16a34a', fontWeight: 700 }}>
                                <UserCheck size={12} /> Validado por {grupo.auditado_por.split(' ')[0]}
                            </span>
                            <span style={{ fontSize: '0.65rem', color: '#22c55e', marginLeft: '16px', fontWeight: 500 }}>
                                {grupo.data_auditoria ? new Date(grupo.data_auditoria).toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' }) : ''}
                            </span>
                        </div>
                    )}
                  </td>
                  
                  <td>
                    <div className="client-info">
                      <span className="client-name">{grupo.nome_empresa}</span>
                      <span className="client-code">Cód: {grupo.cod_empresa}</span>
                    </div>
                  </td>
                  
                  <td style={{ textAlign: 'center', fontWeight: '800', color: 'var(--text-muted)', fontSize: '0.9rem' }}>
                    {grupo.total_arquivos}
                  </td>

                  <td style={{ textAlign: 'center' }}>
                    <span className={`status-pill ${grupo.status_download === 'SUCESSO' ? 'sucesso' : 'erro'}`}>
                      {grupo.status_download}
                    </span>
                  </td>
                                    
                  <td style={{ textAlign: 'center' }}>
                    <span className={`status-pill ${grupo.status_triagem_geral === 'SUCESSO' ? 'sucesso' : 'erro'}`}>
                      {grupo.status_triagem_geral}
                    </span>
                  </td>
                  
                  <td style={{ textAlign: 'center' }}>
                    {grupo.status_tomados_geral === 'CONCLUIDO' ? (
                      <a 
                        href={`http://127.0.0.1:8000/api/download/tomados/${grupo.os}`}
                        title="Baixar planilhas (.zip)"
                        className="action-btn-outline"
                        style={{ textDecoration: 'none' }}
                      >
                        <Download size={14} /> Planilhas
                      </a>
                    ) : grupo.status_tomados_geral === 'PROCESSANDO' ? (
                      <span className="status-badge status-pendente">Na Fila</span>
                    ) : (
                      <span style={{ 
                        display: 'inline-flex', padding: '4px 12px', borderRadius: '8px', 
                        background: '#f1f5f9', color: '#94a3b8', fontSize: '0.75rem', fontWeight: 700
                      }}>
                        N/A
                      </span>
                    )}
                  </td>                  
                </tr>
                
                {/* SUBTABELA EXPANSÍVEL */}
                {expandedOS === grupo.os && (
                  <tr key={`child-${grupo.os}`}>
                    <td colSpan={7} style={{ padding: 0 }}>
                      <SubTable arquivos={grupo.arquivos} />
                    </td>
                  </tr>
                )}
              </React.Fragment>
            ))}
          </tbody>
        </table>
        
        {/* PAGINAÇÃO */}
        <div className="pagination-container">
          <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
            Página <strong>{currentPage}</strong> de <strong>{totalPages || 1}</strong>
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
    </div>
  )
}
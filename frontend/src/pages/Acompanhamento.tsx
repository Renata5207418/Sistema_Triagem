import React, { useState, useEffect, useMemo } from 'react'
import axios from 'axios'
import { Download, ChevronDown, ChevronUp, ChevronLeft, ChevronRight, CheckCircle, Circle, FileText, Calendar } from 'lucide-react'
import DatePicker, { registerLocale } from "react-datepicker";
import "react-datepicker/dist/react-datepicker.css";
import { ptBR } from "date-fns/locale"; 

registerLocale("pt-BR", ptBR);

// --- COMPONENTE INTERNO: Paginação dos Arquivos (Sub-tabela Minimalista) ---
const SubTable = ({ arquivos }: { arquivos: any[] }) => {
  const [page, setPage] = useState(1);
  const itemsPerPage = 10;
  const totalPages = Math.ceil(arquivos.length / itemsPerPage);
  const current = arquivos.slice((page - 1) * itemsPerPage, page * itemsPerPage);

  return (
    <div style={{ 
      padding: '12px 24px 24px 64px', 
      background: '#fcfcfd', 
      borderBottom: '1px solid var(--border)'
    }}>
      <div style={{ borderLeft: '2px solid var(--border)', paddingLeft: '24px' }}>
        
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.8rem' }}>
          <thead>
            <tr>
              <th style={{ textAlign: 'left', paddingBottom: '12px', color: 'var(--text-muted)', fontWeight: 500, textTransform: 'uppercase', letterSpacing: '0.05em', fontSize: '0.7rem' }}>Nome do Arquivo Original</th>
              <th style={{ textAlign: 'left', paddingBottom: '12px', color: 'var(--text-muted)', fontWeight: 500, textTransform: 'uppercase', letterSpacing: '0.05em', fontSize: '0.7rem', width: '180px' }}>Classificação IA</th>
              <th style={{ textAlign: 'right', paddingBottom: '12px', color: 'var(--text-muted)', fontWeight: 500, textTransform: 'uppercase', letterSpacing: '0.05em', fontSize: '0.7rem', width: '120px' }}>Status</th>
            </tr>
          </thead>
          <tbody>
            {current.map((arquivo: any) => (
              <tr key={arquivo.id} style={{ borderBottom: '1px dashed #e4e4e7' }}>
                <td style={{ padding: '10px 0', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <FileText size={14} style={{ opacity: 0.5 }} />
                  {arquivo.arquivo}
                </td>
                <td style={{ padding: '10px 0' }}>
                  <span style={{ padding: '4px 10px', background: 'white', color: '#475569', borderRadius: '6px', fontSize: '0.7rem', fontWeight: 500, border: '1px solid #e2e8f0', boxShadow: '0 1px 2px rgba(0,0,0,0.02)' }}>
                    {arquivo.categoria_ia || 'N/A'}
                  </span>
                </td>
                <td style={{ padding: '10px 0', textAlign: 'right' }}>
                  <span className={`status-badge ${arquivo.status_triagem === 'SUCESSO' ? 'status-ok' : 'status-erro'}`} style={{ fontSize: '0.65rem' }}>
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
                style={{ padding: '4px 12px', fontSize: '0.75rem', background: 'white' }} 
              >
                <ChevronLeft size={14} /> Anterior
              </button>
              <button 
                className="page-btn" 
                onClick={() => setPage(p => Math.min(p + 1, totalPages))} 
                disabled={page === totalPages} 
                style={{ padding: '4px 12px', fontSize: '0.75rem', background: 'white' }} 
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

  const carregarDados = () => {
    axios.get('http://127.0.0.1:8000/api/triagem/auditoria')
      .then(res => setDocumentosFlat(res.data))
      .catch(err => console.error("API falhou", err))
  }

  useEffect(() => { carregarDados() }, [])

  const toggleValidacao = async (osId: number, atualVerificado: number) => {
    const endpoint = atualVerificado === 1 ? 'desmarcar' : 'verificar';
    try {
      await axios.put(`http://127.0.0.1:8000/api/os/${osId}/${endpoint}`);
      carregarDados();
    } catch (err) {
      alert("Erro ao atualizar validação.");
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
    <div>
      <header style={{ marginBottom: '2rem' }}>
        <h2 style={{ fontSize: '1.8rem', fontWeight: 'bold', letterSpacing: '-0.02em' }}>Auditoria de Solicitações</h2>
        <p style={{ color: 'var(--text-muted)', marginTop: '4px' }}>Valide e libere as OS processadas pela inteligência artificial.</p>
      </header>

      <div style={{ display: 'flex', gap: '24px', borderBottom: '1px solid var(--border)', marginBottom: '1.5rem' }}>
        <button 
          onClick={() => setActiveTab('pendentes')}
          style={{ 
            background: 'none', border: 'none', cursor: 'pointer', padding: '0 0 12px 0',
            fontSize: '0.95rem', fontWeight: 600, transition: '0.2s',
            color: activeTab === 'pendentes' ? 'var(--primary)' : 'var(--text-muted)',
            borderBottom: activeTab === 'pendentes' ? '2px solid var(--primary)' : '2px solid transparent'
          }}
        >
          Pendentes de Validação
        </button>
        <button 
          onClick={() => setActiveTab('concluidas')}
          style={{ 
            background: 'none', border: 'none', cursor: 'pointer', padding: '0 0 12px 0',
            fontSize: '0.95rem', fontWeight: 600, transition: '0.2s',
            color: activeTab === 'concluidas' ? '#16a34a' : 'var(--text-muted)',
            borderBottom: activeTab === 'concluidas' ? '2px solid #16a34a' : '2px solid transparent'
          }}
        >
          Validadas / Concluídas
        </button>
      </div>

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
        <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
          Mostrando <strong>{filtrados.length}</strong> resultados
        </div>
        
        <div style={{ display: 'flex', gap: '12px' }}>
          <div style={{ display: 'flex', alignItems: 'center', background: 'white', padding: '0 12px', borderRadius: '8px', border: '1px solid var(--border)', height: '38px', transition: 'border-color 0.2s' }}>
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

          <input 
            type="text" 
            placeholder="Buscar OS, Cód ou Empresa..." 
            className="global-search"
            style={{ width: '250px', padding: '0 16px', borderRadius: '8px', border: '1px solid var(--border)', height: '38px', outline: 'none', transition: 'border-color 0.2s' }}
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
          />
        </div>
      </div>

      <div className="table-container" style={{ borderRadius: '12px', border: '1px solid var(--border)', overflow: 'hidden', boxShadow: '0 1px 3px rgba(0,0,0,0.04)' }}>
        <table className="custom-table" style={{ borderCollapse: 'collapse', width: '100%', textAlign: 'left' }}>
          <thead style={{ background: '#f8fafc', borderBottom: '1px solid var(--border)' }}>
            <tr>
              <th style={{ width: '48px', padding: '14px 16px' }}></th>
              <th style={{ width: '60px', textAlign: 'center', padding: '14px 16px', color: 'var(--text-muted)', fontSize: '0.75rem', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Validar</th>
              <th 
                style={{ width: '140px', cursor: 'pointer', userSelect: 'none', padding: '14px 16px', color: 'var(--text-muted)', fontSize: '0.75rem', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }} 
                onClick={() => requestSort('os')}
                title="Ordenar por OS"
              >
                Solicitação {getSortIcon('os')}
              </th>
              <th 
                style={{ cursor: 'pointer', userSelect: 'none', padding: '14px 16px', color: 'var(--text-muted)', fontSize: '0.75rem', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }} 
                onClick={() => requestSort('nome_empresa')}
                title="Ordenar por Cliente"
              >
                Cliente {getSortIcon('nome_empresa')}
              </th>
              <th 
                style={{ textAlign: 'center', width: '90px', cursor: 'pointer', userSelect: 'none', padding: '14px 16px', color: 'var(--text-muted)', fontSize: '0.75rem', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }} 
                onClick={() => requestSort('total_arquivos')}
                title="Ordenar por Quantidade de Arquivos"
              >
                Arquivos {getSortIcon('total_arquivos')}
              </th>
              <th style={{ textAlign: 'center', width: '110px', padding: '14px 16px', color: 'var(--text-muted)', fontSize: '0.75rem', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Download</th>
              <th style={{ textAlign: 'center', width: '110px', padding: '14px 16px', color: 'var(--text-muted)', fontSize: '0.75rem', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Triagem</th>
              <th 
                style={{ textAlign: 'center', width: '120px', cursor: 'pointer', userSelect: 'none', padding: '14px 16px', color: 'var(--text-muted)', fontSize: '0.75rem', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}
                onClick={() => requestSort('status_tomados_geral')}
                title="Ordenar por Status"
              >
                Tomados {getSortIcon('status_tomados_geral')}
              </th>
            </tr>
          </thead>
          <tbody>
            {currentItems.length === 0 ? (
              <tr><td colSpan={8} style={{ textAlign: 'center', padding: '3rem', color: 'var(--text-muted)' }}>Nenhuma solicitação encontrada.</td></tr>
            ) : currentItems.map((grupo) => (
              <React.Fragment key={`group-${grupo.os}`}>
                <tr style={{ background: 'white', borderBottom: expandedOS === grupo.os ? 'none' : '1px solid var(--border)', transition: 'background 0.2s' }}>
                  
                  <td style={{ textAlign: 'center', padding: '14px 16px' }}>
                    <button className="btn-expand" onClick={() => setExpandedOS(expandedOS === grupo.os ? null : grupo.os)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)' }}>
                      {expandedOS === grupo.os ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
                    </button>
                  </td>
                  
                  <td style={{ textAlign: 'center', verticalAlign: 'middle', padding: '14px 16px' }}>
                    <button 
                      onClick={() => toggleValidacao(grupo.os, grupo.verificado)}
                      style={{ background: 'none', border: 'none', cursor: 'pointer', color: grupo.verificado ? '#16a34a' : '#d1d5db', transition: '0.2s', display: 'flex', alignItems: 'center', justifyContent: 'center', width: '100%' }}
                    >
                      {grupo.verificado ? <CheckCircle size={22} fill="#dcfce7" /> : <Circle size={22} />}
                    </button>
                  </td>

                  <td style={{ padding: '14px 16px' }}>
                    <div style={{ fontWeight: 800, color: 'var(--primary)', fontSize: '0.9rem' }}>#{grupo.os}</div>
                    <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '2px', fontWeight: 500 }}>
                      {grupo.data_os ? new Date(grupo.data_os).toLocaleDateString('pt-BR') : '--/--/----'}
                    </div>
                  </td>
                  
                  <td style={{ padding: '14px 16px' }}>
                    <div style={{ fontWeight: 600, color: 'var(--text-main)', fontSize: '0.85rem' }}>{grupo.nome_empresa}</div>
                    <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '2px' }}>Cód: {grupo.cod_empresa}</div>
                  </td>
                  
                  <td style={{ textAlign: 'center', fontWeight: '600', color: 'var(--text-muted)', fontSize: '0.85rem', padding: '14px 16px' }}>
                    {grupo.total_arquivos}
                  </td>
                  
                  <td style={{ textAlign: 'center', padding: '14px 16px' }}>
                    <span className={`status-badge ${grupo.status_download === 'SUCESSO' ? 'status-ok' : 'status-erro'}`}>
                      {grupo.status_download}
                    </span>
                  </td>
                  
                  <td style={{ textAlign: 'center', padding: '14px 16px' }}>
                    <span className={`status-badge ${grupo.status_triagem_geral === 'SUCESSO' ? 'status-ok' : 'status-erro'}`}>
                      {grupo.status_triagem_geral}
                    </span>
                  </td>
                  
                  <td style={{ textAlign: 'center', padding: '14px 16px' }}>
                    {grupo.status_tomados_geral === 'CONCLUIDO' ? (
                      <a 
                        href={`http://127.0.0.1:8000/api/download/tomados/${grupo.os}`}
                        title="Baixar planilhas (.zip)"
                        style={{ 
                          display: 'inline-flex', 
                          alignItems: 'center', 
                          gap: '6px', 
                          padding: '4px 12px', 
                          background: '#ffffff', 
                          color: 'var(--primary)', 
                          border: '0.5px solid var(--primary-hover)', 
                          borderRadius: '9999px',
                          textDecoration: 'none', 
                          fontSize: '0.75rem', 
                          fontWeight: 600, 
                          letterSpacing: '0.02em',
                          transition: 'all 0.2s ease' 
                        }}
                        onMouseEnter={(e) => { e.currentTarget.style.background = 'var(--primary-light)'; }}
                        onMouseLeave={(e) => { e.currentTarget.style.background = '#ffffff'; }}
                      >
                        <Download size={14} /> Planilhas
                      </a>
                    ) : grupo.status_tomados_geral === 'PROCESSANDO' ? (
                      <span className="status-badge status-pendente">Na Fila</span>
                    ) : (
                      <span style={{ 
                        display: 'inline-flex', 
                        padding: '4px 12px', 
                        borderRadius: '9999px', 
                        background: '#f4f4f5', 
                        color: '#a1a1aa', 
                        fontSize: '0.75rem', 
                        fontWeight: 600, 
                        border: '1px solid #e4e4e7',
                        letterSpacing: '0.02em'
                      }}>
                        N/A
                      </span>
                    )}
                  </td>                  
                </tr>
                {expandedOS === grupo.os && (
                  <tr key={`child-${grupo.os}`}>
                    <td colSpan={8} style={{ padding: 0 }}>
                      <SubTable arquivos={grupo.arquivos} />
                    </td>
                  </tr>
                )}
              </React.Fragment>
            ))}
          </tbody>
        </table>

        <div className="pagination-container" style={{ borderTop: '1px solid var(--border)', padding: '16px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: 'white' }}>
          <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
            Página <strong>{currentPage}</strong> de <strong>{totalPages || 1}</strong>
          </span>
          <div style={{ display: 'flex', gap: '8px' }}>
            <button className="page-btn" onClick={() => setCurrentPage(prev => Math.max(prev - 1, 1))} disabled={currentPage === 1} style={{ background: 'white', border: '1px solid var(--border)', padding: '6px 12px', borderRadius: '8px', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '4px', fontSize: '0.8rem', fontWeight: 500, color: 'var(--text-main)' }}>
              <ChevronLeft size={16} /> Anterior
            </button>
            <button className="page-btn" onClick={() => setCurrentPage(prev => Math.min(prev + 1, totalPages))} disabled={currentPage === totalPages || totalPages === 0} style={{ background: 'white', border: '1px solid var(--border)', padding: '6px 12px', borderRadius: '8px', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '4px', fontSize: '0.8rem', fontWeight: 500, color: 'var(--text-main)' }}>
              Próxima <ChevronRight size={16} />
            </button>
          </div>
        </div>
      </div>      
    </div>
  )
}
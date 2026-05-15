import React, { useState, useEffect, useMemo, useRef } from 'react'
import api from '../services/api';
import { Download, ChevronDown, ChevronUp, ChevronLeft, ChevronRight, CheckCircle, Circle, FileText, Calendar, UserCheck, AlertTriangle, UploadCloud, X, Upload, Search, Filter, Lightbulb } from 'lucide-react'
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
                  <span className={`status-badge ${
                    arquivo.status_triagem.includes('SUCESSO') ? 'status-ok' : 
                    arquivo.status_triagem === 'RESOLVIDO_UPLOAD' ? 'status-pendente' : 
                    'status-erro'
                  }`}
                  style={arquivo.status_triagem === 'RESOLVIDO_UPLOAD' ? { background: '#f1f5f9', color: '#64748b', border: '1px solid #cbd5e1' } : {}}
                  >
                    {arquivo.status_triagem.replace('_', ' ')}
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
              <button className="page-btn" onClick={() => setPage(p => Math.max(p - 1, 1))} disabled={page === 1} style={{ padding: '4px 12px', fontSize: '0.75rem' }}>
                <ChevronLeft size={14} /> Anterior
              </button>
              <button className="page-btn" onClick={() => setPage(p => Math.min(p + 1, totalPages))} disabled={page === totalPages} style={{ padding: '4px 12px', fontSize: '0.75rem' }}>
                Próxima <ChevronRight size={14} />
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

// === NOVO: FUNÇÃO PARA ESTILIZAR AS PÍLULAS (BADGES) UNIFORMEMENTE ===
const getPillStyle = (status: string): React.CSSProperties => {
  const baseStyle: React.CSSProperties = {
    padding: '4px 10px',
    borderRadius: '8px',
    fontSize: '0.65rem',
    fontWeight: 800,
    whiteSpace: 'nowrap', // Garante que não quebre de linha
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    letterSpacing: '0.02em',
    border: '1px solid transparent',
    minWidth: '100px' // <-- AJUSTE AQUI: Força a largura mínima para todos ficarem iguais
  };

  switch (status) {
    case 'SUCESSO':
    case 'CONCLUIDO':
      return { ...baseStyle, background: '#dcfce7', color: '#16a34a', borderColor: '#86efac' };
    case 'ERRO':
      return { ...baseStyle, background: '#fef2f2', color: '#dc2626', borderColor: '#fca5a5' };
    case 'PENDENTE':
    case 'PROCESSANDO':
    case 'Na Fila':
    case 'AÇÃO MANUAL':
      return { ...baseStyle, background: '#fff7ed', color: '#ea580c', borderColor: '#fdba74' }; 

    case 'SÓ MENSAGEM':
      return { ...baseStyle, background: '#edfcff', color: '#0c99ea', borderColor: '#74ddfd' }; 
    case 'Não possui':
    case 'N/A':
      return { ...baseStyle, background: 'var(--primary-light)', color: 'var(--primary)', borderColor: 'var(--primary-light)' }; 
    default:
      return { ...baseStyle, background: '#f1f5f9', color: '#64748b', borderColor: '#e2e8f0' }; 
  }
};

export default function Acompanhamento() {
  const [documentosFlat, setDocumentosFlat] = useState<any[]>([])
  const [quarentenaDocs, setQuarentenaDocs] = useState<any[]>([]) 
  const [expandedOS, setExpandedOS] = useState<number | null>(null)
  
  const [activeTab, setActiveTab] = useState<'pendentes' | 'concluidas' | 'quarentena'>('pendentes')
  const [searchTerm, setSearchTerm] = useState('')

  // Filtros Gerais
  const [filtroDownload, setFiltroDownload] = useState('todos')
  const [filtroTriagem, setFiltroTriagem] = useState('todos')
  const [filtroTomados, setFiltroTomados] = useState('todos')
  
  // === ESTADOS DO NOVO FILTRO EXCEL (QUARENTENA) ===
  const [isFilterOpen, setIsFilterOpen] = useState(false);
  const [deselectedFilters, setDeselectedFilters] = useState<string[]>([]);
  const [tempDeselected, setTempDeselected] = useState<string[]>([]);
  const filterRef = useRef<HTMLDivElement>(null);

  // Fecha o filtro estilo Excel ao clicar fora
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (filterRef.current && !filterRef.current.contains(event.target as Node)) {
        setIsFilterOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);
    
  const [mesFiltro, setMesFiltro] = useState(() => {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
  });

  const [currentPage, setCurrentPage] = useState(1)
  const itemsPerPage = 15
  const [sortConfig, setSortConfig] = useState<{ key: string, direction: 'asc' | 'desc' }>({ key: 'os', direction: 'desc' });

  const [modalUploadOpen, setModalUploadOpen] = useState(false);
  const [modalSuccessOpen, setModalSuccessOpen] = useState(false);
  const [docToFix, setDocToFix] = useState<any>(null);
  const [selectedFiles, setSelectedFiles] = useState<FileList | null>(null);
  const [uploading, setUploading] = useState(false);

  const { user } = useAuth();

  const carregarDados = () => {
    api.get('/api/triagem/auditoria')
      .then(res => setDocumentosFlat(res.data))
      .catch(err => console.error("API falhou", err))
      
    api.get('/api/quarentena/listar')
      .then(res => setQuarentenaDocs(res.data))
      .catch(err => console.error("API Quarentena falhou", err))
  }

  useEffect(() => {
    carregarDados();
    const intervalo = window.setInterval(() => {
      carregarDados();
    }, 15000);
    return () => window.clearInterval(intervalo);
  }, []);

  const toggleValidacao = async (osId: number, atualVerificado: number) => {
    if (atualVerificado === 1) {
      try {
        await api.put(`/api/os/${osId}/desmarcar`);
        carregarDados();
      } catch (err) { alert("Erro ao desmarcar OS."); }
    } else {
      try {
        await api.put(`/api/os/${osId}/verificar`, { usuario: user?.full_name || 'Sistema' });
        carregarDados();
      } catch (err) { alert("Erro ao validar OS."); }
    }
  }

  const handleUploadCorrecao = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedFiles || selectedFiles.length === 0 || !docToFix) return;

    setUploading(true);
    const formData = new FormData();
    formData.append('id_doc_original', docToFix.id.toString());
    Array.from(selectedFiles).forEach(file => { formData.append('arquivos', file); });

    try {
      await api.post(`/api/quarentena/upload-correcao/${docToFix.os}`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });
      setModalUploadOpen(false);
      setSelectedFiles(null);
      setDocToFix(null);
      carregarDados();
      
      setModalSuccessOpen(true);
      setTimeout(() => setModalSuccessOpen(false), 4000); 
      
    } catch (err) {
      console.error(err);
      alert("Erro ao fazer upload da correção.");
    } finally {
      setUploading(false);
    }
  };

  const requestSort = (key: string) => {
    let direction: 'asc' | 'desc' = 'asc';
    if (sortConfig.key === key && sortConfig.direction === 'asc') direction = 'desc';
    setSortConfig({ key, direction });
  };

  const agrupadosPorOS = useMemo(() => {
    const mapa = documentosFlat.reduce((acc: any, doc: any) => {
      if (!acc[doc.os]) {
        const dataMes = doc.data_os ? doc.data_os.substring(0, 7) : '';
        acc[doc.os] = {
          os: doc.os, cod_empresa: doc.cod_empresa, nome_empresa: doc.nome_empresa, status_download: doc.status_download,
          qtd_anexos: doc.qtd_anexos_esperados, verificado: doc.verificado || 0, data_os: doc.data_os,
          mes_ano: dataMes, auditado_por: doc.auditado_por, data_auditoria: doc.data_auditoria, arquivos: [],
          temErroTriagem: false, temTomadosPendente: false, temTomadosProcessado: false
        }
      }
      if (doc.id) {
        acc[doc.os].arquivos.push(doc)
        const statusDeErro = ['ERRO', 'ATENCAO', 'PENDENTE_SENHA'];
        if (statusDeErro.includes(doc.status_triagem)) acc[doc.os].temErroTriagem = true;
        if (doc.categoria_ia === 'nota_servico') {
           if (doc.status_tomados === 'PENDENTE') acc[doc.os].temTomadosPendente = true;
           if (doc.status_tomados === 'PROCESSADO') acc[doc.os].temTomadosProcessado = true;
        }
      }
      return acc
    }, {})

    return Object.values(mapa).map((grupo: any) => {
      let status_tomados = 'Não possui';
      if (grupo.temTomadosPendente) status_tomados = 'PROCESSANDO';
      else if (grupo.temTomadosProcessado) status_tomados = 'CONCLUIDO';
      
      let status_triagem = 'SUCESSO';
      if (grupo.qtd_anexos === 0 && grupo.arquivos.length === 0) status_triagem = 'Não possui';
      else if (grupo.arquivos.length === 0) status_triagem = 'PENDENTE';
      else if (grupo.temErroTriagem) status_triagem = 'ERRO';

      return { ...grupo, status_triagem_geral: status_triagem, status_tomados_geral: status_tomados, total_arquivos: grupo.arquivos.length }
    }) as any[]
  }, [documentosFlat])

  const { filtrados, totalPendentes, totalConcluidas } = useMemo(() => {
    const baseFiltrada = agrupadosPorOS.filter((grupo: any) => {
      const mesMatch = mesFiltro ? grupo.mes_ano === mesFiltro : true;
      const lowerSearch = searchTerm.toLowerCase();
      const textMatch = !searchTerm || String(grupo.os).includes(lowerSearch) || 
                       (grupo.nome_empresa && grupo.nome_empresa.toLowerCase().includes(lowerSearch)) ||
                       (grupo.cod_empresa && String(grupo.cod_empresa).includes(lowerSearch));
      return mesMatch && textMatch;
    });

    const pendentesCount = baseFiltrada.filter((g: any) => g.verificado === 0).length;
    const concluidasCount = baseFiltrada.filter((g: any) => g.verificado === 1).length;

    let filtered = baseFiltrada.filter((grupo: any) =>
      activeTab === 'pendentes' ? grupo.verificado === 0 : grupo.verificado === 1
    );

    if (filtroDownload !== 'todos') {
      filtered = filtered.filter((grupo: any) => {
        const statusReal = grupo.qtd_anexos === 0 ? 'SEM_ANEXO' : (grupo.status_download || 'PENDENTE');
        return statusReal === filtroDownload;
      });
    }

    if (filtroTriagem !== 'todos') {
      filtered = filtered.filter((grupo: any) => grupo.status_triagem_geral === filtroTriagem);
    }

    if (filtroTomados !== 'todos') {
      filtered = filtered.filter((grupo: any) => grupo.status_tomados_geral === filtroTomados);
    }

    filtered.sort((a: any, b: any) => {
      const valorA = a[sortConfig.key] ?? '';
      const valorB = b[sortConfig.key] ?? '';
      if (valorA < valorB) return sortConfig.direction === 'asc' ? -1 : 1;
      if (valorA > valorB) return sortConfig.direction === 'asc' ? 1 : -1;
      return 0;
    });

    return { filtrados: filtered, totalPendentes: pendentesCount, totalConcluidas: concluidasCount };
  }, [agrupadosPorOS, activeTab, searchTerm, mesFiltro, sortConfig, filtroDownload, filtroTriagem, filtroTomados]);

  const getMotivoExibicao = (doc: any) => {
    if (doc.categoria_ia === 'documento_unificado') return 'MÚLTIPLOS TIPOS';
    return doc.motivo_erro || 'Erro Desconhecido';
  };

  const motivosErroUnicos = useMemo(() => {
    const motivos = quarentenaDocs.map(getMotivoExibicao);
    return Array.from(new Set(motivos)).sort();
  }, [quarentenaDocs]);

  const quarentenaFiltrada = useMemo(() => {
    return quarentenaDocs.filter(doc => {
      const lowerSearch = searchTerm.toLowerCase();
      const textMatch = !searchTerm || 
                        String(doc.os).includes(lowerSearch) || 
                        (doc.empresa && doc.empresa.toLowerCase().includes(lowerSearch)) || 
                        (doc.nome_original && doc.nome_original.toLowerCase().includes(lowerSearch));
      
      const motivoAtual = getMotivoExibicao(doc);
      const erroMatch = !deselectedFilters.includes(motivoAtual);

      return textMatch && erroMatch;
    });
  }, [quarentenaDocs, searchTerm, deselectedFilters]);

  useEffect(() => { setCurrentPage(1); }, [searchTerm, activeTab, mesFiltro, filtroDownload, filtroTriagem, filtroTomados, deselectedFilters])

  const listToPaginate = activeTab === 'quarentena' ? quarentenaFiltrada : filtrados;
  const totalPages = Math.ceil(listToPaginate.length / itemsPerPage);
  const currentItems = listToPaginate.slice((currentPage - 1) * itemsPerPage, currentPage * itemsPerPage);

  const getSortIcon = (colName: string) => {
    if (sortConfig.key !== colName) return null;
    return sortConfig.direction === 'asc' ? <ChevronUp size={14} className="inline ml-1" /> : <ChevronDown size={14} className="inline ml-1" />;
  };

  const filtroSelectStyle: React.CSSProperties = {
    height: '42px', borderRadius: '10px', border: '1px solid #e2e8f0', background: '#f8fafc',
    color: '#334155', fontSize: '0.8rem', fontWeight: 600, padding: '0 12px', outline: 'none', cursor: 'pointer', transition: 'all 0.2s', maxWidth: '250px'
  };

  return (
    <div className="page-container">
      <div className="page-header-row">
        <div>
          <h1 className="page-title">Auditoria de Solicitações</h1>
          <p className="page-subtitle">Valide e libere as OS processadas pela inteligência artificial.</p>
        </div>
      </div>

      <div className="tabs-container">
        <button className={`tab-item ${activeTab === 'pendentes' ? 'active' : ''}`} onClick={() => setActiveTab('pendentes')} style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          Pendentes de Validação
          <span style={{ background: activeTab === 'pendentes' ? 'var(--primary)' : '#e2e8f0', color: activeTab === 'pendentes' ? 'white' : '#64748b', padding: '2px 8px', borderRadius: '12px', fontSize: '0.7rem', fontWeight: 700 }}>{totalPendentes}</span>
        </button>
        <button className={`tab-item ${activeTab === 'concluidas' ? 'active' : ''}`} onClick={() => setActiveTab('concluidas')} style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          Validadas / Concluídas
          <span style={{ background: activeTab === 'concluidas' ? '#16a34a' : '#e2e8f0', color: activeTab === 'concluidas' ? 'white' : '#64748b', padding: '2px 8px', borderRadius: '12px', fontSize: '0.7rem', fontWeight: 700 }}>{totalConcluidas}</span>
        </button>
        <button className={`tab-item ${activeTab === 'quarentena' ? 'active' : ''}`} onClick={() => setActiveTab('quarentena')} style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          Revisão (Arquivos com erro)
          <span style={{ background: activeTab === 'quarentena' ? '#ef4444' : '#e2e8f0', color: activeTab === 'quarentena' ? 'white' : '#64748b', padding: '2px 8px', borderRadius: '12px', fontSize: '0.7rem', fontWeight: 700 }}>{quarentenaDocs.length}</span>
        </button>
      </div>

      <div style={{ background: 'white', padding: '16px 20px', borderRadius: '12px', border: '1px solid var(--border)', marginBottom: '1.5rem', boxShadow: '0 1px 2px rgba(0, 0, 0, 0.05)', display: 'flex', flexDirection: 'column', gap: '16px' }}>
        
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '16px' }}>
          <div style={{ position: 'relative', flex: '1', minWidth: '280px', maxWidth: '450px' }}>
            <Search size={18} style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)', color: '#94a3b8' }} />
            <input 
              type="text" 
              placeholder={activeTab === 'quarentena' ? "Buscar OS, Cliente ou Arquivo..." : "Buscar OS, Cliente ou Código..."}
              className="login-input" 
              style={{ width: '100%', height: '42px', padding: '0 16px 0 40px', fontSize: '0.85rem', borderRadius: '10px', border: '1px solid #e2e8f0', outline: 'none', transition: 'border-color 0.2s' }} 
              value={searchTerm} 
              onChange={(e) => setSearchTerm(e.target.value)} 
            />
          </div>

          {activeTab !== 'quarentena' && (
            <div style={{ display: 'flex', gap: '12px', alignItems: 'center', flexWrap: 'wrap' }}>
              <div style={{ display: 'flex', alignItems: 'center', background: '#f8fafc', padding: '0 12px', borderRadius: '10px', border: '1px solid #e2e8f0', height: '42px' }}>
                <Calendar size={16} style={{ color: 'var(--primary)', marginRight: '8px' }} />
                <DatePicker
                  selected={new Date(parseInt(mesFiltro.split('-')[0]), parseInt(mesFiltro.split('-')[1]) - 1, 1)}
                  onChange={(date: Date | null) => { if (date) setMesFiltro(`${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`); }}
                  dateFormat="MMMM yyyy" showMonthYearPicker locale="pt-BR" className="bg-transparent border-none font-bold text-sm text-[#334155] outline-none w-32 cursor-pointer"
                />
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <Filter size={16} color="#94a3b8" style={{ marginRight: '4px' }} />
                <select value={filtroDownload} onChange={(e) => setFiltroDownload(e.target.value)} style={filtroSelectStyle}>
                  <option value="todos">Download: Todos</option>
                  <option value="SUCESSO">Download: Sucesso</option>
                  <option value="ALERTA_HUMANO">Download: Ação Manual</option>
                  <option value="PENDENTE">Download: Pendente</option>
                  <option value="SEM_ANEXO">Download: Só msg</option>
                </select>
                <select value={filtroTriagem} onChange={(e) => setFiltroTriagem(e.target.value)} style={filtroSelectStyle}>
                  <option value="todos">Triagem: Todos</option>
                  <option value="SUCESSO">Triagem: Sucesso</option>
                  <option value="ERRO">Triagem: Erro</option>
                  <option value="PENDENTE">Triagem: Pendente</option>
                  <option value="Não possui">Triagem: Não possui</option>
                </select>
                <select value={filtroTomados} onChange={(e) => setFiltroTomados(e.target.value)} style={filtroSelectStyle}>
                  <option value="todos">Tomados: Todos</option>
                  <option value="CONCLUIDO">Tomados: Concluído</option>
                  <option value="PROCESSANDO">Tomados: Na fila</option>
                  <option value="Não possui">Tomados: Não possui</option>
                </select>
              </div>

              {(filtroDownload !== 'todos' || filtroTriagem !== 'todos' || filtroTomados !== 'todos') && (
                <button onClick={() => { setFiltroDownload('todos'); setFiltroTriagem('todos'); setFiltroTomados('todos'); }} style={{ height: '42px', borderRadius: '10px', border: '1px solid #fca5a5', background: '#fef2f2', color: '#ef4444', fontSize: '0.8rem', fontWeight: 700, padding: '0 14px', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <X size={14} /> Limpar
                </button>
              )}
            </div>
          )}
        </div>

        <div style={{ height: '1px', background: '#f1f5f9', width: '100%' }}></div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '0.8rem', color: '#64748b' }}>
          <span>Utilize os filtros acima para refinar a lista.</span>
          <span>Mostrando <strong style={{ color: '#0f172a' }}>{listToPaginate.length}</strong> resultados encontrados</span>
        </div>
      </div>

      {modalUploadOpen && docToFix && (
        <div style={{ position: 'fixed', inset: 0, backgroundColor: 'rgba(15, 23, 42, 0.6)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 50, backdropFilter: 'blur(4px)' }}>
          <div style={{ background: 'white', borderRadius: '16px', width: '550px', maxWidth: '95%', maxHeight: '90vh', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
            
            <div style={{ padding: '20px 24px', borderBottom: '1px solid var(--border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexShrink: 0 }}>
              <h3 style={{ margin: 0, fontSize: '1.1rem', fontWeight: 800, display: 'flex', alignItems: 'center', gap: '8px' }}>
                <UploadCloud size={20} color="var(--primary)" /> Substituir Documento
              </h3>
              <button onClick={() => {setModalUploadOpen(false); setSelectedFiles(null);}} style={{ background: 'none', border: 'none', cursor: 'pointer' }}><X size={20} /></button>
            </div>
            
            <form onSubmit={handleUploadCorrecao} style={{ padding: '24px', overflowY: 'auto' }}>
              
              <div style={{ marginBottom: '16px', fontSize: '0.85rem', color: 'var(--text-muted)' }}>
                Você está enviando uma correção para a OS <strong>#{docToFix.os}</strong>, referente ao seguinte arquivo:
                <div style={{ 
                  marginTop: '8px', 
                  padding: '10px 12px', 
                  background: '#fef2f2', 
                  border: '1px solid #fca5a5', 
                  borderRadius: '8px', 
                  color: '#991b1b', 
                  fontWeight: 600, 
                  display: 'flex', 
                  alignItems: 'center', 
                  gap: '8px',
                  wordBreak: 'break-all'
                }}>
                  <FileText size={16} style={{ flexShrink: 0 }} />
                  {docToFix.nome_original}
                </div>
              </div>

              <div style={{ marginBottom: '24px', padding: '12px 16px', background: '#eff6ff', border: '1px solid #bfdbfe', borderRadius: '8px', fontSize: '0.8rem', color: '#1e3a8a' }}>
                <p style={{ margin: '0 0 8px 0', fontWeight: 800, display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <Lightbulb size={18} color="#2563eb" /> Dica de Classificação Automática
                </p>
                <p style={{ margin: '0 0 10px 0', lineHeight: '1.4' }}>
                  Renomeie o arquivo usando um dos prefixos abaixo (ex: <strong>EXTRATO_</strong>nome.pdf). O arquivo será classificado na hora sem custo de IA!
                </p>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                  {['TOMADAS', 'EMITIDAS', 'TERCEIROS', 'DANFE', 'EXTRATO', 'PLANILHAS', 'XML', 'RH', 'DOCUMENTOS_GERAIS'].map(p => (
                    <span key={p} style={{ background: 'white', border: '1px solid #93c5fd', padding: '2px 6px', borderRadius: '6px', fontSize: '0.7rem', fontWeight: 700, color: '#2563eb' }}>
                      {p}_
                    </span>
                  ))}
                </div>
                <p style={{ margin: '10px 0 0 0', fontSize: '0.75rem', color: '#3b82f6', fontStyle: 'italic', fontWeight: 600 }}>
                  * Use TOMADAS_, EMITIDAS_ ou TERCEIROS_ para notas de serviço. Assim o robô as direciona para a pasta exata instantaneamente!
                </p>
              </div>

              <div style={{ position: 'relative', border: '2px dashed #cbd5e1', borderRadius: '12px', padding: '32px 16px', textAlign: 'center', background: '#f8fafc', marginBottom: '24px', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', cursor: 'pointer' }}>
                
                <input 
                  type="file" 
                  multiple 
                  accept=".pdf" 
                  onChange={(e) => setSelectedFiles(e.target.files)} 
                  required 
                  style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', opacity: 0, cursor: 'pointer', zIndex: 10 }} 
                />
                
                <UploadCloud size={36} color={selectedFiles && selectedFiles.length > 0 ? "var(--primary)" : "#94a3b8"} style={{ marginBottom: '12px' }} />
                
                {selectedFiles && selectedFiles.length > 0 ? (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                    <span style={{ fontWeight: 800, color: 'var(--primary)', fontSize: '1rem' }}>
                      {selectedFiles.length} arquivo(s) selecionado(s)
                    </span>
                    <span style={{ fontSize: '0.75rem', color: '#64748b' }}>Clique novamente se quiser alterar</span>
                  </div>
                ) : (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                    <span style={{ fontWeight: 700, color: '#475569', fontSize: '0.95rem' }}>
                      Clique aqui ou arraste os arquivos
                    </span>
                    <span style={{ fontSize: '0.75rem', color: '#94a3b8' }}>Apenas arquivos .PDF</span>
                  </div>
                )}
              </div>
              
              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '12px' }}>
                <button type="button" onClick={() => setModalUploadOpen(false)} style={{ padding: '0 16px', height: '40px', borderRadius: '8px', border: '1px solid #e2e8f0', background: 'white', cursor: 'pointer', fontWeight: 600, color: '#475569' }}>Cancelar</button>
                <button type="submit" disabled={uploading || !selectedFiles} style={{ padding: '0 24px', height: '40px', borderRadius: '8px', border: 'none', background: 'var(--primary)', color: 'white', fontWeight: 700, cursor: 'pointer', opacity: (uploading || !selectedFiles) ? 0.6 : 1, transition: 'all 0.2s' }}>{uploading ? 'Enviando...' : 'Enviar Arquivos'}</button>
              </div>
            </form>
          </div>
        </div>
      )}

      <div className="table-card" style={{ overflow: 'visible' }}>
        {activeTab === 'quarentena' ? (
          <table className="modern-table">
            <thead>
              <tr>
                <th style={{ width: '120px' }}>OS</th>
                <th>Cliente</th>
                <th>Arquivo Problemático</th>
                
                <th style={{ width: '280px', position: 'relative' }}>
                  <div ref={filterRef} style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', userSelect: 'none' }}>
                    <span 
                      onClick={() => {
                        setTempDeselected(deselectedFilters);
                        setIsFilterOpen(!isFilterOpen);
                      }}
                      style={{ color: deselectedFilters.length > 0 ? 'var(--primary)' : 'inherit' }}
                    >
                      Motivo / Diagnóstico
                    </span>
                    <Filter 
                      size={14} 
                      color={deselectedFilters.length > 0 ? "var(--primary)" : "#94a3b8"} 
                      onClick={() => {
                        setTempDeselected(deselectedFilters);
                        setIsFilterOpen(!isFilterOpen);
                      }}
                    />

                    {isFilterOpen && (
                      <div style={{
                        position: 'absolute',
                        top: '100%',
                        left: 0,
                        marginTop: '8px',
                        background: 'white',
                        borderRadius: '8px',
                        boxShadow: '0 10px 25px rgba(0,0,0,0.1)',
                        border: '1px solid var(--border)',
                        width: '280px',
                        zIndex: 100,
                        padding: '12px',
                        display: 'flex',
                        flexDirection: 'column',
                        gap: '8px',
                        cursor: 'default',
                        textTransform: 'none',
                        letterSpacing: 'normal'
                      }}>
                        <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', fontWeight: 700, color: 'var(--text-main)' }}>
                          <input
                            type="checkbox"
                            checked={tempDeselected.length === 0}
                            onChange={(e) => {
                              if (e.target.checked) setTempDeselected([]);
                              else setTempDeselected(motivosErroUnicos);
                            }}
                            style={{ width: '16px', height: '16px', cursor: 'pointer', accentColor: 'var(--primary)' }}
                          />
                          (Selecionar Tudo)
                        </label>

                        <div style={{ height: '1px', background: '#f1f5f9', margin: '4px 0' }}></div>

                        <div style={{ maxHeight: '200px', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '10px', paddingRight: '8px' }}>
                          {motivosErroUnicos.map(motivo => (
                            <label key={motivo} style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', color: 'var(--text-muted)', fontSize: '0.85rem', fontWeight: 500 }}>
                              <input
                                type="checkbox"
                                checked={!tempDeselected.includes(motivo)}
                                onChange={(e) => {
                                  if (e.target.checked) setTempDeselected(tempDeselected.filter(x => x !== motivo));
                                  else setTempDeselected([...tempDeselected, motivo]);
                                }}
                                style={{ width: '16px', height: '16px', cursor: 'pointer', accentColor: 'var(--primary)', flexShrink: 0 }}
                              />
                              {motivo}
                            </label>
                          ))}
                        </div>

                        <div style={{ height: '1px', background: '#f1f5f9', margin: '4px 0' }}></div>

                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', paddingTop: '4px' }}>
                          <button
                            onClick={() => setTempDeselected([])}
                            style={{ background: 'none', border: 'none', color: '#94a3b8', fontWeight: 700, fontSize: '0.75rem', cursor: 'pointer' }}
                          >
                            LIMPAR
                          </button>
                          <button
                            onClick={() => {
                              setDeselectedFilters(tempDeselected);
                              setIsFilterOpen(false);
                            }}
                            style={{ background: '#0284c7', color: 'white', border: 'none', padding: '6px 16px', borderRadius: '6px', fontWeight: 700, fontSize: '0.8rem', cursor: 'pointer' }}
                          >
                            OK
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                </th>

                <th style={{ textAlign: 'right', width: '220px' }}>Ações de Resgate</th>
              </tr>
            </thead>
            <tbody>
              {currentItems.length === 0 ? (
                <tr><td colSpan={5} style={{ textAlign: 'center', padding: '4rem', color: 'var(--text-muted)' }}>Nenhum documento na quarentena. Tudo limpo!</td></tr>
              ) : currentItems.map((doc: any) => (
                <tr key={`quarentena-${doc.id}`} style={{ background: 'white', borderBottom: '1px solid #f1f5f9' }}>
                  <td><span className="os-number">#{doc.os}</span></td>
                  <td><span className="client-name">{doc.empresa || 'Desconhecido'}</span></td>
                  <td><div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.85rem' }}><FileText size={16} /><span title={doc.nome_original}>{doc.nome_original.length > 30 ? doc.nome_original.substring(0, 30) + '...' : doc.nome_original}</span></div></td>
                  <td><div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}><AlertTriangle size={16} color="#ef4444" /><span style={{ fontSize: '0.75rem', fontWeight: 800, color: '#ef4444' }}>{getMotivoExibicao(doc)}</span></div></td>
                  <td style={{ textAlign: 'right' }}>
                    <div style={{ display: 'flex', gap: '8px', justifyContent: 'flex-end' }}>
                      <button onClick={() => window.open(`${api.defaults.baseURL}/api/quarentena/download/${doc.id}`, '_blank')} className="action-btn-outline" style={{ borderColor: '#3b82f6', color: '#3b82f6', background: '#eff6ff' }}><Download size={14} /> Baixar</button>
                      <button onClick={() => { setDocToFix(doc); setModalUploadOpen(true); }} className="action-btn-outline" style={{ background: 'var(--primary)', color: 'white' }}><Upload size={14} /> Enviar Arquivos</button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <table className="modern-table">
            <thead>
              <tr>
                <th style={{ width: '48px' }}></th>
                <th style={{ width: '80px', textAlign: 'center' }}>Validar</th>
                <th style={{ width: '160px', cursor: 'pointer' }} onClick={() => requestSort('os')}>Solicitação {getSortIcon('os')}</th>
                <th style={{ cursor: 'pointer' }} onClick={() => requestSort('nome_empresa')}>Cliente {getSortIcon('nome_empresa')}</th>
                <th style={{ textAlign: 'center', width: '100px' }}>Arquivos</th>
                <th style={{ textAlign: 'center', width: '130px' }}>Download</th>
                <th style={{ textAlign: 'center', width: '130px' }}>Triagem</th>
                <th style={{ textAlign: 'center', width: '130px' }}>Tomados</th>
              </tr>
            </thead>
            <tbody>
              {currentItems.length === 0 ? (
                <tr><td colSpan={8} style={{ textAlign: 'center', padding: '4rem', color: 'var(--text-muted)' }}>Nenhuma solicitação encontrada.</td></tr>
              ) : currentItems.map((grupo: any) => (
                <React.Fragment key={`group-${grupo.os}`}>
                  <tr style={{ background: 'white', borderBottom: expandedOS === grupo.os ? 'none' : '1px solid #f1f5f9' }}>
                    <td style={{ textAlign: 'center' }}><button className="btn-expand" onClick={() => setExpandedOS(expandedOS === grupo.os ? null : grupo.os)}>{expandedOS === grupo.os ? <ChevronUp size={18} /> : <ChevronDown size={18} />}</button></td>
                    <td style={{ textAlign: 'center' }}>
                      <button 
                        onClick={() => toggleValidacao(grupo.os, grupo.verificado)} 
                        className={`check-btn ${grupo.verificado ? 'checked' : ''} ${grupo.status_download === 'ALERTA_HUMANO' ? 'retry-mode' : ''}`}
                        title={grupo.status_download === 'ALERTA_HUMANO' ? "Clique aqui após extrair os arquivos manualmente para reprocessar" : "Validar OS"}
                        style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', width: '100%' }}
                      >
                        {grupo.verificado ? (
                          <CheckCircle size={26} fill="#dcfce7" />
                        ) : grupo.status_download === 'ALERTA_HUMANO' ? (
                          <Circle size={26} color="#f97316" strokeWidth={3} />
                        ) : (
                          <Circle size={26} />
                        )}
                      </button>
                    </td>
                    <td>
                      <div className="os-info"><span className="os-number">#{grupo.os}</span><span className="os-date">{grupo.data_os ? new Date(grupo.data_os).toLocaleDateString('pt-BR') : '--/--/----'}</span></div>
                      {grupo.verificado === 1 && grupo.auditado_por && (
                        <div style={{ marginTop: '8px', display: 'flex', flexDirection: 'column' }}><span style={{ fontSize: '0.7rem', color: '#16a34a', fontWeight: 700 }}><UserCheck size={12} /> {grupo.auditado_por.split(' ')[0]}</span></div>
                      )}
                    </td>
                    <td><div className="client-info"><span className="client-name">{grupo.nome_empresa}</span><span className="client-code">Cód: {grupo.cod_empresa}</span></div></td>
                    <td style={{ textAlign: 'center', fontWeight: '800' }}>{grupo.total_arquivos}</td>
                    
                    {/* === COLUNAS COM PÍLULAS PADRONIZADAS === */}
                    <td style={{ textAlign: 'center' }}>
                      {grupo.qtd_anexos === 0 ? (
                        <span style={getPillStyle('SÓ MENSAGEM')} title={grupo.mensagem}>SÓ MENSAGEM</span>
                      ) : (
                        <span style={getPillStyle(grupo.status_download === 'ALERTA_HUMANO' ? 'AÇÃO MANUAL' : grupo.status_download)}>
                          {grupo.status_download === 'ALERTA_HUMANO' ? 'AÇÃO MANUAL' : grupo.status_download}
                        </span>
                      )}
                    </td>
                    
                    <td style={{ textAlign: 'center' }}>
                      <span style={getPillStyle(grupo.status_triagem_geral)}>
                        {grupo.status_triagem_geral}
                      </span>
                    </td>
                    
                    <td style={{ textAlign: 'center' }}>
                      {grupo.status_tomados_geral === 'CONCLUIDO' ? (
                        <a href={`${api.defaults.baseURL}/api/download/tomados/${grupo.os}`} className="action-btn-outline" style={{ display: 'inline-flex', padding: '4px 10px', fontSize: '0.65rem', minWidth: '100px', justifyContent: 'center' }}>
                          <Download size={12} style={{marginRight: '4px'}}/> Planilhas
                        </a>
                      ) : (
                        <span style={getPillStyle(grupo.status_tomados_geral === 'PROCESSANDO' ? 'Na Fila' : grupo.status_tomados_geral)}>
                          {grupo.status_tomados_geral === 'PROCESSANDO' ? 'Na Fila' : grupo.status_tomados_geral}
                        </span>
                      )}
                    </td>                   
                  </tr>
                  {expandedOS === grupo.os && <tr><td colSpan={8} style={{ padding: 0 }}><SubTable arquivos={grupo.arquivos} /></td></tr>}
                </React.Fragment>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="pagination-container" style={{ marginTop: '1rem' }}>
        <span style={{ fontSize: '0.8rem' }}>Página <strong>{currentPage}</strong> de <strong>{totalPages || 1}</strong></span>
        <div style={{ display: 'flex', gap: '8px' }}>
          <button className="page-btn" onClick={() => setCurrentPage(prev => Math.max(prev - 1, 1))} disabled={currentPage === 1}><ChevronLeft size={16} /> Anterior</button>
          <button className="page-btn" onClick={() => setCurrentPage(prev => Math.min(prev + 1, totalPages))} disabled={currentPage === totalPages || totalPages === 0}>Próxima <ChevronRight size={16} /></button>
        </div>
      </div>
      
      {modalSuccessOpen && (
        <div style={{ position: 'fixed', inset: 0, backgroundColor: 'rgba(15, 23, 42, 0.6)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100, backdropFilter: 'blur(4px)' }}>
          <div style={{ background: 'white', borderRadius: '16px', width: '400px', maxWidth: '90%', padding: '32px', display: 'flex', flexDirection: 'column', alignItems: 'center', textAlign: 'center', boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.1)' }}>
            
            <div style={{ background: '#dcfce7', borderRadius: '50%', padding: '16px', marginBottom: '20px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <CheckCircle size={40} color="#16a34a" />
            </div>
            
            <h3 style={{ margin: '0 0 12px 0', fontSize: '1.25rem', fontWeight: 800, color: '#0f172a' }}>
              Arquivos Enviados!
            </h3>
            
            <p style={{ margin: '0 0 24px 0', color: '#64748b', fontSize: '0.95rem', lineHeight: '1.5' }}>
              A correção foi recebida com sucesso. O robô irá fatiar e processar esses arquivos na próxima rodada.
            </p>
            
            <button 
              onClick={() => setModalSuccessOpen(false)} 
              style={{ background: 'var(--primary)', color: 'white', border: 'none', padding: '12px 32px', borderRadius: '8px', fontWeight: 700, cursor: 'pointer', transition: 'opacity 0.2s', width: '100%' }}
            >
              Entendi
            </button>
            
          </div>
        </div>
      )}
    </div>
  )
}
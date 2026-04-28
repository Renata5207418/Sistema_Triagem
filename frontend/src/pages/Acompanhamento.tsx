import React, { useState, useEffect, useMemo } from 'react'
import axios from 'axios'
import { Download, ChevronDown, ChevronUp, ChevronLeft, ChevronRight, CheckCircle, Circle, FileText, Calendar, UserCheck, AlertTriangle, UploadCloud, X, Upload } from 'lucide-react'
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

export default function Acompanhamento() {
  const [documentosFlat, setDocumentosFlat] = useState<any[]>([])
  const [quarentenaDocs, setQuarentenaDocs] = useState<any[]>([]) // Novo Estado para a Quarentena
  const [expandedOS, setExpandedOS] = useState<number | null>(null)
  
  const [activeTab, setActiveTab] = useState<'pendentes' | 'concluidas' | 'quarentena'>('pendentes')
  const [searchTerm, setSearchTerm] = useState('')
  
  const [mesFiltro, setMesFiltro] = useState(() => {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
  });

  const [currentPage, setCurrentPage] = useState(1)
  const itemsPerPage = 15
  const [sortConfig, setSortConfig] = useState<{ key: string, direction: 'asc' | 'desc' }>({ key: 'os', direction: 'desc' });

  // Estados do Modal de Upload
  const [modalUploadOpen, setModalUploadOpen] = useState(false);
  const [docToFix, setDocToFix] = useState<any>(null);
  const [selectedFiles, setSelectedFiles] = useState<FileList | null>(null);
  const [uploading, setUploading] = useState(false);

  const { user } = useAuth();

  const carregarDados = () => {
    // Carrega a Auditoria normal
    axios.get('http://127.0.0.1:8000/api/triagem/auditoria')
      .then(res => setDocumentosFlat(res.data))
      .catch(err => console.error("API falhou", err))
      
    // Carrega a Quarentena
    axios.get('http://127.0.0.1:8000/api/quarentena/listar')
      .then(res => setQuarentenaDocs(res.data))
      .catch(err => console.error("API Quarentena falhou", err))
  }

  useEffect(() => {
    carregarDados();

    const intervalo = window.setInterval(() => {
      carregarDados();
    }, 15000); // atualiza a cada 15 segundos

    return () => {
      window.clearInterval(intervalo);
    };
  }, []);

  const toggleValidacao = async (osId: number, atualVerificado: number) => {
    if (atualVerificado === 1) {
      try {
        await axios.put(`http://127.0.0.1:8000/api/os/${osId}/desmarcar`);
        carregarDados();
      } catch (err) { alert("Erro ao desmarcar OS."); }
    } else {
      try {
        await axios.put(`http://127.0.0.1:8000/api/os/${osId}/verificar`, { usuario: user?.full_name || 'Sistema' });
        carregarDados();
      } catch (err) { alert("Erro ao validar OS."); }
    }
  }

  // Lógica de Upload do Modal
  const handleUploadCorrecao = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedFiles || selectedFiles.length === 0 || !docToFix) return;

    setUploading(true);
    const formData = new FormData();
    formData.append('id_doc_original', docToFix.id.toString());
    
    Array.from(selectedFiles).forEach(file => {
      formData.append('arquivos', file);
    });

    try {
      await axios.post(`http://127.0.0.1:8000/api/quarentena/upload-correcao/${docToFix.os}`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });
      setModalUploadOpen(false);
      setSelectedFiles(null);
      setDocToFix(null);
      carregarDados(); // Recarrega tudo para atualizar as abas
      alert("Arquivos enviados! O robô irá processá-los na próxima rodada.");
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
        if (statusDeErro.includes(doc.status_triagem)) {
           acc[doc.os].temErroTriagem = true;
        }

        if (doc.categoria_ia === 'nota_servico') {
           if (doc.status_tomados === 'PENDENTE') acc[doc.os].temTomadosPendente = true;
           if (doc.status_tomados === 'PROCESSADO') acc[doc.os].temTomadosProcessado = true;
        }
      }
      return acc
    }, {})

    return Object.values(mapa).map((grupo: any) => {
      let status_tomados = 'N/A';
      if (grupo.temTomadosPendente) status_tomados = 'PROCESSANDO';
      else if (grupo.temTomadosProcessado) status_tomados = 'CONCLUIDO';
      
      let status_triagem = 'SUCESSO';
      if (grupo.qtd_anexos === 0 && grupo.arquivos.length === 0) {
        status_triagem = 'N/A';
      } else if (grupo.arquivos.length === 0) {
        status_triagem = 'PENDENTE';
      } else if (grupo.temErroTriagem) {
        status_triagem = 'ERRO';
      }

      return { ...grupo, status_triagem_geral: status_triagem, status_tomados_geral: status_tomados, total_arquivos: grupo.arquivos.length }
    }) as any[]
  }, [documentosFlat])

  const { filtrados, totalPendentes, totalConcluidas } = useMemo(() => {
    const baseFiltrada = agrupadosPorOS.filter(grupo => {
      const mesMatch = mesFiltro ? grupo.mes_ano === mesFiltro : true;
      const lowerSearch = searchTerm.toLowerCase();
      const textMatch = !searchTerm || String(grupo.os).includes(lowerSearch) || (grupo.nome_empresa && grupo.nome_empresa.toLowerCase().includes(lowerSearch)) || (grupo.cod_empresa && String(grupo.cod_empresa).includes(lowerSearch));
      return mesMatch && textMatch;
    });

    const pendentes = baseFiltrada.filter(g => g.verificado === 0).length;
    const concluidas = baseFiltrada.filter(g => g.verificado === 1).length;

    let filtered = baseFiltrada.filter(grupo => activeTab === 'pendentes' ? grupo.verificado === 0 : grupo.verificado === 1);
    
    filtered.sort((a, b) => {
      if (a[sortConfig.key] < b[sortConfig.key]) return sortConfig.direction === 'asc' ? -1 : 1;
      if (a[sortConfig.key] > b[sortConfig.key]) return sortConfig.direction === 'asc' ? 1 : -1;
      return 0;
    });

    return { filtrados: filtered, totalPendentes: pendentes, totalConcluidas: concluidas };
  }, [agrupadosPorOS, activeTab, searchTerm, mesFiltro, sortConfig]);

  // Filtro da aba Quarentena
  const quarentenaFiltrada = useMemo(() => {
    return quarentenaDocs.filter(doc => {
      const lowerSearch = searchTerm.toLowerCase();
      return !searchTerm || String(doc.os).includes(lowerSearch) || (doc.empresa && doc.empresa.toLowerCase().includes(lowerSearch)) || (doc.nome_original && doc.nome_original.toLowerCase().includes(lowerSearch));
    });
  }, [quarentenaDocs, searchTerm]);

  useEffect(() => { setCurrentPage(1); }, [searchTerm, activeTab, mesFiltro])

  // Lógica de Paginação que serve para as duas tabelas
  const listToPaginate = activeTab === 'quarentena' ? quarentenaFiltrada : filtrados;
  const totalPages = Math.ceil(listToPaginate.length / itemsPerPage);
  const currentItems = listToPaginate.slice((currentPage - 1) * itemsPerPage, currentPage * itemsPerPage);

  const getSortIcon = (colName: string) => {
    if (sortConfig.key !== colName) return null;
    return sortConfig.direction === 'asc' ? <ChevronUp size={14} className="inline ml-1" /> : <ChevronDown size={14} className="inline ml-1" />;
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
          <span style={{ background: activeTab === 'pendentes' ? 'var(--primary)' : '#e2e8f0', color: activeTab === 'pendentes' ? 'white' : '#64748b', padding: '2px 8px', borderRadius: '12px', fontSize: '0.7rem', fontWeight: 700, transition: '0.2s' }}>{totalPendentes}</span>
        </button>
        <button className={`tab-item ${activeTab === 'concluidas' ? 'active' : ''}`} onClick={() => setActiveTab('concluidas')} style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          Validadas / Concluídas
          <span style={{ background: activeTab === 'concluidas' ? '#16a34a' : '#e2e8f0', color: activeTab === 'concluidas' ? 'white' : '#64748b', padding: '2px 8px', borderRadius: '12px', fontSize: '0.7rem', fontWeight: 700, transition: '0.2s' }}>{totalConcluidas}</span>
        </button>
        <button className={`tab-item ${activeTab === 'quarentena' ? 'active' : ''}`} onClick={() => setActiveTab('quarentena')} style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          Revisão (Arquivos com erro)
          <span style={{ background: activeTab === 'quarentena' ? '#ef4444' : '#e2e8f0', color: activeTab === 'quarentena' ? 'white' : '#64748b', padding: '2px 8px', borderRadius: '12px', fontSize: '0.7rem', fontWeight: 700, transition: '0.2s' }}>{quarentenaDocs.length}</span>
        </button>
      </div>

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
        <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
          Mostrando <strong>{listToPaginate.length}</strong> resultados
        </div>
        
        <div style={{ display: 'flex', gap: '12px' }}>
          {activeTab !== 'quarentena' && (
            <div style={{ display: 'flex', alignItems: 'center', background: 'white', padding: '0 12px', borderRadius: '10px', border: '1px solid var(--border)', height: '42px' }}>
              <Calendar size={16} style={{ color: 'var(--primary)', marginRight: '8px' }} />
              <DatePicker selected={new Date(parseInt(mesFiltro.split('-')[0]), parseInt(mesFiltro.split('-')[1]) - 1, 1)} onChange={(date: Date | null) => { if (date) setMesFiltro(`${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`); }} dateFormat="MMMM yyyy" showMonthYearPicker locale="pt-BR" className="bg-transparent border-none font-bold text-sm text-[#3a3a3a] focus:ring-0 cursor-pointer uppercase outline-none w-32" />
            </div>
          )}
          <div style={{ position: 'relative' }}>
            <input type="text" placeholder="Buscar OS ou Empresa..." className="login-input" style={{ width: '280px', height: '42px', paddingLeft: '16px', paddingRight: '16px', fontSize: '0.85rem' }} value={searchTerm} onChange={(e) => setSearchTerm(e.target.value)} />
          </div>
        </div>
      </div>

      {/* ========================================== */}
      {/* MODAL DE UPLOAD DE CORREÇÃO                */}
      {/* ========================================== */}
      {modalUploadOpen && docToFix && (
        <div style={{ position: 'fixed', inset: 0, backgroundColor: 'rgba(15, 23, 42, 0.6)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 50, backdropFilter: 'blur(4px)' }}>
          <div style={{ background: 'white', borderRadius: '16px', width: '500px', maxWidth: '95%', boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.1)', overflow: 'hidden' }}>
            <div style={{ padding: '20px 24px', borderBottom: '1px solid var(--border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <h3 style={{ margin: 0, fontSize: '1.1rem', fontWeight: 800, color: 'var(--text-main)', display: 'flex', alignItems: 'center', gap: '8px' }}>
                <UploadCloud size={20} color="var(--primary)" /> Substituir Documento
              </h3>
              <button onClick={() => {setModalUploadOpen(false); setSelectedFiles(null);}} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)' }}><X size={20} /></button>
            </div>
            <form onSubmit={handleUploadCorrecao} style={{ padding: '24px' }}>
              <div style={{ marginBottom: '16px', fontSize: '0.85rem', color: 'var(--text-muted)' }}>
                Faça o upload dos PDFs separados para a OS <strong>#{docToFix.os}</strong>.<br/> O arquivo problemático será apagado da fila do robô.
              </div>
              
              <div style={{ border: '2px dashed #cbd5e1', borderRadius: '12px', padding: '32px', textAlign: 'center', background: '#f8fafc', marginBottom: '24px' }}>
                 <input type="file" multiple accept=".pdf" onChange={(e) => setSelectedFiles(e.target.files)} style={{ display: 'block', width: '100%', cursor: 'pointer', fontSize: '0.85rem' }} required />
                 <p style={{ fontSize: '0.75rem', color: '#94a3b8', marginTop: '8px' }}>Apenas arquivos PDF.</p>
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '12px' }}>
                <button type="button" onClick={() => setModalUploadOpen(false)} style={{ padding: '0 16px', height: '40px', borderRadius: '8px', border: '1px solid #e2e8f0', background: 'white', fontWeight: 600, cursor: 'pointer' }}>Cancelar</button>
                <button type="submit" disabled={uploading || !selectedFiles} style={{ padding: '0 24px', height: '40px', borderRadius: '8px', border: 'none', background: 'var(--primary)', color: 'white', fontWeight: 700, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '8px', opacity: (uploading || !selectedFiles) ? 0.6 : 1 }}>
                  {uploading ? 'Enviando...' : <><Upload size={16} /> Enviar Arquivos</>}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ========================================== */}
      {/* TABELA DE QUARENTENA (HOSPITAL)            */}
      {/* ========================================== */}
      {activeTab === 'quarentena' ? (
        <div className="table-card">
          <table className="modern-table">
            <thead>
              <tr>
                <th style={{ width: '120px' }}>OS</th>
                <th>Cliente</th>
                <th>Arquivo Problemático</th>
                <th>Motivo / Diagnóstico</th>
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
                  <td>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.85rem' }}>
                      <FileText size={16} style={{ color: '#94a3b8' }} />
                      <span title={doc.nome_original}>{doc.nome_original.length > 30 ? doc.nome_original.substring(0, 30) + '...' : doc.nome_original}</span>
                    </div>
                  </td>
                  <td>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <AlertTriangle size={16} color="#ef4444" />
                      <div style={{ display: 'flex', flexDirection: 'column' }}>
                        <span style={{ fontSize: '0.75rem', fontWeight: 800, color: '#ef4444', textTransform: 'uppercase' }}>{doc.categoria_ia === 'documento_unificado' ? 'Frankenstein Detectado' : doc.motivo_erro || 'Erro Desconhecido'}</span>
                        <span style={{ fontSize: '0.7rem', color: '#94a3b8' }}>Ação humana necessária</span>
                      </div>
                    </div>
                  </td>
                  <td style={{ textAlign: 'right' }}>
                    <div style={{ display: 'flex', gap: '8px', justifyContent: 'flex-end' }}>
                      <button 
                        onClick={() => window.open(`http://127.0.0.1:8000/api/quarentena/download/${doc.id}`, '_blank')}
                        title="Baixar para fatiar"
                        className="action-btn-outline" style={{ borderColor: '#3b82f6', color: '#3b82f6', background: '#eff6ff' }}
                      >
                        <Download size={14} /> Baixar
                      </button>
                      <button 
                        onClick={() => { setDocToFix(doc); setModalUploadOpen(true); }}
                        title="Enviar as partes"
                        className="action-btn-outline" style={{ borderColor: 'var(--primary)', color: 'white', background: 'var(--primary)' }}
                      >
                        <Upload size={14} /> Enviar Fatias
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
      /* ========================================== */
      /* TABELA NORMAL DE AUDITORIA DE OS           */
      /* ========================================== */
        <div className="table-card">
          <table className="modern-table">
            <thead>
              <tr>
                <th style={{ width: '48px' }}></th>
                <th style={{ width: '80px', textAlign: 'center' }}>Validar</th>
                <th style={{ width: '160px', cursor: 'pointer' }} onClick={() => requestSort('os')}>Solicitação {getSortIcon('os')}</th>
                <th style={{ cursor: 'pointer' }} onClick={() => requestSort('nome_empresa')}>Cliente {getSortIcon('nome_empresa')}</th>
                <th style={{ textAlign: 'center', width: '100px', cursor: 'pointer' }} onClick={() => requestSort('total_arquivos')}>Arquivos {getSortIcon('total_arquivos')}</th>
                <th style={{ textAlign: 'center', width: '120px' }}>Download</th>
                <th style={{ textAlign: 'center', width: '120px' }}>Triagem</th>
                <th style={{ textAlign: 'center', width: '140px', cursor: 'pointer' }} onClick={() => requestSort('status_tomados_geral')}>Tomados {getSortIcon('status_tomados_geral')}</th>
              </tr>
            </thead>
            <tbody>
              {currentItems.length === 0 ? (
                <tr><td colSpan={7} style={{ textAlign: 'center', padding: '4rem', color: 'var(--text-muted)' }}>Nenhuma solicitação encontrada.</td></tr>
              ) : currentItems.map((grupo: any) => (
                <React.Fragment key={`group-${grupo.os}`}>
                  <tr style={{ background: 'white', borderBottom: expandedOS === grupo.os ? 'none' : '1px solid #f1f5f9', transition: 'background 0.2s' }}>
                    <td style={{ textAlign: 'center' }}><button className="btn-expand" onClick={() => setExpandedOS(expandedOS === grupo.os ? null : grupo.os)}>{expandedOS === grupo.os ? <ChevronUp size={18} /> : <ChevronDown size={18} />}</button></td>
                    <td style={{ textAlign: 'center' }}><button onClick={() => toggleValidacao(grupo.os, grupo.verificado)} className={`check-btn ${grupo.verificado ? 'checked' : ''}`} style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', width: '100%' }}>{grupo.verificado ? <CheckCircle size={26} fill="#dcfce7" /> : <Circle size={26} />}</button></td>
                    <td>
                      <div className="os-info"><span className="os-number">#{grupo.os}</span><span className="os-date">{grupo.data_os ? new Date(grupo.data_os).toLocaleDateString('pt-BR') : '--/--/----'}</span></div>
                      {grupo.verificado === 1 && grupo.auditado_por && (
                        <div style={{ marginTop: '8px', display: 'flex', flexDirection: 'column', gap: '2px', whiteSpace: 'nowrap' }}><span style={{ display: 'flex', alignItems: 'center', gap: '4px', fontSize: '0.7rem', color: '#16a34a', fontWeight: 700 }}><UserCheck size={12} /> Validado por {grupo.auditado_por.split(' ')[0]}</span><span style={{ fontSize: '0.65rem', color: '#22c55e', marginLeft: '16px', fontWeight: 500 }}>{grupo.data_auditoria ? new Date(grupo.data_auditoria).toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' }) : ''}</span></div>
                      )}
                    </td>
                    <td><div className="client-info"><span className="client-name">{grupo.nome_empresa}</span><span className="client-code">Cód: {grupo.cod_empresa}</span></div></td>
                    <td style={{ textAlign: 'center', fontWeight: '800', color: grupo.total_arquivos === 0 ? '#cbd5e1' : 'var(--text-muted)', fontSize: '0.9rem' }}>{grupo.total_arquivos}</td>
                    <td style={{ textAlign: 'center' }}>
                      {grupo.qtd_anexos === 0 ? <span className="status-pill" style={{ background: '#fff7ed', color: '#c2410c', border: '1px solid #fdba74', fontSize: '0.55rem', padding: '4px 8px', whiteSpace: 'nowrap', display: 'inline-flex', alignItems: 'center', fontWeight: 800, letterSpacing: '0.02em' }} title={grupo.mensagem}> SÓ MENSAGEM</span> : <span className={`status-pill ${grupo.status_download === 'SUCESSO' ? 'sucesso' : 'erro'}`}>{grupo.status_download}</span>}
                    </td>
                    <td style={{ textAlign: 'center' }}>
                      {grupo.status_triagem_geral === 'N/A' ? <span style={{ display: 'inline-flex', padding: '4px 12px', borderRadius: '8px', background: '#f1f5f9', color: '#94a3b8', fontSize: '0.75rem', fontWeight: 700 }}>N/A</span> : <span className={`status-pill ${grupo.status_triagem_geral === 'SUCESSO' ? 'sucesso' : 'erro'}`}>{grupo.status_triagem_geral}</span>}
                    </td>
                    <td style={{ textAlign: 'center' }}>
                      {grupo.status_tomados_geral === 'CONCLUIDO' ? <a href={`http://127.0.0.1:8000/api/download/tomados/${grupo.os}`} title="Baixar planilhas (.zip)" className="action-btn-outline" style={{ textDecoration: 'none' }}><Download size={14} /> Planilhas</a> : grupo.status_tomados_geral === 'PROCESSANDO' ? <span className="status-badge status-pendente">Na Fila</span> : <span style={{ display: 'inline-flex', padding: '4px 12px', borderRadius: '8px', background: '#f1f5f9', color: '#94a3b8', fontSize: '0.75rem', fontWeight: 700 }}>N/A</span>}
                    </td>                  
                  </tr>
                  {expandedOS === grupo.os && <tr key={`child-${grupo.os}`}><td colSpan={8} style={{ padding: 0 }}><SubTable arquivos={grupo.arquivos} /></td></tr>}
                </React.Fragment>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* PAGINAÇÃO GLOBAL */}
      <div className="pagination-container" style={{ marginTop: activeTab === 'quarentena' ? '0' : '-1px' }}>
        <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Página <strong>{currentPage}</strong> de <strong>{totalPages || 1}</strong></span>
        <div style={{ display: 'flex', gap: '8px' }}>
          <button className="page-btn" onClick={() => setCurrentPage(prev => Math.max(prev - 1, 1))} disabled={currentPage === 1}><ChevronLeft size={16} /> Anterior</button>
          <button className="page-btn" onClick={() => setCurrentPage(prev => Math.min(prev + 1, totalPages))} disabled={currentPage === totalPages || totalPages === 0}>Próxima <ChevronRight size={16} /></button>
        </div>
      </div>

    </div>
  )
}
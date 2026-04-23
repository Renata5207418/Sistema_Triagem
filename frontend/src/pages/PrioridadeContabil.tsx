import React, { useState, useEffect, useMemo } from 'react';
import axios from 'axios';
import { Settings, ChevronDown, ChevronUp, Trash2, CheckCircle, Circle, Plus, FolderOpen, Calendar, Power, PowerOff, X, Search, ChevronLeft, ChevronRight, Pencil, Check, Bot } from 'lucide-react';
import DatePicker, { registerLocale } from "react-datepicker";
import "react-datepicker/dist/react-datepicker.css";
import { ptBR } from "date-fns/locale";

registerLocale("pt-BR", ptBR);

/* --- Interfaces ------------------------------------------- */
interface IDocumento {
  id: string;
  nome: string;
  recebido: string;
  liberado_em: string | null;
  isAuto?: boolean; 
}

interface IPasta {
  id?: number;
  apelido: string;
  competencia: string;
  pasta_liberada_em: string | null;
  documentos_json: string;
}

interface IEmpresaConfig {
  codigo?: string; 
  apelido: string;
  tipo: 'VITALICIA' | 'MENSAL';
  ativa: number;
  competencia_unica?: string;
}

/* --- Funções Auxiliares ----------------------------------- */
const getHojeYYYYMMDD = () => {
  const hoje = new Date();
  return `${hoje.getFullYear()}-${String(hoje.getMonth() + 1).padStart(2, '0')}-${String(hoje.getDate()).padStart(2, '0')}`;
};

const formatDateTime = () => {
  const hoje = new Date();
  return `${hoje.getFullYear()}-${String(hoje.getMonth() + 1).padStart(2, '0')}-${String(hoje.getDate()).padStart(2, '0')} ${String(hoje.getHours()).padStart(2, '0')}:${String(hoje.getMinutes()).padStart(2, '0')}:${String(hoje.getSeconds()).padStart(2, '0')}`;
};


/* --- Componentes de Tabela -------------------------------- */
function DocumentoRow({ doc, onChange, onRemove }: { doc: IDocumento, onChange: (d: IDocumento) => void, onRemove: () => void }) {
  
  if (doc.isAuto) {
    return (
      <tr className="sub-table-row" style={{ backgroundColor: '#f8fafc', borderBottom: '1px solid #e2e8f0' }}>
        <td style={{ padding: '8px 16px', fontWeight: 700, color: 'var(--primary)', display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Bot size={18} style={{ color: '#635294' }} /> {doc.nome}
        </td>
        <td style={{ padding: '8px 16px', color: 'var(--text-muted)', fontWeight: 600 }}>
          {doc.recebido.split('-').reverse().join('/')}
        </td>
        <td style={{ padding: '5px 16px', textAlign: 'center' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', justifyContent: 'center' }}>
            {doc.liberado_em ? <CheckCircle size={22} fill="#dcfce7" color="#16a34a" /> : <Circle size={22} color="#cbd5e1" />}
            <span className={`status-pill ${doc.liberado_em ? 'sucesso' : 'erro'}`} style={{ background: doc.liberado_em ? '' : '#fef9c3', color: doc.liberado_em ? '' : '#a16207', fontSize:'0.63rem' }}>
              {doc.liberado_em ? 'Validado na Malha' : 'Pendente na Auditoria'}
            </span>
          </div>
        </td>
        <td style={{ padding: '8px 16px', textAlign: 'center' }}>
          <span style={{ fontSize: '0.65rem', color: '#94a3b8', fontWeight: 800, padding: '4px 8px', background: '#e2e8f0', borderRadius: '6px' }}>AUTOMÁTICO</span>
        </td>
      </tr>
    );
  }

  return (
    <tr className="sub-table-row" style={{ backgroundColor: '#ffffff', borderBottom: '1px solid #f1f5f9' }}>
      <td style={{ padding: '8px 16px' }}>
        <input 
          type="text" 
          className="login-input" 
          style={{ height: '36px', fontSize: '0.8rem', paddingLeft: '12px' }}
          placeholder="Ex: 34379 ou SEM MOVIMENTO" 
          value={doc.nome} 
          onChange={(e) => onChange({...doc, nome: e.target.value})} 
        />
      </td>
      <td style={{ padding: '8px 16px' }}>
        <input 
          type="date" 
          className="login-input"
          style={{ height: '36px', fontSize: '0.8rem', paddingLeft: '12px', width: '140px' }}
          value={doc.recebido} 
          onChange={(e) => onChange({...doc, recebido: e.target.value})} 
        />
      </td>
      <td style={{ padding: '8px 16px', textAlign: 'center' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', justifyContent: 'center' }}>
          <button 
            className={`check-btn ${doc.liberado_em ? 'checked' : ''}`}
            onClick={() => onChange({...doc, liberado_em: doc.liberado_em ? null : formatDateTime()})}
            style={{ display: 'flex', alignItems: 'center', justifyContent: 'center' }}
          >
            {doc.liberado_em ? <CheckCircle size={22} fill="#dcfce7" color="#16a34a" /> : <Circle size={22} color="#cbd5e1" />}
          </button>
          <span className={`status-pill ${doc.liberado_em ? 'sucesso' : 'erro'}`} style={{ background: doc.liberado_em ? '' : '#fef9c3', color: doc.liberado_em ? '' : '#a16207' }}>
            {doc.liberado_em ? 'Concluído' : 'Pendente'}
          </span>
        </div>
      </td>
      <td style={{ padding: '8px 16px', textAlign: 'center' }}>
        <button onClick={onRemove} style={{ color: '#ef4444', background: 'none', border: 'none', cursor: 'pointer', padding: '4px', borderRadius: '4px' }}>
          <Trash2 size={18} />
        </button>
      </td>
    </tr>
  );
}

function CompetenciaRow({ pasta, onUpdate }: { pasta: IPasta, onUpdate: (p: IPasta) => void }) {
  const [open, setOpen] = useState(false);
  let docs: IDocumento[] = [];
  try { docs = JSON.parse(pasta.documentos_json || "[]"); } catch(e) {}

  const saveDocs = (newDocs: IDocumento[]) => {
    onUpdate({ ...pasta, documentos_json: JSON.stringify(newDocs) });
  };

  const addDoc = () => {
    const newDoc: IDocumento = { id: Date.now().toString(), nome: '', recebido: getHojeYYYYMMDD(), liberado_em: null };
    saveDocs([...docs, newDoc]);
    setOpen(true);
  };

  // Ordena a lista: Automáticos (Robô) ficam sempre por primeiro
  const sortedDocs = [...docs].sort((a, b) => {
    if (a.isAuto && !b.isAuto) return -1;
    if (!a.isAuto && b.isAuto) return 1;
    return 0;
  });

  return (
    <React.Fragment>
      <tr style={{ background: pasta.pasta_liberada_em ? '#f4fbf7' : '#fdfdfd', borderBottom: '1px solid #e2e8f0' }}>
        <td style={{ padding: '12px 16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
          <button className="btn-expand" onClick={() => setOpen(!open)}>
            {open ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
          </button>
          <FolderOpen size={16} color="#64748b" />
          <span style={{ fontWeight: 700, color: 'var(--text-main)', fontSize: '0.85rem' }}>
            Competência: {pasta.competencia}
          </span>
        </td>
        <td style={{ padding: '12px 16px', color: 'var(--text-muted)', fontSize: '0.85rem', fontWeight: 600 }}>
          {docs.length} solicitação(ões)
        </td>
        <td style={{ padding: '12px 16px' }}>
          <span className="status-badge" style={{ 
            background: pasta.pasta_liberada_em ? '#dcfce7' : '#fef08a', 
            color: pasta.pasta_liberada_em ? '#15803d' : '#854d0e',
            border: 'none'
          }}>
            {pasta.pasta_liberada_em ? 'Fechada' : 'Em Andamento'}
          </span>
        </td>
        <td style={{ padding: '12px 16px', textAlign: 'right' }}>
           <button 
            onClick={() => onUpdate({...pasta, pasta_liberada_em: pasta.pasta_liberada_em ? null : formatDateTime()})}
            className="action-btn-outline"
            style={{ borderColor: pasta.pasta_liberada_em ? '#22c55e' : '#e2e8f0', color: pasta.pasta_liberada_em ? '#22c55e' : '#64748b' }}
          >
            <CheckCircle size={14} /> {pasta.pasta_liberada_em ? 'Reabrir' : 'Concluir Mês'}
          </button>
        </td>
      </tr>

      {open && (
        <tr>
          <td colSpan={4} style={{ padding: 0 }}>
            <div style={{ padding: '16px 24px 24px 64px', background: '#f8fafc', borderBottom: '1px solid var(--border)' }}>
              <div style={{ borderLeft: '2px solid var(--border)', paddingLeft: '24px' }}>
                <table className="sub-table" style={{ width: '100%', background: 'white', borderRadius: '8px', overflow: 'hidden', border: '1px solid #e2e8f0' }}>
                  <thead style={{ background: '#f1f5f9' }}>
                    <tr>
                      <th style={{ width: '35%' }}>Descrição da Tarefa</th>
                      <th style={{ width: '25%' }}>Data de Recebimento</th>
                      <th style={{ width: '25%', textAlign: 'center' }}>Status</th>
                      <th style={{ width: '15%', textAlign: 'center' }}>Ação</th>
                    </tr>
                  </thead>
                  <tbody>
                    {/* Renderiza a lista já ordenada */}
                    {sortedDocs.map(doc => (
                      <DocumentoRow key={doc.id} doc={doc}
                        onChange={(updated) => saveDocs(docs.map(d => d.id === updated.id ? updated : d))}
                        onRemove={() => saveDocs(docs.filter(d => d.id !== doc.id))}
                      />
                    ))}
                    {sortedDocs.length === 0 && (
                      <tr>
                        <td colSpan={4} style={{ textAlign: 'center', padding: '24px', color: '#94a3b8', fontStyle: 'italic', fontSize: '0.8rem' }}>
                          Nenhuma tarefa inserida nesta competência.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
                <button 
                  onClick={addDoc} 
                  style={{ display: 'flex', alignItems: 'center', gap: '6px', marginTop: '12px', padding: '6px 12px', background: 'white', border: '1px dashed #cbd5e1', borderRadius: '6px', color: '#594F7A', fontSize: '0.8rem', fontWeight: 700, cursor: 'pointer' }}
                >
                  <Plus size={14} /> Inserir Manual
                </button>
              </div>
            </div>
          </td>
        </tr>
      )}
    </React.Fragment>
  );
}

function EmpresaRow({ apelido, pastas, onUpdatePasta, onAddPasta }: { apelido: string, pastas: IPasta[], onUpdatePasta: (p: IPasta) => void, onAddPasta: () => void }) {
  const [open, setOpen] = useState(false);
  
  let codigoVisual = "";
  let nomeVisual = apelido;
  
  if (apelido.includes('-')) {
      const partes = apelido.split('-');
      codigoVisual = partes[0].trim();
      nomeVisual = partes.slice(1).join('-').trim();
  }

  return (
    <React.Fragment>
      <tr style={{ background: 'white', borderBottom: open ? 'none' : '1px solid #f1f5f9' }}>
        <td style={{ textAlign: 'center', width: '60px' }}>
          <button className="btn-expand" onClick={() => setOpen(!open)}>
            {open ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
          </button>
        </td>
        <td>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              {codigoVisual && <span style={{ fontWeight: 800, color: '#64748b', fontSize: '0.8rem' }}>{codigoVisual}</span>}
              <span style={{ fontWeight: 700, color: 'var(--primary)', fontSize: '0.95rem' }}>{nomeVisual}</span>
            </div>
        </td>
        <td style={{ textAlign: 'right' }}>
          {pastas.length === 0 ? (
             <button
               onClick={onAddPasta}
               style={{ background: '#797292', color: 'white', border: 'none', height: '32px', padding: '0 14px', borderRadius: '8px', fontWeight: 800, fontSize: '0.75rem', cursor: 'pointer', display: 'inline-flex', alignItems: 'center', gap: '6px' }}
             >
               <Plus size={14} /> CRIAR {pastas.length > 0 ? pastas[0].competencia : ''}
             </button>
          ) : (
             <span className={`status-badge ${pastas[0].pasta_liberada_em ? 'status-ok' : 'status-pendente'}`}>
                {pastas[0].pasta_liberada_em ? 'CONCLUÍDO' : 'EM ANDAMENTO'}
             </span>
          )}
        </td>
      </tr>
      
      {open && (
        <tr>
          <td colSpan={3} style={{ padding: 0 }}>
             <div style={{ padding: '16px 24px 24px 64px', background: '#f8fafc', borderBottom: '1px solid var(--border)' }}>
              <table className="sub-table" style={{ width: '100%', background: 'white', border: '1px solid #e2e8f0', borderRadius: '8px', overflow: 'hidden' }}>
                <tbody>
                  {pastas.map((pasta, i) => (
                    <CompetenciaRow key={i} pasta={pasta} onUpdate={onUpdatePasta} />
                  ))}
                  {pastas.length === 0 && (
                    <tr>
                      <td colSpan={4} style={{ textAlign: 'center', padding: '32px', color: '#94a3b8', fontStyle: 'italic', fontSize: '0.85rem' }}>
                        Nenhuma competência registrada. Clique no botão de criar para começar.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </td>
        </tr>
      )}
    </React.Fragment>
  );
}

export default function PrioridadeContabilPage() {
  const [mesFiltro, setMesFiltro] = useState(() => {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
  });

  const [empresas, setEmpresas] = useState<IEmpresaConfig[]>([]);
  const [pastas, setPastas] = useState<IPasta[]>([]);
  const [modalOpen, setModalOpen] = useState(false);
  const [loading, setLoading] = useState(true);

  const [searchTerm, setSearchTerm] = useState('');
  const [currentPage, setCurrentPage] = useState(1);
  const itemsPerPage = 10;

  const [todasConfigs, setTodasConfigs] = useState<IEmpresaConfig[]>([]);
  const [novoCodigo, setNovoCodigo] = useState('');
  const [novoApelido, setNovoApelido] = useState('');
  const [novoTipo, setNovoTipo] = useState<'VITALICIA' | 'MENSAL'>('VITALICIA');
  const [searchModal, setSearchModal] = useState(''); 
  const [editingApelido, setEditingApelido] = useState<string | null>(null);
  const [editTextInput, setEditTextInput] = useState('');

  const carregarDados = async () => {
    setLoading(true);
    try {
      const [resEmpresas, resFech] = await Promise.all([
        axios.get(`http://127.0.0.1:8000/api/prioridades?month=${mesFiltro}`),
        axios.get(`http://127.0.0.1:8000/api/fechamentos`)
      ]);
      setEmpresas(resEmpresas.data);
      setPastas(resFech.data);
    } catch (error) { console.error(error); } 
    finally { setLoading(false); }
  };

  const carregarConfigsModal = async () => {
    try { const res = await axios.get('http://127.0.0.1:8000/api/prioridades/config'); setTodasConfigs(res.data); } 
    catch (error) { console.error(error); }
  };

  useEffect(() => { document.title = 'Prioridade Contábil'; carregarDados(); }, [mesFiltro]);
  useEffect(() => { if (modalOpen) { carregarConfigsModal(); setSearchModal(''); } }, [modalOpen]);
  useEffect(() => { setCurrentPage(1); }, [searchTerm]); 

  // --- BUSCA AUTOMÁTICA DA EMPRESA ---
  const buscarEmpresaNaDominio = async () => {
    if (!novoCodigo.trim()) return; 
    
    try {
      const res = await axios.get(`http://127.0.0.1:8000/api/dominio/empresa/${novoCodigo.trim()}`);
      console.log("Retorno da API Domínio:", res.data);
      
      if (res.data && res.data.apelido !== undefined) {
        setNovoApelido(res.data.apelido); 
      }
    } catch (err) {
      console.warn("Empresa não encontrada na Domínio com este código.");
    }
  };

  // --- BOTÃO ADICIONAR INTELIGENTE ---
  const handleAddEmpresa = async () => {
    let apelidoFinal = novoApelido.trim();

    if (novoCodigo.trim() && !apelidoFinal) {
       try {
          const res = await axios.get(`http://127.0.0.1:8000/api/dominio/empresa/${novoCodigo.trim()}`);
          if (res.data && res.data.apelido) {
             apelidoFinal = res.data.apelido;
             setNovoApelido(apelidoFinal); 
          }
       } catch (e) {
          console.warn("Busca automática no botão falhou.");
       }
    }

    if (!novoCodigo.trim() || !apelidoFinal) {
      alert("Por favor, preencha o Código e aguarde o Nome da empresa carregar."); 
      return; 
    }

    try {
      await axios.post('http://127.0.0.1:8000/api/prioridades/config', { 
        codigo: novoCodigo.trim(), 
        apelido: apelidoFinal.toUpperCase(),     
        tipo: novoTipo, 
        competencia: novoTipo === 'MENSAL' ? mesFiltro : null 
      });
      
      setNovoCodigo('');
      setNovoApelido(''); 
      carregarConfigsModal(); 
      carregarDados();
    } catch (err) { 
      console.error("Erro ao cadastrar empresa:", err); 
    }
  };

  const handleToggleAtiva = async (apelido: string) => {
    try { await axios.put(`http://127.0.0.1:8000/api/prioridades/config/${encodeURIComponent(apelido)}/toggle`); carregarConfigsModal(); carregarDados(); } 
    catch (err) { console.error(err); }
  };

  const handleDeleteEmpresa = async (apelido: string) => {
    if (!window.confirm(`Tem certeza que deseja excluir ${apelido}? O histórico será mantido.`)) return;
    try { await axios.delete(`http://127.0.0.1:8000/api/prioridades/config/${encodeURIComponent(apelido)}`); carregarConfigsModal(); carregarDados(); } 
    catch (err) { console.error(err); }
  };

  const handleRenameEmpresa = async (oldApelido: string) => {
    if (!editTextInput.trim() || editTextInput === oldApelido) { setEditingApelido(null); return; }
    try {
        await axios.put(`http://127.0.0.1:8000/api/prioridades/config/${encodeURIComponent(oldApelido)}/renomear`, { novo_apelido: editTextInput });
        setEditingApelido(null);
        carregarConfigsModal();
        carregarDados();
    } catch (err) { alert("Erro ao renomear."); }
  }

  const handleUpdatePasta = async (updatedPasta: IPasta) => {
    try {
      await axios.post('http://127.0.0.1:8000/api/fechamentos', updatedPasta);
      carregarDados();
    } catch (err) { console.error(err); }
  };

  const empresasFiltradas = useMemo(() => {
    const temRobo = (apelido: string) => {
      const pasta = pastas.find(p => p.apelido === apelido && p.competencia === mesFiltro);
      if (!pasta) return false;
      try {
        const docs = JSON.parse(pasta.documentos_json || "[]");
        return docs.some((d: any) => d.isAuto);
      } catch {
        return false;
      }
    };

    return empresas
      .filter(emp => 
        emp.apelido.toLowerCase().includes(searchTerm.toLowerCase()) || 
        (emp.codigo && emp.codigo.includes(searchTerm))
      )
      .sort((a, b) => {
        const aRobo = temRobo(a.apelido);
        const bRobo = temRobo(b.apelido);

        if (aRobo && !bRobo) return -1; 
        if (!aRobo && bRobo) return 1;  

        return a.apelido.localeCompare(b.apelido);
      });
  }, [empresas, pastas, searchTerm, mesFiltro]);

  const totalPages = Math.ceil(empresasFiltradas.length / itemsPerPage);
  const currentItems = empresasFiltradas.slice((currentPage - 1) * itemsPerPage, currentPage * itemsPerPage);

  const configsModalFiltradas = useMemo(() => {
    return todasConfigs.filter(cfg => cfg.apelido.toLowerCase().includes(searchModal.toLowerCase()) || (cfg.codigo && cfg.codigo.includes(searchModal)));
  }, [todasConfigs, searchModal]);

  return (
    <div className="page-container">
      <div className="page-header-row">
        <div>
          <h1 className="page-title">Fechamento Contábil</h1>
          <p className="page-subtitle">Acompanhe as prioridades e controle as entregas por empresa.</p>
        </div>
        <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
          <div style={{ display: 'flex', alignItems: 'center', background: 'white', padding: '0 12px', borderRadius: '10px', border: '1px solid var(--border)', height: '42px' }}>
            <Calendar size={16} style={{ color: 'var(--primary)', marginRight: '8px' }} />
            <DatePicker selected={new Date(parseInt(mesFiltro.split('-')[0]), parseInt(mesFiltro.split('-')[1]) - 1)} onChange={(d: Date | null) => { if (d) setMesFiltro(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`); }} dateFormat="MMMM yyyy" showMonthYearPicker locale="pt-BR" className="bg-transparent border-none font-bold text-sm text-[#3a3a3a] focus:ring-0 cursor-pointer uppercase outline-none w-32" />
          </div>
          <button className="action-btn-outline" onClick={() => setModalOpen(true)} style={{ borderColor: 'var(--primary)', color: 'var(--primary)', background: 'var(--primary-light)' }}>
            <Settings size={16} /> Gerenciar Carteira
          </button>
        </div>
      </div>

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
        <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
          Mostrando <strong>{empresasFiltradas.length}</strong> empresas ativas
        </div>
        <div style={{ position: 'relative' }}>
          <Search size={16} style={{ position: 'absolute', left: '12px', top: '13px', color: '#94a3b8' }} />
          <input type="text" placeholder="Buscar empresa..." className="login-input" style={{ width: '280px', height: '42px', paddingLeft: '36px', paddingRight: '16px', fontSize: '0.85rem' }} value={searchTerm} onChange={(e) => setSearchTerm(e.target.value)} />
        </div>
      </div>

      {modalOpen && (
        <div style={{ position: 'fixed', inset: 0, backgroundColor: 'rgba(15, 23, 42, 0.6)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 50, backdropFilter: 'blur(4px)' }}>
          <div style={{ background: 'white', borderRadius: '16px', width: '650px', maxWidth: '95%', boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.1)', overflow: 'hidden', display: 'flex', flexDirection: 'column', maxHeight: '90vh' }}>
            <div style={{ padding: '20px 24px', borderBottom: '1px solid var(--border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <h3 style={{ margin: 0, fontSize: '1.1rem', fontWeight: 800, color: 'var(--text-main)' }}>Configurar Empresas da Carteira</h3>
              <button onClick={() => setModalOpen(false)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)' }}><X size={20} /></button>
            </div>
            
            <div style={{ padding: '24px', overflowY: 'auto' }}>
              <div style={{ background: '#f8fafc', padding: '16px', borderRadius: '12px', marginBottom: '24px', border: '1px solid var(--border)' }}>
                <p style={{ fontSize: '0.7rem', fontWeight: 800, color: '#64748b', marginBottom: '10px', textTransform: 'uppercase' }}>Cadastrar Nova Empresa</p>
                
                <div style={{ display: 'flex', gap: '8px', alignItems: 'center', width: '100%', flexWrap: 'nowrap' }}>
                  <input 
                    type="text" 
                    className="standard-input" 
                    placeholder="Cód" 
                    value={novoCodigo} 
                    onChange={(e) => setNovoCodigo(e.target.value)} 
                    onBlur={buscarEmpresaNaDominio} 
                    onKeyDown={(e) => e.key === 'Enter' && buscarEmpresaNaDominio()} 
                    style={{ minWidth: '60px', maxWidth: '60px', height: '40px', textAlign: 'center', padding: '0', flexShrink: 0 }} 
                  />
                  <input 
                    type="text" 
                    className="standard-input"
                    placeholder="Nome da Empresa..." 
                    value={novoApelido} 
                    onChange={(e) => setNovoApelido(e.target.value)} 
                    onKeyDown={(e) => e.key === 'Enter' && handleAddEmpresa()} 
                    style={{ flex: 1, minWidth: '120px', height: '40px', paddingLeft: '12px' }} 
                  />
                  <select 
                    value={novoTipo} 
                    onChange={e => setNovoTipo(e.target.value as any)} 
                    style={{ width: '115px', height: '40px', padding: '0 8px', borderRadius: '8px', border: '1px solid #cbd5e1', background: 'white', color: '#334155', fontWeight: 600, fontSize: '0.8rem', outline: 'none', flexShrink: 0 }}
                  >
                    <option value="VITALICIA">Recorrente</option>
                    <option value="MENSAL">Só este mês</option>
                  </select>
                  <button 
                    onClick={handleAddEmpresa} 
                    style={{ height: '40px', background: 'var(--primary)', color: 'white', border: 'none', padding: '0 16px', borderRadius: '8px', fontWeight: 700, fontSize: '0.85rem', cursor: 'pointer', whiteSpace: 'nowrap', flexShrink: 0 }}
                  >
                    Adicionar
                  </button>
                </div>
              </div>
              
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                 <p style={{ fontSize: '0.7rem', fontWeight: 800, color: '#64748b', margin: 0, textTransform: 'uppercase' }}>Empresas Cadastradas</p>
                 <div style={{ position: 'relative' }}>
                    <Search size={14} style={{ position: 'absolute', left: '10px', top: '10px', color: '#94a3b8' }} />
                    <input type="text" placeholder="Buscar..." className="login-input" style={{ width: '200px', height: '34px', paddingLeft: '32px', fontSize: '0.8rem' }} value={searchModal} onChange={(e) => setSearchModal(e.target.value)} />
                 </div>
              </div>

              <div style={{ border: '1px solid var(--border)', borderRadius: '12px', overflow: 'hidden' }}>
                {configsModalFiltradas.length === 0 ? (
                  <p style={{ textAlign: 'center', padding: '2rem', color: 'var(--text-muted)', fontSize: '0.85rem', margin: 0 }}>Nenhuma empresa encontrada.</p>
                ) : (
                  <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
                    {configsModalFiltradas.map((cfg) => (
                      <li key={cfg.apelido} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '12px 16px', borderBottom: '1px solid #f1f5f9', background: cfg.ativa ? 'white' : '#f8fafc', opacity: cfg.ativa ? 1 : 0.6 }}>
                        
                        {editingApelido === cfg.apelido ? (
                            <div style={{ display: 'flex', gap: '8px', flex: 1, marginRight: '16px' }}>
                                <input autoFocus className="login-input" style={{ height: '30px', flex: 1 }} value={editTextInput} onChange={e => setEditTextInput(e.target.value)} onKeyDown={e => e.key === 'Enter' && handleRenameEmpresa(cfg.apelido)} />
                                <button onClick={() => handleRenameEmpresa(cfg.apelido)} style={{ background: '#10b981', color: 'white', border: 'none', borderRadius: '6px', padding: '0 10px', cursor: 'pointer' }}><Check size={16} /></button>
                                <button onClick={() => setEditingApelido(null)} style={{ background: '#f1f5f9', color: '#64748b', border: 'none', borderRadius: '6px', padding: '0 10px', cursor: 'pointer' }}><X size={16} /></button>
                            </div>
                        ) : (
                            <div style={{ display: 'flex', alignItems: 'center' }}>
                                {cfg.codigo && <span style={{ fontWeight: 800, color: '#64748b', fontSize: '0.8rem', marginRight: '8px' }}>{cfg.codigo}</span>}
                                <span style={{ fontWeight: 700, color: 'var(--text-main)', fontSize: '0.9rem' }}>{cfg.apelido}</span>
                                <span className={`status-badge ${cfg.tipo === 'VITALICIA' ? 'status-ok' : 'status-pendente'}`} style={{ marginLeft: '10px', fontSize: '0.6rem' }}>{cfg.tipo === 'VITALICIA' ? 'Recorrente' : `Mensal (${cfg.competencia_unica})`}</span>
                            </div>
                        )}

                        {!editingApelido && (
                            <div style={{ display: 'flex', gap: '16px' }}>
                                <button onClick={() => { setEditingApelido(cfg.apelido); setEditTextInput(cfg.apelido); }} style={{ background: 'none', border: 'none', color: '#3b82f6', cursor: 'pointer' }} title="Editar Nome"><Pencil size={16} /></button>
                                <button onClick={() => handleToggleAtiva(cfg.apelido)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: cfg.ativa ? '#10b981' : '#94a3b8' }} title={cfg.ativa ? "Desativar" : "Ativar"}>{cfg.ativa ? <Power size={18} /> : <PowerOff size={18} />}</button>
                                <button onClick={() => handleDeleteEmpresa(cfg.apelido)} style={{ background: 'none', border: 'none', color: '#ef4444', cursor: 'pointer' }} title="Excluir"><Trash2 size={16} /></button>
                            </div>
                        )}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      <div className="table-card">
        <table className="modern-table">
          <thead>
            <tr><th style={{ width: '60px' }}></th><th>Empresa</th><th style={{ textAlign: 'right', paddingRight: '24px' }}>Status Geral</th></tr>
          </thead>
          <tbody>
            {loading && empresas.length === 0 ? (
              <tr><td colSpan={3} style={{ textAlign: 'center', padding: '4rem', color: 'var(--text-muted)' }}>Carregando dados...</td></tr>
            ) : currentItems.length === 0 ? (
              <tr><td colSpan={3} style={{ textAlign: 'center', padding: '4rem', color: 'var(--text-muted)' }}>Nenhuma empresa encontrada.</td></tr>
            ) : (
              currentItems.map((emp) => {
                const pastasDaEmpresa = pastas.filter(p => p.apelido === emp.apelido && p.competencia === mesFiltro);
                return (
                  <EmpresaRow
                    key={emp.apelido}
                    apelido={emp.apelido}
                    pastas={pastasDaEmpresa}
                    onUpdatePasta={handleUpdatePasta}
                    onAddPasta={() => handleUpdatePasta({ apelido: emp.apelido, competencia: mesFiltro, pasta_liberada_em: null, documentos_json: "[]" })}
                  />
                );
              })
            )}
          </tbody>
        </table>
        
        {totalPages > 0 && (
          <div className="pagination-container">
            <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
              Página <strong>{currentPage}</strong> de <strong>{totalPages}</strong>
            </span>
            <div style={{ display: 'flex', gap: '8px' }}>
              <button className="page-btn" onClick={() => setCurrentPage(prev => Math.max(prev - 1, 1))} disabled={currentPage === 1}><ChevronLeft size={16} /> Anterior</button>
              <button className="page-btn" onClick={() => setCurrentPage(prev => Math.min(prev + 1, totalPages))} disabled={currentPage === totalPages}>Próxima <ChevronRight size={16} /></button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
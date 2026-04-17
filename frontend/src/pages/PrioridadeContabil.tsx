import React, { useState, useEffect } from 'react';
import { Settings, ChevronDown, ChevronUp, Trash2, CheckCircle, Circle, Plus, FolderOpen, FileText } from 'lucide-react';

/* --- Interfaces ------------------------------------------- */
interface IDocumento {
  id: string;
  nome: string;
  recebido: string;
  liberado_em: string | null;
}

interface IPasta {
  id?: number;
  apelido: string;
  competencia: string;
  pasta_liberada_em: string | null;
  documentos_json: string;
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

const formataCompetencia = (val: string) => {
  let v = val.replace(/\D/g, '');
  if (v.length > 2) v = v.substring(0, 2) + '/' + v.substring(2, 6);
  return v.substring(0, 7);
};

/* --- Componentes de Tabela -------------------------------- */
function DocumentoRow({ doc, onChange, onRemove }: { doc: IDocumento, onChange: (d: IDocumento) => void, onRemove: () => void }) {
  return (
    <tr className="sub-table-row" style={{ backgroundColor: '#ffffff', borderBottom: '1px solid #f1f5f9' }}>
      <td style={{ padding: '8px 16px' }}>
        <input 
          type="text" 
          className="login-input" 
          style={{ height: '36px', fontSize: '0.8rem', paddingLeft: '12px' }}
          placeholder="Número da Solicitação" 
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
        <button onClick={onRemove} style={{ color: '#ef4444', background: 'none', border: 'none', cursor: 'pointer', padding: '4px', borderRadius: '4px' }} className="hover:bg-red-50 transition-colors">
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
            <CheckCircle size={14} /> {pasta.pasta_liberada_em ? 'Reabrir' : 'Concluir'}
          </button>
        </td>
      </tr>

      {/* Subtabela de Documentos (Expandida) */}
      {open && (
        <tr>
          <td colSpan={4} style={{ padding: 0 }}>
            <div style={{ padding: '16px 24px 24px 64px', background: '#f8fafc', borderBottom: '1px solid var(--border)' }}>
              <div style={{ borderLeft: '2px solid var(--border)', paddingLeft: '24px' }}>
                <h4 style={{ fontSize: '0.8rem', fontWeight: 800, color: '#334155', textTransform: 'uppercase', marginBottom: '12px' }}>
                  Tarefas / Solicitações ({pasta.competencia})
                </h4>
                
                <table className="sub-table" style={{ width: '100%', background: 'white', borderRadius: '8px', overflow: 'hidden', border: '1px solid #e2e8f0' }}>
                  <thead style={{ background: '#f1f5f9' }}>
                    <tr>
                      <th style={{ width: '35%' }}>Identificação da Solicitação</th>
                      <th style={{ width: '25%' }}>Data de Recebimento</th>
                      <th style={{ width: '25%', textAlign: 'center' }}>Validação</th>
                      <th style={{ width: '15%', textAlign: 'center' }}>Excluir</th>
                    </tr>
                  </thead>
                  <tbody>
                    {docs.map(doc => (
                      <DocumentoRow key={doc.id} doc={doc}
                        onChange={(updated) => saveDocs(docs.map(d => d.id === updated.id ? updated : d))}
                        onRemove={() => saveDocs(docs.filter(d => d.id !== doc.id))}
                      />
                    ))}
                    {docs.length === 0 && (
                      <tr>
                        <td colSpan={4} style={{ textAlign: 'center', padding: '24px', color: '#94a3b8', fontStyle: 'italic', fontSize: '0.8rem' }}>
                          Nenhuma solicitação inserida nesta competência.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>

                <button 
                  onClick={addDoc} 
                  style={{ display: 'flex', alignItems: 'center', gap: '6px', marginTop: '12px', padding: '6px 12px', background: 'white', border: '1px dashed #cbd5e1', borderRadius: '6px', color: '#6366f1', fontSize: '0.8rem', fontWeight: 700, cursor: 'pointer' }}
                  className="hover:bg-indigo-50 transition-colors"
                >
                  <Plus size={14} /> Inserir Tarefa
                </button>
              </div>
            </div>
          </td>
        </tr>
      )}
    </React.Fragment>
  );
}

function EmpresaRow({ apelido, pastas, onUpdatePasta, onAddPasta }: { apelido: string, pastas: IPasta[], onUpdatePasta: (p: IPasta) => void, onAddPasta: (comp: string) => void }) {
  const [open, setOpen] = useState(false);
  const [novaComp, setNovaComp] = useState('');

  const handleAdd = () => {
    if(novaComp.length === 7) { onAddPasta(novaComp); setNovaComp(''); setOpen(true); }
  };

  return (
    <React.Fragment>
      <tr style={{ background: 'white', borderBottom: open ? 'none' : '1px solid #f1f5f9' }}>
        <td style={{ textAlign: 'center', width: '60px' }}>
          <button className="btn-expand" onClick={() => setOpen(!open)}>
            {open ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
          </button>
        </td>
        <td style={{ fontWeight: 800, color: 'var(--primary)', fontSize: '0.95rem' }}>
          {apelido}
        </td>
        <td style={{ textAlign: 'right' }}>
          <div style={{ display: 'inline-flex', gap: '8px', alignItems: 'center', background: '#f8fafc', padding: '6px', borderRadius: '12px', border: '1px solid #e2e8f0' }}>
            <input
              type="text"
              className="login-input"
              placeholder="MM/YYYY"
              value={novaComp}
              onChange={(e) => setNovaComp(formataCompetencia(e.target.value))}
              maxLength={7}
              style={{ width: '120px', height: '34px', textAlign: 'center', fontWeight: 700, paddingLeft: '12px', paddingRight: '12px' }}
            />
            <button
              onClick={handleAdd}
              style={{ background: 'var(--primary)', color: 'white', border: 'none', height: '34px', padding: '0 16px', borderRadius: '8px', fontWeight: 800, fontSize: '0.75rem', cursor: 'pointer', transition: '0.2s' }}
              className="hover:opacity-90"
            >
              CRIAR
            </button>
          </div>
        </td>
      </tr>
      
      {/* Subtabela de Pastas (Expandida) */}
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
                        Nenhuma competência registrada para esta empresa. Crie uma acima para iniciar.
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
  const [prioridades, setPrioridades] = useState<string[]>([]);
  const [pastas, setPastas] = useState<IPasta[]>([]);
  const [modalOpen, setModalOpen] = useState(false);
  const [novoApelido, setNovoApelido] = useState('');
  const [loading, setLoading] = useState(true);

  const carregarDados = async () => {
    setLoading(true);
    try {
      // APONTANDO PARA AS NOVAS ROTAS
      const resPrio = await fetch('http://127.0.0.1:8000/api/prioridades');
      const listaPrioridades: string[] = await resPrio.json();
      setPrioridades(listaPrioridades);

      const resFech = await fetch('http://127.0.0.1:8000/api/fechamentos');
      const listaPastas: IPasta[] = await resFech.json();
      setPastas(listaPastas);
    } catch (error) {
      console.error("Erro ao carregar dados", error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    document.title = 'Prioridade Contábil';
    carregarDados();
  }, []);

  const salvarPrioridades = (novaLista: string[]) => {
    setPrioridades(novaLista);
    fetch('http://127.0.0.1:8000/api/prioridades', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(novaLista)
    }).catch(err => console.error("Erro ao salvar prioridades:", err));
  };

  const handleAddPrioridade = () => {
    if (novoApelido.trim() && !prioridades.includes(novoApelido.trim().toUpperCase())) {
      salvarPrioridades([...prioridades, novoApelido.trim().toUpperCase()]);
      setNovoApelido('');
    }
  };

  const handleRemovePrioridade = (apelidoRemover: string) => {
    salvarPrioridades(prioridades.filter(p => p !== apelidoRemover));
  };

  const savePastaToDB = async (pasta: IPasta, isNew: boolean = false) => {
    try {
      await fetch('http://127.0.0.1:8000/api/fechamentos', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(pasta)
      });
      if (isNew) carregarDados(); 
    } catch (e) {
      console.error("Erro ao salvar pasta", e);
    }
  };

  const handleUpdatePasta = (updatedPasta: IPasta) => {
    setPastas(prev => prev.map(p => p.id === updatedPasta.id ? updatedPasta : p));
    savePastaToDB(updatedPasta, false);
  };

  const handleAddPasta = (apelido: string, competencia: string) => {
    const nova: IPasta = { apelido, competencia, pasta_liberada_em: null, documentos_json: "[]" };
    savePastaToDB(nova, true);
  };

  return (
    <div className="page-container">
      
      {/* HEADER DA PÁGINA */}
      <div className="page-header-row">
        <div>
          <h1 className="page-title">Fechamento Contábil</h1>
          <p className="page-subtitle">Acompanhe as prioridades e controle as entregas mensais por empresa.</p>
        </div>
        <div>
          <button 
            className="action-btn-outline" 
            onClick={() => setModalOpen(true)}
            style={{ borderColor: 'var(--primary)', color: 'var(--primary)', background: 'var(--primary-light)' }}
          >
            <Settings size={16} /> Gerenciar Empresas
          </button>
        </div>
      </div>

      {/* MODAL CUSTOMIZADO (SUBSTITUI O MUI DIALOG) */}
      {modalOpen && (
        <div style={{ position: 'fixed', inset: 0, backgroundColor: 'rgba(15, 23, 42, 0.6)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 50, backdropFilter: 'blur(4px)' }}>
          <div style={{ background: 'white', borderRadius: '16px', width: '500px', maxWidth: '90%', boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.1)', overflow: 'hidden' }}>
            <div style={{ padding: '20px 24px', borderBottom: '1px solid var(--border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <h3 style={{ margin: 0, fontSize: '1.1rem', fontWeight: 800, color: 'var(--text-main)' }}>Empresas Prioritárias</h3>
            </div>
            
            <div style={{ padding: '24px' }}>
              <div style={{ display: 'flex', gap: '12px', marginBottom: '24px' }}>
                <input 
                  type="text" 
                  className="login-input" 
                  placeholder="Nome ou Apelido da Empresa" 
                  value={novoApelido} 
                  onChange={(e) => setNovoApelido(e.target.value)} 
                  onKeyDown={(e) => e.key === 'Enter' && handleAddPrioridade()}
                  style={{ flex: 1 }}
                />
                <button 
                  onClick={handleAddPrioridade} 
                  style={{ background: 'var(--primary)', color: 'white', border: 'none', padding: '0 20px', borderRadius: '12px', fontWeight: 700, cursor: 'pointer' }}
                >
                  Adicionar
                </button>
              </div>
              
              <div style={{ maxHeight: '300px', overflowY: 'auto', border: '1px solid var(--border)', borderRadius: '12px' }}>
                {prioridades.length === 0 ? (
                  <p style={{ textAlign: 'center', padding: '2rem', color: 'var(--text-muted)', fontSize: '0.85rem' }}>Nenhuma empresa cadastrada.</p>
                ) : (
                  <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
                    {prioridades.map((p) => (
                      <li key={p} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '12px 16px', borderBottom: '1px solid #f1f5f9' }}>
                        <span style={{ fontWeight: 600, color: '#334155', fontSize: '0.9rem' }}>{p}</span>
                        <button onClick={() => handleRemovePrioridade(p)} style={{ background: 'none', border: 'none', color: '#ef4444', cursor: 'pointer' }} className="hover:text-red-700">
                          <Trash2 size={16} />
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>

            <div style={{ padding: '16px 24px', background: '#f8fafc', borderTop: '1px solid var(--border)', textAlign: 'right' }}>
              <button 
                onClick={() => setModalOpen(false)} 
                style={{ background: 'white', border: '1px solid var(--border)', padding: '8px 24px', borderRadius: '8px', fontWeight: 600, color: '#475569', cursor: 'pointer' }}
              >
                Concluir
              </button>
            </div>
          </div>
        </div>
      )}

      {/* TABELA PRINCIPAL DE EMPRESAS */}
      <div className="table-card">
        <table className="modern-table">
          <thead>
            <tr>
              <th style={{ width: '60px' }}></th>
              <th>Empresa</th>
              <th style={{ textAlign: 'right', paddingRight: '24px' }}>Adicionar Competência</th>
            </tr>
          </thead>
          <tbody>
            {loading && prioridades.length === 0 ? (
              <tr><td colSpan={3} style={{ textAlign: 'center', padding: '4rem', color: 'var(--text-muted)' }}>Carregando dados...</td></tr>
            ) : prioridades.length === 0 ? (
              <tr><td colSpan={3} style={{ textAlign: 'center', padding: '4rem', color: 'var(--text-muted)' }}>Adicione empresas no botão "Gerenciar" para iniciar.</td></tr>
            ) : (
              prioridades.sort().map((empresa) => {
                const pastasDaEmpresa = pastas.filter(p => p.apelido === empresa);
                return (
                  <EmpresaRow
                    key={empresa}
                    apelido={empresa}
                    pastas={pastasDaEmpresa}
                    onUpdatePasta={handleUpdatePasta}
                    onAddPasta={(comp) => handleAddPasta(empresa, comp)}
                  />
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
import React, { useState, useEffect, useRef } from 'react';
import api from '../services/api';
import { 
  FileSearch, HardDrive, Building2, CheckCircle2, Circle, 
  Bot, Activity, Calendar, Trophy, ListTodo, PieChart, 
  Info, Search, Clock, AlertTriangle, Lock, AlertCircle,
  Settings, Plus, Edit2, Trash2, X 
} from 'lucide-react';
import DatePicker, { registerLocale } from "react-datepicker";
import "react-datepicker/dist/react-datepicker.css";
import { ptBR } from "date-fns/locale";
import { useAuth } from '../context/AuthContext';

registerLocale("pt-BR", ptBR);

interface IChecklistItem {
  id: number;
  tarefa_nome: string;
  tipo: 'AUTO' | 'MANUAL';
  status_manual: number;
  concluidas: number;
  total: number;
  usuario_conclusao?: string; 
  data_conclusao?: string;    
}

interface ITopEmpresa {
  cod: string;
  nome: string;
  qtd_os: number;
  qtd_docs: number;
}

interface IRankingProblema {
  nome: string;
  total: number; 
  qtd_senha: number;
  qtd_ia: number;
  qtd_outros: number;
}

export default function Dashboard() {
  const { user } = useAuth();
  
  const [mesFiltro, setMesFiltro] = useState(() => {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
  });

  const [abaAtiva, setAbaAtiva] = useState<'geral' | 'tarefas'>('geral');
  const [buscaTarefa, setBuscaTarefa] = useState('');

  const [resumo, setResumo] = useState({ 
    total_processado: 0, 
    sucesso_triagem: 0, 
    erros_atencao: 0, 
    empresas_ativas: 0, 
    pendente_senha: 0,
    os_sem_anexos: 0,
    tempo_medio_minutos: 0,
    label_tempo: "Tempo Médio / Triagem",
    top_empresas: [] as ITopEmpresa[],
    ranking_problemas: [] as IRankingProblema[]
  });
  
  const [checklist, setChecklist] = useState<IChecklistItem[]>([]);

  // === ESTADOS DO MODAL DE CONFIGURAÇÃO ===
  const [modalConfigOpen, setModalConfigOpen] = useState(false);
  const [tarefasConfig, setTarefasConfig] = useState<any[]>([]);
  const [editandoTarefa, setEditandoTarefa] = useState<any>(null); 
  
  // NOVO: Referência para rolar a tela até o formulário
  const formRef = useRef<HTMLDivElement>(null);

  const carregarDados = async () => {
    try {
      const [resResumo, resCheck] = await Promise.all([
        api.get(`/api/resumo?month=${mesFiltro}`), 
        api.get(`/api/dashboard/checklist?month=${mesFiltro}`)
      ]);
      setResumo(resResumo.data);
      setChecklist(resCheck.data);
    } catch (err) {
      console.error("Erro ao carregar dashboard", err);
    }
  };

  useEffect(() => {
    carregarDados();
    const intervalo = window.setInterval(() => carregarDados(), 30000);
    return () => window.clearInterval(intervalo);
  }, [mesFiltro]);

  // === FUNÇÕES DO MODAL DE CONFIGURAÇÃO ===
  const carregarConfig = async () => {
    try {
      const res = await api.get('/api/dashboard/checklist-config');
      setTarefasConfig(res.data);
    } catch (err) { console.error(err); }
  };

  const salvarTarefaConfig = async () => {
    if (!editandoTarefa?.tarefa_nome) return alert("O nome da tarefa é obrigatório.");
    
    const payload = {
        ...editandoTarefa,
        termo_gestta: editandoTarefa.tipo === 'MANUAL' ? null : editandoTarefa.termo_gestta,
        ativa: editandoTarefa.ativa ?? 1
    };

    try {
      const url = editandoTarefa.id 
        ? `/api/dashboard/checklist-config?id_tarefa=${editandoTarefa.id}` 
        : `/api/dashboard/checklist-config`;
        
      await api.post(url, payload);
      setEditandoTarefa(null);
      carregarConfig();
      carregarDados(); 
    } catch (err) { console.error(err); }
  };

  const excluirTarefaConfig = async (id: number) => {
    if(!window.confirm("Deseja mesmo remover (desativar) esta obrigação?")) return;
    try {
      await api.delete(`/api/dashboard/checklist-config/${id}`);
      carregarConfig();
      carregarDados();
    } catch (err) { console.error(err); }
  };
  // ==========================================

  const formatarNumero = (num: number) => num?.toLocaleString('pt-BR') || 0;

  const formatarTempo = (minutosTotais: number) => {
    if (!minutosTotais || minutosTotais <= 0) return '---';
    if (minutosTotais < 1) return `${Math.round(minutosTotais * 60)} seg`;
    const horas = Math.floor(minutosTotais / 60);
    const minutos = Math.round(minutosTotais % 60);
    if (horas >= 24) return `${Math.floor(horas / 24)}d ${horas % 24}h`;
    if (horas > 0) return `${horas}h ${minutos}m`;
    return `${minutos} min`;
  };

  const handleToggle = async (item: IChecklistItem) => {
    if (item.tipo === 'AUTO') return;
    try {
      await api.put(`/api/dashboard/checklist/${item.id}/toggle`, { 
        status: item.status_manual === 1 ? 0 : 1, 
        month: mesFiltro,
        usuario: user?.full_name || 'Usuário' 
      });
      carregarDados();
    } catch (err) { console.error(err); }
  };

  const totalDocs = resumo.sucesso_triagem + resumo.erros_atencao + resumo.pendente_senha;
  const percSucesso = totalDocs > 0 ? (resumo.sucesso_triagem / totalDocs) * 100 : 0;
  const percErros = totalDocs > 0 ? ((resumo.erros_atencao + resumo.pendente_senha) / totalDocs) * 100 : 0;
  
  const osComAnexo = resumo.total_processado - resumo.os_sem_anexos;
  const percOsAnexo = resumo.total_processado > 0 ? (osComAnexo / resumo.total_processado) * 100 : 0;
  const percOsVazia = resumo.total_processado > 0 ? (resumo.os_sem_anexos / resumo.total_processado) * 100 : 0;

  const maxDemandas = resumo.top_empresas.length > 0 ? Math.max(...resumo.top_empresas.map(e => e.qtd_os)) : 1;
  const maxErros = resumo.ranking_problemas.length > 0 ? Math.max(...resumo.ranking_problemas.map(e => e.total)) : 1;

  const checklistFiltrado = checklist.filter(item => 
    item.tarefa_nome.toLowerCase().includes(buscaTarefa.toLowerCase())
  );

  return (
    <div style={{ paddingBottom: '40px', maxWidth: '1400px', margin: '0 auto' }}>
      
      {/* HEADER */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '2rem' }}>
        <div>
          <h1 style={{ fontSize: '1.8rem', fontWeight: 800, color: 'var(--text-main)', margin: 0 }}>Painel Executivo</h1>
          <p style={{ color: 'var(--text-muted)', margin: 0 }}>Visão geral da agilidade do Robô e obrigações.</p>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', background: 'var(--bg-card)', padding: '0 12px', borderRadius: '10px', border: '1px solid var(--border)', height: '42px' }}>
          <Calendar size={16} style={{ color: 'var(--primary)', marginRight: '8px' }} />
          <DatePicker 
            selected={new Date(parseInt(mesFiltro.split('-')[0]), parseInt(mesFiltro.split('-')[1]) - 1)} 
            onChange={(d: Date | null) => { if (d) setMesFiltro(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`); }} 
            dateFormat="MMMM yyyy" showMonthYearPicker locale="pt-BR" 
            className="bg-transparent border-none font-bold text-sm text-[#3a3a3a] focus:ring-0 cursor-pointer uppercase outline-none w-32" 
          />
        </div>
      </div>

      {/* INDICADORES TOPO */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '1.5rem', marginBottom: '2rem' }}>
        <div className="card" style={{ display: 'flex', alignItems: 'center', gap: '1.2rem', padding: '1.5rem' }}>
          <div style={{ padding: '12px', background: 'var(--primary-light)', color: 'var(--primary)', borderRadius: '12px' }}><HardDrive size={28} /></div>
          <div><p style={{ fontSize: '0.75rem', fontWeight: 800, color: 'var(--text-muted)', textTransform: 'uppercase', margin: 0 }}>OS Baixadas</p><p style={{ fontSize: '1.8rem', fontWeight: 900, color: 'var(--text-main)', margin: 0 }}>{formatarNumero(resumo.total_processado)}</p></div>
        </div>
        
        <div className="card" style={{ display: 'flex', alignItems: 'center', gap: '1.2rem', padding: '1.5rem' }}>
           <div style={{ padding: '12px', background: '#dcfce7', color: '#16a34a', borderRadius: '12px' }}><FileSearch size={28} /></div>
           <div><p style={{ fontSize: '0.75rem', fontWeight: 800, color: 'var(--text-muted)', textTransform: 'uppercase', margin: 0 }}>Arquivos Extraídos</p><p style={{ fontSize: '1.8rem', fontWeight: 900, color: 'var(--text-main)', margin: 0 }}>{formatarNumero(resumo.sucesso_triagem)}</p></div>
        </div>

        <div className="card" style={{ display: 'flex', alignItems: 'center', gap: '1.2rem', padding: '1.5rem' }}>
           <div style={{ padding: '12px', background: '#f1f5f9', color: '#475569', borderRadius: '12px' }}><Building2 size={28} /></div>
           <div><p style={{ fontSize: '0.75rem', fontWeight: 800, color: 'var(--text-muted)', textTransform: 'uppercase', margin: 0 }}>Empresas Atendidas</p><p style={{ fontSize: '1.8rem', fontWeight: 900, color: 'var(--text-main)', margin: 0 }}>{formatarNumero(resumo.empresas_ativas)}</p></div>
        </div>
        <div className="card" style={{ display: 'flex', alignItems: 'center', gap: '1.2rem', padding: '1.5rem' }}>
           <div style={{ padding: '12px', background: '#fff7ed', color: '#ea580c', borderRadius: '12px' }}><Clock size={28} /></div>
           <div>
             <p style={{ fontSize: '0.75rem', fontWeight: 800, color: 'var(--text-muted)', textTransform: 'uppercase', margin: 0 }}>{resumo.label_tempo}</p>
             <p style={{ fontSize: '1.8rem', fontWeight: 900, color: 'var(--text-main)', margin: 0 }}>{formatarTempo(resumo.tempo_medio_minutos)}</p>
           </div>
        </div>
      </div>

      {/* ABAS */}
      <div style={{ display: 'flex', gap: '1rem', borderBottom: '2px solid var(--border)', marginBottom: '2rem' }}>
        <button 
          onClick={() => setAbaAtiva('geral')} 
          style={{ 
            display: 'flex', alignItems: 'center', gap: '8px', padding: '12px 24px', background: 'none', border: 'none', 
            borderBottom: abaAtiva === 'geral' ? '3px solid var(--primary)' : '3px solid transparent', 
            color: abaAtiva === 'geral' ? 'var(--primary)' : 'var(--text-muted)', 
            fontWeight: 800, fontSize: '0.85rem', cursor: 'pointer' 
          }}
        >
          <PieChart size={18} /> Acompanhamento Geral
        </button>

        <button 
          onClick={() => setAbaAtiva('tarefas')} 
          style={{ 
            display: 'flex', alignItems: 'center', gap: '8px', padding: '12px 24px', background: 'none', border: 'none', 
            borderBottom: abaAtiva === 'tarefas' ? '3px solid var(--primary)' : '3px solid transparent', 
            color: abaAtiva === 'tarefas' ? 'var(--primary)' : 'var(--text-muted)', 
            fontWeight: 800, fontSize: '0.85rem', cursor: 'pointer' 
          }}
        >
          <ListTodo size={18} /> Obrigações do Mês
        </button>
      </div>

      {/* CONTEÚDO DA ABA GERAL */}
      {abaAtiva === 'geral' && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(400px, 1fr))', gap: '2rem' }}>
            
            <div className="card" style={{ padding: '24px', display: 'flex', flexDirection: 'column', gap: '2rem' }}>
                <div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '16px' }}><Info size={18} color="var(--primary)" /><h3 style={{ margin: 0, fontSize: '1rem', fontWeight: 800 }}>Composição das OS</h3></div>
                    <div style={{ display: 'flex', height: '24px', borderRadius: '8px', overflow: 'hidden', marginBottom: '12px', border: '1px solid var(--border)', background: '#eee' }}>
                        <div style={{ width: `${percOsAnexo}%`, background: 'var(--primary)', transition: 'width 1s' }}></div>
                        <div style={{ width: `${percOsVazia}%`, background: '#f59e0b', transition: 'width 1s' }}></div>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem', fontWeight: 700 }}>
                        <span style={{ color: 'var(--primary)' }}>Com Arquivos ({formatarNumero(osComAnexo)})</span>
                        <span style={{ color: '#d97706' }}>Só Mensagem ({formatarNumero(resumo.os_sem_anexos)})</span>
                    </div>
                </div>
                <hr style={{ border: 'none', borderTop: '1px dashed var(--border)' }} />
                <div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '16px' }}><Activity size={18} color="#10b981" /><h3 style={{ margin: 0, fontSize: '1rem', fontWeight: 800 }}>Qualidade da Triagem IA</h3></div>
                    <div style={{ display: 'flex', height: '24px', borderRadius: '8px', overflow: 'hidden', marginBottom: '12px', border: '1px solid var(--border)', background: '#eee' }}>
                        <div style={{ width: `${percSucesso}%`, background: '#10b981', transition: 'width 1s' }}></div>
                        <div style={{ width: `${percErros}%`, background: '#ef4444', transition: 'width 1s' }}></div>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem', fontWeight: 700 }}>
                        <span style={{ color: '#059669' }}>Sucesso ({formatarNumero(resumo.sucesso_triagem)})</span>
                        <span style={{ color: '#dc2626' }}>Erros/Senha ({formatarNumero(resumo.erros_atencao + resumo.pendente_senha)})</span>
                    </div>
                </div>
            </div>

            <div className="card" style={{ padding: '24px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '24px' }}><Trophy size={20} color="#f59e0b" /><h3 style={{ margin: 0, fontSize: '1rem', fontWeight: 800 }}>TOP Empresas (Volume)</h3></div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '18px' }}>
                    {resumo.top_empresas.map((emp, index) => (
                        <div key={index}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.8rem', fontWeight: 700, marginBottom: '6px' }}>
                                <span>{index + 1}. {emp.nome}</span>
                                <div style={{ display: 'flex', gap: '8px', color: 'var(--primary)', fontSize: '0.7rem' }}>
                                  <span>{formatarNumero(emp.qtd_os)} OS</span>
                                  <span>|</span>
                                  <span>{formatarNumero(emp.qtd_docs)} docs</span>
                                </div>
                            </div>
                            <div style={{ width: '100%', height: '6px', background: '#f1f5f9', borderRadius: '4px', overflow: 'hidden' }}>
                                <div style={{ width: `${(emp.qtd_os / maxDemandas) * 100}%`, height: '100%', background: 'var(--primary-light)', borderRadius: '4px' }}></div>
                            </div>
                        </div>
                    ))}
                </div>
            </div>

            <div className="card" style={{ padding: '24px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '24px' }}><AlertTriangle size={20} color="#ef4444" /><h3 style={{ margin: 0, fontSize: '1rem', fontWeight: 800 }}>Maiores Geradores de Erros</h3></div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '22px' }}>
                    {resumo.ranking_problemas.map((prob, index) => {
                        const pSenha = (prob.qtd_senha / prob.total) * 100;
                        const pIA = (prob.qtd_ia / prob.total) * 100;
                        const pOutros = (prob.qtd_outros / prob.total) * 100;

                        return (
                            <div key={index} style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                    <span style={{ fontSize: '0.85rem', fontWeight: 700, color: 'var(--text-main)', maxWidth: '70%', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                        {index + 1}. {prob.nome}
                                    </span>
                                    <span style={{ fontSize: '0.75rem', fontWeight: 800, color: '#ef4444' }}>
                                        {prob.total} erros
                                    </span>
                                </div>

                                <div style={{ width: '100%', height: '10px', background: '#f1f5f9', borderRadius: '5px', overflow: 'hidden', display: 'flex', border: '1px solid var(--border)' }}>
                                    <div title={`Senha: ${prob.qtd_senha}`} style={{ width: `${pSenha}%`, background: '#991b1b', transition: 'width 1s' }} />
                                    <div title={`IA/Extração: ${prob.qtd_ia}`} style={{ width: `${pIA}%`, background: '#f97316', transition: 'width 1s' }} />
                                    <div title={`Outros: ${prob.qtd_outros}`} style={{ width: `${pOutros}%`, background: '#ef4444', transition: 'width 1s' }} />
                                </div>

                                <div style={{ display: 'flex', gap: '12px', fontSize: '0.6rem', fontWeight: 700, color: 'var(--text-muted)' }}>
                                    {prob.qtd_senha > 0 && <span style={{ display: 'flex', alignItems: 'center', gap: '3px' }}><Lock size={10} color="#991b1b" /> {prob.qtd_senha} SENHA</span>}
                                    {prob.qtd_ia > 0 && <span style={{ display: 'flex', alignItems: 'center', gap: '3px' }}><Bot size={10} color="#f97316" /> {prob.qtd_ia} IA</span>}
                                    {prob.qtd_outros > 0 && <span style={{ display: 'flex', alignItems: 'center', gap: '3px' }}><AlertCircle size={10} color="#ef4444" /> {prob.qtd_outros} OUTROS</span>}
                                </div>
                            </div>
                        );
                    })}
                </div>
            </div>
        </div>
      )}

    {/* ABA TAREFAS */}
    {abaAtiva === 'tarefas' && (
      <div className="card" style={{ padding: '0', overflow: 'hidden' }}>
        <div style={{ padding: '16px 24px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', gap: '12px', background: '#fafafa' }}>
          <Search size={18} color="var(--text-muted)" />
          <input 
            type="text" 
            placeholder="Filtrar tarefas..." 
            value={buscaTarefa} 
            onChange={(e) => setBuscaTarefa(e.target.value)} 
            style={{ border: 'none', outline: 'none', width: '100%', fontSize: '0.9rem', background: 'transparent' }} 
          />
          <button 
            onClick={() => { setEditandoTarefa(null); setModalConfigOpen(true); carregarConfig(); }}
            style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'white', border: '1px solid var(--border)', borderRadius: '10px', width: '42px', height: '42px', cursor: 'pointer', color: 'var(--text-muted)' }}
            title="Configurar Obrigações"
          >
            <Settings size={20} />
          </button>
        </div>
        
        <div style={{ padding: '0 24px', maxHeight: '65vh', overflowY: 'auto' }} className="custom-scrollbar">
          {checklistFiltrado.length > 0 ? checklistFiltrado.map((item) => (
            <div key={item.id} style={{ 
              display: 'flex', alignItems: 'center', padding: '14px 0', borderBottom: '1px solid var(--border)', 
              opacity: (item.status_manual === 1 || (item.tipo === 'AUTO' && item.concluidas === item.total && item.total > 0)) ? 0.6 : 1 
            }}>
              <div style={{ marginRight: '16px', display: 'flex', alignItems: 'center' }}>
                  <button onClick={() => handleToggle(item)} style={{ background: 'none', border: 'none', cursor: item.tipo === 'MANUAL' ? 'pointer' : 'default', padding: 0, display: 'flex' }}>
                    {(item.status_manual === 1 || (item.tipo === 'AUTO' && item.concluidas === item.total && item.total > 0)) ? 
                      <CheckCircle2 size={22} color="#10b981" fill="#d1fae5" /> : <Circle size={22} color="#cbd5e1" />
                    }
                  </button>
              </div>

              <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'nowrap' }}>
                      <span style={{ fontWeight: 600, fontSize: '0.85rem', color: 'var(--text-main)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                        {item.tarefa_nome}
                      </span>
                      
                      {item.tipo === 'AUTO' && (
                        <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', fontSize: '0.55rem', background: 'var(--primary-light)', color: 'var(--primary)', padding: '2px 8px', borderRadius: '12px', fontWeight: 800, whiteSpace: 'nowrap', flexShrink: 0 }}>
                          <Bot size={12} /> GESTTA
                        </span>
                      )}
                  </div>
                  
                  {item.tipo === 'MANUAL' && item.status_manual === 1 && (
                    <div style={{ fontSize: '0.65rem', color: 'var(--text-muted)', marginTop: '2px' }}>
                      Concluído por <strong>{item.usuario_conclusao?.split(' ')[0]}</strong> em {item.data_conclusao}
                    </div>
                  )}
                  
                  {item.tipo === 'AUTO' && (
                    <div style={{ width: '100%', maxWidth: '250px', height: '6px', background: '#f1f5f9', borderRadius: '10px', overflow: 'hidden', marginTop: '6px', border: '1px solid #e2e8f0' }}>
                      <div style={{ width: `${item.total > 0 ? (item.concluidas / item.total) * 100 : 0}%`, height: '100%', background: item.concluidas === item.total && item.total > 0 ? '#10b981' : 'var(--primary)', transition: 'width 0.5s ease' }} />
                    </div>
                  )}
              </div>

              <div style={{ marginLeft: '20px', fontSize: '0.75rem', fontWeight: 800, color: 'var(--text-muted)', minWidth: '90px', textAlign: 'right' }}>
                {item.tipo === 'AUTO' ? `${item.concluidas} / ${item.total}` : (item.status_manual === 1 ? 'FINALIZADO' : 'PENDENTE')}
              </div>
            </div>
          )) : (
            <div style={{ padding: '3rem', textAlign: 'center', color: 'var(--text-muted)' }}>
              Nenhuma obrigação encontrada para este filtro.
            </div>
          )}
        </div>
      </div>
    )}

      {/* MODAL DE CONFIGURAÇÃO */}
      {modalConfigOpen && (
        <div style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, background: 'rgba(15, 23, 42, 0.6)', backdropFilter: 'blur(4px)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 9999 }}>
          
          <div className="card" style={{ width: '650px', maxHeight: '85vh', display: 'flex', flexDirection: 'column', padding: 0, overflow: 'hidden', boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.25)' }}>
            
            {/* Modal Header Fixo */}
            <div style={{ padding: '20px 24px', borderBottom: '1px solid var(--border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: '#fff', zIndex: 10 }}>
              <h2 style={{ margin: 0, fontSize: '1.25rem', fontWeight: 800, color: 'var(--text-main)' }}>Configurar Obrigações</h2>
              <button onClick={() => setModalConfigOpen(false)} style={{ background: '#f1f5f9', border: 'none', cursor: 'pointer', padding: '6px', borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)' }}>
                <X size={20} />
              </button>
            </div>

            {/* Modal Body (Rolagem) */}
            <div style={{ padding: '24px', overflowY: 'auto' }} className="custom-scrollbar">

              {/* FORMULÁRIO DE EDIÇÃO / CRIAÇÃO */}
              <div ref={formRef} style={{ background: '#f8fafc', padding: '20px', borderRadius: '12px', marginBottom: '32px', border: '1px solid #e2e8f0', boxShadow: 'inset 0 2px 4px 0 rgba(0, 0, 0, 0.02)' }}>
                
                <h3 style={{ fontSize: '1rem', fontWeight: 800, marginBottom: '20px', color: 'var(--text-main)', display: 'flex', alignItems: 'center', gap: '8px' }}>
                  {editandoTarefa?.id ? <Edit2 size={18} color="var(--primary)"/> : <Plus size={18} color="var(--primary)"/>}
                  {editandoTarefa?.id ? 'Editar Obrigação' : 'Nova Obrigação'}
                </h3>
                
                <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: '16px', marginBottom: '16px' }}>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                    <label style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase' }}>Nome da Tarefa</label>
                    <input 
                      type="text" 
                      placeholder="Ex: Fechamento Folha" 
                      value={editandoTarefa?.tarefa_nome || ''} 
                      onChange={(e) => setEditandoTarefa({...editandoTarefa, tarefa_nome: e.target.value})}
                      style={{ padding: '10px 14px', borderRadius: '8px', border: '1px solid #cbd5e1', fontSize: '0.9rem', outline: 'none' }}
                    />
                  </div>
                  
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                    <label style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase' }}>Tipo de Baixa</label>
                    <select 
                      value={editandoTarefa?.tipo || 'MANUAL'} 
                      onChange={(e) => setEditandoTarefa({...editandoTarefa, tipo: e.target.value})}
                      style={{ padding: '10px 14px', borderRadius: '8px', border: '1px solid #cbd5e1', fontSize: '0.9rem', outline: 'none', backgroundColor: '#fff' }}
                    >
                      <option value="MANUAL">Manual</option>
                      <option value="AUTO">Auto (Gestta)</option>
                    </select>
                  </div>
                </div>

                {editandoTarefa?.tipo === 'AUTO' && (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', marginBottom: '16px' }}>
                    <label style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase' }}>Termo exato no Gestta</label>
                    <input 
                      type="text" 
                      placeholder="Ex: ISS RPA" 
                      value={editandoTarefa?.termo_gestta || ''} 
                      onChange={(e) => setEditandoTarefa({...editandoTarefa, termo_gestta: e.target.value})}
                      style={{ padding: '10px 14px', borderRadius: '8px', border: '1px solid #cbd5e1', fontSize: '0.9rem', outline: 'none' }}
                    />
                  </div>
                )}

                {/* Ações do Formulário */}
                <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '12px', marginTop: '24px', paddingTop: '16px', borderTop: '1px solid #e2e8f0' }}>
                  {editandoTarefa?.id && (
                    <button onClick={() => setEditandoTarefa(null)} style={{ padding: '8px 16px', fontSize: '0.85rem', fontWeight: 700, color: '#475569', background: '#f1f5f9', border: 'none', borderRadius: '8px', cursor: 'pointer' }}>
                      Cancelar
                    </button>
                  )}
                  <button onClick={salvarTarefaConfig} style={{ background: 'var(--primary)', color: 'white', border: 'none', padding: '8px 20px', borderRadius: '8px', fontWeight: 700, fontSize: '0.85rem', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '6px', boxShadow: '0 4px 6px -1px rgba(99, 102, 241, 0.2)' }}>
                    <CheckCircle2 size={16} /> Salvar Obrigação
                  </button>
                </div>
              </div>

              {/* LISTA DE TAREFAS EXISTENTES */}
              <div>
                <h3 style={{ fontSize: '1rem', fontWeight: 800, marginBottom: '16px', color: 'var(--text-main)' }}>Obrigações Cadastradas</h3>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                  {tarefasConfig.map(t => (
                    <div key={t.id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '16px', background: '#fff', border: '1px solid #e2e8f0', borderRadius: '10px', opacity: t.ativa ? 1 : 0.5, transition: 'all 0.2s', boxShadow: '0 1px 2px 0 rgba(0, 0, 0, 0.05)' }}>
                      
                      <div>
                        <strong style={{ fontSize: '0.95rem', display: 'block', color: 'var(--text-main)', textDecoration: t.ativa ? 'none' : 'line-through', marginBottom: '4px' }}>
                          {t.tarefa_nome}
                        </strong>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                          <span style={{ fontSize: '0.65rem', fontWeight: 800, color: t.tipo === 'AUTO' ? 'var(--primary)' : '#64748b', background: t.tipo === 'AUTO' ? 'var(--primary-light)' : '#f1f5f9', padding: '4px 8px', borderRadius: '6px' }}>
                            {t.tipo === 'AUTO' ? 'AUTOMÁTICA' : 'MANUAL'}
                          </span>
                          {t.termo_gestta && <span style={{ fontSize: '0.75rem', color: '#94a3b8' }}>Busca: <strong>{t.termo_gestta}</strong></span>}
                        </div>
                      </div>

                      <div style={{ display: 'flex', gap: '8px' }}>
                        <button 
                          onClick={() => { 
                            setEditandoTarefa(t); 
                            formRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }); 
                          }} 
                          style={{ background: '#f0fdf4', border: 'none', cursor: 'pointer', color: '#16a34a', padding: '8px', borderRadius: '8px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}
                          title="Editar"
                        >
                          <Edit2 size={16} />
                        </button>
                        
                        {t.ativa === 1 && (
                          <button 
                            onClick={() => excluirTarefaConfig(t.id)} 
                            style={{ background: '#fef2f2', border: 'none', cursor: 'pointer', color: '#dc2626', padding: '8px', borderRadius: '8px', display: 'flex', alignItems: 'center', justifyContent: 'center' }} 
                            title="Desativar"
                          >
                            <Trash2 size={16} />
                          </button>
                        )}
                      </div>

                    </div>
                  ))}
                </div>
              </div>

            </div>
          </div>
        </div>
      )}
    </div>
  );
}
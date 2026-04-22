import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { FileSearch, HardDrive, Building2, CheckCircle2, Circle, Bot, Activity, Calendar, Trophy, ListTodo, PieChart, Info } from 'lucide-react';
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

export default function Dashboard() {
  const { user } = useAuth();
  
  const [mesFiltro, setMesFiltro] = useState(() => {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
  });

  const [abaAtiva, setAbaAtiva] = useState<'geral' | 'tarefas'>('geral');

  const [resumo, setResumo] = useState({ 
    total_processado: 0, 
    sucesso_triagem: 0, 
    erros_atencao: 0, 
    empresas_ativas: 0, 
    pendente_senha: 0,
    os_sem_anexos: 0,
    top_empresas: [] as ITopEmpresa[]
  });
  
  const [checklist, setChecklist] = useState<IChecklistItem[]>([]);

  const carregarDados = async () => {
    try {
      const [resResumo, resCheck] = await Promise.all([
        axios.get(`http://127.0.0.1:8000/api/resumo?month=${mesFiltro}`), 
        axios.get(`http://127.0.0.1:8000/api/dashboard/checklist?month=${mesFiltro}`)
      ]);
      setResumo(resResumo.data);
      setChecklist(resCheck.data);
    } catch (err) {
      console.error("Erro ao carregar dashboard", err);
    }
  };

  useEffect(() => { carregarDados(); }, [mesFiltro]);

  const handleToggle = async (item: IChecklistItem) => {
    if (item.tipo === 'AUTO') return;
    const novoStatus = item.status_manual === 1 ? 0 : 1;
    try {
      await axios.put(`http://127.0.0.1:8000/api/dashboard/checklist/${item.id}/toggle`, { 
        status: novoStatus, 
        month: mesFiltro,
        usuario: user?.full_name || 'Usuário' 
      });
      carregarDados();
    } catch (err) { console.error(err); }
  };

  // Cálculos para os gráficos de composição
  const totalDocs = resumo.sucesso_triagem + resumo.erros_atencao + resumo.pendente_senha;
  const percSucesso = totalDocs > 0 ? Math.round((resumo.sucesso_triagem / totalDocs) * 100) : 0;
  const percErros = totalDocs > 0 ? Math.round(((resumo.erros_atencao + resumo.pendente_senha) / totalDocs) * 100) : 0;
  
  const osComAnexo = resumo.total_processado - resumo.os_sem_anexos;
  const percOsAnexo = resumo.total_processado > 0 ? Math.round((osComAnexo / resumo.total_processado) * 100) : 0;
  const percOsVazia = resumo.total_processado > 0 ? Math.round((resumo.os_sem_anexos / resumo.total_processado) * 100) : 0;

  const maxDemandas = resumo.top_empresas.length > 0 ? Math.max(...resumo.top_empresas.map(e => e.qtd_os)) : 1;

  return (
    <div style={{ paddingBottom: '40px', maxWidth: '1400px', margin: '0 auto' }}>
      
      {/* HEADER E CALENDÁRIO */}
      <div className="page-header-row" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '2rem' }}>
        <div>
          <h1 className="page-title" style={{ fontSize: '1.8rem', fontWeight: 800, color: 'var(--text-main)', margin: 0 }}>Painel Executivo</h1>
          <p className="page-subtitle" style={{ color: 'var(--text-muted)', margin: 0 }}>Visão geral da esteira RPA e obrigações do mês.</p>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', background: 'var(--bg-card)', padding: '0 12px', borderRadius: '10px', border: '1px solid var(--border)', height: '42px' }}>
          <Calendar size={16} style={{ color: 'var(--primary)', marginRight: '8px' }} />
          <DatePicker 
            selected={new Date(parseInt(mesFiltro.split('-')[0]), parseInt(mesFiltro.split('-')[1]) - 1)} 
            onChange={(d: Date | null) => { if (d) setMesFiltro(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`); }} 
            dateFormat="MMMM yyyy" 
            showMonthYearPicker 
            locale="pt-BR" 
            className="bg-transparent border-none font-bold text-sm text-[#3a3a3a] focus:ring-0 cursor-pointer uppercase outline-none w-32" 
          />
        </div>
      </div>

      {/* 3 CARDS INDICADORES (Clean e Diretos) */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '1.5rem', marginBottom: '2rem' }}>
        <div className="card" style={{ display: 'flex', alignItems: 'center', gap: '1.2rem', padding: '1.5rem' }}>
          <div style={{ padding: '12px', background: 'var(--primary-light)', color: 'var(--primary)', borderRadius: '12px' }}><HardDrive size={28} /></div>
          <div><p style={{ fontSize: '0.75rem', fontWeight: 800, color: 'var(--text-muted)', textTransform: 'uppercase', margin: 0 }}>Total de OS Baixadas</p><p style={{ fontSize: '2rem', fontWeight: 900, color: 'var(--text-main)', margin: 0, lineHeight: 1.1 }}>{resumo.total_processado}</p></div>
        </div>
        <div className="card" style={{ display: 'flex', alignItems: 'center', gap: '1.2rem', padding: '1.5rem' }}>
           <div style={{ padding: '12px', background: '#dcfce7', color: '#16a34a', borderRadius: '12px' }}><FileSearch size={28} /></div>
           <div><p style={{ fontSize: '0.75rem', fontWeight: 800, color: 'var(--text-muted)', textTransform: 'uppercase', margin: 0 }}>Documentos Extraídos</p><p style={{ fontSize: '2rem', fontWeight: 900, color: 'var(--text-main)', margin: 0, lineHeight: 1.1 }}>{resumo.sucesso_triagem}</p></div>
        </div>
        <div className="card" style={{ display: 'flex', alignItems: 'center', gap: '1.2rem', padding: '1.5rem' }}>
           <div style={{ padding: '12px', background: '#f1f5f9', color: '#475569', borderRadius: '12px' }}><Building2 size={28} /></div>
           <div><p style={{ fontSize: '0.75rem', fontWeight: 800, color: 'var(--text-muted)', textTransform: 'uppercase', margin: 0 }}>Empresas Atendidas</p><p style={{ fontSize: '2rem', fontWeight: 900, color: 'var(--text-main)', margin: 0, lineHeight: 1.1 }}>{resumo.empresas_ativas}</p></div>
        </div>
      </div>

      {/* NAVEGAÇÃO DAS ABAS */}
      <div style={{ display: 'flex', gap: '1rem', borderBottom: '2px solid var(--border)', marginBottom: '2rem' }}>
        <button
          onClick={() => setAbaAtiva('geral')}
          style={{
            display: 'flex', alignItems: 'center', gap: '8px',
            padding: '12px 24px', background: 'none',
            border: 'none', borderBottom: abaAtiva === 'geral' ? '3px solid var(--primary)' : '3px solid transparent',
            color: abaAtiva === 'geral' ? 'var(--primary)' : 'var(--text-muted)',
            fontWeight: 800, fontSize: '0.85rem', cursor: 'pointer', transition: 'all 0.2s',
            marginBottom: '-2px'
          }}
        >
          <PieChart size={18} />
          Acompanhamento Geral
        </button>

        <button
          onClick={() => setAbaAtiva('tarefas')}
          style={{
            display: 'flex', alignItems: 'center', gap: '8px',
            padding: '12px 24px', background: 'none',
            border: 'none', borderBottom: abaAtiva === 'tarefas' ? '3px solid var(--primary)' : '3px solid transparent',
            color: abaAtiva === 'tarefas' ? 'var(--primary)' : 'var(--text-muted)',
            fontWeight: 800, fontSize: '0.85rem', cursor: 'pointer', transition: 'all 0.2s',
            marginBottom: '-2px'
          }}
        >
          <ListTodo size={18} />
          Obrigações do Mês
          <span style={{ 
            background: abaAtiva === 'tarefas' ? 'var(--primary-light)' : '#f1f5f9', 
            color: abaAtiva === 'tarefas' ? 'var(--primary)' : 'var(--text-muted)', 
            padding: '2px 8px', borderRadius: '12px', fontSize: '0.65rem', marginLeft: '8px' 
          }}>
            {checklist.filter(c => c.status_manual === 1 || (c.tipo === 'AUTO' && c.concluidas === c.total && c.total > 0)).length} / {checklist.length}
          </span>
        </button>
      </div>

      {/* CONTEÚDO DA ABA 1: VISÃO GERAL (Raio-X) */}
      {abaAtiva === 'geral' && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(450px, 1fr))', gap: '2rem', alignItems: 'stretch' }}>
            
            {/* GRÁFICOS DE COMPOSIÇÃO */}
            <div className="card" style={{ padding: '24px', display: 'flex', flexDirection: 'column', gap: '2rem' }}>
                
                {/* Info 1: Composição das OS */}
                <div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '16px' }}>
                        <Info size={18} color="var(--primary)" />
                        <h3 style={{ margin: 0, fontSize: '1rem', fontWeight: 800, color: 'var(--text-main)' }}>Composição das Solicitações (OS)</h3>
                    </div>
                    {resumo.total_processado === 0 ? (
                        <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Nenhuma OS.</div>
                    ) : (
                        <>
                            <div style={{ display: 'flex', height: '24px', borderRadius: '8px', overflow: 'hidden', marginBottom: '12px', border: '1px solid var(--border)' }}>
                                <div style={{ width: `${percOsAnexo}%`, background: 'var(--primary)', transition: 'width 1s' }}></div>
                                <div style={{ width: `${percOsVazia}%`, background: '#f59e0b', transition: 'width 1s' }}></div>
                            </div>
                            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.8rem', fontWeight: 700 }}>
                                <span style={{ color: 'var(--primary)' }}><span style={{ display: 'inline-block', width:'8px', height:'8px', borderRadius:'50%', background:'var(--primary)', marginRight:'6px'}}></span>Com Arquivos ({osComAnexo})</span>
                                <span style={{ color: '#d97706' }}><span style={{ display: 'inline-block', width:'8px', height:'8px', borderRadius:'50%', background:'#f59e0b', marginRight:'6px'}}></span>Só Mensagem ({resumo.os_sem_anexos})</span>
                            </div>
                        </>
                    )}
                </div>

                <hr style={{ border: 'none', borderTop: '1px dashed var(--border)' }} />

                {/* Info 2: Qualidade da Extração */}
                <div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '16px' }}>
                        <Activity size={18} color="#10b981" />
                        <h3 style={{ margin: 0, fontSize: '1rem', fontWeight: 800, color: 'var(--text-main)' }}>Qualidade da Inteligência Artificial</h3>
                    </div>
                    {totalDocs === 0 ? (
                        <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Nenhum documento lido.</div>
                    ) : (
                        <>
                            <div style={{ display: 'flex', height: '24px', borderRadius: '8px', overflow: 'hidden', marginBottom: '12px', border: '1px solid var(--border)' }}>
                                <div style={{ width: `${percSucesso}%`, background: '#10b981', transition: 'width 1s' }}></div>
                                <div style={{ width: `${percErros}%`, background: '#ef4444', transition: 'width 1s' }}></div>
                            </div>
                            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.8rem', fontWeight: 700 }}>
                                <span style={{ color: '#059669' }}><span style={{ display: 'inline-block', width:'8px', height:'8px', borderRadius:'50%', background:'#10b981', marginRight:'6px'}}></span>Extraído c/ Sucesso ({resumo.sucesso_triagem})</span>
                                <span style={{ color: '#dc2626' }}><span style={{ display: 'inline-block', width:'8px', height:'8px', borderRadius:'50%', background:'#ef4444', marginRight:'6px'}}></span>Erros ou Senha ({resumo.erros_atencao + resumo.pendente_senha})</span>
                            </div>
                        </>
                    )}
                </div>

            </div>

            {/* RANKING AUMENTADO COM DETALHES DE DOCS */}
            <div className="card" style={{ padding: '24px', minHeight: '350px', display: 'flex', flexDirection: 'column' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '24px' }}>
                    <Trophy size={20} color="#f59e0b" />
                    <h3 style={{ margin: 0, fontSize: '1rem', fontWeight: 800, color: 'var(--text-main)' }}>Top Demandas do Mês</h3>
                </div>

                {resumo.top_empresas.length === 0 ? (
                    <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)', fontSize: '0.85rem' }}>Nenhuma OS registrada no mês.</div>
                ) : (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
                        {resumo.top_empresas.map((emp, index) => (
                            <div key={index} style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                                        <span style={{ fontSize: '0.75rem', fontWeight: 900, color: 'var(--text-muted)', width: '20px' }}>#{index + 1}</span>
                                        <span style={{ fontSize: '0.85rem', fontWeight: 700, color: 'var(--text-main)' }}>{emp.nome}</span>
                                    </div>
                                    {/* INFO MELHORADA: OS + DOCS */}
                                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.75rem', fontWeight: 800, color: 'var(--primary)' }}>
                                        <span>{emp.qtd_os} OS</span>
                                        <span style={{ color: 'var(--border)' }}>|</span>
                                        <span style={{ color: 'var(--text-muted)' }}>{emp.qtd_docs} docs</span>
                                    </div>
                                </div>
                                <div style={{ width: '100%', height: '8px', background: '#f1f5f9', borderRadius: '4px', overflow: 'hidden' }}>
                                    <div style={{ width: `${(emp.qtd_os / maxDemandas) * 100}%`, height: '100%', background: 'var(--primary-light)', borderRadius: '4px' }}></div>
                                </div>
                            </div>
                        ))}
                    </div>
                )}
            </div>
        </div>
      )}

      {/* CONTEÚDO DA ABA 2: OBRIGAÇÕES DO MÊS (LISTA COMPACTA) */}
      {abaAtiva === 'tarefas' && (
        <div className="card" style={{ padding: '0', overflow: 'hidden', width: '100%' }}>
          <div style={{ padding: '0 24px', maxHeight: '75vh', overflowY: 'auto' }} className="custom-scrollbar">
            {checklist.map((item) => (
              <div key={item.id} style={{ 
                display: 'flex', alignItems: 'center', padding: '10px 0', /* Reduzi o padding drasticamente */
                borderBottom: '1px solid var(--border)',
                opacity: (item.status_manual === 1 || (item.tipo === 'AUTO' && item.concluidas === item.total && item.total > 0)) ? 0.6 : 1 
              }}>
                <div style={{ marginRight: '16px' }}>
                  <button 
                    onClick={() => handleToggle(item)}
                    style={{ background: 'none', border: 'none', cursor: item.tipo === 'MANUAL' ? 'pointer' : 'default', padding: 0, display: 'flex' }}
                  >
                    {(item.status_manual === 1 || (item.tipo === 'AUTO' && item.concluidas === item.total && item.total > 0)) ? 
                      <CheckCircle2 size={20} color="#10b981" fill="#d1fae5" /> : /* Reduzi o icone */
                      <Circle size={20} color="#cbd5e1" />
                    }
                  </button>
                </div>

                <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '2px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <span style={{ fontWeight: 600, color: 'var(--text-main)', fontSize: '0.8rem' }}>{item.tarefa_nome}</span> {/* Fonte Menor */}
                      {item.tipo === 'AUTO' && (
                        <span style={{ display: 'flex', alignItems: 'center', gap: '4px', fontSize: '0.55rem', background: 'var(--primary-light)', color: 'var(--primary)', padding: '2px 6px', borderRadius: '99px', fontWeight: 800 }}>
                          <Bot size={10} /> GESTTA
                        </span>
                      )}
                    </div>
                    
                    {item.tipo === 'MANUAL' && item.status_manual === 1 && item.usuario_conclusao && (
                      <div style={{ fontSize: '0.65rem', color: 'var(--text-muted)', fontWeight: 500 }}>
                        Por <span style={{ color: '#10b981', fontWeight: 700 }}>{item.usuario_conclusao.split(' ')[0]}</span> em {item.data_conclusao?.split(' ')[0].split('-').reverse().join('/')} às {item.data_conclusao?.split(' ')[1]}
                      </div>
                    )}
                    
                    {item.tipo === 'AUTO' && (
                      <div style={{ width: '100%', maxWidth: '200px', height: '4px', background: '#e2e8f0', borderRadius: '2px', overflow: 'hidden', marginTop: '2px' }}>
                        <div style={{ 
                            width: `${item.total > 0 ? (item.concluidas / item.total) * 100 : 0}%`, 
                            height: '100%', background: item.concluidas === item.total && item.total > 0 ? '#10b981' : 'var(--primary)', transition: 'width 0.5s ease'
                        }} />
                      </div>
                    )}
                </div>

                <div style={{ fontSize: '0.75rem', fontWeight: 800, color: 'var(--text-muted)', textAlign: 'right', minWidth: '80px' }}>
                  {item.tipo === 'AUTO' ? `${item.concluidas} / ${item.total}` : (item.status_manual === 1 ? 'CONCLUÍDO' : 'PENDENTE')}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

    </div>
  );
}
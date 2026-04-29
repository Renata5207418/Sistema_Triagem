import React, { useState, useEffect } from 'react';
import api from '../services/api';
import { AlertTriangle, CheckCircle, Calendar, ChevronDown, ChevronUp, RefreshCw, Circle, UserCheck } from 'lucide-react';
import DatePicker, { registerLocale } from "react-datepicker";
import "react-datepicker/dist/react-datepicker.css";
import { ptBR } from "date-fns/locale"; 
import { useAuth } from '../context/AuthContext';

registerLocale("pt-BR", ptBR);

// Componente da Sub-tabela (AGORA COM A COLUNA DE OS)
const DetalhesNotas = ({ codEmpresa, competencia }: { codEmpresa: string, competencia: string }) => {
  const [notas, setNotas] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const carregarDetalhes = () => {
      api.get(`/api/malha-fiscal/detalhes/${codEmpresa}/${competencia}`)
        .then(res => {
          setNotas(res.data);
          setLoading(false);
        })
        .catch(() => setLoading(false));
    };

    carregarDetalhes();

    const intervalo = window.setInterval(() => {
      carregarDetalhes();
    }, 30000);

    return () => {
      window.clearInterval(intervalo);
    };
  }, [codEmpresa, competencia]);

  if (loading) return <div style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-muted)' }}>Carregando notas...</div>;

  return (
    <div style={{ padding: '16px 24px 24px 64px', background: '#f8fafc', borderBottom: '1px solid var(--border)' }}>
      <div style={{ borderLeft: '2px solid var(--border)', paddingLeft: '24px' }}>
        <table className="sub-table" style={{ width: '100%' }}>
          <thead>
            <tr>
              <th style={{ textAlign: 'left', width: '120px' }}>Número NF</th>
              <th style={{ textAlign: 'left' }}>Prestador (CNPJ)</th>
              <th style={{ textAlign: 'right', width: '120px' }}>Valor Portal</th>
              <th style={{ textAlign: 'right', width: '120px' }}>Valor Onvio</th>
              <th style={{ textAlign: 'center', width: '100px' }}>OS Onvio</th> {/* NOVA COLUNA AQUI */}
              <th style={{ textAlign: 'center', width: '150px' }}>Status</th>
            </tr>
          </thead>
          <tbody>
            {notas.map(nota => (
              <tr key={nota.id} className="sub-table-row" style={{ 
                background: nota.status_conciliacao === 'FALTA_NO_TRIABOT' ? '#fef2f2' : 
                            nota.status_conciliacao === 'DIVERGENCIA_VALOR' ? '#fffbeb' : 
                            nota.status_conciliacao === 'NOTA_FANTASMA_TRIABOT' ? '#f0fdf4' : 'transparent' 
              }}>
                <td style={{ fontWeight: 700, color: 'var(--text-main)' }}>#{nota.numero_nota}</td>
                <td style={{ color: 'var(--text-muted)' }}>{nota.cnpj_prestador}</td>
                <td style={{ textAlign: 'right', fontWeight: 600 }}>
                  {nota.origem === 'TRIABOT' ? '---' : nota.valor_nota.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })}
                </td>
                <td style={{ textAlign: 'right', color: nota.status_conciliacao === 'DIVERGENCIA_VALOR' ? '#d97706' : 'inherit' }}>
                  {nota.status_conciliacao === 'FALTA_NO_TRIABOT' ? '---' : 
                   (nota.status_conciliacao === 'NOTA_FANTASMA_TRIABOT' || nota.status_conciliacao === 'BATEU') ? nota.valor_nota.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' }) : '---'}
                </td>
                
                {/* DADO DA OS AQUI */}
                <td style={{ textAlign: 'center', fontWeight: 700, color: 'var(--primary)' }}>
                  {nota.os_onvio ? `#${nota.os_onvio}` : '---'}
                </td>

                <td style={{ textAlign: 'center' }}>
                    {nota.status_conciliacao === 'FALTA_NO_TRIABOT' && <span style={{ color: '#ef4444', fontWeight: 700, fontSize: '0.7rem' }}>FALTA NO ONVIO</span>}
                    {nota.status_conciliacao === 'DIVERGENCIA_VALOR' && <span style={{ color: '#f59e0b', fontWeight: 700, fontSize: '0.7rem' }}>DIVERGENTE</span>}
                    {nota.status_conciliacao === 'NOTA_FANTASMA_TRIABOT' && <span style={{ color: '#10b981', fontWeight: 700, fontSize: '0.7rem' }}>SÓ NO ONVIO</span>}
                    {nota.status_conciliacao === 'BATEU' && <span style={{ color: '#10b981', fontWeight: 700, fontSize: '0.7rem' }}>OK</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default function MalhaFiscal() {
  const { user } = useAuth(); 
  const [mesFiltro, setMesFiltro] = useState(() => {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
  });
  
  const [clientes, setClientes] = useState<any[]>([]);
  const [expandedCliente, setExpandedCliente] = useState<string | null>(null);
  const [syncing, setSyncing] = useState<string | null>(null);
  const [toast, setToast] = useState<{ text: string, type: 'success' | 'error' } | null>(null);
  const [activeTab, setActiveTab] = useState<'pendentes' | 'concluidas'>('pendentes');

  const showToast = (text: string, type: 'success' | 'error') => {
    setToast({ text, type });
    setTimeout(() => setToast(null), 3500); 
  };

  const carregarResumo = () => {
    api.get(`/api/malha-fiscal/resumo/${mesFiltro}`)
      .then(res => setClientes(res.data))
      .catch(err => console.error(err));
  };

  useEffect(() => {
    carregarResumo();

    const intervalo = window.setInterval(() => {
      carregarResumo();
    }, 30000); // atualiza a cada 30 segundos

    return () => {
      window.clearInterval(intervalo);
    };
  }, [mesFiltro]);

  const handleSincronizar = async (codEmpresa: string) => {
    setSyncing(codEmpresa);
    try {
      await api.post(`/api/malha-fiscal/sincronizar/${codEmpresa}/${mesFiltro}`);
      showToast('Sincronização com AWS concluída!', 'success');
      carregarResumo();
      if (expandedCliente === codEmpresa) setExpandedCliente(null); 
    } catch (e: any) {
      const msgErro = e.response?.data?.detail || 'Erro ao sincronizar com AWS.';
      showToast(msgErro, 'error');
    }
    setSyncing(null);
  };

  const clientesFiltrados = clientes.filter(cli => {
    const isVerificado = Number(cli.verificado) === 1;
    if (activeTab === 'pendentes') return !isVerificado;
    return isVerificado;
  });

  const toggleValidacao = async (codEmpresa: string, atualVerificado: number) => {
    try {
      const isVerificado = Number(atualVerificado) === 1;
      
      if (isVerificado) {
        await api.put(`api/malha-fiscal/desmarcar/${codEmpresa}/${mesFiltro}`);
      } else {
        await api.put(`/api/malha-fiscal/validar/${codEmpresa}/${mesFiltro}`, {
          usuario: user?.full_name || 'Sistema'
        });
      }      
      setTimeout(() => {
        carregarResumo();
      }, 400);

    } catch (err) {
      showToast("Erro ao alterar validação.", 'error');
    }
  };

  return (
    <div className="page-container" style={{ position: 'relative' }}>
      
      {toast && (
        <div style={{
          position: 'fixed', bottom: '32px', right: '32px', zIndex: 9999,
          background: toast.type === 'error' ? '#fef2f2' : '#f0fdf4',
          color: toast.type === 'error' ? '#b91c1c' : '#15803d',
          padding: '16px 24px', borderRadius: '12px', 
          border: `1px solid ${toast.type === 'error' ? '#fca5a5' : '#86efac'}`,
          boxShadow: '0 10px 25px rgba(0,0,0,0.1)', 
          display: 'flex', alignItems: 'center', gap: '12px', fontWeight: 600, fontSize: '0.9rem',
          transition: 'all 0.3s'
        }}>
          {toast.type === 'error' ? <AlertTriangle size={20} /> : <CheckCircle size={20} />}
          {toast.text}
        </div>
      )}

      <div className="page-header-row" style={{ alignItems: 'flex-end' }}>
        <div>
          <h1 className="page-title">Auditoria de Tomados</h1>
          <p className="page-subtitle">Acompanhe as divergências entre o portal e os envios do onvio.</p>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', background: 'white', padding: '0 12px', borderRadius: '10px', border: '1px solid var(--border)', height: '42px' }}>
          <Calendar size={16} style={{ color: 'var(--primary)', marginRight: '8px' }} />
          <DatePicker
            selected={new Date(parseInt(mesFiltro.split('-')[0]), parseInt(mesFiltro.split('-')[1]) - 1, 1)}
            onChange={(date: Date | null) => {
              if (date) setMesFiltro(`${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`);
            }}
            dateFormat="MMMM yyyy"
            showMonthYearPicker
            locale="pt-BR"
            className="bg-transparent border-none font-bold text-sm text-[#3a3a3a] focus:ring-0 cursor-pointer uppercase outline-none w-32"
          />
        </div>
      </div>

      <div className="tabs-container">
        <button 
          className={`tab-item ${activeTab === 'pendentes' ? 'active' : ''}`}
          onClick={() => setActiveTab('pendentes')}
        >
          Pendentes de Validação ({clientes.filter(c => !c.verificado).length})
        </button>
        <button 
          className={`tab-item ${activeTab === 'concluidas' ? 'active' : ''}`}
          onClick={() => setActiveTab('concluidas')}
        >
          Validadas / Concluídas ({clientes.filter(c => c.verificado).length})
        </button>
      </div>

      <div className="table-card">
        <table className="modern-table">
          <thead>
            <tr>
              <th style={{ width: '48px' }}></th>
              <th style={{ width: '80px', textAlign: 'center' }}>Validar</th>
              <th>Cliente</th>
              <th style={{ textAlign: 'center', width: '120px' }}>Total Portal</th>
              <th style={{ textAlign: 'center', width: '120px' }}>Total Onvio</th>
              <th style={{ textAlign: 'center', width: '180px' }}>Status Geral</th>
              <th style={{ textAlign: 'center', width: '120px' }}>Ações</th>
            </tr>
          </thead>
          <tbody>
            {clientesFiltrados.length === 0 ? (
              <tr><td colSpan={7} style={{ textAlign: 'center', padding: '3rem', color: 'var(--text-muted)' }}>Nenhuma auditoria encontrada nesta aba.</td></tr>
            ) : clientesFiltrados.map((cli) => { 
              const temErro = cli.qtd_faltantes > 0 || cli.qtd_divergentes > 0;
              
              return (
                <React.Fragment key={cli.cod_empresa}>
                  <tr style={{ background: 'white', borderBottom: expandedCliente === cli.cod_empresa ? 'none' : '1px solid #f1f5f9' }}>
                    <td style={{ textAlign: 'center' }}>
                      <button className="btn-expand" onClick={() => setExpandedCliente(expandedCliente === cli.cod_empresa ? null : cli.cod_empresa)}>
                        {expandedCliente === cli.cod_empresa ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
                      </button>
                    </td>
                    
                    <td style={{ textAlign: 'center' }}>
                      <button 
                        onClick={() => toggleValidacao(cli.cod_empresa, cli.verificado)}
                        className={`check-btn ${cli.verificado ? 'checked' : ''}`}
                        style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', width: '100%' }}
                      >
                        {cli.verificado ? <CheckCircle size={26} fill="#dcfce7" /> : <Circle size={26} />}
                      </button>
                    </td>

                    <td>
                      <div style={{ fontWeight: 700, color: 'var(--text-main)', fontSize: '0.85rem' }}>{cli.nome_empresa}</div>
                      <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: '12px' }}>
                        <span>Cód: {cli.cod_empresa}</span>
                        {cli.verificado === 1 && cli.auditado_por && (
                          <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', color: '#16a34a', fontWeight: 600 }}>
                            <UserCheck size={12} /> Validado por {cli.auditado_por.split(' ')[0]}
                          </span>
                        )}
                      </div>
                    </td>
                    
                    <td style={{ textAlign: 'center', fontWeight: '800', color: 'var(--text-muted)' }}>{cli.total_aws}</td>
                    <td style={{ textAlign: 'center', fontWeight: '800', color: 'var(--text-muted)' }}>{cli.total_triabot}</td>
                    
                    <td style={{ textAlign: 'center' }}>
                      {temErro ? (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', alignItems: 'center' }}>
                          {cli.qtd_faltantes > 0 && <span className="status-badge status-erro" style={{ fontSize: '0.65rem' }}>{cli.qtd_faltantes} Faltantes</span>}
                          {cli.qtd_divergentes > 0 && <span className="status-badge status-pendente" style={{ fontSize: '0.65rem' }}>{cli.qtd_divergentes} Divergências</span>}
                        </div>
                      ) : (
                        <span className="status-badge status-ok"><CheckCircle size={12} style={{ marginRight: '4px' }}/> 100% Ok</span>
                      )}
                    </td>

                    <td style={{ textAlign: 'center' }}>
                      <button 
                        onClick={() => handleSincronizar(cli.cod_empresa)}
                        disabled={syncing === cli.cod_empresa}
                        className="action-btn-outline"
                      >
                        <RefreshCw size={14} className={syncing === cli.cod_empresa ? "spin" : ""} /> Sync AWS
                      </button>
                    </td>
                  </tr>

                  {expandedCliente === cli.cod_empresa && (
                    <tr>
                      <td colSpan={7} style={{ padding: 0 }}>
                        <DetalhesNotas codEmpresa={cli.cod_empresa} competencia={mesFiltro} />
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
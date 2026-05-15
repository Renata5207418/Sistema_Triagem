import React, { useState, useEffect } from 'react';
import api from '../services/api';
import { 
  AlertTriangle, CheckCircle, Calendar, ChevronDown, ChevronUp, 
  RefreshCw, Circle, UserCheck, ChevronLeft, ChevronRight, Search 
} from 'lucide-react';
import DatePicker, { registerLocale } from "react-datepicker";
import "react-datepicker/dist/react-datepicker.css";
import { ptBR } from "date-fns/locale"; 
import { useAuth } from '../context/AuthContext';

registerLocale("pt-BR", ptBR);

// Componente da Sub-tabela
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
              <th style={{ textAlign: 'center', color: 'var(--primary)', width: '100px' }}>OS Onvio</th>
              <th style={{ textAlign: 'center', width: '150px' }}>Origem</th>
            </tr>
          </thead>
          <tbody>
            {notas.map(nota => {
              const rowStyle = nota.status_conciliacao === 'FALTA_NO_TRIABOT' ? { background: '#f8fafc', color: '#475569' } : 
                               nota.status_conciliacao === 'DIVERGENCIA_VALOR' ? { background: '#f1f5f9', color: '#334155' } : 
                               nota.status_conciliacao === 'NOTA_FANTASMA_TRIABOT' ? { background: '#f8fafc', color: '#475569' } : { background: 'transparent' };

              return (
                <tr key={nota.id} className="sub-table-row" style={rowStyle}>
                  <td style={{ fontWeight: 700, color: 'var(--text-main)' }}>#{nota.numero_nota}</td>
                  <td style={{ color: 'var(--text-muted)' }}>{nota.cnpj_prestador}</td>
                  <td style={{ textAlign: 'right', fontWeight: 600 }}>
                    {nota.origem === 'TRIABOT' ? '---' : nota.valor_nota.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })}
                  </td>
                  <td style={{ textAlign: 'right', color: nota.status_conciliacao === 'DIVERGENCIA_VALOR' ? '#b45309' : 'inherit' }}>
                    {nota.status_conciliacao === 'FALTA_NO_TRIABOT' ? '---' : 
                     (nota.status_conciliacao === 'NOTA_FANTASMA_TRIABOT' || nota.status_conciliacao === 'BATEU' || nota.status_conciliacao === 'DIVERGENCIA_VALOR') ? nota.valor_nota.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' }) : '---'}
                  </td>
                  
                  <td style={{ textAlign: 'center', fontWeight: 800, color: 'var(--primary)' }}>
                    {nota.os_onvio ? `#${nota.os_onvio}` : '---'}
                  </td>

                  <td style={{ textAlign: 'center' }}>
                      {nota.status_conciliacao === 'FALTA_NO_TRIABOT' && <span style={{ color: '#1d4ed8', fontWeight: 800, fontSize: '0.65rem', padding: '4px 10px', background: '#dbeafe', borderRadius: '6px', letterSpacing: '0.02em' }}>SÓ PORTAL AWS</span>}
                      {nota.status_conciliacao === 'DIVERGENCIA_VALOR' && <span style={{ color: '#b45309', fontWeight: 800, fontSize: '0.65rem', padding: '4px 10px', background: '#fef3c7', borderRadius: '6px', letterSpacing: '0.02em' }}>AMBOS (Divergente)</span>}
                      {nota.status_conciliacao === 'NOTA_FANTASMA_TRIABOT' && <span style={{ color: '#c2410c', fontWeight: 800, fontSize: '0.65rem', padding: '4px 10px', background: '#ffedd5', borderRadius: '6px', letterSpacing: '0.02em' }}>SÓ ONVIO</span>}
                      {nota.status_conciliacao === 'BATEU' && <span style={{ color: '#15803d', fontWeight: 800, fontSize: '0.65rem', padding: '4px 10px', background: '#dcfce7', borderRadius: '6px', letterSpacing: '0.02em' }}>AMBOS (Bateu)</span>}
                  </td>
                </tr>
              )
            })}
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
  const [busca, setBusca] = useState(''); // Estado para o campo de busca
  
  // Estados para as Sincronizações
  const [syncing, setSyncing] = useState<string | null>(null);
  const [syncingAll, setSyncingAll] = useState(false);
  const [syncProgress, setSyncProgress] = useState({ current: 0, total: 0 });
  
  const [toast, setToast] = useState<{ text: string, type: 'success' | 'error' } | null>(null);
  const [activeTab, setActiveTab] = useState<'pendentes' | 'concluidas'>('pendentes');

  // === ESTADOS DA PAGINAÇÃO ===
  const [currentPage, setCurrentPage] = useState(1);
  const itemsPerPage = 15;

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
    }, 30000);

    return () => {
      window.clearInterval(intervalo);
    };
  }, [mesFiltro]);

  // Resetar para página 1 sempre que o filtro de busca, aba ou mês mudar
  useEffect(() => {
    setCurrentPage(1);
  }, [activeTab, mesFiltro, busca]);

  const handleSincronizar = async (codEmpresa: string, mostrarAviso: boolean = true) => {
    setSyncing(codEmpresa);

    try {
      await api.post(`/api/malha-fiscal/sincronizar/${codEmpresa}/${mesFiltro}`);
      if (mostrarAviso) showToast('AWS atualizada com sucesso!', 'success');
      
      if (mostrarAviso) carregarResumo();

      if (expandedCliente === codEmpresa) {
        setExpandedCliente(null);
      }
    } catch (e: any) {
      if (mostrarAviso) {
        const msgErro = e.response?.data?.detail || 'Erro ao atualizar AWS.';
        showToast(msgErro, 'error');
      }
      throw e; 
    } finally {
      setSyncing(null);
    }
  };

  const handleSincronizarTodos = async () => {
    const clientesAlvo = clientesFiltrados; // Sincroniza apenas o que está filtrado na tela

    if (clientesAlvo.length === 0) return;

    setSyncingAll(true);
    setSyncProgress({ current: 0, total: clientesAlvo.length });
    let errosCount = 0;

    for (let i = 0; i < clientesAlvo.length; i++) {
      setSyncProgress({ current: i + 1, total: clientesAlvo.length });
      try {
        await handleSincronizar(clientesAlvo[i].cod_empresa, false);
      } catch (error) {
        errosCount++;
      }
    }

    setSyncingAll(false);
    carregarResumo(); 

    if (errosCount > 0) {
      showToast(`Concluído, mas ${errosCount} cliente(s) falharam na atualização.`, 'error');
    } else {
      showToast('Todos os clientes atualizados com sucesso!', 'success');
    }
  };

  // Lógica de filtro: ABA + BUSCA (Nome ou Código)
  const clientesFiltrados = clientes.filter(cli => {
    const isVerificado = Number(cli.verificado) === 1;
    const matchesTab = activeTab === 'pendentes' ? !isVerificado : isVerificado;
    
    const matchesBusca = 
        cli.nome_empresa.toLowerCase().includes(busca.toLowerCase()) ||
        cli.cod_empresa.toString().includes(busca);

    return matchesTab && matchesBusca;
  });

  // === LÓGICA DE FATIAMENTO DA PAGINAÇÃO ===
  const totalPages = Math.ceil(clientesFiltrados.length / itemsPerPage);
  const currentClientes = clientesFiltrados.slice((currentPage - 1) * itemsPerPage, currentPage * itemsPerPage);

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

      <div className="page-header-row" style={{ alignItems: 'flex-end', flexWrap: 'wrap', gap: '16px', marginBottom: '24px' }}>
        <div style={{ flex: 1, minWidth: '300px' }}>
          <h1 className="page-title">Auditoria de Tomados</h1>
          <p className="page-subtitle">Verifique as notas extraídas pelo robô em relação ao portal AWS.</p>
        </div>

        <div style={{ display: 'flex', gap: '12px', alignItems: 'center', flexWrap: 'wrap' }}>
          
          {/* BARRA DE BUSCA */}
          <div style={{ 
            display: 'flex', 
            alignItems: 'center', 
            background: 'white', 
            padding: '0 12px', 
            borderRadius: '10px', 
            border: '1px solid var(--border)', 
            height: '42px',
            width: '280px' 
          }}>
            <Search size={16} style={{ color: 'var(--text-muted)', marginRight: '8px' }} />
            <input 
              type="text"
              placeholder="Buscar cliente ou código..."
              value={busca}
              onChange={(e) => setBusca(e.target.value)}
              style={{
                border: 'none',
                outline: 'none',
                fontSize: '0.85rem',
                width: '100%',
                fontWeight: 500,
                background: 'transparent'
              }}
            />
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

          <button 
            onClick={handleSincronizarTodos}
            disabled={syncingAll || clientesFiltrados.length === 0}
            style={{ 
              display: 'flex', alignItems: 'center', gap: '8px', 
              height: '42px', padding: '0 20px', 
              background: syncingAll ? '#94a3b8' : 'var(--primary)', 
              color: 'white', border: 'none', borderRadius: '10px', 
              fontWeight: 700, fontSize: '0.85rem', cursor: (syncingAll || clientesFiltrados.length === 0) ? 'not-allowed' : 'pointer',
              transition: 'background 0.2s'
            }}
          >
            <RefreshCw size={16} className={syncingAll ? "spin" : ""} />
            {syncingAll ? `Atualizando (${syncProgress.current}/${syncProgress.total})` : "Atualizar Todos"}
          </button>
        </div>
      </div>

      <div className="tabs-container">
        <button 
          className={`tab-item ${activeTab === 'pendentes' ? 'active' : ''}`}
          onClick={() => setActiveTab('pendentes')}
        >
          Revisão Pendente ({clientes.filter(c => !c.verificado).length})
        </button>
        <button 
          className={`tab-item ${activeTab === 'concluidas' ? 'active' : ''}`}
          onClick={() => setActiveTab('concluidas')}
        >
          Validadas ({clientes.filter(c => c.verificado).length})
        </button>
      </div>

      <div className="table-card">
        <table className="modern-table">
          <thead>
            <tr>
              <th style={{ width: '48px' }}></th>
              <th style={{ width: '80px', textAlign: 'center' }}>Validar</th>
              <th>Cliente</th>
              <th style={{ textAlign: 'center', width: '120px' }}>Qtd Portal</th>
              <th style={{ textAlign: 'center', width: '120px' }}>Qtd Onvio</th>
              <th style={{ textAlign: 'center', width: '180px' }}>Resumo</th>
              <th style={{ textAlign: 'center', width: '120px' }}>Ações</th>
            </tr>
          </thead>
          <tbody>
            {currentClientes.length === 0 ? (
              <tr><td colSpan={7} style={{ textAlign: 'center', padding: '3rem', color: 'var(--text-muted)' }}>Nenhum resultado encontrado.</td></tr>
            ) : currentClientes.map((cli) => { 
              const temDiferenca = cli.qtd_faltantes > 0 || cli.qtd_divergentes > 0 || cli.qtd_fantasmas > 0;
              
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
                      <div style={{ fontWeight: 700, color: 'var(--text-main)', fontSize: '0.85rem' }}>
                        {cli.nome_empresa}
                      </div>

                      <div
                        style={{
                          fontSize: '0.75rem',
                          color: 'var(--text-muted)',
                          display: 'flex',
                          alignItems: 'center',
                          gap: '12px',
                          flexWrap: 'wrap'
                        }}
                      >
                        <span>Cód: {cli.cod_empresa}</span>

                        <span>
                          Última AWS:{" "}
                          {cli.ultima_sincronizacao
                            ? new Date(cli.ultima_sincronizacao.replace(" ", "T")).toLocaleString("pt-BR")
                            : "não atualizada"}
                        </span>

                        {cli.verificado === 1 && cli.auditado_por && (
                          <span
                            style={{
                              display: 'inline-flex',
                              alignItems: 'center',
                              gap: '4px',
                              color: '#16a34a',
                              fontWeight: 600
                            }}
                          >
                            <UserCheck size={12} /> Validado por {cli.auditado_por.split(' ')[0]}
                          </span>
                        )}
                      </div>
                    </td>
                    
                    <td style={{ textAlign: 'center', fontWeight: '800', color: 'var(--text-muted)' }}>{cli.total_aws}</td>
                    <td style={{ textAlign: 'center', fontWeight: '800', color: 'var(--text-muted)' }}>{cli.total_triabot}</td>
                    
                    <td style={{ textAlign: 'center' }}>
                      {temDiferenca ? (
                        <span style={{ fontSize: '0.75rem', color: '#64748b', fontWeight: 600 }}>Visualizar notas</span>
                      ) : (
                        <span style={{ fontSize: '0.75rem', color: '#94a3b8', fontWeight: 600 }}>Sem diferenças</span>
                      )}
                    </td>

                    <td style={{ textAlign: 'center' }}>
                      <button 
                        onClick={() => handleSincronizar(cli.cod_empresa)}
                        disabled={syncing === cli.cod_empresa || syncingAll}
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

      {/* RENDERIZAÇÃO DA PAGINAÇÃO */}
      <div className="pagination-container" style={{ marginTop: '1rem' }}>
        <span style={{ fontSize: '0.8rem' }}>Página <strong>{currentPage}</strong> de <strong>{totalPages || 1}</strong></span>
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
  );
}
import { useState, useEffect } from 'react'
import axios from 'axios'
import { FileSearch, HardDrive } from 'lucide-react'

export default function Dashboard() {
  const [resumo, setResumo] = useState({ total_processado: 0, sucesso_triagem: 0, erros_atencao: 0, pendente_senha: 0 })

  useEffect(() => {
    axios.get('http://127.0.0.1:8000/api/resumo')
      .then(res => setResumo(res.data))
      .catch(err => console.error("API falhou", err))
  }, [])

  return (
    <div>
      <header style={{ marginBottom: '2.5rem' }}>
        <h2 style={{ fontSize: '1.8rem', fontWeight: 'bold' }}>Painel Executivo</h2>
        <p style={{ color: 'var(--text-muted)' }}>Controle mensal da esteira (Abril 2026).</p>
      </header>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '1.5rem' }}>
        <div className="card" style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
          <div style={{ padding: '12px', background: 'var(--primary-light)', color: 'var(--primary)', borderRadius: '12px' }}><HardDrive size={24} /></div>
          <div><p style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>Solicitações (Mês)</p><p style={{ fontSize: '1.8rem', fontWeight: 'bold' }}>{resumo.total_processado}</p></div>
        </div>
        <div className="card" style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
           <div style={{ padding: '12px', background: '#dcfce7', color: '#166534', borderRadius: '12px' }}><FileSearch size={24} /></div>
           <div><p style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>Sucesso Triagem</p><p style={{ fontSize: '1.8rem', fontWeight: 'bold' }}>{resumo.sucesso_triagem}</p></div>
        </div>
        <div className="card" style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
           <div style={{ padding: '12px', background: '#fee2e2', color: '#991b1b', borderRadius: '12px' }}><FileSearch size={24} /></div>
           <div><p style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>Pendências/Erros</p><p style={{ fontSize: '1.8rem', fontWeight: 'bold' }}>{resumo.erros_atencao}</p></div>
        </div>
        <div className="card" style={{ display: 'flex', alignItems: 'center', gap: '1rem', borderLeft: '4px solid var(--primary)' }}>
           <div><p style={{ fontSize: '0.85rem', color: 'var(--primary)', fontWeight: 'bold' }}>EMPRESAS ATIVAS</p><p style={{ fontSize: '1.8rem', fontWeight: 'bold' }}>86</p></div>
        </div>
      </div>
    </div>
  )
}
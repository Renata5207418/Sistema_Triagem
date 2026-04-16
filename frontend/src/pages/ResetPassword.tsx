import React, { useState, useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import api from '../services/api';
import { Lock, CheckCircle, ArrowRight } from 'lucide-react';

export const ResetPassword = () => {
  const [searchParams] = useSearchParams();
  const token = searchParams.get('token'); 
  const navigate = useNavigate();

  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState(false);

  useEffect(() => {
    if (!token) {
      setError("Link de recuperação inválido ou ausente. Por favor, solicite um novo e-mail.");
    }
  }, [token]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    if (password !== confirmPassword) {
      setError('As senhas não coincidem.');
      return;
    }
    if (password.length < 6) {
      setError('A senha deve ter no mínimo 6 caracteres.');
      return;
    }

    setLoading(true);
    try {
      await api.post('/auth/reset-password', { token, new_password: password });
      setSuccess(true);
      setTimeout(() => navigate('/login'), 3000);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Erro ao redefinir a senha.');
    } finally {
      setLoading(false);
    }
  };

  const inputClass = "w-full pl-10 pr-4 py-3 bg-gray-50 border border-transparent rounded-xl outline-none focus:bg-white focus:border-indigo-200 focus:ring-2 focus:ring-indigo-100 transition-all text-sm font-semibold placeholder:text-gray-300 text-gray-700";

  return (
    <div className="min-h-screen flex items-center justify-center bg-[#f3f4f6] px-4 font-['Inter',sans-serif]">
      <div className="flex w-full max-w-[850px] bg-white rounded-[35px] shadow-2xl overflow-hidden min-h-[520px]">
        
        {/* LADO ESQUERDO */}
        <div 
          className="hidden md:flex flex-col items-center justify-center w-1/2 bg-[#18181b] p-10 text-center"
          style={{ borderRight: '8px solid var(--primary)' }}
        >
          <img src="/triabot.png" alt="Triagem Logo" className="w-full max-w-[160px] mb-8 drop-shadow-lg" />
          <div className="space-y-2">
            <h2 className="text-3xl font-bold text-white tracking-tight">Sistema Triagem</h2>
            <p className="text-xs uppercase font-black tracking-[0.3em]" style={{ color: 'var(--primary-light)' }}>Auditoria Inteligente</p>
          </div>
          <div className="mt-auto text-[10px] text-gray-500 font-bold uppercase tracking-widest">Acesso Seguro</div>
        </div>

        {/* LADO DIREITO */}
        <div className="flex flex-col justify-center w-full md:w-1/2 p-12 bg-white">
          <div className="mb-10">
            <h1 className="text-3xl font-bold text-[#27272a] mb-2 leading-tight">Nova Senha</h1>
            <p className="text-gray-400 text-sm font-medium">Crie uma senha forte e segura.</p>
          </div>

          {success ? (
            <div className="flex flex-col items-center justify-center text-center space-y-4 py-8">
              <CheckCircle size={64} className="text-green-500" />
              <h2 className="text-xl font-bold text-gray-800">Senha Alterada!</h2>
              <p className="text-sm text-gray-500">Redirecionando você para o login...</p>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="space-y-5">
              {error && <div className="bg-red-50 text-red-600 text-[11px] p-3 rounded-xl border border-red-100 font-bold text-center">{error}</div>}

              <div className="space-y-1">
                <label className="text-[10px] uppercase font-black text-gray-400 ml-1 tracking-widest">Nova Senha</label>
                <div className="relative">
                  <Lock className="absolute left-3.5 top-1/2 -translate-y-1/2 text-gray-300" size={18} />
                  <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} className={inputClass} placeholder="••••••••" required disabled={!token} />
                </div>
              </div>

              <div className="space-y-1">
                <label className="text-[10px] uppercase font-black text-gray-400 ml-1 tracking-widest">Confirmar Senha</label>
                <div className="relative">
                  <Lock className="absolute left-3.5 top-1/2 -translate-y-1/2 text-gray-300" size={18} />
                  <input type="password" value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} className={inputClass} placeholder="••••••••" required disabled={!token} />
                </div>
              </div>

              <button 
                type="submit" 
                disabled={loading || !token} 
                className="w-full text-white py-4 rounded-2xl font-black text-xs uppercase tracking-widest transition-all flex items-center justify-center gap-2 mt-4 shadow-lg active:scale-95 disabled:opacity-50 disabled:cursor-not-allowed"
                style={{ background: 'var(--primary)' }}
              >
                {loading ? 'Salvando...' : 'Confirmar Alteração'}
                {!loading && <ArrowRight size={18} />}
              </button>
            </form>
          )}
        </div>
      </div>
    </div>
  );
};
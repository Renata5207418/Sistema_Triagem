import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import api from '../services/api';
import { Eye, EyeOff, Lock, Mail, UserPlus, ArrowLeft } from 'lucide-react'; 

type AuthMode = 'login' | 'signup' | 'forgot';

export const Login: React.FC = () => {
  const [mode, setMode] = useState<AuthMode>('login');
  const [formData, setFormData] = useState({ name: '', email: '', password: '' });
  const [error, setError] = useState('');
  const [success, setSuccess] = useState(''); // Estado para mensagens de sucesso
  const [loading, setLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const { login } = useAuth();
  const navigate = useNavigate();

  const inputVisual = "w-full bg-[#f8fafc] border border-[#e2e8f0] rounded-xl outline-none focus:bg-white focus:border-indigo-400 focus:ring-4 focus:ring-indigo-50 transition-all text-sm font-medium placeholder:text-gray-400 text-gray-700 login-input py-2";

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setFormData({ ...formData, [e.target.name]: e.target.value });
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setSuccess('');
    setLoading(true);

    try {
      if (mode === 'login') {
        const params = new URLSearchParams();
        // Mantemos 'username' na chave porque o FastAPI (OAuth2) exige esse nome de campo
        params.append('username', formData.email);
        params.append('password', formData.password);
        
        const { data } = await api.post('/auth/token', params, {
          headers: { 'Content-Type': 'application/x-www-form-urlencoded' }
        });
        login(data.access_token);
        navigate('/');
      } else if (mode === 'signup') {
        await api.post('/auth/signup', {
          username: formData.email, // O backend recebe o e-mail como username
          email: formData.email,
          password: formData.password,
          full_name: formData.name
        });
        
        setSuccess("Conta criada com sucesso! Redirecionando...");
        
        // Timer para dar tempo do usuário ler e trocar de tela sozinho
        setTimeout(() => {
          setSuccess('');
          setMode('login');
        }, 2500);

      } else {
        await api.post('/auth/forgot-password', { email: formData.email });
        setSuccess("Link enviado! Verifique sua caixa de entrada.");
        // Limpa o sucesso após 5 segundos
        setTimeout(() => setSuccess(''), 5000);
      }
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Erro ao processar solicitação.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-[#f1f5f9] px-4 font-['Inter',sans-serif]">
      <div className="flex w-full max-w-[850px] bg-white rounded-[32px] shadow-2xl overflow-hidden min-h-[520px]">
        
        {/* ESQUERDA: BANNER */}
        <div className="hidden md:flex flex-col items-center justify-center w-[45%] bg-[#313033] p-12 text-center relative" style={{ borderRight: '8px solid var(--primary)' }}>
          <div className="absolute w-40 h-40 bg-indigo-500/10 blur-[80px] rounded-full"></div>
          <img src="/triabot.png" alt="Logo" className="w-full max-w-[230px] mb-10 relative z-10" />
          <div className="space-y-2 relative z-10">
            <h2 className="text-3xl font-bold text-white tracking-tight">Sistema Triagem</h2>
            <p className="text-xs uppercase font-black tracking-[0.3em] opacity-80" style={{ color: 'var(--primary-light)' }}>Auditoria Inteligente</p>
          </div>   
        </div>

        {/* DIREITA: FORMULÁRIO */}
        <div className="flex flex-col justify-center items-center w-full md:w-[55%] p-8 md:p-12 bg-white">
          <div className="w-full max-w-[360px]"> 
            
            <div className="mb-8 text-left">
              <h1 className="text-3xl font-bold text-[#1e293b] mb-2">
                {mode === 'login' && 'Bem-vindo'}
                {mode === 'signup' && 'Nova Conta'}
                {mode === 'forgot' && 'Recuperar'}
              </h1>
              <p className="text-slate-400 text-sm font-medium">
                {mode === 'forgot' ? 'Insira seu e-mail corporativo.' : 'Acesse a esteira de auditoria fiscal.'}
              </p>
            </div>

            <form onSubmit={handleSubmit} className="login-form-container">
              {/* ÁREA DE FEEDBACK (ERRO E SUCESSO) */}
              {error && (
                <div className="bg-red-50 text-red-600 text-xs p-3 rounded-xl border border-red-100 font-bold text-center mb-4">
                  {error}
                </div>
              )}
              {success && (
                <div className="bg-emerald-50 text-emerald-600 text-xs p-3 rounded-xl border border-emerald-100 font-bold text-center mb-4">
                  {success}
                </div>
              )}

              {mode === 'signup' && (
                <div className="field-group">
                  <label className="text-[10px] uppercase font-bold text-slate-400 ml-1 tracking-widest">Nome Completo</label>
                  <div className="input-wrapper">
                    <UserPlus className="input-icon-left" size={18} />
                    <input name="name" type="text" className={inputVisual} placeholder="Seu nome" onChange={handleInputChange} required />
                  </div>
                </div>
              )}

              <div className="field-group">
                <label className="text-[10px] uppercase font-bold text-slate-400 ml-1 tracking-widest">E-mail Corporativo</label>
                <div className="input-wrapper">
                  <Mail className="input-icon-left" size={18} />
                  <input name="email" type="email" className={inputVisual} placeholder="email@scryta.com.br" onChange={handleInputChange} required />
                </div>
              </div>

              {mode !== 'forgot' && (
                <div className="field-group">
                  <div className="flex justify-between items-center">
                    <label className="text-[10px] uppercase font-bold text-slate-400 ml-1 tracking-widest">Senha</label>
                    {mode === 'login' && (
                      <button type="button" onClick={() => setMode('forgot')} className="text-[10px] font-bold text-primary hover:underline tracking-widest">Esqueci a senha</button>
                    )}
                  </div>
                  <div className="input-wrapper">
                    <Lock className="input-icon-left" size={18} />
                    <input
                      name="password"
                      type={showPassword ? "text" : "password"}
                      value={formData.password}
                      onChange={handleInputChange}
                      className={inputVisual}
                      placeholder="••••••••"
                      required
                    />
                    <button type="button" onClick={() => setShowPassword(!showPassword)} className="input-icon-right">
                      {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                    </button>
                  </div>
                </div>
              )}

              <button 
                type="submit" 
                disabled={loading} 
                className="w-full text-white h-[44px] rounded-xl font-bold text-xs uppercase tracking-widest transition-all shadow-md active:scale-[0.98] disabled:opacity-70 flex items-center justify-center mt-2" 
                style={{ background: 'var(--primary)' }}
              >
                {loading ? 'Processando...' : 
                 mode === 'login' ? 'Entrar no Sistema' : 
                 mode === 'signup' ? 'Criar minha conta' : 'Enviar Link'}
              </button>
            </form>

            <div className="mt-10 text-center border-t border-slate-100 pt-6">
              <p className="text-xs text-slate-400 font-medium">
                {mode === 'login' ? (
                  <>Novo por aqui? <button onClick={() => setMode('signup')} style={{ color: 'var(--primary)' }} className="font-bold hover:underline">Crie sua conta</button></>
                ) : (
                  <button onClick={() => setMode('login')} className="font-bold flex items-center justify-center gap-2 mx-auto hover:text-slate-800 transition-colors">
                    <ArrowLeft size={16} /> Voltar para o Login
                  </button>
                )}
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
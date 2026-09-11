import React, { useState } from 'react';
import { useAppStore } from '@/store/useAppStore';
import { Flame, Info, User, Key, Eye, EyeOff, Terminal, Lock } from 'lucide-react';

export const Login: React.FC = () => {
  const login = useAppStore((s) => s.login);
  const [operatorId, setOperatorId] = useState('OP-98442');
  const [authToken, setAuthToken] = useState('FIREOPS-2026');
  const [showPassword, setShowPassword] = useState(false);

  const handleLogin = (e: React.FormEvent) => {
    e.preventDefault();
    login();
  };

  return (
    <div className="min-h-screen w-screen bg-[#070d1e] flex items-center justify-center relative overflow-hidden px-4 font-sans text-slate-100">
      
      {}
      <div 
        className="absolute inset-0 opacity-20 pointer-events-none"
        style={{
          backgroundImage: `
            radial-gradient(circle at 50% 50%, rgba(6, 182, 212, 0.15) 0%, transparent 60%),
            linear-gradient(to right, rgba(56, 189, 248, 0.05) 1px, transparent 1px),
            linear-gradient(to bottom, rgba(56, 189, 248, 0.05) 1px, transparent 1px)
          `,
          backgroundSize: '100% 100%, 40px 40px, 40px 40px',
        }}
      ></div>

      {}
      <div className="absolute -top-32 -left-32 w-96 h-96 bg-cyan-500/10 rounded-full blur-3xl pointer-events-none"></div>
      <div className="absolute -bottom-32 -right-32 w-96 h-96 bg-red-500/10 rounded-full blur-3xl pointer-events-none"></div>

      {}
      <main className="relative z-10 w-full max-w-md my-auto">
        <div className="w-full p-8 md:p-10 rounded-2xl bg-slate-900/80 border border-cyan-500/30 shadow-2xl backdrop-blur-xl shadow-cyan-950/50 flex flex-col items-center">
          
          {}
          <div className="mb-8 flex flex-col items-center text-center">
            <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-cyan-500 to-blue-600 p-0.5 shadow-lg shadow-cyan-500/30 mb-4 flex items-center justify-center">
              <div className="w-full h-full bg-slate-950 rounded-[14px] flex items-center justify-center">
                <Flame className="w-8 h-8 text-cyan-400" strokeWidth={2.5} />
              </div>
            </div>
            
            <h1 className="text-3xl font-extrabold tracking-wider text-slate-100 font-mono">
              FIREOPS<span className="text-cyan-400">.COMMAND</span>
            </h1>
            <p className="text-xs font-mono uppercase tracking-[0.25em] text-cyan-400/80 mt-1.5 font-semibold">
              Thermal Telemetry System
            </p>
          </div>

          {}
          <div className="w-full text-center mb-6">
            <h2 className="text-sm font-mono font-bold uppercase tracking-widest text-slate-300">
              Access Secure Terminal
            </h2>
            <div className="w-16 h-0.5 bg-gradient-to-r from-transparent via-cyan-400 to-transparent mx-auto mt-2"></div>
          </div>

          {}
          <div className="w-full mb-5 px-3.5 py-2 rounded-xl bg-cyan-950/40 border border-cyan-500/20 text-[11px] font-mono text-cyan-300 flex items-center justify-between">
            <span className="flex items-center gap-1.5">
              <Info className="w-4 h-4 text-cyan-400" />
              Demo Access:
            </span>
            <span className="text-slate-300 font-bold">OP-98442 / FIREOPS-2026</span>
          </div>

          {}
          <form className="w-full space-y-5" onSubmit={handleLogin}>
            
            {}
            <div className="space-y-1.5">
              <label 
                htmlFor="operator_id" 
                className="block text-xs font-mono font-bold uppercase tracking-wider text-cyan-300"
              >
                Operator ID
              </label>
              <div className="relative flex items-center">
                <User className="absolute left-3.5 text-slate-400 w-5 h-5 pointer-events-none" />
                <input 
                  id="operator_id" 
                  type="text" 
                  required
                  placeholder="OP-98442"
                  value={operatorId}
                  onChange={(e) => setOperatorId(e.target.value)}
                  className="w-full pl-11 pr-4 py-3 rounded-xl bg-slate-950/80 border border-slate-700 text-slate-100 placeholder-slate-500 font-mono text-sm focus:border-cyan-400 focus:ring-1 focus:ring-cyan-400 focus:outline-none transition-all duration-200"
                />
              </div>
            </div>

            {}
            <div className="space-y-1.5">
              <label 
                htmlFor="auth_token" 
                className="block text-xs font-mono font-bold uppercase tracking-wider text-cyan-300"
              >
                Authentication Token / Password
              </label>
              <div className="relative flex items-center">
                <Key className="absolute left-3.5 text-slate-400 w-5 h-5 pointer-events-none" />
                <input 
                  id="auth_token" 
                  type={showPassword ? "text" : "password"} 
                  required
                  placeholder="••••••••••••"
                  value={authToken}
                  onChange={(e) => setAuthToken(e.target.value)}
                  className="w-full pl-11 pr-11 py-3 rounded-xl bg-slate-950/80 border border-slate-700 text-slate-100 placeholder-slate-500 font-mono text-sm focus:border-cyan-400 focus:ring-1 focus:ring-cyan-400 focus:outline-none transition-all duration-200"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  aria-label={showPassword ? "Hide password" : "Show password"}
                  className="absolute right-3.5 text-slate-400 hover:text-cyan-400 transition-colors cursor-pointer flex items-center justify-center p-1 rounded focus:outline-none"
                >
                  <span className="material-symbols-outlined text-lg">
                    {showPassword ? 'visibility_off' : 'visibility'}
                  </span>
                </button>
              </div>
            </div>

            {}
            <button 
              type="submit"
              className="w-full mt-4 py-3.5 px-6 rounded-xl bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-400 hover:to-blue-500 text-slate-950 font-mono font-bold text-sm uppercase tracking-wider shadow-lg shadow-cyan-500/25 active:scale-[0.98] transition-all flex items-center justify-center gap-2 cursor-pointer"
            >
              <span className="material-symbols-outlined text-lg">
                terminal
              </span>
              Initialize Command Link
            </button>
          </form>

          {}
          <div className="mt-8 pt-4 border-t border-slate-800 w-full text-center">
            <p className="text-[11px] font-mono text-slate-400 uppercase tracking-wider flex items-center justify-center gap-1.5">
              <span className="material-symbols-outlined text-xs text-cyan-400">lock</span>
              Encrypted Channel • Vigilance-Alpha-9
            </p>
          </div>

        </div>
      </main>
    </div>
  );
};

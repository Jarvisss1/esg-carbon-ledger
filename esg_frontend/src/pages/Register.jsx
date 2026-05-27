import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { Leaf, User, Mail, Lock, Building2, Eye, EyeOff, AlertCircle, CheckCircle, ArrowRight } from 'lucide-react';

const ORGANIZATIONS = [
  'Accenture', 'Air India', 'Airbus', 'Boeing', 'British Airways',
  'Deloitte', 'Emirates', 'Etihad Airways', 'ExxonMobil', 'Goldman Sachs',
  'HSBC', 'Infosys', 'IndiGo', 'JPMorgan Chase', 'KPMG',
  'McKinsey & Company', 'Microsoft', 'PwC', 'Reliance Industries',
  'Shell', 'Siemens', 'Tata Consultancy Services', 'Unilever',
  'Vistara', 'Other',
];

export default function Register() {
  const { register } = useAuth();
  const navigate = useNavigate();

  const [form, setForm] = useState({
    name: '', email: '', password: '', confirmPassword: '', organization: '', role: 'analyst',
  });
  const [showPwd, setShowPwd] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState(false);
  const [loading, setLoading] = useState(false);

  const handleChange = (e) => setForm({ ...form, [e.target.name]: e.target.value });

  const validate = () => {
    if (!form.name.trim()) return 'Full name is required.';
    if (!form.email.trim()) return 'Email is required.';
    if (form.password.length < 8) return 'Password must be at least 8 characters.';
    if (form.password !== form.confirmPassword) return 'Passwords do not match.';
    if (!form.organization) return 'Please select your organisation.';
    return null;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    const err = validate();
    if (err) { setError(err); return; }
    setError('');
    setLoading(true);
    try {
      await register({
        username: form.email,
        email: form.email,
        password: form.password,
        first_name: form.name.split(' ')[0],
        last_name: form.name.split(' ').slice(1).join(' '),
        organization: form.organization,
        role: form.role,
      });
      setSuccess(true);
      setTimeout(() => navigate('/login'), 2500);
    } catch (err) {
      const data = err?.response?.data;
      const msg = data?.email?.[0] || data?.username?.[0] || data?.password?.[0]
        || data?.detail || 'Registration failed. Please try again.';
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-4 relative overflow-hidden">
      <div className="absolute top-[-20%] right-[-10%] w-[500px] h-[500px] rounded-full bg-emerald-900/20 blur-[120px] pointer-events-none" />
      <div className="absolute bottom-[-20%] left-[-10%] w-[400px] h-[400px] rounded-full bg-emerald-800/10 blur-[120px] pointer-events-none" />

      <div className="w-full max-w-md animate-fade-in">
        {/* Logo */}
        <div className="flex flex-col items-center mb-8">
          <div className="w-14 h-14 rounded-2xl bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center mb-4 glow-emerald">
            <Leaf className="w-7 h-7 text-emerald-400" />
          </div>
          <h1 className="text-2xl font-bold text-white tracking-tight">ESG Carbon Ledger</h1>
          <p className="text-zinc-400 text-sm mt-1">Create your analyst account</p>
        </div>

        <div className="glass rounded-2xl p-8">
          <h2 className="text-lg font-semibold text-white mb-6">Create account</h2>

          {success && (
            <div className="flex items-center gap-2.5 bg-emerald-500/10 border border-emerald-500/20 rounded-xl p-3.5 mb-5">
              <CheckCircle className="w-4 h-4 text-emerald-400 shrink-0" />
              <p className="text-emerald-400 text-sm">Account created! Redirecting to login…</p>
            </div>
          )}

          {error && (
            <div className="flex items-center gap-2.5 bg-red-500/10 border border-red-500/20 rounded-xl p-3.5 mb-5">
              <AlertCircle className="w-4 h-4 text-red-400 shrink-0" />
              <p className="text-red-400 text-sm">{error}</p>
            </div>
          )}

          <form onSubmit={handleSubmit} className="flex flex-col gap-4">
            {/* Name */}
            <div className="flex flex-col gap-1.5">
              <label htmlFor="reg-name" className="text-zinc-400 text-xs font-medium uppercase tracking-wider">Full Name</label>
              <div className="relative">
                <User className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-500" />
                <input id="reg-name" type="text" name="name" placeholder="Jane Smith" value={form.name} onChange={handleChange} required
                  className="w-full bg-zinc-900/50 border border-zinc-800 rounded-xl pl-10 pr-4 py-3 text-sm text-zinc-100 placeholder:text-zinc-600 focus:outline-none focus:border-emerald-500/50 focus:ring-1 focus:ring-emerald-500/30 transition-all" />
              </div>
            </div>

            {/* Email */}
            <div className="flex flex-col gap-1.5">
              <label htmlFor="reg-email" className="text-zinc-400 text-xs font-medium uppercase tracking-wider">Work Email</label>
              <div className="relative">
                <Mail className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-500" />
                <input id="reg-email" type="email" name="email" placeholder="analyst@organisation.com" value={form.email} onChange={handleChange} required
                  className="w-full bg-zinc-900/50 border border-zinc-800 rounded-xl pl-10 pr-4 py-3 text-sm text-zinc-100 placeholder:text-zinc-600 focus:outline-none focus:border-emerald-500/50 focus:ring-1 focus:ring-emerald-500/30 transition-all" />
              </div>
            </div>

            {/* Organisation */}
            <div className="flex flex-col gap-1.5">
              <label htmlFor="reg-org" className="text-zinc-400 text-xs font-medium uppercase tracking-wider">Organisation</label>
              <div className="relative">
                <Building2 className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-500 pointer-events-none" />
                <select id="reg-org" name="organization" value={form.organization} onChange={handleChange} required
                  className="w-full bg-zinc-900/50 border border-zinc-800 rounded-xl pl-10 pr-4 py-3 text-sm text-zinc-100 focus:outline-none focus:border-emerald-500/50 focus:ring-1 focus:ring-emerald-500/30 transition-all appearance-none cursor-pointer">
                  <option value="" disabled className="text-zinc-600">Select organisation…</option>
                  {ORGANIZATIONS.map((o) => <option key={o} value={o} className="bg-zinc-900">{o}</option>)}
                </select>
              </div>
            </div>

            {/* Role */}
            <div className="flex flex-col gap-1.5">
              <label className="text-zinc-400 text-xs font-medium uppercase tracking-wider">Role</label>
              <div className="grid grid-cols-2 gap-2">
                {['analyst', 'manager'].map((r) => (
                  <label key={r}
                    className={`flex items-center gap-2.5 border rounded-xl px-4 py-3 cursor-pointer transition-all text-sm ${form.role === r ? 'border-emerald-500/50 bg-emerald-500/10 text-emerald-300' : 'border-zinc-800 bg-zinc-900/50 text-zinc-400 hover:border-zinc-700'}`}>
                    <input type="radio" name="role" value={r} checked={form.role === r} onChange={handleChange} className="sr-only" />
                    <div className={`w-4 h-4 rounded-full border-2 flex items-center justify-center ${form.role === r ? 'border-emerald-400' : 'border-zinc-600'}`}>
                      {form.role === r && <div className="w-2 h-2 rounded-full bg-emerald-400" />}
                    </div>
                    <span className="capitalize">{r}</span>
                  </label>
                ))}
              </div>
            </div>

            {/* Password */}
            <div className="flex flex-col gap-1.5">
              <label htmlFor="reg-password" className="text-zinc-400 text-xs font-medium uppercase tracking-wider">Password</label>
              <div className="relative">
                <Lock className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-500" />
                <input id="reg-password" type={showPwd ? 'text' : 'password'} name="password" placeholder="Min. 8 characters" value={form.password} onChange={handleChange} required
                  className="w-full bg-zinc-900/50 border border-zinc-800 rounded-xl pl-10 pr-12 py-3 text-sm text-zinc-100 placeholder:text-zinc-600 focus:outline-none focus:border-emerald-500/50 focus:ring-1 focus:ring-emerald-500/30 transition-all" />
                <button type="button" onClick={() => setShowPwd(!showPwd)} className="absolute right-3.5 top-1/2 -translate-y-1/2 text-zinc-500 hover:text-zinc-300 transition-colors">
                  {showPwd ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>

            {/* Confirm Password */}
            <div className="flex flex-col gap-1.5">
              <label htmlFor="reg-confirm" className="text-zinc-400 text-xs font-medium uppercase tracking-wider">Confirm Password</label>
              <div className="relative">
                <Lock className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-500" />
                <input id="reg-confirm" type={showConfirm ? 'text' : 'password'} name="confirmPassword" placeholder="Repeat password" value={form.confirmPassword} onChange={handleChange} required
                  className="w-full bg-zinc-900/50 border border-zinc-800 rounded-xl pl-10 pr-12 py-3 text-sm text-zinc-100 placeholder:text-zinc-600 focus:outline-none focus:border-emerald-500/50 focus:ring-1 focus:ring-emerald-500/30 transition-all" />
                <button type="button" onClick={() => setShowConfirm(!showConfirm)} className="absolute right-3.5 top-1/2 -translate-y-1/2 text-zinc-500 hover:text-zinc-300 transition-colors">
                  {showConfirm ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>

            <button id="register-submit-btn" type="submit" disabled={loading || success}
              className="mt-2 w-full bg-emerald-500 hover:bg-emerald-400 disabled:bg-emerald-500/40 disabled:cursor-not-allowed text-zinc-950 font-semibold rounded-xl py-3 flex items-center justify-center gap-2 transition-all duration-200 shadow-[0_0_20px_rgba(16,185,129,0.2)]">
              {loading ? <div className="w-4 h-4 border-2 border-zinc-950 border-t-transparent rounded-full animate-spin" /> : <><span>Create Account</span><ArrowRight className="w-4 h-4" /></>}
            </button>
          </form>

          <p className="text-center text-zinc-500 text-sm mt-6">
            Already have an account?{' '}
            <Link to="/login" className="text-emerald-400 hover:text-emerald-300 font-medium transition-colors">Sign in</Link>
          </p>
        </div>
      </div>
    </div>
  );
}

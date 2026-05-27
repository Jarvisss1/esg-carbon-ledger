import { useState, useEffect } from 'react';
import {
  AreaChart, Area, PieChart, Pie, Cell, ResponsiveContainer,
  Tooltip, XAxis, YAxis, CartesianGrid
} from 'recharts';
import { dashboardAPI, recordsAPI } from '../lib/api';
import { useAuth } from '../context/AuthContext';
import {
  Wind, AlertTriangle, CheckCircle2, FileStack,
  TrendingUp, ClipboardCheck, RefreshCw
} from 'lucide-react';

const SCOPE_COLORS = ['#10b981', '#34d399', '#6ee7b7'];

const MOCK_MONTHLY = [
  { month: 'Jan', tCO2e: 420 }, { month: 'Feb', tCO2e: 380 }, { month: 'Mar', tCO2e: 510 },
  { month: 'Apr', tCO2e: 460 }, { month: 'May', tCO2e: 390 }, { month: 'Jun', tCO2e: 530 },
  { month: 'Jul', tCO2e: 610 }, { month: 'Aug', tCO2e: 590 }, { month: 'Sep', tCO2e: 480 },
  { month: 'Oct', tCO2e: 520 }, { month: 'Nov', tCO2e: 440 }, { month: 'Dec', tCO2e: 470 },
];

const MOCK_SCOPES = [
  { name: 'Scope 1 (Direct)', value: 32, color: SCOPE_COLORS[0] },
  { name: 'Scope 2 (Indirect)', value: 28, color: SCOPE_COLORS[1] },
  { name: 'Scope 3 (Value Chain)', value: 40, color: SCOPE_COLORS[2] },
];

function StatCard({ icon: Icon, label, value, sub, color = 'emerald', trend }) {
  const colorMap = {
    emerald: 'bg-emerald-500/10 border-emerald-500/15 text-emerald-400',
    amber: 'bg-amber-500/10 border-amber-500/15 text-amber-400',
    blue: 'bg-blue-500/10 border-blue-500/15 text-blue-400',
    violet: 'bg-violet-500/10 border-violet-500/15 text-violet-400',
  };
  return (
    <div className="glass rounded-2xl p-5 flex flex-col gap-4 hover:border-zinc-700/50 transition-all group">
      <div className="flex items-start justify-between">
        <div className={`w-10 h-10 rounded-xl border flex items-center justify-center ${colorMap[color]}`}>
          <Icon className="w-5 h-5" />
        </div>
        {trend !== undefined && (
          <span className={`text-xs font-medium px-2 py-1 rounded-full ${trend >= 0 ? 'bg-emerald-500/10 text-emerald-400' : 'bg-red-500/10 text-red-400'}`}>
            {trend >= 0 ? '+' : ''}{trend}%
          </span>
        )}
      </div>
      <div>
        <p className="text-2xl font-bold text-white font-mono tracking-tight">{value}</p>
        <p className="text-sm text-zinc-400 mt-0.5">{label}</p>
        {sub && <p className="text-xs text-zinc-600 mt-1">{sub}</p>}
      </div>
    </div>
  );
}

const CustomTooltip = ({ active, payload, label }) => {
  if (active && payload?.length) {
    return (
      <div className="glass rounded-xl px-3.5 py-2.5 border border-zinc-700/50">
        <p className="text-xs text-zinc-400">{label}</p>
        <p className="text-sm font-semibold text-emerald-400">{payload[0].value} tCO₂e</p>
      </div>
    );
  }
  return null;
};

export default function Dashboard() {
  const { user } = useAuth();
  const [stats, setStats] = useState(null);
  const [assignments, setAssignments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const loadData = async () => {
    try {
      const [statsRes, assignmentsRes] = await Promise.all([
        dashboardAPI.stats(),
        recordsAPI.list({ approved: 'false', excluded: 'false', page_size: 5 })
      ]);
      
      const s = statsRes.data;
      setStats({
        total: s.total ?? 0,
        approved: s.approved ?? 0,
        flagged: s.flagged ?? 0,
        pending: s.pending ?? 0,
        totalTCO2e: (parseFloat(s.total_emissions_kgco2e ?? 0) / 1000).toFixed(1)
      });
      
      const myAssignments = assignmentsRes.data?.results || assignmentsRes.data || [];
      setAssignments(myAssignments);
    } catch {
      // use mock data on error
      setStats({ total: 312, approved: 218, flagged: 24, pending: 70, totalTCO2e: '5,847' });
      setAssignments([]);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => { loadData(); }, []);

  const refresh = () => { setRefreshing(true); loadData(); };

  return (
    <div className="p-8 space-y-8 animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white tracking-tight">
            Good to see you, {user?.first_name || 'Analyst'} 👋
          </h1>
          <p className="text-zinc-400 text-sm mt-1">{user?.organization || 'Your Organisation'} · Carbon Emissions Overview</p>
        </div>
        <button onClick={refresh} disabled={refreshing}
          className="flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-medium text-zinc-300 bg-zinc-800/50 hover:bg-zinc-700/50 border border-zinc-700/50 transition-all disabled:opacity-50">
          <RefreshCw className={`w-4 h-4 ${refreshing ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 xl:grid-cols-4 gap-4">
        <StatCard icon={Wind} label="Total tCO₂e" value={loading ? '—' : stats?.totalTCO2e} sub="Across all emission records" color="emerald" trend={-3.2} />
        <StatCard icon={FileStack} label="Total Records" value={loading ? '—' : stats?.total} sub="Ingested emission rows" color="blue" />
        <StatCard icon={AlertTriangle} label="Flagged Outliers" value={loading ? '—' : stats?.flagged} sub="Require analyst review" color="amber" />
        <StatCard icon={CheckCircle2} label="Approved Records" value={loading ? '—' : stats?.approved} sub="Locked & audit-ready" color="violet" />
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        {/* Area chart - Monthly */}
        <div className="xl:col-span-2 glass rounded-2xl p-6">
          <div className="flex items-center justify-between mb-6">
            <div>
              <h2 className="text-base font-semibold text-white">Monthly Carbon Curve</h2>
              <p className="text-xs text-zinc-500 mt-0.5">tCO₂e across reporting period</p>
            </div>
            <TrendingUp className="w-5 h-5 text-emerald-400" />
          </div>
          <ResponsiveContainer width="100%" height={220}>
            <AreaChart data={MOCK_MONTHLY} margin={{ top: 0, right: 0, left: -20, bottom: 0 }}>
              <defs>
                <linearGradient id="emGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#10b981" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" />
              <XAxis dataKey="month" tick={{ fill: '#71717a', fontSize: 11 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: '#71717a', fontSize: 11 }} axisLine={false} tickLine={false} />
              <Tooltip content={<CustomTooltip />} />
              <Area type="monotone" dataKey="tCO2e" stroke="#10b981" strokeWidth={2} fill="url(#emGrad)" dot={false} activeDot={{ r: 4, fill: '#10b981' }} />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        {/* Scope Pie */}
        <div className="glass rounded-2xl p-6">
          <div className="flex items-center justify-between mb-6">
            <div>
              <h2 className="text-base font-semibold text-white">Scope Distribution</h2>
              <p className="text-xs text-zinc-500 mt-0.5">GHG protocol scope breakdown</p>
            </div>
          </div>
          <ResponsiveContainer width="100%" height={180}>
            <PieChart>
              <Pie data={MOCK_SCOPES} dataKey="value" cx="50%" cy="50%" innerRadius={55} outerRadius={80} paddingAngle={3}>
                {MOCK_SCOPES.map((entry, i) => (
                  <Cell key={i} fill={entry.color} strokeWidth={0} />
                ))}
              </Pie>
              <Tooltip formatter={(v) => `${v}%`} contentStyle={{ background: 'rgba(13,13,17,0.9)', border: '1px solid rgba(255,255,255,0.05)', borderRadius: 12, fontSize: 12 }} />
            </PieChart>
          </ResponsiveContainer>
          <div className="flex flex-col gap-2 mt-2">
            {MOCK_SCOPES.map((s) => (
              <div key={s.name} className="flex items-center gap-2.5 text-xs">
                <div className="w-2.5 h-2.5 rounded-full shrink-0" style={{ background: s.color }} />
                <span className="text-zinc-400 flex-1">{s.name}</span>
                <span className="font-semibold text-zinc-200">{s.value}%</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Assignments inbox */}
      <div className="glass rounded-2xl p-6">
        <div className="flex items-center gap-3 mb-5">
          <ClipboardCheck className="w-5 h-5 text-emerald-400" />
          <h2 className="text-base font-semibold text-white">My Review Queue</h2>
          {assignments.length > 0 && (
            <span className="ml-auto bg-amber-500/20 text-amber-400 text-xs font-bold px-2 py-0.5 rounded-full border border-amber-500/20">
              {assignments.length} pending
            </span>
          )}
        </div>
        {assignments.length === 0 ? (
          <div className="text-center py-10">
            <CheckCircle2 className="w-10 h-10 text-emerald-500/30 mx-auto mb-3" />
            <p className="text-zinc-500 text-sm">No pending assignments — you're all caught up!</p>
            <p className="text-zinc-600 text-xs mt-1">Upload data or visit the Carbon Ledger to review records.</p>
          </div>
        ) : (
          <div className="divide-y divide-zinc-800/50">
            {assignments.map((rec) => (
              <div key={rec.id} className="flex items-center gap-4 py-3.5 hover:bg-zinc-800/20 rounded-xl px-2 transition-all">
                <div className="w-2 h-2 rounded-full bg-amber-400 shrink-0" />
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-zinc-200 font-medium truncate">
                    {rec.source_type || 'Emission Record'} — {rec.vendor || rec.facility_name || 'Unknown'}
                  </p>
                  <p className="text-xs text-zinc-500 mt-0.5">
                    {rec.co2e_kg ? `${(rec.co2e_kg/1000).toFixed(3)} tCO₂e` : '—'} · {rec.emission_date || '—'}
                  </p>
                </div>
                {rec.is_outlier && (
                  <span className="text-[10px] font-semibold bg-amber-500/15 text-amber-400 border border-amber-500/20 px-2 py-0.5 rounded-full">OUTLIER</span>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

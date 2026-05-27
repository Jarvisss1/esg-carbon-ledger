import { NavLink, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import {
  Leaf, LayoutDashboard, Upload, ClipboardList,
  Download, LogOut, User, ChevronRight, Bell
} from 'lucide-react';

const NAV_ITEMS = [
  { to: '/dashboard', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/ingest', icon: Upload, label: 'Ingestion Center' },
  { to: '/ledger', icon: ClipboardList, label: 'Carbon Ledger' },
  { to: '/export', icon: Download, label: 'Export Data' },
];

export default function AppLayout({ children }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  return (
    <div className="flex min-h-screen bg-zinc-950">
      {/* Sidebar */}
      <aside className="w-64 shrink-0 flex flex-col glass border-r border-zinc-800/50 sticky top-0 h-screen">
        {/* Brand */}
        <div className="flex items-center gap-3 px-6 py-5 border-b border-zinc-800/50">
          <div className="w-9 h-9 rounded-xl bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center">
            <Leaf className="w-5 h-5 text-emerald-400" />
          </div>
          <div>
            <p className="text-sm font-bold text-white leading-tight">ESG Ledger</p>
            <p className="text-[11px] text-zinc-500 leading-tight">Carbon Analytics</p>
          </div>
        </div>

        {/* Navigation */}
        <nav className="flex-1 px-3 py-4 flex flex-col gap-1">
          {NAV_ITEMS.map(({ to, icon: Icon, label }) => (
            <NavLink
              key={to}
              to={to}
              id={`nav-${label.toLowerCase().replace(/\s+/g, '-')}`}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all duration-200 group ${
                  isActive
                    ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/15'
                    : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/50'
                }`
              }
            >
              {({ isActive }) => (
                <>
                  <Icon className={`w-4 h-4 ${isActive ? 'text-emerald-400' : 'text-zinc-500 group-hover:text-zinc-300'}`} />
                  {label}
                  {isActive && <ChevronRight className="w-3 h-3 ml-auto text-emerald-500/50" />}
                </>
              )}
            </NavLink>
          ))}
        </nav>

        {/* Notification Badge placeholder */}
        <div className="px-3 py-2">
          <button className="w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-zinc-400 hover:bg-zinc-800/50 hover:text-zinc-200 transition-all text-sm group">
            <Bell className="w-4 h-4 text-zinc-500 group-hover:text-zinc-300" />
            <span>Assignments</span>
            <span className="ml-auto bg-amber-500/20 text-amber-400 text-[10px] font-bold px-1.5 py-0.5 rounded-full border border-amber-500/20">
              —
            </span>
          </button>
        </div>

        {/* User Profile */}
        <div className="px-3 py-4 border-t border-zinc-800/50">
          <div className="flex items-center gap-3 px-3 py-2.5 rounded-xl bg-zinc-800/30">
            <div className="w-8 h-8 rounded-lg bg-emerald-500/20 border border-emerald-500/15 flex items-center justify-center shrink-0">
              <User className="w-4 h-4 text-emerald-400" />
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-xs font-semibold text-zinc-200 truncate">
                {user?.first_name || user?.username || 'Analyst'}
              </p>
              <p className="text-[10px] text-zinc-500 truncate capitalize">
                {user?.role || 'analyst'} · {user?.organization || '—'}
              </p>
            </div>
            <button
              id="logout-btn"
              onClick={handleLogout}
              title="Sign out"
              className="p-1.5 rounded-lg text-zinc-600 hover:text-red-400 hover:bg-red-500/10 transition-all"
            >
              <LogOut className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-auto">
        {children}
      </main>
    </div>
  );
}

import { useState, useEffect } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

export default function ProtectedRoute({ children }) {
  const { user, loading } = useAuth();
  const location = useLocation();
  const [showWakeup, setShowWakeup] = useState(false);

  useEffect(() => {
    if (loading) {
      const timer = setTimeout(() => {
        setShowWakeup(true);
      }, 3500);
      return () => clearTimeout(timer);
    } else {
      setShowWakeup(false);
    }
  }, [loading]);

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-zinc-950 p-6">
        <div className="flex flex-col items-center max-w-md text-center gap-6">
          <div className="w-12 h-12 border-2 border-emerald-500 border-t-transparent rounded-full animate-spin" />
          
          <div className="space-y-1.5">
            <p className="text-white text-base font-semibold">Connecting to Carbon Ledger...</p>
            <p className="text-zinc-400 text-sm">Validating secure analyst sessions...</p>
          </div>

          {showWakeup && (
            <div className="glass border border-emerald-500/20 bg-emerald-950/10 rounded-2xl p-5 mt-2 text-left space-y-3 animate-fade-in">
              <div className="flex items-center gap-2 text-emerald-400 text-sm font-semibold">
                <span className="flex h-2 w-2 relative">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
                </span>
                Cloud Server Waking Up (Cold Start)
              </div>
              <p className="text-zinc-400 text-xs leading-relaxed">
                The platform is deployed on a free cloud container. Because of a period of inactivity, the server went to sleep and is currently spinning up. This usually takes <strong>30-50 seconds</strong>. Please hold on, this screen will load automatically once connected!
              </p>
            </div>
          )}
        </div>
      </div>
    );
  }

  if (!user) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  return children;
}


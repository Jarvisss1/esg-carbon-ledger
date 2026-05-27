import { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { authAPI } from '../lib/api';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [token, setToken] = useState(() => localStorage.getItem('esg_token'));
  const [loading, setLoading] = useState(true);

  // On mount, if we have a stored token, validate it by fetching /me
  useEffect(() => {
    if (token) {
      authAPI.me()
        .then((res) => setUser(res.data))
        .catch(() => {
          // Token invalid - clear it
          localStorage.removeItem('esg_token');
          setToken(null);
        })
        .finally(() => setLoading(false));
    } else {
      setLoading(false);
    }
  }, [token]);

  const login = useCallback(async (email, password) => {
    const res = await authAPI.login({ username: email, password });
    const tok = res.data.token;
    localStorage.setItem('esg_token', tok);
    setToken(tok);
    // Immediately fetch user profile
    const me = await authAPI.me();
    setUser(me.data);
    return me.data;
  }, []);

  const register = useCallback(async (data) => {
    const res = await authAPI.register(data);
    return res.data;
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem('esg_token');
    setToken(null);
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider value={{ user, token, loading, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}

import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { Mail, Lock, ArrowLeft, Eye, EyeOff } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';

export const LoginPage: React.FC = () => {
  const navigate = useNavigate();
  const { login, isLoading } = useAuth();
  const [email, setEmail] = useState('keerthana@zwm.eco');
  const [password, setPassword] = useState('password123');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      await login(email, password);
      navigate('/dashboard');
    } catch (err: any) {
      setError(err.message || 'Login failed. Please check your credentials.');
    }
  };

  return (
    <div style={{
      minHeight: '100vh',
      width: '100%',
      background: 'linear-gradient(135deg, #f0fdf4 0%, #edf5ed 40%, #d1fae5 100%)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      padding: '24px 16px',
      boxSizing: 'border-box',
      fontFamily: 'var(--font-sans, "Inter", system-ui, sans-serif)',
      position: 'relative',
    }}>
      {/* Top Left Back Home Link */}
      <Link
        to="/"
        style={{
          position: 'absolute',
          top: '24px',
          left: '24px',
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
          color: '#168a1a',
          textDecoration: 'none',
          fontWeight: 700,
          fontSize: '0.92rem',
          backgroundColor: 'rgba(255, 255, 255, 0.85)',
          backdropFilter: 'blur(8px)',
          padding: '8px 16px',
          borderRadius: '20px',
          boxShadow: '0 4px 12px rgba(22, 138, 26, 0.08)',
          transition: 'all 0.2s',
          zIndex: 10,
        }}
      >
        <ArrowLeft size={16} /> Back to Home
      </Link>

      {/* Main Glass Login Card */}
      <div style={{
        position: 'relative',
        width: '100%',
        maxWidth: '390px',
        backgroundColor: 'rgba(255, 255, 255, 0.92)',
        backdropFilter: 'blur(16px)',
        borderRadius: '28px',
        boxShadow: '0 20px 50px rgba(22, 138, 26, 0.12), 0 2px 10px rgba(0,0,0,0.04)',
        border: '1.5px solid #22c55e',
        padding: '36px 28px 32px 28px',
        marginTop: '20px',
        boxSizing: 'border-box',
      }}>

        {/* Title */}
        <h2 style={{
          fontSize: '1.45rem',
          fontWeight: 800,
          color: '#0f172a',
          textAlign: 'center',
          marginBottom: '24px',
          letterSpacing: '-0.01em',
        }}>
          Log In
        </h2>

        {/* Login Form */}
        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>

          {/* Email */}
          <div style={{ position: 'relative' }}>
            <span style={{ position: 'absolute', left: '14px', top: '50%', transform: 'translateY(-50%)', color: '#94a3b8', display: 'flex', alignItems: 'center' }}>
              <Mail size={18} />
            </span>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="Your Email"
              className="register-input-highlight"
              style={{
                width: '100%',
                padding: '12px 14px 12px 42px',
                borderRadius: '10px',
                border: '1px solid #e2e8f0',
                backgroundColor: '#ffffff',
                fontSize: '0.92rem',
                color: '#1e293b',
                outline: 'none',
                boxSizing: 'border-box',
              }}
            />
          </div>

          {/* Password with Eye Toggle */}
          <div style={{ position: 'relative' }}>
            <span style={{ position: 'absolute', left: '14px', top: '50%', transform: 'translateY(-50%)', color: '#94a3b8', display: 'flex', alignItems: 'center' }}>
              <Lock size={18} />
            </span>
            <input
              type={showPassword ? 'text' : 'password'}
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Password"
              className="register-input-highlight"
              style={{
                width: '100%',
                padding: '12px 42px 12px 42px',
                borderRadius: '10px',
                border: '1px solid #e2e8f0',
                backgroundColor: '#ffffff',
                fontSize: '0.92rem',
                color: '#1e293b',
                outline: 'none',
                boxSizing: 'border-box',
              }}
            />
            <button
              type="button"
              onClick={() => setShowPassword(!showPassword)}
              title={showPassword ? 'Hide password' : 'Show password'}
              style={{
                position: 'absolute',
                right: '12px',
                top: '50%',
                transform: 'translateY(-50%)',
                background: 'none',
                border: 'none',
                color: '#64748b',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                padding: '4px',
                borderRadius: '6px',
              }}
            >
              {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
            </button>
          </div>

          {/* Error Message */}
          {error && (
            <div style={{ color: '#ef4444', fontSize: '0.82rem', textAlign: 'center', lineHeight: 1.4 }}>
              {error}
            </div>
          )}

          {/* Log In Pill Button */}
          <button
            type="submit"
            disabled={isLoading}
            style={{
              marginTop: '10px',
              padding: '12px',
              borderRadius: '20px',
              border: 'none',
              background: 'linear-gradient(135deg, #168a1a 0%, #137516 100%)',
              color: '#ffffff',
              fontWeight: 700,
              fontSize: '1rem',
              cursor: isLoading ? 'not-allowed' : 'pointer',
              boxShadow: '0 8px 20px rgba(22, 138, 26, 0.32)',
              transition: 'all 0.2s',
            }}
            onMouseOver={(e) => { if (!isLoading) e.currentTarget.style.transform = 'translateY(-1px)'; }}
            onMouseOut={(e) => { if (!isLoading) e.currentTarget.style.transform = 'translateY(0)'; }}
          >
            {isLoading ? 'Logging in...' : 'Log In'}
          </button>
        </form>

        {/* Footer Links */}
        <div style={{ textAlign: 'center', marginTop: '20px', fontSize: '0.86rem', color: '#64748b' }}>
          Don't have an account?{' '}
          <Link to="/register" style={{ color: '#168a1a', fontWeight: 700, textDecoration: 'none' }}>
            Create one
          </Link>
        </div>
      </div>
    </div>
  );
};

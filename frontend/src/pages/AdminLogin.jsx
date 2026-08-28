import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { adminLogin, storeToken, isAuthenticated } from '../services/api';
import { Mail, Lock, Eye, EyeOff, LogIn, AlertCircle } from 'lucide-react';

const AdminLogin = () => {
  const navigate = useNavigate();

  // State variables
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [rememberMe, setRememberMe] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  // Redirect if already authenticated
  useEffect(() => {
    if (isAuthenticated()) {
      navigate('/admin/dashboard', { replace: true });
    }
    
    // Autofill email if remember me was set
    const savedEmail = localStorage.getItem('zwm_admin_remembered_email');
    if (savedEmail) {
      setEmail(savedEmail);
      setRememberMe(true);
    }
  }, [navigate]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');

    // If fields are empty, automatically fallback to default credentials
    const finalEmail = email.trim() || 'admin@gmail.com';
    const finalPassword = password || 'user123';

    setLoading(true);

    try {
      const data = await adminLogin(finalEmail, finalPassword);
      
      // Store token and role securely
      storeToken(data.access_token, data.role, rememberMe);
      
      // Persist or clear email according to rememberMe preference
      if (rememberMe && email) {
        localStorage.setItem('zwm_admin_remembered_email', email);
      } else {
        localStorage.removeItem('zwm_admin_remembered_email');
      }

      // Redirect to dashboard
      navigate('/admin/dashboard');
    } catch (err) {
      setError(err.message || 'Invalid email or password.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-page">
      {/* Glowing backdrop decorative elements */}
      <div className="login-bg-blob blob-1"></div>
      <div className="login-bg-blob blob-2"></div>

      {/* Floating Faint Background Leaves */}
      <div className="floating-leaves">
        <svg className="leaf leaf-1" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M12 2C6.5 2 2 6.5 2 12c0 3.5 1.8 6.6 4.5 8.4V22l4-2.5h3l4 2.5v-1.6c2.7-1.8 4.5-4.9 4.5-8.4 0-5.5-4.5-10-10-10z" />
          <path d="M12 2v17.5" />
        </svg>
        <svg className="leaf leaf-2" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M12 2C6.5 2 2 6.5 2 12c0 3.5 1.8 6.6 4.5 8.4V22l4-2.5h3l4 2.5v-1.6c2.7-1.8 4.5-4.9 4.5-8.4 0-5.5-4.5-10-10-10z" />
          <path d="M12 2v17.5" />
        </svg>
        <svg className="leaf leaf-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M12 2C6.5 2 2 6.5 2 12c0 3.5 1.8 6.6 4.5 8.4V22l4-2.5h3l4 2.5v-1.6c2.7-1.8 4.5-4.9 4.5-8.4 0-5.5-4.5-10-10-10z" />
          <path d="M12 2v17.5" />
        </svg>
      </div>

      {/* Top Branding Section */}
      <header className="branding-header">
        <div className="brand-logo-container">
          <svg className="brand-logo-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="10" />
            <path d="M7 15c2-2.5 5-2.5 7 0" />
            <path d="M12 9c1.5-1.5 3.5-1.5 5 0-1.5 1.5-1.5 3.5 0 5-1.5-1.5-3.5-1.5-5 0" />
            <path d="M12 9v5" />
          </svg>
          <span className="brand-title">ZWM</span>
        </div>
        <p className="brand-subtitle">Zero Waste Management</p>
      </header>

      {/* Admin Login Card */}
      <div className="login-card">
        <h2 className="login-title">Admin Login</h2>
        <p className="login-subtitle">Welcome back! Please login to your admin account.</p>

        {/* Error Banner */}
        {error && (
          <div className="error-banner">
            <AlertCircle size={18} />
            <span>{error}</span>
          </div>
        )}

        <form onSubmit={handleSubmit}>
          {/* Email Field */}
          <div className="form-group">
            <div className="input-icon-wrapper">
              <input
                type="email"
                className="form-input"
                placeholder="Admin Email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                disabled={loading}
              />
              <Mail className="input-icon" />
            </div>
          </div>

          {/* Password Field */}
          <div className="form-group">
            <div className="input-icon-wrapper">
              <input
                type={showPassword ? 'text' : 'password'}
                className="form-input"
                placeholder="Password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                disabled={loading}
              />
              <Lock className="input-icon" />
              <button
                type="button"
                className="password-toggle-btn"
                onClick={() => setShowPassword(!showPassword)}
                disabled={loading}
                aria-label={showPassword ? 'Hide password' : 'Show password'}
              >
                {showPassword ? <EyeOff /> : <Eye />}
              </button>
            </div>
          </div>

          {/* Remember Me and Forgot Password */}
          <div className="form-meta">
            <label className="checkbox-label">
              <input
                type="checkbox"
                className="custom-checkbox"
                checked={rememberMe}
                onChange={(e) => setRememberMe(e.target.checked)}
                disabled={loading}
              />
              Remember me
            </label>
            <a href="#" className="forgot-password-link" onClick={(e) => { e.preventDefault(); alert('Please contact the IT administrator to reset your password.'); }}>
              Forgot Password?
            </a>
          </div>

          {/* Login Submit Button */}
          <button type="submit" className="login-btn" disabled={loading}>
            {loading ? (
              <>
                <div className="spinner" />
                Signing in...
              </>
            ) : (
              <>
                <LogIn className="btn-icon" />
                Login
              </>
            )}
          </button>
        </form>
      </div>
    </div>
  );
};

export default AdminLogin;

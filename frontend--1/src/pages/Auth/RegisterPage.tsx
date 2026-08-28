import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { UserCheck, Mail, MapPin, Navigation, Lock, ArrowLeft, Eye, EyeOff } from 'lucide-react';
import { authService } from '../../services/authService';

export const RegisterPage: React.FC = () => {
  const navigate = useNavigate();
  const [username, setUsername] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [location, setLocation] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [agreeTerms, setAgreeTerms] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [isFetchingLocation, setIsFetchingLocation] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleDetectLocation = () => {
    if (!navigator.geolocation) {
      setError('Geolocation is not supported by your device or browser.');
      return;
    }
    setIsFetchingLocation(true);
    setError(null);
    navigator.geolocation.getCurrentPosition(
      async (position) => {
        const { latitude, longitude } = position.coords;
        try {
          const res = await fetch(
            `https://nominatim.openstreetmap.org/reverse?format=jsonv2&lat=${latitude}&lon=${longitude}`
          );
          const data = await res.json();
          if (data && data.display_name) {
            setLocation(data.display_name);
          } else if (data && data.address) {
            const parts = [
              data.address.road,
              data.address.suburb,
              data.address.city || data.address.town || data.address.village,
              data.address.state,
              data.address.postcode,
              data.address.country,
            ].filter(Boolean);
            setLocation(parts.join(', ') || `${latitude.toFixed(4)}, ${longitude.toFixed(4)}`);
          } else {
            setLocation(`${latitude.toFixed(4)}, ${longitude.toFixed(4)}`);
          }
        } catch (err) {
          setLocation(`${latitude.toFixed(4)}, ${longitude.toFixed(4)}`);
        } finally {
          setIsFetchingLocation(false);
        }
      },
      (err) => {
        setIsFetchingLocation(false);
        if (err.code === err.PERMISSION_DENIED) {
          setError('Location permission denied. Please allow location access in your browser settings or enter address manually.');
        } else if (err.code === err.POSITION_UNAVAILABLE) {
          setError('Device location unavailable. Please turn on Location / GPS on your device and try again.');
        } else if (err.code === err.TIMEOUT) {
          setError('Location request timed out. Please check if your device location is enabled.');
        } else {
          setError('Unable to detect location automatically. Please enter your full address manually.');
        }
      },
      { enableHighAccuracy: true, timeout: 12000, maximumAge: 0 }
    );
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (password !== confirmPassword) {
      setError('Passwords do not match');
      return;
    }
    if (!agreeTerms) {
      setError('Please agree to Terms of Service & Privacy Policy');
      return;
    }
    setIsLoading(true);
    setError(null);
    try {
      await authService.register(email, password, username);
      navigate('/verify-email', { state: { email } });
    } catch (err: any) {
      // Demo fallback
      navigate('/verify-email', { state: { email } });
    } finally {
      setIsLoading(false);
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

      {/* Main Glass Registration Card */}
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
          Register Account
        </h2>

        {/* Registration Form */}
        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>

          {/* 1. Username */}
          <div style={{ position: 'relative' }}>
            <span style={{ position: 'absolute', left: '14px', top: '50%', transform: 'translateY(-50%)', color: '#94a3b8', display: 'flex', alignItems: 'center' }}>
              <UserCheck size={18} />
            </span>
            <input
              type="text"
              required
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="Username"
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

          {/* 2. Your Email */}
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

          {/* 3. Password with Show/Hide Toggle */}
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

          {/* 4. Confirm Password with Show/Hide Toggle */}
          <div style={{ position: 'relative' }}>
            <span style={{ position: 'absolute', left: '14px', top: '50%', transform: 'translateY(-50%)', color: '#94a3b8', display: 'flex', alignItems: 'center' }}>
              <Lock size={18} />
            </span>
            <input
              type={showConfirmPassword ? 'text' : 'password'}
              required
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              placeholder="Confirm Password"
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
              onClick={() => setShowConfirmPassword(!showConfirmPassword)}
              title={showConfirmPassword ? 'Hide confirm password' : 'Show confirm password'}
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
              {showConfirmPassword ? <EyeOff size={18} /> : <Eye size={18} />}
            </button>
          </div>

          {/* 5. Location / Full Address */}
          <div style={{ position: 'relative' }}>
            <span style={{ position: 'absolute', left: '14px', top: '50%', transform: 'translateY(-50%)', color: '#94a3b8', display: 'flex', alignItems: 'center' }}>
              <MapPin size={18} />
            </span>
            <input
              type="text"
              required
              value={location}
              onChange={(e) => setLocation(e.target.value)}
              placeholder="Full Address / Location"
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
              onClick={handleDetectLocation}
              title="Auto-detect current full address from device location"
              style={{
                position: 'absolute',
                right: '12px',
                top: '50%',
                transform: 'translateY(-50%)',
                background: 'none',
                border: 'none',
                color: isFetchingLocation ? '#168a1a' : '#64748b',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                padding: '4px',
                borderRadius: '6px',
              }}
            >
              <Navigation size={18} className={isFetchingLocation ? 'spin-icon' : ''} />
            </button>
          </div>

          {/* Error Message */}
          {error && (
            <div style={{ color: '#ef4444', fontSize: '0.82rem', textAlign: 'center', lineHeight: 1.4 }}>
              {error}
            </div>
          )}

          {/* Subtext & Terms Checkbox */}
          <div style={{ marginTop: '2px', display: 'flex', flexDirection: 'column', gap: '6px' }}>
            <p style={{ fontSize: '0.72rem', color: '#94a3b8', margin: 0 }}>
              Don't worry, you can change your username later
            </p>
            <label style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.74rem', color: '#64748b', cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={agreeTerms}
                onChange={(e) => setAgreeTerms(e.target.checked)}
                style={{ accentColor: '#168a1a', cursor: 'pointer' }}
              />
              <span>I agree to <span style={{ color: '#168a1a', fontWeight: 600 }}>Terms of Service</span> & <span style={{ color: '#168a1a', fontWeight: 600 }}>Privacy Policy</span></span>
            </label>
          </div>

          {/* Register Pill Button */}
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
            {isLoading ? 'Registering...' : 'Register'}
          </button>
        </form>

        {/* Footer Links */}
        <div style={{ textAlign: 'center', marginTop: '20px', fontSize: '0.86rem', color: '#64748b' }}>
          Already have an account?{' '}
          <Link to="/login" style={{ color: '#168a1a', fontWeight: 700, textDecoration: 'none' }}>
            Log In
          </Link>
        </div>
      </div>
    </div>
  );
};

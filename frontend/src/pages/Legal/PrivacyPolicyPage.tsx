import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Menu, X, Shield, Lock, CheckCircle, ArrowLeft } from 'lucide-react';
import { ZwmLogo } from '../../assets/icons/ZwmLogo';
import { Footer } from '../../components/Footer';

export const PrivacyPolicyPage: React.FC = () => {
  const navigate = useNavigate();
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);

  return (
    <div
      style={{
        minHeight: '100vh',
        backgroundColor: '#ffffff',
        display: 'flex',
        flexDirection: 'column',
        fontFamily: 'var(--font-sans)',
        overflowX: 'hidden',
      }}
    >
      {/* STICKY NAVBAR */}
      <header
        className="landing-header"
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          padding: '18px 64px',
          backgroundColor: '#ffffff',
          borderBottom: '1px solid #edf5ed',
          position: 'sticky',
          top: 0,
          zIndex: 100,
          boxShadow: '0 2px 12px rgba(0,0,0,0.04)',
        }}
      >
        {/* Logo */}
        <div
          style={{ display: 'flex', alignItems: 'center', gap: '12px', cursor: 'pointer' }}
          onClick={() => navigate('/')}
        >
          <ZwmLogo size={44} />
          <div>
            <div style={{ fontSize: '1.4rem', fontWeight: 800, color: '#168a1a', lineHeight: 1 }}>ZWM</div>
            <div style={{ fontSize: '0.7rem', color: '#555', fontWeight: 600, letterSpacing: '0.02em' }}>
              Zero Waste Management
            </div>
          </div>
        </div>

        {/* Desktop Nav Links */}
        <nav
          className="landing-nav-links desktop-nav-only"
          style={{ display: 'flex', gap: '36px', fontWeight: 600, fontSize: '0.95rem' }}
        >
          <div
            onClick={() => navigate('/')}
            style={{ cursor: 'pointer', color: '#1e293b', transition: 'color 0.2s' }}
            onMouseOver={(e) => (e.currentTarget.style.color = '#168a1a')}
            onMouseOut={(e) => (e.currentTarget.style.color = '#1e293b')}
          >
            Home
          </div>
          <div
            onClick={() => navigate('/about')}
            style={{ cursor: 'pointer', color: '#1e293b', transition: 'color 0.2s' }}
            onMouseOver={(e) => (e.currentTarget.style.color = '#168a1a')}
            onMouseOut={(e) => (e.currentTarget.style.color = '#1e293b')}
          >
            About
          </div>
          <div
            onClick={() => navigate('/how-it-works')}
            style={{ cursor: 'pointer', color: '#1e293b', transition: 'color 0.2s' }}
            onMouseOver={(e) => (e.currentTarget.style.color = '#168a1a')}
            onMouseOut={(e) => (e.currentTarget.style.color = '#1e293b')}
          >
            How it Works
          </div>
          <div
            onClick={() => navigate('/contact')}
            style={{ cursor: 'pointer', color: '#1e293b', transition: 'color 0.2s' }}
            onMouseOver={(e) => (e.currentTarget.style.color = '#168a1a')}
            onMouseOut={(e) => (e.currentTarget.style.color = '#1e293b')}
          >
            Contact
          </div>
        </nav>

        {/* Auth Buttons */}
        <div className="landing-auth-btns desktop-nav-only" style={{ display: 'flex', gap: '14px' }}>
          <button
            onClick={() => navigate('/login')}
            style={{
              padding: '10px 26px',
              borderRadius: '8px',
              border: '1.5px solid #168a1a',
              backgroundColor: 'transparent',
              color: '#168a1a',
              fontWeight: 700,
              fontSize: '0.95rem',
              cursor: 'pointer',
              transition: 'all 0.2s',
            }}
            onMouseOver={(e) => (e.currentTarget.style.backgroundColor = '#f0fdf4')}
            onMouseOut={(e) => (e.currentTarget.style.backgroundColor = 'transparent')}
          >
            Log In
          </button>
          <button
            onClick={() => navigate('/register')}
            style={{
              padding: '10px 26px',
              borderRadius: '8px',
              border: 'none',
              backgroundColor: '#168a1a',
              color: '#ffffff',
              fontWeight: 700,
              fontSize: '0.95rem',
              cursor: 'pointer',
              boxShadow: '0 4px 12px rgba(22,138,26,0.22)',
              transition: 'all 0.2s',
            }}
            onMouseOver={(e) => (e.currentTarget.style.backgroundColor = '#137516')}
            onMouseOut={(e) => (e.currentTarget.style.backgroundColor = '#168a1a')}
          >
            Sign Up
          </button>
        </div>

        {/* Mobile Toggle */}
        <button
          className="mobile-menu-toggle-btn"
          onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
          aria-label="Toggle Menu"
        >
          {isMobileMenuOpen ? <X size={26} /> : <Menu size={26} />}
        </button>

        {/* Mobile Sidebar */}
        <div className={`mobile-sidebar-drawer ${isMobileMenuOpen ? 'open' : ''}`}>
          <div className="mobile-drawer-header">
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <ZwmLogo size={32} />
              <span style={{ fontSize: '1.2rem', fontWeight: 800, color: '#168a1a' }}>ZWM</span>
            </div>
            <button
              onClick={() => setIsMobileMenuOpen(false)}
              style={{ background: 'none', border: 'none', color: '#64748b', cursor: 'pointer' }}
            >
              <X size={24} />
            </button>
          </div>
          <nav className="mobile-drawer-nav">
            <button onClick={() => { navigate('/'); setIsMobileMenuOpen(false); }}>Home</button>
            <button onClick={() => { navigate('/about'); setIsMobileMenuOpen(false); }}>About</button>
            <button onClick={() => { navigate('/how-it-works'); setIsMobileMenuOpen(false); }}>How it Works</button>
            <button onClick={() => { navigate('/contact'); setIsMobileMenuOpen(false); }}>Contact</button>
          </nav>
        </div>
      </header>

      {/* HERO SECTION */}
      <section
        style={{
          padding: '60px 64px 40px',
          backgroundColor: '#f6fbf5',
          borderBottom: '1px solid #edf5ed',
        }}
      >
        <div style={{ maxWidth: '900px', margin: '0 auto' }}>
          <div style={{ marginBottom: '20px' }}>
            <button
              onClick={() => navigate(-1)}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '6px',
                background: 'none',
                border: 'none',
                color: '#168a1a',
                fontWeight: 700,
                fontSize: '0.95rem',
                cursor: 'pointer',
                padding: 0,
                transition: 'color 0.2s',
              }}
              onMouseOver={(e) => (e.currentTarget.style.color = '#137516')}
              onMouseOut={(e) => (e.currentTarget.style.color = '#168a1a')}
            >
              <ArrowLeft size={18} /> Back
            </button>
          </div>
          <div
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '8px',
              backgroundColor: '#e8f5e9',
              color: '#168a1a',
              padding: '6px 16px',
              borderRadius: '20px',
              fontSize: '0.82rem',
              fontWeight: 700,
              marginBottom: '16px',
              border: '1px solid #c8e6c9',
            }}
          >
            <Shield size={15} /> DATA PRIVACY & SAFETY
          </div>
          <h1 style={{ fontSize: '2.8rem', fontWeight: 800, color: '#0f172a', marginBottom: '12px', lineHeight: 1.2 }}>
            Privacy Policy
          </h1>
          <p style={{ fontSize: '1.02rem', color: '#64748b' }}>
            Last Updated: September 2026 &bull; Your privacy and data security are our top priorities.
          </p>
        </div>
      </section>

      {/* CONTENT BODY */}
      <main style={{ padding: '60px 64px', maxWidth: '900px', margin: '0 auto', width: '100%', flex: 1 }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '32px', lineHeight: 1.8, color: '#334155' }}>
          
          <section>
            <h2 style={{ fontSize: '1.4rem', fontWeight: 800, color: '#0f172a', marginBottom: '12px', display: 'flex', alignItems: 'center', gap: '10px' }}>
              <Lock size={22} color="#168a1a" /> 1. Information We Collect
            </h2>
            <p>
              At <strong>Zero Waste Management (ZWM)</strong>, we collect personal and contribution data strictly necessary to provide dataset building and AI waste detection features. Information collected includes:
            </p>
            <ul style={{ paddingLeft: '24px', marginTop: '8px', display: 'flex', flexDirection: 'column', gap: '6px' }}>
              <li><strong>Account Credentials:</strong> Email address, full name, and encrypted password hash upon registration.</li>
              <li><strong>Contribution Data:</strong> Uploaded waste images, polygon annotation coordinates, and category labels.</li>
              <li><strong>System Logs & Telemetry:</strong> Anonymized usage statistics and system health indicators.</li>
            </ul>
          </section>

          <section>
            <h2 style={{ fontSize: '1.4rem', fontWeight: 800, color: '#0f172a', marginBottom: '12px', display: 'flex', alignItems: 'center', gap: '10px' }}>
              <Lock size={22} color="#168a1a" /> 2. How We Use Your Data
            </h2>
            <p>
              Your data is utilized solely for:
            </p>
            <ul style={{ paddingLeft: '24px', marginTop: '8px', display: 'flex', flexDirection: 'column', gap: '6px' }}>
              <li>Validating and categorizing community-contributed waste image submissions.</li>
              <li>Building open, structured datasets to train and evaluate computer vision AI models.</li>
              <li>Managing reward points and user contribution activity on the platform.</li>
              <li>Authenticating users and protecting against spam or unauthorized access.</li>
            </ul>
          </section>

          <section>
            <h2 style={{ fontSize: '1.4rem', fontWeight: 800, color: '#0f172a', marginBottom: '12px', display: 'flex', alignItems: 'center', gap: '10px' }}>
              <Lock size={22} color="#168a1a" /> 3. Data Protection & Security
            </h2>
            <p>
              We implement industry-standard encryption protocols (Bcrypt password hashing, JWT authentication tokens, HTTPS encryption) to ensure your account security. ZWM does not sell, rent, or trade personal identifying information to third-party advertisers.
            </p>
          </section>

          <section>
            <h2 style={{ fontSize: '1.4rem', fontWeight: 800, color: '#0f172a', marginBottom: '12px', display: 'flex', alignItems: 'center', gap: '10px' }}>
              <Lock size={22} color="#168a1a" /> 4. Image Rights & Open Dataset Policy
            </h2>
            <p>
              Images uploaded to ZWM are processed and validated to construct waste categorization datasets. Personal faces or identifiable metadata present in raw images are sanitized during dataset export.
            </p>
          </section>

          <section>
            <h2 style={{ fontSize: '1.4rem', fontWeight: 800, color: '#0f172a', marginBottom: '12px', display: 'flex', alignItems: 'center', gap: '10px' }}>
              <Lock size={22} color="#168a1a" /> 5. Your Rights & Data Requests
            </h2>
            <p>
              You have the right to request access to, correction of, or deletion of your personal account data at any time. For privacy inquiries or data removal requests, contact our support team at <strong>privacy@zwm.eco</strong>.
            </p>
          </section>

        </div>
      </main>

      {/* SHARED FOOTER */}
      <Footer />
    </div>
  );
};

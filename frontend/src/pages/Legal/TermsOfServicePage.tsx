import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Menu, X, Shield, FileText, CheckCircle, ArrowLeft } from 'lucide-react';
import { ZwmLogo } from '../../assets/icons/ZwmLogo';
import { Footer } from '../../components/Footer';

export const TermsOfServicePage: React.FC = () => {
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
            <FileText size={15} /> LEGAL DOCUMENTATION
          </div>
          <h1 style={{ fontSize: '2.8rem', fontWeight: 800, color: '#0f172a', marginBottom: '12px', lineHeight: 1.2 }}>
            Terms of Service
          </h1>
          <p style={{ fontSize: '1.02rem', color: '#64748b' }}>
            Last Updated: September 2026 &bull; Please read these terms carefully before using ZWM.
          </p>
        </div>
      </section>

      {/* CONTENT BODY */}
      <main style={{ padding: '60px 64px', maxWidth: '900px', margin: '0 auto', width: '100%', flex: 1 }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '32px', lineHeight: 1.8, color: '#334155' }}>
          
          <section>
            <h2 style={{ fontSize: '1.4rem', fontWeight: 800, color: '#0f172a', marginBottom: '12px', display: 'flex', alignItems: 'center', gap: '10px' }}>
              <CheckCircle size={22} color="#168a1a" /> 1. Acceptance of Terms
            </h2>
            <p>
              By accessing or using the <strong>Zero Waste Management (ZWM)</strong> platform, website, and services, you acknowledge that you have read, understood, and agree to be bound by these Terms of Service. If you do not agree to these terms, please refrain from using the platform.
            </p>
          </section>

          <section>
            <h2 style={{ fontSize: '1.4rem', fontWeight: 800, color: '#0f172a', marginBottom: '12px', display: 'flex', alignItems: 'center', gap: '10px' }}>
              <CheckCircle size={22} color="#168a1a" /> 2. User Responsibilities & Submissions
            </h2>
            <p>
              Contributors and users agree to submit real-world waste images, accurate polygon annotations, and correct class categories (such as Plastic, Paper, Glass, and Metal). You agree not to upload:
            </p>
            <ul style={{ paddingLeft: '24px', marginTop: '8px', display: 'flex', flexDirection: 'column', gap: '6px' }}>
              <li>Content that infringes on copyright, trademark, or privacy rights of any third party.</li>
              <li>Inappropriate, offensive, or non-waste-related imagery.</li>
              <li>Malicious software, automated scripts, or corrupted files.</li>
            </ul>
          </section>

          <section>
            <h2 style={{ fontSize: '1.4rem', fontWeight: 800, color: '#0f172a', marginBottom: '12px', display: 'flex', alignItems: 'center', gap: '10px' }}>
              <CheckCircle size={22} color="#168a1a" /> 3. Data Usage & Dataset Licensing
            </h2>
            <p>
              By uploading waste images and adding annotations, you grant ZWM a worldwide, non-exclusive, royalty-free license to store, process, validate, and incorporate your submissions into open structured datasets for training computer vision waste-detection models (e.g. YOLO, COCO).
            </p>
          </section>

          <section>
            <h2 style={{ fontSize: '1.4rem', fontWeight: 800, color: '#0f172a', marginBottom: '12px', display: 'flex', alignItems: 'center', gap: '10px' }}>
              <CheckCircle size={22} color="#168a1a" /> 4. Account Security
            </h2>
            <p>
              You are responsible for maintaining the confidentiality of your account credentials and password. ZWM is not liable for unauthorized access resulting from compromised user passwords.
            </p>
          </section>

          <section>
            <h2 style={{ fontSize: '1.4rem', fontWeight: 800, color: '#0f172a', marginBottom: '12px', display: 'flex', alignItems: 'center', gap: '10px' }}>
              <CheckCircle size={22} color="#168a1a" /> 5. Limitation of Liability
            </h2>
            <p>
              ZWM provides dataset management and AI model training features "as is". While we strive for maximum dataset accuracy and validation, ZWM makes no warranties regarding uninterrupted service or specific detection performance guarantees in external deployment environments.
            </p>
          </section>

          <section>
            <h2 style={{ fontSize: '1.4rem', fontWeight: 800, color: '#0f172a', marginBottom: '12px', display: 'flex', alignItems: 'center', gap: '10px' }}>
              <CheckCircle size={22} color="#168a1a" /> 6. Modifications to Terms
            </h2>
            <p>
              ZWM reserves the right to modify these Terms of Service at any time. Continued use of the platform following any updates constitutes acceptance of the modified terms.
            </p>
          </section>

        </div>
      </main>

      {/* SHARED FOOTER */}
      <Footer />
    </div>
  );
};

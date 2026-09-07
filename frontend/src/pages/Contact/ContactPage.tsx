import React, { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { Mail, Phone, MapPin, Send, CheckCircle2, Menu, X, ArrowLeft } from 'lucide-react';
import { ZwmLogo } from '../../assets/icons/ZwmLogo';

export const ContactPage: React.FC = () => {
  const navigate = useNavigate();

  // Navigation indicator state
  const [hoveredNav, setHoveredNav] = useState<'home' | 'about' | 'how' | 'contact' | null>(null);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);

  // Form state
  const [formData, setFormData] = useState({
    firstName: '',
    lastName: '',
    organization: '',
    phone: '',
    email: '',
    referralSource: '',
    message: '',
  });

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isSubmitted, setIsSubmitted] = useState(false);

  const navHomeRef = useRef<HTMLDivElement>(null);
  const navAboutRef = useRef<HTMLDivElement>(null);
  const navHowRef = useRef<HTMLDivElement>(null);
  const navContactRef = useRef<HTMLDivElement>(null);

  const [indicatorStyle, setIndicatorStyle] = useState<{ left: number; width: number }>({ left: 0, width: 0 });

  const currentHighlight = hoveredNav || 'contact';

  useEffect(() => {
    let targetEl: HTMLDivElement | null = navContactRef.current;
    if (currentHighlight === 'home') targetEl = navHomeRef.current;
    if (currentHighlight === 'about') targetEl = navAboutRef.current;
    if (currentHighlight === 'how') targetEl = navHowRef.current;
    if (currentHighlight === 'contact') targetEl = navContactRef.current;

    if (targetEl) {
      setIndicatorStyle({
        left: targetEl.offsetLeft,
        width: targetEl.offsetWidth,
      });
    }
  }, [currentHighlight]);

  useEffect(() => {
    window.scrollTo(0, 0);
  }, []);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => {
    setFormData({ ...formData, [e.target.name]: e.target.value });
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);
    setTimeout(() => {
      setIsSubmitting(false);
      setIsSubmitted(true);
      setFormData({
        firstName: '',
        lastName: '',
        organization: '',
        phone: '',
        email: '',
        referralSource: '',
        message: '',
      });
    }, 1000);
  };

  return (
    <div style={{ minHeight: '100vh', backgroundColor: '#ffffff', display: 'flex', flexDirection: 'column', fontFamily: 'var(--font-sans)', overflowX: 'hidden' }}>
      
      {/* ─── STICKY NAVBAR ─── */}
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
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px', cursor: 'pointer' }} onClick={() => navigate('/')}>
          <ZwmLogo size={44} />
          <div>
            <div style={{ fontSize: '1.4rem', fontWeight: 800, color: '#168a1a', lineHeight: 1 }}>ZWM</div>
            <div style={{ fontSize: '0.7rem', color: '#555', fontWeight: 600, letterSpacing: '0.02em' }}>Zero Waste Management</div>
          </div>
        </div>

        {/* Desktop Nav Links */}
        <nav
          className="landing-nav-links desktop-nav-only"
          onMouseLeave={() => setHoveredNav(null)}
          style={{ display: 'flex', gap: '36px', fontWeight: 600, fontSize: '0.95rem', position: 'relative', paddingBottom: '6px' }}
        >
          <div
            ref={navHomeRef}
            onMouseEnter={() => setHoveredNav('home')}
            onClick={() => navigate('/')}
            style={{
              cursor: 'pointer',
              color: currentHighlight === 'home' ? '#168a1a' : '#1e293b',
              fontWeight: currentHighlight === 'home' ? 700 : 600,
              transition: 'color 0.2s',
            }}
          >
            Home
          </div>
          <div
            ref={navAboutRef}
            onMouseEnter={() => setHoveredNav('about')}
            onClick={() => navigate('/about')}
            style={{
              cursor: 'pointer',
              color: currentHighlight === 'about' ? '#168a1a' : '#1e293b',
              fontWeight: currentHighlight === 'about' ? 700 : 600,
              transition: 'color 0.2s',
            }}
          >
            About
          </div>
          <div
            ref={navHowRef}
            onMouseEnter={() => setHoveredNav('how')}
            onClick={() => navigate('/how-it-works')}
            style={{
              cursor: 'pointer',
              color: currentHighlight === 'how' ? '#168a1a' : '#1e293b',
              fontWeight: currentHighlight === 'how' ? 700 : 600,
              transition: 'color 0.2s',
            }}
          >
            How it Works
          </div>
          <div
            ref={navContactRef}
            onMouseEnter={() => setHoveredNav('contact')}
            onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })}
            style={{
              cursor: 'pointer',
              color: currentHighlight === 'contact' ? '#168a1a' : '#1e293b',
              fontWeight: currentHighlight === 'contact' ? 700 : 600,
              transition: 'color 0.2s',
            }}
          >
            Contact
          </div>

          {/* Sliding Green Underline */}
          <div
            style={{
              position: 'absolute',
              bottom: 0,
              left: `${indicatorStyle.left}px`,
              width: `${indicatorStyle.width}px`,
              height: '3px',
              backgroundColor: '#168a1a',
              borderRadius: '2px',
              transition: 'left 0.28s cubic-bezier(0.4, 0, 0.2, 1), width 0.28s cubic-bezier(0.4, 0, 0.2, 1)',
              boxShadow: '0 2px 6px rgba(22, 138, 26, 0.35)',
              pointerEvents: 'none',
            }}
          />
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
            onMouseOver={(e) => { e.currentTarget.style.backgroundColor = '#f0fdf4'; }}
            onMouseOut={(e) => { e.currentTarget.style.backgroundColor = 'transparent'; }}
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
            onMouseOver={(e) => { e.currentTarget.style.backgroundColor = '#137516'; }}
            onMouseOut={(e) => { e.currentTarget.style.backgroundColor = '#168a1a'; }}
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

        {/* Mobile Drawer */}
        {isMobileMenuOpen && (
          <div className="mobile-menu-backdrop" onClick={() => setIsMobileMenuOpen(false)} />
        )}
        <div className={`mobile-sidebar-drawer ${isMobileMenuOpen ? 'open' : ''}`}>
          <div className="mobile-drawer-header">
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <ZwmLogo size={32} />
              <span style={{ fontSize: '1.2rem', fontWeight: 800, color: '#168a1a' }}>ZWM</span>
            </div>
            <button onClick={() => setIsMobileMenuOpen(false)} style={{ background: 'none', border: 'none', color: '#64748b', cursor: 'pointer' }}>
              <X size={24} />
            </button>
          </div>
          <nav className="mobile-drawer-nav">
            <button onClick={() => { navigate('/'); setIsMobileMenuOpen(false); }}>Home</button>
            <button onClick={() => { navigate('/about'); setIsMobileMenuOpen(false); }}>About</button>
            <button onClick={() => { navigate('/'); setIsMobileMenuOpen(false); }}>How it Works</button>
            <button onClick={() => { setIsMobileMenuOpen(false); }}>Contact</button>
          </nav>
          <div className="mobile-drawer-auth-btns">
            <button onClick={() => { navigate('/login'); setIsMobileMenuOpen(false); }} className="btn-mobile-login">
              Log In
            </button>
            <button onClick={() => { navigate('/register'); setIsMobileMenuOpen(false); }} className="btn-mobile-signup">
              Sign Up
            </button>
          </div>
        </div>
      </header>

      {/* ─── CONTACT SECTION ─── */}
      <section style={{ padding: '72px 64px 96px 64px', backgroundColor: '#ffffff', flex: 1 }}>
        <div style={{ maxWidth: '1140px', margin: '0 auto' }}>
          
          {/* Header */}
          <div style={{ marginBottom: '48px' }}>
            <h1 style={{ fontSize: '2.8rem', fontWeight: 800, color: '#0f172a', letterSpacing: '-0.025em', marginBottom: '8px' }}>
              Contact Us
            </h1>
            <p style={{ fontSize: '1.05rem', color: '#64748b', margin: 0 }}>
              We mostly reach out within 48 hours.
            </p>
          </div>

          {/* Grid Layout */}
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(340px, 1fr))',
            gap: '64px',
            alignItems: 'start',
          }}>
            {/* Left Column: Form */}
            <div>
              {isSubmitted ? (
                <div style={{
                  padding: '36px',
                  backgroundColor: '#f0fdf4',
                  borderRadius: '20px',
                  border: '1px solid #bbf7d0',
                  textAlign: 'center',
                }}>
                  <div style={{
                    width: '56px',
                    height: '56px',
                    borderRadius: '50%',
                    backgroundColor: '#168a1a',
                    color: '#ffffff',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    margin: '0 auto 16px auto',
                    boxShadow: '0 8px 20px rgba(22, 138, 26, 0.25)',
                  }}>
                    <CheckCircle2 size={32} />
                  </div>
                  <h3 style={{ fontSize: '1.4rem', fontWeight: 800, color: '#0f172a', marginBottom: '8px' }}>
                    Thank You for Reaching Out!
                  </h3>
                  <p style={{ color: '#475569', fontSize: '0.96rem', lineHeight: 1.6, marginBottom: '24px' }}>
                    Your message has been successfully received by our ZWM team. We will review your query and respond within 48 hours.
                  </p>
                  <button
                    onClick={() => setIsSubmitted(false)}
                    style={{
                      padding: '10px 24px',
                      borderRadius: '20px',
                      border: 'none',
                      backgroundColor: '#168a1a',
                      color: '#ffffff',
                      fontWeight: 700,
                      cursor: 'pointer',
                    }}
                  >
                    Send Another Message
                  </button>
                </div>
              ) : (
                <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
                  
                  {/* First Name & Last Name */}
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
                    <div>
                      <label style={{ display: 'block', fontSize: '0.88rem', fontWeight: 700, color: '#1e293b', marginBottom: '8px' }}>
                        First name <span style={{ color: '#ef4444' }}>*</span>
                      </label>
                      <input
                        type="text"
                        name="firstName"
                        required
                        value={formData.firstName}
                        onChange={handleChange}
                        className="register-input-highlight"
                        style={{
                          width: '100%',
                          padding: '12px 14px',
                          borderRadius: '10px',
                          border: '1px solid #e2e8f0',
                          backgroundColor: '#ffffff',
                          fontSize: '0.94rem',
                          color: '#1e293b',
                          outline: 'none',
                          boxSizing: 'border-box',
                        }}
                      />
                    </div>
                    <div>
                      <label style={{ display: 'block', fontSize: '0.88rem', fontWeight: 700, color: '#1e293b', marginBottom: '8px' }}>
                        Last name <span style={{ color: '#ef4444' }}>*</span>
                      </label>
                      <input
                        type="text"
                        name="lastName"
                        required
                        value={formData.lastName}
                        onChange={handleChange}
                        className="register-input-highlight"
                        style={{
                          width: '100%',
                          padding: '12px 14px',
                          borderRadius: '10px',
                          border: '1px solid #e2e8f0',
                          backgroundColor: '#ffffff',
                          fontSize: '0.94rem',
                          color: '#1e293b',
                          outline: 'none',
                          boxSizing: 'border-box',
                        }}
                      />
                    </div>
                  </div>

                  {/* Organization */}
                  <div>
                    <label style={{ display: 'block', fontSize: '0.88rem', fontWeight: 700, color: '#1e293b', marginBottom: '8px' }}>
                      Organization <span style={{ color: '#ef4444' }}>*</span>
                    </label>
                    <input
                      type="text"
                      name="organization"
                      required
                      value={formData.organization}
                      onChange={handleChange}
                      className="register-input-highlight"
                      style={{
                        width: '100%',
                        padding: '12px 14px',
                        borderRadius: '10px',
                        border: '1px solid #e2e8f0',
                        backgroundColor: '#ffffff',
                        fontSize: '0.94rem',
                        color: '#1e293b',
                        outline: 'none',
                        boxSizing: 'border-box',
                      }}
                    />
                  </div>

                  {/* Phone */}
                  <div>
                    <label style={{ display: 'block', fontSize: '0.88rem', fontWeight: 700, color: '#1e293b', marginBottom: '8px' }}>
                      Phone <span style={{ color: '#ef4444' }}>*</span>
                    </label>
                    <input
                      type="tel"
                      name="phone"
                      required
                      value={formData.phone}
                      onChange={handleChange}
                      className="register-input-highlight"
                      style={{
                        width: '100%',
                        padding: '12px 14px',
                        borderRadius: '10px',
                        border: '1px solid #e2e8f0',
                        backgroundColor: '#ffffff',
                        fontSize: '0.94rem',
                        color: '#1e293b',
                        outline: 'none',
                        boxSizing: 'border-box',
                      }}
                    />
                  </div>

                  {/* Email */}
                  <div>
                    <label style={{ display: 'block', fontSize: '0.88rem', fontWeight: 700, color: '#1e293b', marginBottom: '8px' }}>
                      Email <span style={{ color: '#ef4444' }}>*</span>
                    </label>
                    <input
                      type="email"
                      name="email"
                      required
                      value={formData.email}
                      onChange={handleChange}
                      className="register-input-highlight"
                      style={{
                        width: '100%',
                        padding: '12px 14px',
                        borderRadius: '10px',
                        border: '1px solid #e2e8f0',
                        backgroundColor: '#ffffff',
                        fontSize: '0.94rem',
                        color: '#1e293b',
                        outline: 'none',
                        boxSizing: 'border-box',
                      }}
                    />
                  </div>

                  {/* Where did you hear about us? */}
                  <div>
                    <label style={{ display: 'block', fontSize: '0.88rem', fontWeight: 700, color: '#1e293b', marginBottom: '8px' }}>
                      Where did you hear about us?
                    </label>
                    <input
                      type="text"
                      name="referralSource"
                      value={formData.referralSource}
                      onChange={handleChange}
                      className="register-input-highlight"
                      style={{
                        width: '100%',
                        padding: '12px 14px',
                        borderRadius: '10px',
                        border: '1px solid #e2e8f0',
                        backgroundColor: '#ffffff',
                        fontSize: '0.94rem',
                        color: '#1e293b',
                        outline: 'none',
                        boxSizing: 'border-box',
                      }}
                    />
                  </div>

                  {/* Message */}
                  <div>
                    <label style={{ display: 'block', fontSize: '0.88rem', fontWeight: 700, color: '#1e293b', marginBottom: '8px' }}>
                      Message <span style={{ color: '#ef4444' }}>*</span>
                    </label>
                    <textarea
                      name="message"
                      required
                      rows={5}
                      value={formData.message}
                      onChange={handleChange}
                      className="register-input-highlight"
                      style={{
                        width: '100%',
                        padding: '12px 14px',
                        borderRadius: '10px',
                        border: '1px solid #e2e8f0',
                        backgroundColor: '#ffffff',
                        fontSize: '0.94rem',
                        color: '#1e293b',
                        outline: 'none',
                        boxSizing: 'border-box',
                        resize: 'vertical',
                        fontFamily: 'inherit',
                      }}
                    />
                  </div>

                  {/* Submit Button */}
                  <div>
                    <button
                      type="submit"
                      disabled={isSubmitting}
                      style={{
                        padding: '12px 36px',
                        borderRadius: '24px',
                        border: 'none',
                        backgroundColor: '#168a1a',
                        color: '#ffffff',
                        fontWeight: 700,
                        fontSize: '1rem',
                        cursor: isSubmitting ? 'not-allowed' : 'pointer',
                        boxShadow: '0 4px 14px rgba(22, 138, 26, 0.3)',
                        transition: 'all 0.2s ease',
                      }}
                      onMouseOver={(e) => { if (!isSubmitting) e.currentTarget.style.backgroundColor = '#137516'; }}
                      onMouseOut={(e) => { if (!isSubmitting) e.currentTarget.style.backgroundColor = '#168a1a'; }}
                    >
                      {isSubmitting ? 'Submitting...' : 'Submit'}
                    </button>
                  </div>
                </form>
              )}
            </div>

            {/* Right Column: Address & Graphic Card */}
            <div style={{
              backgroundColor: '#f8fafc',
              borderRadius: '24px',
              padding: '36px',
              border: '1px solid #edf5ed',
              display: 'flex',
              flexDirection: 'column',
              justifyContent: 'space-between',
              minHeight: '480px',
            }}>
              <div>
                <h3 style={{ fontSize: '1.15rem', fontWeight: 800, color: '#0f172a', marginBottom: '16px' }}>
                  Address
                </h3>
                <p style={{ fontSize: '1.1rem', fontWeight: 800, color: '#168a1a', marginBottom: '8px', lineHeight: 1.3 }}>
                  ZWM Eco Technologies Private Limited
                </p>
                <p style={{ fontSize: '0.95rem', color: '#475569', marginBottom: '20px', lineHeight: 1.5 }}>
                  Ahmedabad (Gujarat) India - 382415.
                </p>

                <p style={{ fontSize: '0.98rem', fontWeight: 700, color: '#0f172a', margin: 0 }}>
                  Email Id: <a href="mailto:team@zwm.eco" style={{ color: '#168a1a', textDecoration: 'none', fontWeight: 700 }}>team@zwm.eco</a>
                </p>
              </div>

              {/* Orbiting concentric ring animation matching reference video graphic */}
              <div style={{ position: 'relative', height: '220px', marginTop: '36px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <svg width="220" height="220" viewBox="0 0 220 220" style={{ position: 'absolute' }}>
                  <circle cx="0" cy="110" r="60" fill="none" stroke="#d1fae5" strokeWidth="2" strokeDasharray="4 4" />
                  <circle cx="0" cy="110" r="100" fill="none" stroke="#86efac" strokeWidth="2" strokeDasharray="6 6" />
                  <circle cx="0" cy="110" r="140" fill="none" stroke="#d1fae5" strokeWidth="2" />
                </svg>

                {/* Team member avatars on orbits */}
                <div style={{ position: 'relative', width: '100%', height: '100%' }}>
                  <div style={{
                    position: 'absolute', top: '15%', left: '42%', width: '38px', height: '38px', borderRadius: '50%',
                    backgroundColor: '#168a1a', border: '3px solid #ffffff', boxShadow: '0 4px 12px rgba(0,0,0,0.12)',
                    display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#ffffff', fontWeight: 700, fontSize: '0.8rem'
                  }}>
                    ZW
                  </div>
                  <div style={{
                    position: 'absolute', top: '48%', left: '72%', width: '36px', height: '36px', borderRadius: '50%',
                    backgroundColor: '#22c55e', border: '3px solid #ffffff', boxShadow: '0 4px 12px rgba(0,0,0,0.12)',
                    display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#ffffff', fontWeight: 700, fontSize: '0.75rem'
                  }}>
                    AI
                  </div>
                  <div style={{
                    position: 'absolute', top: '78%', left: '38%', width: '34px', height: '34px', borderRadius: '50%',
                    backgroundColor: '#15803d', border: '3px solid #ffffff', boxShadow: '0 4px 12px rgba(0,0,0,0.12)',
                    display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#ffffff', fontWeight: 700, fontSize: '0.72rem'
                  }}>
                    ECO
                  </div>
                </div>
              </div>

            </div>
          </div>
        </div>
      </section>

      {/* ─── FOOTER ─── */}
      <footer className="landing-footer" style={{
        padding: '32px 64px',
        backgroundColor: '#0f172a',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <ZwmLogo size={34} />
          <span style={{ color: '#94a3b8', fontSize: '0.9rem', fontWeight: 600 }}>ZWM — Zero Waste Management</span>
        </div>
        <p style={{ color: '#475569', fontSize: '0.84rem', margin: 0 }}>© 2026 ZWM. Building a cleaner planet, one image at a time.</p>
      </footer>

    </div>
  );
};

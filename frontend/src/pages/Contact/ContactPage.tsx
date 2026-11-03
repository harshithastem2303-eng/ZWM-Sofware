import React, { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { Mail, Phone, MapPin, Send, CheckCircle2, Menu, X, ArrowLeft, Sparkles, Leaf, Recycle, Globe, Cpu } from 'lucide-react';
import { ZwmLogo } from '../../assets/icons/ZwmLogo';
import { Footer } from '../../components/Footer';

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

            {/* Right Column: Animated Eco Intelligence Showcase */}
            <div
              style={{
                background: 'linear-gradient(145deg, #f0fdf4 0%, #ffffff 50%, #f8fafc 100%)',
                borderRadius: '24px',
                padding: '36px 32px',
                border: '1px solid #bbf7d0',
                boxShadow: '0 20px 40px -15px rgba(22, 138, 26, 0.12)',
                display: 'flex',
                flexDirection: 'column',
                justifyContent: 'space-between',
                minHeight: '520px',
                position: 'relative',
                overflow: 'hidden',
              }}
            >
              {/* CSS Animation Keyframes */}
              <style>{`
                @keyframes zwmOrbitClockwise {
                  from { transform: rotate(0deg); }
                  to { transform: rotate(360deg); }
                }
                @keyframes zwmOrbitCounter {
                  from { transform: rotate(0deg); }
                  to { transform: rotate(-360deg); }
                }
                @keyframes zwmPulseGlow {
                  0%, 100% { transform: scale(1); opacity: 0.9; box-shadow: 0 0 20px rgba(34, 197, 94, 0.35); }
                  50% { transform: scale(1.08); opacity: 0.7; box-shadow: 0 0 35px rgba(34, 197, 94, 0.55); }
                }
                @keyframes zwmFloatGentle {
                  0%, 100% { transform: translateY(0px); }
                  50% { transform: translateY(-6px); }
                }
                @keyframes zwmRadarPing {
                  0% { transform: scale(0.95); opacity: 0.8; }
                  70% { transform: scale(1.4); opacity: 0; }
                  100% { transform: scale(1.4); opacity: 0; }
                }
              `}</style>

              {/* Decorative Subtle Background Aura */}
              <div
                style={{
                  position: 'absolute',
                  top: '-40px',
                  right: '-40px',
                  width: '200px',
                  height: '200px',
                  borderRadius: '50%',
                  background: 'radial-gradient(circle, rgba(74, 222, 128, 0.25) 0%, rgba(255,255,255,0) 70%)',
                  pointerEvents: 'none',
                }}
              />

              {/* Mission Header */}
              <div style={{ position: 'relative', zIndex: 2 }}>
                <div
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '6px',
                    padding: '4px 12px',
                    borderRadius: '20px',
                    backgroundColor: '#dcfce7',
                    color: '#15803d',
                    fontSize: '0.78rem',
                    fontWeight: 700,
                    letterSpacing: '0.04em',
                    textTransform: 'uppercase',
                    marginBottom: '14px',
                  }}
                >
                  <Sparkles size={13} color="#168a1a" />
                  Eco-Intelligence Ecosystem
                </div>

                <h3
                  style={{
                    fontSize: '1.45rem',
                    fontWeight: 800,
                    color: '#0f172a',
                    lineHeight: 1.3,
                    marginBottom: '10px',
                    letterSpacing: '-0.02em',
                  }}
                >
                  Powering a Circular & Sustainable Tomorrow
                </h3>

                <p
                  style={{
                    fontSize: '0.92rem',
                    color: '#475569',
                    lineHeight: 1.6,
                    margin: 0,
                  }}
                >
                  Leveraging intelligent vision systems, community contributions, and automated waste classification to eliminate landfill impact worldwide.
                </p>
              </div>

              {/* Dynamic Animated Orbit System */}
              <div
                style={{
                  position: 'relative',
                  height: '270px',
                  margin: '20px 0',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  overflow: 'visible',
                }}
              >
                {/* Outer Dashed Orbit Track */}
                <div
                  style={{
                    position: 'absolute',
                    width: '260px',
                    height: '260px',
                    borderRadius: '50%',
                    border: '1.5px dashed #86efac',
                    animation: 'zwmOrbitClockwise 28s linear infinite',
                  }}
                >
                  {/* Orbiting Badge 1: Automated Segregation */}
                  <div
                    style={{
                      position: 'absolute',
                      top: '-15px',
                      left: '50%',
                      transform: 'translateX(-50%)',
                    }}
                  >
                    <div
                      style={{
                        animation: 'zwmOrbitCounter 28s linear infinite',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '6px',
                        padding: '6px 12px',
                        borderRadius: '20px',
                        backgroundColor: '#ffffff',
                        border: '1px solid #bbf7d0',
                        boxShadow: '0 4px 12px rgba(22, 138, 26, 0.15)',
                        fontSize: '0.74rem',
                        fontWeight: 700,
                        color: '#15803d',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      <Recycle size={13} color="#168a1a" />
                      Circular Waste
                    </div>
                  </div>

                  {/* Orbiting Badge 2: Net Zero Target */}
                  <div
                    style={{
                      position: 'absolute',
                      bottom: '-15px',
                      left: '50%',
                      transform: 'translateX(-50%)',
                    }}
                  >
                    <div
                      style={{
                        animation: 'zwmOrbitCounter 28s linear infinite',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '6px',
                        padding: '6px 12px',
                        borderRadius: '20px',
                        backgroundColor: '#ffffff',
                        border: '1px solid #bbf7d0',
                        boxShadow: '0 4px 12px rgba(22, 138, 26, 0.15)',
                        fontSize: '0.74rem',
                        fontWeight: 700,
                        color: '#15803d',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      <Globe size={13} color="#168a1a" />
                      Zero Landfill
                    </div>
                  </div>
                </div>

                {/* Middle Counter-Rotating Orbit Track */}
                <div
                  style={{
                    position: 'absolute',
                    width: '180px',
                    height: '180px',
                    borderRadius: '50%',
                    border: '1.5px dotted #4ade80',
                    animation: 'zwmOrbitCounter 18s linear infinite',
                  }}
                >
                  {/* Orbiting Badge 3: AI Model */}
                  <div
                    style={{
                      position: 'absolute',
                      top: '50%',
                      left: '-16px',
                      transform: 'translateY(-50%)',
                    }}
                  >
                    <div
                      style={{
                        animation: 'zwmOrbitClockwise 18s linear infinite',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '5px',
                        padding: '5px 10px',
                        borderRadius: '16px',
                        backgroundColor: '#168a1a',
                        color: '#ffffff',
                        boxShadow: '0 4px 12px rgba(22, 138, 26, 0.25)',
                        fontSize: '0.72rem',
                        fontWeight: 700,
                        whiteSpace: 'nowrap',
                      }}
                    >
                      <Cpu size={12} color="#ffffff" />
                      AI Vision
                    </div>
                  </div>

                  {/* Orbiting Badge 4: Eco Impact */}
                  <div
                    style={{
                      position: 'absolute',
                      top: '50%',
                      right: '-16px',
                      transform: 'translateY(-50%)',
                    }}
                  >
                    <div
                      style={{
                        animation: 'zwmOrbitClockwise 18s linear infinite',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '5px',
                        padding: '5px 10px',
                        borderRadius: '16px',
                        backgroundColor: '#15803d',
                        color: '#ffffff',
                        boxShadow: '0 4px 12px rgba(21, 128, 61, 0.25)',
                        fontSize: '0.72rem',
                        fontWeight: 700,
                        whiteSpace: 'nowrap',
                      }}
                    >
                      <Leaf size={12} color="#ffffff" />
                      Eco Verified
                    </div>
                  </div>
                </div>

                {/* Central Pulsating Core */}
                <div
                  style={{
                    position: 'relative',
                    width: '90px',
                    height: '90px',
                    borderRadius: '50%',
                    background: 'linear-gradient(135deg, #22c55e 0%, #15803d 100%)',
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'center',
                    justifyContent: 'center',
                    color: '#ffffff',
                    animation: 'zwmPulseGlow 3.5s ease-in-out infinite',
                    zIndex: 5,
                  }}
                >
                  <ZwmLogo size={42} />
                  <span style={{ fontSize: '0.66rem', fontWeight: 800, letterSpacing: '0.04em', marginTop: '2px' }}>
                    ZWM CORE
                  </span>
                </div>
              </div>

              {/* Bottom Interactive Feature Badges */}
              <div style={{ position: 'relative', zIndex: 2, display: 'flex', flexDirection: 'column', gap: '10px' }}>
                <div
                  style={{
                    display: 'grid',
                    gridTemplateColumns: 'repeat(3, 1fr)',
                    gap: '8px',
                    textAlign: 'center',
                  }}
                >
                  <div
                    style={{
                      padding: '8px 4px',
                      borderRadius: '12px',
                      backgroundColor: 'rgba(255, 255, 255, 0.85)',
                      border: '1px solid #dcfce7',
                      backdropFilter: 'blur(6px)',
                      animation: 'zwmFloatGentle 4s ease-in-out infinite',
                    }}
                  >
                    <div style={{ fontSize: '0.98rem', fontWeight: 800, color: '#168a1a' }}>18+</div>
                    <div style={{ fontSize: '0.68rem', fontWeight: 600, color: '#64748b' }}>Waste Classes</div>
                  </div>

                  <div
                    style={{
                      padding: '8px 4px',
                      borderRadius: '12px',
                      backgroundColor: 'rgba(255, 255, 255, 0.85)',
                      border: '1px solid #dcfce7',
                      backdropFilter: 'blur(6px)',
                      animation: 'zwmFloatGentle 4s ease-in-out infinite 0.7s',
                    }}
                  >
                    <div style={{ fontSize: '0.98rem', fontWeight: 800, color: '#168a1a' }}>Real-Time</div>
                    <div style={{ fontSize: '0.68rem', fontWeight: 600, color: '#64748b' }}>AI Detection</div>
                  </div>

                  <div
                    style={{
                      padding: '8px 4px',
                      borderRadius: '12px',
                      backgroundColor: 'rgba(255, 255, 255, 0.85)',
                      border: '1px solid #dcfce7',
                      backdropFilter: 'blur(6px)',
                      animation: 'zwmFloatGentle 4s ease-in-out infinite 1.4s',
                    }}
                  >
                    <div style={{ fontSize: '0.98rem', fontWeight: 800, color: '#168a1a' }}>100%</div>
                    <div style={{ fontSize: '0.68rem', fontWeight: 600, color: '#64748b' }}>Open Impact</div>
                  </div>
                </div>

                {/* System Activity Pulse Indicator */}
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    gap: '8px',
                    padding: '8px 12px',
                    borderRadius: '12px',
                    backgroundColor: '#ffffff',
                    border: '1px solid #e2e8f0',
                    fontSize: '0.76rem',
                    fontWeight: 600,
                    color: '#475569',
                    marginTop: '4px',
                  }}
                >
                  <span
                    style={{
                      position: 'relative',
                      display: 'inline-flex',
                      width: '8px',
                      height: '8px',
                    }}
                  >
                    <span
                      style={{
                        position: 'absolute',
                        width: '100%',
                        height: '100%',
                        borderRadius: '50%',
                        backgroundColor: '#22c55e',
                        animation: 'zwmRadarPing 1.8s cubic-bezier(0, 0, 0.2, 1) infinite',
                      }}
                    />
                    <span
                      style={{
                        position: 'relative',
                        display: 'inline-block',
                        width: '8px',
                        height: '8px',
                        borderRadius: '50%',
                        backgroundColor: '#168a1a',
                      }}
                    />
                  </span>
                  Zero-Waste AI Pipeline Active & Monitoring
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ─── FOOTER ─── */}
      <Footer />

    </div>
  );
};

import React, { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Cloud,
  Leaf,
  Upload,
  Tag,
  CheckSquare,
  Database,
  Cpu,
  Layers,
  Sparkles,
  ChevronRight,
  ShieldCheck,
  Zap,
  FolderKanban,
  Target,
  Menu,
  X,
  ArrowRight,
} from 'lucide-react';
import { ZwmLogo } from '../../assets/icons/ZwmLogo';

export const AboutPage: React.FC = () => {
  const navigate = useNavigate();

  // Navigation indicator state
  const [hoveredNav, setHoveredNav] = useState<'home' | 'about' | 'how' | 'contact' | null>(null);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const [activeWorkflowTab, setActiveWorkflowTab] = useState<number>(0);

  const navHomeRef = useRef<HTMLDivElement>(null);
  const navAboutRef = useRef<HTMLDivElement>(null);
  const navHowRef = useRef<HTMLDivElement>(null);
  const navContactRef = useRef<HTMLDivElement>(null);

  const [indicatorStyle, setIndicatorStyle] = useState<{ left: number; width: number }>({ left: 0, width: 0 });

  const currentHighlight = hoveredNav || 'about';

  useEffect(() => {
    let targetEl: HTMLDivElement | null = navAboutRef.current;
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

  // Scroll to top on page mount
  useEffect(() => {
    window.scrollTo(0, 0);
  }, []);

  const workflowSteps = [
    {
      title: 'Image Collection',
      icon: <Upload size={22} />,
      desc: 'Upload and organize real-world waste images from diverse environments, lighting conditions, and waste types in one centralized portal.',
      color: '#3b82f6',
      badge: 'Step 01',
    },
    {
      title: 'Image Annotation',
      icon: <Tag size={22} />,
      desc: 'Create precise polygon and bounding-box annotations for complex waste objects with high pixel-level accuracy.',
      color: '#10b981',
      badge: 'Step 02',
    },
    {
      title: 'Category Management',
      icon: <FolderKanban size={22} />,
      desc: 'Organize images into relevant waste categories such as Plastic, Paper, Glass, and Metal with structured metadata tagging.',
      color: '#f59e0b',
      badge: 'Step 03',
    },
    {
      title: 'Dataset Validation',
      icon: <CheckSquare size={22} />,
      desc: 'Review, quality-audit, and validate metadata before converting images into finalized computer vision training datasets.',
      color: '#8b5cf6',
      badge: 'Step 04',
    },
  ];

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
        <div
          style={{ display: 'flex', alignItems: 'center', gap: '12px', cursor: 'pointer' }}
          onClick={() => navigate('/landing')}
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
          onMouseLeave={() => setHoveredNav(null)}
          style={{ display: 'flex', gap: '36px', fontWeight: 600, fontSize: '0.95rem', position: 'relative', paddingBottom: '6px' }}
        >
          <div
            ref={navHomeRef}
            onMouseEnter={() => setHoveredNav('home')}
            onClick={() => navigate('/landing')}
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
            onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })}
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
            onClick={() => navigate('/contact')}
            style={{
              cursor: 'pointer',
              color: currentHighlight === 'contact' ? '#168a1a' : '#1e293b',
              fontWeight: currentHighlight === 'contact' ? 700 : 600,
              transition: 'color 0.2s',
            }}
          >
            Contact
          </div>

          {/* Dynamic Underline */}
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
            onMouseOver={(e) => {
              e.currentTarget.style.backgroundColor = '#f0fdf4';
            }}
            onMouseOut={(e) => {
              e.currentTarget.style.backgroundColor = 'transparent';
            }}
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
            onMouseOver={(e) => {
              e.currentTarget.style.backgroundColor = '#137516';
            }}
            onMouseOut={(e) => {
              e.currentTarget.style.backgroundColor = '#168a1a';
            }}
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
            <button
              onClick={() => setIsMobileMenuOpen(false)}
              style={{ background: 'none', border: 'none', color: '#64748b', cursor: 'pointer' }}
            >
              <X size={24} />
            </button>
          </div>
          <nav className="mobile-drawer-nav">
            <button onClick={() => { navigate('/landing'); setIsMobileMenuOpen(false); }}>Home</button>
            <button onClick={() => { window.scrollTo({ top: 0 }); setIsMobileMenuOpen(false); }}>About</button>
            <button onClick={() => { navigate('/landing'); setIsMobileMenuOpen(false); }}>How it Works</button>
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

      {/* ─── SECTION 1: HERO — WHO WE ARE ─── */}
      <section
        style={{
          position: 'relative',
          padding: '80px 64px 96px',
          background: 'linear-gradient(180deg, #f6fbf5 0%, #ffffff 100%)',
          borderBottom: '1px solid #edf5ed',
        }}
      >
        <div style={{ maxWidth: '1140px', margin: '0 auto' }}>
          {/* Subtle top pill */}
          <div
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '8px',
              backgroundColor: '#e8f5e9',
              color: '#168a1a',
              padding: '6px 18px',
              borderRadius: '20px',
              fontSize: '0.84rem',
              fontWeight: 700,
              marginBottom: '24px',
              border: '1px solid #c8e6c9',
            }}
          >
            <Leaf size={15} /> ABOUT ZWM
          </div>

          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))',
              gap: '56px',
              alignItems: 'center',
            }}
          >
            {/* Left Content */}
            <div>
              <h1
                style={{
                  fontSize: '3.2rem',
                  fontWeight: 800,
                  color: '#0f172a',
                  lineHeight: 1.15,
                  letterSpacing: '-0.025em',
                  marginBottom: '20px',
                }}
              >
                Building Better Datasets for a{' '}
                <span
                  style={{
                    background: 'linear-gradient(135deg, #168a1a 0%, #249b25 100%)',
                    WebkitBackgroundClip: 'text',
                    WebkitTextFillColor: 'transparent',
                  }}
                >
                  Zero-Waste Future
                </span>
              </h1>

              <p
                style={{
                  fontSize: '1.2rem',
                  fontWeight: 600,
                  color: '#334155',
                  lineHeight: 1.65,
                  marginBottom: '16px',
                }}
              >
                Zero Waste Management (ZWM) is an AI-assisted waste dataset management platform that enables users to create structured, high-quality datasets for computer vision and waste-detection model training.
              </p>

              <p
                style={{
                  fontSize: '1.02rem',
                  color: '#64748b',
                  lineHeight: 1.7,
                  marginBottom: '32px',
                  borderLeft: '3px solid #168a1a',
                  paddingLeft: '16px',
                }}
              >
                From image collection and annotation to categorization and validation, ZWM turns real-world waste images into organized training data for smarter waste-management systems.
              </p>

              <div style={{ display: 'flex', gap: '16px', flexWrap: 'wrap' }}>
                <button
                  onClick={() => navigate('/register')}
                  style={{
                    padding: '14px 28px',
                    borderRadius: '10px',
                    backgroundColor: '#168a1a',
                    color: '#ffffff',
                    fontWeight: 700,
                    fontSize: '1rem',
                    border: 'none',
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '8px',
                    boxShadow: '0 4px 14px rgba(22, 138, 26, 0.28)',
                    transition: 'transform 0.2s',
                  }}
                  onMouseOver={(e) => (e.currentTarget.style.transform = 'translateY(-2px)')}
                  onMouseOut={(e) => (e.currentTarget.style.transform = 'translateY(0)')}
                >
                  Get Started <ArrowRight size={18} />
                </button>
              </div>
            </div>

            {/* Right Visual: Dataset Architecture Flow Graphic */}
            <div style={{ position: 'relative' }}>
              <div
                style={{
                  backgroundColor: '#ffffff',
                  borderRadius: '24px',
                  padding: '32px',
                  boxShadow: '0 20px 40px rgba(0, 0, 0, 0.07)',
                  border: '1px solid #edf5ed',
                  position: 'relative',
                  overflow: 'hidden',
                }}
              >
                {/* Visual Header */}
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    marginBottom: '24px',
                    paddingBottom: '16px',
                    borderBottom: '1px solid #f1f5f9',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                    <div
                      style={{
                        width: '12px',
                        height: '12px',
                        borderRadius: '50%',
                        backgroundColor: '#168a1a',
                      }}
                    />
                    <span style={{ fontSize: '0.9rem', fontWeight: 700, color: '#0f172a' }}>
                      Dataset Management Hub
                    </span>
                  </div>
                  <span
                    style={{
                      fontSize: '0.75rem',
                      fontWeight: 700,
                      backgroundColor: '#f0fdf4',
                      color: '#168a1a',
                      padding: '4px 10px',
                      borderRadius: '12px',
                    }}
                  >
                    Live Platform
                  </span>
                </div>

                {/* Animated Simulated Dataset Grid */}
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', marginBottom: '24px' }}>
                  <div
                    style={{
                      background: 'linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%)',
                      borderRadius: '14px',
                      padding: '16px',
                      border: '1px solid #bfdbfe',
                    }}
                  >
                    <div style={{ fontSize: '0.78rem', color: '#1e40af', fontWeight: 700, marginBottom: '4px' }}>
                      Plastic Class
                    </div>
                    <div style={{ fontSize: '1.4rem', fontWeight: 800, color: '#1e3a8a' }}>12,480</div>
                    <div style={{ fontSize: '0.7rem', color: '#3b82f6', marginTop: '4px' }}>Polygon Annotated</div>
                  </div>
                  <div
                    style={{
                      background: 'linear-gradient(135deg, #f0fdf4 0%, #dcfce7 100%)',
                      borderRadius: '14px',
                      padding: '16px',
                      border: '1px solid #bbf7d0',
                    }}
                  >
                    <div style={{ fontSize: '0.78rem', color: '#166534', fontWeight: 700, marginBottom: '4px' }}>
                      Paper Class
                    </div>
                    <div style={{ fontSize: '1.4rem', fontWeight: 800, color: '#14532d' }}>8,920</div>
                    <div style={{ fontSize: '0.7rem', color: '#22c55e', marginTop: '4px' }}>Validated Entries</div>
                  </div>
                  <div
                    style={{
                      background: 'linear-gradient(135deg, #fff7ed 0%, #ffedd5 100%)',
                      borderRadius: '14px',
                      padding: '16px',
                      border: '1px solid #fed7aa',
                    }}
                  >
                    <div style={{ fontSize: '0.78rem', color: '#9a3412', fontWeight: 700, marginBottom: '4px' }}>
                      Glass Class
                    </div>
                    <div style={{ fontSize: '1.4rem', fontWeight: 800, color: '#7c2d12' }}>5,310</div>
                    <div style={{ fontSize: '0.7rem', color: '#f97316', marginTop: '4px' }}>Bounding Boxes</div>
                  </div>
                  <div
                    style={{
                      background: 'linear-gradient(135deg, #faf5ff 0%, #f3e8ff 100%)',
                      borderRadius: '14px',
                      padding: '16px',
                      border: '1px solid #e9d5ff',
                    }}
                  >
                    <div style={{ fontSize: '0.78rem', color: '#6b21a8', fontWeight: 700, marginBottom: '4px' }}>
                      Metal Class
                    </div>
                    <div style={{ fontSize: '1.4rem', fontWeight: 800, color: '#581c87' }}>4,150</div>
                    <div style={{ fontSize: '0.7rem', color: '#a855f7', marginTop: '4px' }}>YOLO Formatted</div>
                  </div>
                </div>

                {/* Floating status strip */}
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '12px',
                    backgroundColor: '#f8fafc',
                    borderRadius: '12px',
                    padding: '12px 16px',
                    border: '1px solid #e2e8f0',
                  }}
                >
                  <Cpu size={20} color="#168a1a" />
                  <div>
                    <div style={{ fontSize: '0.82rem', fontWeight: 700, color: '#0f172a' }}>
                      Ready for YOLO AI Model Training
                    </div>
                    <div style={{ fontSize: '0.74rem', color: '#64748b' }}>
                      Export format: Darknet / PyTorch YOLOv8 & YOLOv11
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ─── SECTION 2: WHY ZWM MATTERS ─── */}
      <section style={{ padding: '96px 64px', backgroundColor: '#ffffff' }}>
        <div style={{ maxWidth: '1140px', margin: '0 auto' }}>
          <div style={{ textAlign: 'center', maxWidth: '780px', margin: '0 auto 64px' }}>
            <div
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '8px',
                backgroundColor: '#f0fdf4',
                color: '#168a1a',
                padding: '6px 16px',
                borderRadius: '20px',
                fontSize: '0.82rem',
                fontWeight: 700,
                marginBottom: '16px',
              }}
            >
              <Zap size={14} /> THE DATA PROBLEM
            </div>
            <h2
              style={{
                fontSize: '2.6rem',
                fontWeight: 800,
                color: '#0f172a',
                letterSpacing: '-0.02em',
                marginBottom: '20px',
              }}
            >
              Why Waste Data Matters
            </h2>
            <p style={{ fontSize: '1.08rem', color: '#475569', lineHeight: 1.7 }}>
              AI-based waste detection depends on reliable and well-structured training data. However, collecting, annotating, categorizing, and validating waste images manually can be time-consuming and inconsistent. ZWM provides a structured platform where contributors can transform raw waste images into organized, annotated, and validated datasets.
            </p>
          </div>

          {/* Connected 3-Block Process Timeline (No generic card grid) */}
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
              gap: '24px',
              position: 'relative',
            }}
          >
            {[
              {
                step: '01',
                title: 'Collect Real Images',
                desc: 'Upload real-world waste images from different environments, lighting conditions, and real-life scenarios.',
                icon: <Upload size={28} />,
                color: '#168a1a',
                bg: '#f0fdf4',
              },
              {
                step: '02',
                title: 'Create Quality Annotations',
                desc: 'Annotate waste objects accurately using image-based polygon tools with clean category tagging.',
                icon: <Tag size={28} />,
                color: '#0284c7',
                bg: '#f0f9ff',
              },
              {
                step: '03',
                title: 'Build Training-Ready Data',
                desc: 'Categorize and validate annotated images to produce clean, high-confidence datasets for model training.',
                icon: <Layers size={28} />,
                color: '#7c3aed',
                bg: '#f5f3ff',
              },
            ].map((block, i) => (
              <div
                key={block.step}
                style={{
                  position: 'relative',
                  backgroundColor: block.bg,
                  borderRadius: '20px',
                  padding: '36px 30px',
                  border: `1.5px solid ${block.color}25`,
                  transition: 'all 0.25s ease',
                }}
                onMouseOver={(e) => {
                  e.currentTarget.style.transform = 'translateY(-4px)';
                  e.currentTarget.style.boxShadow = `0 12px 30px ${block.color}15`;
                }}
                onMouseOut={(e) => {
                  e.currentTarget.style.transform = 'translateY(0)';
                  e.currentTarget.style.boxShadow = 'none';
                }}
              >
                <div
                  style={{
                    fontSize: '2rem',
                    fontWeight: 900,
                    color: block.color,
                    opacity: 0.85,
                    marginBottom: '16px',
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                  }}
                >
                  <span>{block.step}</span>
                  <div
                    style={{
                      width: '48px',
                      height: '48px',
                      borderRadius: '12px',
                      backgroundColor: '#ffffff',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      color: block.color,
                      boxShadow: '0 4px 10px rgba(0,0,0,0.05)',
                    }}
                  >
                    {block.icon}
                  </div>
                </div>
                <h3 style={{ fontSize: '1.25rem', fontWeight: 800, color: '#0f172a', marginBottom: '10px' }}>
                  {block.title}
                </h3>
                <p style={{ fontSize: '0.94rem', color: '#475569', lineHeight: 1.6 }}>{block.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>


      {/* ─── SECTION 4: OUR PLATFORM ─── */}
      <section style={{ padding: '96px 64px', backgroundColor: '#fafffe' }}>
        <div style={{ maxWidth: '1140px', margin: '0 auto' }}>
          <div style={{ textAlign: 'center', maxWidth: '750px', margin: '0 auto 60px' }}>
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
              }}
            >
              <Layers size={14} /> COMPLETE WORKFLOW
            </div>
            <h2 style={{ fontSize: '2.6rem', fontWeight: 800, color: '#0f172a', letterSpacing: '-0.02em', marginBottom: '14px' }}>
              One Platform. Complete Dataset Workflow.
            </h2>
            <p style={{ fontSize: '1.05rem', color: '#64748b' }}>
              Structured dataset creation capabilities built into a clean, unified interface.
            </p>
          </div>

          {/* Dynamic 4 Feature Showcase (Interactive Tabs / Pill Highlights) */}
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))',
              gap: '20px',
            }}
          >
            {workflowSteps.map((ws, index) => {
              const isActive = activeWorkflowTab === index;
              return (
                <div
                  key={ws.title}
                  onClick={() => setActiveWorkflowTab(index)}
                  style={{
                    backgroundColor: isActive ? '#ffffff' : '#f8fafc',
                    borderRadius: '16px',
                    padding: '28px 24px',
                    border: isActive ? `2px solid ${ws.color}` : '1.5px solid #e2e8f0',
                    boxShadow: isActive ? `0 10px 25px ${ws.color}18` : 'none',
                    cursor: 'pointer',
                    transition: 'all 0.22s ease',
                  }}
                >
                  <div
                    style={{
                      display: 'inline-block',
                      fontSize: '0.72rem',
                      fontWeight: 800,
                      color: ws.color,
                      backgroundColor: `${ws.color}15`,
                      padding: '4px 10px',
                      borderRadius: '10px',
                      marginBottom: '16px',
                    }}
                  >
                    {ws.badge}
                  </div>
                  <div
                    style={{
                      width: '44px',
                      height: '44px',
                      borderRadius: '12px',
                      backgroundColor: `${ws.color}15`,
                      color: ws.color,
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      marginBottom: '16px',
                    }}
                  >
                    {ws.icon}
                  </div>
                  <h3 style={{ fontSize: '1.15rem', fontWeight: 800, color: '#0f172a', marginBottom: '10px' }}>
                    {ws.title}
                  </h3>
                  <p style={{ fontSize: '0.88rem', color: '#64748b', lineHeight: 1.6 }}>{ws.desc}</p>
                </div>
              );
            })}
          </div>
        </div>
      </section>

      {/* ─── SECTION 5: HOW ZWM CREATES VALUE ─── */}
      <section
        style={{
          padding: '96px 64px',
          backgroundColor: '#ffffff',
          borderTop: '1px solid #edf5ed',
        }}
      >
        <div style={{ maxWidth: '1140px', margin: '0 auto' }}>
          <div style={{ textAlign: 'center', maxWidth: '750px', margin: '0 auto 60px' }}>
            <div
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '8px',
                backgroundColor: '#f0fdf4',
                color: '#168a1a',
                padding: '6px 16px',
                borderRadius: '20px',
                fontSize: '0.82rem',
                fontWeight: 700,
                marginBottom: '16px',
              }}
            >
              <ShieldCheck size={14} /> KEY ADVANTAGES
            </div>
            <h2 style={{ fontSize: '2.6rem', fontWeight: 800, color: '#0f172a', letterSpacing: '-0.02em' }}>
              How ZWM Creates Value
            </h2>
          </div>

          {/* Clean 4 Value Horizontal Rows */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            {[
              {
                title: 'Better Data Quality',
                text: 'Structured annotations and validation workflows prevent label noise, ensuring clean and accurate datasets.',
                icon: <Target size={24} color="#168a1a" />,
              },
              {
                title: 'Faster Dataset Creation',
                text: 'A centralized workflow reduces manual friction in image handling, tagging, and annotation management.',
                icon: <Zap size={24} color="#168a1a" />,
              },
              {
                title: 'Organized Data Management',
                text: 'Images, waste categories, annotation coordinates, and validation records remain linked in a central database.',
                icon: <FolderKanban size={24} color="#168a1a" />,
              },
              {
                title: 'AI Training Support',
                text: 'Validated datasets seamlessly export into standard formats for immediate training with YOLO models.',
                icon: <Cpu size={24} color="#168a1a" />,
              },
            ].map((v) => (
              <div
                key={v.title}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '24px',
                  backgroundColor: '#f8fafc',
                  borderRadius: '16px',
                  padding: '24px 32px',
                  border: '1px solid #e2e8f0',
                  transition: 'all 0.2s ease',
                }}
                onMouseOver={(e) => {
                  e.currentTarget.style.backgroundColor = '#f0fdf4';
                  e.currentTarget.style.borderColor = '#bbf7d0';
                }}
                onMouseOut={(e) => {
                  e.currentTarget.style.backgroundColor = '#f8fafc';
                  e.currentTarget.style.borderColor = '#e2e8f0';
                }}
              >
                <div
                  style={{
                    width: '52px',
                    height: '52px',
                    borderRadius: '14px',
                    backgroundColor: '#ffffff',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    flexShrink: 0,
                    boxShadow: '0 4px 12px rgba(0,0,0,0.04)',
                  }}
                >
                  {v.icon}
                </div>
                <div>
                  <h3 style={{ fontSize: '1.15rem', fontWeight: 800, color: '#0f172a', marginBottom: '4px' }}>
                    {v.title}
                  </h3>
                  <p style={{ fontSize: '0.94rem', color: '#475569', lineHeight: 1.55 }}>{v.text}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ─── SECTION 6: OUR VISION ─── */}
      <section
        style={{
          padding: '96px 64px',
          backgroundColor: '#f6fbf5',
          borderTop: '1px solid #e9f5e9',
          textAlign: 'center',
        }}
      >
        <div style={{ maxWidth: '860px', margin: '0 auto' }}>
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
              marginBottom: '24px',
            }}
          >
            <Leaf size={14} /> OUR VISION
          </div>

          <h2
            style={{
              fontSize: '2.4rem',
              fontWeight: 800,
              color: '#168a1a',
              lineHeight: 1.3,
              marginBottom: '24px',
              fontStyle: 'italic',
            }}
          >
            "To make waste-management AI smarter by making the data behind it better."
          </h2>

          <p style={{ fontSize: '1.08rem', color: '#334155', lineHeight: 1.75, marginBottom: '48px' }}>
            ZWM aims to create a collaborative ecosystem where real-world waste images can be transformed into reliable datasets, helping researchers, developers, and organizations build better computer-vision systems for waste management.
          </p>

          {/* Animated Ecosystem Visual Strip */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '14px',
              flexWrap: 'wrap',
              backgroundColor: '#ffffff',
              padding: '24px 32px',
              borderRadius: '20px',
              boxShadow: '0 8px 24px rgba(22,138,26,0.08)',
              border: '1px solid #d1fae5',
            }}
          >
            {['Real World Waste', 'Data', 'Knowledge', 'AI', 'Smarter Waste Management'].map((node, idx, arr) => (
              <React.Fragment key={node}>
                <span
                  style={{
                    fontWeight: 800,
                    fontSize: '0.94rem',
                    color: idx === arr.length - 1 ? '#168a1a' : '#1e293b',
                    backgroundColor: idx === arr.length - 1 ? '#f0fdf4' : '#f8fafc',
                    padding: '8px 16px',
                    borderRadius: '12px',
                    border: idx === arr.length - 1 ? '1.5px solid #168a1a' : '1px solid #e2e8f0',
                  }}
                >
                  {node}
                </span>
                {idx < arr.length - 1 && (
                  <span style={{ color: '#168a1a', fontWeight: 800, fontSize: '1.2rem' }}>→</span>
                )}
              </React.Fragment>
            ))}
          </div>
        </div>
      </section>

      {/* ─── SECTION 7: FINAL CTA ─── */}
      <section
        style={{
          padding: '88px 64px',
          background: 'linear-gradient(135deg, #168a1a 0%, #137516 100%)',
          color: '#ffffff',
          textAlign: 'center',
        }}
      >
        <div style={{ maxWidth: '800px', margin: '0 auto' }}>
          <h2 style={{ fontSize: '2.8rem', fontWeight: 800, marginBottom: '18px', letterSpacing: '-0.02em' }}>
            Every Image Can Help Build a Smarter Future
          </h2>
          <p style={{ fontSize: '1.1rem', opacity: 0.9, lineHeight: 1.6, marginBottom: '36px' }}>
            Contribute real-world waste images, create quality annotations, and help build datasets for the next generation of waste-management AI.
          </p>

          <div style={{ display: 'flex', justifyContent: 'center', gap: '16px', flexWrap: 'wrap' }}>
            <button
              onClick={() => navigate('/register')}
              style={{
                padding: '14px 32px',
                borderRadius: '10px',
                backgroundColor: '#ffffff',
                color: '#168a1a',
                fontWeight: 800,
                fontSize: '1rem',
                border: 'none',
                cursor: 'pointer',
                boxShadow: '0 6px 20px rgba(0,0,0,0.15)',
                transition: 'all 0.2s',
              }}
              onMouseOver={(e) => (e.currentTarget.style.transform = 'translateY(-2px)')}
              onMouseOut={(e) => (e.currentTarget.style.transform = 'translateY(0)')}
            >
              Get Started
            </button>
            <button
              onClick={() => navigate('/landing')}
              style={{
                padding: '14px 32px',
                borderRadius: '10px',
                backgroundColor: 'transparent',
                color: '#ffffff',
                fontWeight: 700,
                fontSize: '1rem',
                border: '1.5px solid rgba(255,255,255,0.6)',
                cursor: 'pointer',
                transition: 'all 0.2s',
              }}
              onMouseOver={(e) => (e.currentTarget.style.backgroundColor = 'rgba(255,255,255,0.1)')}
              onMouseOut={(e) => (e.currentTarget.style.backgroundColor = 'transparent')}
            >
              Learn How It Works
            </button>
          </div>
        </div>
      </section>

      {/* ─── FOOTER ─── */}
      <footer
        className="landing-footer"
        style={{
          padding: '32px 64px',
          backgroundColor: '#0f172a',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <ZwmLogo size={34} />
          <span style={{ color: '#94a3b8', fontSize: '0.9rem', fontWeight: 600 }}>
            ZWM — Zero Waste Management
          </span>
        </div>
        <p style={{ color: '#475569', fontSize: '0.84rem' }}>
          © 2026 ZWM. Building a cleaner planet, one image at a time.
        </p>
      </footer>
    </div>
  );
};

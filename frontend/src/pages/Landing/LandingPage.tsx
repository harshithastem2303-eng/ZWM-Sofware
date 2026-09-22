import React, { useRef, useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Cloud, Leaf, Upload, Tag, CheckSquare, Database, ChevronRight, ChevronDown, ChevronUp, Menu, X } from 'lucide-react';
import { ZwmLogo } from '../../assets/icons/ZwmLogo';

export const LandingPage: React.FC = () => {
  const navigate = useNavigate();

  // Refs for smooth scrolling
  const homeRef = useRef<HTMLDivElement>(null);
  const aboutRef = useRef<HTMLDivElement>(null);
  const howItWorksRef = useRef<HTMLDivElement>(null);

  // State to trigger animations every time section enters viewport or button is clicked
  const [isHowItWorksInView, setIsHowItWorksInView] = useState(false);
  const [isAboutInView, setIsAboutInView] = useState(false);

  // Key state counters to force React remount & re-trigger CSS animations on button click
  const [aboutKey, setAboutKey] = useState(0);
  const [howItWorksKey, setHowItWorksKey] = useState(0);

  // State for mobile step info box expansion on touch
  const [expandedMobileStep, setExpandedMobileStep] = useState<string | null>(null);

  // State for mobile sidebar drawer navigation
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);

  // State for FAQ accordion expansion (first item open by default)
  const [openFaqIndex, setOpenFaqIndex] = useState<number | null>(0);

  const faqData = [
    {
      question: 'What is Zero Waste Management (ZWM)?',
      answer: (
        <span>
          ZWM is an AI-assisted platform for collecting, annotating, validating, and managing waste image datasets to support computer-vision-based waste detection.
        </span>
      ),
    },
    {
      question: 'How do I capture or upload waste images?',
      answer: (
        <span>
          Users can <strong>capture waste images using their device camera or upload existing images</strong> through the Upload Image section.
        </span>
      ),
    },
    {
      question: 'How do I annotate and categorize waste images?',
      answer: (
        <span>
          Users can identify waste objects through <strong>polygon-based annotation</strong> and assign the appropriate category, such as Plastic, Paper, Glass, or Metal.
        </span>
      ),
    },
    {
      question: 'How does ZWM ensure dataset quality and validation?',
      answer: (
        <span>
          ZWM maintains structured image, annotation, category, and validation records, helping ensure that only <strong>accurate and properly categorized images</strong> are included in the dataset.
        </span>
      ),
    },
    {
      question: 'How are the validated datasets used for AI model training?',
      answer: (
        <span>
          Validated datasets can be used as input for <strong>YOLO-based model training</strong>, helping develop AI systems for automated waste detection and classification.
        </span>
      ),
    },
  ];

  // Navigation active & hover states for dynamic green underline bar (Desktop)
  const [activeNav, setActiveNav] = useState<'home' | 'about' | 'how' | 'contact'>('home');
  const [hoveredNav, setHoveredNav] = useState<'home' | 'about' | 'how' | 'contact' | null>(null);

  // Refs for nav elements to compute sliding underline position
  const navHomeRef = useRef<HTMLDivElement>(null);
  const navAboutRef = useRef<HTMLDivElement>(null);
  const navHowRef = useRef<HTMLDivElement>(null);
  const navContactRef = useRef<HTMLDivElement>(null);

  const [indicatorStyle, setIndicatorStyle] = useState<{ left: number; width: number }>({ left: 0, width: 0 });

  const currentHighlight = hoveredNav || activeNav;

  useEffect(() => {
    let targetEl: HTMLDivElement | null = null;
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

  const toggleStepExpand = (stepNum: string) => {
    setExpandedMobileStep((prev) => (prev === stepNum ? null : stepNum));
  };

  useEffect(() => {
    const homeObserver = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setActiveNav('home');
        }
      },
      { threshold: 0.3 }
    );

    const howObserver = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setIsHowItWorksInView(true);
          setActiveNav('how');
        }
      },
      { threshold: 0.2 }
    );

    const aboutObserver = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setIsAboutInView(true);
          setActiveNav('about');
        }
      },
      { threshold: 0.25 }
    );

    if (homeRef.current) homeObserver.observe(homeRef.current);
    if (howItWorksRef.current) howObserver.observe(howItWorksRef.current);
    if (aboutRef.current) aboutObserver.observe(aboutRef.current);

    return () => {
      homeObserver.disconnect();
      howObserver.disconnect();
      aboutObserver.disconnect();
    };
  }, []);

  const scrollTo = (ref: React.RefObject<HTMLDivElement | null>) => {
    ref.current?.scrollIntoView({ behavior: 'smooth' });
  };

  const handleNavAbout = () => {
    setActiveNav('about');
    setAboutKey((prev) => prev + 1);
    setIsAboutInView(true);
    aboutRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  const handleNavHowItWorks = () => {
    setActiveNav('how');
    setHowItWorksKey((prev) => prev + 1);
    setIsHowItWorksInView(true);
    howItWorksRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  return (
    <div style={{ minHeight: '100vh', backgroundColor: '#ffffff', display: 'flex', flexDirection: 'column', fontFamily: 'var(--font-sans)', overflowX: 'hidden' }}>

      {/* ─── STICKY NAVBAR ─── */}
      <header className="landing-header" style={{
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
      }}>
        {/* Logo */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px', cursor: 'pointer' }} onClick={() => { setActiveNav('home'); scrollTo(homeRef); }}>
          <ZwmLogo size={44} />
          <div>
            <div style={{ fontSize: '1.4rem', fontWeight: 800, color: '#168a1a', lineHeight: 1 }}>ZWM</div>
            <div style={{ fontSize: '0.7rem', color: '#555', fontWeight: 600, letterSpacing: '0.02em' }}>Zero Waste Management</div>
          </div>
        </div>

        {/* Desktop Nav Links with Dynamic Moving Green Underline Bar */}
        <nav
          className="landing-nav-links desktop-nav-only"
          onMouseLeave={() => setHoveredNav(null)}
          style={{ display: 'flex', gap: '36px', fontWeight: 600, fontSize: '0.95rem', position: 'relative', paddingBottom: '6px' }}
        >
          <div
            ref={navHomeRef}
            onMouseEnter={() => setHoveredNav('home')}
            onClick={() => { setActiveNav('home'); scrollTo(homeRef); }}
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
            onClick={() => { setActiveNav('about'); navigate('/about'); }}
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
            onClick={() => { setActiveNav('how'); navigate('/how-it-works'); }}
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
            onClick={() => { setActiveNav('contact'); navigate('/contact'); }}
            style={{
              cursor: 'pointer',
              color: currentHighlight === 'contact' ? '#168a1a' : '#1e293b',
              fontWeight: currentHighlight === 'contact' ? 700 : 600,
              transition: 'color 0.2s',
            }}
          >
            Contact
          </div>

          {/* Dynamic Animated Sliding Green Line Indicator */}
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

        {/* Desktop Auth Buttons */}
        <div className="landing-auth-btns desktop-nav-only" style={{ display: 'flex', gap: '14px' }}>
          <button
            onClick={() => navigate('/login')}
            style={{
              padding: '10px 26px', borderRadius: '8px',
              border: '1.5px solid #168a1a', backgroundColor: 'transparent',
              color: '#168a1a', fontWeight: 700, fontSize: '0.95rem', cursor: 'pointer',
              transition: 'all 0.2s',
            }}
            onMouseOver={e => { e.currentTarget.style.backgroundColor = '#f0fdf4'; }}
            onMouseOut={e => { e.currentTarget.style.backgroundColor = 'transparent'; }}
          >
            Log In
          </button>
          <button
            onClick={() => navigate('/register')}
            style={{
              padding: '10px 26px', borderRadius: '8px',
              border: 'none', backgroundColor: '#168a1a',
              color: '#ffffff', fontWeight: 700, fontSize: '0.95rem', cursor: 'pointer',
              boxShadow: '0 4px 12px rgba(22,138,26,0.22)',
              transition: 'all 0.2s',
            }}
            onMouseOver={e => { e.currentTarget.style.backgroundColor = '#137516'; }}
            onMouseOut={e => { e.currentTarget.style.backgroundColor = '#168a1a'; }}
          >
            Sign Up
          </button>
        </div>

        {/* Mobile Hamburger Toggle Button */}
        <button
          className="mobile-menu-toggle-btn"
          onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
          aria-label="Toggle Navigation Menu"
        >
          {isMobileMenuOpen ? <X size={26} /> : <Menu size={26} />}
        </button>

        {/* Mobile Backdrop */}
        {isMobileMenuOpen && (
          <div
            className="mobile-menu-backdrop"
            onClick={() => setIsMobileMenuOpen(false)}
          />
        )}

        {/* Mobile Slide-Out Sidebar Drawer */}
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
            <button onClick={() => { scrollTo(homeRef); setIsMobileMenuOpen(false); }}>Home</button>
            <button onClick={() => { navigate('/about'); setIsMobileMenuOpen(false); }}>About</button>
            <button onClick={() => { handleNavHowItWorks(); setIsMobileMenuOpen(false); }}>How it Works</button>
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

      {/* ─── SECTION 1: HOME HERO ─── */}
      <section ref={homeRef} className="landing-hero-section" style={{
        display: 'flex',
        alignItems: 'center',
        padding: '60px 64px',
        gap: '48px',
        minHeight: 'calc(100vh - 74px)',
        backgroundColor: '#fafffe',
      }}>
        {/* Left: Text */}
        <div className="landing-hero-text-container" style={{ flex: 1, position: 'relative' }}>
          {/* Decorative leaves */}
          <div className="hero-decorative-leaf" style={{ position: 'absolute', top: -20, left: -30, opacity: 0.35, pointerEvents: 'none' }}>
            <Leaf size={52} color="#add192" strokeWidth={1} style={{ transform: 'rotate(-30deg)' }} />
          </div>
          <div className="hero-decorative-leaf" style={{ position: 'absolute', bottom: 0, right: '5%', opacity: 0.3, pointerEvents: 'none' }}>
            <Leaf size={36} color="#add192" strokeWidth={1} style={{ transform: 'rotate(40deg)' }} />
          </div>
          <div className="hero-decorative-leaf" style={{ position: 'absolute', top: '45%', left: '-10px', opacity: 0.2, pointerEvents: 'none' }}>
            <div style={{ width: 8, height: 8, borderRadius: '50%', backgroundColor: '#168a1a' }} />
          </div>

          {/* AI Badge */}
          <div style={{
            display: 'inline-flex', alignItems: 'center', gap: '7px',
            backgroundColor: '#f0fdf4', color: '#168a1a',
            padding: '7px 16px', borderRadius: '20px',
            fontSize: '0.84rem', fontWeight: 700, marginBottom: '28px',
            border: '1px solid #d1fae5',
          }}>
            <Cloud size={15} strokeWidth={2.5} /> AI-Powered Waste Detection
          </div>

          {/* Headline */}
          <h1 className="landing-hero-title" style={{
            fontSize: '4rem', fontWeight: 800, color: '#0f172a',
            lineHeight: 1.1, marginBottom: '0', letterSpacing: '-0.025em',
          }}>
            Zero Waste
          </h1>
          <h1 className="landing-hero-title" style={{
            fontSize: '4rem', fontWeight: 800,
            color: '#168a1a', lineHeight: 1.1, marginBottom: '22px', letterSpacing: '-0.025em',
            display: 'flex', alignItems: 'center', gap: '12px',
          }}>
            Management <Leaf className="hero-title-leaf" size={38} color="#add192" fill="#add192" style={{ transform: 'rotate(15deg) translateY(4px)', display: 'inline-block' }} />
          </h1>

          <p className="desktop-nav-only" style={{ fontSize: '1.2rem', fontWeight: 700, color: '#1e293b', marginBottom: '14px' }}>
            A cleaner tomorrow starts with smarter today.
          </p>
          <p className="mobile-only-subtitle">
            Smart AI for a cleaner tomorrow.
          </p>

          <p className="desktop-nav-only" style={{ fontSize: '1.05rem', color: '#475569', lineHeight: 1.65, marginBottom: '36px', maxWidth: '500px' }}>
            ZWM uses advanced AI to detect, classify, and manage waste efficiently. Together, we can build a cleaner, greener, and healthier environment.
          </p>
          <p className="mobile-only-para">
            AI-powered waste detection to classify, annotate, and manage datasets for a cleaner environment.
          </p>

          {/* CTAs */}
          <div className="hero-cta-wrapper" style={{ display: 'flex', gap: '16px', flexWrap: 'wrap' }}>
            <button
              className="hero-btn-upload"
              onClick={() => navigate('/register')}
              style={{
                padding: '14px 30px', borderRadius: '10px', border: 'none',
                backgroundColor: '#168a1a', color: '#ffffff', fontWeight: 700,
                fontSize: '1.02rem', cursor: 'pointer',
                display: 'flex', alignItems: 'center', gap: '9px',
                boxShadow: '0 5px 15px rgba(22,138,26,0.28)',
                transition: 'all 0.2s',
              }}
              onMouseOver={e => { e.currentTarget.style.transform = 'translateY(-2px)'; }}
              onMouseOut={e => { e.currentTarget.style.transform = 'translateY(0)'; }}
            >
              <Cloud size={20} /> Upload Image
            </button>
            <button
              className="hero-btn-learn-more"
              onClick={handleNavAbout}
              style={{
                padding: '14px 30px', borderRadius: '10px',
                border: '1.5px solid #d1d5db', backgroundColor: '#ffffff',
                color: '#1e293b', fontWeight: 700, fontSize: '1.02rem', cursor: 'pointer',
                transition: 'all 0.2s',
              }}
              onMouseOver={e => { e.currentTarget.style.borderColor = '#168a1a'; e.currentTarget.style.color = '#168a1a'; }}
              onMouseOut={e => { e.currentTarget.style.borderColor = '#d1d5db'; e.currentTarget.style.color = '#1e293b'; }}
            >
              Learn More
            </button>
          </div>
        </div>

        {/* Right: Hero Visual (Balanced Full View with Tight Object Segmentation) */}
        <div className="landing-hero-visual hero-image-animated" style={{ flex: 1, maxWidth: '560px', width: '100%', position: 'relative' }}>
          <div className="landing-hero-image-wrapper" style={{
            width: '100%', borderRadius: '20px',
            overflow: 'hidden',
            boxShadow: '0 24px 48px rgba(0,0,0,0.12)',
            position: 'relative',
          }}>
            <img
              src="/images/hero-waste.jpg"
              alt="AI Waste Detection Scene"
              style={{ width: '100%', height: 'auto', display: 'block', borderRadius: '20px' }}
            />
            {/* Bounding Boxes (YOLO Annotation Overlays tightly segmenting real waste objects) */}
            <BBox label="Plastic" score="96%" color="#3b82f6" delay="0.90s" style={{ top: '79.5%', left: '13.5%', width: '22%', height: '13%' }} />
            <BBox label="Paper" score="92%" color="#22c55e" delay="1.05s" style={{ top: '71.5%', left: '36.5%', width: '12%', height: '12%' }} />
            <BBox label="Glass" score="95%" color="#f97316" delay="1.20s" style={{ top: '80%', left: '48.5%', width: '19.5%', height: '13%' }} />
            <BBox label="Metal" score="89%" color="#a855f7" delay="1.35s" style={{ top: '83.5%', left: '78.5%', width: '14%', height: '10%' }} />
          </div>

          {/* Floating AI Card */}
          <div className="landing-hero-popup-card hero-popup-card-animated" style={{
            position: 'absolute', top: '32px', left: '-28px',
            backgroundColor: '#ffffff', borderRadius: '16px',
            padding: '20px 24px', boxShadow: '0 12px 32px rgba(0,0,0,0.13)',
            width: '230px', zIndex: 10,
          }}>
            <p style={{ fontSize: '0.9rem', fontWeight: 700, color: '#0f172a', marginBottom: '14px' }}>AI Detection Result</p>
            <DetectionRow color="#3b82f6" label="Plastic Bottle" count="12" />
            <DetectionRow color="#22c55e" label="Paper" count="08" />
            <DetectionRow color="#f97316" label="Glass" count="05" />
            <DetectionRow color="#a855f7" label="Metal" count="04" />
          </div>
        </div>
      </section>

      {/* ─── SECTION 2: ABOUT ─── */}
      <section ref={aboutRef} className="landing-about-section" style={{
        padding: '88px 64px',
        backgroundColor: '#f6fbf5',
        borderTop: '1px solid #e9f5e9',
        position: 'relative',
        overflow: 'hidden',
      }}>
        <div key={aboutKey} style={{ maxWidth: '1140px', margin: '0 auto' }}>
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))',
            gap: '56px',
            alignItems: 'center',
          }}>
            {/* Left Content Column */}
            <div>
              <h2
                className={isAboutInView ? 'about-title-animated' : ''}
                style={{
                  fontSize: '2.6rem', fontWeight: 800, color: '#0f172a', marginBottom: '22px', letterSpacing: '-0.025em',
                  lineHeight: 1.2,
                  opacity: isAboutInView ? undefined : 0,
                  animationDelay: isAboutInView ? '0.1s' : '0s',
                }}
              >
                What is <span style={{ color: '#168a1a' }}>Zero Waste Management?</span>
              </h2>

              <p
                className={isAboutInView ? 'about-answer-animated' : ''}
                style={{
                  fontSize: '1.1rem', color: '#334155', lineHeight: 1.7, marginBottom: '20px',
                  fontWeight: 600,
                  opacity: isAboutInView ? undefined : 0,
                  animationDelay: isAboutInView ? '0.3s' : '0s',
                }}
              >
                <strong>Zero Waste Management (ZWM)</strong> is an AI-assisted platform that makes it simple to turn real-world waste photos into high-quality training datasets for AI waste detection models.
              </p>

              <p
                className={`about-para-optional ${isAboutInView ? 'about-answer-animated' : ''}`}
                style={{
                  fontSize: '1.02rem', color: '#475569', lineHeight: 1.7, marginBottom: '20px',
                  opacity: isAboutInView ? undefined : 0,
                  animationDelay: isAboutInView ? '0.5s' : '0s',
                }}
              >
                Users upload waste images, add simple annotations to label objects, and categorize items like Plastic, Paper, Glass, and Metal into organized datasets.
              </p>

              <p
                className={isAboutInView ? 'about-answer-animated' : ''}
                style={{
                  fontSize: '1.02rem', color: '#475569', lineHeight: 1.7,
                  opacity: isAboutInView ? undefined : 0,
                  animationDelay: isAboutInView ? '0.7s' : '0s',
                }}
              >
                These validated datasets help build smarter AI systems for automated waste sorting and recycling.
              </p>
            </div>

            {/* Right Column: Animated AI Dataset Scanner Showcase */}
            <div style={{ position: 'relative' }}>
              {/* Outer Card with Glass Shadow */}
              <div style={{
                backgroundColor: '#ffffff',
                borderRadius: '24px',
                padding: '28px',
                boxShadow: '0 20px 48px rgba(22, 138, 26, 0.12)',
                border: '1px solid #d1fae5',
                position: 'relative',
                overflow: 'hidden',
              }}>
                {/* Header Strip */}
                <div style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  paddingBottom: '14px',
                  marginBottom: '16px',
                  borderBottom: '1px solid #f1f5f9',
                }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <div style={{
                      width: '10px', height: '10px', borderRadius: '50%',
                      backgroundColor: '#22c55e',
                      boxShadow: '0 0 10px #22c55e',
                    }} />
                    <span style={{ fontSize: '0.86rem', fontWeight: 800, color: '#0f172a' }}>
                      ZWM Dataset Pipeline
                    </span>
                  </div>
                  <span style={{
                    fontSize: '0.72rem', fontWeight: 700,
                    color: '#168a1a', backgroundColor: '#f0fdf4',
                    padding: '4px 12px', borderRadius: '20px',
                    border: '1px solid #d1fae5',
                  }}>
                    Polygon Annotation Live
                  </span>
                </div>

                {/* Simulated Waste Image Scanning Box with User Uploaded Outdoor Waste Image */}
                <div style={{
                  height: '290px',
                  borderRadius: '16px',
                  position: 'relative',
                  overflow: 'hidden',
                  padding: '14px',
                  display: 'flex',
                  flexDirection: 'column',
                  justifyContent: 'space-between',
                  boxShadow: '0 8px 24px rgba(0,0,0,0.18)',
                }}>
                  {/* User Uploaded Outdoor Waste Background Image */}
                  <img
                    src="/images/outdoor-waste.jpg"
                    alt="Outdoor Real-World Waste Scene"
                    style={{
                      position: 'absolute',
                      top: 0,
                      left: 0,
                      width: '100%',
                      height: '100%',
                      objectFit: 'cover',
                      filter: 'brightness(0.95) contrast(1.05)',
                    }}
                  />

                  {/* Dark Gradient Overlay Mask */}
                  <div style={{
                    position: 'absolute',
                    top: 0, left: 0, right: 0, bottom: 0,
                    background: 'linear-gradient(180deg, rgba(15, 23, 42, 0.35) 0%, rgba(15, 23, 42, 0.05) 40%, rgba(15, 23, 42, 0.6) 100%)',
                    pointerEvents: 'none',
                  }} />

                  {/* Moving Laser Scanner Line */}
                  <div style={{
                    position: 'absolute',
                    top: 0,
                    left: 0,
                    right: 0,
                    height: '4px',
                    background: 'linear-gradient(90deg, transparent, #22c55e 30%, #add192 50%, #22c55e 70%, transparent)',
                    boxShadow: '0 0 18px #22c55e',
                    animation: 'laserScanCycle 4.2s ease-in-out infinite',
                    zIndex: 5,
                    pointerEvents: 'none',
                  }} />

                  {/* Bounding Box 1: HDPE Plastic (Reveals as Scanner Passes) */}
                  <div style={{
                    position: 'absolute',
                    top: '42%',
                    left: '13%',
                    width: '36%',
                    height: '38%',
                    border: '2.5px dashed #22c55e',
                    backgroundColor: 'rgba(34, 197, 94, 0.25)',
                    borderRadius: '10px',
                    boxShadow: '0 0 16px rgba(34, 197, 94, 0.45)',
                    animation: 'scanHdpeBox 4.2s ease-in-out infinite',
                    zIndex: 4,
                  }}>
                    <span style={{
                      position: 'absolute', top: '-24px', left: '-2px',
                      fontSize: '0.68rem', fontWeight: 800, color: '#ffffff',
                      backgroundColor: '#168a1a', padding: '2px 8px', borderRadius: '4px',
                      whiteSpace: 'nowrap', boxShadow: '0 2px 8px rgba(0,0,0,0.3)',
                      display: 'flex', alignItems: 'center', gap: '4px',
                    }}>
                      <span>HDPE Plastic</span>
                      <span style={{ opacity: 0.85, fontSize: '0.62rem' }}>97.4%</span>
                    </span>
                  </div>

                  {/* Bounding Box 2: PET Bottle (Reveals as Scanner Passes) */}
                  <div style={{
                    position: 'absolute',
                    top: '34%',
                    left: '63%',
                    width: '28%',
                    height: '22%',
                    border: '2.5px dashed #3b82f6',
                    backgroundColor: 'rgba(59, 130, 246, 0.25)',
                    borderRadius: '10px',
                    boxShadow: '0 0 16px rgba(59, 130, 246, 0.45)',
                    animation: 'scanPetBox 4.2s ease-in-out infinite',
                    zIndex: 4,
                  }}>
                    <span style={{
                      position: 'absolute', top: '-24px', left: '-2px',
                      fontSize: '0.68rem', fontWeight: 800, color: '#ffffff',
                      backgroundColor: '#3b82f6', padding: '2px 8px', borderRadius: '4px',
                      whiteSpace: 'nowrap', boxShadow: '0 2px 8px rgba(0,0,0,0.3)',
                      display: 'flex', alignItems: 'center', gap: '4px',
                    }}>
                      <span>PET Bottle</span>
                      <span style={{ opacity: 0.85, fontSize: '0.62rem' }}>98.8%</span>
                    </span>
                  </div>

                  {/* Top Bar Info */}
                  <div style={{ position: 'relative', zIndex: 6, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span style={{ fontSize: '0.74rem', fontWeight: 700, color: '#ffffff', backgroundColor: 'rgba(15, 23, 42, 0.75)', padding: '3px 10px', borderRadius: '6px', backdropFilter: 'blur(4px)' }}>
                      Polymer Class: HDPE & PET
                    </span>
                    <span style={{ fontSize: '0.74rem', fontWeight: 700, color: '#add192', backgroundColor: 'rgba(15, 23, 42, 0.75)', padding: '3px 10px', borderRadius: '6px', backdropFilter: 'blur(4px)' }}>
                      COCO / YOLO Export
                    </span>
                  </div>

                  {/* Bottom Bar Status */}
                  <div style={{ position: 'relative', zIndex: 6, display: 'flex', gap: '8px' }}>
                    <span style={{ fontSize: '0.7rem', fontWeight: 700, color: '#ffffff', backgroundColor: '#168a1a', padding: '4px 12px', borderRadius: '8px', boxShadow: '0 2px 8px rgba(22, 138, 26, 0.3)' }}>
                      Detected: HDPE Plastic + PET Bottle
                    </span>
                  </div>
                </div>

                {/* Progress Indicators Bar */}
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', marginTop: '16px' }}>
                  <div style={{ backgroundColor: '#f8fafc', padding: '12px 14px', borderRadius: '12px', border: '1px solid #e2e8f0' }}>
                    <div style={{ fontSize: '0.74rem', color: '#64748b', fontWeight: 600 }}>Dataset Accuracy</div>
                    <div style={{ fontSize: '1.2rem', fontWeight: 800, color: '#168a1a' }}>99.4%</div>
                  </div>
                  <div style={{ backgroundColor: '#f8fafc', padding: '12px 14px', borderRadius: '12px', border: '1px solid #e2e8f0' }}>
                    <div style={{ fontSize: '0.74rem', color: '#64748b', fontWeight: 600 }}>Training Compatibility</div>
                    <div style={{ fontSize: '1.2rem', fontWeight: 800, color: '#0f172a' }}>YOLOv8/v11</div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ─── SECTION 3: HOW IT WORKS ─── */}
      <section ref={howItWorksRef} className="landing-how-section" style={{
        padding: '96px 64px',
        backgroundColor: '#ffffff',
        borderTop: '1px solid #edf5ed',
      }}>
        <div key={howItWorksKey} style={{ maxWidth: '1000px', margin: '0 auto' }}>
          {/* Header */}
          <div className="landing-how-header" style={{ textAlign: 'center', marginBottom: '64px' }}>
            <h2 style={{ fontSize: '2.6rem', fontWeight: 800, color: '#0f172a', letterSpacing: '-0.02em' }}>
              How it <span style={{ color: '#168a1a' }}>Works</span>
            </h2>
            <p style={{ fontSize: '1.05rem', color: '#64748b', marginTop: '12px' }}>
              Five simple steps from image to trained model.
            </p>
          </div>

          {/* Steps - horizontal pipeline */}
          <div style={{ position: 'relative' }}>
            {/* Connector line - animated smooth flow starting from first upload icon */}
            <div className="landing-connector-line" style={{
              position: 'absolute', top: '52px', left: '10%', right: '10%', height: '4px',
              borderRadius: '4px', zIndex: 0, overflow: 'hidden',
              backgroundColor: 'transparent',
            }}>
              {/* Line fill extending smoothly from left to right */}
              <div
                className={`connector-line-fill ${isHowItWorksInView ? 'line-fill-animated' : ''}`}
                style={{
                  height: '100%',
                  width: isHowItWorksInView ? undefined : '0%',
                  background: 'linear-gradient(90deg, #168a1a 0%, #22c55e 50%, #4ade80 100%)',
                  borderRadius: '4px',
                  boxShadow: '0 0 12px rgba(34, 197, 94, 0.6)',
                }}
              />
              {/* Continuous glowing light pulse moving along line */}
              {isHowItWorksInView && (
                <div className="connector-light-pulse" />
              )}
            </div>

            <div className="landing-steps-container" style={{ display: 'flex', justifyContent: 'space-between', gap: '12px', position: 'relative', zIndex: 1 }}>
              <div className="mobile-vertical-timeline-line" />
              {[
                { num: '01', tag: '01 — Upload', iconClass: 'icon-upload', icon: <Upload size={26} />, label: 'Upload', desc: 'Upload your waste images from any device to the platform.' },
                { num: '02', tag: '02 — Annotate', iconClass: 'icon-annotate', icon: <Tag size={26} />, label: 'Annotate', desc: 'Draw polygon annotations around waste objects in the image.' },
                { num: '03', tag: '03 — Categorize', iconClass: 'icon-categorize', icon: <Leaf size={26} />, label: 'Categorize', desc: 'Assign category — Plastic, Paper, Glass, or Metal.' },
                { num: '04', tag: '04 — Validate', iconClass: 'icon-validate', icon: <CheckSquare size={26} />, label: 'Validate', desc: 'Review and validate annotations to ensure dataset quality.' },
                { num: '05', tag: '05 — Build Dataset', iconClass: 'icon-dataset', icon: <Database size={26} />, label: 'Build Dataset', desc: 'Export clean structured dataset ready for YOLO model training.' },
              ].map((step, i) => (
                <div
                  key={step.num}
                  className={`step-item-card ${isHowItWorksInView ? 'step-item-animated' : ''}`}
                  style={{
                    flex: 1,
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'center',
                    textAlign: 'center',
                    opacity: isHowItWorksInView ? undefined : 0,
                    animationDelay: isHowItWorksInView ? `${(i * 0.75).toFixed(2)}s` : '0s',
                  }}
                >
                  {/* Circle / 3D Squircle Icon Node */}
                  <div className={`step-circle-wrapper ${step.iconClass}`} style={{
                    width: '106px', height: '106px', borderRadius: '50%',
                    backgroundColor: i % 2 === 0 ? '#15803d' : '#ffffff',
                    border: `3px solid ${i % 2 === 0 ? '#15803d' : '#22c55e'}`,
                    display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
                    boxShadow: '0 8px 24px rgba(21, 128, 61, 0.18)',
                    color: i % 2 === 0 ? '#ffffff' : '#15803d',
                    marginBottom: '20px',
                    transition: 'all 0.35s cubic-bezier(0.34, 1.56, 0.64, 1)',
                    cursor: 'pointer',
                  }}>
                    {step.icon}
                    <span style={{ fontSize: '0.7rem', fontWeight: 700, marginTop: '4px', opacity: 0.85 }}>{step.num}</span>
                  </div>

                  {/* Text Content Wrapper */}
                  <div className="step-text-wrapper">
                    <span className="step-tag-text">{step.tag}</span>
                    <p className="step-title-text" style={{ fontSize: '1.05rem', fontWeight: 800, color: '#0f172a', marginBottom: '8px' }}>{step.label}</p>
                    <p className="step-desc" style={{ fontSize: '0.82rem', color: '#64748b', lineHeight: 1.55, maxWidth: '145px' }}>{step.desc}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* ─── SECTION 4: FAQ ─── */}
      <section className="landing-faq-section" style={{
        padding: '88px 64px',
        backgroundColor: '#ffffff',
        borderTop: '1px solid #edf5ed',
      }}>
        <div style={{ maxWidth: '960px', margin: '0 auto' }}>
          <h2 style={{
            fontSize: '2.6rem',
            fontWeight: 800,
            color: '#0f172a',
            marginBottom: '36px',
            letterSpacing: '-0.02em',
          }}>
            FAQ's
          </h2>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            {faqData.map((faq, index) => {
              const isOpen = openFaqIndex === index;
              return (
                <div
                  key={index}
                  className="faq-item-card"
                  style={{
                    backgroundColor: '#ffffff',
                    borderRadius: '12px',
                    border: '1px solid #e2e8f0',
                    overflow: 'hidden',
                    transition: 'all 0.25s ease',
                    boxShadow: isOpen ? '0 4px 20px rgba(0, 0, 0, 0.05)' : 'none',
                  }}
                >
                  <button
                    onClick={() => setOpenFaqIndex(isOpen ? null : index)}
                    style={{
                      width: '100%',
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      padding: '22px 28px',
                      backgroundColor: 'transparent',
                      border: 'none',
                      cursor: 'pointer',
                      textAlign: 'left',
                      gap: '16px',
                    }}
                  >
                    <span className="faq-question-text" style={{
                      fontSize: '1.08rem',
                      fontWeight: 700,
                      color: isOpen ? '#168a1a' : '#0f172a',
                      transition: 'color 0.2s ease',
                    }}>
                      {faq.question}
                    </span>
                    <span className="faq-icon-wrapper" style={{ color: isOpen ? '#168a1a' : '#64748b', display: 'flex', alignItems: 'center', flexShrink: 0, transition: 'color 0.2s ease' }}>
                      {isOpen ? <ChevronUp size={22} /> : <ChevronDown size={22} />}
                    </span>
                  </button>

                  {isOpen && (
                    <div style={{
                      padding: '0 28px 24px 28px',
                      fontSize: '0.98rem',
                      color: '#475569',
                      lineHeight: 1.65,
                      animation: 'fadeInAnswer 0.25s ease-out',
                    }}>
                      {faq.answer}
                    </div>
                  )}
                </div>
              );
            })}
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
        <p style={{ color: '#475569', fontSize: '0.84rem' }}>© 2026 ZWM. Building a cleaner planet, one image at a time.</p>
      </footer>

    </div>
  );
};

/* ── Small helper components ── */

const NavLink: React.FC<{ label: string; active?: boolean; onClick: () => void }> = ({ label, active, onClick }) => (
  <div
    onClick={onClick}
    style={{
      cursor: 'pointer',
      display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '4px',
      color: active ? '#168a1a' : '#1e293b',
      fontWeight: active ? 700 : 600,
      transition: 'color 0.15s',
    }}
    onMouseOver={e => { (e.currentTarget as HTMLDivElement).style.color = '#168a1a'; }}
    onMouseOut={e => { (e.currentTarget as HTMLDivElement).style.color = active ? '#168a1a' : '#1e293b'; }}
  >
    {label}
    {active && <div style={{ height: '2.5px', width: '100%', backgroundColor: '#168a1a', borderRadius: '2px' }} />}
  </div>
);

const BBox: React.FC<{ label: string; score?: string; color: string; style: React.CSSProperties; delay?: string }> = ({ label, score, color, style, delay = '0.9s' }) => (
  <div
    className="bbox-animated"
    style={{
      position: 'absolute',
      border: `2px solid ${color}`,
      backgroundColor: `${color}18`,
      borderRadius: '4px',
      boxShadow: `0 0 12px ${color}40`,
      transition: 'all 0.3s ease',
      pointerEvents: 'none',
      animationDelay: delay,
      ...style,
    }}
  >
    <div style={{
      position: 'absolute',
      top: '-24px',
      left: '-2px',
      backgroundColor: color,
      color: '#ffffff',
      padding: '2px 8px',
      fontSize: '0.72rem',
      fontWeight: 700,
      borderRadius: '4px 4px 0 0',
      display: 'flex',
      alignItems: 'center',
      gap: '4px',
      whiteSpace: 'nowrap',
      boxShadow: '0 2px 4px rgba(0,0,0,0.15)',
    }}>
      <span>{label}</span>
      {score && <span style={{ opacity: 0.85, fontSize: '0.66rem' }}>{score}</span>}
    </div>
  </div>
);

const DetectionRow: React.FC<{ color: string; label: string; count: string }> = ({ color, label, count }) => (
  <div style={{
    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
    paddingBottom: '10px', marginBottom: '10px',
    borderBottom: '1px solid #f1f5f9',
  }}>
    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.83rem', fontWeight: 600, color: '#334155' }}>
      <div style={{ width: '10px', height: '10px', borderRadius: '50%', backgroundColor: color, flexShrink: 0 }} />
      {label}
    </div>
    <span style={{ fontWeight: 800, color: '#168a1a', fontSize: '0.88rem' }}>{count}</span>
  </div>
);

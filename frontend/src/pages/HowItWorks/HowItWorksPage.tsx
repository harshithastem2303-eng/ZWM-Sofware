import React, { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Upload,
  Tag,
  Leaf,
  CheckSquare,
  Database,
  ChevronRight,
  ChevronLeft,
  ArrowRight,
  Sparkles,
  ShieldCheck,
  Cpu,
  Layers,
  CheckCircle2,
  Menu,
  X,
  FileCode,
  Box,
  Eye,
} from 'lucide-react';
import { ZwmLogo } from '../../assets/icons/ZwmLogo';
import { Footer } from '../../components/Footer';

const stepsData = [
  {
    num: '01',
    btnLabel: 'Upload',
    tag: 'Step 01 — Upload',
    title: 'Upload Waste Images',
    tagline: 'Upload photos of waste directly from your device',
    icon: <Upload size={28} />,
    color: '#168a1a',
    lightBg: '#f0fdf4',
    border: '#bbf7d0',
    description:
      'Capture or upload waste photos directly from your camera or gallery. Images are automatically validated for quality and tagged with location and timestamp metadata.',
    highlights: [
      'Direct mobile camera capture & simple drag-and-drop upload',
      'Automatic image quality and resolution verification',
      'GPS location & timestamp metadata tagging',
      'Batch upload support for uploading multiple waste photos at once',
    ],
    previewType: 'upload',
  },
  {
    num: '02',
    btnLabel: 'Annotate',
    tag: 'Step 02 — Annotate',
    title: 'Annotate Waste Boundaries',
    tagline: 'Draw precise bounding outlines around waste items',
    icon: <Tag size={28} />,
    color: '#0284c7',
    lightBg: '#f0f9ff',
    border: '#bae6fd',
    description:
      'Draw point-by-point polygon outlines and bounding boxes around waste items like PET bottles, milk pouches, and plastic covers to isolate them accurately from background objects.',
    highlights: [
      'Interactive polygon tracing directly over waste objects',
      'Precise bounding box generation for PET bottles & plastic pouches',
      'Separates overlapping waste items in complex garbage photos',
      'Easy node editing with instant undo and redo tools',
    ],
    previewType: 'annotate',
  },
  {
    num: '03',
    btnLabel: 'Label',
    tag: 'Step 03 — Label',
    title: 'Label & Categorize Waste',
    tagline: 'Assign waste labels: PET bottles, milk pouches, & more',
    icon: <Leaf size={28} />,
    color: '#d97706',
    lightBg: '#fffbe6',
    border: '#fef08a',
    description:
      'Label and sort waste into clear categories such as PET bottles, milk pouches, plastic covers, cardboard boxes, and glass containers for efficient recycling.',
    highlights: [
      'Categorizes specific waste items: PET Bottles & Milk Pouches',
      'Identifies plastic covers, wrappers, cardboard, and metal cans',
      'Automated AI class recommendations with confidence scores',
      'Color-coded category tags for clean dataset organization',
    ],
    previewType: 'categorize',
  },
  {
    num: '04',
    btnLabel: 'Train',
    tag: 'Step 04 — Train',
    title: 'Train AI Model',
    tagline: 'Train computer vision models with prepared datasets',
    icon: <Database size={28} />,
    color: '#7c3aed',
    lightBg: '#f5f3ff',
    border: '#ddd6fe',
    description:
      'Train and export verified waste datasets in standard computer vision formats like YOLO and COCO. Ready for instant AI model training for waste classification.',
    highlights: [
      'Automated YOLOv8 and YOLOv11 dataset zip file generation',
      'Standardized COCO JSON & VOC XML annotation exports',
      'Direct compatibility with PyTorch training pipelines',
      'Version-controlled dataset releases for model retraining',
    ],
    previewType: 'dataset',
  },
];

export const HowItWorksPage: React.FC = () => {
  const navigate = useNavigate();
  const [activeStep, setActiveStep] = useState(0);
  const [hoveredNav, setHoveredNav] = useState<'home' | 'about' | 'how' | 'contact' | null>(null);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const [isAutoplay, setIsAutoplay] = useState(true);

  const navHomeRef = useRef<HTMLDivElement>(null);
  const navAboutRef = useRef<HTMLDivElement>(null);
  const navHowRef = useRef<HTMLDivElement>(null);
  const navContactRef = useRef<HTMLDivElement>(null);

  const [indicatorStyle, setIndicatorStyle] = useState<{ left: number; width: number }>({ left: 0, width: 0 });

  const currentHighlight = hoveredNav || 'how';

  useEffect(() => {
    let targetEl: HTMLDivElement | null = navHowRef.current;
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

  // Autoplay Effect (5s per step)
  useEffect(() => {
    if (!isAutoplay) return;
    const timer = setInterval(() => {
      setActiveStep((prev) => (prev + 1) % stepsData.length);
    }, 5000);
    return () => clearInterval(timer);
  }, [isAutoplay]);

  const safeStepIndex = activeStep >= stepsData.length ? 0 : activeStep;
  const currentStep = stepsData[safeStepIndex] || stepsData[0];

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
            onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })}
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
            <button onClick={() => { window.scrollTo({ top: 0 }); setIsMobileMenuOpen(false); }}>How it Works</button>
            <button onClick={() => { navigate('/contact'); setIsMobileMenuOpen(false); }}>Contact</button>
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

      {/* ─── HERO HEADER ─── */}
      <section style={{
        padding: '72px 64px 48px',
        background: 'linear-gradient(180deg, #f6fbf5 0%, #ffffff 100%)',
        borderBottom: '1px solid #edf5ed',
      }}>
        <div style={{ maxWidth: '1140px', margin: '0 auto', textAlign: 'center' }}>
          <div style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '8px',
            backgroundColor: '#e8f5e9',
            color: '#168a1a',
            padding: '6px 18px',
            borderRadius: '20px',
            fontSize: '0.84rem',
            fontWeight: 700,
            marginBottom: '20px',
            border: '1px solid #c8e6c9',
          }}>
            <Sparkles size={15} /> INTERACTIVE PIPELINE WALKTHROUGH
          </div>

          <h1 style={{
            fontSize: '2.8rem',
            fontWeight: 800,
            color: '#0f172a',
            lineHeight: 1.2,
            letterSpacing: '-0.025em',
            marginBottom: '16px',
          }}>
            How ZWM Turns Waste Photos into{' '}
            <span style={{ color: '#168a1a' }}>Trained AI Models</span>
          </h1>

          <p style={{
            fontSize: '1.1rem',
            color: '#475569',
            maxWidth: '760px',
            margin: '0 auto 40px auto',
            lineHeight: 1.65,
          }}>
            Click through our 4-step interactive workflow below to see how waste images are captured, annotated, categorized, and audited.
          </p>

          {/* ─── STEP SELECTION PIPELINE BAR ─── */}
          <div style={{
            display: 'flex',
            justifyContent: 'center',
            gap: '12px',
            flexWrap: 'wrap',
            marginBottom: '20px',
          }}>
            {stepsData.slice(0, 4).map((step, index) => {
              const isActive = activeStep === index;
              return (
                <button
                  key={step.num}
                  onClick={() => {
                    setActiveStep(index);
                    setIsAutoplay(false);
                  }}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '10px',
                    padding: '12px 22px',
                    borderRadius: '30px',
                    border: isActive ? `2px solid ${step.color}` : '1.5px solid #e2e8f0',
                    backgroundColor: isActive ? step.lightBg : '#ffffff',
                    color: isActive ? step.color : '#475569',
                    fontWeight: isActive ? 800 : 600,
                    fontSize: '0.92rem',
                    cursor: 'pointer',
                    boxShadow: isActive ? `0 6px 18px ${step.color}25` : '0 2px 6px rgba(0,0,0,0.03)',
                    transition: 'all 0.25s cubic-bezier(0.34, 1.56, 0.64, 1)',
                  }}
                  onMouseOver={(e) => {
                    if (!isActive) e.currentTarget.style.borderColor = step.color;
                  }}
                  onMouseOut={(e) => {
                    if (!isActive) e.currentTarget.style.borderColor = '#e2e8f0';
                  }}
                >
                  <span style={{
                    width: '26px',
                    height: '26px',
                    borderRadius: '50%',
                    backgroundColor: isActive ? step.color : '#f1f5f9',
                    color: isActive ? '#ffffff' : '#64748b',
                    fontSize: '0.74rem',
                    fontWeight: 800,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                  }}>
                    {step.num}
                  </span>
                  <span>{step.btnLabel || step.title.split(' ')[0]}</span>
                </button>
              );
            })}
          </div>
        </div>
      </section>

      {/* ─── MAIN INTERACTIVE SHOWCASE (MATCHING USER REFERENCE DESIGN) ─── */}
      <section style={{ padding: '64px 64px 96px', backgroundColor: '#ffffff', position: 'relative' }}>
        <div style={{ maxWidth: '1140px', margin: '0 auto' }}>
          
          <div 
            className="how-it-works-showcase-grid"
            onClick={() => setIsAutoplay(false)}
            style={{
              border: `2px solid ${currentStep.border}`,
            }}
          >

            {/* Background Gradient Accent Glow */}
            <div style={{
              position: 'absolute',
              top: '-100px',
              right: '-100px',
              width: '350px',
              height: '350px',
              borderRadius: '50%',
              backgroundColor: `${currentStep.color}10`,
              filter: 'blur(60px)',
              pointerEvents: 'none',
            }} />

            {/* LEFT COLUMN: REALISTIC DEVICE APP SCREEN MOCKUP */}
            <div style={{ display: 'flex', justifyContent: 'center', position: 'relative' }}>
              
              {/* Outer Phone Mockup Frame */}
              <div style={{
                width: '300px',
                height: '520px',
                backgroundColor: '#0f172a',
                borderRadius: '40px',
                padding: '12px',
                boxShadow: '0 25px 60px rgba(0,0,0,0.25), inset 0 0 0 2px #334155',
                position: 'relative',
              }}>
                
                {/* Phone Speaker Notch */}
                <div style={{
                  position: 'absolute',
                  top: '18px',
                  left: '50%',
                  transform: 'translateX(-50%)',
                  width: '90px',
                  height: '16px',
                  backgroundColor: '#0f172a',
                  borderRadius: '10px',
                  zIndex: 20,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: '6px',
                }}>
                  <div style={{ width: '40px', height: '4px', backgroundColor: '#1e293b', borderRadius: '2px' }} />
                  <div style={{ width: '8px', height: '8px', backgroundColor: '#1e293b', borderRadius: '50%' }} />
                </div>

                {/* Inner Screen Canvas Container */}
                <div style={{
                  width: '100%',
                  height: '100%',
                  backgroundColor: '#ffffff',
                  borderRadius: '30px',
                  overflow: 'hidden',
                  position: 'relative',
                  display: 'flex',
                  flexDirection: 'column',
                }}>
                  
                  {/* Simulated App Header */}
                  <div style={{
                    backgroundColor: '#168a1a',
                    padding: '30px 16px 12px 16px',
                    color: '#ffffff',
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                  }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.85rem', fontWeight: 800 }}>
                      <ZwmLogo size={20} /> ZWM Vision AI
                    </div>
                    <span style={{ fontSize: '0.68rem', backgroundColor: 'rgba(255,255,255,0.25)', padding: '2px 8px', borderRadius: '10px' }}>
                      {currentStep.tag.split(' — ')[1]}
                    </span>
                  </div>

                  {/* STEP 1 PREVIEW: UPLOAD */}
                  {currentStep.previewType === 'upload' && (
                    <div style={{ flex: 1, padding: '16px', display: 'flex', flexDirection: 'column', gap: '14px', backgroundColor: '#f8fafc' }}>
                      <div style={{
                        flex: 1,
                        border: '2px dashed #168a1a',
                        borderRadius: '16px',
                        backgroundColor: '#f0fdf4',
                        display: 'flex',
                        flexDirection: 'column',
                        alignItems: 'center',
                        justifyContent: 'center',
                        padding: '16px',
                        textAlign: 'center',
                      }}>
                        <div style={{
                          width: '48px', height: '48px', borderRadius: '50%',
                          backgroundColor: '#168a1a', color: '#ffffff',
                          display: 'flex', alignItems: 'center', justifyContent: 'center',
                          marginBottom: '10px', boxShadow: '0 4px 12px rgba(22, 138, 26, 0.3)',
                        }}>
                          <Upload size={24} />
                        </div>
                        <p style={{ fontSize: '0.82rem', fontWeight: 800, color: '#0f172a', margin: 0 }}>
                          Select or Drop Waste Image
                        </p>
                        <p style={{ fontSize: '0.68rem', color: '#64748b', marginTop: '4px' }}>
                          JPG, PNG, WEBP up to 25MB
                        </p>
                      </div>

                      {/* Animated Image Cards Ingesting */}
                      <div style={{ display: 'flex', gap: '8px' }}>
                        <div style={{ flex: 1, height: '70px', borderRadius: '10px', overflow: 'hidden', position: 'relative', border: '1.5px solid #22c55e' }}>
                          <img src="/images/hero-waste.jpg" alt="Uploaded Waste" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                          <span style={{ position: 'absolute', bottom: '4px', right: '4px', backgroundColor: '#168a1a', color: '#fff', fontSize: '0.55rem', padding: '1px 5px', borderRadius: '4px', fontWeight: 700 }}>
                            READY
                          </span>
                        </div>
                        <div style={{ flex: 1, height: '70px', borderRadius: '10px', overflow: 'hidden', position: 'relative', border: '1.5px solid #e2e8f0' }}>
                          <img src="/images/outdoor-waste.jpg" alt="Outdoor Waste" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                        </div>
                      </div>
                    </div>
                  )}

                  {/* STEP 2 PREVIEW: ANNOTATE */}
                  {currentStep.previewType === 'annotate' && (
                    <div style={{ flex: 1, position: 'relative', overflow: 'hidden' }}>
                      <img src="/images/hero-waste.jpg" alt="Annotating Waste Items" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                      
                      {/* Top Info Banner */}
                      <div style={{
                        position: 'absolute', top: '10px', left: '10px', right: '10px',
                        backgroundColor: 'rgba(15, 23, 42, 0.88)', backdropFilter: 'blur(6px)',
                        color: '#ffffff', padding: '6px 10px', borderRadius: '8px',
                        fontSize: '0.68rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                        zIndex: 10,
                      }}>
                        <span>Objects Annotated: 2 Items</span>
                        <span style={{ color: '#38bdf8', fontWeight: 800 }}>PET & Glass Bottles</span>
                      </div>

                      {/* ─── 1. PET BOTTLE ANNOTATION ─── */}
                      {/* Bounding Box overlay over plastic PET bottle */}
                      <div style={{
                        position: 'absolute',
                        top: '76.5%',
                        left: '1%',
                        width: '32.5%',
                        height: '16%',
                        border: '2px dashed #0284c7',
                        borderRadius: '4px',
                        boxShadow: '0 0 12px rgba(2, 132, 199, 0.65)',
                        pointerEvents: 'none',
                        zIndex: 5,
                      }}>
                        <span style={{
                          position: 'absolute',
                          top: '-20px',
                          left: '-2px',
                          backgroundColor: '#0284c7',
                          color: '#ffffff',
                          fontSize: '0.60rem',
                          fontWeight: 800,
                          padding: '2px 6px',
                          borderRadius: '4px 4px 4px 0',
                          boxShadow: '0 2px 6px rgba(0,0,0,0.3)',
                          whiteSpace: 'nowrap',
                        }}>
                          PET Bottle 98.5%
                        </span>
                      </div>

                      {/* Polygon overlay for PET bottle */}
                      <svg
                        style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: '100%', pointerEvents: 'none', zIndex: 4 }}
                        viewBox="0 0 100 100"
                        preserveAspectRatio="none"
                      >
                        <polygon
                          points="2,87 5,91 19,87 32,83 31,77 17,79 3,82"
                          fill="rgba(2, 132, 199, 0.38)"
                          stroke="#38bdf8"
                          strokeWidth="1.2"
                          strokeDasharray="2 1"
                        />
                      </svg>

                      {/* Polygon Handle Nodes for PET bottle */}
                      <svg style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: '100%', pointerEvents: 'none', zIndex: 6 }}>
                        <circle cx="2%" cy="87%" r="3.5" fill="#ffffff" stroke="#0284c7" strokeWidth="2" />
                        <circle cx="5%" cy="91%" r="3.5" fill="#ffffff" stroke="#0284c7" strokeWidth="2" />
                        <circle cx="19%" cy="87%" r="3.5" fill="#ffffff" stroke="#0284c7" strokeWidth="2" />
                        <circle cx="32%" cy="83%" r="3.5" fill="#ffffff" stroke="#0284c7" strokeWidth="2" />
                        <circle cx="31%" cy="77%" r="3.5" fill="#ffffff" stroke="#0284c7" strokeWidth="2" />
                        <circle cx="17%" cy="79%" r="3.5" fill="#ffffff" stroke="#0284c7" strokeWidth="2" />
                        <circle cx="3%" cy="82%" r="3.5" fill="#ffffff" stroke="#0284c7" strokeWidth="2" />
                      </svg>

                      {/* ─── 2. GREEN GLASS BOTTLE ANNOTATION ─── */}
                      {/* Bounding Box overlay over green Glass bottle */}
                      <div style={{
                        position: 'absolute',
                        top: '77.5%',
                        left: '44%',
                        width: '35%',
                        height: '13%',
                        border: '2px dashed #16a34a',
                        borderRadius: '4px',
                        boxShadow: '0 0 12px rgba(22, 163, 74, 0.65)',
                        pointerEvents: 'none',
                        zIndex: 5,
                      }}>
                        <span style={{
                          position: 'absolute',
                          top: '-20px',
                          right: '-2px',
                          backgroundColor: '#16a34a',
                          color: '#ffffff',
                          fontSize: '0.60rem',
                          fontWeight: 800,
                          padding: '2px 6px',
                          borderRadius: '4px 4px 0 4px',
                          boxShadow: '0 2px 6px rgba(0,0,0,0.3)',
                          whiteSpace: 'nowrap',
                        }}>
                          Glass Bottle 97.2%
                        </span>
                      </div>

                      {/* Polygon overlay for Glass bottle */}
                      <svg
                        style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: '100%', pointerEvents: 'none', zIndex: 4 }}
                        viewBox="0 0 100 100"
                        preserveAspectRatio="none"
                      >
                        <polygon
                          points="45,89 52,84 59,79 77,79 78,89 58,90 51,89"
                          fill="rgba(22, 163, 74, 0.38)"
                          stroke="#4ade80"
                          strokeWidth="1.2"
                          strokeDasharray="2 1"
                        />
                      </svg>

                      {/* Polygon Handle Nodes for Glass bottle */}
                      <svg style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: '100%', pointerEvents: 'none', zIndex: 6 }}>
                        <circle cx="45%" cy="89%" r="3.5" fill="#ffffff" stroke="#16a34a" strokeWidth="2" />
                        <circle cx="52%" cy="84%" r="3.5" fill="#ffffff" stroke="#16a34a" strokeWidth="2" />
                        <circle cx="59%" cy="79%" r="3.5" fill="#ffffff" stroke="#16a34a" strokeWidth="2" />
                        <circle cx="77%" cy="79%" r="3.5" fill="#ffffff" stroke="#16a34a" strokeWidth="2" />
                        <circle cx="78%" cy="89%" r="3.5" fill="#ffffff" stroke="#16a34a" strokeWidth="2" />
                        <circle cx="58%" cy="90%" r="3.5" fill="#ffffff" stroke="#16a34a" strokeWidth="2" />
                        <circle cx="51%" cy="89%" r="3.5" fill="#ffffff" stroke="#16a34a" strokeWidth="2" />
                      </svg>

                    </div>
                  )}

                  {/* STEP 3 PREVIEW: CATEGORIZE */}
                  {currentStep.previewType === 'categorize' && (
                    <div style={{ flex: 1, padding: '14px', display: 'flex', flexDirection: 'column', gap: '10px', backgroundColor: '#f8fafc' }}>
                      <p style={{ fontSize: '0.78rem', fontWeight: 800, color: '#0f172a', margin: 0 }}>Assign Waste Category</p>
                      
                      {[
                        { label: 'PET Bottle (Plastic)', count: '98.8%', color: '#3b82f6', active: true },
                        { label: 'Milk Pouch (Plastic)', count: '97.5%', color: '#0284c7', active: false },
                        { label: 'Plastic Cover / Wrapper', count: '96.2%', color: '#16a34a', active: false },
                        { label: 'Cardboard Box (Paper)', count: '94.8%', color: '#d97706', active: false },
                      ].map((cat) => (
                        <div key={cat.label} style={{
                          padding: '10px 12px',
                          borderRadius: '10px',
                          backgroundColor: '#ffffff',
                          border: `2px solid ${cat.active ? cat.color : '#e2e8f0'}`,
                          display: 'flex',
                          justifyContent: 'space-between',
                          alignItems: 'center',
                          boxShadow: cat.active ? `0 4px 12px ${cat.color}25` : 'none',
                        }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                            <div style={{ width: '10px', height: '10px', borderRadius: '50%', backgroundColor: cat.color }} />
                            <span style={{ fontSize: '0.76rem', fontWeight: cat.active ? 800 : 600, color: '#1e293b' }}>{cat.label}</span>
                          </div>
                          <span style={{ fontSize: '0.72rem', fontWeight: 800, color: cat.color }}>{cat.count}</span>
                        </div>
                      ))}
                    </div>
                  )}

                  {/* STEP 4 PREVIEW: VALIDATE */}
                  {currentStep.previewType === 'validate' && (
                    <div style={{ flex: 1, padding: '16px', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', textAlign: 'center', backgroundColor: '#f5f3ff' }}>
                      <div style={{
                        width: '64px', height: '64px', borderRadius: '50%',
                        backgroundColor: '#7c3aed', color: '#ffffff',
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        marginBottom: '14px', boxShadow: '0 8px 20px rgba(124, 58, 237, 0.35)'
                      }}>
                        <CheckCircle2 size={36} />
                      </div>
                      <h4 style={{ fontSize: '1rem', fontWeight: 800, color: '#0f172a', marginBottom: '4px' }}>
                        Dataset Audit Passed
                      </h4>
                      <p style={{ fontSize: '0.74rem', color: '#64748b', marginBottom: '16px' }}>
                        Polygon boundaries & labels verified by 2 quality inspectors.
                      </p>
                      <span style={{ fontSize: '0.72rem', fontWeight: 800, color: '#7c3aed', backgroundColor: '#ede9fe', padding: '4px 12px', borderRadius: '12px' }}>
                        Quality Score: 99.4%
                      </span>
                    </div>
                  )}

                  {/* STEP 5 PREVIEW: BUILD DATASET */}
                  {currentStep.previewType === 'dataset' && (
                    <div style={{ flex: 1, padding: '14px', display: 'flex', flexDirection: 'column', gap: '10px', backgroundColor: '#ecfdf5' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <Database size={20} color="#059669" />
                        <span style={{ fontSize: '0.82rem', fontWeight: 800, color: '#065f46' }}>Export Format Ready</span>
                      </div>

                      {[
                        { title: 'YOLOv8 PyTorch Format', ext: 'dataset_v8.zip', icon: <FileCode size={16} /> },
                        { title: 'YOLOv11 Darknet Format', ext: 'dataset_v11.zip', icon: <Box size={16} /> },
                        { title: 'COCO JSON Annotations', ext: 'annotations.json', icon: <Layers size={16} /> },
                      ].map((exp) => (
                        <div key={exp.title} style={{
                          padding: '10px', borderRadius: '10px', backgroundColor: '#ffffff',
                          border: '1px solid #a7f3d0', display: 'flex', alignItems: 'center', gap: '10px'
                        }}>
                          <div style={{ color: '#059669' }}>{exp.icon}</div>
                          <div>
                            <div style={{ fontSize: '0.74rem', fontWeight: 700, color: '#0f172a' }}>{exp.title}</div>
                            <div style={{ fontSize: '0.64rem', color: '#059669' }}>{exp.ext}</div>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}

                </div>
              </div>

              {/* CURVED CONNECTING ARROW SVG (MATCHING REFERENCE DESIGN) */}
              <div className="desktop-nav-only" style={{
                position: 'absolute',
                right: '-45px',
                top: '40%',
                zIndex: 10,
                pointerEvents: 'none',
              }}>
                <svg width="60" height="40" viewBox="0 0 60 40">
                  <path
                    d="M 5 35 Q 30 5 55 20"
                    fill="none"
                    stroke={currentStep.color}
                    strokeWidth="2.5"
                    strokeDasharray="4 2"
                  />
                  <polygon
                    points="55,20 47,15 49,23"
                    fill={currentStep.color}
                  />
                </svg>
              </div>

            </div>

            {/* RIGHT COLUMN: CIRCULAR ACCENT BACKGROUND WITH EXPLANATION CARD */}
            <div style={{ position: 'relative' }}>
              
              {/* Circular Colored Background Container */}
              <div style={{
                backgroundColor: currentStep.lightBg,
                borderRadius: '24px',
                padding: '36px',
                border: `1.5px solid ${currentStep.border}`,
                boxShadow: `0 12px 32px ${currentStep.color}15`,
                position: 'relative',
              }}>
                
                {/* Step Indicators & Autoplay Control */}
                <div style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  width: '100%',
                  marginBottom: '24px',
                  flexWrap: 'wrap',
                  gap: '12px'
                }}>
                  {/* Step Indicators (1 2 3 4) */}
                  <div style={{
                    display: 'flex',
                    gap: '8px',
                    alignItems: 'center',
                  }}>
                    {stepsData.map((step, idx) => {
                      const isCurrent = activeStep === idx;
                      return (
                        <div
                          key={step.num}
                          onClick={(e) => {
                            e.stopPropagation();
                            setActiveStep(idx);
                            setIsAutoplay(false);
                          }}
                          style={{
                            width: '32px',
                            height: '32px',
                            borderRadius: '50%',
                            backgroundColor: isCurrent ? step.color : '#f1f5f9',
                            color: isCurrent ? '#ffffff' : '#475569',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            fontSize: '0.85rem',
                            fontWeight: 800,
                            cursor: 'pointer',
                            boxShadow: isCurrent ? `0 4px 10px ${step.color}30` : 'none',
                            transition: 'all 0.25s cubic-bezier(0.4, 0, 0.2, 1)',
                            border: isCurrent ? `1.5px solid ${step.color}` : '1.5px solid #cbd5e1',
                          }}
                        >
                          {idx + 1}
                        </div>
                      );
                    })}
                  </div>

                  {/* Autoplay Toggle pill */}
                  <div 
                    onClick={(e) => {
                      e.stopPropagation();
                      setIsAutoplay(!isAutoplay);
                    }}
                    style={{
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: '6px',
                      backgroundColor: isAutoplay ? '#fde68a' : '#e2e8f0',
                      color: isAutoplay ? '#92400e' : '#475569',
                      padding: '6px 14px',
                      borderRadius: '20px',
                      fontSize: '0.78rem',
                      fontWeight: 700,
                      cursor: 'pointer',
                      border: isAutoplay ? '1.5px solid #fcd34d' : '1.5px solid #cbd5e1',
                      transition: 'all 0.25s ease',
                      userSelect: 'none',
                      boxShadow: isAutoplay ? '0 2px 8px rgba(217, 119, 6, 0.1)' : 'none'
                    }}
                  >
                    <span 
                      style={{ 
                        display: 'inline-block', 
                        width: '8px', 
                        height: '8px', 
                        borderRadius: '50%', 
                        backgroundColor: isAutoplay ? '#d97706' : '#64748b', 
                        animation: isAutoplay ? 'pulseGlow 1.5s infinite' : 'none' 
                      }} 
                    />
                    {isAutoplay ? 'Autoplay (5s)' : 'Paused'}
                  </div>
                </div>

                {/* Step Title */}
                <h2 style={{
                  fontSize: '2rem',
                  fontWeight: 800,
                  color: '#0f172a',
                  marginBottom: '6px',
                  letterSpacing: '-0.02em',
                }}>
                  {currentStep.title}
                </h2>

                {/* Step Tagline */}
                <p style={{
                  fontSize: '0.92rem',
                  fontWeight: 700,
                  color: currentStep.color,
                  marginBottom: '18px',
                }}>
                  {currentStep.tagline}
                </p>

                {/* Detailed Explanation */}
                <p style={{
                  fontSize: '1rem',
                  color: '#475569',
                  lineHeight: 1.7,
                  marginBottom: '24px',
                }}>
                  {currentStep.description}
                </p>

                {/* Key Technical Highlights */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', marginBottom: '28px' }}>
                  {currentStep.highlights.map((hl) => (
                    <div key={hl} style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                      <CheckCircle2 size={18} color={currentStep.color} style={{ flexShrink: 0 }} />
                      <span style={{ fontSize: '0.88rem', fontWeight: 600, color: '#1e293b' }}>{hl}</span>
                    </div>
                  ))}
                </div>

                {/* Stepper Controller Buttons */}
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', paddingTop: '16px', borderTop: `1px solid ${currentStep.border}` }}>
                  <button
                    onClick={() => setActiveStep((prev) => Math.max(0, prev - 1))}
                    disabled={activeStep === 0}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '6px',
                      padding: '8px 16px',
                      borderRadius: '20px',
                      border: '1px solid #cbd5e1',
                      backgroundColor: '#ffffff',
                      color: activeStep === 0 ? '#94a3b8' : '#1e293b',
                      fontWeight: 700,
                      fontSize: '0.86rem',
                      cursor: activeStep === 0 ? 'not-allowed' : 'pointer',
                    }}
                  >
                    <ChevronLeft size={16} /> Previous Step
                  </button>

                  <button
                    onClick={() => setActiveStep((prev) => Math.min(stepsData.length - 1, prev + 1))}
                    disabled={activeStep === stepsData.length - 1}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '6px',
                      padding: '8px 20px',
                      borderRadius: '20px',
                      border: 'none',
                      backgroundColor: activeStep === stepsData.length - 1 ? '#94a3b8' : currentStep.color,
                      color: '#ffffff',
                      fontWeight: 700,
                      fontSize: '0.86rem',
                      cursor: activeStep === stepsData.length - 1 ? 'not-allowed' : 'pointer',
                      boxShadow: `0 4px 12px ${currentStep.color}35`,
                    }}
                  >
                    Next Step <ChevronRight size={16} />
                  </button>
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

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

export const HowItWorksPage: React.FC = () => {
  const navigate = useNavigate();
  const [activeStep, setActiveStep] = useState(0);
  const [hoveredNav, setHoveredNav] = useState<'home' | 'about' | 'how' | 'contact' | null>(null);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);

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

  const stepsData = [
    {
      num: '01',
      tag: 'Step 01 — Upload',
      title: 'Upload Image Collection',
      tagline: 'Multi-Source Image Ingestion & Metadata Tagging',
      icon: <Upload size={28} />,
      color: '#168a1a',
      lightBg: '#f0fdf4',
      border: '#bbf7d0',
      description:
        'Users capture waste photos directly using their mobile device camera or upload existing image files from local storage into the ZWM platform. Every uploaded image is automatically validated for resolution, tagged with geolocation/timestamps, and stored securely in the dataset repository.',
      highlights: [
        'Direct mobile camera capture & file drag-and-drop upload',
        'Automatic image resolution & format verification',
        'GPS location & timestamp metadata association',
        'Bulk dataset batch upload support',
      ],
      previewType: 'upload',
    },
    {
      num: '02',
      tag: 'Step 02 — Annotate',
      title: 'Polygon-Based Annotation',
      tagline: 'Pixel-Precise Object Contours & Boundary Mapping',
      icon: <Tag size={28} />,
      color: '#0284c7',
      lightBg: '#f0f9ff',
      border: '#bae6fd',
      description:
        'Contributors mark object boundaries in images using interactive polygon annotation tools. Precise point-by-point vertex selection isolates complex, overlapping waste items (like plastic bottles, foil wrappers, or crushed cans) from background clutter with pixel-level fidelity.',
      highlights: [
        'Interactive multi-point polygon contour masking',
        'Auto-generated bounding boxes with bounding dimensions',
        'Support for complex overlapping waste instances',
        'Undo, redo, and polygon node editing',
      ],
      previewType: 'annotate',
    },
    {
      num: '03',
      tag: 'Step 03 — Categorize',
      title: 'Categorize & Taxonomy Tagging',
      tagline: 'Multi-Stream Sorting & Polymer Material Classification',
      icon: <Leaf size={28} />,
      color: '#d97706',
      lightBg: '#fffbe6',
      border: '#fef08a',
      description:
        'Annotated waste items are categorized into specific waste streams: Plastic (PET, HDPE, PP), Paper & Cardboard, Glass, and Metal. ZWM uses structured taxonomy rules to classify materials accurately for targeted recycling pipelines.',
      highlights: [
        'Standardized 4-stream classification: Plastic, Paper, Glass, Metal',
        'Sub-category polymer tagging (e.g. PET bottle vs HDPE container)',
        'Class confidence scoring and automated suggestion tags',
        'Color-coded class visual indicators',
      ],
      previewType: 'categorize',
    },
    {
      num: '04',
      tag: 'Step 04 — Validate',
      title: 'Quality Audit & Dataset Validation',
      tagline: 'Multi-Inspector Quality Verification & Audit Pipeline',
      icon: <CheckSquare size={28} />,
      color: '#7c3aed',
      lightBg: '#f5f3ff',
      border: '#ddd6fe',
      description:
        'To ensure training accuracy, annotated images pass through a quality validation stage. Reviewers audit polygon boundaries, class tags, and image quality. Only verified, high-confidence entries are approved for inclusion in the final training dataset.',
      highlights: [
        'Inspector review and double-blind validation workflow',
        'Polygon overlap and boundary accuracy checks',
        'Flagging and re-annotation request pipeline',
        'Dataset quality health index scoring (99.4%+ target accuracy)',
      ],
      previewType: 'validate',
    },
    {
      num: '05',
      tag: 'Step 05 — Build Dataset',
      title: 'Export Training-Ready Dataset',
      tagline: 'YOLOv8 / YOLOv11 & Computer Vision Model Export',
      icon: <Database size={28} />,
      color: '#059669',
      lightBg: '#ecfdf5',
      border: '#a7f3d0',
      description:
        'Validated images and normalized annotations are compiled into structured computer vision training datasets. Users export ready-to-use dataset packages complete with train/val/test splits formatted for YOLOv8, YOLOv11, COCO, and PyTorch frameworks.',
      highlights: [
        'One-click dataset export in YOLOv8, YOLOv11, and COCO formats',
        'Automated 80/10/10 train, validation, and test split generator',
        'Zipped dataset downloads with normalized label text files',
        'Direct integration ready for AI waste sorting robot training',
      ],
      previewType: 'dataset',
    },
  ];

  const currentStep = stepsData[activeStep];

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
            Click through our 5-step interactive workflow below to see how waste images are captured, annotated, categorized, audited, and exported for AI model training.
          </p>

          {/* ─── STEP SELECTION PIPELINE BAR ─── */}
          <div style={{
            display: 'flex',
            justifyContent: 'center',
            gap: '12px',
            flexWrap: 'wrap',
            marginBottom: '20px',
          }}>
            {stepsData.map((step, index) => {
              const isActive = activeStep === index;
              return (
                <button
                  key={step.num}
                  onClick={() => setActiveStep(index)}
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
                  <span>{step.title.split(' ')[0]}</span>
                </button>
              );
            })}
          </div>
        </div>
      </section>

      {/* ─── MAIN INTERACTIVE SHOWCASE (MATCHING USER REFERENCE DESIGN) ─── */}
      <section style={{ padding: '64px 64px 96px', backgroundColor: '#ffffff', position: 'relative' }}>
        <div style={{ maxWidth: '1140px', margin: '0 auto' }}>
          
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(360px, 1fr))',
            gap: '48px',
            alignItems: 'center',
            backgroundColor: '#fafcf9',
            borderRadius: '32px',
            padding: '48px 40px',
            border: `2px solid ${currentStep.border}`,
            boxShadow: '0 24px 60px rgba(0,0,0,0.06)',
            position: 'relative',
            overflow: 'hidden',
          }}>

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
                      <img src="/images/hero-waste.jpg" alt="Annotating Waste" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                      
                      {/* Polygon Mask Overlay Animation */}
                      <svg style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: '100%' }}>
                        <polygon
                          points="40,120 180,100 220,240 70,260"
                          fill="rgba(2, 132, 199, 0.25)"
                          stroke="#0284c7"
                          strokeWidth="3"
                          strokeDasharray="6 3"
                        />
                        {/* Polygon Handle Nodes */}
                        <circle cx="40" cy="120" r="5" fill="#0284c7" />
                        <circle cx="180" cy="100" r="5" fill="#0284c7" />
                        <circle cx="220" cy="240" r="5" fill="#0284c7" />
                        <circle cx="70" cy="260" r="5" fill="#0284c7" />
                      </svg>

                      <div style={{
                        position: 'absolute', bottom: '12px', left: '12px', right: '12px',
                        backgroundColor: 'rgba(15, 23, 42, 0.85)', backdropFilter: 'blur(6px)',
                        color: '#ffffff', padding: '8px 12px', borderRadius: '10px',
                        fontSize: '0.72rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center'
                      }}>
                        <span>Polygon Contour: 4 Points</span>
                        <span style={{ color: '#38bdf8', fontWeight: 800 }}>Active Tool</span>
                      </div>
                    </div>
                  )}

                  {/* STEP 3 PREVIEW: CATEGORIZE */}
                  {currentStep.previewType === 'categorize' && (
                    <div style={{ flex: 1, padding: '14px', display: 'flex', flexDirection: 'column', gap: '10px', backgroundColor: '#f8fafc' }}>
                      <p style={{ fontSize: '0.78rem', fontWeight: 800, color: '#0f172a', margin: 0 }}>Assign Category Class</p>
                      
                      {[
                        { label: 'Plastic (PET Bottle)', count: '98.8%', color: '#3b82f6', active: true },
                        { label: 'Paper & Cardboard', count: '96.4%', color: '#22c55e', active: false },
                        { label: 'Glass Container', count: '95.1%', color: '#f97316', active: false },
                        { label: 'Metal Can', count: '94.2%', color: '#a855f7', active: false },
                      ].map((cat) => (
                        <div key={cat.label} style={{
                          padding: '10px 12px',
                          borderRadius: '10px',
                          backgroundColor: cat.active ? '#ffffff' : '#ffffff',
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
                
                {/* Step Badge */}
                <div style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '8px',
                  backgroundColor: currentStep.color,
                  color: '#ffffff',
                  padding: '4px 14px',
                  borderRadius: '16px',
                  fontSize: '0.78rem',
                  fontWeight: 800,
                  marginBottom: '16px',
                  boxShadow: `0 4px 12px ${currentStep.color}35`,
                }}>
                  {currentStep.icon} STEP {currentStep.num} OF 05
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

      {/* ─── DETAILED ALL 5 STEPS GRID BREAKDOWN SECTION ─── */}
      <section style={{ padding: '80px 64px 96px', backgroundColor: '#f8fafc', borderTop: '1px solid #edf5ed' }}>
        <div style={{ maxWidth: '1140px', margin: '0 auto' }}>
          
          <div style={{ textAlign: 'center', maxWidth: '720px', margin: '0 auto 56px' }}>
            <h2 style={{ fontSize: '2.4rem', fontWeight: 800, color: '#0f172a', letterSpacing: '-0.02em', marginBottom: '12px' }}>
              Full 5-Step Pipeline Overview
            </h2>
            <p style={{ fontSize: '1.02rem', color: '#64748b' }}>
              Every step engineered for computer vision data integrity.
            </p>
          </div>

          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))',
            gap: '24px',
          }}>
            {stepsData.map((step, idx) => (
              <div
                key={step.num}
                onClick={() => {
                  setActiveStep(idx);
                  window.scrollTo({ top: 400, behavior: 'smooth' });
                }}
                style={{
                  backgroundColor: '#ffffff',
                  borderRadius: '20px',
                  padding: '32px 28px',
                  border: activeStep === idx ? `2px solid ${step.color}` : '1px solid #e2e8f0',
                  boxShadow: activeStep === idx ? `0 12px 30px ${step.color}20` : '0 2px 8px rgba(0,0,0,0.03)',
                  cursor: 'pointer',
                  transition: 'all 0.25s ease',
                  position: 'relative',
                }}
                onMouseOver={(e) => {
                  e.currentTarget.style.transform = 'translateY(-4px)';
                }}
                onMouseOut={(e) => {
                  e.currentTarget.style.transform = 'translateY(0)';
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                  <span style={{ fontSize: '1.6rem', fontWeight: 900, color: step.color }}>{step.num}</span>
                  <div style={{
                    width: '42px', height: '42px', borderRadius: '12px',
                    backgroundColor: step.lightBg, color: step.color,
                    display: 'flex', alignItems: 'center', justifyContent: 'center'
                  }}>
                    {step.icon}
                  </div>
                </div>

                <h3 style={{ fontSize: '1.2rem', fontWeight: 800, color: '#0f172a', marginBottom: '8px' }}>
                  {step.title}
                </h3>
                <p style={{ fontSize: '0.88rem', color: '#64748b', lineHeight: 1.6, margin: 0 }}>
                  {step.description}
                </p>
              </div>
            ))}
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

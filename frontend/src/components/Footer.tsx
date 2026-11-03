import React from 'react';
import { Link } from 'react-router-dom';
import { ZwmLogo } from '../assets/icons/ZwmLogo';

export const Footer: React.FC = () => {
  return (
    <footer
      className="landing-footer"
      style={{
        padding: '56px 64px 32px 64px',
        backgroundColor: '#0f172a',
        color: '#ffffff',
        display: 'flex',
        flexDirection: 'column',
        gap: '40px',
      }}
    >
      {/* Top Footer Columns */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
          gap: '40px',
          alignItems: 'start',
        }}
      >
        {/* Brand & Description Column */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '14px', maxWidth: '340px' }}>
          <Link
            to="/"
            style={{ display: 'flex', alignItems: 'center', gap: '10px', textDecoration: 'none' }}
          >
            <ZwmLogo size={38} />
            <div>
              <div style={{ fontSize: '1.25rem', fontWeight: 800, color: '#168a1a', lineHeight: 1 }}>ZWM</div>
              <div style={{ fontSize: '0.72rem', color: '#94a3b8', fontWeight: 600 }}>Zero Waste Management</div>
            </div>
          </Link>
          <p style={{ fontSize: '0.88rem', color: '#94a3b8', lineHeight: 1.65, margin: 0 }}>
            AI-assisted waste dataset management platform designed to build high-quality datasets for autonomous sorting and computer vision waste detection models.
          </p>
        </div>

        {/* Quick Links Column (Top Bar Contents as Functional Links) */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
          <h4
            style={{
              fontSize: '0.95rem',
              fontWeight: 700,
              color: '#ffffff',
              letterSpacing: '0.02em',
              textTransform: 'uppercase',
              margin: 0,
            }}
          >
            Quick Links
          </h4>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', fontSize: '0.9rem' }}>
            <Link
              to="/"
              style={{
                color: '#cbd5e1',
                textDecoration: 'none',
                fontSize: '0.92rem',
                fontWeight: 600,
                transition: 'color 0.2s',
                width: 'fit-content',
              }}
              onMouseOver={(e) => (e.currentTarget.style.color = '#22c55e')}
              onMouseOut={(e) => (e.currentTarget.style.color = '#cbd5e1')}
            >
              Home
            </Link>
            <Link
              to="/about"
              style={{
                color: '#cbd5e1',
                textDecoration: 'none',
                fontSize: '0.92rem',
                fontWeight: 600,
                transition: 'color 0.2s',
                width: 'fit-content',
              }}
              onMouseOver={(e) => (e.currentTarget.style.color = '#22c55e')}
              onMouseOut={(e) => (e.currentTarget.style.color = '#cbd5e1')}
            >
              About
            </Link>
            <Link
              to="/how-it-works"
              style={{
                color: '#cbd5e1',
                textDecoration: 'none',
                fontSize: '0.92rem',
                fontWeight: 600,
                transition: 'color 0.2s',
                width: 'fit-content',
              }}
              onMouseOver={(e) => (e.currentTarget.style.color = '#22c55e')}
              onMouseOut={(e) => (e.currentTarget.style.color = '#cbd5e1')}
            >
              How it Works
            </Link>
            <Link
              to="/contact"
              style={{
                color: '#cbd5e1',
                textDecoration: 'none',
                fontSize: '0.92rem',
                fontWeight: 600,
                transition: 'color 0.2s',
                width: 'fit-content',
              }}
              onMouseOver={(e) => (e.currentTarget.style.color = '#22c55e')}
              onMouseOut={(e) => (e.currentTarget.style.color = '#cbd5e1')}
            >
              Contact
            </Link>
          </div>
        </div>

        {/* Legal & Policy Column (Terms of Service & Privacy Policy Links) */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
          <h4
            style={{
              fontSize: '0.95rem',
              fontWeight: 700,
              color: '#ffffff',
              letterSpacing: '0.02em',
              textTransform: 'uppercase',
              margin: 0,
            }}
          >
            Legal & Policy
          </h4>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', fontSize: '0.9rem' }}>
            <Link
              to="/terms"
              style={{
                color: '#cbd5e1',
                textDecoration: 'none',
                fontSize: '0.92rem',
                fontWeight: 600,
                transition: 'color 0.2s',
                width: 'fit-content',
              }}
              onMouseOver={(e) => (e.currentTarget.style.color = '#22c55e')}
              onMouseOut={(e) => (e.currentTarget.style.color = '#cbd5e1')}
            >
              Terms of Service
            </Link>
            <Link
              to="/privacy"
              style={{
                color: '#cbd5e1',
                textDecoration: 'none',
                fontSize: '0.92rem',
                fontWeight: 600,
                transition: 'color 0.2s',
                width: 'fit-content',
              }}
              onMouseOver={(e) => (e.currentTarget.style.color = '#22c55e')}
              onMouseOut={(e) => (e.currentTarget.style.color = '#cbd5e1')}
            >
              Privacy Policy
            </Link>
          </div>
        </div>
      </div>

      {/* Bottom Copyright Strip */}
      <div
        style={{
          borderTop: '1px solid #1e293b',
          paddingTop: '24px',
          display: 'flex',
          justify: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: '16px',
          fontSize: '0.84rem',
          color: '#64748b',
        }}
      >
        <p style={{ margin: 0 }}>© 2026 ZWM (Zero Waste Management). All rights reserved.</p>
        <p style={{ margin: 0 }}>Building a cleaner planet, one dataset at a time.</p>
      </div>
    </footer>
  );
};

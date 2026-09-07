import React from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { Home, UploadCloud, User as UserIcon } from 'lucide-react';
import { ZwmLogo } from '../../assets/icons/ZwmLogo';
import { RecycleIllustration } from '../../assets/icons/RecycleIllustration';

export const Sidebar: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();

  const currentPath = location.pathname;

  const isDashboardActive = currentPath === '/' || currentPath === '/dashboard';
  const isUploadActive = currentPath === '/dashboard/upload' || currentPath === '/upload';
  const isProfileActive = currentPath === '/dashboard/profile' || currentPath === '/profile';

  return (
    <aside className="sidebar">
      <div>
        {/* Logo & Brand Header */}
        <div
          className="sidebar-header"
          onClick={() => navigate('/dashboard')}
          style={{ cursor: 'pointer' }}
        >
          <div className="brand-logo-badge">
            <ZwmLogo size={36} />
          </div>
          <div>
            <div className="brand-title">ZWM</div>
            <div className="brand-subtitle">Zero Waste Management</div>
          </div>
        </div>

        {/* Navigation Menu */}
        <nav className="sidebar-nav">
          <button
            className={`nav-item ${isDashboardActive ? 'active' : ''}`}
            onClick={() => navigate('/dashboard')}
            style={{ width: '100%', background: 'none', textAlign: 'left' }}
          >
            <Home size={20} />
            <span>Dashboard</span>
          </button>

          <button
            className={`nav-item ${isUploadActive ? 'active' : ''}`}
            onClick={() => navigate('/dashboard/upload')}
            style={{ width: '100%', background: 'none', textAlign: 'left' }}
          >
            <UploadCloud size={20} />
            <span>Upload Image</span>
          </button>

          <button
            className={`nav-item ${isProfileActive ? 'active' : ''}`}
            onClick={() => navigate('/dashboard/profile')}
            style={{ width: '100%', background: 'none', textAlign: 'left' }}
          >
            <UserIcon size={20} />
            <span>Profile</span>
          </button>
        </nav>
      </div>

      {/* Illustrated Recycle Bin with botanical leaves */}
      <div className="sidebar-illustration">
        <RecycleIllustration />
      </div>
    </aside>
  );
};

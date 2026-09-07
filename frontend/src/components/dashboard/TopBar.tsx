import React, { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Star, ChevronDown, User as UserIcon, LogOut, Settings } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';

export const TopBar: React.FC = () => {
  const navigate = useNavigate();
  const { user, stats, logout } = useAuth();
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Close dropdown on outside click
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setDropdownOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  return (
    <div className="header-profile-points-container" ref={dropdownRef}>
      {/* Combined Single Card matching reference design */}
      <div className="unified-top-card">
        {/* Points Section */}
        <div className="top-card-points-section">
          <div className="star-icon-wrap">
            <Star size={24} fill="#249B25" color="#317827" />
          </div>
          <div className="points-text-group">
            <span className="points-label">Points</span>
            <span className="points-value">{stats?.reward_points ?? user?.reward_points ?? 320}</span>
          </div>
        </div>

        {/* Vertical Divider */}
        <div className="top-card-divider" />

        {/* User Profile Section */}
        <div
          className="top-card-user-section"
          onClick={() => setDropdownOpen(!dropdownOpen)}
          role="button"
          tabIndex={0}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') setDropdownOpen(!dropdownOpen);
          }}
        >
          <span className="profile-name">{user?.full_name || 'Keerthana H M'}</span>
          <ChevronDown
            size={18}
            color="#317827"
            style={{
              transform: dropdownOpen ? 'rotate(180deg)' : 'none',
              transition: 'transform 0.2s ease',
            }}
          />
        </div>
      </div>

      {/* Dropdown Menu */}
      {dropdownOpen && (
        <div className="profile-dropdown" onClick={(e) => e.stopPropagation()}>
          <div
            className="dropdown-item"
            onClick={() => {
              setDropdownOpen(false);
              navigate('/dashboard/profile');
            }}
          >
            <UserIcon size={16} color="#317827" />
            <span>My Profile</span>
          </div>
          <div
            className="dropdown-item"
            onClick={() => {
              setDropdownOpen(false);
              navigate('/dashboard/upload');
            }}
          >
            <Settings size={16} color="#4B5563" />
            <span>Upload Images</span>
          </div>
          <div className="dropdown-divider" />
          <div
            className="dropdown-item"
            onClick={() => {
              setDropdownOpen(false);
              logout();
              navigate('/login');
            }}
            style={{ color: '#ef4444' }}
          >
            <LogOut size={16} />
            <span>Sign Out</span>
          </div>
        </div>
      )}
    </div>
  );
};

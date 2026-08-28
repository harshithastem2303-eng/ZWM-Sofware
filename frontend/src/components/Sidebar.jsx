import React from 'react';
import { Home, Users, BarChart2, Settings as SettingsIcon, LogOut, CheckSquare } from 'lucide-react';

const Sidebar = ({ activeTab, setActiveTab, onLogout }) => {
  const menuItems = [
    { id: 'dashboard', label: 'Dashboard', icon: Home },
    { id: 'validation', label: 'Validation', icon: CheckSquare },
    { id: 'users', label: 'Users', icon: Users },
    { id: 'reports', label: 'Reports', icon: BarChart2 },
    { id: 'settings', label: 'Settings', icon: SettingsIcon },
  ];

  return (
    <aside className="dashboard-sidebar">
      <div className="sidebar-logo">
        <div className="brand-logo-container" style={{ justifyContent: 'flex-start' }}>
          <svg className="brand-logo-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="10" />
            <path d="M7 15c2-2.5 5-2.5 7 0" />
            <path d="M12 9c1.5-1.5 3.5-1.5 5 0-1.5 1.5-1.5 3.5 0 5-1.5-1.5-3.5-1.5-5 0" />
            <path d="M12 9v5" />
          </svg>
          <span className="brand-title" style={{ fontSize: '24px' }}>ZWM</span>
        </div>
        <p className="brand-subtitle" style={{ fontSize: '10px' }}>Zero Waste Management</p>
      </div>

      <ul className="sidebar-menu">
        {menuItems.map((item) => {
          const Icon = item.icon;
          const isActive = activeTab === item.id;
          return (
            <li key={item.id}>
              <a
                href={`#${item.id}`}
                className={`sidebar-item ${isActive ? 'active' : ''}`}
                onClick={(e) => {
                  e.preventDefault();
                  setActiveTab(item.id);
                }}
              >
                <Icon size={18} />
                <span>{item.label}</span>
              </a>
            </li>
          );
        })}
        <li style={{ marginTop: 'auto' }}>
          <a
            href="#"
            className="sidebar-item"
            onClick={(e) => {
              e.preventDefault();
              onLogout();
            }}
            style={{ color: '#ef4444' }}
          >
            <LogOut size={18} />
            <span>Sign Out</span>
          </a>
        </li>
      </ul>
    </aside>
  );
};

export default Sidebar;

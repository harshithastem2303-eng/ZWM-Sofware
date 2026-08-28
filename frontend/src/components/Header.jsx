import React, { useState, useEffect, useRef } from 'react';
import { Bell, Plus, X, Search } from 'lucide-react';
import { createNewAdmin } from '../services/api';

const Header = () => {
  const [showAddAdmin, setShowAddAdmin] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [adminId, setAdminId] = useState('');
  const [adminEmail, setAdminEmail] = useState('');
  const [adminRole, setAdminRole] = useState('Super Admin');
  const [addAdminLoading, setAddAdminLoading] = useState(false);
  const [addAdminSuccess, setAddAdminSuccess] = useState('');
  const [addAdminError, setAddAdminError] = useState('');

  const plusBtnRef = useRef(null);
  const panelRef = useRef(null);

  useEffect(() => {
    const handleOutsideClick = (e) => {
      if (
        panelRef.current &&
        !panelRef.current.contains(e.target) &&
        plusBtnRef.current &&
        !plusBtnRef.current.contains(e.target)
      ) {
        setShowAddAdmin(false);
      }
    };
    document.addEventListener('mousedown', handleOutsideClick);
    return () => document.removeEventListener('mousedown', handleOutsideClick);
  }, []);

  const handleAddAdminSubmit = async (e) => {
    e.preventDefault();
    setAddAdminSuccess('');
    setAddAdminError('');

    if (!adminId.trim()) {
      setAddAdminError('Admin ID is required.');
      return;
    }
    if (!adminEmail.trim()) {
      setAddAdminError('Email is required.');
      return;
    }

    setAddAdminLoading(true);

    try {
      const result = await createNewAdmin(adminId, adminEmail, adminRole);
      setAddAdminSuccess(`Admin created! Temp password: ${result.temp_password}`);
      setAdminId('');
      setAdminEmail('');
    } catch (err) {
      setAddAdminError(err.message || 'Failed to create admin.');
    } finally {
      setAddAdminLoading(false);
    }
  };

  return (
    <header className="dashboard-top-navbar">
      {/* Left section: Welcome Title */}
      <div className="navbar-left">
        <h2 style={{ fontSize: '22px', fontWeight: 700, color: '#0F172A', fontFamily: 'var(--font-main)', margin: 0, display: 'flex', alignItems: 'center', gap: '8px' }}>
          Welcome back, Admin <span style={{ fontSize: '20px' }}>👋</span>
        </h2>
      </div>

      {/* Right section: Action button, Notifications, Profile Card */}
      <div className="navbar-right">
        <button
          ref={plusBtnRef}
          className="navbar-action-btn"
          style={{ padding: '10px 18px', fontSize: '14px' }}
          onClick={() => {
            setShowAddAdmin(!showAddAdmin);
            setAddAdminSuccess('');
            setAddAdminError('');
          }}
        >
          <Plus size={18} />
          <span>Add Admin</span>
        </button>

        <button
          className="navbar-icon-btn"
          style={{ padding: '10px' }}
          aria-label="Notifications"
          onClick={() => alert('No new notifications.')}
        >
          <Bell size={20} />
          <span className="navbar-badge-dot" style={{ top: '8px', right: '8px' }} />
        </button>

        <div className="profile-avatar-card" style={{ cursor: 'default', padding: '8px 16px 8px 12px', borderRadius: '12px' }}>
          <img
            src="https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=150"
            alt="Admin User"
            className="avatar-img"
            style={{ width: '36px', height: '36px' }}
          />
          <div className="profile-info">
            <span className="profile-name" style={{ fontSize: '14px' }}>Admin User</span>
            <span className="profile-role" style={{ fontSize: '11px' }}>Super Admin</span>
          </div>
        </div>

        {showAddAdmin && (
          <div className="add-admin-panel dropdown-animate" ref={panelRef} style={{ top: '74px', right: '40px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '4px' }}>
              <h3 className="panel-title">Add New Admin</h3>
              <X
                size={16}
                style={{ cursor: 'pointer', color: 'var(--color-text-muted)' }}
                onClick={() => setShowAddAdmin(false)}
              />
            </div>

            {addAdminSuccess && (
              <div className="panel-alert panel-alert-success">
                {addAdminSuccess}
              </div>
            )}
            {addAdminError && (
              <div className="panel-alert panel-alert-error">
                {addAdminError}
              </div>
            )}

            <form onSubmit={handleAddAdminSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              <div className="panel-input-group">
                <label className="panel-label">Admin ID</label>
                <input
                  type="text"
                  className="panel-input"
                  placeholder="Enter admin ID"
                  value={adminId}
                  onChange={(e) => setAdminId(e.target.value)}
                  disabled={addAdminLoading}
                />
              </div>

              <div className="panel-input-group">
                <label className="panel-label">Email</label>
                <input
                  type="email"
                  className="panel-input"
                  placeholder="Enter admin email"
                  value={adminEmail}
                  onChange={(e) => setAdminEmail(e.target.value)}
                  disabled={addAdminLoading}
                />
              </div>

              <div className="panel-input-group">
                <label className="panel-label">Role</label>
                <select
                  className="panel-select"
                  value={adminRole}
                  onChange={(e) => setAdminRole(e.target.value)}
                  disabled={addAdminLoading}
                >
                  <option value="Super Admin">Super Admin</option>
                  <option value="Admin">Admin</option>
                </select>
              </div>

              <button type="submit" className="panel-btn" disabled={addAdminLoading}>
                {addAdminLoading ? 'Adding...' : 'Add Admin'}
              </button>
            </form>
          </div>
        )}
      </div>
    </header>
  );
};

export default Header;

import React, { useState, useEffect } from 'react';
import { fetchUsersList } from '../services/api';
import { Search, Filter, Shield, Trophy, Image as ImageIcon, Award, Mail, ArrowUpDown } from 'lucide-react';

const UsersView = () => {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [searchTerm, setSearchTerm] = useState('');
  const [roleFilter, setRoleFilter] = useState('All');
  const [sortBy, setSortBy] = useState('reward_points'); // 'reward_points', 'image_count', 'email'
  const [sortOrder, setSortOrder] = useState('desc');

  useEffect(() => {
    const loadUsers = async () => {
      try {
        const data = await fetchUsersList();
        setUsers(data.users || []);
      } catch (err) {
        setError(err.message || 'Failed to load users list.');
      } finally {
        setLoading(false);
      }
    };
    loadUsers();
  }, []);

  const toggleSort = (field) => {
    if (sortBy === field) {
      setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc');
    } else {
      setSortBy(field);
      setSortOrder('desc');
    }
  };

  // Filter and sort users
  const filteredUsers = users
    .filter((u) => {
      const emailMatch = u.email.toLowerCase().includes(searchTerm.toLowerCase());
      const roleMatch = roleFilter === 'All' ? true : u.role.toLowerCase() === roleFilter.toLowerCase();
      return emailMatch && roleMatch;
    })
    .sort((a, b) => {
      let aVal = a[sortBy];
      let bVal = b[sortBy];

      if (typeof aVal === 'string') {
        aVal = aVal.toLowerCase();
        bVal = bVal.toLowerCase();
      }

      if (aVal < bVal) return sortOrder === 'asc' ? -1 : 1;
      if (aVal > bVal) return sortOrder === 'asc' ? 1 : -1;
      return 0;
    });

  // Calculate stats
  const totalCount = users.length;
  const adminCount = users.filter((u) => u.role === 'admin').length;
  const normalUserCount = totalCount - adminCount;
  const totalRewardPoints = users.reduce((sum, u) => sum + (u.reward_points || 0), 0);
  const avgUploads = totalCount > 0 ? (users.reduce((sum, u) => sum + (u.image_count || 0), 0) / totalCount).toFixed(1) : 0;

  // Helper to determine contribution badges
  const getContributionBadge = (points) => {
    if (points >= 500) return { label: 'Elite Contributor', color: '#7c3aed', bg: '#f5f3ff' }; // Purple
    if (points >= 150) return { label: 'Gold Contributor', color: '#b45309', bg: '#fef3c7' }; // Amber
    if (points >= 50) return { label: 'Silver Contributor', color: '#4b5563', bg: '#f3f4f6' }; // Slate
    return { label: 'Rising Star', color: '#15803d', bg: '#f0fdf4' }; // Green
  };

  if (loading) {
    return (
      <div className="login-page" style={{ background: 'transparent', minHeight: '400px' }}>
        <div className="spinner" style={{ width: '40px', height: '40px', borderTopColor: 'var(--color-primary)' }} />
        <p style={{ marginTop: '16px', fontWeight: '500', color: 'var(--color-primary)' }}>Loading ZWM contributors database...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="dashboard-card" style={{ padding: '40px', textAlign: 'center', borderColor: '#fee2e2' }}>
        <div className="error-banner" style={{ display: 'inline-flex', marginBottom: '0' }}>
          <span>{error}</span>
        </div>
      </div>
    );
  }

  return (
    <div className="page-fade-in" style={{ display: 'flex', flexDirection: 'column', gap: '28px' }}>
      
      {/* Page Heading */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginBottom: '28px' }}>
        <h1 style={{ fontSize: '32px', fontWeight: 700, color: '#0F172A', fontFamily: 'var(--font-main)', lineHeight: '1.2' }}>
          Users
        </h1>
        <p style={{ fontSize: '14px', fontWeight: 400, color: '#64748B', fontFamily: 'var(--font-main)' }}>
          Manage contributors, activity, and access across the platform.
        </p>
      </div>

      {/* Users Metric Highlights */}
      <section className="metrics-row">
        <div className="metric-card">
          <div className="metric-icon-box">
            <Trophy />
          </div>
          <div className="metric-content">
            <span className="metric-label">Total Registered Users</span>
            <span className="metric-value">{totalCount}</span>
            <span className="metric-trend trend-up">
              {normalUserCount} active uploaders
            </span>
          </div>
        </div>

        <div className="metric-card">
          <div className="metric-icon-box" style={{ color: '#8b5cf6', backgroundColor: '#f5f3ff' }}>
            <Shield />
          </div>
          <div className="metric-content">
            <span className="metric-label">System Administrators</span>
            <span className="metric-value">{adminCount}</span>
            <span className="metric-trend" style={{ color: 'var(--color-text-muted)', fontWeight: 500 }}>
              Full console access
            </span>
          </div>
        </div>

        <div className="metric-card">
          <div className="metric-icon-box" style={{ color: '#ea580c', backgroundColor: '#ffedd5' }}>
            <ImageIcon />
          </div>
          <div className="metric-content">
            <span className="metric-label">Avg. Images Uploaded</span>
            <span className="metric-value">{avgUploads}</span>
            <span className="metric-trend trend-up">
              per user database average
            </span>
          </div>
        </div>

        <div className="metric-card">
          <div className="metric-icon-box" style={{ color: '#eab308', backgroundColor: '#fef9c3' }}>
            <Award />
          </div>
          <div className="metric-content">
            <span className="metric-label">Total Points Rewarded</span>
            <span className="metric-value">{totalRewardPoints.toLocaleString()}</span>
            <span className="metric-trend trend-up" style={{ color: '#ca8a04' }}>
              ✦ {totalCount > 0 ? Math.round(totalRewardPoints / totalCount) : 0} points avg.
            </span>
          </div>
        </div>
      </section>

      {/* Main Database Table Container */}
      <div className="dashboard-card" style={{ padding: '24px' }}>
        
        {/* Search, Sort, Filter Actions Header */}
        <div style={{ display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: '16px', marginBottom: '24px', alignItems: 'center' }}>
          <div>
            <h2 className="card-title" style={{ fontSize: '18px', display: 'flex', alignItems: 'center', gap: '8px' }}>
              Contributors List
              <span style={{ fontSize: '12px', background: 'var(--color-primary-light)', color: 'var(--color-primary)', padding: '2px 8px', borderRadius: '12px', fontWeight: 600 }}>
                {filteredUsers.length} Users Found
              </span>
            </h2>
          </div>

          <div style={{ display: 'flex', gap: '12px', alignItems: 'center', flexWrap: 'wrap' }}>
            {/* Search Input */}
            <div style={{ position: 'relative', minWidth: '240px' }}>
              <Search size={16} style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)', color: 'var(--color-text-muted)' }} />
              <input
                type="text"
                placeholder="Search user email..."
                className="panel-input"
                style={{ paddingLeft: '36px', height: '38px', fontSize: '13px' }}
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
              />
            </div>

            {/* Role Filter Dropdown */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Filter size={15} style={{ color: 'var(--color-text-muted)' }} />
              <select
                className="card-select"
                style={{ height: '38px', padding: '0 12px' }}
                value={roleFilter}
                onChange={(e) => setRoleFilter(e.target.value)}
              >
                <option value="All">All Roles</option>
                <option value="user">Users only</option>
                <option value="admin">Admins only</option>
              </select>
            </div>
          </div>
        </div>

        {/* Detailed User Table */}
        <div style={{ overflowX: 'auto', border: '1.5px solid var(--color-border)', borderRadius: '12px' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '14px' }}>
            <thead>
              <tr style={{ background: '#f8fafc', borderBottom: '1.5px solid var(--color-border)', color: 'var(--color-text-muted)', fontWeight: 600 }}>
                <th style={{ padding: '16px 20px' }}>User Details</th>
                <th style={{ padding: '16px' }}>Role</th>
                <th style={{ padding: '16px', cursor: 'pointer' }} onClick={() => toggleSort('image_count')}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                    Uploaded Images <ArrowUpDown size={14} />
                  </div>
                </th>
                <th style={{ padding: '16px', cursor: 'pointer' }} onClick={() => toggleSort('reward_points')}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                    Reward Points <ArrowUpDown size={14} />
                  </div>
                </th>
                <th style={{ padding: '16px 20px' }}>Contribution Status</th>
              </tr>
            </thead>
            <tbody>
              {filteredUsers.length > 0 ? (
                filteredUsers.map((user) => {
                  const badge = getContributionBadge(user.reward_points || 0);
                  const maxTarget = Math.max(500, user.reward_points || 0);
                  const progressPct = Math.min(100, Math.round(((user.reward_points || 0) / maxTarget) * 100));

                  // Initials dicebear SVG avatar generator seed
                  const avatarSeed = user.email.split('@')[0];
                  const avatarUrl = `https://api.dicebear.com/7.x/initials/svg?seed=${encodeURIComponent(avatarSeed)}&backgroundColor=bbf7d0,dcfce7,86efac,a7f3d0`;

                  return (
                    <tr
                      key={user.user_id}
                      style={{
                        borderBottom: '1px solid var(--color-border)',
                        transition: 'background 0.2s',
                      }}
                      className="table-row-hover"
                    >
                      <td style={{ padding: '16px 20px', display: 'flex', alignItems: 'center', gap: '14px' }}>
                        <img
                          src={avatarUrl}
                          alt={user.email}
                          style={{ width: '40px', height: '40px', borderRadius: '50%', objectFit: 'cover', border: '1.5px solid var(--color-border)' }}
                        />
                        <div style={{ display: 'flex', flexDirection: 'column' }}>
                          <span style={{ fontWeight: 600, color: 'var(--color-text-main)' }}>{user.email}</span>
                          <span style={{ fontSize: '11px', color: 'var(--color-text-muted)' }}>ID: {user.user_id}</span>
                        </div>
                      </td>
                      <td style={{ padding: '16px' }}>
                        <span
                          style={{
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: '4px',
                            fontSize: '12px',
                            fontWeight: 600,
                            padding: '4px 8px',
                            borderRadius: '6px',
                            background: user.role === 'admin' ? '#f5f3ff' : '#f0fdf4',
                            color: user.role === 'admin' ? '#7c3aed' : '#15803d',
                          }}
                        >
                          {user.role === 'admin' ? (
                            <>
                              <Shield size={12} />
                              Console Admin
                            </>
                          ) : (
                            'Contributor'
                          )}
                        </span>
                      </td>
                      <td style={{ padding: '16px', fontWeight: 600, color: 'var(--color-text-main)' }}>
                        {user.image_count || 0} uploads
                      </td>
                      <td style={{ padding: '16px', fontWeight: 700, color: 'var(--color-primary)' }}>
                        {user.reward_points || 0} pts
                      </td>
                      <td style={{ padding: '16px 20px' }}>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', maxWidth: '180px' }}>
                          <span
                            style={{
                              fontSize: '11px',
                              fontWeight: 700,
                              color: badge.color,
                              backgroundColor: badge.bg,
                              padding: '2px 8px',
                              borderRadius: '4px',
                              alignSelf: 'flex-start',
                              letterSpacing: '0.2px',
                              textTransform: 'uppercase',
                            }}
                          >
                            {badge.label}
                          </span>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                            <div style={{ flexGrow: 1, height: '5px', background: '#e2e8f0', borderRadius: '3px', overflow: 'hidden' }}>
                              <div style={{ height: '100%', background: badge.color, width: `${progressPct}%`, borderRadius: '3px' }} />
                            </div>
                            <span style={{ fontSize: '11px', color: 'var(--color-text-muted)', fontWeight: 600 }}>{progressPct}%</span>
                          </div>
                        </div>
                      </td>
                    </tr>
                  );
                })
              ) : (
                <tr>
                  <td colSpan="5" style={{ padding: '36px', textAlign: 'center', color: 'var(--color-text-muted)' }}>
                    No users match your criteria. Try adjusting filters or searches.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

export default UsersView;

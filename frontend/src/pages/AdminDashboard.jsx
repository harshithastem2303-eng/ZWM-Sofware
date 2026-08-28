import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { fetchAnalyticsDetails, clearToken, fetchCategoriesList } from '../services/api';
import Sidebar from '../components/Sidebar';
import Header from '../components/Header';
import DashboardView from './DashboardView';
import ValidationView from './ValidationView';
import UsersView from './UsersView';
import ReportsView from './ReportsView';
import SettingsView from './SettingsView';

const AdminDashboard = () => {
  const navigate = useNavigate();

  // Core Shell State Management
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [analytics, setAnalytics] = useState(null);
  const [categoriesList, setCategoriesList] = useState([]);
  const [activeTab, setActiveTab] = useState('dashboard'); // 'dashboard', 'users', 'reports', 'settings'

  // Fetch initial analytics details and categories list
  const loadData = async () => {
    try {
      const data = await fetchAnalyticsDetails();
      setAnalytics(data);
      const catsData = await fetchCategoriesList();
      setCategoriesList(catsData.categories || []);
    } catch (err) {
      setError(err.message || 'Failed to load analytics details.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const handleLogout = () => {
    clearToken();
    navigate('/admin/login');
  };

  if (loading) {
    return (
      <div className="login-page" style={{ paddingBottom: 0 }}>
        <div className="spinner" style={{ width: '40px', height: '40px', borderTopColor: 'var(--color-primary)' }} />
        <p style={{ marginTop: '16px', fontWeight: '500', color: 'var(--color-primary)' }}>Loading ZWM system analytics...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="login-page" style={{ paddingBottom: 0 }}>
        <div className="error-banner">
          <span>{error}</span>
        </div>
        <button onClick={handleLogout} className="login-btn" style={{ maxWidth: '200px', marginTop: '20px' }}>
          Back to Login
        </button>
      </div>
    );
  }

  const renderActiveView = () => {
    switch (activeTab) {
      case 'dashboard':
        return <DashboardView analytics={analytics} categoriesList={categoriesList} refreshData={loadData} setActiveTab={setActiveTab} />;
      case 'validation':
        return <ValidationView refreshDashboardStats={loadData} setActiveTab={setActiveTab} />;
      case 'users':
        return <UsersView />;
      case 'reports':
        return <ReportsView analytics={analytics} />;
      case 'settings':
        return <SettingsView />;
      default:
        return <DashboardView analytics={analytics} categoriesList={categoriesList} refreshData={loadData} setActiveTab={setActiveTab} />;
    }
  };

  return (
    <div className="dashboard-layout" style={{ position: 'relative', overflow: 'hidden' }}>
      {/* Glowing background meshes */}
      <div className="login-bg-blob blob-1" style={{ top: '-10%', left: '15%', opacity: 0.15, filter: 'blur(150px)', pointerEvents: 'none' }} />
      <div className="login-bg-blob blob-2" style={{ bottom: '-10%', right: '10%', opacity: 0.12, filter: 'blur(150px)', pointerEvents: 'none' }} />

      {/* Sidebar Navigation */}
      <Sidebar activeTab={activeTab} setActiveTab={setActiveTab} onLogout={handleLogout} />

      {/* Main Panel Content */}
      <main className="dashboard-main" style={{ position: 'relative', zIndex: 1 }}>
        {/* Top Control Header */}
        <Header />

        {/* Dynamic Inner Tab Workspace View */}
        {renderActiveView()}
      </main>
    </div>
  );
};

export default AdminDashboard;

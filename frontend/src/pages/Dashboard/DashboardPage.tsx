import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { TopBar } from '../../components/dashboard/TopBar';
import { WorkflowSteps } from '../../components/dashboard/WorkflowSteps';
import { StatCard } from '../../components/dashboard/StatCard';
import { CardLeafWatermark } from '../../assets/icons/LeafAccents';
import { userService, UserDashboardData } from '../../services/userService';

export const DashboardPage: React.FC = () => {
  const navigate = useNavigate();
  const [dashboardData, setDashboardData] = useState<UserDashboardData | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const fetchDashboard = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await userService.getDashboard();
      setDashboardData(data);
    } catch (err: any) {
      setError(err.message || 'Failed to load dashboard data.');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchDashboard();
  }, []);

  const handleNavigateUpload = () => {
    navigate('/dashboard/upload');
  };

  if (isLoading) {
    return (
      <div style={{ padding: '60px 20px', textAlign: 'center', color: '#317827', fontWeight: 600, fontSize: '1.1rem' }}>
        Loading dashboard data from server...
      </div>
    );
  }

  if (error) {
    return (
      <div style={{ padding: '32px', textAlign: 'center', backgroundColor: '#fef2f2', borderRadius: '16px', border: '1px solid #fecaca', margin: '24px 0' }}>
        <p style={{ color: '#dc2626', fontWeight: 600, marginBottom: '16px', fontSize: '1rem' }}>{error}</p>
        <button
          onClick={fetchDashboard}
          style={{
            padding: '10px 20px',
            backgroundColor: '#168a1a',
            color: '#ffffff',
            border: 'none',
            borderRadius: '8px',
            cursor: 'pointer',
            fontWeight: 600,
            fontSize: '0.95rem'
          }}
        >
          Retry
        </button>
      </div>
    );
  }

  const userName = dashboardData?.user.full_name?.split(' ')[0] || dashboardData?.user.email || 'User';

  return (
    <>
      {/* 1. HEADER ROW: Welcome Greeting on Left + Points & Profile on Right */}
      <section className="dashboard-header-row">
        <div className="dashboard-welcome-col">
          <h1 className="dashboard-title">
            Welcome {userName} ✋
          </h1>
          <p className="dashboard-subtitle">
            Upload, annotate and build better datasets for a cleaner planet.
          </p>
        </div>

        <div className="dashboard-topbar-col">
          <TopBar />
        </div>
      </section>

      {/* 2. WORKFLOW SECTION: 3-Step Horizontal Process Card */}
      <WorkflowSteps />

      {/* 3. UPLOAD SECTION: Large Centered Upload Area */}
      <section
        className="upload-hero-card"
        onClick={handleNavigateUpload}
        role="button"
        tabIndex={0}
        aria-label="Upload waste image"
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            handleNavigateUpload();
          }
        }}
      >
        <CardLeafWatermark className="upload-card-leaf-watermark" size={145} />

        <button
          type="button"
          className="btn-upload-primary"
          onClick={(e) => {
            e.stopPropagation();
            handleNavigateUpload();
          }}
        >
          {/* Cloud with Up-Arrow Vector */}
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path
              d="M7 16 C4.5 16 3 14.2 3 12 C3 10 4.5 8.4 6.5 8.2 C7 5.2 9.5 3 12.5 3 C15.8 3 18.5 5.5 18.8 8.8 C20.6 9.1 22 10.6 22 12.5 C22 14.5 20.4 16 18.5 16"
              stroke="#ffffff"
              strokeWidth="2.2"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
            <path
              d="M12.5 9.5 V18.5 M9.5 12.5 L12.5 9.5 L15.5 12.5"
              stroke="#ffffff"
              strokeWidth="2.2"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
          <span>Upload Image</span>
        </button>

        <p className="upload-hero-subtext">Click to upload or drag & drop your image here</p>
        <p className="upload-hero-formats">JPG, PNG, JPEG up to 10MB</p>
      </section>

      {/* 4. STATISTICS SECTION: Three Statistic Cards */}
      <section className="stats-grid">
        {/* Card 1: Total Submissions */}
        <StatCard
          icon={
            <svg width="30" height="30" viewBox="0 0 28 28" fill="none" xmlns="http://www.w3.org/2000/svg">
              <rect x="3.5" y="4.5" width="21" height="19" rx="4" stroke="#317827" strokeWidth="2.2" />
              <circle cx="9" cy="9.5" r="2" fill="#317827" />
              <path
                d="M24 18 L18.5 12.5 L7.5 23.5"
                stroke="#317827"
                strokeWidth="2.2"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
              <path
                d="M13.5 17.5 L16.5 14.5 L23.5 21.5"
                stroke="#317827"
                strokeWidth="2.2"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          }
          title="Total Submissions"
          value={dashboardData?.stats.total_submissions ?? 0}
          subtext="All waste images uploaded"
          infoDetail="Real-time count of total submissions by your account from database."
        />

        {/* Card 2: Reward Points */}
        <StatCard
          icon={
            <svg width="30" height="30" viewBox="0 0 28 28" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path
                d="M14 3.5 L22.5 6.8 V13.2 C22.5 18.5 18.9 23.2 14 24.5 C9.1 23.2 5.5 18.5 5.5 13.2 V6.8 L14 3.5 Z"
                stroke="#317827"
                strokeWidth="2.2"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
              <path
                d="M10 13.5 L13 16.5 L18 10.5"
                stroke="#317827"
                strokeWidth="2.4"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          }
          title="Reward Points"
          value={dashboardData?.stats.points ?? 0}
          subtext="Points earned for contributions"
          infoDetail="Reward points awarded for verified uploads."
        />
      </section>

      {/* 5. RECENT SUBMISSIONS SECTION */}
      <section style={{ marginTop: '32px' }}>
        <h2 style={{ fontSize: '1.25rem', fontWeight: 700, color: '#166534', marginBottom: '16px' }}>
          Recent Submissions
        </h2>
        {!dashboardData?.recent_submissions || dashboardData.recent_submissions.length === 0 ? (
          <div style={{
            backgroundColor: '#ffffff',
            borderRadius: '16px',
            padding: '24px',
            textAlign: 'center',
            color: '#6b7280',
            border: '1px solid #e5e7eb'
          }}>
            No submissions yet. Upload your first waste image above!
          </div>
        ) : (
          <div style={{
            backgroundColor: '#ffffff',
            borderRadius: '16px',
            border: '1px solid #e5e7eb',
            overflow: 'hidden',
            boxShadow: '0 1px 3px rgba(0,0,0,0.05)'
          }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.9rem' }}>
              <thead>
                <tr style={{ backgroundColor: '#f9fafb', borderBottom: '1px solid #e5e7eb', color: '#4b5563' }}>
                  <th style={{ padding: '12px 16px', fontWeight: 600 }}>Filename</th>
                  <th style={{ padding: '12px 16px', fontWeight: 600 }}>Status</th>
                  <th style={{ padding: '12px 16px', fontWeight: 600 }}>Validation</th>
                  <th style={{ padding: '12px 16px', fontWeight: 600 }}>Credits</th>
                  <th style={{ padding: '12px 16px', fontWeight: 600 }}>Uploaded At</th>
                </tr>
              </thead>
              <tbody>
                {dashboardData.recent_submissions.map((sub) => (
                  <tr key={sub.id} style={{ borderBottom: '1px solid #f3f4f6' }}>
                    <td style={{ padding: '12px 16px', fontWeight: 500, color: '#111827' }}>{sub.filename}</td>
                    <td style={{ padding: '12px 16px', color: '#6b7280', textTransform: 'capitalize' }}>{sub.status}</td>
                    <td style={{ padding: '12px 16px' }}>
                      <span style={{
                        padding: '4px 10px',
                        borderRadius: '9999px',
                        fontSize: '0.75rem',
                        fontWeight: 600,
                        backgroundColor: sub.is_validated ? '#dcfce7' : '#fef3c7',
                        color: sub.is_validated ? '#15803d' : '#b45309'
                      }}>
                        {sub.is_validated ? 'Validated' : 'Pending'}
                      </span>
                    </td>
                    <td style={{ padding: '12px 16px', color: '#16a34a', fontWeight: 600 }}>+{sub.credits_awarded} pts</td>
                    <td style={{ padding: '12px 16px', color: '#9ca3af' }}>
                      {sub.uploaded_at ? new Date(sub.uploaded_at).toLocaleDateString() : 'N/A'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  );
};

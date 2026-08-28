import React, { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { TopBar } from '../../components/dashboard/TopBar';
import { WorkflowSteps } from '../../components/dashboard/WorkflowSteps';
import { StatCard } from '../../components/dashboard/StatCard';
import { CardLeafWatermark } from '../../assets/icons/LeafAccents';
import { useAuth } from '../../context/AuthContext';

export const DashboardPage: React.FC = () => {
  const navigate = useNavigate();
  const { user, stats, refreshStats, isSyncing } = useAuth();

  // Fetch real-time data from database on mount
  useEffect(() => {
    refreshStats();
  }, [refreshStats]);

  const handleNavigateUpload = () => {
    navigate('/dashboard/upload');
  };

  const userName = user.full_name?.split(' ')[0] || 'Keerthana';

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

      {/* 4. STATISTICS SECTION: Exactly TWO Statistic Cards Side-by-Side */}
      <section className="stats-grid">
        {/* Card 1: Total Images Uploaded */}
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
          title="Total Images Uploaded"
          value={stats.total_uploads ?? 0}
          subtext="All images you have uploaded"
          infoDetail="Real-time count of total images uploaded by your account in the database."
          isSyncing={isSyncing}
        />

        {/* Card 2: Validated Images */}
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
          title="Validated Images"
          value={stats.validated_images ?? 0}
          subtext="Images that are validated"
          infoDetail="Real-time count of images that have been verified and approved into the dataset."
          isSyncing={isSyncing}
        />
      </section>
    </>
  );
};

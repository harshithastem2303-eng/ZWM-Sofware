import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Star,
  Award,
  Calendar,
  Mail,
  Shield,
  Upload,
  CheckCircle,
  ArrowLeft,
  Clock,
} from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { Button } from '../../components/common/Button';
import { TopBar } from '../../components/dashboard/TopBar';

export const ProfilePage: React.FC = () => {
  const navigate = useNavigate();
  const { user, stats } = useAuth();
  const [activeTab, setActiveTab] = useState<'overview' | 'rewards' | 'settings'>('overview');

  const transactions = [
    { id: 1, desc: 'Verified Plastic Bottle Upload', points: 10, time: '2 hours ago', type: 'upload' },
    { id: 2, desc: 'Paper Box Annotation Verified', points: 15, time: 'Yesterday', type: 'annotation' },
    { id: 3, desc: 'Metal Can Multi-Object Detection', points: 10, time: '3 days ago', type: 'upload' },
    { id: 4, desc: 'Early Dataset Contributor Bonus', points: 50, time: '1 week ago', type: 'bonus' },
    { id: 5, desc: 'Glass Bottle Validation Streak', points: 20, time: '2 weeks ago', type: 'streak' },
  ];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', flexWrap: 'wrap', gap: '16px' }}>
        <div>
          <button
            onClick={() => navigate('/dashboard')}
            style={{
              background: 'none',
              border: 'none',
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              color: 'var(--primary-700)',
              fontWeight: 600,
              fontSize: '0.88rem',
              cursor: 'pointer',
              marginBottom: '6px',
            }}
          >
            <ArrowLeft size={16} /> Back to Dashboard
          </button>
          <h1 className="dashboard-title">User Profile & Rewards 👤</h1>
          <p className="dashboard-subtitle">
            Manage your account information, review your earned reward points, and track contribution streaks.
          </p>
        </div>
        <TopBar />
      </div>

      {/* Profile Header Hero Card */}
      <div
        style={{
          background: 'var(--pure-white)',
          borderRadius: 'var(--radius-lg)',
          padding: '32px',
          border: '1px solid var(--border-color)',
          boxShadow: 'var(--shadow-sm)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: '20px',
        }}
      >
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <h2 style={{ fontSize: '1.6rem', fontWeight: 800, color: 'var(--text-primary)', margin: 0 }}>
              {user.full_name || 'Keerthana H M'}
            </h2>
            <span
              style={{
                backgroundColor: 'var(--pale-green)',
                color: 'var(--primary-green)',
                fontSize: '0.75rem',
                fontWeight: 700,
                padding: '4px 10px',
                borderRadius: 'var(--radius-pill)',
                display: 'inline-flex',
                alignItems: 'center',
                gap: '4px',
              }}
            >
              <Award size={13} /> Eco Champion
            </span>
          </div>

          <div style={{ display: 'flex', gap: '18px', marginTop: '10px', color: 'var(--text-secondary)', fontSize: '0.86rem', flexWrap: 'wrap', alignItems: 'center' }}>
            <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <Mail size={15} color="var(--primary-green)" /> {user.email || 'keerthana@zwm.eco'}
            </span>
            <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <Shield size={15} color="var(--primary-green)" /> Role: Contributor
            </span>
            <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <Calendar size={15} color="var(--primary-green)" /> Joined Jan 2025
            </span>
          </div>
        </div>

        {/* Big Points Badge */}
        <div
          style={{
            background: 'var(--very-light-green)',
            border: '1.5px solid var(--border-color)',
            borderRadius: 'var(--radius-lg)',
            padding: '16px 28px',
            textAlign: 'center',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '6px', color: 'var(--primary-green)', fontWeight: 600, fontSize: '0.85rem' }}>
            <Star size={16} fill="var(--cta-green)" color="var(--primary-green)" /> Total Points
          </div>
          <div style={{ fontSize: '2.4rem', fontWeight: 800, color: 'var(--cta-green)', lineHeight: 1.1, marginTop: '4px' }}>
            {stats.reward_points ?? 320}
          </div>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', fontWeight: 500 }}>
            Redeemable for eco-perks
          </span>
        </div>
      </div>

      {/* Tabs */}
      <div style={{ display: 'flex', gap: '12px', borderBottom: '1px solid #e2e8f0', paddingBottom: '2px' }}>
        {(['overview', 'rewards', 'settings'] as const).map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            style={{
              padding: '10px 20px',
              border: 'none',
              background: 'none',
              borderBottom: activeTab === tab ? '2.5px solid var(--primary-600)' : '2.5px solid transparent',
              color: activeTab === tab ? 'var(--primary-700)' : 'var(--neutral-500)',
              fontWeight: activeTab === tab ? 700 : 500,
              fontSize: '0.95rem',
              cursor: 'pointer',
              textTransform: 'capitalize',
            }}
          >
            {tab}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      {activeTab === 'overview' && (
        <div
          style={{
            background: '#ffffff',
            borderRadius: 'var(--radius-lg)',
            padding: '24px',
            border: '1px solid #edf5ed',
            boxShadow: 'var(--shadow-sm)',
          }}
        >
          <h3 style={{ fontSize: '1.05rem', fontWeight: 700, marginBottom: '18px', color: 'var(--neutral-800)' }}>
            Contribution Summary
          </h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '12px 16px', background: '#f8fafc', borderRadius: 'var(--radius-md)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                <Upload size={18} color="var(--primary-600)" />
                <span style={{ fontWeight: 600, color: 'var(--neutral-700)', fontSize: '0.9rem' }}>Total Images Uploaded</span>
              </div>
              <span style={{ fontWeight: 800, color: 'var(--primary-700)', fontSize: '1.2rem' }}>
                {stats.total_uploads ?? 128}
              </span>
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '12px 16px', background: '#f8fafc', borderRadius: 'var(--radius-md)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                <CheckCircle size={18} color="var(--primary-600)" />
                <span style={{ fontWeight: 600, color: 'var(--neutral-700)', fontSize: '0.9rem' }}>Validated Datasets</span>
              </div>
              <span style={{ fontWeight: 800, color: 'var(--primary-700)', fontSize: '1.2rem' }}>
                {stats.validated_images ?? 96}
              </span>
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '12px 16px', background: '#f8fafc', borderRadius: 'var(--radius-md)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                <Clock size={18} color="#f59e0b" />
                <span style={{ fontWeight: 600, color: 'var(--neutral-700)', fontSize: '0.9rem' }}>Pending Verification</span>
              </div>
              <span style={{ fontWeight: 800, color: '#f59e0b', fontSize: '1.2rem' }}>
                {stats.pending_images ?? 32}
              </span>
            </div>
          </div>
        </div>
      )}

      {activeTab === 'rewards' && (
        <div
          style={{
            background: '#ffffff',
            borderRadius: 'var(--radius-lg)',
            padding: '24px',
            border: '1px solid #edf5ed',
            boxShadow: 'var(--shadow-sm)',
          }}
        >
          <h3 style={{ fontSize: '1.05rem', fontWeight: 700, marginBottom: '16px', color: 'var(--neutral-800)' }}>
            Recent Points & Reward Transactions
          </h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
            {transactions.map((tx) => (
              <div
                key={tx.id}
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  padding: '14px 18px',
                  borderRadius: 'var(--radius-md)',
                  backgroundColor: '#f8fafc',
                  border: '1px solid #f1f5f9',
                }}
              >
                <div>
                  <div style={{ fontWeight: 600, color: 'var(--neutral-800)', fontSize: '0.92rem' }}>
                    {tx.desc}
                  </div>
                  <div style={{ fontSize: '0.78rem', color: 'var(--neutral-400)', marginTop: '2px' }}>
                    {tx.time}
                  </div>
                </div>
                <div style={{ fontWeight: 800, color: 'var(--primary-600)', fontSize: '1.1rem' }}>
                  +{tx.points} pts
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {activeTab === 'settings' && (
        <div
          style={{
            background: '#ffffff',
            borderRadius: 'var(--radius-lg)',
            padding: '28px',
            border: '1px solid #edf5ed',
            boxShadow: 'var(--shadow-sm)',
            maxWidth: '600px',
          }}
        >
          <h3 style={{ fontSize: '1.1rem', fontWeight: 700, marginBottom: '18px', color: 'var(--neutral-800)' }}>
            Account Preferences
          </h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <div className="form-group">
              <label className="form-label">Full Name</label>
              <input className="form-input" defaultValue={user.full_name || 'Keerthana H M'} />
            </div>
            <div className="form-group">
              <label className="form-label">Email Address</label>
              <input className="form-input" defaultValue={user.email || 'keerthana@zwm.eco'} disabled />
            </div>
            <Button variant="primary" style={{ alignSelf: 'flex-start' }}>
              Save Changes
            </Button>
          </div>
        </div>
      )}
    </div>
  );
};

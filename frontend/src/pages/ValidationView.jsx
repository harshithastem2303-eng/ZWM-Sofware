import React, { useState, useEffect } from 'react';
import { fetchValidationQueue, validateImageAction, getImageUrl, getToken } from '../services/api';
import { Check, X, ShieldAlert, Image as ImageIcon, Calendar, User, Eye, ArrowRight, CheckCircle2 } from 'lucide-react';

// Secure Image component to handle authorization header for static assets
const SecureImage = ({ src, alt, className, style }) => {
  const [imageSrc, setImageSrc] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    let isMounted = true;
    const loadImage = async () => {
      try {
        setLoading(true);
        const token = getToken();
        const response = await fetch(src, {
          headers: {
            'Authorization': `Bearer ${token}`
          }
        });
        if (!response.ok) throw new Error('Failed to load image');
        const blob = await response.blob();
        const objectUrl = URL.createObjectURL(blob);
        if (isMounted) {
          setImageSrc(objectUrl);
          setLoading(false);
        }
      } catch (err) {
        if (isMounted) {
          setError(true);
          setLoading(false);
        }
      }
    };

    loadImage();

    return () => {
      isMounted = false;
      if (imageSrc) {
        URL.revokeObjectURL(imageSrc);
      }
    };
  }, [src]);

  if (loading) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', minHeight: '200px' }}>
        <div className="spinner" style={{ width: '32px', height: '32px', borderTopColor: 'var(--color-primary)' }} />
      </div>
    );
  }

  if (error) {
    return (
      <div style={{ color: 'var(--color-error)', fontSize: '13px', display: 'flex', flexDirection: 'column', gap: '8px', alignItems: 'center', justifyContent: 'center', height: '100%', minHeight: '200px' }}>
        <ShieldAlert size={28} />
        <span>Failed to load image file from disk</span>
      </div>
    );
  }

  return <img src={imageSrc} alt={alt} className={className} style={{ ...style, width: '100%', height: '100%', objectFit: 'contain' }} />;
};

const ValidationView = ({ refreshDashboardStats, setActiveTab }) => {
  const [queue, setQueue] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [selectedIdx, setSelectedIdx] = useState(null);
  const [actionLoading, setActionLoading] = useState(false);
  const [actionSuccess, setActionSuccess] = useState('');
  const [actionError, setActionError] = useState('');

  const loadQueue = async () => {
    try {
      setLoading(true);
      const data = await fetchValidationQueue();
      const imagesQueue = data.queue || [];
      setQueue(imagesQueue);
      if (imagesQueue.length > 0) {
        setSelectedIdx(0);
      } else {
        setSelectedIdx(null);
      }
    } catch (err) {
      setError(err.message || 'Failed to load validation queue');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadQueue();
  }, []);

  const handleValidationAction = async (imageId, action) => {
    setActionLoading(true);
    setActionSuccess('');
    setActionError('');
    try {
      await validateImageAction(imageId, action);
      setActionSuccess(`Successfully ${action === 'approve' ? 'approved' : 'rejected'} image.`);
      
      // Remove item from queue list
      const updatedQueue = queue.filter(item => item.image_id !== imageId);
      setQueue(updatedQueue);

      // Select next item or null
      if (updatedQueue.length > 0) {
        setSelectedIdx(Math.min(selectedIdx, updatedQueue.length - 1));
      } else {
        setSelectedIdx(null);
      }

      // Propagate update up to dashboard header/KPIs
      if (refreshDashboardStats) {
        refreshDashboardStats();
      }
    } catch (err) {
      setActionError(err.message || `Failed to ${action} image.`);
    } finally {
      setActionLoading(false);
      // Auto-clear success banner
      setTimeout(() => setActionSuccess(''), 4000);
    }
  };

  if (loading) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: '400px' }}>
        <div className="spinner" style={{ width: '40px', height: '40px', borderTopColor: 'var(--color-primary)' }} />
        <p style={{ marginTop: '16px', fontWeight: '500', color: 'var(--color-primary)' }}>Loading pending validation queue...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="dashboard-card" style={{ padding: '40px', textAlign: 'center', borderColor: 'var(--color-error)' }}>
        <div className="error-banner" style={{ display: 'inline-flex', marginBottom: '0' }}>
          <span>{error}</span>
        </div>
      </div>
    );
  }

  const selectedImage = selectedIdx !== null ? queue[selectedIdx] : null;

  return (
    <div className="page-fade-in" style={{ display: 'flex', flexDirection: 'column', gap: '28px' }}>
      {/* Page Heading */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '28px' }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          <h1 style={{ fontSize: '32px', fontWeight: 700, color: '#0F172A', fontFamily: 'var(--font-main)', lineHeight: '1.2' }}>
            Validation
          </h1>
          <p style={{ fontSize: '14px', fontWeight: 400, color: '#64748B', fontFamily: 'var(--font-main)' }}>
            Review and approve submitted waste images before they enter the dataset.
          </p>
        </div>
        <div style={{ display: 'flex', gap: '8px', paddingTop: '4px' }}>
          <span style={{ fontSize: '12px', background: 'var(--color-primary-light)', color: 'var(--color-primary)', padding: '6px 14px', borderRadius: '12px', fontWeight: 700 }}>
            {queue.length} Pending Validation
          </span>
        </div>
      </div>

      {actionSuccess && (
        <div className="panel-alert panel-alert-success" style={{ padding: '14px', fontSize: '14px', display: 'flex', alignItems: 'center', gap: '8px', borderRadius: '12px' }}>
          <CheckCircle2 size={16} />
          {actionSuccess}
        </div>
      )}

      {actionError && (
        <div className="panel-alert panel-alert-error" style={{ padding: '14px', fontSize: '14px', display: 'flex', alignItems: 'center', gap: '8px', borderRadius: '12px' }}>
          <ShieldAlert size={16} />
          {actionError}
        </div>
      )}

      {queue.length === 0 ? (
        <div className="dashboard-card" style={{ padding: '60px 40px', textAlign: 'center', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '16px' }}>
          <div style={{ width: '64px', height: '64px', borderRadius: '50%', backgroundColor: 'var(--color-primary-light)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--color-primary)' }}>
            <Check size={32} strokeWidth={3} />
          </div>
          <h3 style={{ fontSize: '20px', fontWeight: 700, color: 'var(--color-text-main)' }}>All Images Validated</h3>
          <p style={{ color: 'var(--color-text-muted)', fontSize: '14px', maxWidth: '400px' }}>Nice job! The database is clean. There are no community uploads waiting for manual review.</p>
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: '320px 1fr', gap: '24px', alignItems: 'stretch' }}>
          {/* Left Column: Image Queue List */}
          <div className="dashboard-card" style={{ padding: '20px', display: 'flex', flexDirection: 'column', gap: '16px', maxHeight: '600px', overflowY: 'auto' }}>
            <span style={{ fontSize: '12px', fontWeight: 700, color: 'var(--color-text-muted)', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Pending Uploads</span>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
              {queue.map((item, idx) => {
                const isActive = selectedIdx === idx;
                const formattedDate = item.uploaded_at ? new Date(item.uploaded_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : 'Unknown Date';
                
                return (
                  <div
                    key={item.image_id}
                    onClick={() => setSelectedIdx(idx)}
                    style={{
                      padding: '12px 16px',
                      borderRadius: '14px',
                      border: isActive ? '1.5px solid var(--color-primary)' : '1.5px solid var(--color-border)',
                      backgroundColor: isActive ? 'var(--color-primary-light)' : '#ffffff',
                      cursor: 'pointer',
                      transition: 'all 0.2s ease',
                      display: 'flex',
                      flexDirection: 'column',
                      gap: '4px'
                    }}
                  >
                    <span style={{ fontSize: '13px', fontWeight: 600, color: 'var(--color-text-main)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {item.original_filename}
                    </span>
                    <span style={{ fontSize: '11px', color: 'var(--color-text-muted)', display: 'flex', alignItems: 'center', gap: '4px' }}>
                      <User size={10} /> {item.uploader_email}
                    </span>
                    <span style={{ fontSize: '10px', color: 'var(--color-text-muted)', display: 'flex', alignItems: 'center', gap: '4px' }}>
                      <Calendar size={10} /> {formattedDate}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Right Column: Active Validation Panel */}
          {selectedImage && (
            <div className="dashboard-card" style={{ padding: '22px 24px', display: 'flex', flexDirection: 'column', gap: '24px' }}>
              {/* Panel Header */}
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', borderBottom: '1px solid var(--color-border)', paddingBottom: '16px' }}>
                <div>
                  <h3 style={{ fontSize: '18px', fontWeight: 700, color: 'var(--color-text-main)' }}>{selectedImage.original_filename}</h3>
                  <span style={{ fontSize: '11px', color: 'var(--color-text-muted)' }}>Image UUID: {selectedImage.image_id}</span>
                </div>
                <div style={{ display: 'flex', gap: '12px' }}>
                  <button
                    className="control-btn"
                    disabled={actionLoading}
                    onClick={() => handleValidationAction(selectedImage.image_id, 'reject')}
                    style={{ color: 'var(--color-error)', borderColor: '#fca5a5', display: 'flex', alignItems: 'center', gap: '6px', fontSize: '13px', padding: '8px 16px' }}
                  >
                    <X size={16} /> Reject Submission
                  </button>
                  <button
                    className="panel-btn"
                    disabled={actionLoading}
                    onClick={() => handleValidationAction(selectedImage.image_id, 'approve')}
                    style={{ backgroundColor: 'var(--color-primary)', display: 'flex', alignItems: 'center', gap: '6px', fontSize: '13px', padding: '8px 20px', width: 'auto' }}
                  >
                    <Check size={16} /> Approve & Promote
                  </button>
                </div>
              </div>

              {/* Panel Split Content */}
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 300px', gap: '24px', alignItems: 'start' }}>
                {/* Secure Image Preview Box */}
                <div style={{ border: '1.5px solid var(--color-border)', borderRadius: '16px', background: '#0f172a', padding: '16px', display: 'flex', alignItems: 'center', justifyContent: 'center', height: '400px', overflow: 'hidden', position: 'relative' }}>
                  <SecureImage src={getImageUrl(selectedImage.image_id)} alt={selectedImage.original_filename} />
                </div>

                {/* Annotation and Metadata Box */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
                  {/* Uploader Card */}
                  <div style={{ background: '#f8fafc', padding: '16px', borderRadius: '14px', border: '1px solid var(--color-border)', display: 'flex', flexDirection: 'column', gap: '10px' }}>
                    <span style={{ fontSize: '11px', fontWeight: 700, color: 'var(--color-text-muted)', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Uploader Telemetry</span>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', fontSize: '13px' }}>
                      <span style={{ color: 'var(--color-text-muted)' }}>Contributor: <strong style={{ color: 'var(--color-text-main)' }}>{selectedImage.uploader_email}</strong></span>
                      <span style={{ color: 'var(--color-text-muted)' }}>Uploaded: <strong style={{ color: 'var(--color-text-main)' }}>{selectedImage.uploaded_at ? new Date(selectedImage.uploaded_at).toLocaleString() : 'Unknown'}</strong></span>
                    </div>
                  </div>

                  {/* Annotations List */}
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                    <span style={{ fontSize: '11px', fontWeight: 700, color: 'var(--color-text-muted)', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Labeled Annotations ({selectedImage.annotations.length})</span>
                    {selectedImage.annotations.length === 0 ? (
                      <div style={{ fontSize: '13px', color: 'var(--color-text-muted)', fontStyle: 'italic', padding: '8px 4px' }}>
                        No bounding boxes annotated.
                      </div>
                    ) : (
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', maxHeight: '200px', overflowY: 'auto' }}>
                        {selectedImage.annotations.map((ann, idx) => (
                          <div key={idx} style={{ padding: '12px', background: '#f0fdf4', border: '1px solid #bbf7d0', borderRadius: '10px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                            <div style={{ display: 'flex', flexDirection: 'column' }}>
                              <span style={{ fontSize: '13px', fontWeight: 700, color: 'var(--color-primary)' }}>{ann.category_name}</span>
                              <span style={{ fontSize: '10px', color: 'var(--color-text-muted)' }}>Type: {ann.annotation_type || 'bounding_box'}</span>
                            </div>
                            <span style={{ fontSize: '9px', fontWeight: 700, padding: '2px 6px', borderRadius: '8px', backgroundColor: ann.ai_generated ? '#eff6ff' : '#ecfdf5', color: ann.ai_generated ? '#2563eb' : '#10b981' }}>
                              {ann.ai_generated ? 'AI Pre-filled' : 'Human Labeled'}
                            </span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default ValidationView;

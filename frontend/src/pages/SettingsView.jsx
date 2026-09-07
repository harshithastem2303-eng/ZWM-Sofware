import React, { useState, useEffect } from 'react';
import { Save, Sliders, Globe, Check, AlertCircle } from 'lucide-react';
import { fetchSystemSettings, updateSystemSettings } from '../services/api';

const SettingsView = () => {
  // General State
  const [platformName, setPlatformName] = useState('Zero Waste Management System');
  const [adminEmail, setAdminEmail] = useState('admin@zwm-system.com');
  const [apiBaseUrl, setApiBaseUrl] = useState('http://localhost:8000/api');
  const [maintenanceMode, setMaintenanceMode] = useState(false);

  // ML Pipeline State
  const [activeModel, setActiveModel] = useState('YOLO11');
  const [epochs, setEpochs] = useState(50);
  const [imageSize, setImageSize] = useState('640 × 640');
  const [batchSize, setBatchSize] = useState(16);
  const [confidenceThreshold, setConfidenceThreshold] = useState(0.65);
  const [autoRetrainCount, setAutoRetrainCount] = useState(1000);
  const [device, setDevice] = useState('GPU (CUDA)');
  const [optimizer, setOptimizer] = useState('AdamW');
  const [learningRate, setLearningRate] = useState(0.01);
  const [autoTrainToggle, setAutoTrainToggle] = useState(true);

  // Form submit state
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [successMsg, setSuccessMsg] = useState('');
  const [errorMsg, setErrorMsg] = useState('');

  useEffect(() => {
    const loadSettings = async () => {
      try {
        const data = await fetchSystemSettings();
        if (data) {
          if (data.platform_name) setPlatformName(data.platform_name);
          if (data.admin_email) setAdminEmail(data.admin_email);
          if (data.api_base_url) setApiBaseUrl(data.api_base_url);
          if (data.maintenance_mode !== undefined) setMaintenanceMode(data.maintenance_mode);
          if (data.active_model) setActiveModel(data.active_model);
          if (data.epochs) setEpochs(data.epochs);
          if (data.image_size) setImageSize(data.image_size);
          if (data.batch_size) setBatchSize(data.batch_size);
          if (data.confidence_threshold !== undefined) setConfidenceThreshold(data.confidence_threshold);
          if (data.auto_retrain_count) setAutoRetrainCount(data.auto_retrain_count);
          if (data.device) setDevice(data.device);
          if (data.optimizer) setOptimizer(data.optimizer);
          if (data.learning_rate) setLearningRate(data.learning_rate);
          if (data.auto_train_toggle !== undefined) setAutoTrainToggle(data.auto_train_toggle);
        }
      } catch (err) {
        console.warn('Backend settings fetch note:', err.message);
      } finally {
        setLoading(false);
      }
    };
    loadSettings();
  }, []);

  const handleSave = async (e) => {
    e.preventDefault();
    setSaving(true);
    setSuccessMsg('');
    setErrorMsg('');

    try {
      const payload = {
        platform_name: platformName,
        admin_email: adminEmail,
        api_base_url: apiBaseUrl,
        maintenance_mode: maintenanceMode,
        active_model: activeModel,
        epochs: parseInt(epochs) || 50,
        image_size: imageSize,
        batch_size: parseInt(batchSize) || 16,
        device: device,
        optimizer: optimizer,
        learning_rate: parseFloat(learningRate) || 0.01,
        auto_retrain_count: parseInt(autoRetrainCount) || 1000,
        confidence_threshold: parseFloat(confidenceThreshold) || 0.65,
        auto_train_toggle: autoTrainToggle,
      };

      await updateSystemSettings(payload);
      setSuccessMsg('All SaaS and machine learning parameters saved to backend database successfully!');
      window.scrollTo({ top: 0, behavior: 'smooth' });
    } catch (err) {
      setErrorMsg(err.message || 'Failed to save configuration settings to backend.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <form onSubmit={handleSave} className="page-fade-in" style={{ display: 'flex', flexDirection: 'column', gap: '32px' }}>
      
      {/* Page Heading */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '28px' }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          <h1 style={{ fontSize: '32px', fontWeight: 800, color: '#38240d', fontFamily: 'var(--font-main)', lineHeight: '1.2' }}>
            Settings
          </h1>
          <p style={{ fontSize: '14px', fontWeight: 400, color: '#786c5e', fontFamily: 'var(--font-main)' }}>
            Configure platform, dataset, and AI model settings.
          </p>
        </div>
        
        <button type="submit" className="login-btn" style={{ width: 'auto', padding: '10px 24px', fontSize: '14px', borderRadius: '12px', marginTop: '4px' }} disabled={saving}>
          {saving ? (
            <>
              <div className="spinner" />
              Saving Settings...
            </>
          ) : (
            <>
              <Save size={16} />
              Save Configurations
            </>
          )}
        </button>
      </div>

      {/* Success Notification */}
      {successMsg && (
        <div className="panel-alert panel-alert-success" style={{ padding: '16px', fontSize: '14px', display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Check size={18} />
          {successMsg}
        </div>
      )}

      {/* Error Notification */}
      {errorMsg && (
        <div className="panel-alert panel-alert-error" style={{ padding: '16px', fontSize: '14px', display: 'flex', alignItems: 'center', gap: '8px', color: '#dc2626', backgroundColor: '#fef2f2', border: '1px solid #fecaca', borderRadius: '8px' }}>
          <AlertCircle size={18} />
          {errorMsg}
        </div>
      )}

      {/* SaaS Configuration Panels Grid */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1.2fr', gap: '24px', alignItems: 'start' }}>
        
        {/* Left Column: General Platform Information */}
        <div className="dashboard-card" style={{ padding: '28px', display: 'flex', flexDirection: 'column', gap: '20px', height: 'fit-content' }}>
          <h3 style={{ fontSize: '16px', fontWeight: 700, borderBottom: '1.5px solid var(--color-border)', paddingBottom: '12px', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Globe size={18} style={{ color: 'var(--color-primary)' }} />
            General Information
          </h3>

          <div className="panel-input-group">
            <label className="panel-label">Platform Title</label>
            <input
              type="text"
              className="panel-input"
              value={platformName}
              onChange={(e) => setPlatformName(e.target.value)}
            />
          </div>

          <div className="panel-input-group">
            <label className="panel-label">System Administrator Email</label>
            <input
              type="email"
              className="panel-input"
              value={adminEmail}
              onChange={(e) => setAdminEmail(e.target.value)}
            />
          </div>

          <div className="panel-input-group">
            <label className="panel-label">FastAPI Base URL</label>
            <input
              type="text"
              className="panel-input"
              value={apiBaseUrl}
              onChange={(e) => setApiBaseUrl(e.target.value)}
            />
          </div>

          {/* Maintenance Mode Toggle Switch */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '8px 0', marginTop: '4px' }}>
            <div>
              <span style={{ fontSize: '14px', fontWeight: 600, color: 'var(--color-text-main)' }}>Platform Maintenance Mode</span>
              <p style={{ fontSize: '11px', color: 'var(--color-text-muted)', marginTop: '2px' }}>Lock access to uploader endpoints during platform upgrades.</p>
            </div>
            <label style={{ position: 'relative', display: 'inline-block', width: '50px', height: '26px' }}>
              <input
                type="checkbox"
                style={{ opacity: 0, width: 0, height: 0 }}
                checked={maintenanceMode}
                onChange={(e) => setMaintenanceMode(e.target.checked)}
              />
              <span style={{
                position: 'absolute', cursor: 'pointer', top: 0, left: 0, right: 0, bottom: 0,
                backgroundColor: maintenanceMode ? 'var(--color-primary)' : '#cbd5e1',
                transition: '.4s', borderRadius: '34px'
              }}>
                <span style={{
                  position: 'absolute', content: '""', height: '18px', width: '18px', left: maintenanceMode ? '28px' : '4px', bottom: '4px',
                  backgroundColor: 'white', transition: '.4s', borderRadius: '50%'
                }} />
              </span>
            </label>
          </div>
        </div>

        {/* Right Column: Machine Learning Pipeline */}
        <div className="dashboard-card" style={{ padding: '28px', display: 'flex', flexDirection: 'column', gap: '20px', height: 'fit-content' }}>
          <h3 style={{ fontSize: '16px', fontWeight: 700, borderBottom: '1.5px solid var(--color-border)', paddingBottom: '12px', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Sliders size={18} style={{ color: '#3b82f6' }} />
            Machine Learning Pipeline
          </h3>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
            <div className="panel-input-group">
              <label className="panel-label">YOLO Model Architecture</label>
              <select
                className="panel-select"
                value={activeModel}
                onChange={(e) => setActiveModel(e.target.value)}
              >
                <option value="YOLO11n">YOLO11n (Nano)</option>
                <option value="YOLO11">YOLO11 (Standard)</option>
                <option value="YOLO12">YOLO12 (Latest)</option>
                <option value="YOLO8">YOLO8 (Legacy)</option>
              </select>
              <span style={{ fontSize: '11px', color: 'var(--color-text-muted)', marginTop: '2px' }}>Active neural network topology.</span>
            </div>

            <div className="panel-input-group">
              <label className="panel-label">Training Epochs</label>
              <input
                type="number"
                className="panel-input"
                min="1"
                max="1000"
                value={epochs}
                onChange={(e) => setEpochs(parseInt(e.target.value) || 50)}
              />
              <span style={{ fontSize: '11px', color: 'var(--color-text-muted)', marginTop: '2px' }}>Total number of training cycles.</span>
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
            <div className="panel-input-group">
              <label className="panel-label">Input Image Size</label>
              <select
                className="panel-select"
                value={imageSize}
                onChange={(e) => setImageSize(e.target.value)}
              >
                <option value="320 × 320">320 × 320</option>
                <option value="416 × 416">416 × 416</option>
                <option value="640 × 640">640 × 640 (Recommended)</option>
                <option value="1024 × 1024">1024 × 1024</option>
              </select>
              <span style={{ fontSize: '11px', color: 'var(--color-text-muted)', marginTop: '2px' }}>Dimension for tensor scaling.</span>
            </div>

            <div className="panel-input-group">
              <label className="panel-label">Batch Size</label>
              <input
                type="number"
                className="panel-input"
                min="1"
                max="256"
                value={batchSize}
                onChange={(e) => setBatchSize(parseInt(e.target.value) || 16)}
              />
              <span style={{ fontSize: '11px', color: 'var(--color-text-muted)', marginTop: '2px' }}>Images per iteration batch.</span>
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
            <div className="panel-input-group">
              <label className="panel-label">Training Execution Device</label>
              <select
                className="panel-select"
                value={device}
                onChange={(e) => setDevice(e.target.value)}
              >
                <option value="GPU (CUDA)">GPU (CUDA)</option>
                <option value="CPU">CPU Only</option>
              </select>
            </div>

            <div className="panel-input-group">
              <label className="panel-label">Weights Optimization</label>
              <select
                className="panel-select"
                value={optimizer}
                onChange={(e) => setOptimizer(e.target.value)}
              >
                <option value="AdamW">AdamW (Recommended)</option>
                <option value="SGD">SGD</option>
                <option value="Adam">Adam</option>
              </select>
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
            <div className="panel-input-group">
              <label className="panel-label">Initial Learning Rate (lr0)</label>
              <input
                type="number"
                step="0.001"
                className="panel-input"
                value={learningRate}
                onChange={(e) => setLearningRate(parseFloat(e.target.value) || 0.01)}
              />
            </div>

            <div className="panel-input-group">
              <label className="panel-label">Auto-Trigger Threshold</label>
              <input
                type="number"
                className="panel-input"
                value={autoRetrainCount}
                onChange={(e) => setAutoRetrainCount(parseInt(e.target.value) || 1000)}
              />
            </div>
          </div>

          <div className="panel-input-group">
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <label className="panel-label">Confidence Threshold</label>
              <span style={{ fontSize: '12px', fontWeight: 700, color: 'var(--color-primary)' }}>{Math.round(confidenceThreshold * 100)}%</span>
            </div>
            <input
              type="range"
              min="0.30"
              max="0.95"
              step="0.05"
              style={{ accentColor: 'var(--color-primary)', cursor: 'pointer', marginTop: '6px' }}
              value={confidenceThreshold}
              onChange={(e) => setConfidenceThreshold(parseFloat(e.target.value))}
            />
            <span style={{ fontSize: '11px', color: 'var(--color-text-muted)', marginTop: '2px' }}>Min confidence required for AI category pre-filling.</span>
          </div>

          {/* Auto retraining toggle */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '8px 0', marginTop: '2px' }}>
            <div>
              <span style={{ fontSize: '14px', fontWeight: 600, color: 'var(--color-text-main)' }}>Automatic Retraining Trigger</span>
              <p style={{ fontSize: '11px', color: 'var(--color-text-muted)', marginTop: '2px' }}>Queue pipeline jobs when target parameters are met.</p>
            </div>
            <label style={{ position: 'relative', display: 'inline-block', width: '50px', height: '26px' }}>
              <input
                type="checkbox"
                style={{ opacity: 0, width: 0, height: 0 }}
                checked={autoTrainToggle}
                onChange={(e) => setAutoTrainToggle(e.target.checked)}
              />
              <span style={{
                position: 'absolute', cursor: 'pointer', top: 0, left: 0, right: 0, bottom: 0,
                backgroundColor: autoTrainToggle ? 'var(--color-primary)' : '#cbd5e1',
                transition: '.4s', borderRadius: '34px'
              }}>
                <span style={{
                  position: 'absolute', content: '""', height: '18px', width: '18px', left: autoTrainToggle ? '28px' : '4px', bottom: '4px',
                  backgroundColor: 'white', transition: '.4s', borderRadius: '50%'
                }} />
              </span>
            </label>
          </div>
        </div>

      </div>

    </form>
  );
};

export default SettingsView;

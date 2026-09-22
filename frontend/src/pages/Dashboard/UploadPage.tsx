import React, { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  UploadCloud,
  FileImage,
  AlertCircle,
  X,
  ArrowLeft,
  Sparkles,
  Camera,
  FolderOpen,
} from 'lucide-react';
import { Button } from '../../components/common/Button';
import { TopBar } from '../../components/dashboard/TopBar';
import { useAuth } from '../../context/AuthContext';
import { imageService } from '../../services/imageService';

export const UploadPage: React.FC = () => {
  const navigate = useNavigate();
  const { stats, updateStats, refreshStats } = useAuth();

  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Live Camera Modal States
  const [isCameraOpen, setIsCameraOpen] = useState(false);
  const [cameraError, setCameraError] = useState<string | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);

  // Clean up camera stream on unmount
  useEffect(() => {
    return () => {
      if (streamRef.current) {
        streamRef.current.getTracks().forEach((track) => track.stop());
      }
    };
  }, []);

  const startCamera = async () => {
    setErrorMessage(null);
    setCameraError(null);
    setIsCameraOpen(true);

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: { ideal: 'environment' }, width: { ideal: 1280 }, height: { ideal: 720 } },
        audio: false,
      });
      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
      }
    } catch (err: any) {
      console.error('Camera access error:', err);
      setCameraError('Unable to access device camera. Please check browser permissions or browse files.');
    }
  };

  const stopCamera = () => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    }
    setIsCameraOpen(false);
    setCameraError(null);
  };

  const capturePhoto = () => {
    if (!videoRef.current) return;
    const video = videoRef.current;
    const canvas = document.createElement('canvas');
    canvas.width = video.videoWidth || 640;
    canvas.height = video.videoHeight || 480;
    const ctx = canvas.getContext('2d');
    if (ctx) {
      ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
      canvas.toBlob(
        (blob) => {
          if (blob) {
            const capturedFile = new File([blob], `camera_capture_${Date.now()}.jpg`, { type: 'image/jpeg' });
            handleFileSelect(capturedFile);
            stopCamera();
          }
        },
        'image/jpeg',
        0.92
      );
    }
  };

  const handleFileSelect = (file: File) => {
    setErrorMessage(null);

    // Validate size (10MB)
    if (file.size > 10 * 1024 * 1024) {
      setErrorMessage('File size exceeds 10MB limit. Please choose a smaller image.');
      return;
    }

    // Validate type (Images only)
    const validTypes = ['image/jpeg', 'image/png', 'image/jpg', 'image/webp'];
    if (!validTypes.includes(file.type)) {
      setErrorMessage('Invalid file format. Please upload JPG, PNG, or WEBP images only.');
      return;
    }

    setSelectedFile(file);
    const objectUrl = URL.createObjectURL(file);
    setPreviewUrl(objectUrl);
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = () => {
    setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFileSelect(e.dataTransfer.files[0]);
    }
  };

  const handleClear = () => {
    setSelectedFile(null);
    if (previewUrl) {
      URL.revokeObjectURL(previewUrl);
    }
    setPreviewUrl(null);
    setErrorMessage(null);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const handleUploadAndAnnotate = async () => {
    if (!selectedFile) {
      setErrorMessage('Please select or capture an image first.');
      return;
    }

    setIsUploading(true);
    setErrorMessage(null);

    try {
      // Upload the image without preselected category (category selection is on annotation page)
      const res: any = await imageService.uploadImage(selectedFile);

      // Update upload count stats
      if (res.credits_awarded > 0) {
        updateStats({
          total_uploads: (stats.total_uploads || 0) + 1,
          reward_points: (stats.reward_points || 0) + res.credits_awarded,
        });
      }
      refreshStats();

      // Navigate to annotation page with image_id
      navigate('/dashboard/annotate', {
        state: {
          imageId: res.image_id,
          previewUrl: previewUrl,
        },
      });
    } catch (err: any) {
      setErrorMessage(err.message || 'Image upload failed. Please try again.');
    } finally {
      setIsUploading(false);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px', maxWidth: '1000px', margin: '0 auto', width: '100%' }}>
      {/* Page Header */}
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
          <h1 className="dashboard-title">Upload Waste Image 🌿</h1>
          <p className="dashboard-subtitle">
            Capture or select a waste photo from your device to begin annotation and earning reward points.
          </p>
        </div>
        <TopBar />
      </div>

      {/* Main Upload Clean Centered Card */}
      <div
        style={{
          background: '#ffffff',
          borderRadius: 'var(--radius-lg)',
          padding: '32px',
          border: '1px solid #edf5ed',
          boxShadow: 'var(--shadow-sm)',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'stretch',
          gap: '24px',
          width: '100%',
        }}
      >
        <h3 style={{ fontSize: '1.25rem', fontWeight: 700, color: 'var(--neutral-800)', margin: 0, textAlign: 'center' }}>
          Select or Capture Image
        </h3>

        {!previewUrl ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '20px', width: '100%' }}>
            {/* Drag & Drop Zone */}
            <div
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
              onClick={() => fileInputRef.current?.click()}
              style={{
                border: isDragging ? '2.5px dashed var(--primary-600)' : '2.5px dashed #a7f3d0',
                backgroundColor: isDragging ? '#f0fdf4' : '#fafdfa',
                borderRadius: 'var(--radius-lg)',
                padding: '60px 24px',
                textAlign: 'center',
                cursor: 'pointer',
                transition: 'all 0.2s ease',
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
                minHeight: '260px',
              }}
            >
              <input
                ref={fileInputRef}
                type="file"
                accept="image/png,image/jpeg,image/jpg,image/webp"
                style={{ display: 'none' }}
                onChange={(e) => e.target.files?.[0] && handleFileSelect(e.target.files[0])}
              />
              <div
                style={{
                  width: '72px',
                  height: '72px',
                  borderRadius: '50%',
                  backgroundColor: '#dcfce7',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  color: 'var(--primary-600)',
                  marginBottom: '16px',
                }}
              >
                <UploadCloud size={36} />
              </div>
              <p style={{ fontSize: '1.15rem', fontWeight: 700, color: 'var(--neutral-800)' }}>
                Drag and drop your image here
              </p>
              <p style={{ fontSize: '0.92rem', color: 'var(--neutral-500)', marginTop: '4px' }}>
                or <span style={{ color: 'var(--primary-600)', fontWeight: 600 }}>browse files</span> from your computer
              </p>
              <p style={{ fontSize: '0.78rem', color: 'var(--neutral-400)', marginTop: '12px' }}>
                Supports JPG, PNG, WEBP images only (Max 10MB)
              </p>
            </div>

            {/* Quick Action buttons */}
            <div style={{ display: 'flex', gap: '16px', justifyContent: 'center' }}>
              <button
                type="button"
                onClick={startCamera}
                style={{
                  flex: 1,
                  maxWidth: '300px',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: '10px',
                  padding: '16px 20px',
                  borderRadius: '30px',
                  border: '2.5px solid #14532d',
                  backgroundColor: '#16a34a',
                  color: '#ffffff',
                  fontWeight: 700,
                  fontSize: '1rem',
                  cursor: 'pointer',
                  transition: 'all 0.25s cubic-bezier(0.4, 0, 0.2, 1)',
                  boxShadow: '0 4px 14px rgba(22, 163, 74, 0.3)',
                }}
                onMouseOver={(e) => {
                  e.currentTarget.style.backgroundColor = '#15803d';
                  e.currentTarget.style.borderColor = '#14532d';
                  e.currentTarget.style.transform = 'translateY(-2px)';
                  e.currentTarget.style.boxShadow = '0 6px 20px rgba(21, 128, 61, 0.4)';
                }}
                onMouseOut={(e) => {
                  e.currentTarget.style.backgroundColor = '#16a34a';
                  e.currentTarget.style.borderColor = '#14532d';
                  e.currentTarget.style.transform = 'translateY(0)';
                  e.currentTarget.style.boxShadow = '0 4px 14px rgba(22, 163, 74, 0.3)';
                }}
              >
                <Camera size={22} color="#bbf7d0" />
                Capture Image
              </button>

              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                style={{
                  flex: 1,
                  maxWidth: '300px',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: '10px',
                  padding: '16px 20px',
                  borderRadius: '30px',
                  border: '2.5px solid #14532d',
                  backgroundColor: '#16a34a',
                  color: '#ffffff',
                  fontWeight: 700,
                  fontSize: '1rem',
                  cursor: 'pointer',
                  transition: 'all 0.25s cubic-bezier(0.4, 0, 0.2, 1)',
                  boxShadow: '0 4px 14px rgba(22, 163, 74, 0.3)',
                }}
                onMouseOver={(e) => {
                  e.currentTarget.style.backgroundColor = '#15803d';
                  e.currentTarget.style.borderColor = '#14532d';
                  e.currentTarget.style.transform = 'translateY(-2px)';
                  e.currentTarget.style.boxShadow = '0 6px 20px rgba(21, 128, 61, 0.4)';
                }}
                onMouseOut={(e) => {
                  e.currentTarget.style.backgroundColor = '#16a34a';
                  e.currentTarget.style.borderColor = '#14532d';
                  e.currentTarget.style.transform = 'translateY(0)';
                  e.currentTarget.style.boxShadow = '0 4px 14px rgba(22, 163, 74, 0.3)';
                }}
              >
                <FolderOpen size={22} color="#bbf7d0" />
                Browse Device Images
              </button>
            </div>
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '20px', alignItems: 'center', width: '100%' }}>
            {/* Image Preview Container */}
            <div
              style={{
                position: 'relative',
                borderRadius: 'var(--radius-lg)',
                overflow: 'hidden',
                maxHeight: '450px',
                width: '100%',
                maxWidth: '700px',
                backgroundColor: '#f8fafc',
                border: '1px solid #e2e8f0',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              <img
                src={previewUrl}
                alt="Selected preview"
                style={{ width: '100%', maxHeight: '450px', objectFit: 'contain' }}
              />
              <button
                type="button"
                onClick={handleClear}
                style={{
                  position: 'absolute',
                  top: '16px',
                  right: '16px',
                  backgroundColor: 'rgba(15, 23, 42, 0.8)',
                  color: '#ffffff',
                  border: 'none',
                  borderRadius: '50%',
                  width: '36px',
                  height: '36px',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  cursor: 'pointer',
                  boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
                  transition: 'all 0.2s',
                }}
                onMouseOver={(e) => { e.currentTarget.style.backgroundColor = 'rgba(15, 23, 42, 0.95)'; }}
                onMouseOut={(e) => { e.currentTarget.style.backgroundColor = 'rgba(15, 23, 42, 0.8)'; }}
                title="Remove image"
              >
                <X size={20} />
              </button>
            </div>

            {/* File Info */}
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '14px 20px',
                backgroundColor: '#f8fafc',
                borderRadius: 'var(--radius-md)',
                fontSize: '0.92rem',
                width: '100%',
                maxWidth: '700px',
                border: '1px solid #edf2f7',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px', overflow: 'hidden' }}>
                <FileImage size={22} color="var(--primary-600)" style={{ flexShrink: 0 }} />
                <span style={{ fontWeight: 600, color: 'var(--neutral-800)', textOverflow: 'ellipsis', overflow: 'hidden', whiteSpace: 'nowrap' }}>
                  {selectedFile?.name}
                </span>
              </div>
              <span style={{ color: 'var(--neutral-500)', fontSize: '0.85rem', flexShrink: 0 }}>
                {selectedFile ? (selectedFile.size / (1024 * 1024)).toFixed(2) + ' MB' : ''}
              </span>
            </div>

            {/* Action Buttons Directly Below Image Selection Preview */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', width: '100%', maxWidth: '400px', marginTop: '10px' }}>
              <Button
                variant="primary"
                size="lg"
                onClick={handleUploadAndAnnotate}
                disabled={isUploading}
                isLoading={isUploading}
                leftIcon={<UploadCloud size={22} />}
                style={{ width: '100%', padding: '16px', borderRadius: '30px', fontSize: '1.05rem' }}
              >
                Upload & Proceed to Annotate
              </Button>
              <Button
                variant="outline"
                size="md"
                onClick={handleClear}
                disabled={isUploading}
                style={{ width: '100%', padding: '12px', borderRadius: '30px' }}
              >
                Select Different Image
              </Button>
            </div>
          </div>
        )}

        {errorMessage && (
          <div
            style={{
              padding: '12px 16px',
              backgroundColor: '#fef2f2',
              border: '1px solid #fecaca',
              borderRadius: 'var(--radius-md)',
              display: 'flex',
              alignItems: 'center',
              gap: '10px',
              color: '#dc2626',
              fontSize: '0.9rem',
              maxWidth: '700px',
              margin: '0 auto',
              width: '100%',
            }}
          >
            <AlertCircle size={20} />
            <span>{errorMessage}</span>
          </div>
        )}
      </div>

      {/* Info Card */}
      <div
        style={{
          background: 'linear-gradient(135deg, #f0fdf4 0%, #dcfce7 100%)',
          borderRadius: 'var(--radius-lg)',
          padding: '24px',
          border: '1px solid #bbf7d0',
          display: 'flex',
          gap: '16px',
          alignItems: 'center',
          maxWidth: '1000px',
          width: '100%',
        }}
      >
        <div
          style={{
            width: '48px',
            height: '48px',
            borderRadius: '50%',
            backgroundColor: '#ffffff',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            boxShadow: '0 4px 12px rgba(34, 197, 94, 0.15)',
            color: 'var(--primary-600)',
            flexShrink: 0,
          }}
        >
          <Sparkles size={24} />
        </div>
        <div>
          <h4 style={{ fontSize: '1rem', fontWeight: 700, color: 'var(--primary-800)', margin: 0 }}>
            Earn 15 Points per Annotated Image
          </h4>
          <p style={{ fontSize: '0.85rem', color: 'var(--primary-700)', marginTop: '4px', margin: 0 }}>
            Draw boundaries around objects on the next screen and select their waste categories to contribute to our dataset.
          </p>
        </div>
      </div>

      {/* Live Camera Stream Modal */}
      {isCameraOpen && (
        <div
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            backgroundColor: 'rgba(15, 23, 42, 0.85)',
            backdropFilter: 'blur(8px)',
            zIndex: 9999,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: '20px',
          }}
        >
          <div
            style={{
              position: 'relative',
              width: '100%',
              maxWidth: '640px',
              backgroundColor: '#0f172a',
              borderRadius: '24px',
              overflow: 'hidden',
              boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.5)',
              display: 'flex',
              flexDirection: 'column',
              padding: '24px',
              border: '1px solid #334155',
            }}
          >
            <div style={{ display: 'flex', width: '100%', justifyContent: 'space-between', alignItems: 'center', marginBottom: '18px' }}>
              <h4 style={{ color: '#ffffff', margin: 0, fontSize: '1.15rem', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '10px' }}>
                <Camera size={22} color="#22c55e" /> Live Camera Capture
              </h4>
              <button
                type="button"
                onClick={stopCamera}
                style={{ background: 'none', border: 'none', color: '#94a3b8', cursor: 'pointer', padding: '6px', borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}
                title="Close camera"
              >
                <X size={24} />
              </button>
            </div>

            {cameraError ? (
              <div style={{ padding: '36px 20px', textAlign: 'center', color: '#f87171', backgroundColor: '#1e293b', borderRadius: '16px', margin: '10px 0' }}>
                <AlertCircle size={40} style={{ marginBottom: '12px' }} />
                <p style={{ margin: 0, fontSize: '0.95rem', lineHeight: 1.5 }}>{cameraError}</p>
              </div>
            ) : (
              <div style={{ position: 'relative', width: '100%', borderRadius: '16px', overflow: 'hidden', backgroundColor: '#000000', minHeight: '320px', display: 'flex', alignItems: 'center', justifyContent: 'center', border: '1px solid #1e293b' }}>
                <video
                  ref={videoRef}
                  autoPlay
                  playsInline
                  muted
                  style={{ width: '100%', maxHeight: '420px', objectFit: 'contain' }}
                />
              </div>
            )}

            <div style={{ display: 'flex', gap: '14px', marginTop: '20px', width: '100%', justifyContent: 'center' }}>
              {!cameraError && (
                <button
                  type="button"
                  onClick={capturePhoto}
                  style={{
                    padding: '14px 32px',
                    borderRadius: '30px',
                    border: 'none',
                    backgroundColor: '#22c55e',
                    color: '#ffffff',
                    fontWeight: 700,
                    fontSize: '1rem',
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '10px',
                    boxShadow: '0 8px 20px rgba(34, 197, 94, 0.35)',
                    transition: 'all 0.2s',
                  }}
                  onMouseOver={(e) => { e.currentTarget.style.backgroundColor = '#16a34a'; }}
                  onMouseOut={(e) => { e.currentTarget.style.backgroundColor = '#22c55e'; }}
                >
                  <Camera size={22} /> Take Photo
                </button>
              )}
              <button
                type="button"
                onClick={stopCamera}
                style={{
                  padding: '14px 24px',
                  borderRadius: '30px',
                  border: '1px solid #475569',
                  backgroundColor: 'transparent',
                  color: '#cbd5e1',
                  fontWeight: 600,
                  fontSize: '0.95rem',
                  cursor: 'pointer',
                }}
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

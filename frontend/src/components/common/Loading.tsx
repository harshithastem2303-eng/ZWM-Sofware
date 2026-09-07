import React from 'react';

export const Loading: React.FC<{ message?: string; size?: 'sm' | 'md' | 'lg' }> = ({
  message = 'Loading...',
  size = 'md',
}) => {
  const dim = size === 'sm' ? 24 : size === 'lg' ? 48 : 36;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '32px', gap: '12px' }}>
      <div
        style={{
          width: `${dim}px`,
          height: `${dim}px`,
          borderRadius: '50%',
          border: '3px solid var(--primary-100)',
          borderTopColor: 'var(--primary-600)',
          animation: 'spin 0.8s linear infinite',
        }}
      />
      {message && <p style={{ fontSize: '0.9rem', color: 'var(--neutral-500)', fontWeight: 500 }}>{message}</p>}
      <style>{`
        @keyframes spin {
          to { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  );
};

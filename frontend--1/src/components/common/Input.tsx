import React from 'react';

interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
  helperText?: string;
  leftIcon?: React.ReactNode;
  rightIcon?: React.ReactNode;
}

export const Input: React.FC<InputProps> = ({
  label,
  error,
  helperText,
  leftIcon,
  rightIcon,
  className = '',
  id,
  ...props
}) => {
  const inputId = id || (label ? label.toLowerCase().replace(/\s+/g, '-') : undefined);

  return (
    <div className="form-group">
      {label && (
        <label htmlFor={inputId} className="form-label">
          {label}
        </label>
      )}
      <div style={{ position: 'relative', display: 'flex', alignItems: 'center' }}>
        {leftIcon && (
          <span style={{ position: 'absolute', left: '12px', color: 'var(--neutral-400)', display: 'flex', alignItems: 'center', pointerEvents: 'none' }}>
            {leftIcon}
          </span>
        )}
        <input
          id={inputId}
          className={`form-input ${className}`}
          style={{
            paddingLeft: leftIcon ? '40px' : '16px',
            paddingRight: rightIcon ? '40px' : '16px',
            borderColor: error ? '#ef4444' : undefined,
          }}
          {...props}
        />
        {rightIcon && (
          <span style={{ position: 'absolute', right: '12px', color: 'var(--neutral-400)', display: 'flex', alignItems: 'center' }}>
            {rightIcon}
          </span>
        )}
      </div>
      {error ? (
        <span style={{ fontSize: '0.78rem', color: '#ef4444', marginTop: '4px' }}>{error}</span>
      ) : helperText ? (
        <span style={{ fontSize: '0.78rem', color: 'var(--neutral-400)', marginTop: '4px' }}>{helperText}</span>
      ) : null}
    </div>
  );
};

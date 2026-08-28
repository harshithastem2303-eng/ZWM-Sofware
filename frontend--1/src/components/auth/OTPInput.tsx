import React, { useRef, useState } from 'react';

interface OTPInputProps {
  length?: number;
  onComplete: (otp: string) => void;
}

export const OTPInput: React.FC<OTPInputProps> = ({ length = 6, onComplete }) => {
  const [digits, setDigits] = useState<string[]>(Array(length).fill(''));
  const inputsRef = useRef<(HTMLInputElement | null)[]>([]);

  const handleChange = (index: number, value: string) => {
    if (!/^\d*$/.test(value)) return;

    const newDigits = [...digits];
    newDigits[index] = value.slice(-1);
    setDigits(newDigits);

    if (value && index < length - 1) {
      inputsRef.current[index + 1]?.focus();
    }

    const fullOtp = newDigits.join('');
    if (fullOtp.length === length && !newDigits.includes('')) {
      onComplete(fullOtp);
    }
  };

  const handleKeyDown = (index: number, e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Backspace' && !digits[index] && index > 0) {
      inputsRef.current[index - 1]?.focus();
    }
  };

  return (
    <div style={{ display: 'flex', gap: '8px', justifyContent: 'center', margin: '20px 0' }}>
      {digits.map((digit, i) => (
        <input
          key={i}
          ref={(el) => (inputsRef.current[i] = el)}
          type="text"
          maxLength={1}
          value={digit}
          onChange={(e) => handleChange(i, e.target.value)}
          onKeyDown={(e) => handleKeyDown(i, e)}
          style={{
            width: '46px',
            height: '52px',
            textAlign: 'center',
            fontSize: '1.25rem',
            fontWeight: 700,
            borderRadius: '12px',
            border: '1.5px solid var(--neutral-200)',
            outline: 'none',
            color: 'var(--primary-700)',
            backgroundColor: '#ffffff',
            transition: 'all 0.2s',
          }}
          onFocus={(e) => {
            e.target.style.borderColor = 'var(--primary-500)';
            e.target.style.boxShadow = '0 0 0 3px rgba(34, 197, 94, 0.15)';
          }}
          onBlur={(e) => {
            e.target.style.borderColor = 'var(--neutral-200)';
            e.target.style.boxShadow = 'none';
          }}
        />
      ))}
    </div>
  );
};

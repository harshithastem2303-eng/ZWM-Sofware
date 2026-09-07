import React, { useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { CheckCircle2, ArrowRight } from 'lucide-react';
import { AuthLayout } from '../../components/auth/AuthLayout';
import { OTPInput } from '../../components/auth/OTPInput';
import { Button } from '../../components/common/Button';

export const VerifyEmailPage: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const email = (location.state as any)?.email || 'your email';
  const [isVerifying, setIsVerifying] = useState(false);

  const handleVerify = async (code: string) => {
    setIsVerifying(true);
    setTimeout(() => {
      setIsVerifying(false);
      navigate('/dashboard');
    }, 1000);
  };

  return (
    <AuthLayout
      title="Verify Your Email"
      subtitle={`We've sent a 6-digit verification code to ${email}`}
    >
      <div style={{ textAlign: 'center' }}>
        <OTPInput onComplete={handleVerify} />

        <Button
          variant="primary"
          size="lg"
          isLoading={isVerifying}
          onClick={() => handleVerify('123456')}
          rightIcon={<ArrowRight size={18} />}
          style={{ width: '100%', marginTop: '16px' }}
        >
          Verify & Continue
        </Button>

        <p style={{ fontSize: '0.85rem', color: 'var(--neutral-400)', marginTop: '20px' }}>
          Didn't receive code?{' '}
          <button
            onClick={() => alert('Verification code resent!')}
            style={{ background: 'none', border: 'none', color: 'var(--primary-600)', fontWeight: 600, cursor: 'pointer' }}
          >
            Resend
          </button>
        </p>
      </div>
    </AuthLayout>
  );
};

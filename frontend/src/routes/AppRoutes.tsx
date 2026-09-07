import React from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import { DashboardLayout } from '../components/dashboard/DashboardLayout';
import { DashboardPage } from '../pages/Dashboard/DashboardPage';
import { UploadPage } from '../pages/Dashboard/UploadPage';
import { ProfilePage } from '../pages/Dashboard/ProfilePage';
import { LandingPage } from '../pages/Landing/LandingPage';
import { AboutPage } from '../pages/About/AboutPage';
import { ContactPage } from '../pages/Contact/ContactPage';
import { HowItWorksPage } from '../pages/HowItWorks/HowItWorksPage';
import { LoginPage } from '../pages/Auth/LoginPage';
import { RegisterPage } from '../pages/Auth/RegisterPage';
import { VerifyEmailPage } from '../pages/Auth/VerifyEmailPage';

export const AppRoutes: React.FC = () => {
  return (
    <Routes>
      {/* Landing & Authentication */}
      <Route path="/landing" element={<LandingPage />} />
      <Route path="/about" element={<AboutPage />} />
      <Route path="/contact" element={<ContactPage />} />
      <Route path="/how-it-works" element={<HowItWorksPage />} />
      <Route path="/how" element={<Navigate to="/how-it-works" replace />} />
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route path="/verify-email" element={<VerifyEmailPage />} />

      {/* Main Dashboard Pages wrapped in DashboardLayout */}
      <Route path="/" element={<LandingPage />} />
      <Route
        path="/dashboard"
        element={
          <DashboardLayout>
            <DashboardPage />
          </DashboardLayout>
        }
      />
      <Route
        path="/dashboard/upload"
        element={
          <DashboardLayout>
            <UploadPage />
          </DashboardLayout>
        }
      />
      <Route
        path="/dashboard/profile"
        element={
          <DashboardLayout>
            <ProfilePage />
          </DashboardLayout>
        }
      />

      {/* Shortcut Aliases */}
      <Route path="/upload" element={<Navigate to="/dashboard/upload" replace />} />
      <Route path="/profile" element={<Navigate to="/dashboard/profile" replace />} />

      {/* Fallback */}
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  );
};

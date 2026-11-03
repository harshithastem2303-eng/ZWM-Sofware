import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';

// Admin Components & Pages
import AdminLogin from './pages/AdminLogin';
import AdminDashboard from './pages/AdminDashboard';
import ProtectedRoute from './components/ProtectedRoute';

// User Context, Layout & Pages
import { AuthProvider } from './context/AuthContext';
import { DashboardLayout } from './components/dashboard/DashboardLayout';
import { DashboardPage } from './pages/Dashboard/DashboardPage';
import { UploadPage } from './pages/Dashboard/UploadPage';
import { AnnotationPage } from './pages/Dashboard/AnnotationPage';
import { ProfilePage } from './pages/Dashboard/ProfilePage';
import { LandingPage } from './pages/Landing/LandingPage';
import { AboutPage } from './pages/About/AboutPage';
import { ContactPage } from './pages/Contact/ContactPage';
import { HowItWorksPage } from './pages/HowItWorks/HowItWorksPage';
import { LoginPage } from './pages/Auth/LoginPage';
import { RegisterPage } from './pages/Auth/RegisterPage';
import { VerifyEmailPage } from './pages/Auth/VerifyEmailPage';
import { TermsOfServicePage } from './pages/Legal/TermsOfServicePage';
import { PrivacyPolicyPage } from './pages/Legal/PrivacyPolicyPage';
import { UserProtectedRoute } from './components/UserProtectedRoute';
import { useLocation } from 'react-router-dom';

const ScrollToTop: React.FC = () => {
  const { pathname } = useLocation();
  React.useEffect(() => {
    window.scrollTo(0, 0);
  }, [pathname]);
  return null;
};

export const App: React.FC = () => {
  return (
    <BrowserRouter>
      <ScrollToTop />
      <AuthProvider>
        <Routes>
          {/* Admin Routes */}
          <Route path="/admin/login" element={<AdminLogin />} />
          <Route
            path="/admin/dashboard"
            element={
              <ProtectedRoute>
                <AdminDashboard />
              </ProtectedRoute>
            }
          />

          {/* User Landing & Information Pages */}
          <Route path="/" element={<LandingPage />} />
          <Route path="/landing" element={<LandingPage />} />
          <Route path="/about" element={<AboutPage />} />
          <Route path="/contact" element={<ContactPage />} />
          <Route path="/how-it-works" element={<HowItWorksPage />} />
          <Route path="/how" element={<Navigate to="/how-it-works" replace />} />
          <Route path="/terms" element={<TermsOfServicePage />} />
          <Route path="/privacy" element={<PrivacyPolicyPage />} />

          {/* User Auth Pages */}
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
          <Route path="/verify-email" element={<VerifyEmailPage />} />

          {/* User Dashboard Pages wrapped in DashboardLayout & UserProtectedRoute */}
          <Route
            path="/dashboard"
            element={
              <UserProtectedRoute>
                <DashboardLayout>
                  <DashboardPage />
                </DashboardLayout>
              </UserProtectedRoute>
            }
          />
          <Route
            path="/dashboard/upload"
            element={
              <UserProtectedRoute>
                <DashboardLayout>
                  <UploadPage />
                </DashboardLayout>
              </UserProtectedRoute>
            }
          />
          <Route
            path="/dashboard/annotate"
            element={
              <UserProtectedRoute>
                <DashboardLayout>
                  <AnnotationPage />
                </DashboardLayout>
              </UserProtectedRoute>
            }
          />
          <Route
            path="/dashboard/profile"
            element={
              <UserProtectedRoute>
                <DashboardLayout>
                  <ProfilePage />
                </DashboardLayout>
              </UserProtectedRoute>
            }
          />

          {/* User Shortcut Aliases */}
          <Route path="/upload" element={<Navigate to="/dashboard/upload" replace />} />
          <Route path="/profile" element={<Navigate to="/dashboard/profile" replace />} />

          {/* Fallbacks */}
          <Route path="/admin/*" element={<Navigate to="/admin/login" replace />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
};

export default App;

import React from 'react';
import { Sidebar } from './Sidebar';

export const DashboardLayout: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  return (
    <div className="app-container">
      <Sidebar />
      <main className="main-wrapper">
        <div className="dashboard-content">{children}</div>
      </main>
    </div>
  );
};

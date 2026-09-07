import React from 'react';
import { CardLeafWatermark } from '../../assets/icons/LeafAccents';

interface StatCardProps {
  icon: React.ReactNode;
  title: string;
  value: number | string;
  subtext: string;
  infoDetail?: string;
  isSyncing?: boolean;
}

export const StatCard: React.FC<StatCardProps> = ({
  icon,
  title,
  value,
  subtext,
  infoDetail,
  isSyncing = false,
}) => {
  return (
    <div className="stat-card" title={infoDetail}>
      <CardLeafWatermark className="stat-card-leaf" size={85} />
      <div className="stat-icon-box">{icon}</div>
      <div className="stat-info">
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span className="stat-title">{title}</span>
          {isSyncing && (
            <span
              style={{
                width: '6px',
                height: '6px',
                borderRadius: '50%',
                backgroundColor: 'var(--primary-500)',
                animation: 'pulse 1s infinite',
              }}
            />
          )}
        </div>
        <span className="stat-number">{value}</span>
        <span className="stat-subtext">{subtext}</span>
      </div>
    </div>
  );
};

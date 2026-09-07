import React from 'react';

export const ZwmLogo: React.FC<{ size?: number; className?: string }> = ({ size = 44, className }) => {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 100 100"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
    >
      {/* Outer Green Ring: #317827 */}
      <circle cx="50" cy="50" r="45" stroke="#317827" strokeWidth="4.5" fill="#ffffff" />

      {/* Primary Left Upright Leaf: #317827 */}
      <path
        d="M48 78 C24 64 18 38 40 22 C56 42 56 64 48 78 Z"
        fill="#317827"
      />
      {/* Central vein of Left leaf */}
      <path
        d="M38 25 C45 42 46 62 47 74"
        stroke="#ffffff"
        strokeWidth="2.2"
        strokeLinecap="round"
      />

      {/* Secondary Right Sprout Leaf: #ADD192 */}
      <path
        d="M46 54 C50 36 68 28 78 30 C78 46 64 62 46 54 Z"
        fill="#add192"
      />
      <path
        d="M52 50 C60 44 68 38 74 34"
        stroke="#ffffff"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
    </svg>
  );
};

import React from 'react';

/**
 * Top-left decorative corner foliage for Workflow card matching reference
 */
export const CornerFoliageTopLeft: React.FC<{ className?: string }> = ({ className }) => (
  <svg
    viewBox="0 0 160 140"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
    className={className}
    style={{ width: '130px', height: 'auto', display: 'block' }}
  >
    {/* Background soft leaves: #ADD192 */}
    <path
      d="M0 0 C40 15 65 50 55 95 C30 80 12 50 0 0 Z"
      fill="#add192"
      fillOpacity="0.85"
    />
    <path d="M0 0 C30 35 40 60 50 85" stroke="#317827" strokeWidth="1.2" strokeOpacity="0.6" />

    {/* Primary leaf 1: #ECF2E3 */}
    <path
      d="M0 30 C45 35 85 20 105 0 C70 12 35 18 0 30 Z"
      fill="#ecf2e3"
      fillOpacity="0.95"
    />
    <path d="M10 28 C45 22 75 12 98 2" stroke="#249b25" strokeWidth="1.2" strokeOpacity="0.7" />

    {/* Primary leaf 2: #317827 */}
    <path
      d="M20 0 C32 32 20 70 0 85 C8 60 15 25 20 0 Z"
      fill="#317827"
      fillOpacity="0.85"
    />
    <path d="M18 5 C16 35 12 60 2 78" stroke="#ffffff" strokeWidth="1.2" strokeOpacity="0.5" />

    {/* Foreground small tender leaf: #ADD192 */}
    <path
      d="M28 15 C48 30 52 52 42 62 C34 50 32 32 28 15 Z"
      fill="#add192"
      fillOpacity="0.9"
    />

    {/* Floating accent dots / flakes */}
    <circle cx="85" cy="65" r="4.5" fill="#add192" fillOpacity="0.7" />
    <circle cx="115" cy="40" r="3" fill="#249b25" fillOpacity="0.6" />
    <circle cx="55" cy="98" r="3.5" fill="#317827" fillOpacity="0.5" />
  </svg>
);

/**
 * Bottom-right decorative corner foliage for Workflow card matching reference
 */
export const CornerFoliageBottomRight: React.FC<{ className?: string }> = ({ className }) => (
  <svg
    viewBox="0 0 180 160"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
    className={className}
    style={{ width: '145px', height: 'auto', display: 'block' }}
  >
    {/* Large tall foliage branch: #317827 */}
    <path
      d="M180 160 C140 145 105 110 115 65 C145 80 168 115 180 160 Z"
      fill="#317827"
      fillOpacity="0.85"
    />
    <path d="M175 155 C150 120 135 95 120 72" stroke="#ffffff" strokeWidth="1.3" strokeOpacity="0.5" />

    {/* Middle leaf: #ADD192 */}
    <path
      d="M180 125 C130 118 85 140 65 160 C105 145 145 140 180 125 Z"
      fill="#add192"
      fillOpacity="0.9"
    />
    <path d="M170 128 C135 132 100 144 75 156" stroke="#317827" strokeWidth="1.2" strokeOpacity="0.7" />

    {/* Upper middle leaf: #249B25 */}
    <path
      d="M160 160 C148 128 160 90 180 75 C172 100 165 135 160 160 Z"
      fill="#249b25"
      fillOpacity="0.85"
    />

    {/* Upper pointing leaf branch: #ECF2E3 */}
    <path
      d="M145 140 C125 118 120 95 132 82 C142 98 142 120 145 140 Z"
      fill="#ecf2e3"
      fillOpacity="0.9"
    />
    <path d="M143 135 C135 118 130 102 133 88" stroke="#317827" strokeWidth="1.1" strokeOpacity="0.6" />

    {/* Delicate floating dots */}
    <circle cx="85" cy="95" r="4.5" fill="#add192" fillOpacity="0.7" />
    <circle cx="128" cy="48" r="3.5" fill="#249b25" fillOpacity="0.6" />
    <circle cx="160" cy="35" r="2.5" fill="#add192" fillOpacity="0.8" />
  </svg>
);

/**
 * Subtle leaf wreath around each step circle in WorkflowSteps
 */
export const StepLeafWreath: React.FC<{ className?: string }> = ({ className }) => (
  <svg
    viewBox="0 0 110 110"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
    className={className}
    style={{ width: '100%', height: '100%' }}
  >
    {/* Left wreath side: #ADD192 */}
    <path
      d="M28 72 C14 60 12 42 24 30 C28 44 32 58 28 72 Z"
      fill="#add192"
      fillOpacity="0.6"
    />
    <path
      d="M20 52 C8 45 10 28 24 24 C24 36 22 45 20 52 Z"
      fill="#249b25"
      fillOpacity="0.5"
    />
    <path
      d="M34 82 C20 80 16 68 24 58 C30 68 32 75 34 82 Z"
      fill="#317827"
      fillOpacity="0.4"
    />

    {/* Right wreath side: #ADD192 */}
    <path
      d="M82 72 C96 60 98 42 86 30 C82 44 78 58 82 72 Z"
      fill="#add192"
      fillOpacity="0.6"
    />
    <path
      d="M90 52 C102 45 100 28 86 24 C86 36 88 45 90 52 Z"
      fill="#249b25"
      fillOpacity="0.5"
    />
    <path
      d="M76 82 C90 80 94 68 86 58 C80 68 78 75 76 82 Z"
      fill="#317827"
      fillOpacity="0.4"
    />
  </svg>
);

/**
 * Subtle line-art leaf watermark for cards: #ADD192
 */
export const CardLeafWatermark: React.FC<{ className?: string; size?: number }> = ({ className, size = 110 }) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 120 120"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
    className={className}
  >
    {/* Main central leaf */}
    <path
      d="M100 100 C68 95 45 65 58 24 C82 48 90 78 100 100 Z"
      stroke="#add192"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      fill="#f5f8ef"
      fillOpacity="0.6"
    />
    {/* Central vein */}
    <path
      d="M58 24 C72 52 82 76 100 100"
      stroke="#add192"
      strokeWidth="1.4"
      strokeLinecap="round"
    />
    {/* Left branch veins */}
    <path
      d="M72 56 C82 52 92 50 98 52"
      stroke="#add192"
      strokeWidth="1.1"
      strokeLinecap="round"
    />
    <path
      d="M82 72 C90 68 96 68 100 70"
      stroke="#add192"
      strokeWidth="1.1"
      strokeLinecap="round"
    />
    {/* Side sprout leaf */}
    <path
      d="M48 55 C30 45 32 30 44 26 C48 38 48 48 48 55 Z"
      stroke="#add192"
      strokeWidth="1.3"
      fill="#f5f8ef"
      fillOpacity="0.5"
    />
  </svg>
);

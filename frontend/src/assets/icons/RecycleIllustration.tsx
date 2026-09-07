import React from 'react';

export const RecycleIllustration: React.FC<{ className?: string }> = ({ className }) => {
  return (
    <svg
      viewBox="0 0 220 240"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
      style={{ width: '100%', maxWidth: '210px', height: 'auto', display: 'block' }}
    >
      <defs>
        {/* Gradients using exact palette: #317827, #249B25, #ADD192, #ECF2E3 */}
        <linearGradient id="leafGradDark" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#249b25" />
          <stop offset="100%" stopColor="#317827" />
        </linearGradient>

        <linearGradient id="leafGradMedium" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#add192" />
          <stop offset="100%" stopColor="#249b25" />
        </linearGradient>

        <linearGradient id="leafGradLight" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#ecf2e3" />
          <stop offset="100%" stopColor="#add192" />
        </linearGradient>

        <linearGradient id="binBodyGrad" x1="0%" y1="0%" x2="100%" y2="0%">
          <stop offset="0%" stopColor="#1e821f" />
          <stop offset="40%" stopColor="#249b25" />
          <stop offset="85%" stopColor="#317827" />
          <stop offset="100%" stopColor="#1e821f" />
        </linearGradient>

        <linearGradient id="binLidGrad" x1="0%" y1="0%" x2="100%" y2="0%">
          <stop offset="0%" stopColor="#1e821f" />
          <stop offset="45%" stopColor="#2e9e2f" />
          <stop offset="90%" stopColor="#317827" />
          <stop offset="100%" stopColor="#1e821f" />
        </linearGradient>

        <filter id="softShadow" x="-10%" y="-10%" width="130%" height="130%">
          <feDropShadow dx="0" dy="2" stdDeviation="2" floodColor="#151515" floodOpacity="0.06" />
        </filter>
      </defs>

      {/* Ground soft shadow using Pale Green: #ECF2E3 */}
      <ellipse cx="108" cy="226" rx="96" ry="11" fill="#ecf2e3" />
      <ellipse cx="106" cy="225" rx="72" ry="7" fill="#e2ebd6" />

      {/* ================= LEFT BOTANICAL LEAF CLUSTER ================= */}
      <g id="left-plant-stalks">
        {/* Tall Back Plant Leaf Stem */}
        <path
          d="M62 225 Q52 145 74 65"
          stroke="#317827"
          strokeWidth="2.5"
          strokeLinecap="round"
        />

        {/* Top-most slender leaf on stem */}
        <path
          d="M74 65 C68 45 76 30 84 25 C88 38 84 55 74 65 Z"
          fill="url(#leafGradLight)"
        />
        <path d="M75 60 C78 48 81 38 83 27" stroke="#ffffff" strokeWidth="1" strokeLinecap="round" strokeOpacity="0.7" />

        {/* High Left Leaf */}
        <path
          d="M68 95 C45 78 42 55 60 48 C72 65 72 82 68 95 Z"
          fill="url(#leafGradMedium)"
        />
        <path d="M68 90 C60 76 56 64 58 52" stroke="#ffffff" strokeWidth="1.2" strokeLinecap="round" strokeOpacity="0.6" />

        {/* High Right Leaf */}
        <path
          d="M72 85 C92 70 98 52 86 42 C78 58 76 72 72 85 Z"
          fill="url(#leafGradDark)"
        />
        <path d="M73 80 C80 68 85 58 84 46" stroke="#ffffff" strokeWidth="1.2" strokeLinecap="round" strokeOpacity="0.5" />

        {/* Mid-height Left Large Leaf */}
        <path
          d="M60 135 C30 115 24 85 45 75 C60 98 62 118 60 135 Z"
          fill="url(#leafGradMedium)"
        />
        <path d="M58 130 C46 112 40 98 43 80" stroke="#ffffff" strokeWidth="1.3" strokeLinecap="round" strokeOpacity="0.6" />

        {/* Mid-height Right Leaf */}
        <path
          d="M64 125 C88 110 96 90 82 78 C74 96 70 112 64 125 Z"
          fill="url(#leafGradLight)"
        />

        {/* Lower Left Bushy Tropical Leaf (Broad) */}
        <path
          d="M48 185 C18 160 10 128 32 115 C50 140 52 165 48 185 Z"
          fill="url(#leafGradDark)"
        />
        <path d="M46 178 C32 155 24 138 30 120" stroke="#ffffff" strokeWidth="1.3" strokeLinecap="round" strokeOpacity="0.5" />

        {/* Lower Arching Leaf */}
        <path
          d="M40 215 C12 195 8 165 28 152 C44 175 44 198 40 215 Z"
          fill="url(#leafGradMedium)"
        />

        {/* Base curving front leaf */}
        <path
          d="M52 224 C28 215 22 192 38 182 C50 200 54 214 52 224 Z"
          fill="url(#leafGradLight)"
        />
      </g>

      {/* ================= RIGHT FOLIAGE & FLOATING LEAVES ================= */}
      <g id="right-foliage">
        {/* Behind Bin Right Foliage */}
        <path
          d="M138 215 C162 195 174 165 160 145 C146 168 140 192 138 215 Z"
          fill="url(#leafGradMedium)"
        />
        <path
          d="M142 185 C165 168 175 142 164 125 C150 144 144 165 142 185 Z"
          fill="url(#leafGradLight)"
        />
      </g>

      {/* Floating Delicate Leaves and Dots */}
      <g id="floating-leaf-particles" opacity="0.85">
        <path
          d="M152 75 C162 62 174 65 172 76 C162 82 154 82 152 75 Z"
          fill="#add192"
        />
        <path
          d="M134 115 C140 105 148 106 146 114 C140 118 135 118 134 115 Z"
          fill="#ecf2e3"
        />
        <path
          d="M112 45 C116 38 122 39 121 44 C117 47 113 47 112 45 Z"
          fill="#add192"
        />
        <circle cx="166" cy="98" r="3.5" fill="#add192" />
        <circle cx="138" cy="72" r="2.5" fill="#317827" />
        <circle cx="158" cy="132" r="3" fill="#ecf2e3" />
      </g>

      {/* ================= RECYCLING DUSTBIN ================= */}
      <g id="dustbin" filter="url(#softShadow)">
        {/* Main tapered body */}
        <path
          d="M74 154 L80 216 C80.5 219 83 221 86 221 L132 221 C135 221 137.5 219 138 216 L144 154 Z"
          fill="url(#binBodyGrad)"
        />

        {/* Bin Side Edge Highlights */}
        <path
          d="M136 154 L131 216 C131.5 218 133 219 134.5 219 L137.5 216 L143.5 154 Z"
          fill="#add192"
          fillOpacity="0.4"
        />
        <path
          d="M74.5 154 L80.5 216 C80 218 78.5 219 77 219 L80 216 L74.5 154 Z"
          fill="#0f4610"
          fillOpacity="0.3"
        />

        {/* Bin Lid Overhang Rim / Lip */}
        <rect x="68" y="146" width="82" height="10" rx="5" fill="url(#binLidGrad)" />
        <rect x="70" y="145" width="78" height="3" rx="1.5" fill="#add192" fillOpacity="0.7" />

        {/* Bin Lid Dome Top */}
        <path
          d="M76 146 C76 140 82 136 109 136 C136 136 142 140 142 146 Z"
          fill="url(#binLidGrad)"
        />
        <path
          d="M80 144 C84 139 96 137 109 137 C122 137 134 139 138 144"
          stroke="#add192"
          strokeWidth="1.5"
          fill="none"
          strokeLinecap="round"
          strokeOpacity="0.6"
        />

        {/* Bin Lid Handle on top */}
        <path
          d="M98 136 C98 130 102 128 109 128 C116 128 120 130 120 136"
          stroke="#1e821f"
          strokeWidth="4.5"
          strokeLinecap="round"
          fill="none"
        />
        <path
          d="M99 135 C99 130 103 129 109 129 C115 129 119 130 119 135"
          stroke="#2e9e2f"
          strokeWidth="3"
          strokeLinecap="round"
          fill="none"
        />

        {/* Subtle Bin Body Vertical Lines */}
        <line x1="90" y1="160" x2="94" y2="214" stroke="#0f4610" strokeWidth="1.2" strokeOpacity="0.25" />
        <line x1="128" y1="160" x2="124" y2="214" stroke="#add192" strokeWidth="1.2" strokeOpacity="0.3" />

        {/* ================= CRISP UNIVERSAL RECYCLING SYMBOL ================= */}
        <g id="recycling-symbol" transform="translate(109, 185) scale(0.68)">
          <g transform="translate(0, -14)">
            <path d="M-5 -6 L6 -6 L14 7 L7 7 L3 0 L-5 0 Z" fill="#ffffff" />
            <polygon points="12,11 20,4 12,-3" fill="#ffffff" />
          </g>
          <g transform="rotate(120) translate(0, -14)">
            <path d="M-5 -6 L6 -6 L14 7 L7 7 L3 0 L-5 0 Z" fill="#ffffff" />
            <polygon points="12,11 20,4 12,-3" fill="#ffffff" />
          </g>
          <g transform="rotate(240) translate(0, -14)">
            <path d="M-5 -6 L6 -6 L14 7 L7 7 L3 0 L-5 0 Z" fill="#ffffff" />
            <polygon points="12,11 20,4 12,-3" fill="#ffffff" />
          </g>
        </g>
      </g>
    </svg>
  );
};

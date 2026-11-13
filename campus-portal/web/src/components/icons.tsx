import type { SVGProps } from 'react';

type P = SVGProps<SVGSVGElement>;

const base = (p: P) => ({
  width: 17,
  height: 17,
  viewBox: '0 0 24 24',
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 1.6,
  strokeLinecap: 'round' as const,
  strokeLinejoin: 'round' as const,
  ...p,
});

export const IconReview = (p: P) => (
  <svg {...base(p)} aria-hidden="true">
    <path d="M4 4h11l5 5v11H4z" />
    <path d="M9 13l4-4 2 2-4 4H9z" />
    <path d="M15 4v5h5" />
  </svg>
);

export const IconFolder = (p: P) => (
  <svg {...base(p)} aria-hidden="true">
    <path d="M3 7h6l2 2h10v10H3z" />
    <path d="M3 7V5h6" />
  </svg>
);

export const IconRules = (p: P) => (
  <svg {...base(p)} aria-hidden="true">
    <path d="M5 4h14v16H5z" />
    <path d="M8 8h8M8 12h8M8 16h5" />
  </svg>
);

export const IconTemplate = (p: P) => (
  <svg {...base(p)} aria-hidden="true">
    <path d="M4 4h7v7H4zM13 4h7v4h-7zM13 10h7v10h-7zM4 13h7v7H4z" />
  </svg>
);

export const IconSettings = (p: P) => (
  <svg {...base(p)} aria-hidden="true">
    <circle cx="12" cy="12" r="3" />
    <path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M19.1 4.9L17 7M7 17l-2.1 2.1" />
  </svg>
);

export const IconRefresh = (p: P) => (
  <svg {...base({ width: 12, height: 12, strokeWidth: 2, ...p })} aria-hidden="true">
    <path d="M21 12a9 9 0 1 1-2.6-6.4" />
    <path d="M21 4v5h-5" />
  </svg>
);

export const IconFile = (p: P) => (
  <svg {...base({ width: 12, height: 12, strokeWidth: 1.8, ...p })} aria-hidden="true">
    <path d="M6 3h9l5 5v13H6z" />
    <path d="M15 3v5h5" />
  </svg>
);

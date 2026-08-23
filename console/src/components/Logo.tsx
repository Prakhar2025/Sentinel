export function LogoMark({ size = 28 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" aria-hidden="true">
      <g fill="none" stroke="#e8a33d" strokeLinecap="round">
        <path d="M 12 32 A 20 20 0 0 1 32 12" strokeWidth="4" />
        <path d="M 39 15.5 A 20 20 0 0 1 52 32" strokeWidth="4" opacity="0.55" />
        <path d="M 46 39 A 20 20 0 0 1 20 46" strokeWidth="4" opacity="0.3" />
      </g>
      <circle cx="32" cy="32" r="7.5" fill="none" stroke="#e8e3d5" strokeWidth="2.5" />
      <circle cx="32" cy="32" r="2.6" fill="#e8a33d" />
    </svg>
  );
}

export function Wordmark() {
  return (
    <span className="flex items-baseline gap-2">
      <span className="font-display text-[22px] leading-none tracking-tight">Sentinel</span>
      <span className="micro hidden sm:inline">abuse-ring watchroom</span>
    </span>
  );
}

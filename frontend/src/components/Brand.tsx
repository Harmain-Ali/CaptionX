export function Logo({ size = 34 }: { size?: number }) {
  return (
    <svg className="logo" width={size} height={size} viewBox="0 0 40 40" aria-hidden="true">
      <rect width="40" height="40" rx="12" fill="#FF4C00" />
      <path d="M13 13l14 14M27 13L13 27" stroke="#0A0A0A" strokeWidth="4.2" strokeLinecap="round" />
    </svg>
  );
}

export function Wordmark() {
  return <span className="wordmark">caption<b>X</b></span>;
}

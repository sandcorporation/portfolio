/** The Sandcorp mark: two dunes in a rounded square. Colors come from the brand tokens. */
export function LogoMark({ size = 28 }: { size?: number }) {
  return (
    <svg
      className="logo-mark"
      width={size}
      height={size}
      viewBox="0 0 32 32"
      aria-hidden="true"
      focusable="false"
    >
      <rect className="logo-mark-bg" width="32" height="32" rx="7" />
      <path className="logo-mark-far" d="M0 21c5-8 10-9 15-5s10 3 17-4v20H0z" />
      <path className="logo-mark-near" d="M0 26c6-6 11-6 16-2s10 2 16-3v11H0z" />
    </svg>
  );
}

/** Wordmark: mark + "Sandcorp" set in the page font (so it follows the theme). */
export function Wordmark() {
  return (
    <a className="wordmark" href="/" aria-label="Sandcorp 홈">
      <LogoMark />
      <span className="wordmark-text">Sandcorp</span>
    </a>
  );
}

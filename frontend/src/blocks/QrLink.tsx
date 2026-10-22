import { encode } from "uqr";

/** A QR code (inline SVG, drawn as one path) for a URL. */
export function QrCode({ text, label }: { text: string; label: string }) {
  const { data, size } = encode(text, { ecc: "M", border: 0 });
  const cells: string[] = [];
  data.forEach((row, y) =>
    row.forEach((dark, x) => {
      if (dark) cells.push(`M${x} ${y}h1v1h-1z`);
    }),
  );
  return (
    <svg
      className="qr-code"
      role="img"
      aria-label={label}
      viewBox={`-2 -2 ${size + 4} ${size + 4}`}
      shapeRendering="crispEdges"
    >
      <rect x="-2" y="-2" width={size + 4} height={size + 4} className="qr-bg" />
      <path d={cells.join("")} className="qr-fg" />
    </svg>
  );
}

/** What a player becomes on paper: a QR code and the address it opens, on the customer page. */
export function QrLink({ href, kind }: { href: string; kind: string }) {
  return (
    <div className="qr-link">
      <QrCode text={href} label={`${kind} 보기 QR 코드`} />
      <p>
        <span>{kind}은 온라인 제안서에서 재생합니다.</span>
        <a href={href}>{href}</a>
      </p>
    </div>
  );
}

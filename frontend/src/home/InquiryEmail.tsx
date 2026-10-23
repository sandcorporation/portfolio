import { useEffect, useRef, useState } from "react";

export const COPIED_MS = 1600;

/** Selects the link's text so the visitor can copy it by hand (when the clipboard is refused). */
function selectText(node: HTMLElement) {
  const selection = window.getSelection();
  if (!selection) return;
  const range = document.createRange();
  range.selectNodeContents(node);
  selection.removeAllRanges();
  selection.addRange(range);
}

/**
 * 「이메일」 label, the address as a mailto link and a 「주소 복사」 button. The button says
 * 「복사됨」 for 1.6 s; if the clipboard refuses, the address text is selected instead.
 * An empty address renders nothing (no button either).
 */
export function InquiryEmail({ email }: { email: string }) {
  const link = useRef<HTMLAnchorElement>(null);
  const timer = useRef<number | undefined>(undefined);
  const [copied, setCopied] = useState(false);

  useEffect(() => () => window.clearTimeout(timer.current), []);

  if (!email) return null;

  async function copy() {
    try {
      await navigator.clipboard.writeText(email);
    } catch {
      // no clipboard (insecure page, denied): leave the address selected for ctrl+C
      if (link.current) selectText(link.current);
      return;
    }
    setCopied(true);
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setCopied(false), COPIED_MS);
  }

  return (
    <div className="inquiry-email">
      <p className="inquiry-email-label">이메일</p>
      <div className="inquiry-email-row">
        <a ref={link} href={`mailto:${email}`}>
          {email}
        </a>
        <button type="button" className="copy-button" onClick={() => void copy()}>
          {copied ? "복사됨" : "주소 복사"}
        </button>
        <span className="visually-hidden" role="status">
          {copied ? "이메일 주소를 복사했습니다" : ""}
        </span>
      </div>
    </div>
  );
}

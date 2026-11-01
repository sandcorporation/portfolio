import { useState, type FormEvent } from "react";
import type { OfferingCard } from "../services/types";

type Status = "idle" | "sending" | "done" | "error";

const ERRORS: Record<number, string> = {
  429: "문의가 너무 많습니다. 잠시 후 다시 시도해 주세요.",
  422: "입력을 확인해 주세요. 이름, 연락처, 내용은 꼭 필요합니다.",
};

const PLAIN_KINDS = ["신규 개발", "유지보수"];

/** The 구분 to preselect: `?inquiry=<offering slug>` (the service pages' 「견적 문의」 link) picks that
 * offering, whose `inquiry_kind` is its Inquiry.Kind value; anything else keeps the default. */
function initialKind(offerings: OfferingCard[]): string {
  const slug = new URLSearchParams(window.location.search).get("inquiry");
  return offerings.find((o) => o.slug === slug)?.inquiry_kind ?? "신규 개발";
}

export function InquiryForm({ offerings = [] }: { offerings?: OfferingCard[] }) {
  const [status, setStatus] = useState<Status>("idle");
  const [error, setError] = useState("");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const values = Object.fromEntries(new FormData(form).entries());
    setStatus("sending");
    try {
      const response = await fetch("/api/inquiries", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(values),
      });
      if (response.ok) {
        form.reset();
        setStatus("done");
        return;
      }
      setError(ERRORS[response.status] ?? "접수하지 못했습니다. 잠시 후 다시 시도해 주세요.");
    } catch {
      setError("접수하지 못했습니다. 네트워크를 확인해 주세요.");
    }
    setStatus("error");
  }

  if (status === "done") {
    return (
      <p className="inquiry-done" role="status">
        접수되었습니다. 확인 후 남겨 주신 연락처로 답변드리겠습니다.
      </p>
    );
  }

  return (
    <form className="inquiry-form" onSubmit={(e) => void submit(e)}>
      <label>
        구분
        <select name="kind" defaultValue={initialKind(offerings)}>
          {[...PLAIN_KINDS, ...offerings.map((o) => o.inquiry_kind), "제안", "기타"].map((kind) => (
            <option key={kind} value={kind}>
              {kind}
            </option>
          ))}
        </select>
      </label>
      <label>
        이름
        <input name="name" required maxLength={80} autoComplete="name" />
      </label>
      <label>
        <span>
          회사 <span className="optional">(선택)</span>
        </span>
        <input name="company" maxLength={120} autoComplete="organization" />
      </label>
      <label>
        연락처
        <input
          name="contact"
          required
          maxLength={200}
          placeholder="이메일 또는 전화번호"
          autoComplete="email"
        />
      </label>
      <label className="wide">
        내용
        <textarea name="message" required maxLength={4000} rows={5} />
      </label>
      {/* Honeypot: invisible to people and assistive tech; bots that fill every field give themselves away. */}
      <div className="inquiry-trap" aria-hidden="true">
        <label>
          웹사이트
          <input name="website" tabIndex={-1} autoComplete="off" />
        </label>
      </div>
      {status === "error" && (
        <p className="inquiry-error wide" role="alert">
          {error}
        </p>
      )}
      <button type="submit" className="wide" disabled={status === "sending"}>
        {status === "sending" ? "보내는 중…" : "보내기"}
      </button>
    </form>
  );
}

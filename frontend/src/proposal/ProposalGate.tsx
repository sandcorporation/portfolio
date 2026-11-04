import type { ReactNode } from "react";
import { Masthead } from "../brand/Masthead";
import { formatDate } from "./ProposalDocument";
import type { CodeScreenData, ExpiredScreenData, Supplier } from "./types";

function GateShell({ children, plain }: { children: ReactNode; plain?: boolean }) {
  return (
    <>
      <Masthead plain={plain === true} />
      <main className="page gate-page">
        <section className="gate">{children}</section>
      </main>
    </>
  );
}

const ERRORS: Record<NonNullable<CodeScreenData["error"]>, string> = {
  wrong: "접근 코드가 맞지 않습니다. 다시 확인해 주세요.",
  blocked: "잘못 입력한 횟수가 많아 잠시 막아 두었습니다. 15분쯤 뒤에 다시 시도해 주세요.",
};

/** The code form. It posts to this same address; the server answers with the document. */
export function ProposalCodeScreen({ data, action }: { data: CodeScreenData; action: string }) {
  return (
    <GateShell plain={data.platform_mode}>
      <p className="section-head" aria-hidden="true">
        <span>Proposal</span>
      </p>
      <h1 id="gate-title">제안서 열기</h1>
      <p className="gate-lead">전달받은 접근 코드를 입력해 주세요.</p>
      <form className="gate-form" method="post" action={action} aria-labelledby="gate-title">
        <input type="hidden" name="csrfmiddlewaretoken" value={data.csrf_token} />
        <label>
          접근 코드
          <input
            name="code"
            required
            autoFocus
            autoComplete="off"
            autoCapitalize="none"
            spellCheck={false}
            maxLength={32}
            placeholder="접근 코드"
            aria-invalid={data.error ? true : undefined}
            aria-describedby={data.error ? "gate-error" : undefined}
          />
        </label>
        {data.error && (
          <p id="gate-error" className="gate-error" role="alert">
            {ERRORS[data.error]}
          </p>
        )}
        <button type="submit">열기</button>
      </form>
      <p className="gate-note">코드를 확인하면 이 브라우저에서 7일 동안 다시 묻지 않습니다.</p>
    </GateShell>
  );
}

function Contact({ supplier }: { supplier: Supplier }) {
  return (
    <dl className="gate-contact">
      <div>
        <dt>공급자</dt>
        <dd>{supplier.name}</dd>
      </div>
      {supplier.email && (
        <div>
          <dt>이메일</dt>
          <dd>
            <a href={`mailto:${supplier.email}`}>{supplier.email}</a>
          </dd>
        </div>
      )}
      {supplier.phone && (
        <div>
          <dt>전화</dt>
          <dd>
            <a href={`tel:${supplier.phone.replaceAll(/[^\d+]/g, "")}`}>{supplier.phone}</a>
          </dd>
        </div>
      )}
    </dl>
  );
}

/** Past the validity date: no document, only whom to ask for a new one. */
export function ProposalExpiredScreen({ data }: { data: ExpiredScreenData }) {
  return (
    <GateShell plain={data.platform_mode}>
      <h1>제안서 유효기간이 지났습니다</h1>
      <p className="gate-lead">
        이 제안서는 {formatDate(data.valid_until)}까지 유효했습니다. 새 견적이 필요하시면 아래로
        연락해 주세요.
      </p>
      <Contact supplier={data.supplier} />
    </GateShell>
  );
}

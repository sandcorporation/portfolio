import { render, screen } from "@testing-library/react";
import { DocumentView } from "./DocumentView";
import { documentOf, exampleBlock } from "./testing";

test("callout 블록은 종류(안내·주의·조건)와 제목, 본문을 보여 준다", () => {
  render(
    <DocumentView
      document={documentOf(
        exampleBlock("security", "callout"),
        exampleBlock("payment-terms", "callout"),
        exampleBlock("case-note", "callout"),
      )}
    />,
  );

  const warning = screen.getByRole("complementary", { name: "주의" });
  expect(warning).toHaveTextContent("보안 조건 · 고객자료 외부 전송 금지");
  expect(warning).toHaveTextContent("외부 AI API와 클라우드 구독 서비스에는 전송하지 않습니다.");
  expect(screen.getByRole("complementary", { name: "조건" })).toHaveTextContent("견적 조건");
  expect(screen.getByRole("complementary", { name: "안내" })).toHaveTextContent(
    "수행 사례의 수치는 고객사 동의를 받아 공개합니다.",
  );
});

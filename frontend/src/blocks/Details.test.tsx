import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DocumentView } from "./DocumentView";
import { documentOf, exampleBlock } from "./testing";

test("details 블록은 접혀 있다가 요약을 누르면 펼쳐진다", async () => {
  const { container } = render(
    <DocumentView document={documentOf(exampleBlock("api-fees", "details"))} />,
  );
  const details = container.querySelector("details");

  expect(details).not.toHaveAttribute("open");
  await userEvent.click(screen.getByText("API 요금 보기"));
  expect(details).toHaveAttribute("open");
  expect(screen.getByRole("cell", { name: "Deepgram Nova-3" })).toBeInTheDocument();
});

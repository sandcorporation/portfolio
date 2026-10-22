import { render, screen } from "@testing-library/react";
import { App } from "./App";

test("홈은 준비 중 안내를 보여 준다", () => {
  render(<App />);

  expect(screen.getByRole("heading", { name: "Sandcorp" })).toBeInTheDocument();
  expect(screen.getByText("사이트를 준비하고 있습니다.")).toBeInTheDocument();
});

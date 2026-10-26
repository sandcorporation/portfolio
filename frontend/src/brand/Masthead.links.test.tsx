import { render, screen } from "@testing-library/react";
import { SiteFooter, SiteMeta, SiteNav } from "./Masthead";

describe("external links (#129)", () => {
  it("open nav and GitHub links in a new tab, internal ones in the same tab", () => {
    render(
      <>
        <SiteMeta />
        <SiteNav />
        <SiteFooter />
      </>,
    );
    const foresight = screen.getByRole("link", { name: /Foresight/ });
    expect(foresight).toHaveAttribute("target", "_blank");
    expect(foresight).toHaveAttribute("rel", "noopener noreferrer");
    for (const github of screen.getAllByRole("link", { name: "GitHub" })) {
      expect(github).toHaveAttribute("target", "_blank");
      expect(github).toHaveAttribute("rel", "noopener noreferrer");
    }
    expect(screen.getByRole("link", { name: "기록" })).not.toHaveAttribute("target");
    expect(screen.getByRole("link", { name: "홈" })).not.toHaveAttribute("target");
  });
});

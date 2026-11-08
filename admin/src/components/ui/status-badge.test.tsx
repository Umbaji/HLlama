import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { StatusBadge } from "./status-badge";

describe("StatusBadge", () => {
  it("shows its text with the colour of its tone", () => {
    const html = renderToStaticMarkup(<StatusBadge tone="danger">Rejected</StatusBadge>);
    expect(html).toContain("Rejected");
    expect(html).toContain("text-destructive");
  });

  it("a pending status is amber, a success green", () => {
    expect(renderToStaticMarkup(<StatusBadge tone="pending">x</StatusBadge>)).toContain("amber");
    expect(renderToStaticMarkup(<StatusBadge tone="success">x</StatusBadge>)).toContain("emerald");
  });
});

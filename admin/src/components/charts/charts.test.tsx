import { describe, expect, it } from "vitest";
import { Pagination } from "@/components/ui/pagination";
import { StatGrid } from "./stat-grid";
import { renderIntl } from "@/test/intl";

describe("StatGrid", () => {
  it("shows every figure of the overview", async () => {
    const { html, missing } = await renderIntl(
      <StatGrid stats={{
        total_users: 1234, active_users: 1001, inactive_users: 233, total_admins: 3, total_questions: 5678,
        new_users_7d: 12, new_users_30d: 45, questions_7d: 67, questions_30d: 89,
      }} />,
    );
    expect(missing).toEqual([]);
    for (const value of ["1,234", "1,001", "5,678", "12", "45", "67", "89"]) expect(html).toContain(value);
  });
});

describe("Pagination", () => {
  const META = {
    request_id: "550e8400-e29b-41d4-a716-446655440000",
    served_at: "2026-10-29T12:00:00Z",
    current_page: 1,
    total_pages: 3,
    total_count: 60,
    page_size: 20,
    has_more: true,
  };

  it("is hidden when everything fits on one page", async () => {
    const { html } = await renderIntl(<Pagination meta={{ ...META, total_pages: 1 }} page={1} onPageChange={() => {}} />);
    expect(html).toBe("");
  });

  it("cannot go before the first page", async () => {
    const { html, missing } = await renderIntl(<Pagination meta={META} page={1} onPageChange={() => {}} />);
    expect(missing).toEqual([]);
    expect(html.match(/disabled=""/g)).toHaveLength(1);
  });
});

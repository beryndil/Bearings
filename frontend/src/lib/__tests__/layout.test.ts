/**
 * Layout-shape regression test for item 2.1's app shell.
 *
 * Asserts the three-column grid that `docs/behavior/chat.md`
 * §"opens an existing chat" describes — sidebar / main / inspector —
 * so a refactor in items 2.2-2.10 cannot silently collapse one of the
 * columns.
 */
import { render } from "@testing-library/svelte";
import { describe, expect, it } from "vitest";

import Layout from "../../routes/+layout.svelte";

describe("app shell layout", () => {
  it("renders sidebar, main and inspector regions", () => {
    const { getByTestId } = render(Layout);

    expect(getByTestId("app-shell")).toBeInTheDocument();
    expect(getByTestId("app-shell-sidebar")).toBeInTheDocument();
    expect(getByTestId("app-shell-main")).toBeInTheDocument();
    expect(getByTestId("app-shell-inspector")).toBeInTheDocument();
  });

  it("center column has header, body and composer slots", () => {
    const { getByTestId } = render(Layout);

    expect(getByTestId("app-shell-main-header")).toBeInTheDocument();
    expect(getByTestId("app-shell-main-body")).toBeInTheDocument();
    expect(getByTestId("app-shell-main-composer")).toBeInTheDocument();
  });

  it("labels each region with an ARIA landmark for screen readers", () => {
    const { getByLabelText } = render(Layout);

    expect(getByLabelText("Sessions sidebar")).toBeInTheDocument();
    expect(getByLabelText("Conversation pane")).toBeInTheDocument();
    expect(getByLabelText("Inspector")).toBeInTheDocument();
  });
});

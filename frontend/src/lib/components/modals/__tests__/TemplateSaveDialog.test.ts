/**
 * TemplateSaveDialog modal tests (N-7).
 *
 * Acceptance criteria:
 *  1. Renders with the initial name pre-filled in the input.
 *  2. Clicking Save calls onSave with the trimmed input value.
 *  3. Empty name shows the validation error, does not call onSave.
 *  4. Clicking Cancel calls onCancel without calling onSave.
 *  5. Pressing Esc calls onCancel.
 *  6. Pressing Enter submits (calls onSave).
 *  7. Backdrop click calls onCancel.
 *  8. Prop errorMessage renders in the error element.
 */
import { fireEvent, render, waitFor } from "@testing-library/svelte";
import { describe, expect, it, vi } from "vitest";

import TemplateSaveDialog from "../TemplateSaveDialog.svelte";

function renderDialog(props: {
  initialName?: string;
  onSave?: (name: string) => void;
  onCancel?: () => void;
  errorMessage?: string | null;
}) {
  return render(TemplateSaveDialog, {
    props: {
      initialName: props.initialName ?? "My Session",
      onSave: props.onSave ?? vi.fn(),
      onCancel: props.onCancel ?? vi.fn(),
      errorMessage: props.errorMessage ?? null,
    },
  });
}

describe("TemplateSaveDialog", () => {
  it("(1) renders with initial name pre-filled", () => {
    const { getByTestId } = renderDialog({ initialName: "Foo Bar" });
    const input = getByTestId("template-save-dialog-input") as HTMLInputElement;
    expect(input.value).toBe("Foo Bar");
  });

  it("(2) clicking Save calls onSave with trimmed name", async () => {
    const onSave = vi.fn();
    const { getByTestId } = renderDialog({ initialName: "  my template  ", onSave });
    fireEvent.click(getByTestId("template-save-dialog-save"));
    await waitFor(() => expect(onSave).toHaveBeenCalledWith("my template"));
  });

  it("(3) empty name shows validation error, does not call onSave", async () => {
    const onSave = vi.fn();
    const { getByTestId } = renderDialog({ initialName: "", onSave });
    fireEvent.click(getByTestId("template-save-dialog-save"));
    await waitFor(() => {
      expect(getByTestId("template-save-dialog-error")).toBeTruthy();
    });
    expect(onSave).not.toHaveBeenCalled();
  });

  it("(4) clicking Cancel calls onCancel, not onSave", async () => {
    const onSave = vi.fn();
    const onCancel = vi.fn();
    const { getByTestId } = renderDialog({ onSave, onCancel });
    fireEvent.click(getByTestId("template-save-dialog-cancel"));
    await waitFor(() => expect(onCancel).toHaveBeenCalled());
    expect(onSave).not.toHaveBeenCalled();
  });

  it("(5) pressing Esc calls onCancel", async () => {
    const onCancel = vi.fn();
    const { getByTestId } = renderDialog({ onCancel });
    const dialog = getByTestId("template-save-dialog");
    fireEvent.keyDown(dialog, { key: "Escape" });
    await waitFor(() => expect(onCancel).toHaveBeenCalled());
  });

  it("(6) pressing Enter submits (calls onSave)", async () => {
    const onSave = vi.fn();
    const { getByTestId } = renderDialog({ initialName: "template-name", onSave });
    const dialog = getByTestId("template-save-dialog");
    fireEvent.keyDown(dialog, { key: "Enter" });
    await waitFor(() => expect(onSave).toHaveBeenCalledWith("template-name"));
  });

  it("(7) backdrop click calls onCancel", async () => {
    const onCancel = vi.fn();
    // The backdrop is the presentation div containing the dialog
    const { container } = renderDialog({ onCancel });
    const backdrop = container.querySelector('[role="presentation"]') as HTMLElement;
    fireEvent.click(backdrop);
    await waitFor(() => expect(onCancel).toHaveBeenCalled());
  });

  it("(8) errorMessage prop renders in error element", async () => {
    const { getByTestId } = renderDialog({ errorMessage: "Duplicate template name" });
    const errorEl = getByTestId("template-save-dialog-error");
    expect(errorEl.textContent).toContain("Duplicate template name");
  });
});

<script lang="ts" module>
  /**
   * Shared status-derivation helper — exported so the ChecklistView
   * tests can assert the colour mapping without poking at DOM classes.
   * Keeping the function module-level (not inside the component
   * <script>) lets the unit tests import it directly without a
   * Svelte mount.
   */
  import {
    CHECKLIST_STRINGS,
    ITEM_OUTCOME_BLOCKED,
    ITEM_OUTCOME_FAILED,
    ITEM_OUTCOME_SKIPPED,
  } from "../../config";
  import type { ChecklistItemOut } from "../../api/checklists";

  /**
   * Pip colour alphabet — mirrors the table in
   * ``docs/behavior/checklists.md`` §"Item-status colors". Keeping
   * each constant named so the auditor's "no inline literals" gate
   * grep finds them without false positives on Tailwind class strings.
   */
  export const PIP_COLOR_NONE = "none";
  export const PIP_COLOR_SLATE = "slate";
  export const PIP_COLOR_BLUE = "blue";
  export const PIP_COLOR_GREEN = "green";
  export const PIP_COLOR_AMBER = "amber";
  export const PIP_COLOR_RED = "red";
  export const PIP_COLOR_GREY = "grey";

  export type PipColor =
    | typeof PIP_COLOR_NONE
    | typeof PIP_COLOR_SLATE
    | typeof PIP_COLOR_BLUE
    | typeof PIP_COLOR_GREEN
    | typeof PIP_COLOR_AMBER
    | typeof PIP_COLOR_RED
    | typeof PIP_COLOR_GREY;

  /**
   * Derive the pip colour for ``item`` per behavior/checklists.md
   * §"Item-status colors":
   *
   * | Color | State |
   * |---|---|
   * | (none / hollow) | Not yet attempted by a driver, no paired chat. |
   * | Slate | Has a paired chat, no run currently driving the item. |
   * | Blue, animated | The autonomous driver currently has this item active. |
   * | Green | Item is checked. |
   * | Amber | Item is blocked. |
   * | Red | Item failed. |
   * | Grey | Item was skipped. |
   *
   * ``isCurrent`` is true when the active run's ``current_item_id``
   * matches this item's id — that's the blue/animated state per the
   * behavior doc.
   */
  export function pipColorForItem(item: ChecklistItemOut, isCurrent: boolean): PipColor {
    if (isCurrent) return PIP_COLOR_BLUE;
    if (item.checked_at !== null) return PIP_COLOR_GREEN;
    if (item.blocked_reason_category === ITEM_OUTCOME_BLOCKED) return PIP_COLOR_AMBER;
    if (item.blocked_reason_category === ITEM_OUTCOME_FAILED) return PIP_COLOR_RED;
    if (item.blocked_reason_category === ITEM_OUTCOME_SKIPPED) return PIP_COLOR_GREY;
    if (item.chat_session_id !== null) return PIP_COLOR_SLATE;
    return PIP_COLOR_NONE;
  }

  /** Tooltip lookup keyed on the pip colour. */
  export function pipTooltip(color: PipColor): string {
    switch (color) {
      case PIP_COLOR_NONE:
        return CHECKLIST_STRINGS.sentinelEventTooltipNone;
      case PIP_COLOR_SLATE:
        return CHECKLIST_STRINGS.sentinelEventTooltipSlate;
      case PIP_COLOR_BLUE:
        return CHECKLIST_STRINGS.sentinelEventTooltipBlue;
      case PIP_COLOR_GREEN:
        return CHECKLIST_STRINGS.sentinelEventTooltipGreen;
      case PIP_COLOR_AMBER:
        return CHECKLIST_STRINGS.sentinelEventTooltipAmber;
      case PIP_COLOR_RED:
        return CHECKLIST_STRINGS.sentinelEventTooltipRed;
      case PIP_COLOR_GREY:
        return CHECKLIST_STRINGS.sentinelEventTooltipGrey;
    }
  }
</script>

<script lang="ts">
  /**
   * SentinelEvent — the colored item-status pip rendered as the
   * leftmost column of every checklist row.
   *
   * Behavior anchors:
   *
   * - ``docs/behavior/checklists.md`` §"Item-status colors" — the
   *   color/state table this component implements 1:1.
   * - ``docs/behavior/checklists.md`` §"Sentinels" — the auto-driver
   *   writes the outcome category (``blocked`` / ``failed`` /
   *   ``skipped``) on the item row when it consumes a terminal
   *   sentinel; this component derives the colour from those columns.
   * - ``docs/architecture-v1.md`` §1.2 — the checklist component
   *   group sits under ``components/checklist/``.
   *
   * The component is presentational. The parent (ChecklistItemRow)
   * passes the row + the active-run's ``current_item_id`` so the
   *  "blue / animated" state lights up exactly when the driver is
   * actively walking the item.
   */
  interface Props {
    item: ChecklistItemOut;
    /** ``true`` when the active run's ``current_item_id`` is this item. */
    isCurrent?: boolean;
  }

  const { item, isCurrent = false }: Props = $props();

  const color = $derived(pipColorForItem(item, isCurrent));
  const tooltip = $derived(pipTooltip(color));
</script>

<span
  class="sentinel-event sentinel-event--{color}"
  class:sentinel-event--animated={color === "blue"}
  data-testid="sentinel-event"
  data-pip-color={color}
  title={tooltip}
  aria-label={CHECKLIST_STRINGS.sentinelEventAriaLabel}
  role="img"
></span>

<style>
  /*
   * Pip colours map to theme tokens so item 2.9's theme provider can
   * re-tint without re-painting this component. Every fallback colour
   * is the canonical Tailwind shade so the surface still reads
   * correctly when the theme variables are unset.
   */
  .sentinel-event {
    display: inline-block;
    width: 0.5rem;
    height: 0.5rem;
    border-radius: 9999px;
    border: 1px solid var(--bearings-border, rgba(255, 255, 255, 0.18));
    background-color: transparent;
    flex-shrink: 0;
  }
  .sentinel-event--none {
    background-color: transparent;
  }
  .sentinel-event--slate {
    background-color: var(--bearings-pip-slate, rgb(100, 116, 139));
  }
  .sentinel-event--blue {
    background-color: var(--bearings-pip-blue, rgb(59, 130, 246));
  }
  .sentinel-event--green {
    background-color: var(--bearings-pip-green, rgb(34, 197, 94));
  }
  .sentinel-event--amber {
    background-color: var(--bearings-pip-amber, rgb(245, 158, 11));
  }
  .sentinel-event--red {
    background-color: var(--bearings-pip-red, rgb(239, 68, 68));
  }
  .sentinel-event--grey {
    background-color: var(--bearings-pip-grey, rgb(148, 163, 184));
  }

  /*
   * Animated blue — behavior doc §"Item-status colors" calls for the
   * blue pip to be "animated" while the driver is active on the
   * item. A subtle pulsing keeps the status legible without grabbing
   * the user's attention away from the conversation pane.
   */
  .sentinel-event--animated {
    animation: sentinel-event-pulse 1200ms ease-in-out infinite;
  }
  @keyframes sentinel-event-pulse {
    0%,
    100% {
      opacity: 1;
    }
    50% {
      opacity: 0.55;
    }
  }
</style>

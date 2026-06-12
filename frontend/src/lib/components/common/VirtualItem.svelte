<script lang="ts">
  /**
   * Viewport-aware virtualisation wrapper (gap-cycle-01-012).
   *
   * Keeps DOM node counts bounded on long timelines (conversation pane,
   * sessions sidebar) by lazy-mounting its slot content when the row
   * enters the viewport and replacing it with a fixed-height placeholder
   * when the row leaves. The placeholder preserves the exact measured
   * height of the content so the container's total height — and therefore
   * the scrollbar thumb position — stays stable.
   *
   * Design choices:
   *
   * - Starts ``visible = true`` so content renders immediately on first
   *   paint. The IntersectionObserver fires shortly after mount and
   *   unmounts rows outside the viewport + margin.
   * - ``reservedHeight`` is captured from ``getBoundingClientRect()``
   *   inside the observer callback, before ``visible`` is set to
   *   ``false``. Both state writes happen in the same microtask so
   *   Svelte batches them into a single DOM mutation — no layout thrash.
   * - When content re-mounts (``visible = true``), the explicit height
   *   style is cleared so the element resizes to its natural content
   *   height. This handles rows whose height changes between mount cycles
   *   (e.g. tool-output streaming adds content).
   *
   * ``alwaysVisible``:
   *
   * When ``true`` the IntersectionObserver is not wired and ``visible``
   * is held permanently ``true``. Use this for rows that must stay
   * mounted regardless of scroll position — specifically the in-flight
   * streaming assistant turn, which would otherwise be virtualized away
   * the moment its parent scroll container's ``scrollHeight`` grows past
   * the current ``scrollTop``. When ``alwaysVisible`` transitions from
   * ``true`` to ``false`` (e.g. after ``message_complete``), the
   * ``$effect`` re-runs and wires the observer at the element's current
   * intersection state so the row is immediately eligible for
   * virtualisation if it has scrolled out of view.
   *
   * Behaviour anchor: ``docs/behavior/chat.md`` (conversation turn list),
   * ``docs/behavior/`` §"SessionList" (sidebar rows).
   */
  import type { Snippet } from "svelte";
  import { VIRTUAL_ITEM_ROOT_MARGIN } from "../../config";

  interface Props {
    /**
     * IntersectionObserver ``rootMargin`` — controls how far outside the
     * viewport a row preloads. Positive values pre-mount rows before they
     * enter the viewport, preventing visible blank flashes on fast scroll.
     * Defaults to ``VIRTUAL_ITEM_ROOT_MARGIN`` (200 px top + bottom).
     */
    rootMargin?: string;
    /** Slot content to mount / unmount as the row crosses the viewport. */
    children?: Snippet;
    /**
     * When ``true``, the IntersectionObserver is bypassed and the content
     * is always rendered regardless of scroll position. Transitions to
     * ``false`` are handled reactively: the ``$effect`` re-runs and wires
     * the observer at the element's current intersection state.
     *
     * Set this for the active streaming assistant turn so tokens render
     * live even when the scroll container is slightly past true-bottom
     * (see ``CONVERSATION_AT_BOTTOM_THRESHOLD_PX`` rationale).
     */
    alwaysVisible?: boolean;
  }

  const {
    rootMargin = VIRTUAL_ITEM_ROOT_MARGIN,
    children,
    alwaysVisible = false,
  }: Props = $props();

  /** Reference to the outer wrapper element. Used by the observer. */
  let wrapperEl = $state<HTMLDivElement | null>(null);

  /** Whether the slot content is currently mounted. */
  let visible = $state(true);

  /**
   * Last measured height (px) while content was mounted. Applied as an
   * explicit ``height`` style on the wrapper when the content is hidden
   * so the document's total height — and therefore the scrollbar — does
   * not shift.
   *
   * ``null`` until the row has exited the viewport at least once.
   */
  let reservedHeight = $state<number | null>(null);

  /**
   * Wire (or bypass) the IntersectionObserver whenever ``alwaysVisible``
   * or ``wrapperEl`` changes.
   *
   * - When ``alwaysVisible = true``: set ``visible = true`` immediately
   *   and skip observer creation. The cleanup is a no-op (the observer
   *   was never created).
   * - When ``alwaysVisible = false``: create the IntersectionObserver as
   *   before. If ``alwaysVisible`` just transitioned from ``true``, the
   *   observer fires with the element's current intersection state so
   *   the row is immediately eligible for virtualisation.
   *
   * Using ``$effect`` instead of ``onMount`` lets Svelte re-run this
   * logic reactively when ``alwaysVisible`` changes (e.g. after
   * ``message_complete`` flips the streaming turn's ``complete`` flag).
   */
  $effect(() => {
    if (alwaysVisible) {
      visible = true;
      return;
    }

    const el = wrapperEl;
    if (el === null) return;

    const observer = new IntersectionObserver(
      (entries) => {
        const entry = entries[0];
        if (entry === undefined) return;

        if (entry.isIntersecting) {
          visible = true;
        } else {
          // Capture the current height before the DOM update removes the
          // content. Both writes are in the same synchronous callback so
          // Svelte 5 batches them into one flush — the DOM jumps from
          // "content visible, no explicit height" to "placeholder visible,
          // explicit height = N" atomically.
          reservedHeight = el.getBoundingClientRect().height;
          visible = false;
        }
      },
      { rootMargin },
    );

    observer.observe(el);
    return () => observer.disconnect();
  });

  /**
   * Explicit height applied to the wrapper while content is hidden.
   * Cleared (``undefined``) when the content is visible so the element
   * resizes naturally with its content.
   */
  const wrapperStyle = $derived(
    !visible && reservedHeight !== null ? `height: ${reservedHeight}px` : undefined,
  );
</script>

<!--
  The wrapper div is the IntersectionObserver target. Its ``style``
  carries an explicit height only while content is hidden, preserving
  the total document height so the scrollbar thumb does not jump.
-->
<div bind:this={wrapperEl} class="virtual-item" style={wrapperStyle} data-testid="virtual-item">
  {#if visible}
    {@render children?.()}
  {:else}
    <!--
      Empty placeholder. The outer wrapper's explicit ``height`` style
      maintains the scroll geometry; this div is a semantic container
      for accessibility tooling.
    -->
    <div
      class="virtual-item__placeholder"
      aria-hidden="true"
      data-testid="virtual-item-placeholder"
    ></div>
  {/if}
</div>

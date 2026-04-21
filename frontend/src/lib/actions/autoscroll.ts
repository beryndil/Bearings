/**
 * Svelte action: keep `node` scrolled to its bottom as content grows,
 * but only while the user is already parked near the bottom. If they
 * scroll up to read earlier output, we leave their scroll position
 * alone until they scroll back down.
 *
 * Pass any value that changes when content grows (e.g. the output
 * length). The action re-evaluates "am I at the bottom?" on every
 * user scroll event and sticks to the bottom on `update`.
 */
const NEAR_BOTTOM_PX = 24;

export function stickToBottom(node: HTMLElement, _deps: unknown) {
  let atBottom = true;

  const onScroll = () => {
    atBottom = node.scrollHeight - node.scrollTop - node.clientHeight < NEAR_BOTTOM_PX;
  };
  node.addEventListener('scroll', onScroll, { passive: true });

  const scroll = () => {
    if (!atBottom) return;
    queueMicrotask(() => {
      node.scrollTop = node.scrollHeight;
    });
  };

  scroll();
  return {
    update(_next: unknown) {
      scroll();
    },
    destroy() {
      node.removeEventListener('scroll', onScroll);
    }
  };
}

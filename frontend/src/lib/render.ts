/**
 * Markdown + code-highlight rendering primitives for the conversation
 * pane.
 *
 * `docs/behavior/chat.md` §"Conversation rendering" mandates CommonMark +
 * GFM with syntax-highlighted code blocks. Item 2.1 wires the libraries
 * (`marked` + `shiki`) so item 2.3 (Conversation + streaming) consumes
 * the same primitives without re-deciding the parser stack.
 *
 * Stubs vs full implementation:
 *
 * - `renderMarkdown` is real — `marked.parse` is deterministic and
 *   pure, so wiring it now costs nothing and lets the empty-state
 *   placeholder in `+page.svelte` round-trip through the pipeline.
 * - `highlightCode` builds a shiki highlighter on first call and
 *   caches the singleton. Item 2.3 will swap the static theme list
 *   for a theme-aware one tied to `data-theme` (per
 *   `docs/behavior/themes.md` §"What gets re-themed live").
 */
import { marked, type MarkedOptions } from "marked";
import { createHighlighter, type Highlighter } from "shiki";

const DEFAULT_MARKED_OPTIONS: MarkedOptions = {
  // CommonMark + GFM per behavior/chat.md §"Conversation rendering".
  gfm: true,
  breaks: false,
};

/**
 * Render a Markdown source string to HTML using marked.
 *
 * Returns a `Promise<string>` because marked may run async extensions
 * (highlight, etc.) in 2.3+; for the 2.1 wiring it resolves
 * synchronously, but consumers that await the promise won't have to
 * change shape.
 */
export async function renderMarkdown(source: string): Promise<string> {
  return marked.parse(source, DEFAULT_MARKED_OPTIONS);
}

let highlighterPromise: Promise<Highlighter> | null = null;

/**
 * Lazily construct (and cache) a shiki highlighter loaded with the
 * fenced-code-block languages Bearings is most likely to render in
 * v1. Item 2.3 will extend the language list / wire theme switching.
 */
function getHighlighter(): Promise<Highlighter> {
  if (highlighterPromise === null) {
    highlighterPromise = createHighlighter({
      themes: ["github-dark", "github-light"],
      langs: ["bash", "diff", "javascript", "json", "python", "shell", "svelte", "typescript"],
    });
  }
  return highlighterPromise;
}

/**
 * Highlight a code snippet to HTML using shiki. Defaults to a
 * dark-on-dark theme pair that pairs with the Midnight Glass surface;
 * item 2.9 will read `data-theme` and pick the correct shiki theme
 * synchronously per `docs/behavior/themes.md` §"What gets re-themed live".
 */
export async function highlightCode(
  source: string,
  lang: string,
  theme: "github-dark" | "github-light" = "github-dark",
): Promise<string> {
  const hl = await getHighlighter();
  return hl.codeToHtml(source, { lang, theme });
}

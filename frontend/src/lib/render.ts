import { marked } from 'marked';
import { createHighlighter, type Highlighter } from 'shiki';

const THEME = 'github-dark';

// Preloaded at highlighter init: the langs that dominate agent chat / tool
// output. Keep this list tight — every entry compiles a TextMate grammar at
// WASM startup. The rest are loaded on first demand via loadLanguage().
const PRELOAD_LANGS = ['python', 'typescript', 'bash', 'json', 'markdown', 'diff'] as const;

// Loaded on demand the first time a fenced block with that language appears.
// Grammar compile happens once per lang, then the instance caches it.
const ON_DEMAND_LANGS = [
  'javascript',
  'shell',
  'html',
  'css',
  'svelte',
  'yaml',
  'sql',
  'rust',
  'go',
  'toml'
] as const;

const ALL_LANGS: readonly string[] = [...PRELOAD_LANGS, ...ON_DEMAND_LANGS];
const ON_DEMAND_SET: ReadonlySet<string> = new Set(ON_DEMAND_LANGS);

let highlighter: Highlighter | null = null;
let highlighterPromise: Promise<void> | null = null;
const langLoads = new Map<string, Promise<void>>();

// Lazy init: shiki's WASM + grammars are ~hundreds of KB and were previously
// loaded via top-level await, blocking first paint. We now kick off loading
// on the first codeToHtml() call. Until it resolves, renderMarkdown() falls
// through to the existing plain <pre><code> branch — which re-renders with
// highlighting on the next reactive update once the promise settles.
function ensureHighlighter(): Promise<void> {
  if (highlighterPromise) return highlighterPromise;
  highlighterPromise = createHighlighter({
    themes: [THEME],
    langs: [...PRELOAD_LANGS]
  }).then((h) => {
    highlighter = h;
  });
  return highlighterPromise;
}

// Fire-and-forget loader for on-demand grammars. The current render falls
// through to the fallback; the next reactive update picks up the new grammar
// once the promise settles.
function ensureLangLoaded(lang: string): void {
  if (!highlighter) return;
  if (langLoads.has(lang)) return;
  if (highlighter.getLoadedLanguages().includes(lang)) return;
  const p = highlighter
    // shiki's BundledLanguage string union isn't exported at our import path;
    // ALL_LANGS gates the value so the cast is safe at runtime.
    .loadLanguage(lang as Parameters<Highlighter['loadLanguage']>[0])
    .then(() => undefined);
  langLoads.set(lang, p);
}

function escapeHtml(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

/** Wrap a rendered code-block HTML string so the context-menu delegate
 * (see `$lib/actions/contextmenu-delegate.ts`) can find it at
 * right-click time. Tests and the delegate both key on
 * `data-bearings-code-block` — changing the attr breaks both. The
 * language attribute is optional (fenceless blocks omit it); the
 * delegate treats a missing value as `null`. */
function wrapCodeBlock(html: string, lang: string | null): string {
  const attr = lang ? ` data-language="${escapeHtml(lang)}"` : '';
  return `<div data-bearings-code-block${attr}>${html}</div>`;
}

marked.use({
  renderer: {
    code({ text, lang }): string {
      // Carry the raw fence tag on the wrapper so `copy_with_fence`
      // can reconstruct the original triple-backtick block, even when
      // the lang isn't in our ALL_LANGS highlight set.
      const wrapperLang = lang ? lang : null;
      if (highlighter && lang && ALL_LANGS.includes(lang)) {
        if (highlighter.getLoadedLanguages().includes(lang)) {
          try {
            const html = highlighter.codeToHtml(text, { lang, theme: THEME });
            return wrapCodeBlock(html, wrapperLang);
          } catch {
            // Unknown lang edge case — fall through to plain <pre><code>.
          }
        } else if (ON_DEMAND_SET.has(lang)) {
          // Kick off grammar load; fall through to fallback for this render.
          ensureLangLoaded(lang);
        }
      } else if (!highlighter) {
        // Kick off the WASM load on first real demand. Fire-and-forget:
        // this render falls through to the fallback; next reactive update
        // picks up the ready highlighter.
        void ensureHighlighter();
      }
      const fallback = `<pre class="shiki-fallback"><code>${escapeHtml(text)}</code></pre>`;
      return wrapCodeBlock(fallback, wrapperLang);
    }
  }
});

marked.setOptions({
  gfm: true,
  breaks: true
});

/** Renders Markdown text into an HTML string.
 *
 * Content is trusted at the localhost-only boundary in v0.1.x — originates
 * from the user or their own agent. The consumer must still use `{@html}`
 * responsibly.
 */
export function renderMarkdown(text: string): string {
  if (!text) return '';
  return marked.parse(text, { async: false }) as string;
}

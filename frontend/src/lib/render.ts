import { marked } from 'marked';

marked.setOptions({
  gfm: true,
  breaks: true
});

/** Renders Markdown text into an HTML string.
 *
 * Untrusted content. The consumer is responsible for passing the result to
 * `{@html ...}` only after auditing trust boundaries — in v0.1.3 all
 * rendered content originates from either the local user or the user's own
 * Claude Code agent, both running on 127.0.0.1, so this is acceptable.
 */
export function renderMarkdown(text: string): string {
  if (!text) return '';
  return marked.parse(text, { async: false }) as string;
}

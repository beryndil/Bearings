const ESCAPES: Record<string, string> = {
  '&': '&amp;',
  '<': '&lt;',
  '>': '&gt;',
  '"': '&quot;',
  "'": '&#39;'
};

function escapeHtml(input: string): string {
  return input.replace(/[&<>"']/g, (c) => ESCAPES[c]);
}

function escapeRegExp(input: string): string {
  return input.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

/**
 * Returns HTML in which every case-insensitive occurrence of `query`
 * inside `text` is wrapped in a `<mark>` tag. The source is
 * HTML-escaped *before* inserting marks, so a message containing
 * `<script>` renders harmlessly.
 *
 * An empty query short-circuits to the escaped text.
 */
export function highlightText(text: string, query: string): string {
  const escaped = escapeHtml(text);
  if (!query) return escaped;
  const pattern = new RegExp(escapeRegExp(query), 'gi');
  return escaped.replace(pattern, (match) => `<mark>${match}</mark>`);
}

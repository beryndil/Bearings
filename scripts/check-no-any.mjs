#!/usr/bin/env node
/**
 * Frontend `any`-type guard. Fails non-zero when explicit TypeScript
 * `any` shows up in `frontend/src/**` outside of allowlisted sites.
 *
 * Why a custom script instead of ESLint:
 *   The project ships svelte-check + vitest as its TS toolchain — no
 *   ESLint config exists. Pulling in `@typescript-eslint` to lint a
 *   single rule is heavier than the rule warrants. This script is the
 *   minimum viable gate: detect explicit-`any` TypeScript syntax,
 *   skip legitimate non-type matches (comments, strings, the
 *   `expect.any(Error)` vitest matcher), exit 1 on a hit. If/when the
 *   linter set grows beyond this one rule, swap this for ESLint.
 *
 * The detection strategy is regex-on-stripped-source:
 *   1. Strip `/* ... *\/` block comments.
 *   2. Strip `// ...` line tails.
 *   3. Strip the body of single/double/back-quoted string literals.
 *   4. Run a small set of patterns that bind to TS type contexts.
 *
 * Run:  node scripts/check-no-any.mjs
 */

import { readFileSync } from 'node:fs';
import { execSync } from 'node:child_process';
import { resolve, relative } from 'node:path';

const ROOT = resolve(new URL('..', import.meta.url).pathname);
const SRC_REL = 'frontend/src';
const SRC_ABS = resolve(ROOT, SRC_REL);

/** Files explicitly permitted to use `any`. Empty for now — every site
 *  has a typed alternative. Add an entry only with a one-line rationale
 *  comment justifying why the type cannot be tightened. */
const ALLOWLIST = new Set([
  // (path, line) tuples e.g. 'lib/foo.ts:42'
]);

/** TS type-context patterns. Each pattern targets syntax that only
 *  appears in a type position; matches outside type position (e.g.
 *  `expect.any(...)`, `Array.isArray(any)`) are filtered upstream by
 *  the comment/string strip + the bare-identifier exclusions below. */
const TS_ANY_PATTERNS = [
  /:\s*any\b/, // `: any`
  /\bas\s+any\b/, // `as any`
  /<\s*any\s*[>,|]/, // `<any>` / `<any,` / `<any|`
  /\bany\[\]/, // `any[]`
  /,\s*any\s*[>,|\s]/, // `, any>` / `, any,` / `, any |`
  /\|\s*any\b/, // `| any`
  /=\s*any\s*[>,|;\s]/ // generic default `T = any`
];

function listFiles() {
  // git ls-files keeps us inside tracked sources only — node_modules,
  // .svelte-kit, dist all stay out automatically.
  const out = execSync(
    `git ls-files -- '${SRC_REL}/*.ts' '${SRC_REL}/*.svelte'`,
    { cwd: ROOT, encoding: 'utf8' }
  );
  return out
    .split('\n')
    .map((s) => s.trim())
    .filter(Boolean)
    .map((p) => resolve(ROOT, p));
}

/** Replace block-comment bodies with newline-preserving whitespace so
 *  line numbers stay aligned with the source. */
function stripBlockComments(src) {
  return src.replace(/\/\*[\s\S]*?\*\//g, (m) =>
    m.replace(/[^\n]/g, ' ')
  );
}

/** Drop `// ...` line tails. Naive but adequate for our codebase —
 *  `//` inside a string would have been masked by stripStrings already
 *  if applied first. We strip strings first, so this runs cleanly. */
function stripLineComments(src) {
  return src
    .split('\n')
    .map((line) => line.replace(/\/\/.*$/, ''))
    .join('\n');
}

/** Replace string-literal bodies with empty placeholders. Handles
 *  single, double, and back-tick. Doesn't try to follow template
 *  expression boundaries — false negatives inside `${...}` are
 *  acceptable; the strict patterns above wouldn't fire on prose. */
function stripStrings(src) {
  return src
    .replace(/'(?:\\.|[^'\\])*'/g, "''")
    .replace(/"(?:\\.|[^"\\])*"/g, '""')
    .replace(/`(?:\\.|[^`\\])*`/g, '``');
}

function scanFile(absPath) {
  const rel = relative(ROOT, absPath);
  const raw = readFileSync(absPath, 'utf8');
  // Order matters: strings first (they may contain `//` or `/*`),
  // then block comments, then line tails.
  const stripped = stripLineComments(
    stripBlockComments(stripStrings(raw))
  );
  const hits = [];
  const lines = stripped.split('\n');
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    for (const pat of TS_ANY_PATTERNS) {
      if (pat.test(line)) {
        const key = `${relative(SRC_ABS, absPath)}:${i + 1}`;
        if (ALLOWLIST.has(key)) break;
        hits.push({ file: rel, lineno: i + 1, text: raw.split('\n')[i] });
        break;
      }
    }
  }
  return hits;
}

function main() {
  const files = listFiles();
  const hits = files.flatMap(scanFile);
  if (hits.length === 0) {
    console.log(
      `check-no-any: 0 explicit \`any\` in ${SRC_REL}/ (${files.length} files scanned)`
    );
    process.exit(0);
  }
  console.error(
    `check-no-any: found ${hits.length} explicit \`any\` usage(s):\n`
  );
  for (const h of hits) {
    console.error(`  ${h.file}:${h.lineno}: ${h.text.trim()}`);
  }
  console.error(
    '\nFix: tighten the type, or add the (file, line) to ALLOWLIST in this script with a rationale.'
  );
  process.exit(1);
}

main();

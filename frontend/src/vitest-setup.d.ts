/**
 * Ambient module declaration so TypeScript picks up the
 * `@testing-library/jest-dom` matchers (`.toBeInTheDocument()`,
 * `.toHaveClass()`, etc.) augmented onto `expect()` by the side-effect
 * import in `vitest.setup.ts`.
 *
 * Without this triple-slash reference the matchers work at runtime
 * but svelte-check / tsc fail on the missing property declarations.
 */
/// <reference types="@testing-library/jest-dom" />

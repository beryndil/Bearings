// Flat-config ESLint setup for the SvelteKit frontend (item 2.1).
//
// `eslint-plugin-svelte`'s flat-config presets auto-wire `svelte.parser`
// for `*.svelte` files and route `<script lang="ts">` content through
// `@typescript-eslint/parser`, so we don't have to spell that out here.
import js from "@eslint/js";
import tseslint from "@typescript-eslint/eslint-plugin";
import tsparser from "@typescript-eslint/parser";
import svelte from "eslint-plugin-svelte";
import prettier from "eslint-config-prettier";
import globals from "globals";

export default [
  {
    // Generated SvelteKit + build outputs are out of scope.
    ignores: ["node_modules/", "build/", "dist/", ".svelte-kit/", "../src/bearings/web/dist/"],
  },
  js.configs.recommended,
  {
    files: ["**/*.{js,cjs,mjs,ts}"],
    languageOptions: {
      parser: tsparser,
      parserOptions: {
        ecmaVersion: 2022,
        sourceType: "module",
      },
      globals: {
        ...globals.browser,
        ...globals.node,
      },
    },
    plugins: { "@typescript-eslint": tseslint },
    rules: { ...tseslint.configs.recommended.rules },
  },
  ...svelte.configs["flat/recommended"],
  {
    files: ["**/*.svelte"],
    languageOptions: {
      parserOptions: {
        // Route `<script lang="ts">` through the TS parser; the svelte
        // plugin's preset wires svelte.parser for the template body.
        parser: tsparser,
      },
      globals: {
        ...globals.browser,
      },
    },
  },
  {
    files: ["**/*.{test,spec}.{ts,js}", "vitest.setup.ts"],
    languageOptions: {
      globals: {
        ...globals.node,
      },
    },
  },
  prettier,
  ...svelte.configs["flat/prettier"],
];

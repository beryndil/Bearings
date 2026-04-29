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
        // Svelte 5 runes — used in .svelte.ts modules. The
        // eslint-plugin-svelte flat preset auto-injects them for
        // .svelte files; .svelte.ts files need them spelled out.
        $state: "readonly",
        $derived: "readonly",
        $effect: "readonly",
        $props: "readonly",
        $bindable: "readonly",
        $inspect: "readonly",
        // ``RequestInfo`` is part of the Fetch lib but not always
        // injected as a global by ESLint's preset; add it explicitly
        // so test files using it as a parameter type pass.
        RequestInfo: "readonly",
      },
    },
    plugins: { "@typescript-eslint": tseslint },
    rules: {
      ...tseslint.configs.recommended.rules,
      // Defer to @typescript-eslint/no-unused-vars; the base rule
      // misreads TypeScript function-type parameter names (which are
      // documentation-only) as unused identifiers.
      "no-unused-vars": "off",
      "@typescript-eslint/no-unused-vars": [
        "error",
        { argsIgnorePattern: "^_", varsIgnorePattern: "^_" },
      ],
    },
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
    plugins: { "@typescript-eslint": tseslint },
    rules: {
      // Same reasoning as the .ts override above — type-signature
      // parameter names are documentation, not declarations.
      "no-unused-vars": "off",
      "@typescript-eslint/no-unused-vars": [
        "error",
        { argsIgnorePattern: "^_", varsIgnorePattern: "^_" },
      ],
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

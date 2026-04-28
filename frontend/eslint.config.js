// Flat-config ESLint setup for the SvelteKit frontend.
// Item 2.1 will extend this with SvelteKit-specific rules; here we only
// register the parser + svelte plugin so `eslint .` exits clean on the
// (currently empty) sources.
import js from "@eslint/js";
import tseslint from "@typescript-eslint/eslint-plugin";
import tsparser from "@typescript-eslint/parser";
import svelte from "eslint-plugin-svelte";
import prettier from "eslint-config-prettier";

export default [
  js.configs.recommended,
  {
    files: ["**/*.ts"],
    languageOptions: {
      parser: tsparser,
      parserOptions: {
        ecmaVersion: 2022,
        sourceType: "module",
      },
    },
    plugins: { "@typescript-eslint": tseslint },
    rules: { ...tseslint.configs.recommended.rules },
  },
  {
    files: ["**/*.svelte"],
    languageOptions: {
      parser: svelte.parser,
      parserOptions: { parser: tsparser },
    },
    plugins: { svelte },
    rules: { ...svelte.configs.recommended.rules },
  },
  prettier,
  {
    ignores: ["node_modules/", "build/", "dist/", ".svelte-kit/"],
  },
];

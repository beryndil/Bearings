/**
 * PostCSS plugin chain for the Tailwind v3 + autoprefixer pipeline.
 *
 * SvelteKit picks this file up automatically for both the global
 * `app.css` and component `<style>` blocks (via `vitePreprocess`).
 */
export default {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
};

import { defineConfig } from 'vite';

// Served from https://<user>.github.io/portfolio-market-credit-risk-analytics/ on GitHub Pages.
export default defineConfig({
  base: process.env.GITHUB_PAGES ? '/portfolio-market-credit-risk-analytics/' : '/',
});

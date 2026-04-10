# Rendered Career Pages Fallback

- Saved at: 2026-04-10T18:30:00.136985Z

Added optional JavaScript-rendered career page support to the custom career page source. New config fields let a page opt into Playwright rendering and specify rendered link selectors and wait selectors. The source still tries static HTML and sitemap discovery first, then falls back to a rendered DOM scrape when enabled. Added tests for selector extraction and rendered fallback behavior, plus README instructions for installing the browser extra and Chromium.

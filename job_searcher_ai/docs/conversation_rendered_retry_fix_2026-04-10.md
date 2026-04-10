# Rendered Fallback Retry Fix

- Saved at: 2026-04-10T18:31:40.518280Z

Updated the custom career page connector so JavaScript-rendered extraction is retried when static discovery only finds generic listing pages that do not parse into real jobs. This fixes the KUKA case where the static crawl discovered the /stellenangebote index page and never reached the rendered job detail URLs. Added a regression test covering that exact flow.

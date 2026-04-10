# Custom Render Logging

- Saved at: 2026-04-10T22:40:20.463523Z

Added detailed diagnostics to the custom career page source for rendered-page debugging. The source now logs how many candidate URLs came from static crawl, sitemap fallback, and rendered DOM extraction, including selector match counts, filtered link counts, and small URL samples. This is intended to make KUKA-style debugging straightforward when JavaScript-rendered job pages fail to appear in outputs.

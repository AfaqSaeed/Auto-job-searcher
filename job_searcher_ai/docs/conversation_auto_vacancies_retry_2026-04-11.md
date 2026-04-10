# Auto Vacancies Retry

- Saved at: 2026-04-10T23:30:02.663067Z

Updated the custom career page rendered fallback to automatically try simple include-pattern subpaths such as /stellenangebote or /vacancies beneath the configured careers page URL. This fixes the KUKA case where rendering /karriere alone returned no job anchors, while /karriere/stellenangebote contains the job list. Added a regression test for the derived render URL behavior.

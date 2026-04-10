# Custom Source Summary Fix

- Saved at: 2026-04-10T21:49:56.538386Z

Fixed a misleading log summary for custom career pages. A 404 from optional discovery URLs such as sitemap.xml was previously reported as a wrong ATS board slug, which only makes sense for Greenhouse or Lever. The summary now explains that optional discovery resources may be missing and that rendered or in-page discovery may still be required. Added a regression test for the custom career page 404 case.

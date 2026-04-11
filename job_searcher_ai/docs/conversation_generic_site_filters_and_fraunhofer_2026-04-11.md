# Generic Site Filters And Fraunhofer

- Saved at: 2026-04-11T00:05:03.088830Z

Added generic site-filter execution for rendered career pages. The custom career page source now derives a small set of filter plans from detected page controls, the configured target countries, the page company, and generated search terms, then applies those plans in Playwright before collecting result links. Updated settings.yaml to enable site-filter execution for KUKA and added Fraunhofer Jobs EN as a second test target using the same generic mechanism.

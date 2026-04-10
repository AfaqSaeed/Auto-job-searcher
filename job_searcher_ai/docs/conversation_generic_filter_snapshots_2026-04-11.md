# Generic Filter Snapshots

- Saved at: 2026-04-10T23:55:54.508619Z

Generalized the custom career page source by adding rendered filter introspection. The source now captures detected filter controls and options from rendered DOM pages into a new outputs/custom_career_page_filters.json artifact, with inferred semantic kinds such as search_text, country_region, company, and category. This provides the foundation for driving built-in site filters generically across many career pages instead of hardcoding KUKA-specific logic.

# 0.2.6

- Update the pinned core to 0.2.5 to retain intermediate temporal evidence
  before visually deduplicating additional frames.
- Configure `evidence.options.max_selected_gap_seconds` in `pipeline_config`
  (default 300 seconds, 0 disables). The evidence response reports actual gaps,
  unmet targets and warnings within the existing frame and image budgets.
- Preserve existing aggregation state, delivery receipts, analysis results and
  deployment options during the update.

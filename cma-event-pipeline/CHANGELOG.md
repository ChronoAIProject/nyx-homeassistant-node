# 0.3.0-alpha.2

- Accept JSON `expected_revision` for owner rule updates/archive when a proxy
  strips `If-Match`. Preserve atomic revision checks and credential boundaries.
- Send both header and body preconditions from the management page. Reject
  conflicts and invalid versions; stale writes still return 409.

# 0.3.0-alpha.1

- Rename the displayed add-on to Video Event Monitor; preserve its installed
  slug, internal hostname, image package and private deployment options.
- Add an admin-only HA Ingress page and owner API for multiple persistent rules,
  camera/zone discovery, quick configuration, advanced JSON, enable/disable,
  copy/archive, immutable revisions and recent decisions/results.
- Import the existing policy/state once as default v1. Retain original IDs,
  queues, results and callback paths. New revisions isolate state and callbacks;
  retired queues pause, and activities predating cutover are not replayed.
- Keep connection credentials and the single CMA destination in deployment
  options. New rules default to disabled and delivery off.
- Repair Frigate history for rules without image evidence; accept shared-bridge
  global heartbeats for multiple camera rules.
- Use complete HA backups for managed multi-rule state. Reject partial legacy
  exports; no scripts, host port, HA API or Supervisor permission are added.

# 0.2.6

- Update the pinned core to 0.2.5 to retain intermediate temporal evidence
  before visually deduplicating additional frames.
- Configure `evidence.options.max_selected_gap_seconds` in `pipeline_config`
  (default 300 seconds, 0 disables). The evidence response reports actual gaps,
  unmet targets and warnings within the existing frame and image budgets.
- Preserve existing aggregation state, delivery receipts, analysis results and
  deployment options during the update.

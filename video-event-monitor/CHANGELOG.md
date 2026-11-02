# Video Event Monitor release history

The current slug is `video-event-monitor`. Core and HA package versions are
separate; a worker/profile or documentation update does not imply a new installed
add-on version. See [packaging and updates](README.md#packaging-and-updates).

# 0.3.0-alpha.6

- Pin core 0.3.4 with opt-in recording-index alignment, bounded nearby snapshot
  retries, actual/requested timestamp metadata and explicit missing coverage.
- Support optional observations before configured object tracks end within the
  existing source-frame, selected-frame, time and page budgets. Track ending
  does not establish removal or consumption.
- Keep all stored rules, revisions, results and deployment settings. Enable the
  new evidence options through a managed rule revision when desired.

# 0.3.0-alpha.5

- Repair ownership of the full private state tree before dropping privileges so
  Supervisor-restored rule registries and nested history databases can open.
  Reject links/special files and keep Supervisor's options outside this repair.
- Exercise a restart with root-owned restored state in the packaged image smoke test.

# 0.3.0-alpha.4

- Unify the repository references, image packages, add-on directory/slug, panel
  title and runtime messages under Video Event Monitor / `video-event-monitor`.
- Pin core 0.3.3. This changes the HA installation identity: use the
  [complete-state migration procedure](../docs/monitor-identity-migration.md),
  verify rules/history and switch Relay/node targets before retiring the old add-on.

# 0.3.0-alpha.3

- Distinguish skipped/local-only events, paused/queued/retrying/failed delivery,
  CMA acceptance awaiting a callback, and actual worker results in history.
  Missing callbacks are not treated as failures; synthetic tests stay distinct.
- Add a Chinese/English selector for the management page, including status
  reasons, actions, confirmations and errors. Default to the browser language
  and preserve unsaved rule edits when switching. Revalidate UI assets on reload.
- Pin core 0.3.2; preserve all existing rules, revisions, results and queues.

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

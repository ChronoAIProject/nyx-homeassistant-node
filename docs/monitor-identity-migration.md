# Video Event Monitor: installation identity migration

The product, core repository/image, HA directory and add-on slug now use
**Video Event Monitor** / `video-event-monitor`. The HA wrapper image is
`ghcr.io/chronoaiproject/video-event-monitor-ha`.

The former core repository `frigate-cma-events` redirects to the new repository;
old image digests remain available for rollback. HA does not redirect an add-on
identity: the former `cma-event-pipeline` installation must be migrated. Do not
install an empty replacement and discard the original data. Changing directory
names alone does not move rules or history.

## Prepare

1. Publish the renamed core and HA image; verify both architecture manifests and
   access from HA. Refresh the Supervisor store and verify the new add-on is listed.
2. Export private options and record the old add-on hostname, Relay destination,
   NyxID service targets, current rules/revisions, decision/result counts, active
   CMA work and both outboxes. Retain the original backups and credential references.
3. Wait for active analysis/callbacks and CMA deliveries to drain. Stop Relay,
   then stop the old monitor. Keep both stopped while taking the final backup and
   switching targets; this prevents competing writers and duplicate deliveries.
4. Use Supervisor to create an **unencrypted partial backup of only the stopped
   monitor**, with no HA/folders selected. Download it to private local storage.
   The file contains credentials and should have mode `0600`.

## Transfer the complete state

From this repository, prepare a separate backup for the renamed installation:

```sh
python3 scripts/migrate_monitor_backup.py /private/old-monitor.tar \
  /private/video-event-monitor.tar --target-version 0.3.0-alpha.4 \
  > /private/migration-report.json
```

The helper changes only backup/add-on identity metadata, version, image, panel
settings and generated Supervisor identity tokens. It copies the options and all
data files byte-for-byte, including the rule registry, nested rule revisions,
SQLite databases and WAL files. It does not use the legacy single-rule export.
The output gets a new backup ID, restores stopped, and never replaces the original
archive or an existing output file. Custom image/AppArmor archives, encrypted,
multi-add-on, unsafe or oversized backups are rejected for separate review.

Upload the generated backup through Supervisor's backup upload API/page, then
restore **only the new `video-event-monitor` add-on**. Do not restore HA, folders,
other add-ons or Supervisor settings. Check the restore job to completion; the
new monitor must remain stopped. Keep the old installation stopped and intact.
The helper prepares an archive; it does not call HA or switch live traffic.

## Switch and verify

1. Start the new monitor. Obtain its actual hostname from Supervisor; the
   repository prefix is installation-specific.
2. Update matching NyxID service endpoints and ordinary-node local targets, keeping
   existing service IDs/grants and credentials. Verify owner and worker routes
   reach the restored instance and retain their respective access restrictions.
3. Compare all rules and revisions, historical decisions/results and outbox state
   against the private snapshot. Verify state ownership, current core/add-on
   versions and the Chinese/English page, including the full product name.
4. Update the Relay destination URL to the new hostname, keeping its destination
   ID and credentials. Start Relay, verify heartbeats and an explicitly bounded
   test, then confirm no failed/duplicate deliveries or changes to old results.
5. Restart the new monitor and verify persistence again. Enable its HA sidebar
   panel if desired. Keep the old add-on disabled/stopped until acceptance is complete;
   only then uninstall it. Preserve the original private backup for rollback.
6. Update the private active inventory, links/bookmarks and any operational notes.
   Worker/channel prompts and notification configuration need changes only if
   they reference renamed addresses; do not change stable candidate/result IDs.

If acceptance fails, stop the new monitor before restoring the prior routes and
starting the old instance. Never run both against the same live event stream.
After the new instance processes live events, reconcile its new state before any
rollback; blindly restoring the older snapshot can repeat already-delivered work.

Display names for separate components (Event Relay, NyxID Node, CMA and a
user-named Worker/NyxBot) keep describing those components. Configuration keys
such as `pipeline_config` and protocol event types remain unchanged. Existing
optional MongoDB installations retain their legacy database default; keep an
explicit `MONGODB_DATABASE` when using a differently named database.

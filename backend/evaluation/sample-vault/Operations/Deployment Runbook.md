---
aliases:
  - Release procedure
tags:
  - operations
  - deployment
---
# Deployment runbook

Use this runbook when publishing the application to production.

## Rollback

If health checks fail after deployment, stop the rollout and redeploy the previously tagged container image. Verify the `/health` endpoint before reopening traffic.

Rotate credentials only when required by [[Secret Rotation]]. Backups are documented in [[Backup Policy]].

# AWS Inventory + Migration Roadmap to Victus

Audit date: 2026-11-05. Account `294733692749`, region `us-east-2`. Sources: live AWS CLI queries (as root), CloudWatch, Cost Explorer, IAM credential report, codebase grep.

> **Execution status (2026-11-05, same day).** Decision: keep S3 (cheap, keeps the account active), move everything else. Victus was brought back up and relocated. Done: Postgres 17 on Victus with verified migration + nightly backups to a new private bucket; zombie EC2/EIP, ECR, root keys, SNS, SSM, Athena/Glue deleted; SNS/SSM/Athena removed from code. RDS `ag-dashboard` deleted by Raj in the console (final snapshot `ag-dashboard-final-20261105` kept); its orphaned network interface, security groups `rds-ec2-1` / `ec2-rds-1` / `launch-wizard-1` / `launch-wizard-2`, log group `RDSOSMetrics`, roles `rds-monitoring-role` + `EC2_USDA` and both `USDA-*` policies are all deleted. **Only remaining step:** around 2026-11-19, delete snapshots `ag-dashboard-final-20261105` (RDS) and `snap-0cc027bef2af87b6a` (EBS). Phase 3 (object storage) is not happening: S3 stays.

---

## 1. Live health check (what is broken right now)

| Check | Result |
|---|---|
| Victus on Tailscale (`server-local-ubuntu`, 100.75.64.59) | **Offline, last seen ~30 days ago** (around 2026-10-06). SSH times out. |
| `agri-intel.rvedire.com` (prod API) | **Cloudflare 1033** (tunnel has no connector) |
| `api` / `anomaly` / `mothra.rvedire.com` (same tunnel) | **HTTP 530**, so the whole box is down, not just ag-prediction |
| RDS `DatabaseConnections` | **0 since the week of 2026-09-27** (1-2 before that) |
| RDS security group allowlist | `50.90.232.153/32`, `136.52.89.100/32`. Current home IP is **`136.52.223.0`**, so **not allowed**. Home IP changed, and RDS is unreachable from both the PC and Victus. |
| `victus-ag-service` key last used | 2026-09-15 |
| Public S3 object reads (frontend) | OK (200). Listing the bucket is 403, which is fine. |

Likely timeline: home IP rotated in late Sep (RDS writes stop), then Victus went fully offline in early Oct. Nothing alerted, because SNS alerts depend on the cron box being alive. Since then there have been no Sunday newsletters, no weekly yield/drought runs, no futures/DXY ingest, and `/forecasts` + `/insights` have had no data.

---

## 2. AWS inventory

### Billed resources (~$43.60/month, every month since July)

| Resource | Details | Monthly cost | Still needed? |
|---|---|---:|---|
| **EC2 `i-05846d4343400eadc`** `doorknobs_aws_server` | t3.small, **running**, launched 2026-06-11. This is the "dead" EC2 that the July migration replaced. Avg CPU 0.4%. | $15.48 | **No, it's a zombie** |
| EBS `vol-00aa40ca706ad0503` | 30 GB gp3 attached to the zombie | $2.40 | No |
| Public IPv4 (VPC line item) | 3 addresses: EIP `16.58.84.210` (zombie EC2), `13.59.67.57` + `3.18.171.52` (RDS ENIs) | $11.16 | No, once EC2 and RDS are gone |
| **RDS `ag-dashboard`** | db.t4g.micro, Postgres 17.9, 20 GB gp3 (~2 GB used), public, 1-day backup retention | $14.20 | Yes until migrated |
| S3 `usda-analysis-datasets` | ~7.8 GB, public-read bucket policy, CORS `*` GET/HEAD | $0.33 | Yes (see Phase 3) |
| ECR `usda-dashboard` | one 380 MB image from 2025-12-06, unused | $0.04 | No |

The zombie EC2, its EBS volume and its IP have cost about **$21.60/month since July (~$86 so far)**. TECHNICAL_SUMMARY.md quotes ~$16/month; the real figure is $43.60.

### S3 layout (`usda-analysis-datasets`)

| Prefix | Size | Used by | Note |
|---|---:|---|---|
| `survey_datasets/raw_legacy/` | **6.9 GB** | nothing found in code | 89% of the bucket. Archive it, don't migrate it. |
| `survey_datasets/backups/` | 121 MB | rollback copies | archive |
| `survey_datasets/partitioned_states_demo/` | 106 MB | nothing found | archive |
| `survey_datasets/partitioned_states/` + `_counties/` | 71 MB | **browser** (hyparquet), `/api/data` proxy | serve |
| `survey_datasets/athena_optimized/` + `_counties/` | 71 MB | Athena only | drop with Athena |
| `survey_datasets/overview/` | 2.7 MB | **browser** (`overviewData.ts`) | serve |
| `enrichment/` | 0.1 MB | **browser** | serve |
| `models/` | 240 MB | backend startup fallback (`main.py::_load_models`), train upload | Victus already has them on local disk |
| `yield-caches/` | 82 MB | yield inference | local disk |
| `newsletters/` | 2 MB | agent publisher + `/api/v1/agent/*` proxy | local disk or object store |
| `aquiferwatch/` | 227 MB | **browser** (aquifer tab); **written by the separate aquifer-watch project** | serve; coordinate with that repo |
| `athena-results/` | ~0 | Athena | drop |

### Free / near-free resources

| Resource | Details | Status |
|---|---|---|
| Athena workgroup `usda-dashboard` + Glue DB `usda_agricultural.quickstats_data` | Points at `athena_optimized/` | **Dead code.** No query history; `fetchStateAggregated` / `fetchCommodityTrend` / `fetchStateComparison` and `useAthenaQuery` have **zero callers** in `web_app/src`. |
| SNS `usda-pipeline-alerts` | 1 email sub: `rvedire@iu.edu` | Used by `cron_runner.sh` (14 publish calls) |
| SSM `/usda/quickstats-api-key` | SecureString | Fallback only; `.env` already has the key. Victus still calls it (the key's last-used service is `ssm`). |
| CloudWatch | `RDSOSMetrics` log group only | goes with RDS |
| RDS snapshots | 3 automated + manual `final-ag-dashboard7ba8fb58...` (2026-05-27) | keep the manual one until cutover is proven |

### IAM / security findings

| Finding | Severity |
|---|---|
| **Root account has an active access key** (rotated 2026-02-28, last used 2026-06-15 for SNS, i.e. it lives on the zombie EC2) | **High.** Deactivate and delete it. |
| Zombie EC2 is internet-facing (EIP + `launch-wizard-2` SG) with root keys on disk and no patching since June | **High** |
| RDS publicly accessible (allowlisted IPs only) | Medium, goes away with migration |
| `victus-ag-service` (S3 + SNS inline policy), role `EC2_USDA`, policies `USDA-Pipeline-S3-Access` / `USDA-Athena-Query-Access` | cleanup after migration |
| Console users `raj`, `snehayadav` (no keys) | leave, unrelated |

**Out of scope but blocking account closure:** buckets `cms-provider-payment-data` and `igdb-streamlitapp-datasets` belong to other projects.

---

## 3. Roadmap

### Phase 0: Bring Victus back (blocker, do first)

1. Physically check Victus: power, network, disk. Look at `journalctl -b -1` for why it died (OOM, kernel panic, power cut, disk full).
2. Confirm that `tailscaled`, `cloudflared`, `ag-prediction` and `cron` are all `systemctl is-enabled` so they come back after a reboot.
3. BIOS: set "Restore on AC power loss = Power On". Consider a small UPS.
4. Temporary RDS access until Phase 2: add the new home IP `136.52.223.0/32` to `sg-07d8f1f41630dfa58`. Remove the two stale IPs.
5. Catch-up runs (same as the July migration): `ingest_futures` / `ingest_fred` with lookback argv for the gap since about 2026-09-27, `--weekly-drought`, `--weekly-yield`, the October and November WASDE (`--monthly-wasde`), and one `--weekly-fieldpulse` with `--slug`.
6. **Add dead-man monitoring that lives off-box.** This outage went unnoticed for 30 days. Use a free healthchecks.io check pinged at the end of each cron mode, plus an UptimeRobot (or Cloudflare) monitor on `https://agri-intel.rvedire.com/health`. Both email you when Victus goes silent.

### Phase 1: Stop paying for nothing (about 30 minutes, no code changes, saves ~$25/month)

1. Rescue anything unique from the zombie EC2 first. Most likely there is nothing left, since the July migration copied everything.
2. **Terminate `i-05846d4343400eadc`**, delete `vol-00aa40ca706ad0503` if it isn't deleted on termination, and **release EIP `eipalloc-0abbb6ab79f61066e`**.
3. **Deactivate, then delete, the root access key.** Do this once the EC2 is gone, since it is the key's only consumer.
4. Delete ECR repo `usda-dashboard`.

Result: about $43.60 drops to ~$18/month (RDS + 2 IPs + S3).

### Phase 2: Postgres from RDS to Victus (saves ~$21.60/month, biggest step)

1. Install Postgres **17** on Victus (PGDG apt repo, to match RDS 17.9). Bind it to `localhost` + the Tailscale interface only. In `pg_hba.conf`, allow `100.64.0.0/10` for dev-PC access over Tailscale.
2. Create role `ag_app` + database `ag_dashboard`.
3. Pre-dump: stop crons + `ag-prediction` so nothing writes.
4. Run on Victus: `pg_dump -Fc -h ag-dashboard.cvuu6ce8odqc.us-east-2.rds.amazonaws.com -U ag_app ag_dashboard > ag_dashboard.dump`, then `pg_restore -d ag_dashboard --no-owner --role=ag_app`.
5. Verify: `alembic current` = 014, plus row counts on `acreage_accuracy`, `yield_accuracy`, `price_forecasts`, `futures_daily`, `agent_runs` and `agent_picks` match RDS.
6. Point `DATABASE_URL` in the Victus `.env` at `localhost:5432`. Restart `ag-prediction`, run one dry `--weekly-fieldpulse`, and hit `/forecasts` + `/insights`.
7. Dev PC: `.env` `DATABASE_URL` uses `100.75.64.59:5432` (remember ProtonVPN blocks this, same as before).
8. Backups (RDS was doing this for you): a nightly `pg_dump -Fc` cron, 14 days kept locally, plus an off-box copy (Cloudflare R2 free tier, or another machine). **Test a restore once.**
9. Rollback window: take a manual RDS snapshot, then **stop** RDS. It auto-restarts after 7 days, so after a clean week **delete** it. Keep the final snapshot one more month (~$2), then delete it.
10. Run `apply backend/agent/sql/agent_reader_role.sql` now; it's free on a self-managed DB.

Result: ~$0.33/month (S3 only).

### Phase 3: Object storage

The constraint: the browser fetches parquet/JSON **directly** from S3 over public HTTPS with CORS. Whatever replaces S3 must be a public, CORS-enabled HTTPS endpoint, and the dashboard's *exploratory* tabs (Crops, Overview, Aquifer) will depend on it. Today only Forecasts/Insights depend on Victus.

**Recommendation: don't put public data on Victus.** Victus just went dark for 30 days. If it had been serving S3 too, the entire site would have been blank, not just the forecasts. Two good options:

- **A. Keep S3 for the ~0.4 GB public serving set** ($0.01-0.05/month after the archive cleanup). Zero code change.
- **B. Move to Cloudflare R2** at `data.rvedire.com`. Free tier (10 GB, zero egress), S3-compatible, and gets you to $0 AWS.

If you still want everything on Victus: run MinIO (or Garage) on Victus with a `data.rvedire.com` tunnel ingress, and accept that Victus becomes a whole-site SPOF.

Code work, the same for B or MinIO:
1. Frontend: replace the hardcoded `*.s3.us-east-2.amazonaws.com` URLs with one `NEXT_PUBLIC_DATA_BASE_URL` env var. Touches `utils/serviceData.ts:4,7`, `utils/overviewData.ts:20`, `app/api/data/route.ts:5`, `components/aquifer/{useBaseline,useIrrigationHistory,MethodologyStrip,AquiferMap.legacy}`.
2. Backend/pipeline: add an `S3_ENDPOINT_URL` setting in `backend/config.py` and a single `get_s3_client()` helper. Replace the ~22 direct `boto3.client("s3", ...)` sites (`main.py`, `agent/publisher.py`, `routers/agent.py`, `pipeline/upload_to_s3.py`, `build_*_aggregates.py`, `rebuild_enrichment.py`, `train*.py`, ETL scripts).
3. Models, yield caches and newsletters can simply stay on Victus local disk. The backend already loads models locally first. Newsletter files are only read through the backend proxy, so they don't need a public bucket.
4. Coordinate with the **aquifer-watch** project, which writes `aquiferwatch/`.
5. Copy: `rclone sync` the serving prefixes only. Archive `raw_legacy/`, `backups/` and `partitioned_states_demo/` to local cold storage (an external drive or a Victus data disk) before deleting them from S3.

### Phase 4: Retire the remaining AWS services (code cleanup)

| Service | Replace with | Code change |
|---|---|---|
| **Athena + Glue** | Nothing (dead code). If ad-hoc SQL is wanted later: DuckDB over local parquet in a FastAPI endpoint. | Delete `app/api/athena/**`, `utils/athenaClient.ts`, `hooks/useAthenaQuery.ts`, the 3 unused fetchers in `serviceData.ts`, and `@aws-sdk/client-athena`. Then delete the `usda-dashboard` workgroup, the Glue DB and the `athena_optimized*` prefixes. Remove any AWS keys from the Vercel env. |
| **SNS alerts** | A `notify()` shell function in `cron_runner.sh` that posts to Slack (bot token already in `.env`) + healthchecks.io ping | Replace 14 `aws sns publish` blocks. Delete the topic. |
| **SSM** | `.env` only | Drop the SSM fallback in `pipeline/quickstats_ingest.py:252-268`. Delete the parameter. |
| **IAM** | n/a | After Phases 2-4, delete `victus-ag-service` + its keys on Victus, role `EC2_USDA`, `rds-monitoring-role`, and the two `USDA-*` policies. |

### Phase 5: Docs

Update CLAUDE.md (architecture diagram, AWS table, env vars), `docs/TECHNICAL_SUMMARY.md` (cost line), `docs/cloud-architecture-*`, and the deployment memory.

---

## 4. End state

| | Today | After Phase 1 | After Phase 2 | After 3B + 4 |
|---|---:|---:|---:|---:|
| AWS monthly | $43.60 | ~$18 | ~$0.33 | $0 |
| Runs on Victus | API, cron, agent | same | + Postgres | + (optional) object store |
| Off-box dependencies | S3, RDS, Vercel, Cloudflare | same | S3, Vercel, Cloudflare | R2/S3, Vercel, Cloudflare |

Suggested order: **Phase 0 → Phase 1 (same day) → Phase 2 (one evening) → Phase 4 Athena/SNS/SSM cleanup → Phase 3 when convenient.**

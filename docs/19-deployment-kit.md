# 19 — Deployment Kit (all-AWS, click-level steps)

Everything is prepared in the repo; these are the manual clicks. Total time: ~30 minutes. Running cost: ~$6-8/month on credits, with a hard ceiling on every metered item.

## What runs where

| Piece | AWS service | Notes |
|-------|-------------|-------|
| Console (static) | S3 + CloudFront | built by `make snapshot` (zero backend mode) or `npm run build` (live mode) |
| API (full engine) | App Runner | deploys the repo Dockerfile directly from GitHub |
| Live narratives | Bedrock | server-side only, daily-capped in code (`EXPLAIN_DAILY_CAP`) |

## One-time AWS prep

1. **IAM user or role for deploys** with: S3 write on the demo bucket, App Runner full access, Bedrock invoke on the four models in the chain. Use the AWS CLI already configured on this machine.
2. Record the account ID and region (us-east-1) in your notes, never in the repo.

## Step 1: publish the container image (or let App Runner build)

App Runner can build directly from the GitHub repo (it reads `Dockerfile` at the root). In the console: App Runner → Create service → Repository type: GitHub → pick `Prakhar2025/Sentinel`, branch `main` → Deployment: automatic → Configure: CPU 1 vCPU, Memory 2 GB → Add environment variables:

```
SENTINEL_API_KEY=<generate a strong random string>
SENTINEL_ADMIN_API_KEY=<leave placeholder; admin is unused publicly>
PUBLIC_DEMO=1
EXPLAIN_DAILY_CAP=50
AWS_REGION=us-east-1
```

Bedrock credentials: create an App Runner **instance role** with `bedrock:InvokeModel` on the four model IDs; attach it at service creation. No AWS keys in env, ever — App Runner injects the role.

3. Health check path: `/healthz`. Port: 8000. Create. First deploy takes ~5 minutes; note the `*.awsapprunner.com` URL.

## Step 2: seed the public demo state

From your machine (one time, against the local seeded store being uploaded or via an ingest pass):

```
python -m sentinel.backfill --db demo-seed.db --rebuild --limit 20
```

Upload `demo-seed.db` into the container's `/app/data` by either: (a) adding a one-off App Runner shell operation, or (b) simpler for v1: commit a generation step into the image — extend the Dockerfile CMD entrypoint to run `python -m sentinel.backfill --db sentinel.db --rebuild --limit 20` when `SEED_ON_START=1` (add the flag as an env var; seeding is deterministic and takes ~90 s of container start once).

## Step 3: publish the console

Two modes, pick per audience:

- **Live mode** (talks to App Runner): `cd console`, build with `NEXT_PUBLIC_API_URL=https://<your-apprunner-url> NEXT_PUBLIC_API_KEY=<the public demo key> npx next build`, sync `.next/standalone` per Next docs or host the export.
- **Snapshot mode** (zero backend): `make snapshot`, then upload `console/out/` to S3, enable static website hosting, put CloudFront in front (free tier). Console env at build: `NEXT_PUBLIC_DEMO=1`.

## Step 4: wire the console origin

Set App Runner env `CONSOLE_ORIGIN` to the console's final HTTPS URL (CORS is scoped to exactly one origin by design). Redeploy App Runner once.

## Cost ceiling

| Meter | Ceiling |
|-------|---------|
| App Runner smallest config | ~$6-8/month while provisioned (delete service to stop) |
| S3 + CloudFront | ~$0-0.50 (free tier covers demo traffic) |
| Bedrock via explain button | 50 calls/day ≈ <$1, hard cap in code |
| Your $20/month alarm | fits with margin; credits absorb for years |

## Security checklist before going live

- [ ] `PUBLIC_DEMO=1` set (admin routes and unmask 404 structurally)
- [ ] Rate limiter active (defaults: 30 req/min/IP)
- [ ] Explain cap set and the counter file on persistent storage
- [ ] App Runner instance role grants Bedrock invoke only
- [ ] No `.env`, no keys in the repo (gitleaks in CI enforces)
- [ ] Console origin matches exactly in `CONSOLE_ORIGIN`

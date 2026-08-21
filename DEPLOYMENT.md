# Petto backend deployment safety

Railway uses `python -m app.predeploy` before releasing a deployment. The command validates the environment, applies Alembic migrations through `head`, and verifies that the database revision exactly matches the repository head. Railway then probes `/ready`, which checks both database connectivity and the migration revision.

## Required Railway variables

| Variable | Staging | Production | Purpose |
| --- | --- | --- | --- |
| `APP_ENV` | `staging` | `production` | Enables deployed-environment validation |
| `DATABASE_URL` | required | required | Runtime DB connection; transaction pooler is allowed |
| `MIGRATION_DATABASE_URL` | required | required | Direct or session-pooler DB URL; do not use port `6543` |
| `SUPABASE_URL` | required | required | Environment-specific Supabase API URL |
| `SUPABASE_KEY` | required | required | Environment-specific publishable key used with each verified user JWT for private Storage RLS |
| `GEMINI_API_KEY` | required | required | AI assessment provider credential |
| `ALLOWED_ORIGINS` | recommended | required | Comma-separated frontend origins; wildcard is rejected in production |
| `ENABLE_MOCK_DATA` | `false` | `false` | Public mock-data route must remain disabled |

### Database connection pool

| Variable | Recommended | Purpose |
| --- | --- | --- |
| `DB_POOL_SIZE` | `3` | Persistent connections per worker in direct/session mode |
| `DB_MAX_OVERFLOW` | `1` | Temporary burst connections per worker |
| `DB_POOL_TIMEOUT_SECONDS` | `10` | Maximum wait for a pooled connection |
| `DB_POOL_RECYCLE_SECONDS` | `300` | Recycle persistent connections before they become stale |
| `DB_CONNECT_TIMEOUT_SECONDS` | `10` | Fail quickly when the database cannot be reached |

Supabase pooler usernames must include the project reference, for example
`postgres.<project-ref>`. Port `5432` is session mode and uses the bounded local
pool. Port `6543` is transaction mode and delegates pooling to Supavisor. Pool
limits apply per Uvicorn worker and per Railway replica.

Never copy production data, database credentials, API keys, or Storage files into staging. Use synthetic test records only.

## Deployment checklist

- [ ] CI tests pass.
- [ ] A logical database backup and a separate Storage backup exist.
- [ ] Migrations were rehearsed on staging from the current production revision.
- [ ] Supabase security and performance advisors were reviewed.
- [ ] Railway staging variables point only to staging resources.
- [ ] `python -m app.predeploy` succeeds.
- [ ] `/health` returns HTTP 200.
- [ ] `/ready` returns HTTP 200 and reports the repository migration head.
- [ ] Authentication, pet CRUD, assessment failure behavior, and Storage upload are smoke-tested.
- [ ] Roll back if `/ready` fails, migrations do not reach head, authentication fails, or HTTP 5xx exceeds 2% for five minutes.

Schema downgrades are not an automatic rollback mechanism. Roll application code back only when it remains compatible with the migrated schema; otherwise restore into a new recovery project from the verified backup.

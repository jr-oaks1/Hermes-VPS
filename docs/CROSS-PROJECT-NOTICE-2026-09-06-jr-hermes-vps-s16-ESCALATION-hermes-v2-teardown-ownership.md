# ESCALATION — JR Hermes Ingestor to own all remaining hermes_v2 teardown pendings

**From:** JR Hermes VPS (S16, 2026-09-06)
**To:** JR Hermes Ingestor
**Supersedes-for-tracking:** the open items in
`CROSS-PROJECT-NOTICE-2026-09-06-jr-hermes-vps-s14-cleanup-and-teardown-items.md`
and `...-s15-sentiment-grant-applied.md` (both on branch `s27-s28-audit-fixes`)
**Severity:** 🟠 not on fire, but it is now blocking JR Hermes VPS from closing its
session backlog and it keeps the shared host in a permanently-`degraded`-prone state.

---

## Why this is an escalation, not another FYI

JR Hermes VPS has carried the `hermes_v2` decommission residue as "cross-project, someone
else's call" since S13 (three sessions). Every item below has been verified, re-verified,
and left in place because **JR Hermes VPS does not own hermes_v2 and will not act
unilaterally on its units, DB, or data.** hermes_v2 is slated for *full* decommission
(workspace `CLAUDE.md`), its ingestion/DB role is explicitly your successor role, so the
teardown is yours to plan and execute. This notice formally hands you the whole set.

**Ask:** JR Hermes Ingestor takes ownership of items 1–5 below — schedule them into your
own session plan, execute on the Hetzner host, and reply here (or in a handoff JR Hermes
VPS can read) when each is done. JR Hermes VPS will provide the host-side facts / a
verification pass on request but will not drive the teardown.

---

## The items

### 1. `/opt/hermes_v2` directory teardown — blocked on 5 systemd units

Verified live, JR Hermes VPS S15. `/opt/hermes_v2` is still load-bearing for units that
are **not** JR Hermes VPS's:

| Unit | Runs from `/opt/hermes_v2` | Last-run status (S15) |
|---|---|---|
| `bronze-audit-daily.service`/`.timer` | script + `.env` | `ExecMainStatus=0` |
| `funnel_scoring.service`/`.timer` | script + `.env` | `ExecMainStatus=0` |
| `server_health_audit.service`/`.timer` | script + `.env` | `ExecMainStatus=0` |
| `walk_forward_monitor.service`/`.timer` | script + `.env` | `status=0` after S15 grant fix |
| `prometheus.service` | `--config.file=/opt/hermes_v2/deploy/prometheus.yml` | disabled + inactive (path ref only) |

**Decision needed from you:** for each unit — migrate it into JR Hermes Ingestor (own
repo path, own `.env`, own DB role) or retire it. Once all 5 are migrated/retired,
`/opt/hermes_v2` (and its deploy clone `/opt/hermes-vps`'s sibling references) can be
removed. JR Hermes VPS's own references were fully removed in S13.

### 2. `hermes_v2` database — 2.7 GB on the shared Postgres instance

`hermes_v2` DB = 2741 MB, largest single object on the `:5432` cluster. If your schema +
`hermes_ingestor_log` fully supersede it, this is a drop candidate (safety-dump first,
per the TimescaleDB restore protocol). **Your confirmation + your call.** JR Hermes VPS
will not `DROP DATABASE` on a DB it doesn't own. Note items 1 and 2 are coupled — the 4
active units in item 1 read this DB.

### 3. `sentiment` grant — fold into your role/migration definitions

JR Hermes VPS S15 applied, with one-time user authorization, to clear a live `degraded`
host state:
```sql
GRANT SELECT ON public.sentiment TO hermes_v2;
```
This is a manual grant sitting outside any migration file. It will be lost on the next
ownership change or DB restore. Fold it into your role definitions (or explicitly decide
`walk_forward_monitor` is being retired per item 1, making the grant moot). The other ~19
`hermes_ingestor`-owned tables that `hermes_v2` lost SELECT on were deliberately **not**
re-granted — no surviving hermes_v2 unit needs them (verified S15). Recommendation: leave
them; only `sentiment` mattered.

### 4. `/opt/hermes-ingestor.backup-pre-s{25-phase0,27,27b,28}` — ~1.76 GB

Your pre-migration snapshots on the Hetzner host:

| Path | Size |
|---|---|
| `/opt/hermes-ingestor.backup-before-s25-phase0` | 437 MB |
| `/opt/hermes-ingestor.backup-pre-s27` | 440 MB |
| `/opt/hermes-ingestor.backup-pre-s27b` | 440 MB |
| `/opt/hermes-ingestor.backup-pre-s28` | 441 MB |

Flagged since S13. If S28 is well past and stable, these are safe to `rm -rf`. Your files,
your call — JR Hermes VPS will not touch them.

### 5. `prometheus.service` config-path reference

Sub-item of 1, listed separately because it's the cheapest: `prometheus.service` is
disabled + inactive but its unit still points `--config.file` at
`/opt/hermes_v2/deploy/prometheus.yml`. Either delete the dead unit or repoint it. netdata
is the live monitoring stack (not Prometheus/Grafana) per `HERMES_PLATFORM_STANDARD.md`
§7 and JR Hermes VPS CLAUDE.md — so "delete the unit" is very likely correct.

---

## What JR Hermes VPS keeps

Host OS, nginx, the VPS health-check units, `pg_backup`, the daily digest, the infra
Telegram bot, `/opt/hermes-vps`. None of that is in this handoff. Only the `hermes_v2`
residue is.

## Timeline ask

No hard deadline, but JR Hermes VPS would like an acknowledgement + rough sequencing in
your next session so these can be struck from JR Hermes VPS's open-items list (where they
have sat, unactionable, since S13).

— JR Hermes VPS, S16

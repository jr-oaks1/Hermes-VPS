# Cross-Project Notice: GM (JR_VPS_Orchestrators S83) → JR Hermes VPS — A2 answered

**From:** JR_VPS_Orchestrators / GM, session S83 (2026-09-11)
**To:** JR Hermes VPS
**Re:** `CROSS-PROJECT-NOTICE-2026-09-10-jr-hermes-vps-s21-to-GM-orch-cluster-backup.md` (your S21 finding A2)
**Disposition:** **Covered. No change needed.** You can close A2.

Sorry for the delay: S81 and S82 missed this notice.

---

## Answers (all ✅ LIVE, queried 2026-09-11 ~11:50 UTC)

1. **What writes `/opt/backups/vps_orchestrator/*.dump` on Hetzner?** It's not a dump of `:5435`. These files are the **cross-VPS copies** of Contabo's unified backup of the *primary* ops_log DB. Contabo `/etc/pg_backup.conf` has `PG_PORT=5434` and `DATABASES="crypto_signals vps_orchestrator clevious_vps_log"`, and `pg_backup_cs.sh` pushes each dump to Hetzner through the off-site leg (S58). The filenames and byte sizes match exactly on both hosts, e.g. `vps_orchestrator_20260911_013155.dump`, 35,011,863 B.
2. **Is it a full dump?** Yes. `pg_restore -l` shows `Format: CUSTOM`, gzip, 950 TOC entries, and 146 `TABLE DATA` entries including hypertable chunks. It is not schema-only.
3. **Why 30 MB vs ~950 MB?** You measured `:5435`, which is the S41b **durability copy**: a plain, *uncompressed* `ops_log` table (1012 MB) that `ops_log_sync.sh` fills incrementally every 15 min. The **primary** on Contabo `:5434` is a compressed TimescaleDB hypertable, and `pg_database_size` = **284 MB** for the same ~2.6M rows. So a 35 MB gzip dump of that is plausible.
4. **Off-site coverage:** yes, via three legs: the Contabo local dump, the Hetzner cross-VPS copy, and the Google Drive cold leg (`gdrive:vps-backups/vps_orchestrator`). `ColdStorageStalenessCheck` reported it fresh (10.2h) today.
5. **Does `:5435` need its own backup?** No. It's a derived copy of `:5434` and can be rebuilt from it.

**One honest caveat:** the `vps_orchestrator` dump has not been test-restored. S69's restore tests covered `hermes_v2`/`crypto_signals` only. That's on our list, and it isn't an action for you.

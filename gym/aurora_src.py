"""Read-only access to AURORA's production database (MonArk QMAP).

The DGX reaches the server through the MonArk tailnet bridge; open the tunnel
first (local port 15433 -> server 54327), then:

    python -m gym.aurora_src profile   # schema, sizes, activity, live index usage -> results/aurora/profile.json
    python -m gym.aurora_src load      # copy the current data into the DGX test database sddb_aurora

Only the read-only role `chatbot_ro` is used (read-only transactions, 15 s
statement limit). The copy reads in key-ordered chunks that each stay well
under that limit, so the production server never runs a long scan for us.
Large per-flake segmentation masks and per-chip scan logs are not copied
(they are never filtered on); every other column is. The copy stays on the
DGX; no AURORA rows enter the repository.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import psycopg

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = ROOT / "results" / "aurora"
DB = os.environ.get("SDDB_AURORA_DB", "sddb_aurora")  # lanes run on their own copies
SRC_PORT = int(os.environ.get("AURORA_TUNNEL_PORT", "15433"))
PW_FILE = Path.home() / "secrets" / "pcl_chatbot_ro_password"

# Columns copied per table (segmentation masks and chip scan logs left out).
TABLES = {
    "bulk_crystal": ["bulk_crystal_id", "material", "grower", "growth_date", "batch_id", "created_at",
                     "updated_at", "growth_parameters"],
    "wafer": ["wafer_id", "manufacturer", "lot_batch_id", "substrate_material", "oxide_material",
              "measured_oxide_thickness", "created_at", "updated_at"],
    "tray": ["tray_id", "grid_x", "grid_y", "current_location", "created_at", "updated_at"],
    "chip": ["chip_id", "tray_id", "current_status", "current_location", "tray_index", "row_number",
             "column_letter", "created_at", "updated_at", "exfoliation_parameters", "wafer_id",
             "bulk_crystal_id", "removed_at"],
    "image": ["image_id", "chip_id", "image_path", "meta_data", "created_at", "updated_at"],
    "image_process_info": ["image_process_info_id", "image_id", "is_processed", "flake_detector_settings",
                           "created_at", "updated_at"],
    "crystallite": ["crystallite_id", "x_position", "y_position", "z_position", "thickness_ai", "thickness_afm",
                    "classification_ai", "classification_h", "reviewed", "h_label_checked", "chip_id",
                    "bulk_crystal_id", "image_id", "image_process_info_id", "image_path", "bounding_box_ai",
                    "physical_dimensions", "classification_confidence_ai", "detection_confidence_ai",
                    "uncertainty_score_ai", "user_id", "user_action_at", "created_at", "updated_at", "removed_at"],
    "export_queue": ["id", "crystallite_id", "added_by", "added_at", "exported_at", "export_batch_id"],
}
CHUNK = 50_000


def src():
    return psycopg.connect(host="127.0.0.1", port=SRC_PORT, dbname="postgres", user="chatbot_ro",
                           password=PW_FILE.read_text().strip(), autocommit=True)


def dst(dbname=DB):
    sys.path.insert(0, str(ROOT))
    from sdldb.layers.config import StackConfig
    c = psycopg.connect(**StackConfig.from_env().pg_dsn(dbname), autocommit=True)
    c.execute("SET max_parallel_workers_per_gather = 0")
    c.execute("SET max_parallel_maintenance_workers = 0")
    return c


def cmd_profile(_):
    """What AURORA holds and how it is used now (pg_stat counters since the server last started)."""
    out = {}
    with src() as c:
        q = lambda s, a=None: c.execute(s, a).fetchall()
        out["server"] = dict(version=q("SHOW server_version")[0][0],
                             started=str(q("SELECT pg_postmaster_start_time()")[0][0]),
                             captured=str(q("SELECT now()")[0][0]),
                             settings={k: v for k, v in q("SELECT name, setting FROM pg_settings WHERE name IN "
                                                          "('shared_buffers','work_mem','effective_cache_size',"
                                                          "'random_page_cost','maintenance_work_mem')")})
        out["tables"] = {t: dict(rows_est=n, total_mb=round(tot / 2**20, 1), heap_mb=round(h / 2**20, 1))
                         for t, n, tot, h in q(
            "SELECT c.relname, c.reltuples::bigint, pg_total_relation_size(c.oid), pg_relation_size(c.oid) "
            "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
            "WHERE n.nspname='public' AND c.relkind='r'")}
        out["table_usage"] = {t: dict(seq_scan=s, idx_scan=i, ins=a, upd=u)
                              for t, s, i, a, u in q(
            "SELECT relname, seq_scan, idx_scan, n_tup_ins, n_tup_upd FROM pg_stat_user_tables "
            "WHERE schemaname='public'")}
        out["index_usage"] = [dict(table=t, index=ix, scans=s, tuples_read=r, size_mb=round(z / 2**20, 1), definition=d)
                              for t, ix, s, r, z, d in q(
            "SELECT s.relname, s.indexrelname, s.idx_scan, s.idx_tup_read, pg_relation_size(s.indexrelid), "
            "pg_get_indexdef(s.indexrelid) FROM pg_stat_user_indexes s WHERE s.schemaname='public' "
            "ORDER BY s.relname, s.idx_scan DESC")]
        out["activity"] = dict(
            chips_per_month={str(m): n for m, n in q("SELECT date_trunc('month',created_at)::date, count(*) FROM chip GROUP BY 1 ORDER BY 1")},
            images_per_month={str(m): n for m, n in q("SELECT date_trunc('month',created_at)::date, count(*) FROM image GROUP BY 1 ORDER BY 1")},
            images_last_30d=q("SELECT count(*), count(DISTINCT chip_id) FROM image WHERE created_at > now()-interval '30 days'")[0],
        )
        out["content"] = dict(
            materials={m: n for m, n in q("SELECT material, count(*) FROM bulk_crystal GROUP BY 1")},
            classification_ai={str(k): n for k, n in q("SELECT classification_ai, count(*) FROM crystallite GROUP BY 1")},
            review_state={f"reviewed={a},checked={b}": n for a, b, n in
                          q("SELECT reviewed, h_label_checked, count(*) FROM crystallite GROUP BY 1,2")},
            export_queue=q("SELECT count(*), count(exported_at) FROM export_queue")[0],
        )
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "profile.json").write_text(json.dumps(out, indent=1, default=str))
    print(json.dumps({k: out[k] for k in ("server", "tables")}, indent=1, default=str))


DDL_TYPES = {"USER-DEFINED": "text", "ARRAY": "text[]"}


def cmd_load(a):
    with dst("postgres") as c:
        if not c.execute("SELECT 1 FROM pg_database WHERE datname=%s", (DB,)).fetchone():
            c.execute(f"CREATE DATABASE {DB}")
    t_all = time.time()
    report = {}
    with src() as s, dst() as d:
        for t, cols in TABLES.items():
            types = dict(s.execute("SELECT column_name, data_type FROM information_schema.columns "
                                   "WHERE table_schema='public' AND table_name=%s", (t,)).fetchall())
            d.execute(f"DROP TABLE IF EXISTS {t} CASCADE")
            d.execute(f"CREATE TABLE {t} (" + ", ".join(
                f"{col} {DDL_TYPES.get(types[col], types[col])}" for col in cols) + ")")
            key, last, n, t0 = cols[0], None, 0, time.time()
            sel = ", ".join(f"{col}::text" if types[col] == "USER-DEFINED" else col for col in cols)
            while True:
                where = f"WHERE {key} > %s" if last else ""
                rows = s.execute(f"SELECT {sel} FROM {t} {where} ORDER BY {key} LIMIT {CHUNK}",
                                 (last,) if last else None).fetchall()
                if not rows:
                    break
                with d.cursor() as cur, cur.copy(f"COPY {t} ({', '.join(cols)}) FROM STDIN") as cp:
                    for r in rows:
                        cp.write_row([json.dumps(v) if isinstance(v, (dict, list)) else v for v in r])
                last, n = rows[-1][0], n + len(rows)
                if len(rows) < CHUNK:
                    break
                if n % 500_000 == 0:
                    print(t, n, round(time.time() - t0, 1), "s", flush=True)
            d.execute(f"ALTER TABLE {t} ADD PRIMARY KEY ({key})")
            report[t] = dict(rows=n, copy_s=round(time.time() - t0, 1))
            print(t, report[t], flush=True)
        d.execute("VACUUM ANALYZE")
        report["db_size"] = d.execute("SELECT pg_size_pretty(pg_database_size(%s))", (DB,)).fetchone()[0]
    report["total_s"] = round(time.time() - t_all, 1)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "load_report.json").write_text(json.dumps(report, indent=1))
    print(json.dumps(report))


def main():
    p = argparse.ArgumentParser()
    s = p.add_subparsers(dest="cmd", required=True)
    s.add_parser("profile")
    s.add_parser("load")
    a = p.parse_args()
    {"profile": cmd_profile, "load": cmd_load}[a.cmd](a)


if __name__ == "__main__":
    main()

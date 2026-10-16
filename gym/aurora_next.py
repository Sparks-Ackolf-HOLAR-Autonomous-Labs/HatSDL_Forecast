"""SIMULATED projection of AURORA's planned stacking, device and transport records (E3c).

AURORA's database today ends at exfoliated flakes (crystal -> chip -> tile -> flake, with the
exfoliation settings of each chip). The facility's later workflow steps (stacking, device
fabrication, cryogenic transport) have no tables yet. To exercise questions that span the whole
loop, this module writes a clearly labelled simulated projection of those steps into a separate
schema `aurora_next` of the DGX copy. Every simulated stack is built from REAL AURORA flakes
(graphite monolayers for the twisted bilayer, real hBN flakes for encapsulation), so the joins
back to source crystals and exfoliation settings run on real rows. Only the downstream outcomes
are simulated. Nothing here is a measurement, and nothing is written to AURORA's server.

Generation rules (fixed seed, so the projection is the same in every run):
  - stack: tear-and-stack or cut-and-stack of one graphite monolayer; target twist from a grid
    around the magic angle; measured mean twist = target + relaxation offset + noise; twist
    inhomogeneity grows with flake area (bubbles), pickup temperature and cut-and-stack is lower.
  - device: 1-2 per stack; hall bar, dual-gated hall bar or van der Pauw geometry.
  - transport run: 1-3 cooldowns per device. A correlated-insulator signature appears with a
    probability that peaks when the measured twist is within about 0.1 deg of 1.08 deg and falls
    with twist inhomogeneity; superconductivity additionally needs base temperature < 1 K and is
    more likely with a graphite gate. Source quality: natural graphite 1.0, synthetic graphite
    rods 0.75 (an assumption, not an AURORA result).

    python -m gym.aurora_next build     # (re)create schema aurora_next in sddb_aurora
    python -m gym.aurora_next summary   # also build the chip x layer-class aggregate (E3c db=summary)
"""
from __future__ import annotations

import argparse
import math
import random
import time

from gym.aurora_src import dst

SCHEMA = "aurora_next"
TWISTS = [0.8, 0.95, 1.0, 1.05, 1.1, 1.15, 1.2, 1.3, 1.5]
SOURCE_Q = {"graphite": 1.0, "Graphite rods": 0.75, "HOPG": 0.9}
COST_PER_FAB_HOUR = 120.0     # USD, technician + tool time (assumption)
COST_PER_CRYO_HOUR = 60.0     # USD, helium and instrument time (assumption)


def build(n_stacks=420, seed=7):
    c = dst()
    c.execute("SET statement_timeout = '600s'")
    r = random.Random(seed)
    flakes = c.execute(
        "SELECT cr.crystallite_id, b.material, cr.chip_id, ((cr.physical_dimensions->>'area_um2')::numeric)::float, "
        "ch.exfoliation_parameters->>'sample_pressure_kpa', ch.exfoliation_parameters->>'heat_to_temperature_c' "
        "FROM crystallite cr JOIN bulk_crystal b USING (bulk_crystal_id) JOIN chip ch USING (chip_id) "
        "WHERE b.material IN ('graphite','Graphite rods','HOPG') AND cr.classification_ai='monolayer' "
        "AND cr.removed_at IS NULL AND (cr.physical_dimensions->>'area_um2') IS NOT NULL "
        "AND ((cr.physical_dimensions->>'area_um2')::numeric) > 150").fetchall()
    hbn = [x[0] for x in c.execute(
        "SELECT cr.crystallite_id FROM crystallite cr JOIN bulk_crystal b USING (bulk_crystal_id) "
        "WHERE b.material='hBN' AND cr.classification_ai IN ('thick','trilayer') AND cr.removed_at IS NULL "
        "AND ((cr.physical_dimensions->>'area_um2')::numeric) > 400 LIMIT 5000")]
    c.execute(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE")
    c.execute(f"CREATE SCHEMA {SCHEMA}")
    c.execute(f"COMMENT ON SCHEMA {SCHEMA} IS 'SIMULATED projection of AURORA stacking/device/transport (E3c); not measurements'")
    c.execute(f"""CREATE TABLE {SCHEMA}.stack (
        stack_id text PRIMARY KEY, graphene_flake_id uuid NOT NULL, hbn_top_flake_id uuid, hbn_bottom_flake_id uuid,
        method text, target_twist_deg float, measured_twist_deg float, twist_inhomogeneity_deg float,
        pickup_temp_c float, graphite_gate bool, fab_hours float, created_at timestamptz)""")
    c.execute(f"""CREATE TABLE {SCHEMA}.device (
        device_id text PRIMARY KEY, stack_id text REFERENCES {SCHEMA}.stack, geometry text,
        channel_width_um float, channel_length_um float, fab_hours float, created_at timestamptz)""")
    c.execute(f"""CREATE TABLE {SCHEMA}.transport_run (
        run_id text PRIMARY KEY, device_id text REFERENCES {SCHEMA}.device, cooldown int, base_temperature_k float,
        correlated_insulator bool, superconducting bool, tc_k float, cryostat_hours float, cost_usd float,
        created_at timestamptz)""")
    stacks, devices, runs = [], [], []
    t0 = 1.80e9
    picks = r.sample(flakes, min(n_stacks, len(flakes)))
    for i, (fid, mat, chip, area, sp, ht) in enumerate(picks):
        method = r.choice(["tear-and-stack", "tear-and-stack", "cut-and-stack"])
        target = r.choice(TWISTS)
        pickup = r.choice([90.0, 110.0, 120.0])
        inhom = 0.02 + 0.00012 * min(area, 1500) + 0.0008 * (pickup - 90) + (0.0 if method == "cut-and-stack" else 0.03)
        inhom = max(0.01, inhom * r.lognormvariate(0, 0.35))
        measured = target - 0.04 + r.gauss(0, 0.05)  # relaxation toward smaller angle
        gate = r.random() < 0.5
        sfab = r.uniform(10, 26)
        sid = f"stk-{i:04d}"
        created = t0 + i * 3600 * 18
        stacks.append((sid, fid, r.choice(hbn) if hbn else None, r.choice(hbn) if hbn else None, method, target,
                       round(measured, 3), round(inhom, 3), pickup, gate, round(sfab, 1), created))
        q = SOURCE_Q.get(mat, 0.8)
        for d in range(r.choice([1, 1, 2])):
            geom = r.choice(["hall bar", "dual-gated hall bar", "van der Pauw"])
            did = f"{sid}-d{d}"
            dfab = r.uniform(6, 12) + (3 if geom == "dual-gated hall bar" else 0)
            devices.append((did, sid, geom, round(r.uniform(1, 3), 2), round(r.uniform(2, 8), 2), round(dfab, 1),
                            created + 86400 * 3))
            # device-level quality: local twist sampled within the inhomogeneity
            local = measured + r.gauss(0, inhom)
            peak = math.exp(-((local - 1.08) / 0.09) ** 2)
            p_ci = 1.8 * q * peak * math.exp(-inhom / 0.12) * (1.1 if geom == "dual-gated hall bar" else 0.85)
            for k in range(r.choice([1, 2, 2, 3])):
                base = r.choice([0.02, 0.3, 1.6])
                ci = r.random() < min(0.95, p_ci)
                p_sc = (0.55 * p_ci * (1.4 if gate else 1.0)) if base < 1 else 0.0
                sc = ci and r.random() < min(0.9, p_sc / max(p_ci, 1e-6))
                hours = {0.02: 48, 0.3: 24, 1.6: 10}[base] * r.uniform(0.8, 1.3)
                runs.append((f"{did}-c{k}", did, k, base, ci, sc, round(r.uniform(0.5, 3.0), 2) if sc else None,
                             round(hours, 1), round(hours * COST_PER_CRYO_HOUR, 0), created + 86400 * (7 + 4 * k)))
    with c.cursor() as cur:
        cur.executemany(f"INSERT INTO {SCHEMA}.stack VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,to_timestamp(%s))", stacks)
        cur.executemany(f"INSERT INTO {SCHEMA}.device VALUES (%s,%s,%s,%s,%s,%s,to_timestamp(%s))", devices)
        cur.executemany(f"INSERT INTO {SCHEMA}.transport_run VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,to_timestamp(%s))", runs)
    for t in ("stack", "device", "transport_run"):
        c.execute(f"ANALYZE {SCHEMA}.{t}")
    print(f"aurora_next: {len(stacks)} stacks, {len(devices)} devices, {len(runs)} transport runs "
          f"(from {len(flakes)} real graphite monolayers, {len(hbn)} real hBN flakes)")


def summary():
    """The self-driving action for E3c: a chip x layer-class aggregate of the 6.2 M-flake table."""
    c = dst()
    c.execute("SET statement_timeout = '600s'")
    t = time.perf_counter()
    c.execute("DROP TABLE IF EXISTS sddb_chip_class_counts")
    c.execute("""CREATE TABLE sddb_chip_class_counts AS
        SELECT chip_id, bulk_crystal_id, classification_ai, count(*) AS n,
               percentile_cont(0.5) WITHIN GROUP (ORDER BY ((physical_dimensions->>'area_um2')::numeric)) AS median_area_um2
        FROM crystallite WHERE removed_at IS NULL GROUP BY 1, 2, 3""")
    c.execute("CREATE INDEX ON sddb_chip_class_counts (bulk_crystal_id)")
    c.execute("ANALYZE sddb_chip_class_counts")
    n = c.execute("SELECT count(*) FROM sddb_chip_class_counts").fetchone()[0]
    print(f"sddb_chip_class_counts: {n} rows, built in {time.perf_counter() - t:.1f} s")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("cmd", choices=["build", "summary"])
    a = p.parse_args()
    build() if a.cmd == "build" else summary()


if __name__ == "__main__":
    main()

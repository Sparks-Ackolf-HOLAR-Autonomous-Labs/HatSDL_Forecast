"""Connection settings for the stack started by stack/stackctl.sh.

Values come from environment variables, falling back to the defaults of
stackctl.sh; passwords are read from the stack's secrets.env (never from the
repository).
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

STACK = Path(os.environ.get("SDLDB_STACK", Path.home() / "monster_blood" / "sdldb_stack"))


def _secrets():
    f = Path(os.environ.get("SDLDB_SECRETS", STACK / "secrets.env"))
    out = {}
    if f.exists():
        for line in f.read_text().splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip()
    return out


@dataclass
class StackConfig:
    pg_host: str = "127.0.0.1"
    pg_port: int = 55432
    pg_user: str = "sdldb"
    pg_password: str = ""
    s3_endpoint: str = "http://127.0.0.1:38333"
    s3_key: str = ""
    s3_secret: str = ""
    raw_bucket: str = "sdldb-raw"
    lake_bucket: str = "sdldb-lake"
    neo4j_uri: str = "bolt://127.0.0.1:57687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = ""

    @classmethod
    def from_env(cls):
        s = {**_secrets(), **os.environ}
        return cls(pg_host=s.get("SDLDB_PG_HOST", cls.pg_host), pg_port=int(s.get("SDLDB_PG_PORT", cls.pg_port)),
                   pg_password=s.get("SDLDB_PG_PASSWORD", ""),
                   s3_endpoint=s.get("SDLDB_S3_ENDPOINT", cls.s3_endpoint),
                   s3_key=s.get("SDLDB_S3_KEY", ""), s3_secret=s.get("SDLDB_S3_SECRET", ""),
                   neo4j_uri=s.get("SDLDB_NEO4J_URI", cls.neo4j_uri),
                   neo4j_password=s.get("SDLDB_NEO4J_PASSWORD", ""))

    def pg_dsn(self, dbname="postgres"):
        return dict(host=self.pg_host, port=self.pg_port, user=self.pg_user, password=self.pg_password,
                    dbname=dbname)

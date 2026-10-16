#!/usr/bin/env bash
# Build and start the PostgreSQL 16 server the experiments ran on, in user space (no root, no Docker),
# with the settings of the runs: port 55432, user sdldb, shared_buffers 512MB, max_connections 50,
# listening on 127.0.0.1 only. The password is random, written to $SDLDB_STACK/secrets.env (mode 600)
# and read from there by sdldb/layers/config.py; it is never printed.
#
#   export SDLDB_STACK=$HOME/sddb_stack      # anywhere outside this folder
#   bash stack/postgres_setup.sh             # build (about 5 min), initialise, start
#   bash stack/postgres_setup.sh stop
set -euo pipefail
ROOT=${SDLDB_STACK:?set SDLDB_STACK to a directory outside this folder}
PGV=16.10; PORT=55432
PG=$ROOT/pg/bin; D=$ROOT/data/pg; L=$ROOT/logs
if [ "${1:-}" = stop ]; then "$PG/pg_ctl" -D "$D" stop; exit; fi
mkdir -p "$ROOT"/{src,logs,data}
if [ ! -x "$PG/postgres" ]; then
  cd "$ROOT/src"
  [ -f postgresql-$PGV.tar.bz2 ] || curl -fsSLO https://ftp.postgresql.org/pub/source/v$PGV/postgresql-$PGV.tar.bz2
  tar xjf postgresql-$PGV.tar.bz2
  (cd postgresql-$PGV && ./configure --prefix="$ROOT/pg" --without-readline --without-icu --without-openssl >"$L/configure.log" \
     && make -j"$(nproc)" >"$L/make.log" 2>&1 && make install >>"$L/make.log" 2>&1)
fi
if [ ! -f "$ROOT/secrets.env" ]; then
  umask 077
  echo "SDLDB_PG_PASSWORD=$(python3 -c 'import secrets; print(secrets.token_hex(16))')" > "$ROOT/secrets.env"
fi
if [ ! -f "$D/PG_VERSION" ]; then
  pw=$(mktemp); grep '^SDLDB_PG_PASSWORD=' "$ROOT/secrets.env" | cut -d= -f2- | tr -d '\n' > "$pw"
  "$PG/initdb" -D "$D" -U sdldb --pwfile="$pw" -A scram-sha-256 >"$L/initdb.log"; rm -f "$pw"
  cat >>"$D/postgresql.conf" <<CONF
listen_addresses = '127.0.0.1'
port = $PORT
shared_buffers = 512MB
max_connections = 50
CONF
fi
"$PG/pg_isready" -q -h 127.0.0.1 -p $PORT || "$PG/pg_ctl" -D "$D" -l "$L/postgres.log" -w start
echo "PostgreSQL $PGV on 127.0.0.1:$PORT (user sdldb, password in $ROOT/secrets.env)"

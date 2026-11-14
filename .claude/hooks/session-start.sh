#!/bin/bash
# SessionStart hook (Claude Code on the web only — see CLAUDE_CODE_REMOTE guard below).
# Gets a fresh remote sandbox ready to both develop this project AND answer data questions
# straight from R2 without any manual setup:
#   - `uv sync` so extract.py, load_duckdb.py and the scripts have their deps.
#   - `rclone` installed + configured against an `r2:` remote from this environment's
#     R2_ACCESS_KEY/R2_SECRET_ACCESS_KEY/R2_ENDPOINT env vars, with a wrapper that works
#     around a bug in the apt-packaged rclone (see below).
#   - With FM_R2_REMOTE set (e.g. `r2:my-bucket`, a non-secret environment variable):
#       * the user's gitignored fmm.toml, CAREER.md, career-notes/ and fmstats/known_answers/
#         pulled from `<remote>/config/` (the canonical copy) on every start, so a cloud session
#         knows the career a laptop does;
#       * DuckDB's `httpfs` extension pre-placed from a copy vendored in the bucket, so a session
#         can `ATTACH 's3://<bucket>/site-data/fm-<career>.duckdb'` immediately — see
#         docs/agent-context/remote-duckdb-access.md for the exact ATTACH syntax.
#
# All of this is best-effort: an environment without R2 creds or FM_R2_REMOTE still starts up
# fine, it just skips those steps.
set -uo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd "$CLAUDE_PROJECT_DIR" || exit 0

# --- Python deps ---------------------------------------------------------------------------
uv sync

# --- rclone + the r2: remote ----------------------------------------------------------------
if [ ! -x /usr/bin/rclone ]; then
  apt-get update -qq && apt-get install -y -qq rclone
fi

# The apt-packaged rclone (1.60.1) throws LoadCustomCABundleError if AWS_CA_BUNDLE is set
# alongside a proxied HTTP transport (this sandbox's egress proxy sets it). Go's TLS stack
# already trusts the proxy CA via SSL_CERT_FILE, so a wrapper that drops just that one env var
# fixes it without touching the CA trust itself. /usr/local/bin precedes /usr/bin on PATH.
cat > /usr/local/bin/rclone << 'WRAP'
#!/bin/bash
exec env -u AWS_CA_BUNDLE /usr/bin/rclone "$@"
WRAP
chmod +x /usr/local/bin/rclone

if [ -n "${R2_ACCESS_KEY:-}" ] && [ -n "${R2_SECRET_ACCESS_KEY:-}" ] && [ -n "${R2_ENDPOINT:-}" ]; then
  mkdir -p ~/.config/rclone
  cat > ~/.config/rclone/rclone.conf << EOF
[r2]
type = s3
provider = Cloudflare
access_key_id = ${R2_ACCESS_KEY}
secret_access_key = ${R2_SECRET_ACCESS_KEY}
endpoint = ${R2_ENDPOINT}
acl = private
no_check_bucket = true
EOF

fi

REMOTE="${FM_R2_REMOTE:-}"
if [ -n "$REMOTE" ] && [ -f ~/.config/rclone/rclone.conf ]; then
  # --- The user's own settings (gitignored; the bucket's copy is canonical) ----------------
  # Pulled on EVERY start, not only when missing: a container can carry a copy from an older
  # session, and a store built from a stale fmm.toml publishes the wrong career settings. A
  # local copy that differed is kept beside it as <file>.replaced (scripts/config_sync.py).
  FM_R2_REMOTE="$REMOTE" uv run python scripts/config_sync.py pull >/dev/null 2>&1

  # --- Vendor the DuckDB httpfs extension from the bucket ----------------------------------
  # INSTALL httpfs needs extensions.duckdb.org, which a network-restricted sandbox may block
  # outright — and even once that host is allowlisted over HTTPS, DuckDB's installer requests
  # a PLAIN HTTP url by default, which can still 403 on a host+scheme-specific policy. Fetching
  # our own pre-vendored copy from R2 (the one host we already know this project can reach)
  # sidesteps both problems entirely. Re-vendor with:
  #   uv run python -c "import duckdb; print(duckdb.__version__)"     # -> <v>
  #   rclone copyto ~/.duckdb/extensions/v<v>/linux_amd64/httpfs.duckdb_extension \
  #     $FM_R2_REMOTE/vendor/duckdb-extensions/v<v>/linux_amd64/httpfs.duckdb_extension
  # (only needed again if the project's duckdb version bumps).
  DUCKDB_V=$(uv run python -c "import duckdb; print(duckdb.__version__)" 2>/dev/null)
  if [ -n "$DUCKDB_V" ]; then
    EXT_DIR="$HOME/.duckdb/extensions/v${DUCKDB_V}/linux_amd64"
    if [ ! -f "$EXT_DIR/httpfs.duckdb_extension" ]; then
      mkdir -p "$EXT_DIR"
      rclone copyto "$REMOTE/vendor/duckdb-extensions/v${DUCKDB_V}/linux_amd64/httpfs.duckdb_extension" \
        "$EXT_DIR/httpfs.duckdb_extension" 2>/dev/null
    fi
  fi
fi

exit 0

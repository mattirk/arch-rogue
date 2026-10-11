# Relay deployment — ar.rita-kasari.fi

The Odin relay (`tools/relay/`) replaces the archived Python relay on the
same host. It deploys through `.github/workflows/server-deploy.yml` in this
private repository: a GitHub-hosted job builds and tests a fully static
`archrogue_relay` binary, then the self-hosted runner `arch-rogue-server-1`
(which *is* the production host) installs it as a systemd **user** unit.
The runner must never be registered on the public mirror; if this repository
ever goes public, delete the workflow and deregister the runner first.

## Topology

```
game clients ──wss://ar.rita-kasari.fi/mp──▶ nginx (TLS, port 443)
                                              │  plaintext ws, loopback
                                              ▼
                                   archrogue_relay --bind 127.0.0.1 --port $PORT
```

- The relay has no TLS listener, certificate, or key (MULTIPLAYER.md D2).
- `GET /healthz` answers `200 ok` with no room or player data.
- Browser clients present an `Origin`; the relay accepts only the
  `ORIGINS` allowlist (comma-separated). Native clients send no Origin.

## Triggers

- Push to `master` touching `tools/relay/**`, `src/net_protocol/**`,
  `vendor/libwebsockets/**`, or the workflow itself.
- Manual `workflow_dispatch` with an optional `ref` to roll back to any
  commit beyond the on-disk history.

## What a deploy does

1. **Build job (GitHub-hosted):** pinned Odin from `toolchain.properties`,
   `./build.sh relay-test`, then `./build.sh relay -extra-linker-flags:-static`
   (static: no glibc coupling to the host), smoke-starts the binary and curls
   `/healthz`, uploads the binary plus `tools/relay/deploy/`.
2. **Deploy job (self-hosted runner):** downloads the artifact into
   `~/arch-rogue-relay/releases/<timestamp>-<sha>/`, writes
   `~/arch-rogue-relay/env` from the GitHub Environment **`ar-rita-kasari-fi`**
   variables `PORT`, `ORIGINS` (optional; default
   `https://mattirk.github.io`) and `MAX_ROOMS` (optional; default 128),
   (per-source caps default to 8 connections and 4 open rooms per client
   address, and an empty room expires after 30 minutes; override with
   `--max-conns-per-source`, `--max-rooms-per-source`, `--waiting-max-s` in
   the unit's `ExecStart` if ever needed),
   installs/enables `arch-rogue-relay.service`, flips the `current` symlink,
   restarts the unit, and probes `http://127.0.0.1:$PORT/healthz` for 10 s.
   On failure it prints the journal tail, flips back to the previous release,
   restarts, and fails the job. The five newest releases are kept.
3. The first successful deploy also stops and disables the old Python unit
   `arch-rogue-server` if it exists.

## Protecting the deploy path (required GitHub settings)

The deploy job runs on the production host, so these settings in the private
repository are part of the security boundary (security audit 2026-10-11,
finding 5). They cannot be expressed in the workflow file itself:

- Environment **`ar-rita-kasari-fi`** → *Deployment branches and tags*:
  **Selected branches** = `master` only. Without it, a `workflow_dispatch`
  from any branch with write access would run that branch's workflow file on
  the host. (The workflow additionally refuses to deploy unless
  `github.ref` is `master`.)
- Environment → *Required reviewers*: at least one, so a deploy needs a
  second click even from master.
- Branch protection on `master`: no force-pushes, no deletions.
- The self-hosted runner label `arch-rogue-server-1` must exist only on that
  host, and the runner must not be registered at organization level.

Remaining hardening that needs root on the host and is not yet done: run the
relay as its own system user (a system unit with `User=archrogue-relay` and a
root-owned release directory, the runner restricted to a narrow `sudo
systemctl restart arch-rogue-relay`), so that a relay compromise cannot reach
the runner's credentials. Today both share the runner's account; the user
unit's sandbox directives (`arch-rogue-relay.service`) limit what a
compromised relay can do with the filesystem, kernel, and network but not
which Unix user it is.

## Log retention (privacy policy commitment)

`website/privacy.html` promises that player IP addresses are not access-logged
and that anything the web server or system journal records on failures is
deleted within 30 days. The nginx config turns `access_log off` for `/mp` and
`/healthz`; the host must also bound the two remaining sinks (root, once):

```bash
# journald (relay unit output, sshd, etc.)
sudo mkdir -p /etc/systemd/journald.conf.d
printf '[Journal]\nMaxRetentionSec=30day\nSystemMaxUse=500M\n' | \
  sudo tee /etc/systemd/journald.conf.d/retention.conf
sudo systemctl restart systemd-journald
# nginx error log: default logrotate is weekly x 4 rotations (<= 28 days);
# verify /etc/logrotate.d/nginx says "weekly" and "rotate 4" or tighter.
grep -E 'weekly|daily|rotate' /etc/logrotate.d/nginx
```

The relay process itself logs connection counts, close codes, and room codes
only; it never logs addresses, names, tokens, or payloads (see
`tools/relay/core/hub.odin` `logf` call sites).

## One-time host provisioning (root)

1. Lingering for the runner user, so `systemctl --user` works without a login
   session (already done for the Python relay):
   `sudo loginctl enable-linger <runner-user>`
2. Make sure `curl` is installed (the health probe uses it).
3. Reverse proxy: copy `nginx-ar.rita-kasari.fi.conf` to
   `/etc/nginx/conf.d/`, replace `RELAY_PORT` with the Environment's `PORT`,
   check the certificate paths (the existing Let's Encrypt lineage used by
   the old `stream` block can be reused), open 443 in the firewall, then
   `sudo nginx -t && sudo systemctl reload nginx`.
4. Remove the old `stream { listen 43666 ssl; ... }` block once the Odin
   clients are the only users, and close 43666 in the firewall.
5. On the GitHub Environment `ar-rita-kasari-fi`: keep `PORT`; add
   `ORIGINS` if the web build is served from anywhere besides
   `https://mattirk.github.io` (local web testing against the live relay
   needs e.g. `http://127.0.0.1:8090` added — or run a local relay instead).
   `SERVER` is no longer read.

## Verifying

```bash
curl -i https://ar.rita-kasari.fi/healthz            # 200 ok
# from a checkout, two bots over the real network:
build/coop_bot --role host --url wss://ar.rita-kasari.fi/mp --code-file /tmp/code --seconds 20 &
build/coop_bot --role join --url wss://ar.rita-kasari.fi/mp --code-file /tmp/code --seconds 20
```

Management on the host: `systemctl --user status arch-rogue-relay`,
`journalctl --user -u arch-rogue-relay -f`. Logs are metadata only (room
codes, connection ids, close codes, rejection reasons); never tokens, names
in bulk, or payloads.

## Manual rollback

```bash
ls ~/arch-rogue-relay/releases/
ln -sfn ~/arch-rogue-relay/releases/<older> ~/arch-rogue-relay/current
systemctl --user restart arch-rogue-relay
```

# Relay Server Deployment

The multiplayer relay (`server/`, stdlib-only, plain TCP behind the nginx
stream TLS proxy) deploys automatically through GitHub Actions:
`.github/workflows/deploy-server.yml` runs on every master push that touches
`server/**` or `src/arch_rogue_protocol/**` (or via manual dispatch), gates on
the relay test modules, then deploys on the self-hosted runner
`arch-rogue-server-1`.

## How a deploy works

1. The runner copies `server/` and `src/arch_rogue_protocol/` into
   `~/arch-rogue-relay/releases/<timestamp>-<sha>` (the layout mirrors the repo
   root because `server/protocol.py` resolves the codec at
   `<root>/src/arch_rogue_protocol`).
2. `~/arch-rogue-relay/env` is rewritten from the `PORT` and `SERVER`
   variables of the GitHub Environment **`ar-rita-kasari-fi`** (the deploy job
   declares `environment: ar-rita-kasari-fi` and maps them via
   `${{ vars.PORT }}`/`${{ vars.SERVER }}`) — these become the relay's startup
   parameters `--port`/`--host` via the systemd unit.
3. The `~/arch-rogue-relay/current` symlink flips to the new release and
   `systemctl --user restart arch-rogue-server` runs.
4. A TCP probe (`server/deploy/probe_port.py`) must connect to
   `127.0.0.1:$PORT` within 10 s; otherwise the workflow prints the journal
   tail, flips `current` back to the previous release, restarts, and fails.
5. The five newest releases are kept for manual rollback (`ln -sfn <release>
   ~/arch-rogue-relay/current && systemctl --user restart arch-rogue-server`).

Relay deploys are decoupled from game releases: the relay forwards gameplay
payloads verbatim and clients pair by their own `content_revision`. A restart
only drops in-flight rooms, which the client reconnect grace absorbs.

## One-time host provisioning

As the GitHub Actions runner user on `arch-rogue-server-1`:

```bash
mkdir -p ~/.config/systemd/user ~/arch-rogue-relay/releases
cp server/deploy/arch-rogue-server.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable arch-rogue-server
loginctl enable-linger "$USER"   # relay survives logout/reboot
```

Requirements: `python3` on PATH, the GitHub Environment `ar-rita-kasari-fi`
defining the variables `PORT` and `SERVER` (Settings → Environments →
ar-rita-kasari-fi → Environment variables), and nginx already proxying TLS to
`$SERVER:$PORT`. The unit is a *user* unit — `systemctl --user`/`journalctl
--user -u arch-rogue-server` are the management commands. The first start will
fail harmlessly until the first deploy has created
`~/arch-rogue-relay/{env,current}`.

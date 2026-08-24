# Licensed runtime sound effects

The WAV files used by Arch Rogue come from a commercially licensed third-party
library. They are not covered by this repository's Apache-2.0 license.

The private canonical repository contains the curated runtime WAVs. The public
source snapshot deliberately contains only this file and `manifest.json`; it
must never contain the purchased source pack, individual runtime WAVs, or a
runtime SFX bundle.

The game degrades safely to silence when the files are absent. Source checking
and native compilation work without them. The complete test/release pipeline
requires an authorized injection because audio integrity tests reject partial
or modified sets.

## If you own the source asset pack

Generate the curated runtime set directly from your local purchase:

```bash
python3 tools/import_licensed_sfx.py \
  --source "/path/to/licensed-sfx-source"
python3 tools/sfx_bundle.py verify
```

The importer requires `ffmpeg`. It uses the explicit source mapping and duration
policy in `tools/import_licensed_sfx.py`, then writes only game-ready PCM WAVs
under this directory.

## Inject an authorized curated set

From an existing curated directory:

```bash
python3 tools/sfx_bundle.py inject \
  --source-dir "/private/path/to/curated-sfx"
```

From the private release bundle:

```bash
python3 tools/sfx_bundle.py inject \
  --bundle "/private/path/to/arch-rogue-sfx-runtime.tar.gz"
```

Every injected filename, byte size, and SHA-256 digest must match
`manifest.json`. Archive extraction rejects links, traversal, extra files,
duplicate files, and incomplete sets.

## Create the private CI bundle

Run this only in the private canonical checkout after verifying the assets:

```bash
python3 tools/sfx_bundle.py verify
python3 tools/sfx_bundle.py create \
  --output build/arch-rogue-sfx-runtime.tar.gz
sha256sum build/arch-rogue-sfx-runtime.tar.gz
```

Store that archive in access-controlled object storage or as a private-repository
release asset. Do not commit it, upload it to a public GitHub release, or pass it
between public workflow jobs as an Actions artifact.

### Automated private GitHub Release

`.github/workflows/mirror-public.yml` owns the transport asset. On every private
`master` push it:

1. Strictly verifies all runtime WAVs.
2. Hashes the manifest and bundle tool contract.
3. Reuses the existing private asset when that contract is unchanged.
4. Otherwise creates or replaces `arch-rogue-sfx-runtime.tar.gz` on the private
   `sfx-runtime` prerelease.
5. Pushes the WAV-free public snapshot only after the private asset is current.

Public build jobs query the stable endpoint
`https://api.github.com/repos/mattirk/arch-rogue-master/releases/tags/sfx-runtime`
and resolve the current asset ID by filename. They therefore need no changing
URL or archive-checksum secret. The manifest still verifies every extracted WAV
by exact SHA-256 and size, and archive validation rejects extra or partial sets.

The only manual setup is a fine-grained token with read-only Contents access to
`mattirk/arch-rogue-master`, stored in the public repository as the complete
`ARCH_ROGUE_SFX_BUNDLE_AUTHORIZATION` value (`Bearer TOKEN`). Do not grant write,
organization, package, or unrelated repository access. See the root `README.md`
for the public Actions-secret location.

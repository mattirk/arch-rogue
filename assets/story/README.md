# MX-story authored art

This directory is the self-contained panel-art pack for story mode.

- 34 backdrops: 8 omens, 10 guest roles, 15 endings, and the Lossless Soul
- 30 named guest portraits
- 17 fixed-size icons: 10 relics and 7 panel choices
- 81 PNGs total

`manifest.json` maps the exact runtime semantic keys to canonical relative paths
and SHA-256 hashes. Runtime textures are optional and retain procedural fallback,
but the committed pack is strict: missing, extra, unreadable, wrongly sized, or
hash-stale files fail the verifier and Odin acceptance test.

From the repository root:

```bash
python tools/verify_story_assets.py
python tools/verify_story_assets.py --write-manifest
```

The second command is only for an intentional art change; review the changed PNG
and manifest hash together.

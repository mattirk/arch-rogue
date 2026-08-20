# Arch Rogue download site

This directory is the static GitHub Pages site for Arch Rogue, currently `6.0.0-alpha.21`.

## Local preview

From the repository root:

```bash
python -m http.server 8000 --directory website
```

Then open `http://localhost:8000`.

## Platform availability

- **Linux x64:** automated `.tar.gz` release archive.
- **Android:** automated signed release APK.
- **Windows and macOS:** visible as disabled **Coming soon** cards.
- **Steam:** public wishlist/store link only; it is not a download target.

## Release manifest

`downloads.json` uses schema 2. Every entry under `assets` is an object with an `available` boolean and an optional `url`:

```json
{
  "schema": 2,
  "assets": {
    "windows": { "available": false },
    "linux": { "available": true, "url": "https://github.com/..." }
  }
}
```

The committed manifest gives Linux and Android safe releases-page fallbacks for local previews. The JavaScript treats missing platform entries or missing optional URLs as partial information rather than failing the whole manifest, while unavailable entries remain disabled.

Release automation runs `tools/generate_download_manifest.py` with the version and Git commit. The generator validates the repository, SemVer version, and hexadecimal commit, shortens the commit to twelve characters, and uses the commit-addressed tag `v<version>-<sha12>`. It emits exact URLs for:

- `arch-rogue-v<version>-<sha12>-linux-x64.tar.gz`
- `Arch-Rogue.apk`

Windows and macOS are always marked unavailable and have no URL. The release tag remains commit-addressed even though the Android asset uses a stable product-facing filename, because GitHub's `/releases/latest/download/...` shortcut excludes prereleases.

GitHub repository settings must use **GitHub Actions** as the Pages source. The deployment job reports the resulting URL in the Actions summary.

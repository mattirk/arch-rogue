# Arch Rogue download site

This directory is the static GitHub Pages source for Arch Rogue `6.0.0-alpha.23`. The public site includes downloads at the Pages root and the audited browser build at [`play/`](https://mattirk.github.io/arch-rogue/play/).

## Local preview

From the repository root:

```bash
python -m http.server 8000 --directory website
```

Then open `http://localhost:8000`. The committed source does not contain generated `play/` files, so this command previews the download site only.

## Platform availability

- **Web:** the Play card uses the project-relative `href="play/"` and supports current desktop Chromium-family and Firefox browsers with WebGL2.
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

## Pages assembly

GitHub repository settings must use **GitHub Actions** as the Pages source. The canonical public workflow is authored at `tools/public-repo/workflows/build-release.yml`. It downloads the exact `arch-rogue-web` artifact already built and audited for the prerelease, copies this directory into `build/pages`, validates and strips the archive's single `arch-rogue-web/` root into `build/pages/play`, reruns `tools/web_audit.py`, and uploads `build/pages` as one Pages artifact. Generated browser files are never committed under `website/`.

The release audit measures the self-hosted Brotli-ready payload and validates content hashes, heap policy, packs, and runtime contracts. A locally assembled combined tree can exercise the deployed route with `node tools/web_smoke.mjs --dist build/pages --entry-path /play/index.html`. GitHub Pages controls its own response headers and does not promise the `.br` negotiation or immutable/no-cache policy supplied by `tools/web_serve.py`; do not present the audited Brotli wire size or local cache headers as measured Pages behavior. The deploy job retries the site-relative `play/` and `play/packs.json` routes after publication.

Browser saves use asynchronous IndexedDB site data scoped to the browser origin. Clearing site data removes them, and moving the play page to a different origin would not migrate them automatically. The deployment job reports the resulting Pages URL in the Actions summary.

# Arch Rogue download site

This directory is the static GitHub Pages site for Arch Rogue downloads. It is intentionally separate from the experimental pygbag game build in `web/`.

## Local preview

From the repository root:

```bash
python -m http.server 8000 --directory website
```

Then open `http://localhost:8000`.

## Release links

`downloads.json` is a progressive-enhancement manifest. The committed copy sends visitors to the releases page, so buttons remain useful in a local preview or before the first deployment. On every successful `master` release, `.github/workflows/build-release.yml` runs `tools/generate_download_manifest.py` with that release's version and commit, then deploys the site through GitHub Pages. The deployed manifest contains immutable, exact `browser_download_url` values for Windows, Linux, the universal macOS app, and Android.

This is preferable to GitHub's `/releases/latest/download/...` shortcut because automated Arch Rogue builds are prereleases, and prereleases are excluded from the `latest` release redirect.

GitHub repository settings must use **GitHub Actions** as the Pages source. The deployment job reports the resulting URL in the Actions summary.

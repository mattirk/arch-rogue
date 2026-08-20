from __future__ import annotations

import importlib.util
import json
import unittest
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEBSITE = ROOT / "website"


class SiteParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.platforms: list[str] = []
        self.platform_attributes: dict[str, dict[str, str | None]] = {}
        self.images: list[dict[str, str | None]] = []
        self.links: list[dict[str, str | None]] = []
        self.status_regions: int = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if values.get("data-platform"):
            platform = str(values["data-platform"])
            self.platforms.append(platform)
            self.platform_attributes[platform] = values
        if tag == "img":
            self.images.append(values)
        if tag == "a":
            self.links.append(values)
        if values.get("role") == "status" and values.get("aria-live"):
            self.status_regions += 1


def load_manifest_module():
    path = ROOT / "tools" / "generate_download_manifest.py"
    spec = importlib.util.spec_from_file_location("download_manifest", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load download manifest generator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class WebsiteTests(unittest.TestCase):
    def test_page_exposes_accessible_platform_availability(self) -> None:
        parser = SiteParser()
        parser.feed((WEBSITE / "index.html").read_text(encoding="utf-8"))
        self.assertCountEqual(parser.platforms, ["windows", "linux", "macos", "android"])
        self.assertEqual(len(parser.platforms), len(set(parser.platforms)))
        self.assertEqual(parser.status_regions, 1)
        self.assertTrue(parser.images)
        self.assertTrue(all(image.get("alt") is not None for image in parser.images))

        for platform in ("windows", "macos"):
            with self.subTest(platform=platform):
                attributes = parser.platform_attributes[platform]
                self.assertEqual(attributes.get("role"), "link")
                self.assertEqual(attributes.get("aria-disabled"), "true")
                self.assertEqual(attributes.get("tabindex"), "-1")
                self.assertIsNone(attributes.get("href"))
                self.assertIn("is-unavailable", str(attributes.get("class") or "").split())

        for platform in ("linux", "android"):
            with self.subTest(platform=platform):
                attributes = parser.platform_attributes[platform]
                self.assertIsNone(attributes.get("aria-disabled"))
                self.assertTrue(str(attributes.get("href", "")).startswith(
                    "https://github.com/mattirk/arch-rogue/releases"
                ))

        play_links = [link for link in parser.links if link.get("data-play-link") == "true"]
        self.assertEqual(len(play_links), 1)
        play = play_links[0]
        self.assertEqual(play.get("href"), "play/")
        self.assertEqual(play.get("aria-label"), "Play Arch Rogue in your browser")
        self.assertIsNone(play.get("aria-disabled"))
        self.assertIn("play-badge", str(play.get("class") or "").split())
        self.assertNotIn('href="/play/"', (WEBSITE / "index.html").read_text(encoding="utf-8"))

    def test_referenced_local_assets_exist(self) -> None:
        page = (WEBSITE / "index.html").read_text(encoding="utf-8")
        styles = (WEBSITE / "styles.css").read_text(encoding="utf-8")
        for relative_path in (
            "styles.css",
            "app.js",
            "assets/icon.png",
            # The hero shows the animated spin; the static PNG stays in
            # assets/ for capsules and external embeds (existence-only below).
            "assets/title_logo_spin.gif",
            "assets/background_title.png",
            "assets/panel.png",
            "assets/panel_inset.png",
            "assets/row.png",
            "assets/platform-windows.png",
            "assets/platform-linux.png",
            "assets/platform-macos.png",
            "assets/platform-android.png",
            "assets/platform-steam.png",
        ):
            with self.subTest(path=relative_path):
                self.assertTrue((WEBSITE / relative_path).is_file())
                self.assertIn(relative_path, page + styles)
        # Kept but intentionally unreferenced by the site itself.
        self.assertTrue((WEBSITE / "assets/title_logo.png").is_file())

    def test_site_copy_matches_current_release_contract(self) -> None:
        page = (WEBSITE / "index.html").read_text(encoding="utf-8")
        script = (WEBSITE / "app.js").read_text(encoding="utf-8")
        styles = (WEBSITE / "styles.css").read_text(encoding="utf-8")
        self.assertIn("Version 6.0.0-alpha.23", page)
        self.assertNotIn("6.0.0-alpha.21", page)
        self.assertIn("Play now", page)
        self.assertIn("Desktop WebGL2 alpha", page)
        self.assertIn(".play-glyph", styles)
        self.assertNotIn("Arch Rogue Odin", page + script)
        self.assertIn("x64 tar.gz archive", page)
        self.assertIn("Signed APK", page)
        self.assertGreaterEqual(page.count("Coming soon"), 2)
        self.assertIn("Store page only", page)
        self.assertIn('[aria-disabled="true"]', styles)
        self.assertNotIn("Descend. Adapt. Survive.", page)
        self.assertNotIn("A grim isometric action roguelike", page)
        self.assertNotIn("Build-defining loot", page)
        self.assertIn("Unique class skills", page)
        self.assertNotIn("Recommended", page + script + styles)

    def test_script_tolerates_partial_schema_2_manifests(self) -> None:
        script = (WEBSITE / "app.js").read_text(encoding="utf-8")
        self.assertIn("manifest.schema !== 2", script)
        self.assertIn("const assets = isRecord(manifest.assets) ? manifest.assets : {};", script)
        self.assertIn("asset.available === false", script)
        self.assertNotIn("Incomplete download manifest", script)
        self.assertNotIn("linked !== badges.size", script)
        self.assertNotIn("innerHTML", script)

    def test_privacy_copy_describes_only_current_features(self) -> None:
        privacy = (WEBSITE / "privacy.html").read_text(encoding="utf-8").lower()
        self.assertIn("deferred online features", privacy)
        self.assertIn("not included in the", privacy)
        self.assertIn("no telemetry", privacy)
        self.assertIn("indexeddb site data", privacy)
        self.assertIn("best-effort", privacy)
        self.assertIn("clearing site data", privacy)
        self.assertNotIn("multiplayer relay", privacy)
        self.assertNotIn("two-player co-op", privacy)
        self.assertNotIn("achievements", privacy)
        self.assertNotIn("cloud saves", privacy)
        self.assertNotIn("aggregate statistics", privacy)
        self.assertNotIn("data controller", privacy)

    def test_ember_animation_stays_compositor_friendly(self) -> None:
        styles = (WEBSITE / "styles.css").read_text(encoding="utf-8")
        self.assertIn("transform: translate3d", styles)
        self.assertIn("contain: strict", styles)
        self.assertIn("animation: ember-rise 28s linear infinite", styles)
        self.assertIn("backface-visibility: hidden", styles)
        self.assertNotIn(".embers::after", styles)
        self.assertNotIn("filter: drop-shadow(0 0", styles)
        self.assertNotIn("steps(", styles)
        self.assertNotIn("animation: ember-drift", styles)
        self.assertNotIn("background-position: 17%", styles)
        self.assertNotIn("cover fixed", styles)

    def test_generator_creates_exact_schema_2_commit_addressed_release_links(self) -> None:
        module = load_manifest_module()
        manifest = module.build_manifest(
            "mattirk/arch-rogue",
            "6.0.0-alpha.23",
            "1234567890abcdef",
        )
        self.assertEqual(manifest["schema"], 2)
        self.assertEqual(manifest["version"], "6.0.0-alpha.23")
        self.assertEqual(manifest["commit"], "1234567890ab")
        self.assertEqual(
            manifest["release_url"],
            "https://github.com/mattirk/arch-rogue/releases/tag/v6.0.0-alpha.23-1234567890ab",
        )
        self.assertEqual(
            manifest["assets"],
            {
                "windows": {"available": False},
                "linux": {
                    "available": True,
                    "url": "https://github.com/mattirk/arch-rogue/releases/download/v6.0.0-alpha.23-1234567890ab/arch-rogue-v6.0.0-alpha.23-1234567890ab-linux-x64.tar.gz",
                },
                "macos": {"available": False},
                "android": {
                    "available": True,
                    "url": "https://github.com/mattirk/arch-rogue/releases/download/v6.0.0-alpha.23-1234567890ab/Arch-Rogue.apk",
                },
            },
        )

    def test_generator_rejects_invalid_release_inputs(self) -> None:
        module = load_manifest_module()
        valid = ("mattirk/arch-rogue", "6.0.0-alpha.23", "1234567890ab")
        invalid_values = (
            (("mattirk", valid[1], valid[2]), "repository without name"),
            (("mattirk/arch-rogue/extra", valid[1], valid[2]), "repository with extra path"),
            (("mattirk /arch-rogue", valid[1], valid[2]), "repository with whitespace"),
            ((valid[0], "v6.0.0", valid[2]), "version with leading v"),
            ((valid[0], "6.0", valid[2]), "incomplete version"),
            ((valid[0], "6.0.0-alpha.01", valid[2]), "prerelease with leading zero"),
            ((valid[0], valid[1], "1234567890a"), "short commit"),
            ((valid[0], valid[1], "12345xz"), "non-hex commit"),
            ((valid[0], valid[1], "a" * 41), "long commit"),
        )
        for arguments, description in invalid_values:
            with self.subTest(description=description), self.assertRaises(ValueError):
                module.build_manifest(*arguments)

    def test_committed_manifest_is_valid_safe_schema_2_fallback(self) -> None:
        manifest = json.loads((WEBSITE / "downloads.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["schema"], 2)
        self.assertEqual(manifest["version"], "6.0.0-alpha.23")
        self.assertEqual(manifest["commit"], "pending")
        self.assertCountEqual(manifest["assets"], ["windows", "linux", "macos", "android"])
        self.assertEqual(manifest["assets"]["windows"], {"available": False})
        self.assertEqual(manifest["assets"]["macos"], {"available": False})
        for platform in ("linux", "android"):
            with self.subTest(platform=platform):
                asset = manifest["assets"][platform]
                self.assertTrue(asset["available"])
                self.assertTrue(asset["url"].startswith(
                    "https://github.com/mattirk/arch-rogue/releases"
                ))
        self.assertTrue(manifest["release_url"].startswith(
            "https://github.com/mattirk/arch-rogue/releases"
        ))


if __name__ == "__main__":
    unittest.main()

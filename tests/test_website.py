from __future__ import annotations

import importlib.util
import json
from html.parser import HTMLParser
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
WEBSITE = ROOT / "website"


class SiteParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.platforms: list[str] = []
        self.images: list[dict[str, str | None]] = []
        self.status_regions = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if values.get("data-platform"):
            self.platforms.append(str(values["data-platform"]))
        if tag == "img":
            self.images.append(values)
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
    def test_page_exposes_all_platforms_and_accessible_release_status(self) -> None:
        parser = SiteParser()
        parser.feed((WEBSITE / "index.html").read_text(encoding="utf-8"))
        self.assertCountEqual(parser.platforms, ["windows", "linux", "macos", "android"])
        self.assertEqual(len(parser.platforms), len(set(parser.platforms)))
        self.assertEqual(parser.status_regions, 1)
        self.assertTrue(parser.images)
        self.assertTrue(all(image.get("alt") is not None for image in parser.images))

    def test_referenced_local_assets_exist(self) -> None:
        page = (WEBSITE / "index.html").read_text(encoding="utf-8")
        styles = (WEBSITE / "styles.css").read_text(encoding="utf-8")
        for relative_path in (
            "styles.css",
            "app.js",
            "assets/icon.png",
            "assets/title_logo.png",
            "assets/background_title.png",
            "assets/panel.png",
            "assets/panel_inset.png",
            "assets/row.png",
            "assets/platform-windows.png",
            "assets/platform-linux.png",
            "assets/platform-macos.png",
            "assets/platform-android.png",
        ):
            with self.subTest(path=relative_path):
                self.assertTrue((WEBSITE / relative_path).is_file())
                self.assertIn(relative_path, page + styles)

    def test_site_copy_excludes_removed_pitch_and_recommendation(self) -> None:
        page = (WEBSITE / "index.html").read_text(encoding="utf-8")
        script = (WEBSITE / "app.js").read_text(encoding="utf-8")
        styles = (WEBSITE / "styles.css").read_text(encoding="utf-8")
        self.assertNotIn("Descend. Adapt. Survive.", page)
        self.assertNotIn("A grim isometric action roguelike", page)
        self.assertNotIn("Build-defining loot", page)
        self.assertIn("Unique class skills", page)
        self.assertNotIn("Recommended", page + script + styles)

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

    def test_generator_creates_exact_immutable_release_links(self) -> None:
        module = load_manifest_module()
        manifest = module.build_manifest("mattirk/arch-rogue", "4.4.0", "1234567890abcdef")
        self.assertEqual(manifest["commit"], "1234567")
        self.assertEqual(
            manifest["release_url"],
            "https://github.com/mattirk/arch-rogue/releases/tag/v4.4.0-1234567",
        )
        self.assertEqual(
            manifest["assets"],
            {
                "windows": "https://github.com/mattirk/arch-rogue/releases/download/v4.4.0-1234567/arch-rogue-v4.4.0-1234567-windows-x64.exe",
                "linux": "https://github.com/mattirk/arch-rogue/releases/download/v4.4.0-1234567/arch-rogue-v4.4.0-1234567-linux-x64",
                "macos": "https://github.com/mattirk/arch-rogue/releases/download/v4.4.0-1234567/arch-rogue-v4.4.0-1234567-macos-universal.zip",
                "android": "https://github.com/mattirk/arch-rogue/releases/download/v4.4.0-1234567/arch-rogue-v4.4.0-1234567-android-release.apk",
            },
        )

    def test_committed_manifest_is_valid_safe_fallback(self) -> None:
        manifest = json.loads((WEBSITE / "downloads.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["schema"], 1)
        self.assertCountEqual(manifest["assets"], ["windows", "linux", "macos", "android"])
        for url in [manifest["release_url"], *manifest["assets"].values()]:
            self.assertTrue(url.startswith("https://github.com/mattirk/arch-rogue/releases"))


if __name__ == "__main__":
    unittest.main()

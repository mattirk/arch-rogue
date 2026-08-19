from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pygame

import arch_rogue
from arch_rogue import game as game_module
from arch_rogue.content import RARITY_PROFILES, SECRET_HINTS, SHRINE_HINTS, TRAP_HINTS
from arch_rogue.game import ARCHETYPES, Game
from arch_rogue.models import Item


class ScriptPermissionTests(unittest.TestCase):
    """Committed shell scripts must be executable *in git's index*.

    This repository sets ``core.filemode = false``, so git ignores the working
    tree's executable bit entirely: `chmod +x` changes nothing git will record,
    and a script committed 100644 shows up as no change at all. The first sign
    is a CI job dying with "Permission denied" and exit 126, which is what
    happened to tools/build_steam_linux.sh. Only `git update-index --chmod=+x`
    fixes it, so assert on the index rather than on the filesystem.
    """

    def test_committed_shell_scripts_are_executable(self) -> None:
        root = Path(__file__).resolve().parents[1]
        try:
            listing = subprocess.run(
                ["git", "ls-files", "-s", "*.sh"],
                cwd=root,
                capture_output=True,
                text=True,
                check=True,
            ).stdout
        except (OSError, subprocess.CalledProcessError) as error:
            self.skipTest(f"git unavailable: {error}")

        scripts = [line.split() for line in listing.splitlines() if line.strip()]
        self.assertTrue(scripts, "expected at least one committed shell script")
        for mode, _sha, _stage, path in scripts:
            with self.subTest(path):
                self.assertEqual(
                    mode,
                    "100755",
                    f"{path} is committed non-executable; fix with "
                    f"`git update-index --chmod=+x {path}`",
                )


class SmokeTestHookTests(unittest.TestCase):
    """The depot smoke test: CI boots the packaged build and expects exit 0.

    If this hook stops being read, the Steam deploy silently loses its only
    end-to-end check that the frozen bundle actually starts.
    """

    def test_the_hook_is_off_unless_the_environment_asks_for_it(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertFalse(game_module.smoke_test_requested())

    def test_common_truthy_spellings_are_accepted(self) -> None:
        for value in ("1", "true", "TRUE", "yes", "on"):
            with self.subTest(value=value):
                with mock.patch.dict(
                    os.environ, {game_module.SMOKE_TEST_ENV: value}
                ):
                    self.assertTrue(game_module.smoke_test_requested())

    def test_other_values_do_not_enable_it(self) -> None:
        for value in ("0", "false", "no", ""):
            with self.subTest(value=value):
                with mock.patch.dict(
                    os.environ, {game_module.SMOKE_TEST_ENV: value}
                ):
                    self.assertFalse(game_module.smoke_test_requested())

    def test_the_run_loop_stops_itself_after_a_few_frames(self) -> None:
        game = Game(screen_size=(320, 200), headless=True)
        try:
            frames = []
            game.draw = lambda: frames.append(1)  # type: ignore[method-assign]
            game.handle_events = lambda: None  # type: ignore[method-assign]
            with mock.patch.dict(os.environ, {game_module.SMOKE_TEST_ENV: "1"}):
                game.run()
            self.assertEqual(len(frames), game_module.SMOKE_TEST_FRAMES)
            self.assertFalse(game.running)
        finally:
            pygame.quit()


class HeadlessStorageIsolationTests(unittest.TestCase):
    """Headless runs must not touch the developer's real profile.

    Until 4.9.21 a headless ``Game`` refused to *read* home-directory
    preferences but still defaulted its ``options_path`` and ``save_path`` there,
    so any test reaching ``save_options`` (every test that finalises a run)
    overwrote the developer's own ``meta_progress`` and run save.
    """

    def test_a_headless_game_stores_nothing_in_the_home_directory(self) -> None:
        game = Game(screen_size=(320, 200), headless=True)
        try:
            home = Path.home().resolve()
            for path in (game.options_path, game.save_path):
                with self.subTest(path=str(path)):
                    self.assertFalse(
                        path.resolve().is_relative_to(home),
                        f"headless Game would write {path} inside {home}",
                    )
        finally:
            pygame.quit()

    def test_headless_games_share_one_throwaway_directory(self) -> None:
        # Persistence across instances still works for callers that want it;
        # what changes is only where "the default location" points.
        first = Game(screen_size=(320, 200), headless=True)
        second = Game(screen_size=(320, 200), headless=True)
        try:
            self.assertEqual(first.options_path, second.options_path)
        finally:
            pygame.quit()

    def test_an_explicit_save_path_still_wins(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "run.json"
            game = Game(screen_size=(320, 200), headless=True, save_path=target)
            try:
                self.assertEqual(game.save_path, target)
            finally:
                pygame.quit()


class SaveAndMetadataTests(unittest.TestCase):

    def test_release_version_metadata_is_aligned(self) -> None:
        root = Path(__file__).resolve().parents[1]
        expected = arch_rogue.__version__

        with (root / "pyproject.toml").open("rb") as handle:
            project_version = tomllib.load(handle)["project"]["version"]
        with (root / "server" / "pyproject.toml").open("rb") as handle:
            server_project_version = tomllib.load(handle)["project"]["version"]

        buildozer_text = (root / "buildozer.spec").read_text(encoding="utf-8")
        buildozer_matches = re.findall(
            r"(?m)^(package\.version|version)\s*=\s*([^\s#]+)",
            buildozer_text,
        )
        self.assertEqual(len(buildozer_matches), 2)

        server_init = (root / "server" / "__init__.py").read_text(encoding="utf-8")
        server_match = re.search(
            r'(?m)^__version__\s*=\s*["\']([^"\']+)["\']',
            server_init,
        )
        self.assertIsNotNone(server_match)
        assert server_match is not None

        downloads = json.loads(
            (root / "website" / "downloads.json").read_text(encoding="utf-8")
        )
        changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
        changelog_match = re.search(
            r"(?m)^##\s+v?(\d+(?:\.\d+)+(?:[-+][0-9A-Za-z.-]+)?)\b",
            changelog,
        )
        self.assertIsNotNone(changelog_match)
        assert changelog_match is not None

        versions = {
            "pyproject.toml": project_version,
            "buildozer.spec package.version": dict(buildozer_matches)["package.version"],
            "buildozer.spec version": dict(buildozer_matches)["version"],
            "server/pyproject.toml": server_project_version,
            "server/__init__.py": server_match.group(1),
            "website/downloads.json": downloads["version"],
            "CHANGELOG.md": changelog_match.group(1),
        }
        for source, actual in versions.items():
            with self.subTest(source=source):
                self.assertEqual(actual, expected)

    def test_metadata_content_profiles_and_save_version(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = Game(
                screen_size=(760, 520),
                headless=True,
                save_path=Path(tmpdir) / "run.json",
            )
            game.options_path = Path(tmpdir) / "options.json"
            game.rng.seed(1202)
            game.restart(ARCHETYPES[1])
            if game.story_intro_pending:
                self.assertTrue(game.choose_story_relic_path(0))
            try:
                self.assertIn("Cursed", RARITY_PROFILES)
                self.assertIn("Twilight Shrine", SHRINE_HINTS)
                self.assertIn("Moonlit Bargain", SECRET_HINTS)
                self.assertIn("Rune Trap", TRAP_HINTS)

                self.assertTrue(game.save_run())
                saved = json.loads(game.save_path.read_text(encoding="utf-8"))
                self.assertEqual(saved["version"], 5)
                self.assertEqual(saved["release"], arch_rogue.__version__)
            finally:
                pass

    def test_pre_455_save_on_stairs_restores_to_adjacent_walkable_tile(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            save_path = Path(tmpdir) / "run.json"
            game = Game(screen_size=(960, 540), headless=True, save_path=save_path)
            game.rng.seed(455)
            game.restart(ARCHETYPES[0])
            if game.story_intro_pending:
                self.assertTrue(game.choose_story_relic_path(0))
            stairs = game.dungeon.stairs
            game.player.x, game.player.y = stairs[0] + 0.5, stairs[1] + 0.5
            self.assertTrue(game.save_run())

            loaded = Game(screen_size=(960, 540), headless=True, save_path=save_path)
            loaded.rng.seed(455)
            self.assertTrue(loaded.load_run())
            self.assertNotEqual(
                (int(loaded.player.x), int(loaded.player.y)),
                loaded.dungeon.stairs,
            )
            self.assertFalse(
                loaded.dungeon.blocked_for_radius(
                    loaded.player.x,
                    loaded.player.y,
                    0.27,
                    block_stairs=True,
                )
            )

    def test_run_state_save_and_resume_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            save_path = Path(tmpdir) / "run.json"
            game = Game(screen_size=(960, 540), headless=True, save_path=save_path)
            try:
                game.rng.seed(2026)
                game.restart(ARCHETYPES[2])
                game.current_depth = 4
                game.elapsed = 73.5
                game.player.hp = 41
                game.player.mana = 12
                game.player.inventory.append(
                    Item(
                        "Beta Blade",
                        "weapon",
                        power=11,
                        rarity="Rare",
                        affixes=["Cruel", "of Force"],
                        unidentified=True,
                    )
                )
                game.player.equipment["armor"] = Item(
                    "Beta Mail", "armor", defense=5, rarity="Magic"
                )
                self.assertTrue(game.save_run())

                loaded = Game(
                    screen_size=(960, 540), headless=True, save_path=save_path
                )
                loaded.rng.seed(2026)
                self.assertTrue(loaded.load_run())

                self.assertEqual(loaded.state, "playing")
                self.assertEqual(loaded.current_depth, 4)
                self.assertEqual(loaded.player.class_name, "Arcanist")
                self.assertEqual(loaded.player.hp, 41)
                self.assertEqual(int(loaded.player.mana), 12)
                self.assertEqual(loaded.player.inventory[0].name, "Beta Blade")
                self.assertTrue(loaded.player.inventory[0].unidentified)
                armor = loaded.player.equipment["armor"]
                self.assertIsNotNone(armor)
                assert armor is not None
                self.assertEqual(armor.name, "Beta Mail")
                self.assertTrue(
                    loaded.dungeon.is_floor(loaded.player.x, loaded.player.y)
                )
            finally:
                pass

    def test_restored_enemy_color_is_hashable_tuple(self) -> None:
        # Regression: enemies are serialized via __dict__, so the color tuple
        # becomes a JSON list on disk. Restoring via Enemy(**enemy) used to keep
        # that list, which crashed draw_impact's overlay cache (the cache key is a
        # tuple containing color, and a list makes it unhashable). The restore
        # path must normalize color back to a tuple.
        from arch_rogue.models import Enemy

        with tempfile.TemporaryDirectory() as tmpdir:
            save_path = Path(tmpdir) / "run.json"
            game = Game(screen_size=(960, 540), headless=True, save_path=save_path)
            try:
                game.rng.seed(2026)
                game.restart(ARCHETYPES[2])
                # Force at least one enemy into the run so the save has a color
                # field to round-trip. restart() leaves enemies empty until the
                # floor is populated, so append one directly.
                game.enemies.append(
                    Enemy(
                        "Cultist",
                        "caster",
                        4.5,
                        4.5,
                        18,
                        18,
                        2.4,
                        6,
                        7,
                        5.0,
                        1.2,
                        color=(160, 70, 200),
                    )
                )
                for enemy in game.enemies:
                    self.assertIsInstance(enemy.color, tuple)
                self.assertTrue(game.save_run())

                loaded = Game(
                    screen_size=(960, 540), headless=True, save_path=save_path
                )
                self.assertTrue(loaded.load_run())
                self.assertTrue(loaded.enemies, "restored run should have enemies")
                for enemy in loaded.enemies:
                    self.assertIsInstance(
                        enemy.color,
                        tuple,
                        "restored enemy.color must be a tuple, not a list",
                    )
                    # The exact failure mode of the crash: hashing a tuple that
                    # contains enemy.color must succeed.
                    hash(("death", 0, 0, 0, enemy.color))
            finally:
                pass

    def test_add_impact_normalizes_list_color(self) -> None:
        # Defensive: add_impact is called from many code paths. If any caller
        # passes a list color, the ImpactEffect must still get a tuple so the
        # draw_impact overlay cache key stays hashable.
        with tempfile.TemporaryDirectory() as tmpdir:
            game = Game(
                screen_size=(960, 540), headless=True, save_path=Path(tmpdir) / "run.json"
            )
            try:
                game.rng.seed(2026)
                game.restart(ARCHETYPES[2])
                game.add_impact(0.0, 0.0, [255, 90, 70], ttl=0.3, kind="burst")
                self.assertEqual(len(game.impact_effects), 1)
                effect = game.impact_effects[0]
                self.assertIsInstance(effect.color, tuple)
                # The draw_impact overlay cache builds a tuple key containing
                # effect.color; that key must be hashable.
                hash((effect.kind, effect.archetype, 0, 0, 0, effect.color))
            finally:
                pass


if __name__ == "__main__":
    unittest.main()

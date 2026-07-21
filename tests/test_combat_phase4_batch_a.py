from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from arch_rogue.content import ARCHETYPES
from arch_rogue.combat.class_skills import CLASS_SKILLS, _DEFAULT_CLASS_SKILL
from arch_rogue.game import Game
from arch_rogue.models import Enemy, Item


class _FakeRng:
    """Deterministic stand-in exposing only what ``roll_melee_crit`` uses."""

    def __init__(self, values: list[float]) -> None:
        self._values = list(values)
        self._i = 0

    def random(self) -> float:
        v = self._values[self._i % len(self._values)]
        self._i += 1
        return v


class CombatPhase4BatchATests(unittest.TestCase):
    def make_game(
        self, tmpdir: str, archetype_index: int = 0, seed: int = 2202
    ) -> Game:
        game = Game(
            screen_size=(820, 540),
            headless=True,
            save_path=Path(tmpdir) / "run.json",
        )
        game.options_path = Path(tmpdir) / "options.json"
        game.rng.seed(seed)
        game.restart(ARCHETYPES[archetype_index])
        if game.story_intro_pending:
            self.assertTrue(game.choose_story_relic_path(0))
        game.active_cutscene = None
        return game

    def _make_enemy(self, game: Game) -> Enemy:
        return Enemy(
            "Target",
            "melee",
            game.player.x + 1.0,
            game.player.y,
            10,
            10,
            1.0,
            5,
            1,
            0.8,
            1.0,
        )

    # ------------------------------------------------------------------
    # #7 ClassSkill registry
    # ------------------------------------------------------------------
    def test_registry_maps_every_archetype_and_default_matches_old_defaults(self) -> None:
        expected = {
            "Warden": ("time_skip", "player_cast_time_skip", "Time Skip", (235, 205, 120)),
            "Rogue": ("ambush_bell", "player_cast_ambush_bell", "Ambush Bell", (170, 230, 150)),
            "Arcanist": ("nova", "player_cast_nova", "Nova", (120, 210, 255)),
            "Acolyte": ("spirit_call", "player_cast_spirit_call", "Spirit Call", (220, 95, 140)),
            "Ranger": ("spirit_beast", "player_cast_spirit_beast", "Spirit Beast", (150, 215, 105)),
        }
        self.assertEqual(set(CLASS_SKILLS), set(expected))
        for archetype, (kind, cast, bonus, color) in expected.items():
            entry = CLASS_SKILLS[archetype]
            self.assertEqual(entry.archetype, archetype)
            self.assertEqual(entry.kind, kind)
            self.assertEqual(entry.cast_method, cast)
            self.assertEqual(entry.bonus_term, bonus)
            self.assertEqual(entry.color, color)
        # default matches the pre-registry fallbacks (Arcanist/nova values)
        self.assertEqual(_DEFAULT_CLASS_SKILL.kind, "nova")
        self.assertEqual(_DEFAULT_CLASS_SKILL.cast_method, "player_cast_nova")
        self.assertEqual(_DEFAULT_CLASS_SKILL.bonus_term, "Nova")
        self.assertEqual(_DEFAULT_CLASS_SKILL.color, (120, 210, 255))

    def test_class_skill_methods_route_through_registry_for_each_archetype(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            for index, archetype in enumerate(
                ["Warden", "Rogue", "Arcanist", "Acolyte", "Ranger"]
            ):
                game = self.make_game(tmpdir, archetype_index=index)
                entry = CLASS_SKILLS[archetype]
                self.assertEqual(game.class_skill_kind(), entry.kind)
                self.assertEqual(game.skill_color(), entry.color)
                # cast_method names a real method on the composed CombatMixin
                self.assertTrue(callable(getattr(game, entry.cast_method)))
                # equipment_class_skill_bonus() without gear returns False; the
                # canonical bonus term is the registry's bonus_term.
                game.player.equipment = {slot: None for slot in game.player.equipment}
                self.assertFalse(game.equipment_class_skill_bonus())

    def test_unknown_archetype_falls_back_to_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, archetype_index=2)  # Arcanist
            game.player.class_name = "Nobody"
            self.assertEqual(game.class_skill_kind(), _DEFAULT_CLASS_SKILL.kind)
            self.assertEqual(game.skill_color(), _DEFAULT_CLASS_SKILL.color)
            self.assertEqual(
                game.equipment_class_skill_bonus(),
                game.equipment_skill_bonus(_DEFAULT_CLASS_SKILL.bonus_term),
            )

    # ------------------------------------------------------------------
    # #4 attack-speed / cast-speed getters
    # ------------------------------------------------------------------
    def test_speed_getters_clamp_and_default_to_zero(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            game.player.equipment = {slot: None for slot in game.player.equipment}
            self.assertEqual(game.player_attack_speed(), 0.0)
            self.assertEqual(game.player_cast_speed(), 0.0)

            game.player.equipment["weapon"] = Item(
                "Blade", "weapon", power=2, attack_speed=0.18
            )
            self.assertAlmostEqual(game.player_attack_speed(), 0.18)
            game.player.equipment["armor"] = Item(
                "Robe", "armor", defense=1, cast_speed=0.20
            )
            self.assertAlmostEqual(game.player_cast_speed(), 0.20)

            # clamp to [-0.20, 0.35]
            game.player.equipment["weapon"].attack_speed = 2.0
            self.assertEqual(game.player_attack_speed(), 0.35)
            game.player.equipment["weapon"].attack_speed = -1.0
            self.assertEqual(game.player_attack_speed(), -0.20)

    def test_melee_cooldown_consumes_player_attack_speed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            game.player.equipment = {slot: None for slot in game.player.equipment}
            base = game.melee_cooldown()
            game.player.equipment["weapon"] = Item(
                "Blade", "weapon", power=2, attack_speed=0.18
            )
            self.assertLess(game.melee_cooldown(), base)

    # ------------------------------------------------------------------
    # #3 crit refactor
    # ------------------------------------------------------------------
    def test_rogue_crit_profile_tiers_and_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, archetype_index=1)  # Rogue
            game.player.skill_upgrades.clear()
            self.assertEqual(game._rogue_crit_profile(), (0.0, 1.0))
            tiers = [
                ("rogue_precision", (0.15, 1.60)),
                ("rogue_venom", (0.20, 1.75)),
                ("rogue_executioner", (0.28, 1.95)),
                ("rogue_crimson_edge", (0.34, 2.10)),
                ("rogue_deathmark", (0.40, 2.25)),
            ]
            for upgrade, expected in tiers:
                game.player.skill_upgrades.clear()
                game.player.skill_upgrades.append(upgrade)
                self.assertEqual(game._rogue_crit_profile(), expected, upgrade)

    def test_roll_melee_crit_gates_on_rogue_class(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            # Warden with rogue_precision (profile would grant 0.15) never crits:
            # the roll is class-gated to Rogue.
            game = self.make_game(tmpdir, archetype_index=0)  # Warden
            game.player.skill_upgrades.append("rogue_precision")
            enemy = self._make_enemy(game)
            game.rng = _FakeRng([0.0])  # would satisfy < 0.15 if not class-gated
            is_crit, _ = game.roll_melee_crit(enemy)
            self.assertFalse(is_crit)

    def test_roll_melee_crit_precision_roll_is_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, archetype_index=1)  # Rogue
            game.player.skill_upgrades.append("rogue_precision")  # 0.15 chance, 1.60 mult
            enemy = self._make_enemy(game)
            game.floaters.clear()

            game.rng = _FakeRng([0.10])  # < 0.15 -> crit
            is_crit, mult = game.roll_melee_crit(enemy)
            self.assertTrue(is_crit)
            self.assertAlmostEqual(mult, 1.60)
            self.assertEqual(game.floaters, [])  # "Critical" floater is the caller's job

            game.rng = _FakeRng([0.90])  # >= 0.15 -> no crit, no smoke (no smoke gear)
            is_crit, mult = game.roll_melee_crit(enemy)
            self.assertFalse(is_crit)
            self.assertAlmostEqual(mult, 1.60)

    def test_roll_melee_crit_smoke_override(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, archetype_index=1)  # Rogue
            game.player.skill_upgrades.clear()  # base backstabs never crit
            game.player.equipment = {slot: None for slot in game.player.equipment}
            game.player.equipment["weapon"] = Item(
                "Smoke Blade", "weapon", power=2, unique_effect="smoke crits"
            )
            game.set_player_status("smoke", 1.0)
            enemy = self._make_enemy(game)
            game.floaters.clear()

            # First random() = 0.5 -> precision roll fails (chance 0.0 anyway).
            # Second random() = 0.10 -> smoke override fires (< 0.30).
            game.rng = _FakeRng([0.5, 0.10])
            is_crit, mult = game.roll_melee_crit(enemy)
            self.assertTrue(is_crit)
            self.assertAlmostEqual(mult, 1.80)
            self.assertTrue(any(f.text == "Smoke Crit" for f in game.floaters))


if __name__ == "__main__":
    unittest.main()
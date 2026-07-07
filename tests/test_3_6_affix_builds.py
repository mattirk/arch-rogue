from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from arch_rogue.content import (  # noqa: E402
    AFFIX_DEFINITIONS,
    ARCHETYPES,
    RARITY_AFFIX_ROLL_RANGES,
    UNIQUE_ITEM_DEFINITIONS,
)
from arch_rogue.game import Game  # noqa: E402
from arch_rogue.inventory import AFFIX_TAG_LABELS  # noqa: E402
from arch_rogue.models import Enemy, Item  # noqa: E402


class AffixBuild310Tests(unittest.TestCase):
    def make_game(
        self, tmpdir: str, archetype_index: int = 0, seed: int = 3100
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

    def test_affix_table_has_rarity_roll_ranges_and_new_stat_families(self) -> None:
        names = {affix.name for affix in AFFIX_DEFINITIONS}
        tags = {tag for affix in AFFIX_DEFINITIONS for tag in affix.tags}

        self.assertGreaterEqual(len(AFFIX_DEFINITIONS), 25)
        self.assertTrue(
            {
                "Ember-Veined",
                "Venomous",
                "Quickened",
                "Rune-Cut",
                "Fleet",
                "Mirror-Barbed",
                "of Alacrity",
                "of Siphons",
            }.issubset(names)
        )
        self.assertTrue(
            {
                "attack_speed",
                "cast_speed",
                "movement",
                "thorns",
                "lifesteal",
                "proc",
                "bolt",
            }.issubset(tags)
        )
        self.assertLess(
            RARITY_AFFIX_ROLL_RANGES["Magic"][1],
            RARITY_AFFIX_ROLL_RANGES["Legendary"][1],
        )
        self.assertGreater(
            RARITY_AFFIX_ROLL_RANGES["Cursed"][0],
            RARITY_AFFIX_ROLL_RANGES["Rare"][0],
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            storm = next(
                affix for affix in AFFIX_DEFINITIONS if affix.name == "Storm-Touched"
            )
            item = Item("Test Wand", "weapon", rarity="Legendary")
            game.rng.seed(7)
            game._apply_affix_definition(item, storm, "Legendary")

            self.assertIn("Storm-Touched", item.affixes)
            self.assertEqual(item.damage_type, "arcane")
            self.assertIn("bolt", item.affix_tags)
            self.assertGreaterEqual(item.cast_speed, 0.04 * 1.25)
            self.assertLessEqual(item.cast_speed, 0.08 * 1.55)
            self.assertGreater(item.proc_chance, 0.0)

    def test_affix_synergies_modify_combat_resolution(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, archetype_index=2, seed=3101)
            base_bolt_cooldown = game.bolt_cooldown()
            base_melee_cooldown = game.melee_cooldown()
            weapon = Item(
                "Siphoning Emberstar",
                "weapon",
                power=3,
                rarity="Rare",
                damage_type="arcane",
                skill_bonus="Bolt +1 shard / Bolt pierce",
                proc_effect="ignite",
                affix_tags=["cast_speed", "bolt", "fire", "lifesteal"],
                attack_speed=0.18,
                cast_speed=0.20,
                lifesteal=0.20,
                proc_chance=1.0,
            )
            armor = Item(
                "Barbed Robe",
                "armor",
                defense=1,
                rarity="Rare",
                proc_effect="thorns",
                affix_tags=["thorns"],
                thorns=5,
            )
            game.player.equipment["weapon"] = weapon
            game.player.equipment["armor"] = armor

            self.assertLess(game.bolt_cooldown(), base_bolt_cooldown)
            self.assertLess(game.melee_cooldown(), base_melee_cooldown)

            enemy = Enemy(
                "Crypt Brute",
                "melee",
                game.player.x + 1.0,
                game.player.y,
                80,
                80,
                1.8,
                10,
                15,
                1.0,
                1.0,
            )
            game.enemies = [enemy]
            game.player.hp = game.player.max_hp - 20
            before_hp = game.player.hp

            game.damage_enemy(
                enemy,
                20,
                knockback_from=(1.0, 0.0),
                damage_type="arcane",
            )

            self.assertIn("burning", enemy.statuses)
            self.assertLess(enemy.hp, 60)
            self.assertGreater(game.player.hp, before_hp)

            attacker = Enemy(
                "Thorn Target",
                "melee",
                game.player.x + 1.0,
                game.player.y,
                30,
                30,
                1.8,
                10,
                10,
                1.0,
                1.0,
            )
            game.enemies.append(attacker)
            game.take_player_damage(10, source="melee", attacker=attacker)
            self.assertLess(attacker.hp, 30)

    def test_unique_item_definitions_cover_archetypes_and_generate_items(self) -> None:
        by_archetype = {
            archetype.name: [
                definition
                for definition in UNIQUE_ITEM_DEFINITIONS
                if definition.archetype == archetype.name
            ]
            for archetype in ARCHETYPES
        }
        for archetype_name, definitions in by_archetype.items():
            self.assertGreaterEqual(len(definitions), 2, archetype_name)
            self.assertTrue(any(definition.affix_tags for definition in definitions))
            self.assertTrue(
                any(
                    definition.attack_speed
                    or definition.cast_speed
                    or definition.move_speed
                    or definition.thorns
                    or definition.lifesteal
                    for definition in definitions
                ),
                archetype_name,
            )

        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, archetype_index=4, seed=3102)
            ranger_definition = by_archetype["Ranger"][0]
            item = game._make_unique_from_definition(ranger_definition, 3.0, 4.0)

            self.assertEqual(item.rarity, "Unique")
            self.assertEqual(item.x, 3.0)
            self.assertEqual(item.y, 4.0)
            self.assertIn(
                "volley", set(item.affix_tags) | set(item.skill_bonus.lower().split())
            )
            self.assertTrue(item.attack_speed or item.move_speed or item.thorns)

    def test_cursed_items_gain_power_with_explicit_tradeoffs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, seed=3103)
            blade = Item(
                "Hungry Knife",
                "weapon",
                power=5,
                rarity="Rare",
                attack_speed=0.05,
                move_speed=0.02,
            )
            game._apply_cursed_bargain(blade)

            self.assertTrue(blade.cursed)
            self.assertEqual(blade.rarity, "Cursed")
            self.assertIn("Tempting Curse", blade.affixes)
            self.assertIn("curse", blade.affix_tags)
            self.assertEqual(blade.power, 9)
            self.assertGreater(blade.attack_speed, 0.05)
            self.assertLess(blade.move_speed, 0.02)

            armor = Item(
                "Hex Plate", "armor", defense=4, rarity="Rare", cast_speed=0.04
            )
            game._apply_cursed_bargain(armor)
            self.assertEqual(armor.defense, 7)
            self.assertGreaterEqual(armor.thorns, 2)
            self.assertLess(armor.cast_speed, 0.04)

    def test_expanded_item_fields_roundtrip_and_old_saves_default_noop(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, seed=3104)
            old_item_data = {
                "name": "Old Storm Blade",
                "slot": "weapon",
                "power": 7,
                "rarity": "Rare",
                "affixes": ["Storm-Touched"],
                "damage_type": "arcane",
                "skill_bonus": "Bolt +1 shard",
                "proc_effect": "lifesteal",
            }
            migrated = game.item_from_dict(old_item_data)
            self.assertIsNotNone(migrated)
            assert migrated is not None
            self.assertEqual(migrated.affix_tags, [])
            self.assertEqual(migrated.attack_speed, 0.0)
            self.assertEqual(migrated.cast_speed, 0.0)
            self.assertEqual(migrated.thorns, 0)
            self.assertEqual(migrated.lifesteal, 0.0)
            self.assertEqual(migrated.proc_chance, 0.0)

            modern = Item(
                "Modern Siphon",
                "weapon",
                power=8,
                rarity="Legendary",
                affixes=["of Siphons"],
                damage_type="shadow",
                proc_effect="lifesteal",
                affix_tags=["lifesteal", "blood"],
                attack_speed=0.07,
                cast_speed=0.04,
                move_speed=0.03,
                thorns=2,
                lifesteal=0.12,
                proc_chance=0.45,
            )
            restored = game.item_from_dict(game.item_to_dict(modern))
            self.assertIsNotNone(restored)
            assert restored is not None
            self.assertEqual(restored.affix_tags, ["lifesteal", "blood"])
            self.assertAlmostEqual(restored.attack_speed, 0.07)
            self.assertAlmostEqual(restored.cast_speed, 0.04)
            self.assertAlmostEqual(restored.move_speed, 0.03)
            self.assertEqual(restored.thorns, 2)
            self.assertAlmostEqual(restored.lifesteal, 0.12)
            self.assertAlmostEqual(restored.proc_chance, 0.45)

    def test_inventory_tag_labels_are_ascii_and_chips_resolve(self) -> None:
        for tag, label in AFFIX_TAG_LABELS.items():
            self.assertTrue(label.isascii(), tag)
            self.assertLessEqual(len(label), 12, tag)

    def test_inventory_hints_surface_affix_tags_and_build_relevance(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, archetype_index=1, seed=3105)
            game.player.skill_upgrades.append("rogue_precision")
            blade = Item(
                "Venom Tempo Knife",
                "weapon",
                power=11,
                rarity="Rare",
                affixes=["Venomous", "Quickened"],
                damage_type="poison",
                skill_bonus="Melee tempo",
                proc_effect="poison",
                affix_tags=["critical", "poison", "attack_speed"],
                attack_speed=0.12,
                proc_chance=0.50,
            )

            summary = game.item_decision_summary(blade)
            tooltips = game.item_affix_tooltip_lines(blade)
            chips = game.item_affix_tag_chips(blade)

            self.assertIn("Build: supports", summary)
            self.assertIn("poison", summary)
            self.assertIn("poison", chips)
            self.assertIn("attack_speed", chips)
            self.assertTrue(any("attack speed" in line for line in tooltips))
            # Rendering the selected card with procedural icon chips must not error.
            game.inventory_open = True
            game.draw_inventory()


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import os
import random
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from arch_rogue.content import (  # noqa: E402
    ARCHETYPES,
    UNIQUE_ITEM_DEFINITIONS,
)
from arch_rogue.game import Game  # noqa: E402
from arch_rogue.models import Enemy, Item  # noqa: E402
from arch_rogue.combat.damage import DamageContext  # noqa: E402


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
                DamageContext(
                    target=enemy,
                    amount=20,
                    damage_type="arcane",
                    knockback_from=(1.0, 0.0),
                )
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

    def test_unique_effects_produce_tangible_gameplay_effects(self) -> None:
        # Spot-check that equipping archetype uniques actually changes combat
        # outcomes versus baseline.
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, archetype_index=0, seed=3111)
            game.player.equipment["weapon"] = None
            game.player.equipment["armor"] = None
            base_armor = game.player.armor()

            # Oathwall Carapace — armor unique bonus.
            oathwall = game._make_unique_from_definition(
                next(
                    u
                    for u in UNIQUE_ITEM_DEFINITIONS
                    if u.unique_effect == "oathwall aegis"
                ),
                0.0,
                0.0,
            )
            game.player.equipment["armor"] = oathwall
            self.assertGreater(game.player.armor(), base_armor + oathwall.defense)

            # Splinter Storm — extra bolt angles.
            game.player.equipment["weapon"] = game._make_unique_from_definition(
                next(
                    u
                    for u in UNIQUE_ITEM_DEFINITIONS
                    if u.unique_effect == "splinter storm"
                ),
                0.0,
                0.0,
            )
            game.player.equipment["armor"] = None
            game.player.mana = game.player.max_mana
            game.player.bolt_timer = 0.0
            game.projectiles.clear()
            game.player_cast_bolt()
            self.assertGreaterEqual(len(game.projectiles), 3)

            # Vanish on Dash — grants smoke status.
            game.player.equipment["armor"] = game._make_unique_from_definition(
                next(
                    u
                    for u in UNIQUE_ITEM_DEFINITIONS
                    if u.unique_effect == "vanish on dash"
                ),
                0.0,
                0.0,
            )
            game.player.equipment["weapon"] = None
            game.player.stamina = game.player.max_stamina
            game.player.dash_timer = 0.0
            game.player.status_effects.clear()
            game.player_dash()
            self.assertGreater(game.player_status("smoke"), 0)

            # Sanguine Echo — boosts lifesteal ratio.
            game.player.equipment["weapon"] = game._make_unique_from_definition(
                next(
                    u
                    for u in UNIQUE_ITEM_DEFINITIONS
                    if u.unique_effect == "sanguine echo"
                ),
                0.0,
                0.0,
            )
            game.player.equipment["armor"] = None
            ratio = game.equipment_lifesteal_ratio()
            self.assertGreater(ratio, 0.06)  # base lifesteal + sanguine echo bonus

            # Counter Smite — boosts riposte counter damage.
            game.player.equipment["weapon"] = game._make_unique_from_definition(
                next(
                    u
                    for u in UNIQUE_ITEM_DEFINITIONS
                    if u.unique_effect == "counter smite"
                ),
                0.0,
                0.0,
            )
            game.player.equipment["armor"] = None
            game.player.skill_upgrades.append("warden_riposte")
            enemy = Enemy(
                "Counter Target",
                "melee",
                game.player.x + 1.0,
                game.player.y,
                200,
                200,
                1.0,
                5,
                10,
                1.0,
                1.0,
            )
            game.enemies = [enemy]
            enemy_hp_before = enemy.hp
            game.take_player_damage(5, source="melee", attacker=enemy)
            self.assertLess(enemy.hp, enemy_hp_before - 5)


class RolledEquipmentCeilingTests(unittest.TestCase):
    def make_game(self, tmpdir: str, seed: int = 3300) -> Game:
        game = Game(
            screen_size=(820, 540),
            headless=True,
            save_path=Path(tmpdir) / "run.json",
        )
        game.options_path = Path(tmpdir) / "options.json"
        game.rng.seed(seed)
        game.restart(ARCHETYPES[0])
        if game.story_intro_pending:
            self.assertTrue(game.choose_story_relic_path(0))
        game.active_cutscene = None
        return game

    def test_legendary_is_never_rolled_and_uniques_outclass_rolls(self) -> None:
        from arch_rogue.content import (
            MAX_ROLLED_ARMOR_DEFENSE,
            MAX_ROLLED_WEAPON_POWER,
        )

        weakest_unique_power = min(
            d.power for d in UNIQUE_ITEM_DEFINITIONS if d.slot == "weapon"
        )
        weakest_unique_defense = min(
            d.defense for d in UNIQUE_ITEM_DEFINITIONS if d.slot == "armor"
        )
        # The caps are fixed below the weakest unique with a deliberate gap
        # (uniques were tripled in 4.10.x while rolled ceilings stayed put).
        self.assertLess(MAX_ROLLED_WEAPON_POWER, weakest_unique_power)
        self.assertLess(MAX_ROLLED_ARMOR_DEFENSE, weakest_unique_defense)

        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            for index in range(600):
                item = game._make_loot(1.0 + index % 7, 1.0 + index % 5)
                self.assertNotEqual(item.rarity, "Legendary", item.name)
                if item.rarity == "Unique":
                    continue
                if item.slot == "weapon":
                    self.assertLess(
                        item.power, weakest_unique_power, item.name
                    )
                elif item.slot == "armor":
                    self.assertLess(
                        item.defense, weakest_unique_defense, item.name
                    )
            # Rare rolls with stacked boosts (cursed bargain) stay capped too.
            for index in range(200):
                item = game._make_equipment("weapon", "Rare", 1.0, 1.0)
                self.assertLessEqual(item.power, MAX_ROLLED_WEAPON_POWER)
                item = game._make_equipment("armor", "Rare", 1.0, 1.0)
                self.assertLessEqual(item.defense, MAX_ROLLED_ARMOR_DEFENSE)

    def test_unique_armor_waits_for_depth_4(self) -> None:
        from arch_rogue.content import UNIQUE_ARMOR_MIN_DEPTH

        self.assertEqual(UNIQUE_ARMOR_MIN_DEPTH, 4)
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            # Floors 1-3: every unique source funnels through _make_unique,
            # which must only surface weapons (this covers the guaranteed
            # Twilight Shrine unique as well as the loot-roll window).
            for depth in (1, 2, 3):
                game.current_depth = depth
                for index in range(120):
                    item = game._make_unique(1.0, 1.0)
                    self.assertEqual(item.rarity, "Unique")
                    self.assertNotEqual(
                        item.slot,
                        "armor",
                        f"unique armor {item.name} dropped on floor {depth}",
                    )
            # From the gate floor on, armors join the pool again (with 240
            # draws the ~49% armor share cannot statistically miss).
            game.current_depth = UNIQUE_ARMOR_MIN_DEPTH
            slots = {
                game._make_unique(1.0, 1.0).slot for _ in range(240)
            }
            self.assertIn("armor", slots)
            self.assertIn("weapon", slots)

    def test_unique_loot_window_is_the_5_0_rate(self) -> None:
        # 5.0 halved the base unique window to 0.3%: a roll of 0.995 (inside
        # the old 0.994 window) now yields ordinary gear; only > 0.997 hits.
        class ForcedRandom(random.Random):
            def __init__(self, forced: float) -> None:
                super().__init__(99)
                self.forced: float | None = forced

            def random(self) -> float:
                if self.forced is not None:
                    value, self.forced = self.forced, None
                    return value
                return super().random()

        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            game.run_modifier = replace(game.run_modifier, loot_bonus=0.0)
            game.story_state = None

            game.rng = ForcedRandom(0.995)
            self.assertNotEqual(game._make_loot(1.0, 1.0).rarity, "Unique")
            game.rng = ForcedRandom(0.9975)
            self.assertEqual(game._make_loot(1.0, 1.0).rarity, "Unique")


class CurseLockAndRemoveCurseTests(unittest.TestCase):
    def make_game(self, tmpdir: str, seed: int = 3200) -> Game:
        game = Game(
            screen_size=(820, 540),
            headless=True,
            save_path=Path(tmpdir) / "run.json",
        )
        game.options_path = Path(tmpdir) / "options.json"
        game.rng.seed(seed)
        game.restart(ARCHETYPES[0])
        if game.story_intro_pending:
            self.assertTrue(game.choose_story_relic_path(0))
        game.active_cutscene = None
        return game

    @staticmethod
    def cursed_weapon() -> Item:
        return Item(
            "Grave Knife",
            "weapon",
            power=9,
            rarity="Cursed",
            cursed=True,
            affixes=["Tempting Curse"],
            affix_tags=["curse", "risk"],
            move_speed=-0.03,
        )

    def test_cursed_equipment_blocks_replacement(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            cursed = self.cursed_weapon()
            plain = Item("Iron Sword", "weapon", power=5, rarity="Common")
            game.player.inventory[:] = [cursed, plain]
            game.use_inventory_slot(0)
            self.assertIs(game.player.equipment["weapon"], cursed)

            game.use_inventory_slot(game.player.inventory.index(plain))
            self.assertIs(game.player.equipment["weapon"], cursed)
            self.assertIn(plain, game.player.inventory)
            self.assertTrue(
                any("will not come off" in f.text for f in game.floaters)
            )

    def test_remove_curse_scroll_frees_equipped_item(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            cursed = self.cursed_weapon()
            plain = Item("Iron Sword", "weapon", power=5, rarity="Common")
            scroll = Item(
                "Scroll of Remove Curse", "remove_curse", rarity="Magic"
            )
            game.player.inventory[:] = [cursed, plain, scroll]
            game.use_inventory_slot(0)

            game.use_inventory_slot(game.player.inventory.index(scroll))
            self.assertFalse(cursed.cursed)
            self.assertEqual(cursed.rarity, "Rare")
            self.assertNotIn("Tempting Curse", cursed.affixes)
            self.assertNotIn("curse", cursed.affix_tags)
            self.assertAlmostEqual(cursed.move_speed, 0.0)
            self.assertNotIn(scroll, game.player.inventory)

            game.use_inventory_slot(game.player.inventory.index(plain))
            self.assertIs(game.player.equipment["weapon"], plain)

    def test_remove_curse_prefers_equipped_and_survives_no_target(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            bag_cursed = self.cursed_weapon()
            scroll = Item(
                "Scroll of Remove Curse", "remove_curse", rarity="Magic"
            )
            game.player.inventory[:] = [bag_cursed, scroll]
            # No equipped curse: the bag item is cleansed instead.
            game.use_inventory_slot(game.player.inventory.index(scroll))
            self.assertFalse(bag_cursed.cursed)

            # Nothing cursed anywhere: the scarce scroll is not consumed.
            scroll_two = Item(
                "Scroll of Remove Curse", "remove_curse", rarity="Magic"
            )
            game.player.inventory.append(scroll_two)
            game.use_inventory_slot(game.player.inventory.index(scroll_two))
            self.assertIn(scroll_two, game.player.inventory)

    def test_unique_cursed_item_returns_to_unique_rarity(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            relic = Item(
                "Emberbrand",
                "weapon",
                power=12,
                rarity="Cursed",
                cursed=True,
                unique_effect="embers on hit",
                affixes=["Tempting Curse"],
                affix_tags=["curse", "risk"],
                move_speed=-0.03,
            )
            scroll = Item(
                "Scroll of Remove Curse", "remove_curse", rarity="Magic"
            )
            game.player.inventory[:] = [relic, scroll]
            game.use_inventory_slot(0)
            game.use_inventory_slot(game.player.inventory.index(scroll))
            self.assertEqual(relic.rarity, "Unique")


if __name__ == "__main__":
    unittest.main()

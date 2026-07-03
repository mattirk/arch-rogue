from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


from arch_rogue.content import ARCHETYPES, RARITY_PROFILES, SKILL_UPGRADES
from arch_rogue.game import ENEMY_DEFINITIONS, Game
from arch_rogue.models import Enemy, Item


class CombatSkillsLoot22Tests(unittest.TestCase):
    def tearDown(self) -> None:
        pass

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

    def test_content_tables_enemy_traits_and_player_resist_save_roundtrip(
        self,
    ) -> None:
        # Merged from three tests sharing an identical Game fixture
        # (archetype_index=0, seed=2202): content-table / item-save roundtrip,
        # enemy role/resistance/status-speed determinism, and player-resist
        # damage interaction plus saved status/equipment roundtrip.
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            try:
                # --- content tables expose synergy hooks ---
                self.assertIn("Legendary", RARITY_PROFILES)
                upgrade_keys = {upgrade.key for upgrade in SKILL_UPGRADES}
                self.assertTrue(
                    {
                        "warden_aegis",
                        "rogue_venom",
                        "arcanist_permafrost",
                        "acolyte_gravebind",
                        "ranger_beastmark",
                    }.issubset(upgrade_keys)
                )

                # --- item save roundtrip with synergy fields ---
                item = Item(
                    "Synergy Blade",
                    "weapon",
                    power=7,
                    rarity="Legendary",
                    affixes=["Storm-Touched"],
                    damage_type="arcane",
                    skill_bonus="Bolt +1 shard",
                    proc_effect="lifesteal",
                )
                label = item.label
                self.assertIn("arcane", label)
                self.assertIn("Bolt +1 shard", label)
                self.assertIn("lifesteal", label)

                restored = game.item_from_dict(game.item_to_dict(item))
                self.assertIsNotNone(restored)
                assert restored is not None
                self.assertEqual(restored.damage_type, "arcane")
                self.assertEqual(restored.skill_bonus, "Bolt +1 shard")
                self.assertEqual(restored.proc_effect, "lifesteal")

                # --- enemy roles / resistances / status speed determinism ---
                enemy = Enemy(
                    "Venom Skitter",
                    "melee",
                    game.player.x + 2.0,
                    game.player.y,
                    30,
                    30,
                    3.6,
                    7,
                    15,
                    0.95,
                    0.72,
                )
                game._assign_enemy_combat_traits(enemy)
                game.enemies = [enemy]
                self.assertEqual(enemy.role, "flanker")
                self.assertEqual(enemy.damage_type, "poison")
                self.assertGreater(enemy.resistances["poison"], 0)
                self.assertLess(enemy.resistances["fire"], 0)
                self.assertLess(game.mitigate_enemy_damage(enemy, 20, "poison"), 20)
                self.assertGreater(game.mitigate_enemy_damage(enemy, 20, "fire"), 20)

                game.apply_enemy_status(enemy, "chilled", 1.2)
                self.assertLess(game.enemy_speed_multiplier(enemy), 1.0)
                game.update_enemy_statuses(0.6)
                self.assertIn("chilled", enemy.statuses)
                game.update_enemy_statuses(0.7)
                self.assertNotIn("chilled", enemy.statuses)

                # --- player resists interact with damage type, statuses persist ---
                game.enemies = []
                game.player.equipment["armor"] = Item(
                    "Grounded Mail",
                    "armor",
                    defense=6,
                    rarity="Rare",
                    affixes=["Grounded"],
                    damage_type="arcane",
                    skill_bonus="Nova ward",
                    proc_effect="thorns",
                )
                arcane_taken = game.take_player_damage(
                    30, source="projectile", damage_type="arcane"
                )
                physical_taken = game.take_player_damage(
                    30, source="projectile", damage_type="physical"
                )
                self.assertLess(arcane_taken, physical_taken)

                game.player.status_effects["aegis"] = 0.5
                self.assertTrue(game.save_run())
                loaded = Game(
                    screen_size=(820, 540),
                    headless=True,
                    save_path=game.save_path,
                )
                self.assertTrue(loaded.load_run(), loaded.last_load_error)
                self.assertIn("aegis", loaded.player.status_effects)
                loaded_armor = loaded.player.equipment["armor"]
                self.assertIsNotNone(loaded_armor)
                assert loaded_armor is not None
                self.assertEqual(loaded_armor.proc_effect, "thorns")
            finally:
                pass

    def test_bolt_projectiles_carry_damage_types_statuses_and_skill_bonus_shards(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, archetype_index=2)
            try:
                game.projectiles.clear()
                # Milestone 3.7: Arc Bolt is a single shot unless the Bolt
                # branch is committed; grant the branch entry node so the
                # multi-bolt fan (plus the equipment shard bonus) is exercised.
                game.player.skill_upgrades.append("arcanist_splinter")
                game.player.skill_upgrades.append("arcanist_permafrost")
                game.player.equipment["weapon"] = Item(
                    "Frost Test Wand",
                    "weapon",
                    power=3,
                    rarity="Rare",
                    damage_type="frost",
                    skill_bonus="Bolt +1 shard",
                    proc_effect="chill",
                )
                game.player.mana = game.player.max_mana
                game.player.bolt_timer = 0.0
                game.player.facing_x = 1.0
                game.player.facing_y = 0.0

                game.player_cast_bolt()

                self.assertGreaterEqual(len(game.projectiles), 4)
                self.assertTrue(
                    all(
                        projectile.damage_type == "frost"
                        for projectile in game.projectiles
                    )
                )
                self.assertTrue(
                    all(
                        projectile.status_effect == "chilled"
                        for projectile in game.projectiles
                    )
                )
                self.assertTrue(
                    all(
                        projectile.status_duration >= 1.4
                        for projectile in game.projectiles
                    )
                )
            finally:
                pass

    def test_damage_enemy_applies_resistance_status_and_lifesteal_proc(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, archetype_index=1)
            try:
                enemy = Enemy(
                    "Crypt Brute",
                    "melee",
                    game.player.x + 1.0,
                    game.player.y,
                    80,
                    80,
                    1.7,
                    12,
                    20,
                    1.0,
                    1.0,
                    resistances={"physical": 0.50, "shadow": -0.20},
                )
                game.enemies = [enemy]
                game.player.hp = game.player.max_hp - 10
                game.player.equipment["weapon"] = Item(
                    "Leeching Knife",
                    "weapon",
                    power=4,
                    rarity="Rare",
                    damage_type="shadow",
                    proc_effect="lifesteal",
                )

                before_hp = game.player.hp
                game.damage_enemy(
                    enemy,
                    20,
                    knockback_from=(1.0, 0.0),
                    damage_type="physical",
                    status_effect="poisoned",
                    status_duration=2.0,
                )

                self.assertEqual(enemy.hp, 70)
                self.assertIn("poisoned", enemy.statuses)
                self.assertGreater(game.player.hp, before_hp)

                game.damage_enemy(
                    enemy, 20, knockback_from=(1.0, 0.0), damage_type="shadow"
                )
                self.assertLessEqual(enemy.hp, 46)
            finally:
                pass

    def test_new_enemy_roster_has_unique_sprites(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            try:
                enemy_names = {definition.name for definition in ENEMY_DEFINITIONS}
                for name in {
                    "Ash Hound",
                    "Rune Sentinel",
                    "Plague Toad",
                    "Hollow Knight",
                }:
                    self.assertIn(name, enemy_names)
                    self.assertIn(name, game.sprites.enemies)
                self.assertGreaterEqual(len(game.sprites.enemies), len(enemy_names))
            finally:
                pass


if __name__ == "__main__":
    unittest.main()

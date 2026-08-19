from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import arch_rogue
import pygame  # noqa: F401  (required to initialize pygame subsystems in tests)

from arch_rogue.content import (
    ARCHETYPES,
    discipline_by_key,
    disciplines_for_archetype,
)
from arch_rogue.game import Game
from arch_rogue.models import Enemy, Projectile, Room, Tile


def _make_enemy(x: float, y: float, hp: int = 200) -> Enemy:
    return Enemy(
        "Test Dummy",
        "melee",
        x,
        y,
        hp,
        hp,
        1.0,
        6,
        12,
        1.0,
        1.0,
    )


class SkillPathVariability37Tests(unittest.TestCase):
    def make_game(self, tmpdir, archetype_index=0, seed=3701) -> Game:
        game = Game(
            screen_size=(960, 600),
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

    # --- choose_discipline enforces the two-path limit ---------------

    def test_choose_discipline_enforces_two_path_limit(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, archetype_index=0)
            try:
                game.player.memory_tokens = 10

                # Commit to Bulwark and Riposte (two degree-1 entries).
                self.assertTrue(game.choose_discipline("warden_bulwark"))
                self.assertTrue(game.choose_discipline("warden_riposte"))

                # Degree-1 entries of the other two paths must be rejected.
                self.assertFalse(game.choose_discipline("warden_smite"))
                self.assertFalse(game.choose_discipline("warden_ward"))

                # available_disciplines excludes Vow/Fortress degree-1 nodes
                # but still offers deeper nodes in committed paths.
                choices = game.available_disciplines()
                choice_keys = {node.key for node in choices}
                self.assertNotIn("warden_smite", choice_keys)
                self.assertNotIn("warden_ward", choice_keys)
                self.assertIn("warden_aegis", choice_keys)  # Bulwark Degree 2
                self.assertIn("warden_counter", choice_keys)  # Riposte Degree 2
            finally:
                pass

    # --- discipline_state distinguishes path_locked vs locked ----------

    def test_discipline_state_reports_path_locked(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, archetype_index=0)
            try:
                game.player.memory_tokens = 10

                smite = discipline_by_key("warden_smite")
                self.assertIsNotNone(smite)
                # Before any commitment Vow Degree 1 is simply available.
                self.assertEqual(game.discipline_state(smite), "available")

                # A prereq-locked node (Bulwark Degree 2 before Bulwark Degree 1) is "locked".
                aegis = discipline_by_key("warden_aegis")
                self.assertIsNotNone(aegis)
                self.assertEqual(game.discipline_state(aegis), "locked")

                # Commit to two paths -> Vow becomes path_locked.
                self.assertTrue(game.choose_discipline("warden_bulwark"))
                self.assertTrue(game.choose_discipline("warden_riposte"))
                self.assertEqual(game.discipline_state(smite), "path_locked")
            finally:
                pass

    # --- Arc Bolt fan + pierce + homing progression ----------------------

    def test_arc_bolt_multi_shot_with_splinter_and_pierce_homing_progression(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, archetype_index=2)
            try:
                # splinter Degree 1 -> 2 bolts (one extra shard)
                game.player.skill_upgrades.append("arcanist_splinter")
                game.projectiles.clear()
                game.player.mana = game.player.max_mana
                game.player.bolt_timer = 0.0
                game.player.facing_x = 1.0
                game.player.facing_y = 0.0
                game.player_cast_bolt()
                self.assertEqual(len(game.projectiles), 2)
                self.assertTrue(all(p.pierce == 0 for p in game.projectiles))

                # + overload Degree 2 -> a 3-bolt fan and pierce 1
                game.player.skill_upgrades.append("arcanist_overload")
                game.projectiles.clear()
                game.player.bolt_timer = 0.0
                game.player.mana = game.player.max_mana
                game.player_cast_bolt()
                self.assertEqual(len(game.projectiles), 3)
                self.assertTrue(all(p.pierce == 1 for p in game.projectiles))

                # + pierce Degree 3 -> pierce ramps to 2 (bolt count unchanged)
                game.player.skill_upgrades.append("arcanist_pierce")
                game.projectiles.clear()
                game.player.bolt_timer = 0.0
                game.player.mana = game.player.max_mana
                game.player_cast_bolt()
                self.assertEqual(len(game.projectiles), 3)
                self.assertTrue(all(p.pierce == 2 for p in game.projectiles))

                # + arc tyrant capstone -> homing
                game.player.skill_upgrades.append("arcanist_arc_tyrant")
                game.projectiles.clear()
                game.player.bolt_timer = 0.0
                game.player.mana = game.player.max_mana
                game.player_cast_bolt()
                self.assertTrue(all(p.homing > 0.0 for p in game.projectiles))
                self.assertAlmostEqual(game.projectiles[0].homing, 0.85, places=2)
            finally:
                pass

        # overload alone (prereqs bypassed via direct append) -> 3 bolts, pierce 1.
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, archetype_index=2)
            try:
                game.player.skill_upgrades.append("arcanist_overload")
                game.projectiles.clear()
                game.player.mana = game.player.max_mana
                game.player.bolt_timer = 0.0
                game.player.facing_x = 1.0
                game.player.facing_y = 0.0
                game.player_cast_bolt()
                # Overload splits the bolt into a 3-shot fan and grants pierce 1
                # even without splinter (prereqs bypassed via direct append).
                self.assertEqual(len(game.projectiles), 3)
                self.assertTrue(all(p.pierce == 1 for p in game.projectiles))
            finally:
                pass

    # --- Warden Shield Bash: gradual cleave ramp (1/2/3 foes) -----------

    def test_warden_melee_single_target_without_bulwark(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, archetype_index=0)
            try:
                px, py = game.player.x, game.player.y
                game.player.facing_x = 1.0
                game.player.facing_y = 0.0
                near = _make_enemy(px + 0.6, py, hp=200)
                far = _make_enemy(px + 1.0, py, hp=200)
                game.enemies = [near, far]

                # Both enemies are inside the melee arc.
                arc = game.enemies_in_melee_arc()
                self.assertEqual(len(arc), 2)
                self.assertIn(near, arc)
                self.assertIn(far, arc)

                # Base Shield Bash only hits one foe.
                game.player.melee_timer = 0.0
                game.player.stamina = game.player.max_stamina
                game.player_melee_attack()
                self.assertLess(near.hp, 200)
                self.assertEqual(far.hp, 200)

                # Bulwark Degree 1 unlocks the cleave arc -> both foes hit.
                game.player.skill_upgrades.append("warden_bulwark")
                near.hp = 200
                far.hp = 200
                game.player.melee_timer = 0.0
                game.player.stamina = game.player.max_stamina
                game.player_melee_attack()
                self.assertLess(near.hp, 200)
                self.assertLess(far.hp, 200)

                # Aegis Degree 2 widens the cleave arc to 3 foes; add a third enemy.
                game.player.skill_upgrades.append("warden_aegis")
                third = _make_enemy(px + 1.4, py, hp=200)
                game.enemies = [near, far, third]
                near.hp = 200
                far.hp = 200
                third.hp = 200
                # The third enemy is within the extended reach (1.55 + 0.28).
                self.assertIn(third, game.enemies_in_melee_arc())
                game.player.melee_timer = 0.0
                game.player.stamina = game.player.max_stamina
                game.player_melee_attack()
                self.assertLess(near.hp, 200)
                self.assertLess(far.hp, 200)
                self.assertLess(third.hp, 200)
            finally:
                pass

    # --- Acolyte lifesteal gated behind Sanguine (melee + spell) -------

    def test_acolyte_lifesteal_gated_behind_sanguine(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, archetype_index=3)
            try:
                px, py = game.player.x, game.player.y
                enemy = _make_enemy(px + 0.8, py, hp=9999)
                game.enemies = [enemy]
                game.player.facing_x = 1.0
                game.player.facing_y = 0.0

                # Helper ramps one step per Blood degree; base leech is 0.
                self.assertEqual(game._acolyte_melee_leech(), 0)
                self.assertEqual(game._acolyte_spell_leech(), 0)

                # --- Melee: no sanguine -> no leech ---
                game.player.hp = game.player.max_hp - 20
                hp_before = game.player.hp
                game.player.melee_timer = 0.0
                game.player.stamina = game.player.max_stamina
                game.player_melee_attack()
                self.assertEqual(game.player.hp, hp_before)

                # --- Melee: with sanguine -> leech applies (degree 1 = 2) ---
                game.player.skill_upgrades.append("acolyte_sanguine")
                self.assertEqual(game._acolyte_melee_leech(), 2)
                game.player.hp = game.player.max_hp - 20
                hp_before = game.player.hp
                game.player.melee_timer = 0.0
                game.player.stamina = game.player.max_stamina
                game.player_melee_attack()
                self.assertGreater(game.player.hp, hp_before)

                # --- Spirit Call: no sanguine -> familiar hit has no leech ---
                game.player.skill_upgrades.remove("acolyte_sanguine")
                self.assertEqual(game._acolyte_spell_leech(), 0)
                enemy2 = _make_enemy(px + 1.0, py, hp=9999)
                game.enemies = [enemy2]
                game.player.hp = game.player.max_hp - 20
                hp_before = game.player.hp
                game.player.class_skill_timer = 0.0
                game.player.mana = game.player.max_mana
                game.player_cast_spirit_call()
                game._familiar_attack(game.familiars[0], enemy2)
                self.assertEqual(game.player.hp, hp_before)

                # --- Spirit Call: with sanguine -> familiar leech applies ---
                game.player.skill_upgrades.append("acolyte_sanguine")
                self.assertEqual(game._acolyte_spell_leech(), 3)
                enemy3 = _make_enemy(px + 1.0, py, hp=9999)
                game.enemies = [enemy3]
                game.player.hp = game.player.max_hp - 20
                hp_before = game.player.hp
                game.player.class_skill_timer = 0.0
                game.player.mana = game.player.max_mana
                game.player_cast_spirit_call()
                game._familiar_attack(game.familiars[0], enemy3)
                self.assertGreater(game.player.hp, hp_before)

                # --- Blood Pact Degree 3 ramps melee leech to 4 (gradual degree step) ---
                game.player.skill_upgrades.append("acolyte_blood_pact")
                self.assertEqual(game._acolyte_melee_leech(), 4)
                self.assertEqual(game._acolyte_spell_leech(), 5)
            finally:
                pass


class ArcBoltStormPathTests(unittest.TestCase):
    """The Arcanist Storm path is Arc Bolt's chaining route."""

    STATS_ONLY_DESCRIPTIONS = {
        "warden_counter": "Improves melee power and stamina reserves.",
        "warden_riposte_edge": "Further improves melee power and armor.",
        "warden_iron_vow": (
            "Greatly strengthens armor, vitality, and stamina reserves."
        ),
        "warden_reckoning": (
            "Improves melee power, Guard Bolt damage, and mana reserves."
        ),
        "warden_unbreakable": (
            "Grants the path's greatest armor and vitality boost, with deeper "
            "stamina reserves."
        ),
        "warden_final_reckoning": (
            "Greatly improves melee power, Guard Bolt damage, and stamina "
            "reserves."
        ),
        "warden_smite": "Strengthens Guard Bolt and expands mana reserves.",
        "warden_judgment": (
            "Further strengthens Guard Bolt and mana reserves."
        ),
        "warden_consecrate": "Deepens Guard Bolt damage and mana reserves.",
        "warden_divine_wrath": (
            "Greatly strengthens Guard Bolt and mana reserves."
        ),
        "warden_avatar_of_light": (
            "Grants the path's greatest Guard Bolt and mana boost while "
            "strengthening vitality."
        ),
        "rogue_shadowstep": (
            "Expands stamina reserves and quickens your stride."
        ),
        "rogue_phantom": (
            "Expands stamina reserves and quickens your stride."
        ),
        # 4.11.0 rebalance: the Marksman path buffs the bolt (spell_bonus is
        # Bolt's damage stat, mirroring the Warden's Guard Bolt paths) and
        # grants smaller stamina reserves than before.
        "rogue_marksman": (
            "Improves bolt damage, melee power, and stamina reserves."
        ),
        "rogue_sharpshot": (
            "Further improves bolt damage, melee power, and stamina reserves."
        ),
        "rogue_deadeye": (
            "Greatly improves bolt damage, melee power, and stamina reserves."
        ),
        "rogue_eagle_eye": (
            "Further improves bolt damage, melee power, and stamina reserves."
        ),
        "rogue_assassin": (
            "Grants the path's greatest bolt and melee power boost, with "
            "deeper stamina reserves."
        ),
        # 5.0: "arcanist_ward" left this table — Arcane Ward now also
        # grants mana regen (combat.costs.MANA_REGEN_UPGRADES).
        "arcanist_ward_mend": (
            "Strengthens armor, vitality, and mana reserves."
        ),
        "arcanist_ward_overload": (
            "Strengthens armor, spellcraft, and mana reserves."
        ),
        "arcanist_aegis": (
            "Greatly strengthens armor, vitality, and mana reserves."
        ),
        "arcanist_eternal_aegis": (
            "Further strengthens armor, vitality, and mana reserves."
        ),
        "acolyte_ashen": "Strengthens armor and mana reserves.",
        "acolyte_spirit_host": "Improves spellcraft and mana reserves.",
        "acolyte_grave_chorus": (
            "Strengthens armor, spellcraft, and mana reserves."
        ),
        "acolyte_undying_veil": (
            "Further strengthens armor, spellcraft, and mana reserves."
        ),
        # 5.0: "acolyte_curse" left this table — Hex now also grants mana
        # regen (combat.costs.MANA_REGEN_UPGRADES).
        "acolyte_decay": "Further improves spellcraft and mana reserves.",
        "acolyte_fragility": "Deepens spellcraft and mana reserves.",
        "acolyte_doom": "Greatly improves spellcraft and mana reserves.",
        "acolyte_eternal_doom": (
            "Brings spellcraft and mana reserves to their peak."
        ),
        "ranger_thornfield": "Improves spellcraft and stamina reserves.",
        "ranger_hunter_drive": (
            "Improves melee power and stamina reserves, and quickens your "
            "stride."
        ),
        "ranger_wild_domination": (
            "Improves spellcraft and stamina reserves, and quickens your "
            "stride."
        ),
        "ranger_survival": "Strengthens vitality and stamina reserves.",
        "ranger_camouflage": (
            "Expands stamina reserves and quickens your stride."
        ),
        "ranger_pathfinder": "Improves spellcraft and stamina reserves.",
        "ranger_ambush": (
            "Improves melee power and stamina reserves, and quickens your "
            "stride."
        ),
        "ranger_ghost_step": (
            "Strengthens vitality and stamina reserves, and quickens your "
            "stride."
        ),
    }

    STORM_PATH = (
        "arcanist_charge",
        "arcanist_chain_lightning",
        "arcanist_tempest",
        "arcanist_storm_caller",
        "arcanist_world_storm",
    )

    def make_game(self, tmpdir, seed=3703) -> Game:
        game = Game(
            screen_size=(960, 600),
            headless=True,
            save_path=Path(tmpdir) / "run.json",
        )
        game.options_path = Path(tmpdir) / "options.json"
        game.rng.seed(seed)
        game.restart(ARCHETYPES[2])  # Arcanist
        if game.story_intro_pending:
            self.assertTrue(game.choose_story_relic_path(0))
        game.active_cutscene = None
        # Starter gear must not add bolt shards, procs, or cast speed to these
        # discipline-only comparisons.
        game.player.equipment = {
            slot: None for slot in game.player.equipment
        }
        return game

    @staticmethod
    def open_test_area(game: Game) -> None:
        for tx in range(16, 40):
            for ty in range(16, 26):
                game.dungeon.tiles[tx][ty] = Tile.FLOOR

    @staticmethod
    def chain_projectile(x: float, y: float, damage: int = 100) -> Projectile:
        return Projectile(
            x,
            y,
            0.0,
            0.0,
            damage,
            "player",
            (92, 170, 255),
            damage_type="arcane",
            archetype="Arcanist",
        )

    def resolve_chain(
        self,
        game: Game,
        upgrades: tuple[str, ...],
        primary: Enemy,
        targets: list[Enemy],
    ) -> list[Enemy]:
        game.player.skill_upgrades[:] = upgrades
        game.enemies = [primary, *targets]
        projectile = self.chain_projectile(primary.x, primary.y)
        game._maybe_chain_lightning(projectile, primary)
        return [target for target in targets if target.hp < target.max_hp]

    def test_bolt_and_storm_content_contract_and_bonuses(self) -> None:
        bolt_nodes = tuple(
            node
            for node in disciplines_for_archetype("Arcanist")
            if node.path == "Bolt"
        )
        self.assertEqual(
            tuple(
                (node.key, node.name, node.degree, node.description)
                for node in bolt_nodes
            ),
            (
                (
                    "arcanist_splinter",
                    "Splintered Arcana",
                    1,
                    "Arc Bolt splinters into longer-lived shards.",
                ),
                (
                    "arcanist_overload",
                    "Arc Overload",
                    2,
                    "Arc Bolt erupts in a piercing fan.",
                ),
                (
                    "arcanist_pierce",
                    "Piercing Arc",
                    3,
                    "Arc Bolts pierce deeper through enemy ranks.",
                ),
                (
                    "arcanist_storm",
                    "Conduit Sigil",
                    4,
                    "Piercing Arc Bolts retain more force after passing "
                    "through foes.",
                ),
                (
                    "arcanist_arc_tyrant",
                    "Arc Tyrant",
                    5,
                    "Arc Bolts home toward the nearest unhit foe.",
                ),
            ),
        )

        nodes = tuple(
            node
            for node in disciplines_for_archetype("Arcanist")
            if node.path == "Storm"
        )
        self.assertEqual(
            tuple(
                (
                    node.key,
                    node.name,
                    node.degree,
                    node.prerequisites,
                    node.spell_bonus,
                    node.max_mana_bonus,
                )
                for node in nodes
            ),
            (
                ("arcanist_charge", "Static Charge", 1, (), 2, 8),
                (
                    "arcanist_chain_lightning",
                    "Chain Lightning",
                    2,
                    ("arcanist_charge",),
                    2,
                    8,
                ),
                (
                    "arcanist_tempest",
                    "Tempest",
                    3,
                    ("arcanist_chain_lightning",),
                    3,
                    10,
                ),
                (
                    "arcanist_storm_caller",
                    "Stormcaller",
                    4,
                    ("arcanist_tempest",),
                    4,
                    12,
                ),
                (
                    "arcanist_world_storm",
                    "World Storm",
                    5,
                    ("arcanist_storm_caller",),
                    5,
                    14,
                ),
            ),
        )
        self.assertEqual(sum(node.spell_bonus for node in nodes), 16)
        self.assertEqual(sum(node.max_mana_bonus for node in nodes), 52)
        self.assertEqual(
            tuple(node.description for node in nodes),
            (
                "Arc Bolt costs less mana.",
                "The cast's shared Storm charge arcs from the earliest Arc "
                "Bolt impact to a nearby foe at reduced damage.",
                "The Storm chain reaches farther and continues through more "
                "foes.",
                "The Storm chain reaches farther, strikes more foes, and "
                "prioritizes elite, miniboss, and boss prey.",
                "The Storm chain reaches its greatest range and breadth while "
                "retaining elite priority.",
            ),
        )

        # The Degree-4 Bolt node keeps its stable save/glyph key, but its
        # display name and copy no longer collide with Storm's chain identity.
        conduit = discipline_by_key("arcanist_storm")
        self.assertIsNotNone(conduit)
        assert conduit is not None
        self.assertEqual(
            (conduit.key, conduit.name, conduit.path, conduit.degree),
            ("arcanist_storm", "Conduit Sigil", "Bolt", 4),
        )
        self.assertIn("pierc", conduit.description.casefold())
        self.assertNotIn("chain", conduit.description.casefold())

    def test_all_discipline_descriptions_are_qualitative(self) -> None:
        numeric_copy = re.compile(
            r"\d|\b(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|"
            r"first|second|third|fourth|fifth)\b",
            re.IGNORECASE,
        )
        for archetype in ARCHETYPES:
            for node in disciplines_for_archetype(archetype.name):
                with self.subTest(numeric_description=node.key):
                    self.assertIsNone(numeric_copy.search(node.description))

    def test_stats_only_disciplines_claim_only_applied_stats(self) -> None:
        actual = {
            node.key: node.description
            for archetype in ARCHETYPES
            for node in disciplines_for_archetype(archetype.name)
            if node.key in self.STATS_ONLY_DESCRIPTIONS
        }
        self.assertEqual(actual, self.STATS_ONLY_DESCRIPTIONS)

    def test_static_charge_reduces_bolt_mana_cost_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            self.assertEqual(game.bolt_mana_cost(), 7)
            base_cooldown = game.bolt_cooldown()

            game.player.skill_upgrades.append("arcanist_focus")
            self.assertEqual(game.bolt_mana_cost(), 7)

            game.player.skill_upgrades.append("arcanist_charge")

            self.assertEqual(game.bolt_mana_cost(), 6)
            self.assertEqual(game.bolt_cooldown(), base_cooldown)

    def test_chain_ladder_caps_targets_and_keeps_fixed_damage(self) -> None:
        tiers = (
            (self.STORM_PATH[:1], 0),
            (self.STORM_PATH[:2], 1),
            (self.STORM_PATH[:3], 2),
            (self.STORM_PATH[:4], 3),
            (self.STORM_PATH, 4),
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            self.open_test_area(game)
            for upgrades, expected_hits in tiers:
                with self.subTest(degree=len(upgrades)):
                    primary = _make_enemy(18.5, 20.5, hp=500)
                    # Six sequentially reachable foes prove both the degree
                    # cap and World Storm's four-target ceiling.
                    targets = [
                        _make_enemy(18.5 + 1.5 * step, 20.5, hp=500)
                        for step in range(1, 7)
                    ]
                    damaged = self.resolve_chain(
                        game, upgrades, primary, targets
                    )
                    self.assertEqual(len(damaged), expected_hits)
                    for target in damaged:
                        # Chain damage is fixed from the original projectile,
                        # not recursively reduced from the previous jump.
                        self.assertEqual(target.max_hp - target.hp, 55)

    def test_chain_reach_grows_at_each_degree(self) -> None:
        tiers = (
            (self.STORM_PATH[:2], 2.6),
            (self.STORM_PATH[:3], 2.8),
            (self.STORM_PATH[:4], 3.2),
            (self.STORM_PATH, 3.6),
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            self.open_test_area(game)
            for upgrades, reach in tiers:
                with self.subTest(degree=len(upgrades), case="inside"):
                    primary = _make_enemy(20.5, 20.5, hp=500)
                    inside = _make_enemy(
                        primary.x + reach - 0.05, primary.y, hp=500
                    )
                    self.assertEqual(
                        self.resolve_chain(game, upgrades, primary, [inside]),
                        [inside],
                    )

                with self.subTest(degree=len(upgrades), case="outside"):
                    primary = _make_enemy(20.5, 20.5, hp=500)
                    outside = _make_enemy(
                        primary.x + reach + 0.05, primary.y, hp=500
                    )
                    self.assertEqual(
                        self.resolve_chain(game, upgrades, primary, [outside]),
                        [],
                    )

    def test_stormcaller_prioritizes_elites_and_bosses(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            self.open_test_area(game)
            primary = _make_enemy(20.5, 20.5, hp=500)
            normals = [
                _make_enemy(20.9, 20.5, hp=500),
                _make_enemy(20.5, 20.9, hp=500),
                _make_enemy(20.1, 20.5, hp=500),
                _make_enemy(20.5, 20.1, hp=500),
            ]
            boss = _make_enemy(23.3, 20.5, hp=500)
            boss.kind = "boss"
            elite = _make_enemy(23.5, 20.5, hp=500)
            elite.elite_modifier = "Runed"

            damaged = self.resolve_chain(
                game,
                self.STORM_PATH[:4],
                primary,
                [*normals, boss, elite],
            )

            self.assertEqual(len(damaged), 3)
            self.assertIn(boss, damaged)
            self.assertIn(elite, damaged)
            self.assertEqual(
                sum(normal in damaged for normal in normals),
                1,
            )

    def test_splinter_shards_share_storm_charge_until_first_hit(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            self.open_test_area(game)
            game.player.skill_upgrades[:] = [
                "arcanist_splinter",
                "arcanist_charge",
                "arcanist_chain_lightning",
            ]
            game.player.x, game.player.y = 18.5, 20.5
            game.player.facing_x, game.player.facing_y = 1.0, 0.0
            game.player.mana = game.player.max_mana
            game.player.bolt_timer = 0.0

            game.player_cast_bolt()
            self.assertEqual(len(game.projectiles), 2)
            first_shard, second_shard = game.projectiles
            charge = first_shard.storm_chain_charge
            self.assertIsNotNone(charge)
            assert charge is not None
            self.assertIs(second_shard.storm_chain_charge, charge)
            self.assertFalse(charge.spent)

            # The old fixed-carrier design assigned Storm to the first shard.
            # Resolve only the second shard to prove that a missed sibling no
            # longer discards the cast's one chain.
            primary = _make_enemy(20.5, 20.5, hp=500)
            secondary = _make_enemy(22.0, 20.5, hp=500)
            game.enemies = [primary, secondary]
            game.projectiles = [second_shard]
            second_shard.x, second_shard.y = primary.x, primary.y
            second_shard.vx = second_shard.vy = 0.0
            expected_chain_damage = int(second_shard.damage * 0.55)

            game.update_projectiles(0.01)

            self.assertTrue(charge.spent)
            self.assertLess(primary.hp, primary.max_hp)
            self.assertEqual(
                secondary.max_hp - secondary.hp,
                expected_chain_damage,
            )

    def test_multishot_cast_shares_one_storm_charge_after_piercing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            self.open_test_area(game)
            game.player.skill_upgrades[:] = [
                "arcanist_splinter",
                "arcanist_overload",
                "arcanist_pierce",
                "arcanist_storm",
                "arcanist_arc_tyrant",
                *self.STORM_PATH,
            ]
            game.player.x, game.player.y = 18.5, 20.5
            game.player.facing_x, game.player.facing_y = 1.0, 0.0
            game.player.mana = game.player.max_mana
            game.player.bolt_timer = 0.0

            # This is a real three-shot Overload cast. All bolts pierce twice,
            # home, and share exactly one cast-level World Storm payload.
            game.player_cast_bolt()
            self.assertEqual(len(game.projectiles), 3)
            self.assertTrue(
                all(projectile.pierce == 2 for projectile in game.projectiles)
            )
            self.assertTrue(
                all(
                    projectile.storm_chain_charge is not None
                    for projectile in game.projectiles
                )
            )
            charge = game.projectiles[0].storm_chain_charge
            assert charge is not None
            self.assertTrue(
                all(
                    projectile.storm_chain_charge is charge
                    for projectile in game.projectiles
                )
            )
            self.assertFalse(charge.spent)
            self.assertTrue(
                all(
                    abs(projectile.homing - 0.85) < 0.001
                    for projectile in game.projectiles
                )
            )
            first_hit_bolt = max(game.projectiles, key=lambda p: p.damage)
            first_hit_damage = first_hit_bolt.damage

            primary = _make_enemy(20.5, 20.5, hp=500)
            first_chain = [
                _make_enemy(20.5 + 1.5 * step, 20.5, hp=500)
                for step in range(1, 5)
            ]
            later_pierce = _make_enemy(34.5, 20.5, hp=500)
            second_chain_candidates = [
                _make_enemy(35.5 + step, 20.5, hp=500)
                for step in range(3)
            ]
            game.enemies = [
                primary,
                *first_chain,
                later_pierce,
                *second_chain_candidates,
            ]

            # Resolve only the center bolt. Its first direct impact spends the
            # shared World Storm charge and reaches the four-target cap.
            game.projectiles = [first_hit_bolt]
            first_hit_bolt.x, first_hit_bolt.y = primary.x, primary.y
            first_hit_bolt.vx = first_hit_bolt.vy = 0.0
            game.update_projectiles(0.01)
            self.assertTrue(charge.spent)
            self.assertLess(primary.hp, primary.max_hp)
            self.assertTrue(
                all(enemy.hp < enemy.max_hp for enemy in first_chain)
            )
            self.assertTrue(
                all(
                    enemy.max_hp - enemy.hp == int(first_hit_damage * 0.55)
                    for enemy in first_chain
                )
            )
            self.assertEqual(later_pierce.hp, later_pierce.max_hp)
            self.assertTrue(
                all(
                    enemy.hp == enemy.max_hp
                    for enemy in second_chain_candidates
                )
            )

            # The bolt survives by piercing. Its next direct hit deals damage,
            # but cannot emit the full chain a second time.
            self.assertEqual(game.projectiles, [first_hit_bolt])
            first_hit_bolt.x, first_hit_bolt.y = (
                later_pierce.x,
                later_pierce.y,
            )
            first_hit_bolt.vx = first_hit_bolt.vy = 0.0
            game.update_projectiles(0.01)
            self.assertLess(later_pierce.hp, later_pierce.max_hp)
            self.assertTrue(
                all(
                    enemy.hp == enemy.max_hp
                    for enemy in second_chain_candidates
                )
            )

    def test_arc_tyrant_ignores_dead_and_already_hit_targets(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            self.open_test_area(game)
            projectile = Projectile(
                20.5,
                20.5,
                9.0,
                0.0,
                100,
                "player",
                (92, 170, 255),
                homing=0.85,
            )
            already_hit = _make_enemy(21.0, 20.5, hp=500)
            dead = _make_enemy(20.5, 19.0, hp=1)
            dead.hp = 0
            fresh = _make_enemy(20.5, 22.0, hp=500)
            projectile.hit_enemies.add(id(already_hit))
            game.enemies = [already_hit, dead, fresh]

            game._steer_homing_projectile(projectile, 0.1)

            self.assertGreater(projectile.vy, 0.0)

    def test_arc_tyrant_ignores_nearer_enemy_behind_wall(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            self.open_test_area(game)
            projectile = Projectile(
                20.5,
                20.5,
                9.0,
                0.0,
                100,
                "player",
                (92, 170, 255),
                homing=0.85,
            )
            hidden = _make_enemy(20.5, 22.5, hp=500)
            visible = _make_enemy(22.5, 18.5, hp=500)
            game.dungeon.tiles[20][21] = Tile.WALL
            game.enemies = [hidden, visible]
            self.assertFalse(
                game.dungeon.line_of_sight(
                    projectile.x,
                    projectile.y,
                    hidden.x,
                    hidden.y,
                )
            )
            self.assertTrue(
                game.dungeon.line_of_sight(
                    projectile.x,
                    projectile.y,
                    visible.x,
                    visible.y,
                )
            )

            game._steer_homing_projectile(projectile, 0.1)

            self.assertLess(projectile.vy, 0.0)

    def test_piercing_bolt_collision_skips_an_already_hit_body(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            self.open_test_area(game)
            already_hit = _make_enemy(20.5, 20.5, hp=500)
            fresh = _make_enemy(20.5, 20.5, hp=500)
            projectile = Projectile(
                20.5,
                20.5,
                0.0,
                0.0,
                100,
                "player",
                (92, 170, 255),
                damage_type="arcane",
                archetype="Arcanist",
                pierce=1,
                owner_id=game.player.player_id,
            )
            projectile.hit_enemies.add(id(already_hit))
            game.enemies = [already_hit, fresh]
            game.projectiles = [projectile]

            game.update_projectiles(0.01)

            self.assertEqual(already_hit.hp, already_hit.max_hp)
            self.assertLess(fresh.hp, fresh.max_hp)

    def test_conduit_sigil_preserves_more_piercing_bolt_damage(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            self.open_test_area(game)

            def damage_after_first_pierce(upgrades: list[str]) -> int:
                game.player.skill_upgrades[:] = upgrades
                target = _make_enemy(20.5, 20.5, hp=500)
                game.enemies = [target]
                game.projectiles = [
                    Projectile(
                        target.x,
                        target.y,
                        0.0,
                        0.0,
                        100,
                        "player",
                        (92, 170, 255),
                        damage_type="arcane",
                        archetype="Arcanist",
                        pierce=1,
                        owner_id=game.player.player_id,
                    )
                ]
                game.update_projectiles(0.01)
                self.assertEqual(len(game.projectiles), 1)
                return game.projectiles[0].damage

            self.assertEqual(damage_after_first_pierce([]), 70)
            self.assertEqual(
                damage_after_first_pierce(["arcanist_storm"]),
                82,
            )

    def test_492_storm_stats_migrate_once_across_493_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            base_spell = game.player.spell_bonus
            base_max_mana = game.player.max_mana

            # Build the aggregate stats that a fully mastered Storm path stored
            # under 4.9.2: +20 spell and +56 maximum/current mana.
            game.player.skill_upgrades[:] = list(self.STORM_PATH)
            game.player.spell_bonus = base_spell + 20
            game.player.max_mana = base_max_mana + 56
            game.player.mana = game.player.max_mana
            self.assertTrue(game.save_run())
            old_save = json.loads(game.save_path.read_text(encoding="utf-8"))
            old_save["release"] = "4.9.2"
            game.save_path.write_text(
                json.dumps(old_save),
                encoding="utf-8",
            )

            migrated = Game(
                screen_size=(960, 600),
                headless=True,
                save_path=game.save_path,
            )
            migrated.options_path = Path(tmpdir) / "options_migrated.json"
            self.assertTrue(migrated.load_run(), migrated.last_load_error)
            expected_stats = (
                base_spell + 16,
                base_max_mana + 52,
                float(base_max_mana + 52),
            )
            self.assertEqual(
                (
                    migrated.player.spell_bonus,
                    migrated.player.max_mana,
                    migrated.player.mana,
                ),
                expected_stats,
            )

            # Saving stamps the current release. Loading that roundtrip must
            # not apply the old-save reconciliation a second time.
            self.assertTrue(migrated.save_run())
            roundtrip_save = json.loads(
                migrated.save_path.read_text(encoding="utf-8")
            )
            self.assertEqual(roundtrip_save["release"], arch_rogue.__version__)
            roundtrip = Game(
                screen_size=(960, 600),
                headless=True,
                save_path=migrated.save_path,
            )
            roundtrip.options_path = Path(tmpdir) / "options_roundtrip.json"
            self.assertTrue(roundtrip.load_run(), roundtrip.last_load_error)
            self.assertEqual(
                (
                    roundtrip.player.spell_bonus,
                    roundtrip.player.max_mana,
                    roundtrip.player.mana,
                ),
                expected_stats,
            )


class FrostNovaWideningTests(unittest.TestCase):
    """Frost Nova widening: the Nova path is the dedicated area route.

    Every acquired Nova-path node adds one radius step, and mastering the
    Nova path plus a second full path (the run's whole two-path commitment)
    makes the nova engulf the player's entire room.
    """

    NOVA_PATH = (
        "arcanist_focus",
        "arcanist_permafrost",
        "arcanist_glacial",
        "arcanist_blizzard",
        "arcanist_absolute_zero",
    )
    WARD_PATH = (
        "arcanist_ward",
        "arcanist_ward_mend",
        "arcanist_ward_overload",
        "arcanist_aegis",
        "arcanist_eternal_aegis",
    )

    def make_game(self, tmpdir, seed=3702) -> Game:
        game = Game(
            screen_size=(960, 600),
            headless=True,
            save_path=Path(tmpdir) / "run.json",
        )
        game.options_path = Path(tmpdir) / "options.json"
        game.rng.seed(seed)
        game.restart(ARCHETYPES[2])  # Arcanist
        if game.story_intro_pending:
            self.assertTrue(game.choose_story_relic_path(0))
        game.active_cutscene = None
        return game

    def carve_room(self, game: Game, x: int, y: int, w: int, h: int) -> Room:
        """Carve a synthetic room and make it the only room on the floor."""
        for tx in range(x - 1, x + w + 1):
            for ty in range(y - 1, y + h + 1):
                game.dungeon.tiles[tx][ty] = Tile.WALL
        room = Room(x, y, w, h)
        for tx in range(room.x, room.x + room.w):
            for ty in range(room.y, room.y + room.h):
                game.dungeon.tiles[tx][ty] = Tile.FLOOR
        game.dungeon.rooms = [room]
        return room

    def cast_nova(self, game: Game) -> None:
        game.player.class_skill_timer = 0.0
        game.player.mana = game.player.max_mana
        game.player_cast_nova()

    def test_nova_path_descriptions_do_not_claim_arc_bolt_buffs(self) -> None:
        nodes = tuple(
            node
            for node in disciplines_for_archetype("Arcanist")
            if node.path == "Nova"
        )
        self.assertEqual(
            tuple(node.description for node in nodes),
            (
                "Mana recovers faster while Frost Nova reaches farther.",
                "Frost Nova spreads wider and chills longer while Mage Strike "
                "chills foes.",
                "Frost Nova reaches farther.",
                "Frost Nova reaches farther while armor and spellcraft improve.",
                "Frost Nova reaches its widest; master another path and it "
                "engulfs the whole room.",
            ),
        )
        self.assertTrue(
            all("bolt" not in node.description.casefold() for node in nodes)
        )

    def test_nova_path_does_not_modify_arc_bolt_cost_or_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            game.player.equipment = {
                slot: None for slot in game.player.equipment
            }
            base_cost = game.bolt_mana_cost()
            game.player.skill_upgrades.extend(self.NOVA_PATH)

            self.assertEqual(game.bolt_mana_cost(), base_cost)
            self.assertEqual(game.bolt_damage_type(), "arcane")

            game.projectiles.clear()
            game.player.mana = game.player.max_mana
            game.player.bolt_timer = 0.0
            game.player.facing_x, game.player.facing_y = 1.0, 0.0
            game.player_cast_bolt()

            self.assertEqual(len(game.projectiles), 1)
            self.assertTrue(
                all(not projectile.status_effect for projectile in game.projectiles)
            )
            self.assertTrue(
                all(
                    projectile.status_duration == 0.0
                    for projectile in game.projectiles
                )
            )

    def test_nova_radius_grows_one_step_per_nova_node(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            base = game.nova_radius()
            for count, key in enumerate(self.NOVA_PATH, start=1):
                game.player.skill_upgrades.append(key)
                self.assertAlmostEqual(game.nova_radius(), base + 0.55 * count)
            # Widening is cumulative per node, not keyed to the deepest pick.
            self.assertAlmostEqual(game.nova_radius(), base + 2.75)

    def test_nova_cast_reaches_farther_with_a_nova_node(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            self.carve_room(game, 4, 4, 10, 6)
            game.player.x, game.player.y = 5.5, 6.5
            enemy = _make_enemy(game.player.x + 2.8, game.player.y)
            game.enemies = [enemy]

            # Base blast (2.45 tiles) falls short of a foe 2.8 tiles out.
            self.cast_nova(game)
            self.assertEqual(enemy.hp, enemy.max_hp)

            # One Nova-path node widens the blast past the foe.
            game.player.skill_upgrades.append("arcanist_focus")
            self.cast_nova(game)
            self.assertLess(enemy.hp, enemy.max_hp)

    def test_nova_engulfs_room_only_with_two_full_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            room = self.carve_room(game, 4, 4, 12, 10)
            game.player.x, game.player.y = 5.5, 5.5
            # Far room corner: ~11.4 tiles out, beyond the widest radius blast.
            far_corner = _make_enemy(14.5, 12.5)
            game.enemies = [far_corner]

            game.player.skill_upgrades.extend(self.NOVA_PATH)
            self.assertFalse(game.nova_engulfs_room())
            self.cast_nova(game)
            self.assertEqual(far_corner.hp, far_corner.max_hp)

            # Completing a second full path unlocks the room-wide max effect.
            game.player.skill_upgrades.extend(self.WARD_PATH)
            self.assertTrue(game.nova_engulfs_room())
            self.assertIs(game.dungeon.room_at(game.player.x, game.player.y), room)
            self.cast_nova(game)
            self.assertLess(far_corner.hp, far_corner.max_hp)

    def test_room_engulf_does_not_reach_foes_outside_the_room(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            self.carve_room(game, 4, 4, 12, 10)
            game.player.x, game.player.y = 5.5, 5.5
            game.player.skill_upgrades.extend(self.NOVA_PATH + self.WARD_PATH)
            self.assertTrue(game.nova_engulfs_room())

            # A corridor foe past the room's east wall, well beyond the radius.
            for tx in range(16, 20):
                game.dungeon.tiles[tx][5] = Tile.FLOOR
            outside = _make_enemy(18.5, 5.5)
            inside = _make_enemy(14.5, 12.5)
            game.enemies = [outside, inside]
            self.cast_nova(game)
            self.assertLess(inside.hp, inside.max_hp)
            self.assertEqual(outside.hp, outside.max_hp)


class RogueMarksmanPathTests(unittest.TestCase):
    """4.11.0 rebalance: Marksman trades stamina for bolt damage.

    spell_bonus is Bolt's damage stat (14 + level*2 + spell_bonus), so these
    nodes buff the Rogue's bolt the same way the Warden's Guard Bolt paths do,
    while the stamina ladder shrank from its pre-4.11.0 total of 40.
    """

    def test_marksman_nodes_grant_bolt_damage_and_smaller_stamina(self) -> None:
        nodes = {
            node.key: node
            for node in disciplines_for_archetype("Rogue")
            if node.path == "Marksman"
        }
        expected = {
            "rogue_marksman": (2, 1, 4),
            "rogue_sharpshot": (3, 1, 4),
            "rogue_deadeye": (4, 2, 4),
            "rogue_eagle_eye": (5, 2, 4),
            "rogue_assassin": (6, 3, 6),
        }
        self.assertEqual(set(nodes), set(expected))
        for key, (melee, spell, stamina) in expected.items():
            with self.subTest(key):
                node = nodes[key]
                self.assertEqual(
                    (node.melee_bonus, node.spell_bonus, node.max_stamina_bonus),
                    (melee, spell, stamina),
                )
        self.assertEqual(
            sum(node.max_stamina_bonus for node in nodes.values()), 22
        )
        self.assertEqual(sum(node.spell_bonus for node in nodes.values()), 9)


if __name__ == "__main__":
    unittest.main()

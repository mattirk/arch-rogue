from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from arch_rogue.combat._utils import (
    BIGHIT_BOSS_THROW_FACTOR,
    BIGHIT_CANCEL_COOLDOWN,
    BIGHIT_CHARGE_TIME,
    BIGHIT_CLEAVE_FACTOR,
    BIGHIT_COOLDOWN,
    BIGHIT_DAMAGE_MULT,
    BIGHIT_STAMINA_COST,
    BIGHIT_THROW_TILES,
    BIGHIT_THROW_TILES_RANGER,
    KNOCKBACK_DECAY_RATE,
    KNOCKBACK_SPEED,
)
from arch_rogue.content import ARCHETYPES
from arch_rogue.game import Game
from arch_rogue.models import Enemy
from arch_rogue_protocol import wire


class _ScriptedRng:
    """Deterministic rng stub: fixed randrange, scripted random() sequence."""

    def __init__(self, randoms: list[float], randrange_value: int = 0) -> None:
        self._randoms = list(randoms)
        self._i = 0
        self._randrange_value = randrange_value

    def random(self) -> float:
        value = self._randoms[self._i % len(self._randoms)]
        self._i += 1
        return value

    def randrange(self, *_args) -> int:
        return self._randrange_value

    def choice(self, seq):
        return seq[0]

    def seed(self, *_args) -> None:
        pass


ARCHETYPE_INDEX = {
    archetype.name: index for index, archetype in enumerate(ARCHETYPES)
}


class BigHitTestBase(unittest.TestCase):
    def make_game(self, tmpdir: str, archetype: str = "Warden") -> Game:
        game = Game(
            screen_size=(820, 540),
            headless=True,
            save_path=Path(tmpdir) / "run.json",
        )
        game.options_path = Path(tmpdir) / "options.json"
        game.rng.seed(4100)
        game.restart(ARCHETYPES[ARCHETYPE_INDEX[archetype]])
        if game.story_intro_pending:
            self.assertTrue(game.choose_story_relic_path(0))
        game.active_cutscene = None
        return game

    def add_enemy(
        self,
        game: Game,
        dx: float = 1.0,
        dy: float = 0.0,
        hp: int = 500,
        size: int = 1,
    ) -> Enemy:
        enemy = Enemy(
            "Target",
            "melee",
            game.player.x + dx,
            game.player.y + dy,
            hp,
            hp,
            1.0,
            5,
            1,
            0.8,
            1.0,
            size=size,
        )
        game.enemies.append(enemy)
        return enemy

    def start_charge(self, game: Game) -> None:
        game.player.facing_x = 1.0
        game.player.facing_y = 0.0
        game.player_big_hit()
        self.assertTrue(game.player_big_hit_charging())

    def use_scripted_rng(
        self, game: Game, randoms: list[float] | None = None
    ) -> None:
        # 0.99 never passes a crit or equipment-proc roll, so damage is the
        # deterministic pre-crit arithmetic and no loot/status rng interferes.
        game.rng = _ScriptedRng(randoms or [0.99])

    def expected_hit(
        self, game: Game, target: Enemy, cleave: bool = False
    ) -> int:
        """Reproduce _fire_big_hit's damage arithmetic (no jitter, no crit)."""
        damage = int(game.player.melee_damage() * BIGHIT_DAMAGE_MULT)
        if game.equipment_skill_bonus("Melee"):
            damage += 2
        if cleave:
            damage = max(1, int(damage * BIGHIT_CLEAVE_FACTOR))
        damage = game.apply_story_player_damage(damage)
        return max(
            1,
            game.mitigate_enemy_damage(target, damage, game.weapon_damage_type()),
        )


class BigHitChargeFlowTests(BigHitTestBase):
    def test_press_spends_stamina_and_blocks_other_actions(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            self.add_enemy(game)
            stamina = game.player.stamina
            mana = game.player.mana
            self.start_charge(game)
            self.assertAlmostEqual(
                game.player.stamina, stamina - BIGHIT_STAMINA_COST
            )
            self.assertFalse(game.player_big_hit_committed())
            # A second press while charging must not double-spend.
            game.player_big_hit()
            self.assertAlmostEqual(
                game.player.stamina, stamina - BIGHIT_STAMINA_COST
            )
            # Auto-melee, bolt, and the class skill are locked out mid-charge.
            game.player_melee_attack()
            self.assertEqual(game.player.melee_timer, 0.0)
            game.player_cast_bolt()
            self.assertEqual(game.player.bolt_timer, 0.0)
            self.assertEqual(game.player.mana, mana)
            game.player_cast_class_skill()
            self.assertEqual(game.player.class_skill_timer, 0.0)

    def test_press_refused_on_cooldown_or_without_stamina(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            game.player.bighit_timer = 1.0
            game.player_big_hit()
            self.assertFalse(game.player_big_hit_charging())
            game.player.bighit_timer = 0.0
            game.player.stamina = BIGHIT_STAMINA_COST - 1
            game.player_big_hit()
            self.assertFalse(game.player_big_hit_charging())

    def test_release_before_halfway_cancels_at_the_short_cooldown(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            stamina = game.player.stamina
            self.start_charge(game)
            game._update_big_hit(0.2)
            self.assertFalse(game.player_big_hit_committed())
            game.player_big_hit_release()
            self.assertFalse(game.player_big_hit_charging())
            self.assertAlmostEqual(
                game.player.bighit_timer, BIGHIT_CANCEL_COOLDOWN
            )
            # Stamina stays spent — cancelling still cost the wind.
            self.assertAlmostEqual(
                game.player.stamina, stamina - BIGHIT_STAMINA_COST
            )

    def test_release_after_halfway_is_ignored_and_the_blow_fires(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            enemy = self.add_enemy(game)
            self.start_charge(game)
            game._update_big_hit(BIGHIT_CHARGE_TIME * 0.6)
            self.assertTrue(game.player_big_hit_committed())
            game.player_big_hit_release()
            self.assertTrue(game.player_big_hit_charging())
            game._update_big_hit(BIGHIT_CHARGE_TIME)
            self.assertFalse(game.player_big_hit_charging())
            self.assertAlmostEqual(game.player.bighit_timer, BIGHIT_COOLDOWN)
            self.assertLess(enemy.hp, enemy.max_hp)

    def test_whiff_pays_the_full_cooldown(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            game.enemies = []
            self.start_charge(game)
            game._update_big_hit(BIGHIT_CHARGE_TIME)
            self.assertFalse(game.player_big_hit_charging())
            self.assertAlmostEqual(game.player.bighit_timer, BIGHIT_COOLDOWN)

    def test_dash_cancels_uncommitted_but_not_committed_charges(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            self.start_charge(game)
            game._update_big_hit(0.1)
            game.player_dash()
            self.assertFalse(game.player_big_hit_charging())
            self.assertGreater(game.player.dash_timer, 0.0)
            self.assertAlmostEqual(
                game.player.bighit_timer, BIGHIT_CANCEL_COOLDOWN, places=5
            )
            # Reset and commit: dash must now be refused entirely.
            game.player.bighit_timer = 0.0
            game.player.dash_timer = 0.0
            game.player.stamina = game.player.max_stamina
            self.start_charge(game)
            game._update_big_hit(BIGHIT_CHARGE_TIME * 0.6)
            self.assertTrue(game.player_big_hit_committed())
            game.player_dash()
            self.assertTrue(game.player_big_hit_charging())
            self.assertEqual(game.player.dash_timer, 0.0)

    def test_auto_melee_suppressed_during_update_while_charging(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            enemy = self.add_enemy(game)
            self.start_charge(game)
            game.update_player(0.01)
            self.assertEqual(game.player.melee_timer, 0.0)
            self.assertEqual(enemy.hp, enemy.max_hp)
            self.assertTrue(game.player_big_hit_charging())


class BigHitFireTests(BigHitTestBase):
    def fire(self, game: Game) -> None:
        self.start_charge(game)
        game._update_big_hit(BIGHIT_CHARGE_TIME)

    def test_primary_damage_and_throw_velocity(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, "Arcanist")
            enemy = self.add_enemy(game)
            self.use_scripted_rng(game)
            expected = self.expected_hit(game, enemy)
            self.fire(game)
            self.assertEqual(enemy.hp, enemy.max_hp - expected)
            self.assertAlmostEqual(
                enemy.knockback_vx, BIGHIT_THROW_TILES * KNOCKBACK_DECAY_RATE
            )
            self.assertAlmostEqual(enemy.knockback_vy, 0.0)
            # Force Slam rider: the hurled target lands chilled.
            self.assertGreaterEqual(enemy.statuses.get("chilled", 0.0), 2.5)

    def test_boss_resists_the_throw_but_not_the_damage(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, "Arcanist")
            boss = self.add_enemy(game, size=2)
            self.use_scripted_rng(game)
            expected = self.expected_hit(game, boss)
            self.fire(game)
            self.assertEqual(boss.hp, boss.max_hp - expected)
            self.assertAlmostEqual(
                boss.knockback_vx,
                BIGHIT_THROW_TILES
                * KNOCKBACK_DECAY_RATE
                * BIGHIT_BOSS_THROW_FACTOR,
            )

    def test_cleave_target_takes_falloff_and_only_a_nudge(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, "Arcanist")
            primary = self.add_enemy(game, dx=1.0)
            secondary = self.add_enemy(game, dx=1.1, dy=0.35)
            self.use_scripted_rng(game)
            expected_primary = self.expected_hit(game, primary)
            expected_cleave = self.expected_hit(game, secondary, cleave=True)
            self.fire(game)
            self.assertEqual(primary.hp, primary.max_hp - expected_primary)
            self.assertEqual(secondary.hp, secondary.max_hp - expected_cleave)
            self.assertAlmostEqual(
                primary.knockback_vx,
                BIGHIT_THROW_TILES * KNOCKBACK_DECAY_RATE,
            )
            # The cleave victim gets the ordinary melee nudge, not the hurl.
            self.assertAlmostEqual(secondary.knockback_vx, KNOCKBACK_SPEED)
            self.assertEqual(secondary.statuses.get("chilled", 0.0), 0.0)

    def test_warden_bulwark_slam_throws_everyone_at_full_damage(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, "Warden")
            primary = self.add_enemy(game, dx=1.0)
            secondary = self.add_enemy(game, dx=1.1, dy=0.35)
            self.use_scripted_rng(game)
            expected = self.expected_hit(game, primary)
            self.fire(game)
            self.assertEqual(primary.hp, primary.max_hp - expected)
            self.assertEqual(secondary.hp, secondary.max_hp - expected)
            hurl = BIGHIT_THROW_TILES * KNOCKBACK_DECAY_RATE
            self.assertAlmostEqual(primary.knockback_vx, hurl)
            self.assertAlmostEqual(secondary.knockback_vx, hurl)

    def test_ranger_pinning_strike_snares_and_throws_farther(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, "Ranger")
            enemy = self.add_enemy(game)
            self.use_scripted_rng(game)
            self.fire(game)
            self.assertAlmostEqual(
                enemy.knockback_vx,
                BIGHIT_THROW_TILES_RANGER * KNOCKBACK_DECAY_RATE,
            )
            self.assertGreater(enemy.statuses.get("snared", 0.0), 0.0)

    def test_acolyte_blood_reap_heals_a_quarter_of_the_damage(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, "Acolyte")
            enemy = self.add_enemy(game)
            self.use_scripted_rng(game)
            expected = self.expected_hit(game, enemy)
            game.player.hp = 40
            self.fire(game)
            self.assertEqual(
                game.player.hp, 40 + max(1, int(expected * 0.25))
            )

    def test_rogue_killing_blow_doubles_the_precision_crit_chance(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, "Rogue")
            game.player.skill_upgrades.append("rogue_precision")
            enemy = self.add_enemy(game)
            # 0.25 fails the base 0.15 Precision roll but passes the doubled
            # 0.30 chance — the crit only lands because of the rider.
            self.use_scripted_rng(game, randoms=[0.25])
            is_crit, _mult = game.roll_melee_crit(enemy)
            self.assertFalse(is_crit)
            is_crit, mult = game.roll_melee_crit(enemy, chance_scale=2.0)
            self.assertTrue(is_crit)
            self.assertAlmostEqual(mult, 1.60)
            self.fire(game)
            self.assertTrue(
                any("Critical" in floater.text for floater in game.floaters)
            )


class BigHitKnockbackChainTests(BigHitTestBase):
    """The hurl must survive packmates: contact resolution ejects the mover,
    so without chain-shove a thrown enemy dead-stops on the first body in its
    flight path (~0.06 of the 2.0 tiles, the 4.10.0 playtest bug)."""

    def integrate(self, game: Game, enemies: list[Enemy], frames: int) -> None:
        dt = 1.0 / 60.0
        for _ in range(frames):
            for enemy in enemies:
                game._apply_enemy_knockback(enemy, dt)

    def test_throw_plows_through_a_packmate_in_the_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, "Arcanist")
            game.enemies = []
            primary = self.add_enemy(game, dx=1.0)
            blocker = self.add_enemy(game, dx=1.8)
            self.use_scripted_rng(game)
            self.start_charge(game)
            game._update_big_hit(BIGHIT_CHARGE_TIME)
            self.assertAlmostEqual(
                primary.knockback_vx, BIGHIT_THROW_TILES * KNOCKBACK_DECAY_RATE
            )
            start_primary, start_blocker = primary.x, blocker.x
            self.integrate(game, [primary, blocker], 40)
            # Un-fixed this was ~0.06; the flier must cover real ground and
            # the blocker must be plowed along (velocity transfer, no damage).
            self.assertGreater(primary.x - start_primary, 1.0)
            self.assertGreater(blocker.x - start_blocker, 0.4)
            self.assertEqual(blocker.hp, blocker.max_hp)

    def test_ordinary_melee_nudge_does_not_chain(self) -> None:
        from arch_rogue.combat._utils import KNOCKBACK_CHAIN_MIN_SPEED

        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, "Arcanist")
            game.enemies = []
            nudged = self.add_enemy(game, dx=1.0)
            neighbor = self.add_enemy(game, dx=1.5)
            self.assertLess(KNOCKBACK_SPEED, KNOCKBACK_CHAIN_MIN_SPEED)
            nudged.knockback_vx = KNOCKBACK_SPEED
            self.integrate(game, [nudged, neighbor], 10)
            self.assertEqual(neighbor.knockback_vx, 0.0)
            self.assertEqual(neighbor.knockback_vy, 0.0)

    def test_boss_bulk_is_never_chain_shoved(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, "Arcanist")
            game.enemies = []
            flier = self.add_enemy(game, dx=1.0)
            boss = self.add_enemy(game, dx=2.0, size=2)
            flier.knockback_vx = BIGHIT_THROW_TILES * KNOCKBACK_DECAY_RATE
            start_boss = boss.x
            self.integrate(game, [flier, boss], 40)
            self.assertEqual(boss.knockback_vx, 0.0)
            # The flier thuds against the bulk instead of passing through.
            self.assertLess(abs(boss.x - start_boss), 0.2)

    def test_thrown_kill_paints_a_directional_burst_trail(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, "Arcanist")
            game.enemies = []
            weak = self.add_enemy(game, hp=5)
            corpse_x = weak.x
            self.use_scripted_rng(game)
            self.start_charge(game)
            bursts_before = sum(
                1 for impact in game.impact_effects if impact.kind == "burst"
            )
            game._update_big_hit(BIGHIT_CHARGE_TIME)
            self.assertNotIn(weak, game.enemies)
            trail = [
                impact
                for impact in game.impact_effects
                if impact.kind == "burst" and impact.x > corpse_x + 0.2
            ]
            self.assertGreaterEqual(len(trail), 2)
            self.assertGreater(
                sum(1 for i in game.impact_effects if i.kind == "burst"),
                bursts_before,
            )


class BigHitRenderingTests(BigHitTestBase):
    def test_frame_renders_through_uncommitted_committed_and_cooldown(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            self.add_enemy(game)
            self.start_charge(game)
            game.draw()  # uncommitted: class-colored ring + rising fill
            game._update_big_hit(BIGHIT_CHARGE_TIME * 0.6)
            self.assertTrue(game.player_big_hit_committed())
            game.draw()  # committed: gold ring + border flash
            game._update_big_hit(BIGHIT_CHARGE_TIME)
            self.assertAlmostEqual(game.player.bighit_timer, BIGHIT_COOLDOWN)
            game.draw()  # cooling down: slot sweep + pip row

    def test_hud_slot_one_carries_the_big_hit_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, "Rogue")
            slot = game.hud_action_slots()[0]
            self.assertEqual(slot["kind"], "bighit")
            self.assertEqual(slot["label"], "Killing Blow")
            self.assertEqual(slot["asset"], "hud.action.rogue.killing_blow")
            self.assertEqual(slot["cost"], BIGHIT_STAMINA_COST)
            self.assertEqual(slot["charge"], 0.0)
            self.start_charge(game)
            game._update_big_hit(BIGHIT_CHARGE_TIME * 0.5)
            charge = game.hud_action_slots()[0]["charge"]
            self.assertGreater(charge, 0.4)


class BigHitNetworkingTests(BigHitTestBase):
    def test_wire_carries_the_bighit_intent_pair(self) -> None:
        self.assertIn("bighit", wire.INTENT_ACTIONS)
        self.assertIn("bighit_release", wire.INTENT_ACTIONS)
        self.assertGreaterEqual(wire.MP_PROTOCOL_VERSION, 2)
        message = wire.make_intent(
            input_seq=1, move_x=1.0, move_y=0.0, action="bighit"
        )
        self.assertEqual(message["action"], "bighit")

    def test_remote_action_dispatch_starts_and_releases_the_charge(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            game._mp_dispatch_remote_action("bighit", None)
            self.assertTrue(game.player_big_hit_charging())
            game._update_big_hit(0.1)
            game._mp_dispatch_remote_action("bighit_release", None)
            self.assertFalse(game.player_big_hit_charging())
            self.assertAlmostEqual(
                game.player.bighit_timer, BIGHIT_CANCEL_COOLDOWN
            )

    def test_snapshot_timers_roundtrip_the_bighit_cooldown(self) -> None:
        from arch_rogue.net import sync

        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            game.player.bighit_timer = 3.3
            data = sync.player_fast_dict(game, game.player)
            self.assertEqual(len(data["timers"]), 6)
            self.assertAlmostEqual(data["timers"][5], 3.3)
            game.player.bighit_timer = 0.0
            sync.apply_player_fast(game, game.player, data)
            self.assertAlmostEqual(game.player.bighit_timer, 3.3)
            # A pre-4.10 five-element timer list still applies cleanly and
            # leaves the local cooldown untouched.
            legacy = dict(data)
            legacy["timers"] = data["timers"][:5]
            sync.apply_player_fast(game, game.player, legacy)
            self.assertAlmostEqual(game.player.bighit_timer, 3.3)


if __name__ == "__main__":
    unittest.main()

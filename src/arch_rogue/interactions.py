# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Matti Rita-Kasari
#
# AI Provenance & Liability Notice:
# This repository contains code generated, assisted, or refactored by Artificial
# Intelligence models. Provided strictly "AS IS" under Apache 2.0 with no warranty
# of clean IP provenance or non-infringement; downstream users assume all legal
# and financial risk and should perform their own compliance audits.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# pyright: reportAttributeAccessIssue=false
from __future__ import annotations

import math

from .constants import DUNGEON_DEPTH, MAX_INVENTORY
from .content import (
    HELL_DIFFICULTY_NAME,
    SECRET_HINTS,
    SHRINE_HINTS,
    TRAP_HINTS,
    InteractionHint,
)
from .models import Color, Enemy, Familiar, FloatingText, Item, SecretCache, Shrine, Trap


class InteractionMixin:
    SPIRIT_BEAST_PET_RANGE = 1.5
    SPIRIT_BEAST_PET_HEAL = 2
    SPIRIT_BEAST_PET_COOLDOWN = 2.0
    SPIRIT_BEAST_PET_ANIMATION_DURATION = 0.8
    PARTNER_RAISE_RANGE = 1.6
    _BEAST_DISCIPLINE_KEYS = (
        "ranger_beast_bond",
        "ranger_pack_tactics",
        "ranger_alpha",
        "ranger_spirit_companion",
        "ranger_primal_lord",
    )

    def spirit_beast_pet_heal(self) -> int:
        """Petting heal amount: base 2, doubled per Beast discipline degree."""
        degrees = sum(
            1
            for key in self._BEAST_DISCIPLINE_KEYS
            if self.player.has_upgrade(key)
        )
        return self.SPIRIT_BEAST_PET_HEAL * (2 ** degrees)

    def current_interaction_hint(self) -> tuple[str, str, str, Color] | None:
        if self.story_intro_pending:
            return (
                "1-3",
                "Guest dialog awaits",
                "Choose a story path to place the guest relic and begin the level.",
                self.story_state.accent if self.story_state else self.theme.accent,
            )
        story_relic = self.nearby_story_relic()
        if story_relic is not None:
            return (
                "E",
                f"Recover {story_relic.display_name}",
                self.item_decision_summary(story_relic),
                self.story_state.accent if self.story_state else self.theme.accent,
            )
        fallen_partner = self.nearby_raisable_partner()
        if fallen_partner is not None:
            partner_name = fallen_partner.display_name or "your partner"
            return (
                "E",
                f"Raise {partner_name}",
                "Revive your fallen partner to half health"
                f" · {self.player.raise_charges} Raise left",
                (240, 228, 160),
            )
        # Ranger: surface petting as a first-class tappable action on mobile,
        # matching how items/doors/guests advertise their interact prompt.
        spirit_beast = self.nearby_pettable_spirit_beast()
        if spirit_beast is not None:
            beast_name = getattr(spirit_beast, "name", "") or "Spirit Beast"
            return (
                "E",
                f"Pet {beast_name}",
                f"Soothe your companion · +{self.spirit_beast_pet_heal()} HP",
                (142, 202, 92),
            )
        door = self.nearby_closed_door()
        if door is not None:
            # While a boss arena is sealed, the doors are locked; surface that
            # clearly instead of the normal "Open door" prompt.
            sealed = getattr(self, "boss_engaged", False) and any(
                dx == door[0] and dy == door[1]
                for dx, dy, _tile in self.boss_sealed_tiles
            )
            if sealed:
                return (
                    "",
                    "Sealed by the boss",
                    "Slay the guardian to open the doors.",
                    self.theme.accent,
                )
            return (
                "E",
                "Open door",
                "Doors gate special rooms and side rooms.",
                self.theme.accent,
            )
        shopkeeper = self.nearby_shopkeeper()
        if shopkeeper is not None:
            return (
                "E",
                f"Trade with {shopkeeper.name}",
                f"{shopkeeper.role} · buy and sell supplies · {self.player.gold} gold",
                (225, 190, 92),
            )
        if self.player_near_stairs():
            if self.current_depth < DUNGEON_DEPTH:
                next_plan = self.next_floor_plan()
                detail = (
                    f"Next: {next_plan.theme_name} — {self.floor_plan_summary(next_plan)}"
                    if next_plan is not None
                    else "Stairs are safe only when you choose to leave."
                )
                return (
                    "E",
                    f"Descend to depth {self.current_depth + 1}/{DUNGEON_DEPTH}",
                    detail,
                    self.theme.stair,
                )
            if self.boss_alive():
                return (
                    "!",
                    "Gate sealed",
                    "Defeat the gate tyrant before using the final stairs.",
                    (245, 95, 70),
                )
            return (
                "E",
                "Complete the run",
                "The tyrant is dead; descend to claim victory.",
                self.theme.stair,
            )
        guest = self.nearby_story_guest()
        if guest:
            # Mobile contextual prompts are tappable only for the generic
            # interaction key; desktop still advertises the direct 1-3 story
            # choices so keyboard-only play keeps the original shortcut UI.
            return (
                "E" if getattr(self, "mobile_mode", False) else "1-3",
                f"{guest.name}, {guest.role}",
                self.story_choices_hint(guest),
                guest.color,
            )
        secret = self.nearby_secret()
        if secret:
            hint = SECRET_HINTS.get(
                secret.kind,
                InteractionHint(
                    secret.kind, "Open the revealed secret.", self.theme.accent
                ),
            )
            return ("E", hint.title, hint.detail, hint.color)
        shrine = self.nearby_shrine()
        if shrine:
            hint = SHRINE_HINTS.get(
                shrine.kind,
                InteractionHint(
                    shrine.kind, "Use the shrine's bargain.", self.theme.accent
                ),
            )
            return ("E", hint.title, hint.detail, hint.color)
        item = self.nearby_item()
        if item:
            return (
                "E",
                f"Pick up {item.display_name}",
                self.item_decision_summary(item),
                self.rarity_color(item.visible_rarity),
            )

        trap = self.nearby_trap_warning()
        if trap:
            hint = TRAP_HINTS.get(
                trap.kind,
                InteractionHint(
                    trap.kind, "Dangerous floor trigger nearby.", (245, 95, 70)
                ),
            )
            return ("!", hint.title, hint.detail, hint.color)
        return None

    def nearby_raisable_partner(self):
        """The fallen co-op partner within reach, if the actor can still Raise."""

        if (
            not self.mp_active
            or self.player.hp <= 0
            or self.player.raise_charges <= 0
        ):
            return None
        for partner in self.players:
            if partner is self.player or partner.hp > 0:
                continue
            if (
                math.hypot(
                    partner.x - self.player.x, partner.y - self.player.y
                )
                < self.PARTNER_RAISE_RANGE
            ):
                return partner
        return None

    def raise_partner(self, partner) -> bool:
        """Revive a fallen partner to half health, spending one Raise charge.

        The raiser plays the celebratory "act" flourish over the corpse —
        except the Ranger, whose authored petting clip fits the gesture.
        """

        if (
            partner is None
            or partner.hp > 0
            or self.player.raise_charges <= 0
        ):
            return False
        self.player.raise_charges -= 1
        partner.hp = max(1, partner.max_hp // 2)
        partner.status_effects = {}
        partner.death_anim_time = 0.0
        dx = partner.x - self.player.x
        dy = partner.y - self.player.y
        distance = math.hypot(dx, dy)
        if distance > 0.001:
            self.player.facing_x = dx / distance
            self.player.facing_y = dy / distance
        self.player.moving = False
        state = "pet" if self.player.class_name == "Ranger" else "act"
        duration = (
            self.sprites.actor_clip_seconds(self.player.class_name, state)
            or 1.0
        )
        self.set_player_action_visual(state, duration)
        partner_name = partner.display_name or "Your partner"
        self.floaters.append(
            FloatingText(
                f"{partner_name} rises again",
                partner.x,
                partner.y - 0.6,
                (240, 228, 160),
                ttl=1.5,
            )
        )
        self.add_impact(
            partner.x,
            partner.y,
            (240, 228, 160),
            ttl=0.58,
            radius=0.68,
            kind="burst",
        )
        self.play_sfx("shrine")
        self.save_run()
        return True

    def nearby_pettable_spirit_beast(self) -> Familiar | None:
        """Return the closest living, ready Spirit Beast within petting reach."""
        if self.player.class_name != "Ranger":
            return None
        best: Familiar | None = None
        best_distance_sq = self.SPIRIT_BEAST_PET_RANGE**2
        for familiar in self.familiars:
            if (
                familiar.kind != "spirit_beast"
                or not familiar.alive
                or familiar.pet_cooldown > 0.0
            ):
                continue
            dx = familiar.x - self.player.x
            dy = familiar.y - self.player.y
            distance_sq = dx * dx + dy * dy
            if distance_sq >= best_distance_sq:
                continue
            if not self.dungeon.line_of_sight(
                self.player.x, self.player.y, familiar.x, familiar.y
            ):
                continue
            best = familiar
            best_distance_sq = distance_sq
        return best

    def can_pet_spirit_beast_now(self, familiar: Familiar) -> bool:
        """Return whether the interact action would pet this beast right now."""
        if self.nearby_pettable_spirit_beast() is not familiar:
            return False
        return not (
            self.story_intro_pending
            or self.nearby_story_relic() is not None
            or self.nearby_raisable_partner() is not None
            or self.nearby_closed_door() is not None
            or self.nearby_shopkeeper() is not None
            or self.player_near_stairs()
            or self.nearby_story_guest() is not None
            or self.nearby_secret() is not None
            or self.nearby_shrine() is not None
            or self.nearby_item() is not None
        )

    def pet_spirit_beast(self, familiar: Familiar) -> bool:
        """Pet one nearby Spirit Beast, healing two HP and starting paired clips."""
        if (
            self.player.class_name != "Ranger"
            or not any(candidate is familiar for candidate in self.familiars)
            or familiar.kind != "spirit_beast"
            or not familiar.alive
            or familiar.pet_cooldown > 0.0
        ):
            return False
        dx = familiar.x - self.player.x
        dy = familiar.y - self.player.y
        distance = math.hypot(dx, dy)
        if distance >= self.SPIRIT_BEAST_PET_RANGE:
            return False
        if not self.dungeon.line_of_sight(
            self.player.x, self.player.y, familiar.x, familiar.y
        ):
            return False
        if distance > 0.001:
            nx, ny = dx / distance, dy / distance
            self.player.facing_x = nx
            self.player.facing_y = ny
            familiar.facing_x = -nx
            familiar.facing_y = -ny

        heal = self.spirit_beast_pet_heal()
        familiar.hp = min(
            familiar.max_hp, familiar.hp + heal
        )
        familiar.pet_cooldown = self.SPIRIT_BEAST_PET_COOLDOWN
        familiar.pet_anim_timer = self.SPIRIT_BEAST_PET_ANIMATION_DURATION
        familiar.attack_anim_timer = 0.0
        familiar.moving = False
        familiar.move_x = 0.0
        familiar.move_y = 0.0
        self.player.moving = False
        self.set_player_action_visual(
            "pet", self.SPIRIT_BEAST_PET_ANIMATION_DURATION
        )

        self.floaters.append(
            FloatingText(
                f"+{heal}",
                familiar.x,
                familiar.y - 0.45,
                self.skill_color(),
                ttl=0.9,
            )
        )
        self.add_impact(
            (self.player.x + familiar.x) * 0.5,
            (self.player.y + familiar.y) * 0.5,
            self.skill_color(),
            ttl=0.30,
            radius=0.24,
            kind="spark",
        )
        self.play_sfx("pickup")
        return True

    def nearby_closed_door(self) -> tuple[int, int] | None:
        return self.dungeon.nearby_closed_door(self.player.x, self.player.y)

    def open_nearby_door(self) -> bool:
        door = self.nearby_closed_door()
        if door is None:
            return False
        # Boss-arena seals lock the doors shut until the boss dies; the player
        # cannot simply pull them open to flee the encounter.
        if getattr(self, "boss_engaged", False) and any(
            dx == door[0] and dy == door[1] for dx, dy, _tile in self.boss_sealed_tiles
        ):
            self.floaters.append(
                FloatingText(
                    "Sealed by the boss",
                    door[0] + 0.5,
                    door[1] + 0.1,
                    self.theme.accent,
                    ttl=1.0,
                )
            )
            return False
        if not self.dungeon.open_door(*door):
            return False
        self.tile_cache.clear()
        self.prewarm_tile_cache()
        self.floaters.append(
            FloatingText(
                "Door opened", door[0] + 0.5, door[1] + 0.1, self.theme.accent, ttl=1.0
            )
        )
        self.add_impact(
            door[0] + 0.5,
            door[1] + 0.5,
            self.theme.accent,
            ttl=0.28,
            radius=0.36,
            kind="spark",
        )
        self.play_sfx("pickup")
        self.save_run()
        return True

    def player_near_stairs(self) -> bool:
        return (
            math.hypot(
                self.player.x - self.dungeon.stairs[0] - 0.5,
                self.player.y - self.dungeon.stairs[1] - 0.5,
            )
            < 1.0
        )

    def interact(self) -> None:
        # 4.6 co-op: the joiner submits an interaction intent; the host
        # validates and resolves it (first valid claim wins the item).
        # 4.7.12: shops are the exception — the joiner opens its own local
        # shop UI (the floor is seed-identical, keeper inventories are
        # snapshot-synced) and only transactions go to the host. The checks
        # that outrank shops in the host's priority order and are readable
        # from replicated state defer to the host first.
        if self.mp_is_joiner():
            if (
                self.nearby_story_relic() is None
                and self.nearby_raisable_partner() is None
                and self.nearby_closed_door() is None
            ):
                shopkeeper = self.nearby_shopkeeper()
                if shopkeeper is None:
                    nearest = self.nearby_item()
                    if nearest is not None and nearest.slot == "shop_sign":
                        shopkeeper = self.shopkeeper_for_sign(nearest)
                if shopkeeper is not None:
                    self.open_shop(shopkeeper)
                    self.mp_queue_action(
                        "shop_open",
                        target=str(self.shopkeepers.index(shopkeeper)),
                    )
                    return
            self.mp_queue_action("interact")
            return
        if self.story_intro_pending:
            self.floaters.append(
                FloatingText(
                    "Choose 1-3 to answer the guest first",
                    self.player.x,
                    self.player.y - 0.5,
                    self.story_state.accent if self.story_state else self.theme.accent,
                    ttl=1.1,
                )
            )
            return
        story_relic = self.nearby_story_relic()
        if story_relic is not None:
            self.collect_story_relic(story_relic)
            return
        fallen_partner = self.nearby_raisable_partner()
        if fallen_partner is not None:
            self.raise_partner(fallen_partner)
            return
        if self.open_nearby_door():
            return
        shopkeeper = self.nearby_shopkeeper()
        if shopkeeper is not None:
            # 4.7.12: the joiner runs its own local shop UI, so a remote
            # actor's interact near a keeper means its client targeted
            # something else (position skew) — fall through to the other
            # checks instead of opening the modal shop on the host.
            if not (
                self.mp_active
                and self.player.player_id != self.local_player_id
            ):
                self.open_shop(shopkeeper)
                return
        if self.player_near_stairs():
            # On Hell, descent is a shared decision: every living player must
            # stand near the stairs before either can trigger it. On lower
            # difficulties either living player may descend alone (a fallen
            # partner respawns at the start of the next floor).
            if (
                self.mp_active
                and self.difficulty_profile().name == HELL_DIFFICULTY_NAME
                and not self.mp_all_living_players_near_stairs()
            ):
                self.floaters.append(
                    FloatingText(
                        "Both of you must reach the stairs",
                        self.player.x,
                        self.player.y - 0.5,
                        self.theme.accent,
                        ttl=1.2,
                    )
                )
                return
            if self.current_depth < DUNGEON_DEPTH:
                self.descend_to_next_depth()
                return
            if self.boss_alive():
                self.floaters.append(
                    FloatingText(
                        "The gate is sealed by its tyrant",
                        self.player.x,
                        self.player.y - 0.5,
                        self.theme.accent,
                        ttl=1.2,
                    )
                )
                return
            self.run_stats.floors_cleared = max(
                self.run_stats.floors_cleared, DUNGEON_DEPTH
            )
            self.state = "victory"
            self.unlock_hell_difficulty()
            self.finalize_run("victory")
            self.audio.stop_music()
            self.play_sfx("victory")
            self.delete_save()
            self.mp_notify_run_ended("victory")
            return
        guest = self.nearby_story_guest()
        if guest:
            # Story dialogue is host-controlled: whichever player hails the
            # guest, the modal choice UI opens on the host (the cutscene
            # pauses the shared simulation, so the partner freezes with a
            # banner while the host answers for both).
            self.talk_to_story_guest(guest)
            return
        secret = self.nearby_secret()
        if secret:
            self.open_secret(secret)
            return
        shrine = self.nearby_shrine()
        if shrine:
            self.activate_shrine(shrine)
            return
        nearest = self.nearby_item()
        if nearest:
            if nearest.slot == "story_relic":
                self.collect_story_relic(nearest)
                return
            if nearest.slot == "shop_sign":
                # The joiner opens its shop locally from the sign; a remote
                # actor's interact must never open (and range-flicker) the
                # host's modal shop.
                if not (
                    self.mp_active
                    and self.player.player_id != self.local_player_id
                ):
                    shopkeeper = self.shopkeeper_for_sign(nearest)
                    if shopkeeper is not None:
                        self.open_shop(shopkeeper)
                return
            if len(self.player.inventory) >= MAX_INVENTORY:
                self.floaters.append(
                    FloatingText(
                        "Inventory full",
                        self.player.x,
                        self.player.y - 0.4,
                        (235, 210, 120),
                    )
                )
                return
            self.items.remove(nearest)
            self.player.inventory.append(nearest)
            self.run_stats.loot_picked_up += 1
            self.record_notable_loot(nearest)
            self.floaters.append(
                FloatingText(
                    f"Picked up {nearest.display_name}",
                    self.player.x,
                    self.player.y - 0.4,
                    (210, 230, 180),
                    ttl=1.2,
                )
            )
            self.play_sfx("pickup")
            self.save_run()
            return
        spirit_beast = self.nearby_pettable_spirit_beast()
        if spirit_beast is not None:
            self.pet_spirit_beast(spirit_beast)

    def collect_story_relic(self, relic: Item) -> None:
        if relic in self.items:
            self.items.remove(relic)
        self.story_relic_collected = True
        self.story_relic_position = None
        guest = self.current_story_guest_for_depth()
        message = "Guest relic recovered"
        if guest is not None:
            message = f"Relic points to {guest.name}"
        self.player.mana = min(self.player.max_mana, self.player.mana + 6)
        self.player.stamina = min(self.player.max_stamina, self.player.stamina + 12)
        self.floaters.append(
            FloatingText(
                message,
                self.player.x,
                self.player.y - 0.5,
                self.story_state.accent if self.story_state else self.theme.accent,
                ttl=1.4,
            )
        )
        self.add_impact(
            relic.x,
            relic.y,
            self.story_state.accent if self.story_state else self.theme.accent,
            ttl=0.62,
            radius=0.62,
            kind="burst",
        )
        if self.story_state is not None:
            self.story_state.log.append(
                f"Depth {self.current_depth}: Guest relic recovered — {message}."
            )
            del self.story_state.log[:-12]
        self.play_sfx("pickup")
        self.save_run()

    def nearby_item(self) -> Item | None:
        nearby = [
            item
            for item in self.items
            if math.hypot(item.x - self.player.x, item.y - self.player.y) < 1.0
        ]
        return min(
            nearby,
            key=lambda item: math.hypot(item.x - self.player.x, item.y - self.player.y),
            default=None,
        )

    def nearby_story_relic(self) -> Item | None:
        nearby = [
            item
            for item in self.items
            if item.slot == "story_relic"
            and math.hypot(item.x - self.player.x, item.y - self.player.y) < 1.0
        ]
        return min(
            nearby,
            key=lambda item: math.hypot(item.x - self.player.x, item.y - self.player.y),
            default=None,
        )

    def nearby_trap_warning(self) -> Trap | None:
        nearby = [
            trap
            for trap in self.traps
            if trap.active
            and math.hypot(trap.x - self.player.x, trap.y - self.player.y) < 1.35
        ]
        return min(
            nearby,
            key=lambda trap: math.hypot(trap.x - self.player.x, trap.y - self.player.y),
            default=None,
        )

    def nearby_secret(self) -> SecretCache | None:
        nearby = [
            secret
            for secret in self.secrets
            if secret.revealed
            and not secret.opened
            and math.hypot(secret.x - self.player.x, secret.y - self.player.y) < 1.1
        ]
        return min(
            nearby,
            key=lambda secret: math.hypot(
                secret.x - self.player.x, secret.y - self.player.y
            ),
            default=None,
        )

    def open_secret(self, secret: SecretCache) -> None:
        secret.opened = True
        self.run_stats.secrets_opened += 1
        if secret.kind not in self.run_stats.discoveries:
            self.run_stats.discoveries.append(secret.kind)
            del self.run_stats.discoveries[:-8]
        if secret.kind == "Forgotten Skill Altar":
            self.grant_discipline(reason="forgotten altar")
            message = "Forgotten altar deepens your build"
        elif secret.kind == "Moonlit Bargain":
            self.player.hp = max(1, self.player.hp - max(6, self.player.max_hp // 8))
            self.items.append(
                self._make_equipment(
                    self.rng.choice(("weapon", "armor")), "Rare", secret.x, secret.y
                )
            )
            message = "Moonlit bargain takes blood for gear"
        elif secret.kind == "Cursed Reliquary" and self.rng.random() < 0.55:
            self.enemies.append(self._make_miniboss(secret.x + 0.3, secret.y + 0.3))
            message = "Reliquary wakes a sworn guardian"
        else:
            drops = 2 if "Stash" in secret.kind or secret.kind == "Sealed Armory" else 1
            for _ in range(drops):
                if secret.kind == "Sealed Armory":
                    self.items.append(
                        self._make_equipment(
                            self.rng.choice(("weapon", "armor")),
                            "Magic",
                            secret.x,
                            secret.y,
                        )
                    )
                else:
                    self.items.append(self._make_loot(secret.x, secret.y))
            message = f"Opened {secret.kind}"
        color = SECRET_HINTS.get(
            secret.kind, InteractionHint(secret.kind, message, self.theme.accent)
        ).color
        self.floaters.append(
            FloatingText(message, secret.x, secret.y - 0.3, color, ttl=1.4)
        )
        self.add_impact(secret.x, secret.y, color, ttl=0.52, radius=0.62, kind="burst")
        self.play_sfx("secret")
        self.save_run()

    def boss_alive(self) -> bool:
        return any(enemy.kind == "boss" for enemy in self.enemies)

    def floor_guardian_alive(self) -> bool:
        plan = self.current_floor_plan()
        if plan is None or not plan.boss_key or self.current_depth >= DUNGEON_DEPTH:
            return False
        return any(
            enemy.kind == "boss" or enemy.role == "floor_boss" for enemy in self.enemies
        )

    def boss_enemy(self) -> Enemy | None:
        """Active named boss for the top-of-screen health bar: the final gate
        tyrant or the current floor guardian (4-tile encounters only)."""
        return next(
            (
                enemy
                for enemy in self.enemies
                if enemy.is_boss_encounter and enemy.alive
            ),
            None,
        )

    def nearby_shrine(self) -> Shrine | None:
        nearby = [
            shrine
            for shrine in self.shrines
            if not shrine.used
            and math.hypot(shrine.x - self.player.x, shrine.y - self.player.y) < 1.15
        ]
        return min(
            nearby,
            key=lambda shrine: math.hypot(
                shrine.x - self.player.x, shrine.y - self.player.y
            ),
            default=None,
        )

    def activate_shrine(self, shrine: Shrine) -> None:
        shrine.used = True
        self.run_stats.shrines_used += 1
        if shrine.kind == "Mending Shrine":
            self.player.hp = self.player.max_hp
            self.player.mana = self.player.max_mana
            message = "Shrine restored you"
        elif shrine.kind == "Insight Shrine":
            identified = self.identify_all_items()
            message = (
                f"Shrine revealed {identified} item{'s' if identified != 1 else ''}"
            )
        elif shrine.kind == "War Shrine":
            leveled = self.player.gain_xp(25)
            self.player.stamina = self.player.max_stamina
            message = "War Shrine grants focus"
            if leveled:
                message = "War Shrine grants a level and mastery token"
        elif shrine.kind == "Haste Shrine":
            self.player.stamina = self.player.max_stamina
            self.player.dash_timer = 0.0
            self.player.speed += 0.18
            message = "Haste Shrine quickens your stride"
        elif shrine.kind == "Oath Shrine":
            granted = self.grant_discipline(reason="oath shrine")
            message = (
                "Oath Shrine grants a new technique"
                if granted
                else "Oath Shrine finds no path left"
            )
        elif shrine.kind == "Vigil Shrine":
            self.player.raise_charges += 1
            message = "Vigil Shrine grants another Raise"
        elif shrine.kind == "Twilight Shrine":
            self.player.hp = max(1, self.player.hp - max(5, self.player.max_hp // 10))
            self.items.append(self._make_unique(self.player.x, self.player.y))
            message = "Twilight Shrine trades blood for a relic"
        else:
            self.items.append(self._make_loot(self.player.x, self.player.y))
            self.items.append(
                self._make_loot(self.player.x + 0.25, self.player.y + 0.25)
            )
            message = "Fortune Shrine spills offerings"
        color = SHRINE_HINTS.get(
            shrine.kind, InteractionHint(shrine.kind, message, (245, 215, 120))
        ).color
        self.floaters.append(
            FloatingText(message, self.player.x, self.player.y - 0.5, color, ttl=1.3)
        )
        self.add_impact(shrine.x, shrine.y, color, ttl=0.58, radius=0.68, kind="burst")
        self.play_sfx("shrine")
        self.save_run()

# pyright: reportAttributeAccessIssue=false
from __future__ import annotations

import math
import random
import re
from typing import Any

from .content import STORY_LOCATION_MOTIFS
from .models import FloatingText, Item, SecretCache, Shrine, StoryGuest
from .quest_assets import ActiveQuestCutscene, RuntimeDialogueChoice, format_asset_text
from .story import (
    StoryEngine,
    clamp_story_effect,
    record_story_choice,
    record_unanswered_story_beat,
    story_beat_for_depth,
    story_beat_index_for_depth,
    story_effect,
    story_guest_from_beat,
)


class StoryRuntimeMixin:
    def start_story_mode(self) -> None:
        self.story_seed = self.rng.randrange(1, 2**31)
        self.story_state = StoryEngine.generate(
            self.story_seed,
            self.selected_archetype.name,
            self.run_number,
            self.theme.name,
            self.run_modifier.name,
        )
        self.story_guests = []
        self._apply_story_theme_for_current_depth()

    def current_story_beat(self) -> Any:
        return story_beat_for_depth(self.story_state, self.current_depth)

    def story_effect_value(
        self, key: str, minimum: float = -1.0, maximum: float = 1.0
    ) -> float:
        return clamp_story_effect(story_effect(self.story_state, key), minimum, maximum)

    def story_header_line(self) -> str:
        if self.story_state is None:
            return "Story: unwritten"
        beat = self.current_story_beat()
        if beat is None:
            return f"Story: {self.story_state.title}"
        status = "resolved" if beat.resolved_choice else "unresolved"
        return f"Story: {self.story_state.title} · {beat.title} ({status})"

    def story_choice_preview(self, choice_key: str) -> str:
        previews = {
            "aid": "mercy wards, heals, and reveals",
            "bargain": "relic power for blood and curses",
            "defy": "damage, XP, and hunters",
        }
        return previews.get(choice_key, "the dungeon answers")

    def story_choices_hint(self, guest: StoryGuest) -> str:
        entries = [
            f"{index + 1} {choice.label}: {self.story_choice_preview(choice.key)}"
            for index, choice in enumerate(guest.choices[:3])
        ]
        return " · ".join(entries) + " · E hear plea"

    def quest_cutscene_context(self, guest: StoryGuest | None = None) -> dict[str, str]:
        beat = self.current_story_beat()
        story = self.story_state
        active_guest = guest or self.current_story_guest_for_depth()
        if active_guest is None:
            active_guest = self.nearby_story_guest()
        motif = next(
            (
                candidate
                for candidate in STORY_LOCATION_MOTIFS
                if beat is not None and candidate.theme_name == beat.theme_name
            ),
            None,
        )
        location_image = (
            motif.image
            if motif is not None
            else (beat.theme_name.lower() if beat is not None else "unlit stone")
        )
        location_danger = (
            motif.danger if motif is not None else "the dungeon listens for hesitation"
        )
        guest_name = active_guest.name if active_guest else "Unknown Guest"
        guest_role = active_guest.role if active_guest else "Guest"
        guest_motive = active_guest.motive if active_guest else "waits for a choice"
        guest_dialogue = (
            active_guest.dialogue
            if active_guest
            else (beat.dialogue if beat else "The guest waits for an answer.")
        )
        cinematic_narration = "The dungeon waits in silence."
        if story is not None and beat is not None:
            cinematic_narration = (
                f"The narrator's candle reveals {location_image}. "
                f"Here, {location_danger}. {beat.summary} "
                f"{guest_name}, {guest_role}, {guest_motive}. "
                f"The relic glimmers as {story.relic_form}; {story.relic_temptation}. "
                f"{guest_dialogue}"
            )
        context = {
            "depth": str(self.current_depth),
            "player_class": getattr(
                self.player, "class_name", self.selected_archetype.name
            ),
            "story_title": story.title if story else "Unwritten Descent",
            "player_backstory": story.player_backstory
            if story
            else "An unnamed exile descends.",
            "objective": story.objective if story else "Survive the dungeon.",
            "antagonist": story.antagonist if story else "Gate Tyrant",
            "faction": story.faction if story else "the dungeon",
            "rival_faction": story.rival_faction if story else "the rival faction",
            "relic_name": story.relic_name if story else "Nameless Relic",
            "relic_form": story.relic_form if story else "a relic",
            "relic_temptation": story.relic_temptation
            if story
            else "it wants to be used",
            "location_image": location_image,
            "location_danger": location_danger,
            "cinematic_narration": cinematic_narration,
            "beat_title": beat.title if beat else "Unwritten Beat",
            "beat_summary": beat.summary if beat else "The floor waits in silence.",
            "beat_dialogue": beat.dialogue
            if beat
            else "The guest waits for an answer.",
            "guest_name": guest_name,
            "guest_role": guest_role,
            "guest_motive": guest_motive,
            "guest_dialogue": guest_dialogue,
        }
        return {key: " ".join(str(value).split()) for key, value in context.items()}

    def start_quest_cutscene(
        self, asset_id: str, guest: StoryGuest | None = None
    ) -> bool:
        asset = self.quest_cutscenes.get(asset_id)
        if asset is None:
            return False
        active_guest = guest or self.current_story_guest_for_depth()
        self.active_cutscene = ActiveQuestCutscene(
            asset_id=asset.id,
            node_id=asset.start_node,
            guest_depth=active_guest.depth if active_guest else self.current_depth,
            guest_beat_index=active_guest.beat_index if active_guest else -1,
            context=self.quest_cutscene_context(active_guest),
        )
        return True

    def close_active_cutscene(self) -> None:
        self.active_cutscene = None

    def active_cutscene_asset(self) -> Any:
        if self.active_cutscene is None:
            return None
        return self.quest_cutscenes.get(self.active_cutscene.asset_id)

    def active_cutscene_node(self) -> Any:
        asset = self.active_cutscene_asset()
        if asset is None or self.active_cutscene is None:
            return None
        return asset.nodes.get(self.active_cutscene.node_id)

    def active_cutscene_guest(self) -> StoryGuest | None:
        if self.active_cutscene is None:
            return None
        if self.active_cutscene.guest_beat_index >= 0:
            for guest in self.story_guests:
                if (
                    guest.depth == self.active_cutscene.guest_depth
                    and guest.beat_index == self.active_cutscene.guest_beat_index
                ):
                    return guest
        return self.nearby_story_guest() or self.current_story_guest_for_depth()

    def active_cutscene_text(self) -> str:
        node = self.active_cutscene_node()
        if node is None or self.active_cutscene is None:
            return ""
        context = {**self.quest_cutscene_context(self.active_cutscene_guest())}
        context.update(self.active_cutscene.context)
        return format_asset_text(node.text, context)

    def cutscene_narration_char_delay(self, char: str) -> float:
        if char == "\n":
            return 0.18
        if char in ".!?":
            return 0.25
        if char in ";:":
            return 0.16
        if char in ",—":
            return 0.10
        if char.isspace():
            return 0.012
        return 0.026

    def active_cutscene_narration_duration(self, text: str | None = None) -> float:
        narration = self.active_cutscene_text() if text is None else text
        if not narration:
            return 0.0
        return sum(self.cutscene_narration_char_delay(char) for char in narration)

    def active_cutscene_narration_char_count(self, text: str | None = None) -> int:
        if self.active_cutscene is None:
            return 0
        narration = self.active_cutscene_text() if text is None else text
        if not narration:
            return 0
        elapsed = max(0.0, self.active_cutscene.node_elapsed)
        spoken_time = 0.0
        for index, char in enumerate(narration):
            spoken_time += self.cutscene_narration_char_delay(char)
            if spoken_time > elapsed:
                return index
        return len(narration)

    def active_cutscene_visible_text(self) -> str:
        narration = self.active_cutscene_text()
        return narration[: self.active_cutscene_narration_char_count(narration)]

    def active_cutscene_narration_complete(self) -> bool:
        narration = self.active_cutscene_text()
        return self.active_cutscene_narration_char_count(narration) >= len(narration)

    def active_cutscene_narration_progress(self) -> float:
        narration = self.active_cutscene_text()
        if not narration:
            return 1.0
        return min(
            1.0, self.active_cutscene_narration_char_count(narration) / len(narration)
        )

    def active_cutscene_current_sentence_text(self) -> str:
        narration = self.active_cutscene_text()
        if not narration:
            return ""
        char_count = self.active_cutscene_narration_char_count(narration)
        if char_count <= 0:
            return ""
        cursor = min(char_count, len(narration))
        start = 0
        for mark in (". ", "! ", "? ", "\n"):
            found = narration.rfind(mark, 0, cursor)
            if found >= 0:
                start = max(start, found + len(mark))
        end_candidates = [
            found
            for mark in (".", "!", "?", "\n")
            if (found := narration.find(mark, cursor)) >= 0
        ]
        end = min(end_candidates) if end_candidates else len(narration)
        return narration[start:end].strip()

    def reveal_active_cutscene_narration(self) -> None:
        if self.active_cutscene is None:
            return
        self.active_cutscene.node_elapsed = max(
            self.active_cutscene.node_elapsed,
            self.active_cutscene_narration_duration() + 0.05,
        )

    def active_cutscene_speaker_name(self) -> str:
        asset = self.active_cutscene_asset()
        node = self.active_cutscene_node()
        if asset is None or node is None or self.active_cutscene is None:
            return "Narrator"
        if node.speaker == "narrator":
            return "Narrator"
        actor = asset.actors.get(node.speaker)
        if actor is None:
            return node.speaker.title()
        context = {**self.quest_cutscene_context(self.active_cutscene_guest())}
        context.update(self.active_cutscene.context)
        return format_asset_text(actor.name, context)

    def active_cutscene_choices(self) -> list[RuntimeDialogueChoice]:
        node = self.active_cutscene_node()
        if node is None:
            return []
        if node.choice_source == "story_relic_options":
            return [
                RuntimeDialogueChoice(
                    label=label,
                    detail=detail,
                    action="choose_story_relic_path",
                    choice_key=choice_key,
                    source_index=index,
                )
                for index, (choice_key, label, detail) in enumerate(
                    self.story_relic_choice_options()
                )
            ]
        if node.choice_source == "story_guest_choices":
            guest = self.active_cutscene_guest()
            if guest is None:
                return []
            return [
                RuntimeDialogueChoice(
                    label=choice.label,
                    detail=f"{choice.intent} ({self.story_choice_preview(choice.key)})",
                    action="resolve_story_choice",
                    choice_key=choice.key,
                    source_index=index,
                )
                for index, choice in enumerate(guest.choices[:3])
            ]
        context = (
            {**self.active_cutscene.context}
            if self.active_cutscene is not None
            else self.quest_cutscene_context()
        )
        return [
            RuntimeDialogueChoice(
                label=format_asset_text(choice.label, context),
                detail=format_asset_text(choice.detail, context),
                next_node=choice.next_node,
                action=choice.action,
                choice_key=choice.choice_key,
                source_index=index,
            )
            for index, choice in enumerate(node.choices)
        ]

    def set_active_cutscene_node(self, node_id: str) -> bool:
        asset = self.active_cutscene_asset()
        if asset is None or self.active_cutscene is None or node_id not in asset.nodes:
            return False
        self.active_cutscene.node_id = node_id
        self.active_cutscene.node_elapsed = 0.0
        self.active_cutscene.context = self.quest_cutscene_context(
            self.active_cutscene_guest()
        )
        return True

    def advance_active_cutscene(self) -> bool:
        if self.active_cutscene is None:
            return False
        if not self.active_cutscene_narration_complete():
            self.reveal_active_cutscene_narration()
            return True
        choices = self.active_cutscene_choices()
        if len(choices) == 1 and choices[0].next_node and not choices[0].action:
            return self.set_active_cutscene_node(choices[0].next_node)
        if not choices:
            self.close_active_cutscene()
            return True
        return False

    def choose_active_cutscene_option(self, choice_index: int) -> bool:
        if self.active_cutscene is None:
            return False
        choices = self.active_cutscene_choices()
        if not (0 <= choice_index < len(choices)):
            return False
        choice = choices[choice_index]
        if choice.action == "choose_story_relic_path":
            return self.choose_story_relic_path(choice.source_index)
        if choice.action == "resolve_story_choice":
            guest = self.active_cutscene_guest()
            if guest is None:
                return False
            resolved = self.resolve_story_choice(guest, choice.source_index)
            if resolved:
                self.close_active_cutscene()
            return resolved
        if choice.action == "close":
            self.close_active_cutscene()
            return True
        if choice.next_node:
            return self.set_active_cutscene_node(choice.next_node)
        self.close_active_cutscene()
        return True

    def update_active_cutscene(self, dt: float) -> None:
        if self.active_cutscene is None:
            return
        self.active_cutscene.elapsed += dt
        self.active_cutscene.node_elapsed += dt

    def story_relic_choice_options(self) -> list[tuple[str, str, str]]:
        beat = self.current_story_beat()
        if self.story_state is None or beat is None:
            return self.default_story_relic_choice_options()
        base_seed = self.story_relic_choice_text_seed(beat)
        key_salts = {"aid": 11_117, "bargain": 65_537, "defy": 104_729}
        return [
            self.story_relic_choice_option_for_key(
                key, beat, random.Random(base_seed + key_salts[key])
            )
            for key in self.story_relic_choice_key_order(beat)
        ]

    def story_relic_choice_key_order(self, beat: Any) -> list[str]:
        keys = ["aid", "bargain", "defy"]
        rng = random.Random(self.story_relic_choice_text_seed(beat) ^ 0xA511E9B3)
        rng.shuffle(keys)
        if keys == ["aid", "bargain", "defy"]:
            keys = ["bargain", "defy", "aid"]
        return keys

    def default_story_relic_choice_options(self) -> list[tuple[str, str, str]]:
        return [
            (
                "aid",
                "Offer a gentle vow",
                "promise to carry the guest's burden before your own",
            ),
            (
                "bargain",
                "Whisper a hidden bargain",
                "ask the dungeon to answer in riddles, debts, and signs",
            ),
            (
                "defy",
                "Refuse the omen",
                "turn from the guest's terms and trust your own path",
            ),
        ]

    def story_relic_choice_text_seed(self, beat: Any) -> int:
        parts = [
            str(self.story_seed),
            str(self.run_number),
            str(self.current_depth),
            beat.title,
            beat.guest_name,
            beat.guest_role,
        ]
        if self.story_state is not None:
            parts.extend(
                (
                    self.story_state.title,
                    self.story_state.faction,
                    self.story_state.rival_faction,
                    self.story_state.relic_name,
                )
            )
        seed = 2_166_136_261
        for char in "|".join(parts):
            seed ^= ord(char)
            seed = (seed * 16_777_619) & 0xFFFFFFFF
        return seed

    def story_relic_choice_option_for_key(
        self, choice_key: str, beat: Any, rng: random.Random
    ) -> tuple[str, str, str]:
        choice = next(
            (candidate for candidate in beat.choices if candidate.key == choice_key),
            None,
        )
        if choice is None:
            return next(
                option
                for option in self.default_story_relic_choice_options()
                if option[0] == choice_key
            )
        guest = self.story_choice_short_name(beat.guest_name)
        role = self.safe_story_choice_text(beat.guest_role.lower(), "guest")
        relic = self.safe_story_choice_text(
            self.story_state.relic_name
            if self.story_state is not None
            else "the relic",
            "the relic",
        )
        faction = self.safe_story_choice_text(
            self.story_state.faction if self.story_state is not None else "the dungeon",
            "the dungeon",
        )
        antagonist = self.safe_story_choice_text(
            self.story_state.antagonist
            if self.story_state is not None
            else "the tyrant",
            "the tyrant",
        )
        motive = self.short_story_choice_clause(beat.guest_motive, 36)
        title = self.safe_story_choice_text(beat.title, "this omen")
        intent = self.short_story_choice_clause(choice.intent, 48)
        label_templates = {
            "aid": (
                "Keep {guest}'s vow",
                "Mercy for the {role}",
                "Answer {guest} kindly",
                "Carry {guest}'s plea",
                "Honor the {role}",
            ),
            "bargain": (
                "Name {guest}'s price",
                "Trade a sealed vow",
                "Speak in owed terms",
                "Bind {relic}'s debt",
                "Ask the {role}'s price",
            ),
            "defy": (
                "Refuse {guest}'s terms",
                "Break the old demand",
                "Challenge {antagonist}'s claim",
                "Trust your own oath",
                "Deny the {role}'s omen",
            ),
        }
        detail_templates = {
            "aid": (
                "{intent}; remember {motive}",
                "answer {guest} as {role}: {intent}",
                "set {relic} toward mercy: {intent}",
                "let {title} end in witness: {intent}",
            ),
            "bargain": (
                "{intent}; weigh it against {faction}",
                "answer {guest} with measured terms: {intent}",
                "bind {relic} to a price: {intent}",
                "let {title} become debt: {intent}",
            ),
            "defy": (
                "{intent}; keep {relic} in your own hands",
                "answer {guest} with iron restraint: {intent}",
                "set your oath against {antagonist}: {intent}",
                "let {title} break before you: {intent}",
            ),
        }
        format_values = {
            "guest": guest,
            "role": role,
            "relic": relic,
            "faction": faction,
            "antagonist": antagonist,
            "motive": motive,
            "title": title,
            "intent": intent,
        }
        label = rng.choice(label_templates[choice_key]).format(**format_values)
        detail = rng.choice(detail_templates[choice_key]).format(**format_values)
        return (
            choice_key,
            self.short_story_choice_clause(label, 34),
            self.short_story_choice_clause(detail, 92),
        )

    def story_choice_short_name(self, name: str) -> str:
        safe_name = self.safe_story_choice_text(name, "the guest")
        parts = safe_name.split()
        if len(parts) > 2:
            safe_name = " ".join(parts[:2])
        return safe_name

    def safe_story_choice_text(self, text: str, fallback: str) -> str:
        result = " ".join(str(text).replace("\n", " ").split())
        replacements = {
            "unguarded": "alone",
            "guarded": "watched",
            "guardian": "warden",
            "guidance": "counsel",
            "guiding": "veiled",
            "guide": "shape",
            "light": "sign",
            "beacon": "sign",
            "lantern": "taper",
            "trail": "trace",
        }
        for term, replacement in replacements.items():
            result = re.sub(term, replacement, result, flags=re.IGNORECASE)
        result = " ".join(result.split()).strip(" ;:,.—")
        return result or fallback

    def short_story_choice_clause(self, text: str, limit: int) -> str:
        safe = self.safe_story_choice_text(text, "the guest's plea")
        if len(safe) <= limit:
            return safe
        shortened = safe[: max(1, limit - 1)].rsplit(" ", 1)[0].strip(" ;:,.—")
        return f"{shortened}…" if shortened else safe[:limit]

    def story_relic_choice_traits(self, choice_key: str) -> tuple[bool, bool]:
        traits = {
            "aid": (True, False),
            "bargain": (True, True),
            "defy": (False, True),
        }
        return traits.get(choice_key, (True, False))

    def story_relic_choice_label(self) -> str:
        for key, label, _detail in self.story_relic_choice_options():
            if key == self.story_relic_choice_key:
                return label
        return "unbound"

    def current_story_guest_for_depth(self) -> StoryGuest | None:
        return next(
            (
                guest
                for guest in self.story_guests
                if guest.depth == self.current_depth and not guest.resolved
            ),
            None,
        )

    def current_story_relic(self) -> Item | None:
        return next((item for item in self.items if item.slot == "story_relic"), None)

    def story_relic_target_position(self) -> tuple[float, float] | None:
        relic = self.current_story_relic()
        if relic is not None:
            return relic.x, relic.y
        if not self.story_relic_collected:
            return self.story_relic_position
        return None

    def begin_story_level_intro(self) -> None:
        beat = self.current_story_beat()
        guest = self.current_story_guest_for_depth()
        self.story_relic_depth = self.current_depth
        self.story_relic_choice_key = ""
        self.story_relic_position = None
        self.story_relic_collected = False
        self.story_relic_guidance_enabled = False
        self.story_relic_guarded = False
        self.items = [item for item in self.items if item.slot != "story_relic"]
        self.story_intro_pending = beat is not None and guest is not None
        if self.story_intro_pending:
            self.start_quest_cutscene("story_guest_omen", guest)
        else:
            self.close_active_cutscene()

    def story_intro_lines(self) -> list[str]:
        if self.story_state is None:
            return []
        beat = self.current_story_beat()
        guest = self.current_story_guest_for_depth()
        lines = [self.story_state.title, self.story_state.objective]
        if beat is not None:
            lines.extend(
                [
                    f"Depth {beat.depth}: {beat.title}",
                    beat.summary,
                    beat.dialogue,
                ]
            )
        if guest is not None:
            lines.append(
                f"{guest.name}, {guest.role}, waits somewhere ahead. Before the level begins, choose how their relic echo should surface."
            )
            lines.append(
                "Your answer will shape how the relic stirs, but the dungeon will not reveal the cost until the level begins."
            )
        return lines

    def choose_story_relic_path(self, choice_index: int) -> bool:
        options = self.story_relic_choice_options()
        if not self.story_intro_pending or not (0 <= choice_index < len(options)):
            return False
        choice_key, choice_label, _detail = options[choice_index]
        guidance_enabled, guarded = self.story_relic_choice_traits(choice_key)
        guest = self.current_story_guest_for_depth()
        if guest is None:
            self.story_intro_pending = False
            return False
        relic_x, relic_y = self.story_relic_location_for_choice(choice_key, guest)
        self.items = [item for item in self.items if item.slot != "story_relic"]
        relic_name = (
            f"{guest.name}'s Echo of {self.story_state.relic_name}"
            if self.story_state is not None
            else "Guest Relic Echo"
        )
        self.items.append(
            Item(
                relic_name,
                "story_relic",
                rarity="Unique",
                x=relic_x,
                y=relic_y,
                affixes=[
                    "Story Relic",
                    choice_label,
                    "Guiding Light" if guidance_enabled else "No Guiding Light",
                    "Guarded" if guarded else "Unguarded",
                ],
                unique_effect="guides the guest's plea"
                if guidance_enabled
                else "the guest's light has gone silent",
            )
        )
        self.story_relic_depth = self.current_depth
        self.story_relic_choice_key = choice_key
        self.story_relic_position = (relic_x, relic_y)
        self.story_relic_collected = False
        self.story_relic_guidance_enabled = guidance_enabled
        self.story_relic_guarded = guarded
        if guarded:
            self.spawn_story_relic_guard(relic_x, relic_y)
        self.story_intro_pending = False
        self.close_active_cutscene()
        if self.story_state is not None:
            self.story_state.flags.append(f"{self.current_depth}:relic:{choice_key}")
            self.story_state.log.append(
                f"Depth {self.current_depth}: {choice_label} — the guest relic surfaced"
                f" {'with a guiding light' if guidance_enabled else 'without a guiding light'}"
                f" {'and a guardian' if guarded else 'and no guardian'}."
            )
            del self.story_state.log[:-12]
        self.floaters.append(
            FloatingText(
                f"{choice_label}: "
                f"{'follow the relic trail' if guidance_enabled else 'find the relic without a trail'}",
                self.player.x,
                self.player.y - 0.6,
                self.story_state.accent if self.story_state else self.theme.accent,
                ttl=1.8,
            )
        )
        self.play_sfx("shrine")
        self.save_run()
        return True

    def story_relic_location_for_choice(
        self, choice_key: str, guest: StoryGuest
    ) -> tuple[float, float]:
        if choice_key == "aid":
            return self.drop_position_near(guest.x, guest.y)
        if choice_key == "bargain":
            if self.secrets:
                secret = min(
                    self.secrets,
                    key=lambda candidate: math.hypot(
                        candidate.x - guest.x, candidate.y - guest.y
                    ),
                )
                secret.revealed = True
                return self.drop_position_near(secret.x, secret.y)
            side_rooms = self.dungeon.rooms[2:-1] or self.dungeon.rooms[1:]
            room = max(
                side_rooms,
                key=lambda candidate: math.hypot(
                    candidate.center[0] + 0.5 - self.player.x,
                    candidate.center[1] + 0.5 - self.player.y,
                ),
            )
            x, y = room.random_point(self.rng)
            return self.drop_position_near(x, y)
        final_room = self.dungeon.rooms[-1]
        x, y = final_room.random_point(self.rng)
        return self.drop_position_near(x, y)

    def spawn_story_relic_guard(self, relic_x: float, relic_y: float) -> None:
        offsets = (
            (1.8, 0.0),
            (-1.8, 0.0),
            (0.0, 1.8),
            (0.0, -1.8),
            (1.4, 1.4),
            (-1.4, 1.4),
            (1.4, -1.4),
            (-1.4, -1.4),
        )
        guard_x, guard_y = relic_x, relic_y
        for ox, oy in offsets:
            candidate_x, candidate_y = relic_x + ox, relic_y + oy
            if not self.dungeon.blocked_for_radius(
                candidate_x, candidate_y, radius=0.28
            ):
                guard_x, guard_y = candidate_x, candidate_y
                break
        guard = self._make_story_hunter(guard_x, guard_y, prefix="Relic Guardian")
        guard.kind = "miniboss"
        guard.name = f"Relic Guardian {guard.name.split(' ', 2)[-1]}"
        guard.elite_modifier = "Relic Guardian"
        guard.telegraph = "bound to the guest relic by the opening story choice"
        guard.max_hp = max(1, int(guard.max_hp * 1.45))
        guard.hp = guard.max_hp
        guard.damage += 3 + self.current_depth // 2
        guard.xp += 24 + self.current_depth * 2
        guard.aggro_range += 3.0
        guard.color = self.story_state.accent if self.story_state else self.theme.accent
        self.enemies.append(guard)

    def story_mechanics_summary(self) -> str:
        if self.story_state is None:
            return ""
        forces: list[str] = []
        resist = self.story_effect_value("damage_resist", 0.0, 0.35)
        if resist > 0:
            forces.append(f"Mercy ward -{int(round(resist * 100))}% damage")
        healing = self.story_effect_value("healing_echo", 0.0, 1.0)
        if healing > 0:
            forces.append(f"Echo heals {int(round(min(1.0, healing) * 100))}% on kills")
        relic = self.story_effect_value("relic_power", 0.0, 0.35)
        if relic > 0:
            forces.append(f"Relic power +{int(round(relic * 100))}% spell force")
        blood = self.story_effect_value("blood_price", 0.0, 0.35)
        if blood > 0:
            forces.append("Blood price drains HP on spells")
        damage = self.story_effect_value("damage_bonus", 0.0, 0.35)
        if damage > 0:
            forces.append(f"Defiance +{int(round(damage * 100))}% damage")
        hunters = self.story_effect_value("hunter_pressure", 0.0, 0.35)
        if hunters > 0:
            forces.append("Hunters stalk each new floor")
        pressure = self.story_effect_value("enemy_pressure", -0.35, 0.45)
        if abs(pressure) >= 0.01:
            direction = "more" if pressure > 0 else "fewer"
            forces.append(f"{direction} enemies {int(round(abs(pressure) * 100))}%")
        loot = self.story_effect_value("loot_bonus", 0.0, 0.35)
        if loot > 0:
            forces.append(f"loot +{int(round(loot * 100))}%")
        traps = self.story_effect_value("trap_bonus", 0.0, 0.28)
        if traps > 0:
            forces.append(f"traps +{int(round(traps * 100))}%")
        return " · ".join(forces[:7])

    def story_panel_lines(self) -> list[str]:
        if self.story_state is None:
            return []
        lines = [
            self.story_state.title,
            f"Goal: {self.story_state.objective}",
        ]
        beat = self.current_story_beat()
        if beat is not None:
            status = beat.resolved_choice or "awaiting choice"
            lines.append(f"Depth {beat.depth}: {beat.title} — {status}")
            lines.append(beat.summary)
            if beat.outcome:
                lines.append(f"Outcome: {beat.outcome}")
            else:
                lines.append(beat.dialogue)
                guest = self.nearby_story_guest()
                if guest is not None:
                    choice_details = [
                        f"{index + 1} {choice.label}: {choice.intent} ({self.story_choice_preview(choice.key)})"
                        for index, choice in enumerate(guest.choices[:3])
                    ]
                    lines.append("Choices: " + " · ".join(choice_details))
        mechanics = self.story_mechanics_summary()
        if self.story_intro_pending:
            lines.append(
                "Guest relic: choose 1-3 to bind its first location before the level begins."
            )
        elif self.story_relic_choice_key and not self.story_relic_collected:
            cues = (
                "follow the guiding light"
                if self.story_relic_guidance_enabled
                else "no guiding light; search from the choice clue"
            )
            guard = (
                "guarded by a relic guardian"
                if self.story_relic_guarded
                else "unguarded"
            )
            lines.append(
                f"Guest relic: {self.story_relic_choice_label()} — {cues}; {guard}."
            )
        elif self.story_relic_collected:
            lines.append("Guest relic: recovered; the guest's plea is clearer.")
        if mechanics:
            lines.append(f"Story forces: {mechanics}")
        elif self.story_state.log:
            lines.append(self.story_state.log[-1])
        return lines

    def story_player_damage_bonus(self, spell: bool = False) -> float:
        damage = self.story_effect_value("damage_bonus", 0.0, 0.35)
        relic = self.story_effect_value("relic_power", 0.0, 0.35)
        relic_weight = 1.0 if spell else 0.6
        return min(0.55, damage + relic * relic_weight)

    def apply_story_player_damage(self, damage: int, spell: bool = False) -> int:
        bonus = self.story_player_damage_bonus(spell=spell)
        if bonus <= 0:
            return max(1, damage)
        return max(1, int(round(damage * (1.0 + bonus))))

    def apply_story_blood_price(self, reason: str) -> int:
        price = self.story_effect_value("blood_price", 0.0, 0.35)
        if price <= 0 or self.player.hp <= 1:
            return 0
        cost = max(
            1,
            min(10, int(round(self.player.max_hp * (0.015 + price * 0.18)))),
        )
        actual = min(cost, self.player.hp - 1)
        if actual <= 0:
            return 0
        self.player.hp -= actual
        self.run_stats.damage_taken += actual
        self.floaters.append(
            FloatingText(
                f"{reason.title()} blood price -{actual}",
                self.player.x,
                self.player.y - 0.55,
                self.story_state.accent if self.story_state else (190, 60, 85),
                ttl=1.0,
            )
        )
        self.add_impact(
            self.player.x,
            self.player.y,
            self.story_state.accent if self.story_state else (190, 60, 85),
            ttl=0.36,
            radius=0.42,
            kind="blood",
        )
        return actual

    def resolve_unanswered_story_beat(self) -> str:
        if self.story_state is None:
            return ""
        beat_index = story_beat_index_for_depth(self.story_state, self.current_depth)
        beat = self.current_story_beat()
        if beat is None or beat_index is None or beat.resolved_choice:
            return ""
        if not record_unanswered_story_beat(self.story_state, self.current_depth):
            return ""
        for guest in self.story_guests:
            if guest.depth == self.current_depth and guest.beat_index == beat_index:
                guest.resolved = True
                guest.resolved_choice = "unanswered"
        return f"{beat.guest_name} was forsaken; hunters stir below"

    def _apply_story_theme_for_current_depth(self) -> None:
        plan = self.current_floor_plan()
        if plan is not None:
            self.apply_floor_plan_for_current_depth()
            return
        beat = self.current_story_beat()
        if beat is not None:
            self.theme = self.theme_by_name(beat.theme_name)
            self.run_music_theme = self.theme.name

    def _populate_story_guest(self) -> None:
        if self.story_state is None:
            return
        beat_index = story_beat_index_for_depth(self.story_state, self.current_depth)
        if beat_index is None:
            return
        beat = self.story_state.beats[beat_index]
        if beat.resolved_choice:
            return
        if any(
            guest.depth == self.current_depth and guest.beat_index == beat_index
            for guest in self.story_guests
        ):
            return
        available_rooms = self.dungeon.rooms[1:-1] or self.dungeon.rooms[:1]
        if not available_rooms:
            return
        room = available_rooms[(self.current_depth + beat_index) % len(available_rooms)]
        x, y = room.random_point(self.rng)
        self.story_guests.append(
            story_guest_from_beat(self.story_state, beat_index, x, y)
        )

    def nearby_story_guest(self) -> StoryGuest | None:
        nearby = [
            guest
            for guest in self.story_guests
            if not guest.resolved
            and guest.depth == self.current_depth
            and math.hypot(guest.x - self.player.x, guest.y - self.player.y) < 1.25
        ]
        return min(
            nearby,
            key=lambda guest: math.hypot(
                guest.x - self.player.x, guest.y - self.player.y
            ),
            default=None,
        )

    def mark_story_guest_met(self, guest: StoryGuest) -> None:
        if not guest.met:
            guest.met = True
            self.run_stats.guests_met += 1

    def talk_to_story_guest(self, guest: StoryGuest) -> None:
        self.mark_story_guest_met(guest)
        if self.start_quest_cutscene("story_guest_dialogue", guest):
            return
        self.floaters.append(
            FloatingText(
                f"{guest.role}: choose 1-3",
                guest.x,
                guest.y - 0.55,
                guest.color,
                ttl=1.4,
            )
        )
        self.floaters.append(
            FloatingText(
                guest.motive[:42],
                guest.x,
                guest.y - 0.2,
                (225, 215, 190),
                ttl=1.4,
            )
        )

    def resolve_story_choice(self, guest: StoryGuest, choice_index: int) -> bool:
        if guest.resolved or not (0 <= choice_index < len(guest.choices)):
            return False
        choice = guest.choices[choice_index]
        self.mark_story_guest_met(guest)
        guest.resolved = True
        guest.resolved_choice = choice.key
        if self.story_state is not None:
            record_story_choice(self.story_state, guest.depth, choice)
        self.run_stats.story_choices += 1
        self._apply_story_choice_reward(guest, choice.key)
        self.floaters.append(
            FloatingText(
                f"{choice.label}: story changed",
                guest.x,
                guest.y - 0.65,
                guest.color,
                ttl=1.5,
            )
        )
        self.add_impact(
            guest.x, guest.y, guest.color, ttl=0.58, radius=0.7, kind="burst"
        )
        if (
            self.active_cutscene is not None
            and self.active_cutscene.guest_depth == guest.depth
            and self.active_cutscene.guest_beat_index == guest.beat_index
        ):
            self.close_active_cutscene()
        self.play_sfx("shrine")
        self.save_run()
        return True

    def _apply_story_choice_reward(self, guest: StoryGuest, choice_key: str) -> None:
        if choice_key == "aid":
            self.player.hp = min(
                self.player.max_hp, self.player.hp + max(16, self.player.max_hp // 5)
            )
            self.player.mana = min(
                self.player.max_mana,
                self.player.mana + max(10, self.player.max_mana // 4),
            )
            self.player.stamina = self.player.max_stamina
            revealed = 0
            for secret in sorted(
                self.secrets,
                key=lambda secret: math.hypot(secret.x - guest.x, secret.y - guest.y),
            ):
                if secret.opened or secret.revealed:
                    continue
                if math.hypot(secret.x - guest.x, secret.y - guest.y) > 7.0:
                    continue
                secret.revealed = True
                revealed += 1
                if revealed >= 2:
                    break
            if revealed == 0:
                cache_x, cache_y = self.drop_position_near(guest.x, guest.y)
                self.secrets.append(
                    SecretCache(cache_x, cache_y, "Mercy-Sealed Cache", revealed=True)
                )
            self.shrines.append(Shrine(guest.x, guest.y, "Mending Shrine"))
        elif choice_key == "bargain":
            blood_price = self.story_effect_value("blood_price", 0.0, 0.35)
            cost = max(
                6,
                min(22, int(round(self.player.max_hp * (0.08 + blood_price * 0.45)))),
            )
            previous_hp = self.player.hp
            self.player.hp = max(1, self.player.hp - cost)
            self.run_stats.damage_taken += previous_hp - self.player.hp
            item = self._make_equipment(
                self.rng.choice(("weapon", "armor")),
                "Rare",
                guest.x,
                guest.y,
            )
            self._empower_story_relic_item(item, guaranteed=True)
            self.items.append(item)
        elif choice_key == "defy":
            leveled = self.player.gain_xp(24 + self.current_depth * 3)
            if leveled:
                self.grant_skill_point(reason="story defiance")
            spawn_x, spawn_y = self.drop_position_near(guest.x, guest.y)
            self.enemies.append(
                self._make_story_hunter(spawn_x, spawn_y, prefix="Story-Marked")
            )

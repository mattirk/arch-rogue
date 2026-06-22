from __future__ import annotations

import json
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class CutsceneActorAsset:
    id: str
    name: str
    sprite: str
    x: float
    y: float
    scale: float = 1.0
    color: str = "accent"


@dataclass(frozen=True)
class SpriteAnimationFrameAsset:
    actor: str
    duration: float
    dx: float = 0.0
    dy: float = 0.0
    scale: float = 1.0
    alpha: float = 1.0
    pose: str = "idle"


@dataclass(frozen=True)
class SpriteAnimationAsset:
    id: str
    loop: bool
    frames: tuple[SpriteAnimationFrameAsset, ...]

    @property
    def duration(self) -> float:
        return sum(frame.duration for frame in self.frames)


@dataclass(frozen=True)
class DialogueChoiceAsset:
    label: str
    detail: str = ""
    next_node: str = ""
    action: str = ""
    choice_key: str = ""


@dataclass(frozen=True)
class DialogueNodeAsset:
    id: str
    speaker: str
    text: str
    animation: str = ""
    choice_source: str = ""
    choices: tuple[DialogueChoiceAsset, ...] = ()


@dataclass(frozen=True)
class QuestCutsceneAsset:
    id: str
    title: str
    trigger: str
    start_node: str
    actors: dict[str, CutsceneActorAsset]
    animations: dict[str, SpriteAnimationAsset]
    nodes: dict[str, DialogueNodeAsset]


@dataclass(frozen=True)
class RuntimeDialogueChoice:
    label: str
    detail: str = ""
    next_node: str = ""
    action: str = ""
    choice_key: str = ""
    source_index: int = 0


@dataclass
class ActiveQuestCutscene:
    asset_id: str
    node_id: str
    guest_depth: int = 0
    guest_beat_index: int = -1
    elapsed: float = 0.0
    node_elapsed: float = 0.0
    context: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "node_id": self.node_id,
            "guest_depth": self.guest_depth,
            "guest_beat_index": self.guest_beat_index,
            "elapsed": self.elapsed,
            "node_elapsed": self.node_elapsed,
            "context": dict(self.context),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "ActiveQuestCutscene | None":
        if not isinstance(data, dict):
            return None
        asset_id = str(data.get("asset_id", ""))
        node_id = str(data.get("node_id", ""))
        if not asset_id or not node_id:
            return None
        context_data = data.get("context", {})
        context = (
            {str(key): str(value) for key, value in context_data.items()}
            if isinstance(context_data, dict)
            else {}
        )
        return cls(
            asset_id=asset_id,
            node_id=node_id,
            guest_depth=int(data.get("guest_depth", 0)),
            guest_beat_index=int(data.get("guest_beat_index", -1)),
            elapsed=float(data.get("elapsed", 0.0)),
            node_elapsed=float(data.get("node_elapsed", 0.0)),
            context=context,
        )


class _SafeFormatDict(dict[str, str]):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def format_asset_text(text: str, context: dict[str, str]) -> str:
    return str(text).format_map(_SafeFormatDict(context))


def load_quest_cutscene_library(
    asset_path: str | Path | None = None,
) -> dict[str, QuestCutsceneAsset]:
    """Load and validate quest cutscene assets.

    The built-in pipeline is intentionally JSON-based so authored quest scenes can be
    edited without touching gameplay code. Validation happens at load time to keep
    broken dialogue links or animation references from failing mid-run.
    """

    if asset_path is None:
        asset_text = (
            resources.files("arch_rogue.assets")
            .joinpath("quest_cutscenes.json")
            .read_text(encoding="utf-8")
        )
    else:
        asset_text = Path(asset_path).read_text(encoding="utf-8")
    raw = json.loads(asset_text)
    if not isinstance(raw, dict):
        raise ValueError("Quest cutscene asset root must be an object")
    if int(raw.get("schema_version", 0)) != 1:
        raise ValueError("Unsupported quest cutscene schema_version")
    cutscene_values = raw.get("cutscenes", [])
    if not isinstance(cutscene_values, list):
        raise ValueError("Quest cutscene assets must contain a cutscenes list")

    library: dict[str, QuestCutsceneAsset] = {}
    for cutscene_data in cutscene_values:
        cutscene = _parse_cutscene(cutscene_data)
        if cutscene.id in library:
            raise ValueError(f"Duplicate cutscene id: {cutscene.id}")
        library[cutscene.id] = cutscene
    return library


def _parse_cutscene(data: Any) -> QuestCutsceneAsset:
    if not isinstance(data, dict):
        raise ValueError("Cutscene entry must be an object")
    cutscene_id = _required_str(data, "id", "cutscene")
    title = _required_str(data, "title", cutscene_id)
    trigger = str(data.get("trigger", "manual"))

    actors_list = data.get("actors", [])
    if not isinstance(actors_list, list) or not actors_list:
        raise ValueError(f"Cutscene {cutscene_id} must define at least one actor")
    actors: dict[str, CutsceneActorAsset] = {}
    for actor_data in actors_list:
        actor = _parse_actor(actor_data, cutscene_id)
        if actor.id in actors:
            raise ValueError(f"Cutscene {cutscene_id} has duplicate actor {actor.id}")
        actors[actor.id] = actor

    animations_list = data.get("animations", [])
    if not isinstance(animations_list, list):
        raise ValueError(f"Cutscene {cutscene_id} animations must be a list")
    animations: dict[str, SpriteAnimationAsset] = {}
    for animation_data in animations_list:
        animation = _parse_animation(animation_data, cutscene_id, actors)
        if animation.id in animations:
            raise ValueError(
                f"Cutscene {cutscene_id} has duplicate animation {animation.id}"
            )
        animations[animation.id] = animation

    dialogue_data = data.get("dialogue", {})
    if not isinstance(dialogue_data, dict):
        raise ValueError(f"Cutscene {cutscene_id} dialogue must be an object")
    start_node = _required_str(dialogue_data, "start", cutscene_id)
    nodes_list = dialogue_data.get("nodes", [])
    if not isinstance(nodes_list, list) or not nodes_list:
        raise ValueError(f"Cutscene {cutscene_id} dialogue must define nodes")
    nodes: dict[str, DialogueNodeAsset] = {}
    for node_data in nodes_list:
        node = _parse_node(node_data, cutscene_id)
        if node.id in nodes:
            raise ValueError(f"Cutscene {cutscene_id} has duplicate node {node.id}")
        nodes[node.id] = node

    if start_node not in nodes:
        raise ValueError(f"Cutscene {cutscene_id} start node {start_node} is missing")
    for node in nodes.values():
        if node.speaker and node.speaker not in actors and node.speaker != "narrator":
            raise ValueError(
                f"Cutscene {cutscene_id} node {node.id} uses unknown speaker {node.speaker}"
            )
        if node.animation and node.animation not in animations:
            raise ValueError(
                f"Cutscene {cutscene_id} node {node.id} uses unknown animation {node.animation}"
            )
        for choice in node.choices:
            if choice.next_node and choice.next_node not in nodes:
                raise ValueError(
                    f"Cutscene {cutscene_id} node {node.id} links to missing node {choice.next_node}"
                )

    return QuestCutsceneAsset(
        id=cutscene_id,
        title=title,
        trigger=trigger,
        start_node=start_node,
        actors=actors,
        animations=animations,
        nodes=nodes,
    )


def _parse_actor(data: Any, cutscene_id: str) -> CutsceneActorAsset:
    if not isinstance(data, dict):
        raise ValueError(f"Cutscene {cutscene_id} actor must be an object")
    return CutsceneActorAsset(
        id=_required_str(data, "id", cutscene_id),
        name=str(data.get("name", data.get("id", "actor"))),
        sprite=str(data.get("sprite", "story_guest")),
        x=_normalized_float(data.get("x", 0.5), "actor x", cutscene_id),
        y=_normalized_float(data.get("y", 0.5), "actor y", cutscene_id),
        scale=max(0.1, float(data.get("scale", 1.0))),
        color=str(data.get("color", "accent")),
    )


def _parse_animation(
    data: Any, cutscene_id: str, actors: dict[str, CutsceneActorAsset]
) -> SpriteAnimationAsset:
    if not isinstance(data, dict):
        raise ValueError(f"Cutscene {cutscene_id} animation must be an object")
    animation_id = _required_str(data, "id", cutscene_id)
    frames_list = data.get("frames", [])
    if not isinstance(frames_list, list) or not frames_list:
        raise ValueError(
            f"Cutscene {cutscene_id} animation {animation_id} needs frames"
        )
    frames: list[SpriteAnimationFrameAsset] = []
    for frame_data in frames_list:
        if not isinstance(frame_data, dict):
            raise ValueError(
                f"Cutscene {cutscene_id} animation {animation_id} frame must be an object"
            )
        actor_id = _required_str(frame_data, "actor", animation_id)
        if actor_id not in actors:
            raise ValueError(
                f"Cutscene {cutscene_id} animation {animation_id} references unknown actor {actor_id}"
            )
        duration = float(frame_data.get("duration", 0.0))
        if duration <= 0:
            raise ValueError(
                f"Cutscene {cutscene_id} animation {animation_id} frame duration must be positive"
            )
        frames.append(
            SpriteAnimationFrameAsset(
                actor=actor_id,
                duration=duration,
                dx=float(frame_data.get("dx", 0.0)),
                dy=float(frame_data.get("dy", 0.0)),
                scale=max(0.1, float(frame_data.get("scale", 1.0))),
                alpha=max(0.0, min(1.0, float(frame_data.get("alpha", 1.0)))),
                pose=str(frame_data.get("pose", "idle")),
            )
        )
    return SpriteAnimationAsset(
        id=animation_id,
        loop=bool(data.get("loop", True)),
        frames=tuple(frames),
    )


def _parse_node(data: Any, cutscene_id: str) -> DialogueNodeAsset:
    if not isinstance(data, dict):
        raise ValueError(f"Cutscene {cutscene_id} node must be an object")
    choices_data = data.get("choices", [])
    if not isinstance(choices_data, list):
        raise ValueError(f"Cutscene {cutscene_id} node choices must be a list")
    choices = tuple(_parse_choice(choice, cutscene_id) for choice in choices_data)
    return DialogueNodeAsset(
        id=_required_str(data, "id", cutscene_id),
        speaker=str(data.get("speaker", "narrator")),
        text=str(data.get("text", "")),
        animation=str(data.get("animation", "")),
        choice_source=str(data.get("choice_source", "")),
        choices=choices,
    )


def _parse_choice(data: Any, cutscene_id: str) -> DialogueChoiceAsset:
    if not isinstance(data, dict):
        raise ValueError(f"Cutscene {cutscene_id} choice must be an object")
    return DialogueChoiceAsset(
        label=str(data.get("label", "Continue")),
        detail=str(data.get("detail", "")),
        next_node=str(data.get("next", "")),
        action=str(data.get("action", "")),
        choice_key=str(data.get("choice_key", "")),
    )


def _required_str(data: dict[str, Any], key: str, owner: str) -> str:
    value = str(data.get(key, "")).strip()
    if not value:
        raise ValueError(f"{owner} requires non-empty {key}")
    return value


def _normalized_float(value: Any, label: str, owner: str) -> float:
    result = float(value)
    if not 0.0 <= result <= 1.0:
        raise ValueError(f"{owner} {label} must be between 0 and 1")
    return result

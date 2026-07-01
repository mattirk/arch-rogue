from __future__ import annotations

import json
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Cutscene asset dataclasses
#
# The milestone 3.4 pipeline is fully data-driven: every visual element of the
# stage (curtains, proscenium, footlights, props, spotlights, ambient motes,
# backdrop bands) is described by a frozen dataclass populated from JSON at
# load time. The renderer reads these structures directly so the hot path
# never rebuilds dicts or parses strings per frame.
# ---------------------------------------------------------------------------


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


# --- Stage definition (milestone 3.4) --------------------------------------


@dataclass(frozen=True)
class StagePropAsset:
    """A static or gently animated prop placed on the stage.

    Props are drawn behind actors and described entirely by data so new
    cutscenes can dress the stage without code changes. ``kind`` selects a
    procedural pixel-art routine in the renderer; ``x``/``y`` are normalized
    stage coordinates (0..1).
    """

    id: str
    kind: str
    x: float
    y: float
    scale: float = 1.0
    color: str = "accent"
    phase: float = 0.0
    amplitude: float = 0.0


@dataclass(frozen=True)
class StageLightAsset:
    """A spotlight or ambient light cone aimed at the stage.

    ``target`` is a normalized stage position the light points at; ``tint``
    is a color role name resolved by the renderer. Lights sway subtly using
    a sine phase so the stage feels alive without per-frame allocation.
    """

    id: str
    kind: str
    source_x: float
    source_y: float
    target_x: float
    target_y: float
    radius: float = 0.18
    intensity: float = 0.6
    tint: str = "accent"
    sway: float = 0.0
    phase: float = 0.0


@dataclass(frozen=True)
class AmbientEffectAsset:
    """Repeating ambient particle/effect generator for the stage.

    ``kind`` selects the particle routine (mote, ember, dust, spark, leaf,
    snow). ``count`` particles are simulated each frame from deterministic
    per-index phases so the look is stable and allocation-free.
    """

    kind: str
    count: int = 12
    color: str = "accent"
    speed: float = 1.0
    drift: float = 0.0
    phase: float = 0.0


@dataclass(frozen=True)
class CurtainAsset:
    """Theatrical curtain drape framing the stage.

    ``side`` is ``"left"``, ``"right"`` or ``"both"``. ``gather`` (0..1)
    controls how tightly the curtain is pulled open; ``sway`` controls the
    idle ripple amplitude. Color is a role name resolved by the renderer.
    """

    side: str = "both"
    gather: float = 0.32
    sway: float = 1.0
    color: str = "velvet"
    phase: float = 0.0


@dataclass(frozen=True)
class StageAsset:
    """Full stage dressing for a cutscene.

    All fields default to empty tuples so older schema_version 1 cutscenes
    (which have no ``stage`` block) load cleanly and render with the
    built-in default dressing synthesized by the renderer.
    """

    backdrop: str = "dungeon"
    curtain: CurtainAsset = field(default_factory=CurtainAsset)
    props: tuple[StagePropAsset, ...] = ()
    lights: tuple[StageLightAsset, ...] = ()
    ambient: tuple[AmbientEffectAsset, ...] = ()
    floor_color: str = "stage_floor"
    proscenium: bool = True
    footlights: bool = True


@dataclass(frozen=True)
class QuestCutsceneAsset:
    id: str
    title: str
    trigger: str
    start_node: str
    actors: dict[str, CutsceneActorAsset]
    animations: dict[str, SpriteAnimationAsset]
    nodes: dict[str, DialogueNodeAsset]
    stage: StageAsset = field(default_factory=StageAsset)


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

    The built-in pipeline is intentionally JSON-based so authored quest scenes
    can be edited without touching gameplay code. Validation happens at load
    time to keep broken dialogue links or animation references from failing
    mid-run. Schema version 2 adds the optional ``stage`` block; version 1
    assets are still accepted and fall back to default stage dressing.
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
    schema_version = int(raw.get("schema_version", 0))
    if schema_version not in (1, 2):
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

    stage = _parse_stage(data.get("stage"), cutscene_id)

    return QuestCutsceneAsset(
        id=cutscene_id,
        title=title,
        trigger=trigger,
        start_node=start_node,
        actors=actors,
        animations=animations,
        nodes=nodes,
        stage=stage,
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


def _parse_stage(data: Any, cutscene_id: str) -> StageAsset:
    """Parse the optional ``stage`` block.

    Missing or non-dict stage data yields a default ``StageAsset`` so legacy
    schema_version 1 cutscenes keep working. Every nested list is validated
    and converted to a tuple so the resulting asset is fully immutable and
    safe to share across frames.
    """

    if data is None:
        return StageAsset()
    if not isinstance(data, dict):
        raise ValueError(f"Cutscene {cutscene_id} stage must be an object")

    curtain = _parse_curtain(data.get("curtain"), cutscene_id)

    props_data = data.get("props", [])
    if not isinstance(props_data, list):
        raise ValueError(f"Cutscene {cutscene_id} stage props must be a list")
    props = tuple(_parse_prop(prop, cutscene_id) for prop in props_data)

    lights_data = data.get("lights", [])
    if not isinstance(lights_data, list):
        raise ValueError(f"Cutscene {cutscene_id} stage lights must be a list")
    lights = tuple(_parse_light(light, cutscene_id) for light in lights_data)

    ambient_data = data.get("ambient", [])
    if not isinstance(ambient_data, list):
        raise ValueError(f"Cutscene {cutscene_id} stage ambient must be a list")
    ambient = tuple(_parse_ambient(effect, cutscene_id) for effect in ambient_data)

    return StageAsset(
        backdrop=str(data.get("backdrop", "dungeon")),
        curtain=curtain,
        props=props,
        lights=lights,
        ambient=ambient,
        floor_color=str(data.get("floor_color", "stage_floor")),
        proscenium=bool(data.get("proscenium", True)),
        footlights=bool(data.get("footlights", True)),
    )


def _parse_curtain(data: Any, cutscene_id: str) -> CurtainAsset:
    if data is None:
        return CurtainAsset()
    if not isinstance(data, dict):
        raise ValueError(f"Cutscene {cutscene_id} curtain must be an object")
    side = str(data.get("side", "both"))
    if side not in ("left", "right", "both"):
        raise ValueError(
            f"Cutscene {cutscene_id} curtain side must be left, right, or both"
        )
    return CurtainAsset(
        side=side,
        gather=_normalized_float(
            data.get("gather", 0.32), "curtain gather", cutscene_id
        ),
        sway=max(0.0, float(data.get("sway", 1.0))),
        color=str(data.get("color", "velvet")),
        phase=float(data.get("phase", 0.0)),
    )


def _parse_prop(data: Any, cutscene_id: str) -> StagePropAsset:
    if not isinstance(data, dict):
        raise ValueError(f"Cutscene {cutscene_id} stage prop must be an object")
    kind = str(data.get("kind", "pillar"))
    if kind not in (
        "pillar",
        "altar",
        "lectern",
        "candelabra",
        "banner",
        "brazier",
        "throne",
        "crate",
    ):
        raise ValueError(f"Cutscene {cutscene_id} stage prop kind {kind!r} is unknown")
    return StagePropAsset(
        id=_required_str(data, "id", cutscene_id),
        kind=str(data.get("kind", "pillar")),
        x=_normalized_float(data.get("x", 0.5), "prop x", cutscene_id),
        y=_normalized_float(data.get("y", 0.5), "prop y", cutscene_id),
        scale=max(0.1, float(data.get("scale", 1.0))),
        color=str(data.get("color", "accent")),
        phase=float(data.get("phase", 0.0)),
        amplitude=max(0.0, float(data.get("amplitude", 0.0))),
    )


def _parse_light(data: Any, cutscene_id: str) -> StageLightAsset:
    if not isinstance(data, dict):
        raise ValueError(f"Cutscene {cutscene_id} stage light must be an object")
    kind = str(data.get("kind", "spot"))
    if kind not in ("spot", "cone", "wash", "beam"):
        raise ValueError(
            f"Cutscene {cutscene_id} stage light kind must be spot, cone, wash, or beam"
        )
    return StageLightAsset(
        id=_required_str(data, "id", cutscene_id),
        kind=kind,
        source_x=_normalized_float(
            data.get("source_x", 0.5), "light source_x", cutscene_id
        ),
        source_y=_normalized_float(
            data.get("source_y", 0.0), "light source_y", cutscene_id
        ),
        target_x=_normalized_float(
            data.get("target_x", 0.5), "light target_x", cutscene_id
        ),
        target_y=_normalized_float(
            data.get("target_y", 0.5), "light target_y", cutscene_id
        ),
        radius=max(0.02, float(data.get("radius", 0.18))),
        intensity=max(0.0, min(1.0, float(data.get("intensity", 0.6)))),
        tint=str(data.get("tint", "accent")),
        sway=float(data.get("sway", 0.0)),
        phase=float(data.get("phase", 0.0)),
    )


def _parse_ambient(data: Any, cutscene_id: str) -> AmbientEffectAsset:
    if not isinstance(data, dict):
        raise ValueError(f"Cutscene {cutscene_id} ambient effect must be an object")
    kind = str(data.get("kind", "mote"))
    if kind not in ("mote", "ember", "dust", "spark", "leaf", "snow", "ash"):
        raise ValueError(
            f"Cutscene {cutscene_id} ambient kind must be mote, ember, dust, spark, leaf, snow, ash"
        )
    return AmbientEffectAsset(
        kind=kind,
        count=max(0, min(64, int(data.get("count", 12)))),
        color=str(data.get("color", "accent")),
        speed=max(0.0, float(data.get("speed", 1.0))),
        drift=float(data.get("drift", 0.0)),
        phase=float(data.get("phase", 0.0)),
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

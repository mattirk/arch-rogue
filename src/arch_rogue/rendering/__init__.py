from __future__ import annotations

from .actors import RenderingActorMixin
from .base import RenderingBaseMixin
from .effects import RenderingEffectsMixin
from .hud import RenderingHudMixin
from .story_overlays import RenderingStoryOverlayMixin
from .world import RenderingWorldMixin


class RenderingMixin(
    RenderingBaseMixin,
    RenderingWorldMixin,
    RenderingActorMixin,
    RenderingEffectsMixin,
    RenderingHudMixin,
    RenderingStoryOverlayMixin,
):
    pass


__all__ = ["RenderingMixin"]

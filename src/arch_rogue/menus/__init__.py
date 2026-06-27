from __future__ import annotations

from .base import MenuBaseMixin, MenuRow
from .character import MenuCharacterMixin
from .inventory import MenuInventoryMixin
from .options import MenuOptionsMixin
from .state_overlay import MenuStateOverlayMixin
from .title import MenuTitleMixin


class MenuRenderer(
    MenuBaseMixin,
    MenuTitleMixin,
    MenuOptionsMixin,
    MenuCharacterMixin,
    MenuInventoryMixin,
    MenuStateOverlayMixin,
):
    """Centralized menu and overlay renderer.

    The renderer uses a small set of primitives—centered panels, fixed-width key
    badges, wrapped body text, and clipped single-line labels—so every menu uses
    the same alignment rules instead of hand-placed text offsets.
    """


__all__ = ["MenuRenderer", "MenuRow"]

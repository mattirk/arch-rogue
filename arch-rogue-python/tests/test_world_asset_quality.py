from __future__ import annotations

import hashlib
import itertools
import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pygame

from arch_rogue.constants import DUNGEON_FLOOR_VARIANTS
from arch_rogue.sprites import AssetSpriteLibrary


WORLD_SIZE = (512, 512)
FLOOR_ALPHA_SHA256 = (
    "5f1f96ac06253d2316098fd50ce2a55b89ced494c64972b84455a7efaad67565"
)
WALL_ALPHA_SHA256 = (
    "4443f8ebd3ce3ffe0366d5d79cab5867096beedb3ac454e4d8bf2d4296b660e9"
)
DOOR_ALPHA_SHA256 = (
    "4443f8ebd3ce3ffe0366d5d79cab5867096beedb3ac454e4d8bf2d4296b660e9"
)
STAIR_ALPHA_SHA256 = (
    "20116f156b6bd717c22a052358a491fbe5674209036bd553b8e2f8ac32173792"
)
STAIR_ANIMATION_XOR_SHA256 = (
    "e2799421f5508bab976aa315c95a777d06546af60419fb47664d2fde51c8f814"
)
STAIR_REAR_FROZEN_RGBA_SHA256 = (
    "4b37c7077fc75c20bf12c2f9e1a9215803fec9f80f0e219ced2e4168996f281c"
)
STAIR_REAR_FLOOR_OFFSETS = ((-256, -112), (0, -240), (256, -112))
FLOOR_VARIANT_PATHS = [
    "world/hd/floor.png",
    "world/hd/floor_002.png",
    "world/hd/floor_003.png",
    "world/hd/floor_004.png",
]
GUIDING_OVERLAY_PATHS = [
    f"world/hd/guiding_overlay_{index:03d}.png" for index in range(1, 9)
]
STAIR_FRAME_PATHS = [
    "world/hd/stairs.png",
    *(f"world/hd/stairs_{index:03d}.png" for index in range(1, 8)),
]
WALL_KEYS = [
    "wall",
    *(
        f"wall_{kind}_{side}"
        for kind in ("quest_room", "bar", "garden", "lossless_soul")
        for side in ("left", "right")
    ),
]
HD_DOOR_PATHS = [
    f"world/hd/door_{state}_{side}.png"
    for state in ("closed", "open")
    for side in ("left", "right")
]


def rgba_bytes(surface: pygame.Surface) -> bytes:
    return pygame.image.tobytes(surface, "RGBA")


def alpha_bytes(surface: pygame.Surface) -> bytes:
    return rgba_bytes(surface)[3::4]


def near_black_exterior_boundary(
    surface: pygame.Surface,
    *,
    dark_luma: float = 48.0,
) -> list[tuple[int, int]]:
    """Return opaque exterior-edge pixels dark enough to render as a fringe."""

    width, height = surface.get_size()
    rgba = rgba_bytes(surface)
    alpha = rgba[3::4]
    dark_boundary: list[tuple[int, int]] = []
    for y in range(height):
        for x in range(width):
            pixel = y * width + x
            if alpha[pixel] < 128:
                continue
            if not any(
                nx < 0
                or ny < 0
                or nx >= width
                or ny >= height
                or alpha[ny * width + nx] == 0
                for nx, ny in (
                    (x - 1, y),
                    (x + 1, y),
                    (x, y - 1),
                    (x, y + 1),
                )
            ):
                continue
            offset = pixel * 4
            red, green, blue = rgba[offset : offset + 3]
            luminance = red * 0.2126 + green * 0.7152 + blue * 0.0722
            if luminance < dark_luma:
                dark_boundary.append((x, y))
    return dark_boundary


def max_diagonal_plateau_rows(
    alpha: bytes,
    *,
    start_y: int,
    stop_y: int,
    side: str,
) -> int:
    """Measure the longest unchanged edge run along one diagonal."""

    width = WORLD_SIZE[0]
    edges: list[int] = []
    for y in range(start_y, stop_y):
        row = alpha[y * width : (y + 1) * width]
        if side == "left":
            edge = next(x for x, value in enumerate(row) if value >= 128)
        else:
            edge = next(
                x
                for x in range(width - 1, -1, -1)
                if row[x] >= 128
            )
        edges.append(edge)
    return max(len(list(run)) for _edge, run in itertools.groupby(edges))


def changed_opaque_pixels(
    first: pygame.Surface,
    second: pygame.Surface,
    alpha: bytes,
) -> int:
    first_rgba = rgba_bytes(first)
    second_rgba = rgba_bytes(second)
    return sum(
        first_rgba[offset : offset + 3] != second_rgba[offset : offset + 3]
        for pixel, offset in enumerate(range(0, len(first_rgba), 4))
        if alpha[pixel] >= 128
    )


def partial_delta_blocks(
    first: pygame.Surface,
    second: pygame.Surface,
    *,
    block_size: int = 8,
) -> int:
    """Count aligned blocks containing both changed and unchanged pixels.

    A 64px animation enlarged to 512px with nearest-neighbour scaling changes
    whole aligned 8x8 blocks, so its count is zero. Native-resolution animation
    detail crosses those old block boundaries and yields partial blocks.
    """

    width, height = first.get_size()
    first_rgba = rgba_bytes(first)
    second_rgba = rgba_bytes(second)
    partial = 0
    for block_y in range(0, height, block_size):
        for block_x in range(0, width, block_size):
            changed = 0
            pixels = 0
            for y in range(block_y, min(block_y + block_size, height)):
                row_offset = y * width * 4
                for x in range(block_x, min(block_x + block_size, width)):
                    offset = row_offset + x * 4
                    changed += (
                        first_rgba[offset : offset + 4]
                        != second_rgba[offset : offset + 4]
                    )
                    pixels += 1
            if 0 < changed < pixels:
                partial += 1
    return partial


def square_window_counts(
    values: list[bool],
    width: int,
    height: int,
    radius: int,
) -> list[int]:
    """Count true pixels in every clipped square window using an integral map."""

    stride = width + 1
    integral = [0] * (stride * (height + 1))
    for y in range(height):
        row_total = 0
        source_row = y * width
        previous_row = y * stride
        output_row = (y + 1) * stride
        for x in range(width):
            row_total += values[source_row + x]
            integral[output_row + x + 1] = (
                integral[previous_row + x + 1] + row_total
            )

    counts: list[int] = []
    for y in range(height):
        y0 = max(0, y - radius)
        y1 = min(height, y + radius + 1)
        for x in range(width):
            x0 = max(0, x - radius)
            x1 = min(width, x + radius + 1)
            counts.append(
                integral[y1 * stride + x1]
                - integral[y0 * stride + x1]
                - integral[y1 * stride + x0]
                + integral[y0 * stride + x0]
            )
    return counts


def stair_rear_rim_edit_mask(
    frames: list[pygame.Surface],
    floor: pygame.Surface,
) -> list[bool]:
    """Reconstruct the deterministic N/NW/NE PixelLab normalization mask."""

    width, height = WORLD_SIZE
    frame_rgba = [rgba_bytes(frame) for frame in frames]
    alpha = frame_rgba[0][3::4]
    opaque = [value > 0 for value in alpha]
    inner_area = (20 * 2 + 1) ** 2
    outer_band = [
        visible and count < inner_area
        for visible, count in zip(
            opaque,
            square_window_counts(opaque, width, height, 20),
            strict=True,
        )
    ]

    floor_alpha = alpha_bytes(floor)
    backed_by_neighbor: list[bool] = []
    for y in range(height):
        for x in range(width):
            backed_by_neighbor.append(
                any(
                    0 <= x - offset_x < width
                    and 0 <= y - offset_y < height
                    and floor_alpha[
                        (y - offset_y) * width + x - offset_x
                    ]
                    > 0
                    for offset_x, offset_y in STAIR_REAR_FLOOR_OFFSETS
                )
            )

    animated = [
        any(
            frame[pixel * 4 : pixel * 4 + 4]
            != frame_rgba[0][pixel * 4 : pixel * 4 + 4]
            for frame in frame_rgba[1:]
        )
        for pixel in range(width * height)
    ]
    animation_guard = [
        count > 0
        for count in square_window_counts(animated, width, height, 4)
    ]
    return [
        band and backed and not guarded
        for band, backed, guarded in zip(
            outer_band,
            backed_by_neighbor,
            animation_guard,
            strict=True,
        )
    ]


class WorldAssetQualityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        pygame.init()
        pygame.display.set_mode((64, 64), pygame.HIDDEN)

    @classmethod
    def tearDownClass(cls) -> None:
        pygame.quit()

    def setUp(self) -> None:
        self.library = AssetSpriteLibrary()
        self.assertTrue(self.library.available, self.library.load_error)

    def sources(self, paths: list[str]) -> list[pygame.Surface]:
        surfaces: list[pygame.Surface] = []
        for path in paths:
            surface = self.library._source_surface(path)
            self.assertIsNotNone(surface, path)
            assert surface is not None
            surfaces.append(surface)
        return surfaces

    def test_floor_variants_share_canonical_geometry_but_not_texture(self) -> None:
        entry = self.library.manifest["world"]["floor"]
        self.assertEqual(entry["path"], FLOOR_VARIANT_PATHS[0])
        self.assertEqual(entry.get("variants"), FLOOR_VARIANT_PATHS)
        self.assertEqual(len(FLOOR_VARIANT_PATHS), DUNGEON_FLOOR_VARIANTS)
        self.assertEqual(tuple(entry["source_anchor"]), (256, 320))

        floors = self.sources(FLOOR_VARIANT_PATHS)
        self.assertTrue(all(surface.get_size() == WORLD_SIZE for surface in floors))
        self.assertTrue(
            all(
                surface.get_bounding_rect(min_alpha=1)
                == pygame.Rect(0, 192, 512, 286)
                for surface in floors
            ),
            "generic floor family no longer uses the canonical shallow shell",
        )
        alphas = [alpha_bytes(surface) for surface in floors]
        self.assertTrue(all(alpha == alphas[0] for alpha in alphas[1:]))
        self.assertEqual(hashlib.sha256(alphas[0]).hexdigest(), FLOOR_ALPHA_SHA256)

        opaque_pixels = sum(alpha >= 128 for alpha in alphas[0])
        self.assertGreater(opaque_pixels, 0)
        for first_index, second_index in itertools.combinations(range(4), 2):
            changed = changed_opaque_pixels(
                floors[first_index],
                floors[second_index],
                alphas[0],
            )
            self.assertGreaterEqual(
                changed,
                opaque_pixels // 50,
                (
                    f"floor variants {first_index} and {second_index} differ at "
                    f"only {changed}/{opaque_pixels} visible pixels"
                ),
            )
            self.assertNotEqual(
                rgba_bytes(pygame.transform.flip(floors[first_index], True, False)),
                rgba_bytes(floors[second_index]),
                (
                    f"floor variant {second_index} is only a horizontal mirror "
                    f"of variant {first_index}"
                ),
            )

    def test_guiding_overlays_are_sparse_and_follow_selected_floor(self) -> None:
        floor_entry = self.library.manifest["world"]["floor"]
        guiding_entry = self.library.manifest["world"]["guiding_floor"]
        self.assertNotIn("frames", guiding_entry)
        self.assertEqual(guiding_entry.get("variants"), FLOOR_VARIANT_PATHS)
        self.assertEqual(guiding_entry.get("overlay_frames"), GUIDING_OVERLAY_PATHS)
        self.assertEqual(guiding_entry["source_anchor"], floor_entry["source_anchor"])
        self.assertEqual(guiding_entry["tint_strength"], floor_entry["tint_strength"])
        self.assertEqual(
            self.library.world_animation_frame_count("guiding_floor"),
            len(GUIDING_OVERLAY_PATHS) + 1,
        )

        floor_alpha = alpha_bytes(self.sources([FLOOR_VARIANT_PATHS[0]])[0])
        opaque_floor_pixels = sum(alpha >= 128 for alpha in floor_alpha)
        for path, overlay in zip(
            GUIDING_OVERLAY_PATHS,
            self.sources(GUIDING_OVERLAY_PATHS),
            strict=True,
        ):
            self.assertEqual(overlay.get_size(), WORLD_SIZE, path)
            overlay_alpha = alpha_bytes(overlay)
            visible = sum(alpha > 0 for alpha in overlay_alpha)
            self.assertGreater(visible, 0, path)
            self.assertLess(visible, opaque_floor_pixels // 2, path)
            outside_floor = sum(
                overlay_value > 0 and floor_value == 0
                for overlay_value, floor_value in zip(
                    overlay_alpha, floor_alpha, strict=True
                )
            )
            self.assertEqual(
                outside_floor,
                0,
                f"{path} paints outside the canonical floor silhouette",
            )

        world_kwargs = {
            "target_canvas": WORLD_SIZE,
            "target_anchor": (256, 320),
            "tint": (112, 108, 104),
            "accent": (156, 92, 188),
        }
        resolved_floors: list[bytes] = []
        resolved_guides: list[bytes] = []
        for variant in range(DUNGEON_FLOOR_VARIANTS):
            floor = self.library.resolve_world(
                "floor", **world_kwargs, variant=variant
            )
            plain_guide = self.library.resolve_world(
                "guiding_floor",
                **world_kwargs,
                variant=variant,
                animation_frame=0,
            )
            glowing_guide = self.library.resolve_world(
                "guiding_floor",
                **world_kwargs,
                variant=variant,
                animation_frame=1,
            )
            self.assertIsNotNone(floor)
            self.assertIsNotNone(plain_guide)
            self.assertIsNotNone(glowing_guide)
            assert floor is not None
            assert plain_guide is not None
            assert glowing_guide is not None

            floor_rgba = rgba_bytes(floor[0])
            plain_rgba = rgba_bytes(plain_guide[0])
            glowing_rgba = rgba_bytes(glowing_guide[0])
            self.assertEqual(
                plain_rgba,
                floor_rgba,
                f"guiding frame zero lost floor variant {variant}",
            )
            self.assertEqual(alpha_bytes(glowing_guide[0]), alpha_bytes(floor[0]))
            floor_alpha = alpha_bytes(floor[0])
            changed = sum(
                floor_alpha[offset // 4] > 0
                and floor_rgba[offset : offset + 4]
                != glowing_rgba[offset : offset + 4]
                for offset in range(0, len(floor_rgba), 4)
            )
            # Ignore RGB-only differences underneath alpha=0. Pygame is free
            # to normalize those invisible source pixels during an alpha blit;
            # they cannot make the rendered route visually denser.
            opaque = sum(alpha >= 128 for alpha in floor_alpha)
            self.assertGreater(changed, 0)
            self.assertLess(
                changed,
                opaque // 2,
                "guidance overlay replaced too much of its selected base floor",
            )
            resolved_floors.append(floor_rgba)
            resolved_guides.append(glowing_rgba)

        self.assertEqual(len(set(resolved_floors)), DUNGEON_FLOOR_VARIANTS)
        self.assertEqual(len(set(resolved_guides)), DUNGEON_FLOOR_VARIANTS)

    def test_wall_family_keeps_mask_without_near_black_exterior_fringe(self) -> None:
        surfaces: list[tuple[str, pygame.Surface]] = []
        for key in WALL_KEYS:
            entry = self.library.manifest["world"][key]
            self.assertEqual(tuple(entry["source_anchor"]), (256, 384), key)
            surface = self.sources([entry["path"]])[0]
            self.assertEqual(surface.get_size(), WORLD_SIZE, key)
            self.assertEqual(
                surface.get_bounding_rect(min_alpha=1),
                pygame.Rect(64, 56, 392, 424),
                key,
            )
            alpha = alpha_bytes(surface)
            self.assertEqual(
                hashlib.sha256(alpha).hexdigest(),
                WALL_ALPHA_SHA256,
                f"{key} changed the canonical wall alpha mask",
            )
            surfaces.append((key, surface))

        for key, surface in surfaces:
            dark_boundary = near_black_exterior_boundary(surface)
            self.assertEqual(
                len(dark_boundary),
                0,
                (
                    f"{key} retains {len(dark_boundary)} near-black exterior "
                    f"pixels; examples: {dark_boundary[:8]}"
                ),
            )

        # The former 64px alpha was enlarged into eight-row plateaus. The
        # canonical 512px contour advances on every source row, so maximum zoom
        # sees fine native isometric steps instead of a sawtooth silhouette.
        alpha = alpha_bytes(surfaces[0][1])
        for region, start_y, stop_y in (
            ("upper", 56, 145),
            ("lower", 391, 480),
        ):
            for side in ("left", "right"):
                longest = max_diagonal_plateau_rows(
                    alpha,
                    start_y=start_y,
                    stop_y=stop_y,
                    side=side,
                )
                self.assertLessEqual(
                    longest,
                    1,
                    (
                        f"wall {region}-{side} diagonal retains a "
                        f"{longest}-row sawtooth plateau"
                    ),
                )

    def test_hd_door_family_keeps_geometry_without_black_edge_fringe(self) -> None:
        door_entries = {
            key: entry
            for key, entry in self.library.manifest["world"].items()
            if key in {"door_closed", "door_open"}
            or key.startswith(("door_closed_", "door_open_"))
        }
        self.assertEqual(
            len(door_entries),
            18,
            "every HD door manifest entry must remain covered by this QA check",
        )
        for key, entry in door_entries.items():
            self.assertIn(entry["path"], HD_DOOR_PATHS, key)
            self.assertEqual(tuple(entry["source_anchor"]), (256, 384), key)
            self.assertEqual(entry["reference_width"], 392, key)
            self.assertEqual(entry["tint_strength"], 0.46, key)

        paths = sorted({entry["path"] for entry in door_entries.values()})
        self.assertEqual(paths, sorted(HD_DOOR_PATHS))
        wall_alpha = alpha_bytes(
            self.sources(
                [self.library.manifest["world"]["wall"]["path"]]
            )[0]
        )
        resolved_rgba: list[bytes] = []
        for path, surface in zip(paths, self.sources(paths), strict=True):
            self.assertEqual(surface.get_size(), WORLD_SIZE, path)
            self.assertEqual(
                surface.get_bounding_rect(min_alpha=1),
                pygame.Rect(64, 56, 392, 424),
                path,
            )
            alpha = alpha_bytes(surface)
            self.assertTrue(
                set(alpha) <= {0, 255},
                f"{path} must retain binary transparency",
            )
            self.assertEqual(
                hashlib.sha256(alpha).hexdigest(),
                DOOR_ALPHA_SHA256,
                f"{path} changed the canonical door alpha mask",
            )
            self.assertEqual(
                alpha,
                wall_alpha,
                f"{path} must share the native structural wall contour",
            )
            dark_boundary = near_black_exterior_boundary(surface)
            self.assertEqual(
                len(dark_boundary),
                0,
                (
                    f"{path} retains {len(dark_boundary)} near-black exterior "
                    f"pixels; examples: {dark_boundary[:8]}"
                ),
            )
            for region, start_y, stop_y in (
                ("upper", 56, 145),
                ("lower", 391, 480),
            ):
                for side in ("left", "right"):
                    longest = max_diagonal_plateau_rows(
                        alpha,
                        start_y=start_y,
                        stop_y=stop_y,
                        side=side,
                    )
                    self.assertLessEqual(
                        longest,
                        1,
                        (
                            f"{path} {region}-{side} diagonal retains a "
                            f"{longest}-row sawtooth plateau"
                        ),
                    )
            resolved_rgba.append(rgba_bytes(surface))

        self.assertEqual(
            len(set(resolved_rgba)),
            len(HD_DOOR_PATHS),
            "closed/open and left/right HD doors must remain distinct",
        )

    def test_stair_animation_is_aligned_and_has_native_resolution_deltas(
        self,
    ) -> None:
        entry = self.library.manifest["world"]["stairs"]
        self.assertEqual(entry["path"], STAIR_FRAME_PATHS[0])
        self.assertEqual(entry["frames"], STAIR_FRAME_PATHS)
        self.assertEqual(tuple(entry["source_anchor"]), (256, 336))

        frames = self.sources(STAIR_FRAME_PATHS)
        self.assertTrue(all(frame.get_size() == WORLD_SIZE for frame in frames))
        alphas = [alpha_bytes(frame) for frame in frames]
        self.assertTrue(all(alpha == alphas[0] for alpha in alphas[1:]))
        self.assertEqual(
            hashlib.sha256(alphas[0]).hexdigest(),
            STAIR_ALPHA_SHA256,
            "stair repair changed the canonical floor-matched silhouette",
        )
        bounds = [frame.get_bounding_rect(min_alpha=1) for frame in frames]
        self.assertTrue(all(bound == bounds[0] for bound in bounds[1:]))
        self.assertGreater(bounds[0].width, 0)
        self.assertGreater(bounds[0].height, 0)

        base_rgba = rgba_bytes(frames[0])
        self.assertTrue(all(rgba_bytes(frame) != base_rgba for frame in frames[1:]))
        partial_blocks = [
            partial_delta_blocks(frames[0], frame) for frame in frames[1:]
        ]
        self.assertTrue(
            all(count > 0 for count in partial_blocks),
            (
                "stairs still change only in uniform 8x8 blocks, indicating a "
                f"64px animation enlarged to 512px: {partial_blocks}"
            ),
        )
        self.assertGreaterEqual(
            max(partial_blocks),
            32,
            f"stairs animation has too little native-scale detail: {partial_blocks}",
        )

    def test_stair_rear_rim_matches_neighbor_floor_palette_without_drift(
        self,
    ) -> None:
        frames = self.sources(STAIR_FRAME_PATHS)
        floors = self.sources(FLOOR_VARIANT_PATHS)
        editable = stair_rear_rim_edit_mask(frames, floors[0])
        editable_points = [
            (pixel % WORLD_SIZE[0], pixel // WORLD_SIZE[0])
            for pixel, value in enumerate(editable)
            if value
        ]
        self.assertEqual(len(editable_points), 19_017)
        self.assertEqual(
            (
                min(x for x, _ in editable_points),
                min(y for _, y in editable_points),
                max(x for x, _ in editable_points) + 1,
                max(y for _, y in editable_points) + 1,
            ),
            (26, 89, 486, 339),
        )

        frame_rgba = [rgba_bytes(frame) for frame in frames]
        frozen = bytearray()
        for rgba in frame_rgba:
            for pixel, is_editable in enumerate(editable):
                if not is_editable:
                    frozen.extend(rgba[pixel * 4 : pixel * 4 + 4])
        self.assertEqual(
            hashlib.sha256(frozen).hexdigest(),
            STAIR_REAR_FROZEN_RGBA_SHA256,
            "the stair-rim redraw changed approved pixels outside its mask",
        )

        rim_rgba = bytes(
            channel
            for pixel, is_editable in enumerate(editable)
            if is_editable
            for channel in frame_rgba[0][pixel * 4 : pixel * 4 + 4]
        )
        for rgba in frame_rgba[1:]:
            self.assertEqual(
                bytes(
                    channel
                    for pixel, is_editable in enumerate(editable)
                    if is_editable
                    for channel in rgba[pixel * 4 : pixel * 4 + 4]
                ),
                rim_rgba,
                "the static rear-rim redraw flickers with the stair glow",
            )

        animation_delta = bytearray()
        for rgba in frame_rgba[1:]:
            animation_delta.extend(
                before ^ after
                for before, after in zip(
                    frame_rgba[0],
                    rgba,
                    strict=True,
                )
            )
        self.assertEqual(
            hashlib.sha256(animation_delta).hexdigest(),
            STAIR_ANIMATION_XOR_SHA256,
            "the rear-rim redraw changed the approved violet pulse",
        )

        width, height = WORLD_SIZE
        alpha = frame_rgba[0][3::4]
        boundary: list[tuple[int, int, int]] = []
        for y in range(1, min(300, height - 1)):
            for x in range(1, width - 1):
                pixel = y * width + x
                if alpha[pixel] == 0:
                    continue
                if (
                    alpha[pixel - 1] == 0
                    or alpha[pixel + 1] == 0
                    or alpha[pixel - width] == 0
                    or alpha[pixel + width] == 0
                ):
                    boundary.append((x, y, pixel))
        self.assertEqual(len(boundary), 756)

        dark_boundary = 0
        floor_distances: list[float] = []
        for x, y, pixel in boundary:
            offset = pixel * 4
            red, green, blue = frame_rgba[0][offset : offset + 3]
            luminance = red * 0.2126 + green * 0.7152 + blue * 0.0722
            dark_boundary += luminance < 48

            samples: list[tuple[int, int, int]] = []
            for offset_x, offset_y in STAIR_REAR_FLOOR_OFFSETS:
                floor_x = x - offset_x
                floor_y = y - offset_y
                if not (
                    0 <= floor_x < WORLD_SIZE[0]
                    and 0 <= floor_y < WORLD_SIZE[1]
                ):
                    continue
                for floor in floors:
                    color = floor.get_at((floor_x, floor_y))
                    if color.a:
                        samples.append((color.r, color.g, color.b))
            self.assertTrue(samples, (x, y))
            floor_distances.append(
                min(
                    (
                        abs(red - sample[0])
                        + abs(green - sample[1])
                        + abs(blue - sample[2])
                    )
                    / 3
                    for sample in samples
                )
            )

        self.assertLessEqual(
            dark_boundary,
            16,
            f"rear stair arc retains {dark_boundary} near-black edge pixels",
        )
        self.assertLessEqual(
            sum(floor_distances) / len(floor_distances),
            16,
            "rear stair arc no longer belongs to the neighboring floor palette",
        )
        self.assertLessEqual(
            sum(distance > 48 for distance in floor_distances),
            24,
            "too many rear stair edge pixels contrast sharply with every floor",
        )

    def test_stair_treads_begin_at_the_upper_rim(self) -> None:
        base = self.sources([STAIR_FRAME_PATHS[0]])[0]

        # This corridor follows the clockwise entry run from the rear inner lip
        # to the pre-existing right-side steps.  The former upscale left only
        # isolated bright flecks here; its first substantial tread began at
        # y=213, roughly halfway down the well.
        corridor_surface = pygame.Surface(WORLD_SIZE)
        corridor_surface.fill("black")
        pygame.draw.polygon(
            corridor_surface,
            "white",
            (
                (310, 154),
                (365, 158),
                (398, 190),
                (384, 220),
                (370, 272),
                (283, 272),
                (283, 240),
                (319, 210),
                (300, 184),
            ),
        )
        corridor = pygame.mask.from_threshold(
            corridor_surface, "white", threshold=(1, 1, 1, 255)
        )

        tread = pygame.Mask(WORLD_SIZE)
        for y in range(154, 273):
            for x in range(283, 399):
                if not corridor.get_at((x, y)):
                    continue
                red, green, blue, alpha = base.get_at((x, y))
                luminance = (299 * red + 587 * green + 114 * blue) // 1000
                if alpha >= 128 and luminance >= 130:
                    tread.set_at((x, y))

        substantial = [
            component
            for component in tread.connected_components()
            if component.count() >= 200
        ]
        self.assertTrue(substantial, "upper stair entry has no readable tread")
        first_tread_y = min(
            component.get_bounding_rects()[0].top for component in substantial
        )
        self.assertLessEqual(
            first_tread_y,
            170,
            f"stair treads still begin halfway down the well at y={first_tread_y}",
        )


if __name__ == "__main__":
    unittest.main()

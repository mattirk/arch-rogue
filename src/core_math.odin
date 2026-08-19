package archrogue

import "core:math"

// 2:1 isometric projection. One dungeon tile projects to a 64x32 px diamond
// at zoom 1, matching the pygame game's proportions. Tile space is the unit
// grid (tile (i, j) spans corners (i, j)..(i+1, j+1)); world space is
// isometric screen pixels before camera transform.

TILE_W :: 64
TILE_H :: 32
TILE_HALF_W :: TILE_W / 2
TILE_HALF_H :: TILE_H / 2
CAMERA_FOLLOW_RATE :: 14.0
CAMERA_FOCUS_Y :: 0.48

camera_follow_fraction :: proc(dt: f32) -> f32 {
	if dt <= 0 do return 0
	return 1-math.exp(-CAMERA_FOLLOW_RATE*dt)
}

// Convert a semantic action's normalized lifetime into the seconds consumed
// by the generic sprite sampler. Using the full frame count makes every frame
// reachable before a non-looping action clears at progress 1.
normalized_action_clip_time :: proc(progress: f32, frames: int, fps: f32) -> f32 {
	if frames <= 0 || fps <= 0 do return 0
	return clamp(progress, f32(0), f32(1)) * f32(frames) / fps
}

Vec2 :: [2]f32

world_from_tile :: proc(t: Vec2) -> Vec2 {
	return {(t.x - t.y) * TILE_HALF_W, (t.x + t.y) * TILE_HALF_H}
}

tile_from_world :: proc(w: Vec2) -> Vec2 {
	u := w.x / TILE_HALF_W
	v := w.y / TILE_HALF_H
	return {(v + u) * 0.5, (v - u) * 0.5}
}

vec_rotate :: proc(v: Vec2, angle: f32) -> Vec2 {
	c := math.cos(angle)
	s := math.sin(angle)
	return {c * v.x - s * v.y, s * v.x + c * v.y}
}

mix_color_u8 :: proc(a, b: [4]u8, amount: f32) -> [4]u8 {
	t := clamp(amount, f32(0), f32(1))
	out: [4]u8
	for channel in 0 ..< 4 {
		out[channel] = u8(clamp(f32(a[channel]) + (f32(b[channel]) - f32(a[channel])) * t, 0, 255))
	}
	return out
}

// Tile-space facing -> sprite sheet row. Sheet rows follow the manifest
// direction order (south, south-east, east, north-east, north, north-west,
// west, south-west); the names are screen-space, so project facing to screen
// before bucketing into 45-degree slices.
sprite_row_for_facing :: proc(facing: Vec2) -> int {
	s := Vec2{facing.x - facing.y, (facing.x + facing.y) * 0.5}
	angle := math.atan2(s.y, s.x) // east = 0, screen-south positive
	k := int(math.round(angle / (math.PI / 4)))
	k = ((k % 8) + 8) % 8 // 0=E 1=SE 2=S 3=SW 4=W 5=NW 6=N 7=NE
	rows := [8]int{2, 1, 0, 7, 6, 5, 4, 3}
	return rows[k]
}

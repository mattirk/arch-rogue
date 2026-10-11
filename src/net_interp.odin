package archrogue

// Joiner-side presentation of remote actors (MULTIPLAYER.md section 6,
// "Remote actor interpolation"). Each snapshot is stamped with the host's
// monotonic clock; the joiner renders a slightly delayed host timeline and
// interpolates between the two buffered samples around it. The delay follows
// measured arrival jitter within fixed bounds. Presentation only: nothing here
// feeds gameplay, collision, or command generation.

import "core:math"
import "core:math/linalg"

COOP_INTERP_SAMPLES      :: 12
COOP_RENDER_DELAY_MIN_MS :: f64(50)
COOP_RENDER_DELAY_MAX_MS :: f64(250)
COOP_RENDER_RESYNC_MS    :: f64(400) // timeline error that snaps instead of easing
COOP_EXTRAPOLATE_MS      :: f64(80)  // bounded cosmetic hold past the newest sample
COOP_ARRIVAL_WINDOW      :: 64       // ~2 s of snapshot arrivals

Coop_Actor_Kind :: enum u8 {
	Partner,
	Enemy,
	Familiar,
	Npc,   // shopkeeper (index 0) and ambient residents
	Guest,
	Soul,
	Projectile,
}

Coop_Actor_Sample :: struct {
	key:    u64,
	pos:    Vec2,
	facing: Vec2,
	anim:   f32,
}

Coop_Sample :: struct {
	host_ms: f64,
	actors:  [dynamic]Coop_Actor_Sample,
}

Coop_Interp_State :: struct {
	samples:      [COOP_INTERP_SAMPLES]Coop_Sample,
	count:        int,
	head:         int, // index of the newest sample
	offset_ms:    f64, // local clock minus host clock, lowest-latency estimate
	offset_valid: bool,
	jitter_ms:    f64,
	delay_ms:     f64,
	render_ms:    f64, // host-clock time currently presented
	newest_local: f64, // local arrival time of the newest sample
	last_transit_ms: f64, // newest sample's delivery delay above the fastest seen
	arrivals:     [COOP_ARRIVAL_WINDOW]f64, // recent (local - host) transit samples
	arrival_count: int,
	arrival_head: int,
	render_valid: bool,
}

coop_actor_key :: proc(kind: Coop_Actor_Kind, id: u64) -> u64 {
	return u64(kind) << 56 | (id & 0x00FF_FFFF_FFFF_FFFF)
}

coop_interp_destroy :: proc(s: ^Coop_Interp_State) {
	for &sample in s.samples do delete(sample.actors)
	s^ = {}
}

coop_interp_reset :: proc(s: ^Coop_Interp_State) {
	for &sample in s.samples do clear(&sample.actors)
	s.count = 0
	s.head = 0
	s.render_valid = false
}

// Records the actor positions of an installed snapshot.
coop_interp_record :: proc(s: ^Coop_Interp_State, run: ^Run, host_ms: f64, local_ms: i64) {
	// Clock mapping over a sliding window: the fastest recent delivery fixes
	// the offset, and the spread of recent deliveries (jitter) sets the
	// buffering delay, so a path that slows down is followed within ~2 s.
	d := f64(local_ms) - host_ms
	s.arrivals[s.arrival_head] = d
	s.arrival_head = (s.arrival_head + 1) % COOP_ARRIVAL_WINDOW
	s.arrival_count = min(s.arrival_count + 1, COOP_ARRIVAL_WINDOW)
	lo, hi := d, d
	for k in 0 ..< s.arrival_count {
		lo = min(lo, s.arrivals[k])
		hi = max(hi, s.arrivals[k])
	}
	s.offset_ms = lo
	s.offset_valid = true
	s.jitter_ms = hi - lo
	s.last_transit_ms = d - lo
	// Buffer one snapshot interval plus the transit spread.
	target_delay := clamp(f64(COOP_SNAPSHOT_MS) * 1.5 + s.jitter_ms + 10, COOP_RENDER_DELAY_MIN_MS, COOP_RENDER_DELAY_MAX_MS)
	if s.delay_ms == 0 do s.delay_ms = target_delay
	s.delay_ms += (target_delay - s.delay_ms) * 0.1

	if s.count > 0 && host_ms <= s.samples[s.head].host_ms do return // stale or duplicate
	s.newest_local = f64(local_ms)
	s.head = (s.head + 1) % COOP_INTERP_SAMPLES
	s.count = min(s.count + 1, COOP_INTERP_SAMPLES)
	sample := &s.samples[s.head]
	sample.host_ms = host_ms
	clear(&sample.actors)
	remote := &run.players[1 - run.local_slot]
	append(&sample.actors, Coop_Actor_Sample{coop_actor_key(.Partner, 0), remote.pos, remote.facing, remote.anim_time})
	for &e in run.enemies do append(&sample.actors, Coop_Actor_Sample{coop_actor_key(.Enemy, u64(e.entity_id)), e.pos, e.facing, e.anim_time})
	for &f in run.familiars do append(&sample.actors, Coop_Actor_Sample{coop_actor_key(.Familiar, u64(f.entity_id)), f.pos, f.facing, f.anim_time})
	append(&sample.actors, Coop_Actor_Sample{coop_actor_key(.Npc, 0), run.shopkeeper.pos, run.shopkeeper.motion.facing, run.shopkeeper.motion.anim_time})
	for i in 0 ..< run.ambient_residents.count {
		r := &run.ambient_residents.items[i]
		append(&sample.actors, Coop_Actor_Sample{coop_actor_key(.Npc, u64(i + 1)), r.pos, r.motion.facing, r.motion.anim_time})
	}
	for &g, i in run.story_runtime.guests {
		append(&sample.actors, Coop_Actor_Sample{coop_actor_key(.Guest, u64(i)), g.pos, g.motion.facing, g.motion.anim_time})
	}
	soul := &run.story_runtime.soul
	append(&sample.actors, Coop_Actor_Sample{coop_actor_key(.Soul, 0), soul.pos, soul.motion.facing, soul.motion.anim_time})
	for &p in run.projectiles do append(&sample.actors, Coop_Actor_Sample{coop_actor_key(.Projectile, p.entity_id), p.pos, p.vel, p.visual_age})
}

@(private = "file")
find_actor :: proc(sample: ^Coop_Sample, key: u64, hint: int) -> (Coop_Actor_Sample, bool) {
	if hint >= 0 && hint < len(sample.actors) && sample.actors[hint].key == key do return sample.actors[hint], true
	for a in sample.actors do if a.key == key do return a, true
	return {}, false
}

// Position of one actor on the presented host timeline.
coop_interp_actor :: proc(s: ^Coop_Interp_State, key: u64, hint: int) -> (sample: Coop_Actor_Sample, found: bool) {
	if s.count == 0 do return {}, false
	t := s.render_ms
	newer: ^Coop_Sample
	for k in 0 ..< s.count {
		idx := (s.head - k + COOP_INTERP_SAMPLES) % COOP_INTERP_SAMPLES
		older := &s.samples[idx]
		a, a_ok := find_actor(older, key, hint)
		if older.host_ms <= t || k == s.count - 1 {
			if !a_ok {
				if newer != nil {
					if b, b_ok := find_actor(newer, key, hint); b_ok do return b, true // just spawned
				}
				return {}, false
			}
			if newer == nil do return a, true // at or past the newest sample: hold
			b, b_ok := find_actor(newer, key, hint)
			if !b_ok do return a, true
			span := newer.host_ms - older.host_ms
			if span <= 0 do return b, true
			f := f32(clamp((t - older.host_ms) / span, 0, 1))
			// Never ease through a teleport, respawn, or floor-scale jump.
			if linalg.distance(a.pos, b.pos) > COOP_SNAP_DISTANCE do return f < .5 ? a : b, true
			out := b
			out.pos = linalg.lerp(a.pos, b.pos, f)
			out.anim = a.anim + (b.anim - a.anim) * f
			if f < .5 do out.facing = a.facing
			return out, true
		}
		newer = older
	}
	return {}, false
}

// Advances the presented host time by one fixed tick and pulls it gently
// toward (now - offset - delay), snapping only after a large disruption.
coop_interp_advance :: proc(s: ^Coop_Interp_State, local_ms: i64) {
	if s.count == 0 || !s.offset_valid do return
	// Anchor to the newest arrival rather than a global clock offset, so a
	// path that slows down shifts the timeline immediately instead of
	// running the presentation into the end of the buffer.
	newest := s.samples[s.head].host_ms
	target := newest + (f64(local_ms) - s.newest_local) - s.delay_ms
	target = min(target, newest + COOP_EXTRAPOLATE_MS)
	if !s.render_valid || abs(target - s.render_ms) > COOP_RENDER_RESYNC_MS {
		s.render_ms = target
		s.render_valid = true
		return
	}
	s.render_ms += f64(SIM_DT) * 1000
	s.render_ms += (target - s.render_ms) * 0.08
	s.render_ms = min(s.render_ms, newest + COOP_EXTRAPOLATE_MS)
}

// Applies the presented timeline to every remote actor of the replica.
coop_interp_apply :: proc(s: ^Coop_Interp_State, run: ^Run) {
	if s.count == 0 do return
	place :: proc(s: ^Coop_Interp_State, key: u64, hint: int, pos, prev, facing: ^Vec2, anim: ^f32) {
		sample, ok := coop_interp_actor(s, key, hint)
		if !ok do return
		prev^ = pos^
		pos^ = sample.pos
		if facing != nil && sample.facing != {} do facing^ = sample.facing
		if anim != nil do anim^ = sample.anim
	}
	remote := &run.players[1 - run.local_slot]
	place(s, coop_actor_key(.Partner, 0), 0, &remote.pos, &remote.prev_pos, &remote.facing, &remote.anim_time)
	for &e, i in run.enemies do place(s, coop_actor_key(.Enemy, u64(e.entity_id)), i + 1, &e.pos, &e.prev_pos, &e.facing, &e.anim_time)
	base := 1 + len(run.enemies)
	for &f, i in run.familiars do place(s, coop_actor_key(.Familiar, u64(f.entity_id)), base + i, &f.pos, &f.prev_pos, &f.facing, &f.anim_time)
	base += len(run.familiars)
	place(s, coop_actor_key(.Npc, 0), base, &run.shopkeeper.pos, &run.shopkeeper.prev_pos, &run.shopkeeper.motion.facing, &run.shopkeeper.motion.anim_time)
	for i in 0 ..< run.ambient_residents.count {
		r := &run.ambient_residents.items[i]
		place(s, coop_actor_key(.Npc, u64(i + 1)), base + 1 + i, &r.pos, &r.prev_pos, &r.motion.facing, &r.motion.anim_time)
	}
	for &g, i in run.story_runtime.guests {
		place(s, coop_actor_key(.Guest, u64(i)), -1, &g.pos, &g.prev_pos, &g.motion.facing, &g.motion.anim_time)
	}
	soul := &run.story_runtime.soul
	place(s, coop_actor_key(.Soul, 0), -1, &soul.pos, &soul.prev_pos, &soul.motion.facing, &soul.motion.anim_time)
	// Projectiles ride the same delayed timeline; a shot seen in only one
	// sample so far advances along its host velocity until the next arrives.
	for &p in run.projectiles {
		sample, ok, visible := coop_interp_projectile(s, p.entity_id)
		p.hidden = !visible
		if !ok do continue
		if p.hidden {
			p.pos = sample.pos // park at the spawn point, hidden, until born
			p.prev_pos = p.pos
			continue
		}
		p.prev_pos = p.pos
		p.pos = sample.pos
		p.visual_age = sample.anim
		// Buffer under-run: a straight shot may coast on its host velocity
		// for the bounded extrapolation window instead of freezing.
		newest := &s.samples[s.head]
		if s.render_ms > newest.host_ms {
			ahead := f32((s.render_ms - newest.host_ms) / 1000)
			p.pos += p.vel * ahead
			p.visual_age += ahead
		}
	}
}

coop_interp_snapshot_age_ms :: proc(s: ^Coop_Interp_State, local_ms: i64) -> f64 {
	if s.count == 0 || !s.offset_valid do return 0
	return math.max(0, f64(local_ms) - s.offset_ms - s.samples[s.head].host_ms)
}

// A projectile is visible only while the presented time lies within samples
// that contain it: not before its spawn sample, and not after the last sample
// that still had it (it ended on the host in between).
coop_interp_projectile :: proc(s: ^Coop_Interp_State, id: u64) -> (sample: Coop_Actor_Sample, found, visible: bool) {
	key := coop_actor_key(.Projectile, id)
	sample, found = coop_interp_actor(s, key, -1)
	if !found do return
	newer_has, older_has, have_older := false, false, false
	for k in 0 ..< s.count {
		idx := (s.head - k + COOP_INTERP_SAMPLES) % COOP_INTERP_SAMPLES
		sm := &s.samples[idx]
		has := false
		for a in sm.actors do if a.key == key {has = true; break}
		if sm.host_ms > s.render_ms {
			newer_has = has // the nearest sample after render time
			continue
		}
		older_has, have_older = has, true
		break
	}
	if !have_older do return sample, true, false // timeline before every sample containing it
	if !older_has do return sample, true, false // not spawned yet at render time
	// Spawned; still alive unless the next sample dropped it (or no next
	// sample exists yet, in which case hold at the newest).
	newest_is_older := s.samples[s.head].host_ms <= s.render_ms
	return sample, true, newest_is_older || newer_has
}

package archrogue

// Deterministic presentation events emitted by the headless simulation.
// They consume no RNG and never feed back into gameplay. The renderer reads
// this bounded queue for combat raster, short-lived LOS-clipped lights, and
// scoped screen feedback.

MAX_FEEL_EVENTS :: 128
PLAYER_HIT_FLASH_SECONDS :: 0.22
PLAYER_HEAVY_HIT_FLASH_SECONDS :: 0.32
ENEMY_HIT_FLASH_SECONDS :: 0.22
BOSS_HIT_FLASH_SECONDS :: 0.32

Feel_Kind :: enum {
	Hit,
	Blood,
	Death,
	Burst,
	Slash,
	Cast,
	Dash,
	Time_Skip,
	Nova,
	Summon,
	Command,
	Bell_Plant,
	Bell_Arm,
	Bell_Detonate,
	Knockback_Travel,
	Elite_Death,
	Miniboss_Death,
	Boss_Payoff,
	Screen_Flash,
}

Feel_Phase :: enum u8 {
	None,
	Start,
	End,
	Origin,
	Arrival,
	Triggered,
	Expired,
}

Feel_Style :: enum u8 {
	Generic,
	Warden,
	Rogue,
	Arcanist,
	Acolyte,
	Ranger,
	Enemy,
}

Feel_Visibility :: enum u8 {
	World,        // raster/light/screen cue requires current LOS at its origin
	Player_Local, // local pain/feedback remains visible regardless of origin lookup
	Global,       // transitions and other deliberate full-screen presentation
}

Feel_Priority :: enum u8 {
	Low,
	Normal,
	High,
	Critical,
}

Feel_Event :: struct {
	kind:       Feel_Kind,
	phase:      Feel_Phase,
	style:      Feel_Style,
	visibility: Feel_Visibility,
	priority:   Feel_Priority,
	pos:        Vec2,
	direction:  Vec2,
	color:      [4]u8,
	remaining:  f32,
	duration:   f32,
	radius:     f32,
	heavy:      bool,
	engulf_room: bool,
}

Feel_Light_Profile :: struct {
	radius:    f32,
	intensity: f32,
	duration:  f32,
	lift:      f32,
	enabled:   bool,
}

feel_style_for_archetype :: proc(archetype: Archetype_Id) -> Feel_Style {
	switch archetype {
	case .Warden:   return .Warden
	case .Rogue:    return .Rogue
	case .Arcanist: return .Arcanist
	case .Acolyte:  return .Acolyte
	case .Ranger:   return .Ranger
	}
	return .Generic
}

feel_emit :: proc(
	run: ^Run,
	kind: Feel_Kind,
	pos: Vec2,
	color: [4]u8,
	duration, radius: f32,
	direction := Vec2{},
	phase := Feel_Phase.None,
	style := Feel_Style.Generic,
	visibility := Feel_Visibility.World,
	priority := Feel_Priority.Normal,
	heavy := false,
	engulf_room := false,
) {
	if run == nil || duration <= 0 do return
	event := Feel_Event{
		kind=kind,phase=phase,style=style,visibility=visibility,priority=priority,
		pos=pos,direction=direction,color=color,
		remaining=duration,duration=duration,radius=radius,
		heavy=heavy,engulf_room=engulf_room,
	}
	if len(run.feel) < MAX_FEEL_EVENTS {
		append(&run.feel, event)
		return
	}

	// Presentation overload must never grow without bound or perturb gameplay.
	// A critical payoff may deterministically replace the oldest lower-priority
	// spark; equal/lower-priority overflow remains drop-new and RNG-free.
	for &old, index in run.feel {
		if int(old.priority) >= int(priority) do continue
		run.feel[index] = event
		return
	}
}

feel_emit_enemy_hit :: proc(run: ^Run, enemy: ^Enemy, damage_type: Damage_Type) {
	if enemy == nil do return
	boss := enemy.role == .Boss
	feel_emit(
		run,.Hit,enemy.pos,DAMAGE_TYPE_COLORS[damage_type],
		boss ? f32(.46) : f32(.32),
		boss ? f32(.58) : f32(.36),
		priority = boss ? Feel_Priority.High : Feel_Priority.Low,
	)
}

mark_enemy_hit_flash :: proc(enemy: ^Enemy) {
	if enemy == nil do return
	enemy.hit_flash = 1
	enemy.hit_flash_duration = enemy.role == .Boss ? BOSS_HIT_FLASH_SECONDS : ENEMY_HIT_FLASH_SECONDS
}

mark_player_hit_flash :: proc(player: ^Player, damage: int) {
	if player == nil || damage <= 0 do return
	heavy := f32(damage) >= f32(player.max_hp)*.18
	player.hit_flash = 1
	player.hit_flash_duration = heavy ? PLAYER_HEAVY_HIT_FLASH_SECONDS : PLAYER_HIT_FLASH_SECONDS
}

feel_emit_player_hurt :: proc(run: ^Run, damage: int) {
	if run == nil || damage <= 0 do return
	heavy := f32(damage) >= f32(run.player.max_hp) * .18
	flash_color := heavy ? [4]u8{160,35,32,255} : [4]u8{105,24,28,255}
	flash_duration: f32 = heavy ? .30 : .18
	feel_emit(run,.Blood,run.player.pos,{245,95,70,255},.34,.42,priority=.High)
	feel_emit(
		run,.Screen_Flash,run.player.pos,flash_color,flash_duration,0,
		visibility=.Player_Local,priority=.Critical,
	)
}

feel_emit_enemy_death :: proc(run: ^Run, enemy: ^Enemy, accent: [4]u8) {
	if run == nil || enemy == nil do return
	// Preserve the established body-death timelines; semantic rank events add
	// the MX.6 payoff vocabulary without shortening the corpse send-off.
	body_duration: f32 = .58
	body_radius: f32 = enemy.big ? .86 : .56
	#partial switch enemy.role {
	case .Elite:
		body_duration, body_radius = .66, .68
	case .Miniboss:
		body_duration, body_radius = .74, .80
	case .Boss:
		body_duration, body_radius = .82, 1.05
	}
	feel_emit(run,.Death,enemy.pos,enemy.color,body_duration,body_radius,priority=.High)
	rank_radius: f32 = enemy.big ? .96 : .66
	switch enemy.role {
	case .Elite:
		feel_emit(run,.Elite_Death,enemy.pos,enemy.color,.48,rank_radius,priority=.High)
	case .Miniboss:
		feel_emit(run,.Miniboss_Death,enemy.pos,accent,.48,rank_radius,priority=.High)
	case .Boss:
		feel_emit(run,.Boss_Payoff,enemy.pos,accent,.72,enemy.big ? f32(.96) : f32(.82),priority=.Critical)
		feel_emit(
			run,.Screen_Flash,enemy.pos,accent,.36,0,
			visibility=.World,priority=.Critical,
		)
	case .Normal:
	}
}

feel_emit_slash :: proc(run: ^Run, pos, direction: Vec2, heavy := false) {
	duration: f32 = heavy ? .24 : .18
	radius: f32 = heavy ? .62 : .42
	feel_emit(
		run,.Slash,pos,{255,235,170,255},duration,radius,direction,
		priority=heavy ? Feel_Priority.High : Feel_Priority.Normal,heavy=heavy,
	)
	if heavy do feel_emit(run,.Burst,pos,{221,168,83,255},.42,.62,priority=.High)
}

feel_emit_enemy_slash :: proc(run: ^Run, pos, direction: Vec2, color: [4]u8) {
	feel_emit(run,.Slash,pos,color,.14,.42,direction,style=.Enemy)
}

feel_enemy_cast_color :: proc(run: ^Run, enemy: ^Enemy) -> [4]u8 {
	if enemy == nil do return DAMAGE_TYPE_COLORS[.Arcane]
	color := DAMAGE_TYPE_COLORS[enemy.damage_type]
	if run != nil && (enemy.role == .Miniboss || enemy.role == .Boss) {
		color = THEMES[clamp(run.theme_index, 0, len(THEMES)-1)].accent
	}
	return color
}

feel_emit_enemy_cast :: proc(run: ^Run, enemy: ^Enemy, radius: f32 = .36) {
	if run == nil || enemy == nil do return
	feel_emit(
		run,.Cast,enemy.pos,feel_enemy_cast_color(run, enemy),.28,radius,
		direction=enemy.facing,style=.Enemy,priority=enemy.role == .Boss ? Feel_Priority.High : Feel_Priority.Normal,
	)
}

feel_emit_enemy_nova :: proc(run: ^Run, enemy: ^Enemy, radius: f32) {
	if run == nil || enemy == nil do return
	feel_emit(
		run,.Nova,enemy.pos,feel_enemy_cast_color(run, enemy),.40,radius,
		direction=enemy.facing,style=.Enemy,priority=enemy.role == .Boss ? Feel_Priority.High : Feel_Priority.Normal,
	)
}

feel_event_visible :: proc(event: ^Feel_Event, source_visible, dev_reveal: bool) -> bool {
	if event == nil do return false
	if dev_reveal do return true
	return event.visibility != .World || source_visible
}

feel_light_profile :: proc(event: ^Feel_Event) -> Feel_Light_Profile {
	if event == nil do return {}
	switch event.kind {
	case .Cast, .Time_Skip, .Nova:
		return {radius=2.1,intensity=.85,duration=.28,lift=12,enabled=true}
	case .Dash:
		duration: f32 = event.phase == .End ? .26 : .24
		return {radius=2.1,intensity=.85,duration=duration,lift=12,enabled=true}
	case .Summon:
		if event.phase == .Arrival do return {radius=1.8,intensity=.70,duration=.22,lift=10,enabled=true}
		return {radius=2.1,intensity=.85,duration=.28,lift=12,enabled=true}
	case .Command:
		return {radius=1.8,intensity=.70,duration=.22,lift=10,enabled=true}
	case .Bell_Plant:
		return {radius=1.8,intensity=.75,duration=.30,lift=6,enabled=true}
	case .Bell_Arm:
		return {radius=1.45,intensity=.55,duration=.24,lift=6,enabled=true}
	case .Bell_Detonate:
		if event.phase == .Expired do return {radius=2.0,intensity=.55,duration=.34,lift=8,enabled=true}
		return {radius=2.8,intensity=.85,duration=.42,lift=8,enabled=true}
	case .Knockback_Travel:
		return {radius=1.3,intensity=.42,duration=.18,lift=10,enabled=true}
	case .Elite_Death:
		return {radius=1.8,intensity=.62,duration=.24,lift=12,enabled=true}
	case .Miniboss_Death:
		return {radius=2.3,intensity=.72,duration=.30,lift=12,enabled=true}
	case .Boss_Payoff:
		return {radius=3.2,intensity=.92,duration=.45,lift=14,enabled=true}
	case .Hit, .Blood, .Death, .Burst, .Slash, .Screen_Flash:
	}
	return {}
}

feel_light_life :: proc(event: ^Feel_Event, profile: Feel_Light_Profile) -> f32 {
	if event == nil || !profile.enabled || profile.duration <= 0 do return 0
	elapsed := max(f32(0), event.duration - event.remaining)
	return clamp(1 - elapsed / profile.duration, f32(0), f32(1))
}

tick_feel_events :: proc(run: ^Run, dt: f32) {
	if run == nil || dt <= 0 do return
	// Stable compaction keeps equal-depth event painter order reproducible as
	// older cues expire; unordered removal used to reshuffle survivors.
	write := 0
	for read in 0 ..< len(run.feel) {
		run.feel[read].remaining -= dt
		if run.feel[read].remaining <= 0 do continue
		if write != read do run.feel[write] = run.feel[read]
		write += 1
	}
	if write != len(run.feel) do resize(&run.feel, write)
}

clear_feel_events :: proc(run: ^Run) {
	if run != nil do clear(&run.feel)
}

feel_progress :: proc(event: ^Feel_Event) -> f32 {
	if event == nil || event.duration <= 0 do return 1
	return clamp(1-event.remaining/event.duration,0,1)
}

feel_life :: proc(event: ^Feel_Event) -> f32 {
	if event == nil || event.duration <= 0 do return 0
	return clamp(event.remaining/event.duration,0,1)
}

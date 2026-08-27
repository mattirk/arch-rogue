package archrogue

// Dev-only capture, screenshot, and deterministic perf staging. These scenarios
// are driven by desktop env toggles or the web profiling harness; ordinary
// simulation and renderer APIs stay free of capture concerns. Staging consumes
// no gameplay RNG streams beyond the documented derived perf streams.

import "core:math"
import "core:fmt"
import "core:strconv"

MX6_Capture_Scenario :: enum u8 {
	None,
	Melee,
	Big_Hit,
	Bolt,
	Class_Skill,
	Dash,
	Enemy_Base_Melee,
	Enemy_Base_Ranged,
	Enemy_Strike,
	Enemy_Bolt,
	Enemy_Fan,
	Enemy_Nova,
	Miniboss,
	Boss_Attack,
	Boss_Cast,
	Familiar_Wisp,
	Familiar_Crow,
	Familiar_Beast,
	Fow_Nova,
}

dev_archetype_from_env :: proc(value:string) -> (Archetype_Id,bool) {
	switch value {
	case "warden":   return .Warden,true
	case "rogue":    return .Rogue,true
	case "arcanist": return .Arcanist,true
	case "acolyte":  return .Acolyte,true
	case "ranger":   return .Ranger,true
	}
	if index,ok:=strconv.parse_int(value);ok && 0<=index && index<len(Archetype_Id) {
		return Archetype_Id(index),true
	}
	return {},false
}

MX_Story_Capture_Scenario :: enum u8 {
	None,
	Omen_Initial,
	Relic_Choices,
	Guest,
	Soul,
	Mistbound,
	Ending,
}

mx_story_capture_scenario_from_env :: proc(value: string) -> MX_Story_Capture_Scenario {
	switch value {
	case "omen_initial":  return .Omen_Initial
	case "relic_choices": return .Relic_Choices
	case "guest":         return .Guest
	case "soul":          return .Soul
	case "mistbound":     return .Mistbound
	case "ending":        return .Ending
	}
	return .None
}

MX_Save_Capture_Scenario :: enum u8 {
	None,
	Empty,
	Populated,
	Victories,
	Fallen,
	Recovery,
	Abandon,
}

mx_save_capture_scenario_from_env :: proc(value:string)->MX_Save_Capture_Scenario {
	switch value {
	case "empty":return .Empty
	case "populated":return .Populated
	case "victories":return .Victories
	case "fallen":return .Fallen
	case "recovery":return .Recovery
	case "abandon":return .Abandon
	}
	return .None
}

mx6_capture_scenario_from_env :: proc(value:string) -> MX6_Capture_Scenario {
	switch value {
	case "melee":              return .Melee
	case "big_hit":            return .Big_Hit
	case "bolt":               return .Bolt
	case "class":              return .Class_Skill
	case "dash":               return .Dash
	case "enemy_base_melee":   return .Enemy_Base_Melee
	case "enemy_base_ranged":  return .Enemy_Base_Ranged
	case "enemy_strike":       return .Enemy_Strike
	case "enemy_bolt":         return .Enemy_Bolt
	case "enemy_fan":          return .Enemy_Fan
	case "enemy_nova":         return .Enemy_Nova
	case "miniboss":           return .Miniboss
	case "boss_attack":        return .Boss_Attack
	case "boss_cast":          return .Boss_Cast
	case "familiar_wisp":      return .Familiar_Wisp
	case "familiar_crow":      return .Familiar_Crow
	case "familiar_beast":     return .Familiar_Beast
	case "fow_nova":           return .Fow_Nova
	}
	return .None
}

mx6_capture_direction_from_env :: proc(value:string) -> (Vec2,bool) {
	// Names are screen-space; vectors are tile-space before isometric projection.
	switch value {
	case "south":      return { 1, 1},true
	case "south-east": return { 1, 0},true
	case "east":       return { 1,-1},true
	case "north-east": return { 0,-1},true
	case "north":      return {-1,-1},true
	case "north-west": return {-1, 0},true
	case "west":       return {-1, 1},true
	case "south-west": return { 0, 1},true
	}
	return {},false
}

@(private = "file")
mx6_capture_unit :: proc(direction:Vec2) -> Vec2 {
	length:=math.hypot(direction.x,direction.y)
	return length>1e-5?direction/length:Vec2{1,1}/math.sqrt(f32(2))
}

@(private = "file")
mx6_capture_place :: proc(
	run:^Run,
	origin,direction:Vec2,
	distance,radius:f32,
) -> (Vec2,bool) {
	if run==nil do return {},false
	unit:=mx6_capture_unit(direction)
	// Step inward deterministically if a small room or furnishing clips the ideal
	// composition. No gameplay RNG is consumed by capture placement.
	for step in 0..<16 {
		d:=distance-f32(step)*.08
		if d<.55 do break
		candidate:=origin+unit*d
		if blocked_for_radius(&run.dungeon,candidate.x,candidate.y,radius,block_stairs=true) do continue
		if !line_of_sight(&run.dungeon,origin.x,origin.y,candidate.x,candidate.y) do continue
		return candidate,true
	}
	return origin,false
}

@(private = "file")
mx6_capture_reset :: proc(app:^App,direction:Vec2) -> Vec2 {
	run:=&app.run
	restore_sealed(&run.dungeon,run.sealed[:])
	clear(&run.sealed)
	clear(&run.enemies)
	clear(&run.projectiles)
	clear(&run.familiars)
	clear(&run.bells)
	clear(&run.numbers)
	clear(&run.ground_items)
	clear(&run.sfx)
	clear_feel_events(run)
	clear(&run.traps)
	clear(&run.shrines)
	clear(&run.secrets)
	run.nav={}
	run.boss_engaged=false
	// Artificial first-room bosses must not be recovered into a generated final
	// arena by the encounter watchdog during the one-step real commit below.
	run.dungeon.boss_arena=false
	run.arrival_timer=0
	run.wall_face_timer=0
	run.wall_touches=0
	run.shop_requested=false
	run.refuge={}

	app.death_pending=false
	app.death_timer=0
	app.inventory_open=false
	app.character_open=false
	app.shop_open=false
	app_story_close_panel(app)
	app.story_minigame={}
	app_clear_play_input(app)

	player:=&run.player
	player.pos=run_spawn_point(run)
	player.prev_pos=player.pos
	player.facing=mx6_capture_unit(direction)
	player.moving=false
	player.hp=player.max_hp
	player.mana=f32(player.max_mana)
	player.stamina=f32(player.max_stamina)
	player.melee_timer=0
	player.bolt_timer=0
	player.dash_timer=0
	player.class_skill_timer=0
	player.bighit_timer=0
	player.bighit_charge=0
	player.time_skip_timer=0
	player.swing_timer=0
	player.melee_commit_timer=0
	player.potion_timer=0
	player.hit_flash=0
	player.hit_flash_duration=0
	player.statuses={}
	player.poison_tick=0
	run.hitstop_ticks=0
	player_clear_visual_action(player)
	return player.facing
}

@(private = "file")
mx6_capture_shift_player :: proc(run:^Run,direction:Vec2,distance:f32) {
	if run==nil do return
	candidate:=run.player.pos+mx6_capture_unit(direction)*distance
	if blocked_for_radius(
		&run.dungeon,candidate.x,candidate.y,ACTOR_MOVE_COLLISION_RADIUS,block_stairs=true,
	) {
		return
	}
	run.player.pos=candidate
	run.player.prev_pos=candidate
}

@(private = "file")
mx6_capture_enemy :: proc(
	run:^Run,
	kind:Enemy_Kind,
	pos,facing:Vec2,
	pending:int,
	ability:Ability_Id={},
	has_ability:=false,
) {
	enemy:=enemy_make(kind,pos,run.depth)
	enemy.prev_pos=pos
	enemy.facing=facing
	enemy.aggro_range=max(enemy.aggro_range,f32(12))
	enemy.cooldown=0
	if has_ability {
		enemy.ability_count=1
		enemy.abilities[0]=ability
	}
	enemy_ensure_id(run,&enemy)
	enemy_begin_windup(&enemy,0,pending,facing)
	append(&run.enemies,enemy)
	// The public fixed-step path commits the windup, emits semantic effects and
	// creates real projectiles/damage. Follow-up ticks reach a readable action
	// frame while the freshly emitted feel events remain unaged.
	for _ in 0..<5 do sim_tick(run,{})
}

@(private = "file")
mx6_capture_boss :: proc(run:^Run,pos,facing:Vec2,ability:Ability_Id) {
	def:=BOSS_DEFS[Boss_Id.Gate_Tyrant]
	boss:=Enemy{
		kind=.Ghoul,
		boss_id=.Gate_Tyrant,
		name=def.name,
		role=.Boss,
		elite_mod=-1,
		final_boss=def.final_boss,
		big=true,
		pos=pos,
		prev_pos=pos,
		facing=facing,
		hp=def.max_hp,
		max_hp=def.max_hp,
		damage=def.damage,
		xp=def.xp,
		speed=def.speed,
		aggro_range=def.aggro_range,
		attack_range=def.attack_range,
		attack_cd_s=def.attack_cooldown,
		ranged=def.attack_range>=2,
		color=def.color,
		damage_type=def.damage_type,
		abilities={ability,ability},
		ability_count=1,
		pending_ability=PENDING_BASE_ATTACK,
		last_ability=-1,
	}
	enemy_ensure_id(run,&boss)
	enemy_begin_windup(&boss,0,0,facing)
	append(&run.enemies,boss)
	run.boss_engaged=true
	for _ in 0..<5 do sim_tick(run,{})
}

@(private = "file")
mx6_capture_familiar :: proc(run:^Run,direction:Vec2,kind:Familiar_Kind) {
	spawned:=false
	switch kind {
	case .Wisp:
		spawned=player_cast_spirit_call_rank(run,0)
	case .Crow:
		spawned=player_cast_spirit_call_rank(run,1)
	case .Spirit_Beast:
		spawned=player_cast_spirit_beast_rank(run,0)
	case .Bar_Dancer, .Soulless_Clanker, .String:
	}
	if !spawned || len(run.familiars)==0 do return

	// The summon was only the public construction path; isolate the requested
	// attack/fallback moment before driving companion AI against a real target.
	clear(&run.numbers)
	clear(&run.sfx)
	clear_feel_events(run)
	player_clear_visual_action(&run.player)
	familiar:=&run.familiars[0]
	facing:=mx6_capture_unit(direction)
	if pos,ok:=mx6_capture_place(run,run.player.pos,facing,.78,FAMILIAR_MOVE_COLLISION_RADIUS);ok {
		familiar.pos=pos
		familiar.prev_pos=pos
	}
	familiar.facing=facing
	familiar.move_dir=facing
	familiar.command=.Attack
	familiar.attack_timer=0
	familiar.attack_anim_timer=0
	familiar.moving=false

	target_pos,ok:=mx6_capture_place(run,familiar.pos,facing,.82,ACTOR_MOVE_COLLISION_RADIUS)
	if !ok do return
	target:=enemy_make(.Ghoul,target_pos,run.depth)
	target.prev_pos=target_pos
	target.facing=-facing
	target.hp=max(target.hp,200)
	target.max_hp=target.hp
	target.cooldown=100
	target.aggro_range=0
	enemy_ensure_id(run,&target)
	append(&run.enemies,target)
	tick_familiars_dt(run,.01)
	tick_familiars_dt(run,.10)
}

mx6_stage_capture :: proc(app:^App,view:^View,scenario:MX6_Capture_Scenario,direction:Vec2) {
	if app==nil || view==nil || app.mode!=.Playing || scenario==.None do return
	run:=&app.run
	facing:=mx6_capture_reset(app,direction)
	player:=&run.player
	if .Enemy_Base_Melee<=scenario && scenario<=.Boss_Cast {
		mx6_capture_shift_player(run,facing,.45)
	}

	switch scenario {
	case .Melee:
		player_melee(run,facing)
		player_tick_visual_action(player,.08)
	case .Big_Hit:
		if player_big_hit_begin(run,facing) {
			player_big_hit_fire(run)
			player_tick_visual_action(player,.10)
		}
	case .Bolt:
		if player_cast_bolt(run,facing) {
			for _ in 0..<5 do sim_tick(run,{})
		}
	case .Class_Skill:
		if player_cast_class_skill(run,facing) {
			player_tick_visual_action(player,.12)
		}
	case .Dash:
		if player_dash(run,facing) do player_tick_visual_action(player,.08)
	case .Enemy_Base_Melee:
		if pos,ok:=mx6_capture_place(run,player.pos,-facing,1.15,ACTOR_MOVE_COLLISION_RADIUS);ok {
			mx6_capture_enemy(run,.Gate_Warden,pos,facing,PENDING_BASE_ATTACK)
		}
	case .Enemy_Base_Ranged:
		if pos,ok:=mx6_capture_place(run,player.pos,-facing,1.85,ACTOR_MOVE_COLLISION_RADIUS);ok {
			mx6_capture_enemy(run,.Grave_Archer,pos,facing,PENDING_BASE_ATTACK)
		}
	case .Enemy_Strike:
		if pos,ok:=mx6_capture_place(run,player.pos,-facing,1.15,ACTOR_MOVE_COLLISION_RADIUS);ok {
			mx6_capture_enemy(run,.Gate_Warden,pos,facing,0,.Gate_Strike,true)
		}
	case .Enemy_Bolt:
		if pos,ok:=mx6_capture_place(run,player.pos,-facing,2.25,ACTOR_MOVE_COLLISION_RADIUS);ok {
			mx6_capture_enemy(run,.Cultist,pos,facing,0,.Arcane_Lance,true)
		}
	case .Enemy_Fan:
		if pos,ok:=mx6_capture_place(run,player.pos,-facing,2.25,ACTOR_MOVE_COLLISION_RADIUS);ok {
			mx6_capture_enemy(run,.Grave_Archer,pos,facing,0,.Frost_Fan,true)
		}
	case .Enemy_Nova:
		if pos,ok:=mx6_capture_place(run,player.pos,-facing,1.75,ACTOR_MOVE_COLLISION_RADIUS);ok {
			mx6_capture_enemy(run,.Plague_Toad,pos,facing,0,.Ember_Nova,true)
		}
	case .Miniboss:
		if pos,ok:=mx6_capture_place(run,player.pos,-facing,1.55,ACTOR_MOVE_COLLISION_RADIUS);ok {
			enemy:=enemy_make(.Crypt_Brute,pos,run.depth)
			enemy.prev_pos=pos
			enemy.facing=facing
			enemy.cooldown=100
			enemy.aggro_range=0
			promote_miniboss(&enemy,THEMES[run.theme_index].accent)
			enemy_ensure_id(run,&enemy)
			append(&run.enemies,enemy)
		}
	case .Boss_Attack:
		if pos,ok:=mx6_capture_place(run,player.pos,-facing,1.40,BOSS_MOVE_RADIUS);ok {
			mx6_capture_boss(run,pos,facing,.Gate_Strike)
		}
	case .Boss_Cast:
		if pos,ok:=mx6_capture_place(run,player.pos,-facing,2.25,BOSS_MOVE_RADIUS);ok {
			// Semantic Cast deliberately resolves through the boss Attack sheet.
			mx6_capture_boss(run,pos,facing,.Shadow_Volley)
		}
	case .Familiar_Wisp:
		mx6_capture_familiar(run,facing,.Wisp)
	case .Familiar_Crow:
		mx6_capture_familiar(run,facing,.Crow)
	case .Familiar_Beast:
		mx6_capture_familiar(run,facing,.Spirit_Beast)
	case .Fow_Nova:
		// Put the caster beside the first room's north-west wall. The live-LOS
		// shader must clip this wide ring at the room boundary even with lighting
		// disabled; reveal-mode comparison intentionally bypasses the clip.
		room:=run.dungeon.rooms_buf[0]
		player.pos={f32(room.x)+1.2,f32(room.y)+1.2}
		player.prev_pos=player.pos
		player.facing={-1,-1}/math.sqrt(f32(2))
		feel_emit(
			run,.Nova,player.pos,ARCHETYPE_SKILL_COLORS[.Arcanist],.48,3.8,
			direction=player.facing,style=.Arcanist,priority=.High,
		)
		// Half-life makes the projected ring cross both adjacent walls, turning
		// this into a real per-fragment FOW test instead of an origin-only check.
		run.feel[len(run.feel)-1].remaining=.24
	case .None:
	}

	player.prev_pos=player.pos
	player.moving=false
	run.arrival_timer=0
	refresh_visibility(run)
	view_center_on(view,world_from_tile(player.pos))
}

MX7_Capture_Scenario :: enum u8 {
	None,
	Baseline,
	Door,
	Stairs,
	Shop,
	Bar,
	Garden,
	Boss,
	Crowd,
	Loot,
	Trap,
	Shrine,
	Secret,
	Fow,
	Victory_Panel,
	Dead_Panel,
}

mx7_capture_scenario_from_env :: proc(value: string) -> MX7_Capture_Scenario {
	switch value {
	case "baseline": return .Baseline
	case "door": return .Door
	case "stairs": return .Stairs
	case "shop": return .Shop
	case "bar": return .Bar
	case "garden": return .Garden
	case "boss": return .Boss
	case "crowd": return .Crowd
	case "loot": return .Loot
	case "trap": return .Trap
	case "shrine": return .Shrine
	case "secret": return .Secret
	case "fow": return .Fow
	case "victory_panel": return .Victory_Panel
	case "dead_panel": return .Dead_Panel
	}
	return .None
}

@(private = "file")
mx7_capture_room :: proc(run: ^Run, scenario: MX7_Capture_Scenario) -> (room: Room, room_index: int) {
	if run == nil || run.dungeon.room_count == 0 do return {},-1
	kind := Special_Room_Kind.None
	#partial switch scenario {
	case .Shop: kind = .Shop
	case .Bar: kind = .Bar
	case .Garden: kind = .Garden
	case:
	}
	if kind != .None {
		if special,found := special_room_for_kind(&run.dungeon,kind); found && 0 <= special.room_index && special.room_index < run.dungeon.room_count {
			return run.dungeon.rooms_buf[special.room_index],special.room_index
		}
	}
	if scenario == .Boss || scenario == .Stairs {
		room_index = run.dungeon.room_count-1
	} else {
		room_index = min(1,run.dungeon.room_count-1)
	}
	return run.dungeon.rooms_buf[room_index],room_index
}

@(private = "file")
mx7_force_special_room :: proc(run: ^Run, kind: Special_Room_Kind, room_index: int) -> bool {
	if run == nil || room_index < 0 || room_index >= run.dungeon.room_count do return false
	room := run.dungeon.rooms_buf[room_index]
	center := room_center(room)
	// Capture-only authored chamber: close the full perimeter around the existing
	// interior and leave one west-facing doorway. This cannot affect real floors.
	for x in room.x..<room.x+room.w {
		run.dungeon.tiles[x][room.y] = .Wall
		run.dungeon.tiles[x][room.y+room.h-1] = .Wall
	}
	for y in room.y..<room.y+room.h {
		run.dungeon.tiles[room.x][y] = .Wall
		run.dungeon.tiles[room.x+room.w-1][y] = .Wall
	}
	run.dungeon.tiles[room.x][center.y] = .Closed_Door
	run.dungeon.special_rooms_buf = {}
	run.dungeon.special_rooms_buf[0] = {kind,room_index}
	run.dungeon.special_room_count = 1
	run.dungeon.bar_furnishings = {}
	run.dungeon.shop_gold = {}
	plan_bar_furnishings(&run.dungeon)
	plan_shop_gold(&run.dungeon)
	run.has_shopkeeper = false
	run.shopkeeper = {}
	if kind == .Shop {
		run.shopkeeper = shopkeeper_make(run.seed,run.depth,room,room_index)
		run.has_shopkeeper = true
	}
	room_npc_initialize_ambient_residents(run)
	return true
}

@(private = "file")
mx7_clear_dynamic_world :: proc(run: ^Run) {
	if run == nil do return
	clear(&run.enemies)
	clear(&run.projectiles)
	clear(&run.familiars)
	clear(&run.bells)
	clear(&run.numbers)
	clear(&run.ground_items)
	clear(&run.traps)
	clear(&run.shrines)
	clear(&run.secrets)
	clear_feel_events(run)
	clear(&run.sfx)
	run.dungeon.solid_props = {}
	run.next_enemy_id = 0
	run.next_familiar_id = 0
	run.boss_engaged = false
}

@(private = "file")
mx7_stage_crowd :: proc(run: ^Run, center: Vec2) -> int {
	if run == nil do return 0
	clear(&run.enemies)
	kinds := [8]Enemy_Kind{.Ghoul,.Grave_Archer,.Cultist,.Gate_Warden,.Crypt_Brute,.Plague_Toad,.Ash_Hound,.Bone_Imp}
	offsets := [12]Vec2{{-2,-1},{-1,-2},{0,-2},{1,-2},{2,-1},{2,0},{2,1},{1,2},{0,2},{-1,2},{-2,1},{-2,0}}
	for offset,i in offsets {
		pos := center+offset
		if blocked_for_radius(&run.dungeon,pos.x,pos.y,ACTOR_MOVE_COLLISION_RADIUS,block_stairs=true) do continue
		enemy := enemy_make(kinds[i%len(kinds)],pos,run.depth)
		enemy.prev_pos = pos
		enemy.cooldown = 100
		enemy_ensure_id(run,&enemy)
		append(&run.enemies,enemy)
	}
	loot_rng := rng_make(derive_seed(run.seed,0x50455246),stream=11)
	for offset in ([4]Vec2{{-.6,-.6},{.6,-.6},{-.6,.6},{.6,.6}}) do append(&run.ground_items,make_loot(&loot_rng,center+offset,run=run))
	return len(run.enemies)
}

@(private = "file")
mx7_stage_dressing :: proc(run: ^Run, scenario: MX7_Capture_Scenario, center: Vec2) {
	if run == nil do return
	#partial switch scenario {
	case .Loot:
		clear(&run.ground_items)
		loot_rng := rng_make(derive_seed(run.seed,0x4D5837),stream=11)
		for offset in ([5]Vec2{{-.8,0},{.8,0},{0,-.8},{0,.8},{.7,.7}}) {
			append(&run.ground_items,make_loot(&loot_rng,center+offset,run=run))
		}
	case .Trap:
		clear(&run.traps)
		offsets := [3]Vec2{{-.8,.25},{.8,.25},{0,-.85}}
		for kind in Trap_Kind {
			append(&run.traps,Trap{pos=center+offsets[int(kind)],kind=kind,damage=18,active=true,revealed=true,reveal_progress=1})
		}
	case .Shrine:
		clear(&run.shrines)
		append(&run.shrines,Shrine{pos=center+{.8,0},kind=.Twilight})
	case .Secret:
		clear(&run.secrets)
		append(&run.secrets,Secret{pos=center+{.8,0},kind=.Hidden_Cache,revealed=true})
	case .Crowd:
		_ = mx7_stage_crowd(run,center)
	case:
	}
}

mx7_stage_capture :: proc(app: ^App, view: ^View, scenario: MX7_Capture_Scenario, theme_index: int, dark_override: int, open_door := false) -> bool {
	if app == nil || view == nil || app.mode != .Playing || scenario == .None do return false
	if scenario == .Victory_Panel || scenario == .Dead_Panel {
		mx7_stage_end_panel(app, scenario == .Victory_Panel)
		return true
	}
	run := &app.run
	if 0 <= theme_index && theme_index < len(THEMES) do run.theme_index = theme_index
	if dark_override >= 0 do run.dark_floor = dark_override != 0
	run.arrival_timer = 0
	app.inventory_open,app.character_open,app.shop_open = false,false,false
	app.story_minigame = {}
	app_story_close_panel(app)
	room,room_index := mx7_capture_room(run,scenario)
	if room_index < 0 do return false
	mx7_clear_dynamic_world(run)
	if scenario == .Shop && !mx7_force_special_room(run,.Shop,room_index) do return false
	if scenario == .Bar && !mx7_force_special_room(run,.Bar,room_index) do return false
	if scenario == .Garden && !mx7_force_special_room(run,.Garden,room_index) do return false
	center_tile := room_center(room)
	center := Vec2{f32(center_tile.x)+.5,f32(center_tile.y)+.5}
	player_pos := center+Vec2{-1.2,.8}
	if scenario == .Stairs {
		s := run.dungeon.stairs
		center = {f32(s.x)+.5,f32(s.y)+.5}
		player_pos = center+{-2,0}
	} else if scenario == .Fow {
		player_pos = {f32(room.x)+1.2,f32(room.y)+1.2}
		center = player_pos
	} else if scenario == .Door {
		found_door := false
		for x in 0..<MAP_W {
			for y in 0..<MAP_H {
				kind := run.dungeon.tiles[x][y]
				if kind != .Closed_Door && kind != .Open_Door do continue
				if open_door do run.dungeon.tiles[x][y] = .Open_Door
				else do run.dungeon.tiles[x][y] = .Closed_Door
				center = {f32(x)+.5,f32(y)+.5}
				spots := [4]Vec2{{f32(x)+1.5,f32(y)+.5},{f32(x)-.5,f32(y)+.5},{f32(x)+.5,f32(y)+1.5},{f32(x)+.5,f32(y)-.5}}
				for spot in spots {
					if !blocked_for_radius(&run.dungeon,spot.x,spot.y,ACTOR_MOVE_COLLISION_RADIUS,block_stairs=true) {
						player_pos=spot
						found_door=true
						break
					}
				}
				if !found_door do continue
				break
			}
			if found_door do break
		}
		if !found_door do return false
	}
	if blocked_for_radius(&run.dungeon,player_pos.x,player_pos.y,ACTOR_MOVE_COLLISION_RADIUS,block_stairs=true) {
		player_pos = center
	}
	run.player.pos = player_pos
	run.player.prev_pos = player_pos
	run.player.facing = {1,0}
	run.player.moving = false
	if scenario == .Boss do mx6_capture_boss(run,center,{-1,0},.Shadow_Volley)
	mx7_stage_dressing(run,scenario,center)
	if scenario == .Fow {
		feel_emit(run,.Nova,player_pos,ARCHETYPE_SKILL_COLORS[.Arcanist],.48,3.8,direction={-1,-1},style=.Arcanist,priority=.High)
		run.feel[len(run.feel)-1].remaining = .24
	}
	refresh_visibility(run)
	// Baselines model a previously visited stairs tile so normal and dark cards
	// both exercise the persistent off-viewport guidance arrow.
	if scenario == .Baseline {
		s := run.dungeon.stairs
		if dungeon_in_bounds(s.x,s.y) do run.explored[s.x][s.y] = true
	}
	view_center_on(view,world_from_tile(center))
	return true
}

mx7_stage_perf :: proc(app: ^App, view: ^View, theme_index: int, dark_override: int) -> bool {
	if app == nil || view == nil || app.mode != .Playing do return false
	run := &app.run
	if 0 <= theme_index && theme_index < len(THEMES) do run.theme_index = theme_index
	if dark_override >= 0 do run.dark_floor = dark_override != 0
	mx7_clear_dynamic_world(run)
	// Dedicated synthetic 16×16 arena guarantees the visible workload rather
	// than inheriting generated special rooms, doors, or furnishings.
	run.dungeon.special_rooms_buf = {}
	run.dungeon.special_room_count = 0
	run.dungeon.bar_furnishings = {}
	run.dungeon.shop_gold = {}
	run.has_shopkeeper = false
	run.shopkeeper = {}
	run.ambient_residents = {}
	for x in 0..<MAP_W do for y in 0..<MAP_H do run.dungeon.tiles[x][y]=.Wall
	arena := Room{24,24,16,16}
	run.dungeon.room_count=1
	run.dungeon.rooms_buf[0]=arena
	for x in arena.x+1..<arena.x+arena.w-1 do for y in arena.y+1..<arena.y+arena.h-1 do run.dungeon.tiles[x][y]=.Floor
	run.dungeon.stairs={arena.x+arena.w-2,arena.y+arena.h-2}
	run.dungeon.tiles[run.dungeon.stairs.x][run.dungeon.stairs.y]=.Stairs
	center_tile := room_center(arena)
	center := Vec2{f32(center_tile.x)+.5,f32(center_tile.y)+.5}
	run.player.pos = center
	run.player.prev_pos = center
	run.player.facing = {1,0}
	run.player.moving = false
	run.player.hp = run.player.max_hp
	run.arrival_timer = 0
	if mx7_stage_crowd(run,center) != 12 do return false
	// Fixed persistent visual load is refreshed after each simulation pass.
	mx7_perf_refresh_visuals(run)
	append(&run.shrines,Shrine{pos=center+{2.3,0},kind=.Twilight})
	append(&run.traps,Trap{pos=center+{-2.3,0},kind=.Rune,damage=18,active=true,revealed=true,reveal_progress=1})
	refresh_visibility(run)
	view_center_on(view,world_from_tile(center))
	return true
}

mx7_perf_refresh_visuals :: proc(run: ^Run) {
	if run == nil do return
	center := run.player.pos
	clear(&run.projectiles)
	clear(&run.numbers)
	clear_feel_events(run)
	for i in 0..<24 {
		angle := f32(i)*math.TAU/24
		direction := Vec2{math.cos(angle),math.sin(angle)}
		pos := center+direction*(1+f32(i%3)*.45)
		append(&run.projectiles,Projectile{pos=pos,prev_pos=pos,vel=direction,visual=Projectile_Visual(i%len(Projectile_Visual)),visual_age=f32(i)*.07,damage=1,ttl=100,color=DAMAGE_TYPE_COLORS[Damage_Type(i%len(Damage_Type))]})
		feel_emit(run,Feel_Kind(i%(len(Feel_Kind)-1)),pos,DAMAGE_TYPE_COLORS[Damage_Type(i%len(Damage_Type))],100,.55,direction={1,0})
		append(&run.numbers,Damage_Number{pos=pos,value=10+i,kind=.Damage_Dealt,damage_type=Damage_Type(i%len(Damage_Type))})
	}
}

mx_story_stage_capture :: proc(app: ^App, scenario: MX_Story_Capture_Scenario) -> bool {
	if app == nil || app.mode != .Playing || scenario == .None do return false
	app.inventory_open,app.character_open,app.shop_open = false,false,false
	app.story_minigame = {}
	app_story_close_panel(app)

	switch scenario {
	case .Omen_Initial:
		beat := story_current_beat(&app.run)
		if beat == nil do return false
		app.run.story.relic = .Asterion_Nail
		if !app_story_open_omen(app) do return false
		app.story_panel.node_elapsed = 0
	case .Relic_Choices:
		beat := story_current_beat(&app.run)
		if beat == nil do return false
		app.run.story.relic = .Crown_Of_Antlers_And_Teeth
		if !app_story_open_omen(app) do return false
		app_story_panel_reveal(app)
		app.story_panel.choice_cursor = 1
	case .Guest:
		guest_index := -1
		for guest, index in app.run.story_runtime.guests {
			if guest.role == .Antlered_Hunter && guest.variant == 2 {
				guest_index = index
				break
			}
		}
		if guest_index < 0 do return false
		guest := &app.run.story_runtime.guests[guest_index]
		guest.witness = false
		guest.resolved = false
		if !app_story_open_guest_dialogue(app,guest_index) do return false
		app_story_panel_reveal(app)
		app.story_panel.choice_cursor = 2
	case .Soul:
		app.run.depth = 7
		room_index := min(1,app.run.dungeon.room_count-1)
		if room_index < 0 do return false
		app.run.dungeon.special_room_count = 1
		app.run.dungeon.special_rooms_buf[0] = {.Hall_Of_Unlost_Echoes,room_index}
		app.run.story_runtime.soul = {}
		app.run.story_runtime.hall = {}
		index := app.run.depth-1
		app.run.story_runtime.hall_ledgers[index] = {}
		app.run.story_runtime.soul_games[index] = {valid=true,room_index=room_index,outcome=.Won}
		story_populate_floor(&app.run)
		if !app.run.story_runtime.soul.present || !app_story_open_lossless_soul(app) do return false
		app_story_panel_reveal(app)
		app.story_panel.choice_cursor = 1
	case .Mistbound:
		app.run.depth = 7
		room_index := min(1,app.run.dungeon.room_count-1)
		if room_index < 0 do return false
		app.run.dungeon.special_room_count = 1
		app.run.dungeon.special_rooms_buf[0] = {.Hall_Of_Unlost_Echoes,room_index}
		app.run.story_runtime.soul = {}
		app.run.story_runtime.hall = {}
		index := app.run.depth-1
		app.run.story_runtime.hall_ledgers[index] = {}
		app.run.story_runtime.soul_games[index] = {}
		story_populate_floor(&app.run)
		if !app.run.story_runtime.soul.present||
			!story_resolve_lossless_soul(&app.run,.Release)||
			!app_story_start_mirror_the_unlost(app,room_index) {
			return false
		}
		// Capture staging bypasses the live audio-boundary wait so the requested
		// frame can deterministically show the active chase.
		app.story_soul_hunt_music_ready=true
		for _ in 0..<8 {
			if app.story_minigame.phase==.Play do break
			_=story_soul_hunt_tick(app,{},.25)
		}
		if app.story_minigame.phase!=.Play||app.story_minigame.active_cell<0 do return false
		// Let the first apparition finish condensing so the visual fixture shows
		// the authored target rather than only its opening bank of mist.
		_=story_soul_hunt_tick(app,{},.18)
		app.options.mist_enabled=true
	case .Ending:
		app.run.story.flags.gate = .Unresolved
		if !story_record_gate_choice(&app.run.story,.Aid) do return false
		app.run.story_runtime.epilogue_stage = .Ending
		if !app_story_open_epilogue(app) do return false
		app_story_panel_reveal(app)
	case .None:
		return false
	}
	if scenario==.Mistbound do return app_story_soul_hunt_active(app)&&!app.story_panel.active
	return app.story_panel.active && !app.story_minigame.active
}

mx_save_stage_capture :: proc(app:^App,scenario:MX_Save_Capture_Scenario)->bool {
	if app==nil||scenario==.None do return false
	profile_destroy(&app.profile)
	profile_init(&app.profile,"mx-save-capture")
	app.chronicle={archetype_filter=-1,difficulty_filter=-1,focus=.Timeline}
	app.active_run_damaged=false;app.active_run_available=false;app.confirm_index=0
	if scenario==.Recovery {app.active_run_damaged=true;app.mode=.Recovery;return true}
	if scenario==.Abandon {app.active_run_available=true;app.mode=.Abandon_Confirm;return true}
	if scenario!=.Empty {
		for i in 0..<14 {
			victory:=i%3==0
			run_id:=fmt.aprintf("capture-run-%02d",i)
			record:=Chronicle_Record{
				record_schema_version=CHRONICLE_RECORD_SCHEMA_VERSION,
				run_id=run_id,outcome=victory?.Victory:.Fallen,
				archetype=Archetype_Id(i%len(Archetype_Id)),difficulty=Difficulty_Id(i%len(Difficulty_Id)),
				seed=u64(0xA700+i),deepest_floor=1+i%DUNGEON_DEPTH,
				started_at_utc="2026-08-17T18:00:00Z",ended_at_utc="2026-08-17T18:42:00Z",
				active_ticks=u64((12+i*4)*SIM_HZ*60),final_level=2+i%9,kills=8+i*7,
				traps_triggered=i%5,shrines_used=1+i%4,secrets_opened=i%3,
				bars_visited=3,bars_toasted=i%4,challenge_rooms_cleared=i%2,
				run_modifier=Run_Modifier_Id(i%len(Run_Modifier_Id)),
				cause_of_death=victory?"":"void_sentinel",
				story_relic_id="Asterion_Nail",story_ending_id=victory?"the_held_door":"",
			}
			record.visited_theme_ids[0]="crypt_of_ash";record.visited_theme_count=1
			record.defeated_boss_ids[0]="ash_gallows";record.defeated_boss_count=1
			record.notable_items[0]={item_id="asterion_nail",display_name="Asterion Nail",rarity=.Unique};record.notable_count=1
			_=profile_finalize_record(&app.profile,&record)
			delete(run_id)
		}
	}
	app.chronicle.outcome=.All
	if scenario==.Victories do app.chronicle.outcome=.Victories
	if scenario==.Fallen do app.chronicle.outcome=.Fallen
	app.mode=.Chronicle
	return true
}

// Worst-case end-of-run panel staging: the longest modifier name, saturated
// counters, and three long notable finds stress the fitted summary/ledger
// lines so overflow regressions are visible in one capture.
@(private = "file")
mx7_stage_end_panel :: proc(app: ^App, victory: bool) {
	run := &app.run
	player := &run.player
	run.depth = 10
	player.level = 19
	run.kills = 9999
	player.gold = 999999
	longest := Run_Modifier_Id(0)
	for id in Run_Modifier_Id {
		if len(RUN_MODIFIERS[id].name) > len(RUN_MODIFIERS[longest].name) do longest = id
	}
	run.modifier = longest
	run.shrines_used = 12
	run.secrets_opened = 19
	run.traps_triggered = 24
	run.challenge_rooms_cleared = 9
	run.bars_toasted = 19
	run.bars_visited = 19
	run.notable_count = 3
	run.notable_loot[0] = {rarity = .Legendary, item_id = "", name = "Voidforged Runeweave Mantle of the Patient Grave"}
	run.notable_loot[1] = {rarity = .Unique, item_id = "", name = "Asterion Nail of the Tenth Unrung Bell"}
	run.notable_loot[2] = {rarity = .Cursed, item_id = "", name = "Oathless Knight's Bargain-Sealed Crown"}
	app.mode = victory ? .Victory : .Dead
}

mx7_perf_percentile :: proc(samples: []f32, fraction: f32) -> f32 {
	if len(samples) == 0 do return 0
	index := clamp(int(math.ceil(fraction*f32(len(samples))))-1,0,len(samples)-1)
	return samples[index]
}

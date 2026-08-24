package archrogue

// MX-story run-time integration. The deterministic corpus/choice engine lives
// in story.odin; this file owns per-run world state, modal state machines, the
// three story minigames, and friendly NPC behavior. It is intentionally
// raylib-free so every story path remains headless-testable.

import "core:fmt"
import "core:math"

STORY_PANEL_TEXT_CAP :: 4096
STORY_MINIGAME_MAX_CELLS :: 12
STORY_MINIGAME_MAX_SEQUENCE :: 6
STORY_NPC_SPEED :: f32(0.76)
STORY_NPC_RADIUS :: ROOM_NPC_RADIUS
STORY_NPC_HOLD_RANGE :: ROOM_NPC_INTERACTION_HOLD_RANGE
STORY_NPC_LEASH :: f32(8.0)
STORY_RELIC_INTERACT_RANGE :: f32(1.15)
STORY_GUEST_INTERACT_RANGE :: f32(1.25)
STORY_GARDEN_INTERACT_RANGE :: f32(1.35)
STORY_RESULT_SECONDS :: f32(1.25)
STORY_GARDEN_TARGET_SECONDS :: f32(1.55)
STORY_SOUL_MISMATCH_SECONDS :: f32(0.68)
STORY_NARRATION_SPEED :: f32(2.25)

Story_Relic_Path :: enum u8 {
	Unchosen,
	Aid,
	Bargain,
	Defy,
}

Story_Soul_Verdict :: enum u8 {
	Unresolved,
	Preserve,
	Release,
	Refuse,
}

Story_Epilogue_Stage :: enum u8 {
	Unstarted,
	Gate,
	Ending,
	Bell,
	Completed,
}

Story_Minigame_Kind :: enum u8 {
	None,
	Bind_The_Page,
	Wake_The_Moonbloom,
	Mirror_The_Unlost,
}

Story_Minigame_Phase :: enum u8 {
	Ready,
	Preview,
	Play,
	Result,
}

Story_Minigame_Outcome :: enum u8 {
	None,
	Won,
	Lost,
}

Story_Sigil_Id :: enum u8 {
	Key,
	Clock,
	Sun,
	Moon,
	Sword,
	Shield,
	Star,
	Flame,
	Serpent,
	Ouroboros,
	Phoenix,
	Dragon,
	Cross,
	Infinity,
}

@(rodata)
STORY_SIGIL_NAMES := [Story_Sigil_Id]string{
	.Key = "key", .Clock = "clock", .Sun = "sun", .Moon = "moon",
	.Sword = "sword", .Shield = "shield", .Star = "star", .Flame = "flame",
	.Serpent = "serpent", .Ouroboros = "ouroboros", .Phoenix = "phoenix",
	.Dragon = "dragon", .Cross = "cross", .Infinity = "infinity",
}

Story_Panel_Kind :: enum u8 {
	None,
	Omen,
	Guest,
	Epilogue,
	Soul,
}

Story_Panel_Node :: enum u8 {
	None,
	Relic_Choice,
	Guest_Choice,
	Epilogue_Gate,
	Epilogue_Ending,
	Epilogue_Bell,
	Soul_Reflection,
	Soul_Settled,
}


Story_Guest :: struct {
	entity_id:   u64,
	depth:       int,
	beat_index:  int,
	role:        Story_Guest_Role_Id,
	variant:     int,
	name:        string,
	motive:      string,
	dialogue:    string,
	pos:         Vec2,
	prev_pos:    Vec2,
	motion:      Story_Npc_Motion,
	resolution:  Story_Resolution,
	met:         bool,
	resolved:    bool,
	witness:     bool,
	ally:        bool,
	alive:       bool,
	hp:          int,
	max_hp:      int,
	attack_timer:f32,
}

Lossless_Soul :: struct {
	entity_id:    u64,
	present:      bool,
	met:          bool,
	armed:        bool,
	alive:        bool,
	room_index:   int,
	verdict:      Story_Soul_Verdict,
	pos:          Vec2,
	prev_pos:     Vec2,
	motion:       Story_Npc_Motion,
	hp:           int,
	max_hp:       int,
	attack_timer: f32,
}

Story_Relic_Echo :: struct {
	relic:              Story_Relic_Id,
	depth:              int,
	position:           Vec2,
	present:            bool,
	collected:          bool,
	guidance:           bool,
	guardian:           bool,
	guidance_to_stairs: bool,
}

Story_Relic_Record :: struct {
	committed:          bool,
	path:               Story_Relic_Path,
	position:           Vec2,
	collected:          bool,
	guidance:           bool,
	guardian:           bool,
	guidance_to_stairs: bool,
	choice_order:       [STORY_CHOICE_COUNT]Story_Choice_Verb,
}

Story_Minigame_Ledger :: struct {
	valid:      bool,
	room_index: int,
	outcome:    Story_Minigame_Outcome,
}

Story_Hall_State :: struct {
	seen:       bool,
	met:        bool,
	room_index: int,
	verdict:    Story_Soul_Verdict,
}

Story_Hall_Ledger :: struct {
	valid:      bool,
	met:        bool,
	room_index: int,
	verdict:    Story_Soul_Verdict,
}

Story_Request_Flags :: struct {
	omen:          bool,
	guest:         bool,
	guest_index:   int,
	soul:          bool,
	garden:        bool,
	garden_room:   int,
	collect_relic: bool,
	epilogue:      bool,
}

Story_Run_Runtime :: struct {
	initialized:      bool,
	run_number:       int,
	guests:           [dynamic]Story_Guest,
	soul:             Lossless_Soul,
	relic:            Story_Relic_Echo,
	relic_records:    [STORY_BEAT_COUNT]Story_Relic_Record,
	bind_results:     [STORY_BEAT_COUNT]Story_Minigame_Outcome,
	garden_games:     [STORY_BEAT_COUNT]Story_Minigame_Ledger,
	soul_games:       [STORY_BEAT_COUNT]Story_Minigame_Ledger,
	hall_ledgers:     [STORY_BEAT_COUNT]Story_Hall_Ledger,
	hall:             Story_Hall_State,
	requests:         Story_Request_Flags,
	guidance_path:    [dynamic][2]int,
	epilogue_stage:   Story_Epilogue_Stage,
	guests_met:       int,
	choices_resolved: int,
	blood_paid:       int,
	minigame_counter: int,
}

Story_Panel_State :: struct {
	active:        bool,
	mandatory:     bool,
	kind:          Story_Panel_Kind,
	node:          Story_Panel_Node,
	guest_index:   int,
	choice_cursor: int,
	elapsed:       f32,
	node_elapsed:  f32,
	text:          [STORY_PANEL_TEXT_CAP]u8,
	text_len:      int,
}

Story_Panel_Choice :: struct {
	label:       string,
	detail:      string,
	key:         string,
	verb:        Story_Choice_Verb,
	has_verb:    bool,
	verdict:     Story_Soul_Verdict,
	has_verdict: bool,
}

Story_Panel_Choice_List :: struct {
	items: [STORY_CHOICE_COUNT]Story_Panel_Choice,
	count: int,
}

Story_Art_Identity :: struct {
	panel_kind:    Story_Panel_Kind,
	node:          Story_Panel_Node,
	archetype:     Archetype_Id,
	motif:         Story_Motif_Id,
	has_motif:     bool,
	relic:         Story_Relic_Id,
	has_relic:     bool,
	guest_role:    Story_Guest_Role_Id,
	guest_variant: int,
	has_guest:     bool,
	ending_verb:   Story_Choice_Verb,
	has_ending:    bool,
}

Story_Minigame_State :: struct {
	active:           bool,
	kind:             Story_Minigame_Kind,
	phase:            Story_Minigame_Phase,
	outcome:          Story_Minigame_Outcome,
	instance_id:      int,
	seed:             u64,
	depth:            int,
	room_index:       int,
	continuation:     Story_Choice_Verb,
	has_continuation: bool,
	revision:         int,
	elapsed:          f32,
	time_left:        f32,
	goal:             int,
	score:            int,
	mistakes:         int,
	board:            [STORY_MINIGAME_MAX_CELLS]Story_Sigil_Id,
	board_count:      int,
	sequence:         [STORY_MINIGAME_MAX_SEQUENCE]int,
	sequence_count:   int,
	step:             int,
	active_cell:      int,
	target_time:      f32,
	revealed:         [2]int,
	revealed_count:   int,
	matched:          [STORY_MINIGAME_MAX_CELLS]bool,
	lock_time:        f32,
	result_time:      f32,
	last_cell:        int,
	last_correct:     bool,
	feedback_time:    f32,
}

Story_Ally_Stats :: struct {
	max_hp:       int,
	damage:       int,
	attack_range: f32,
	attack_cd:    f32,
	speed:        f32,
	damage_type:  Damage_Type,
}

STORY_GUEST_ALLY_STATS :: Story_Ally_Stats{30, 7, 1.15, .9, 2.0, .Physical}
STORY_SOUL_ALLY_STATS  :: Story_Ally_Stats{24, 8, 4.2, 1.5, 1.7, .Arcane}

@(private = "file")
story_distance_sq :: proc(a, b: Vec2) -> f32 {
	d := a - b
	return d.x*d.x + d.y*d.y
}

@(private = "file")
story_motion_make :: proc(pos: Vec2, room_index: int, seed: u64, profile := Room_Npc_Profile_Id.Story_Guest) -> Story_Npc_Motion {
	return room_npc_motion_make(pos,room_index,seed,profile)
}

story_run_destroy :: proc(run: ^Run, allocator := context.allocator) {
	if run == nil do return
	delete(run.story_runtime.guests)
	delete(run.story_runtime.guidance_path)
	story_state_destroy(&run.story, allocator)
	run.story_runtime = {}
}

story_run_initialize :: proc(run: ^Run, archetype: Archetype_Id) {
	if run == nil do return
	story_run_destroy(run)
	starting_theme := Story_Motif_Id(clamp(run.plan[0].theme_index,0,len(Story_Motif_Id)-1))
	run.story = story_generate(run.seed, archetype, 1, starting_theme, run.modifier)
	run.story_runtime = {
		initialized=true,
		run_number=1,
		guests=make([dynamic]Story_Guest,0,STORY_BEAT_COUNT*2),
		guidance_path=make([dynamic][2]int,0,MAP_W*MAP_H),
	}
	for i in 0..<STORY_BEAT_COUNT do run.plan[i].theme_index = int(run.story.beats[i].motif)
}

story_current_beat :: proc(run: ^Run) -> ^Story_Beat {
	if run == nil || !run.story_runtime.initialized do return nil
	return story_beat_for_depth(&run.story,run.depth)
}

story_prepare_floor :: proc(run: ^Run) {
	if run == nil || !run.story_runtime.initialized do return
	if beat := story_current_beat(run); beat != nil do run.plan[run.depth-1].theme_index = int(beat.motif)
	run.story_runtime.requests = {}
	run.story_runtime.relic = {}
	clear(&run.story_runtime.guidance_path)
}

story_should_force_hall :: proc(run: ^Run) -> bool {
	return run != nil && run.story_runtime.initialized && run.depth >= 7 && !run.story_runtime.hall.seen
}

@(private = "file")
story_room_position :: proc(d: ^Dungeon, room_index: int) -> Vec2 {
	if d == nil || room_index < 0 || room_index >= d.room_count do return {}
	center := room_center(d.rooms_buf[room_index])
	return {f32(center.x)+.5,f32(center.y)+.5}
}

@(private = "file")
story_guest_index_for_depth :: proc(run: ^Run, depth: int, include_witnesses := false) -> int {
	if run == nil do return -1
	for &guest,i in run.story_runtime.guests {
		if guest.depth == depth && (include_witnesses || !guest.witness) do return i
	}
	return -1
}

story_current_guest :: proc(run: ^Run) -> ^Story_Guest {
	i := story_guest_index_for_depth(run,run.depth)
	if i < 0 do return nil
	return &run.story_runtime.guests[i]
}

@(private = "file")
story_spawn_current_guest :: proc(run: ^Run) {
	beat := story_current_beat(run)
	if beat == nil do return
	special, found := special_room_for_kind(&run.dungeon,.Quest)
	if !found do return
	room_index := special.room_index
	pos := story_room_position(&run.dungeon,room_index)
	index := story_guest_index_for_depth(run,run.depth)
	if index >= 0 {
		guest := &run.story_runtime.guests[index]
		guest.pos,guest.prev_pos = pos,pos
		guest.motion = story_motion_make(pos,room_index,run.story.stream_seed~u64(run.depth)*0x9E3779B1)
		return
	}
	max_hp := 30 + run.depth*3
	guest := Story_Guest{
		depth=run.depth,beat_index=run.depth-1,role=beat.guest_role,variant=beat.guest_variant,
		name=beat.guest_name,motive=beat.guest_motive,dialogue=beat.dialogue,
		pos=pos,prev_pos=pos,motion=story_motion_make(pos,room_index,run.story.stream_seed~u64(run.depth)*0x9E3779B1),
		resolution=beat.resolution,resolved=beat.resolution!=.Unresolved,alive=true,hp=max_hp,max_hp=max_hp,
	}
	append(&run.story_runtime.guests,guest)
}

@(private = "file")
story_spawn_lossless_soul :: proc(run: ^Run) {
	// Soul is floor-local. Clear the prior floor before looking for this floor's
	// Hall, otherwise its old coordinates become valid in unrelated geometry.
	run.story_runtime.soul = {}
	special,found := special_room_for_kind(&run.dungeon,.Hall_Of_Unlost_Echoes)
	if !found do return
	index := clamp(run.depth,1,STORY_BEAT_COUNT)-1
	ledger := &run.story_runtime.hall_ledgers[index]
	ledger.valid=true
	ledger.room_index=special.room_index
	run.story_runtime.hall.seen=true
	run.story_runtime.hall.room_index=special.room_index
	pos := story_room_position(&run.dungeon,special.room_index)
	max_hp := STORY_SOUL_ALLY_STATS.max_hp + run.depth*2
	verdict := ledger.verdict
	run.story_runtime.soul = {
		present=true,met=ledger.met,armed=verdict!=.Unresolved,alive=true,room_index=special.room_index,
		verdict=verdict,pos=pos,prev_pos=pos,motion=story_motion_make(pos,special.room_index,run.story.stream_seed~0x10551055~u64(run.depth),.Lossless_Soul),
		hp=max_hp,max_hp=max_hp,
	}
}

@(private = "file")
story_spawn_gate_witnesses :: proc(run: ^Run) {
	if run == nil || run.depth < DUNGEON_DEPTH do return
	for &guest in run.story_runtime.guests do if guest.witness do return
	room := run.dungeon.rooms_buf[0]
	center := story_room_position(&run.dungeon,0)
	offsets := [9]Vec2{{-1.7,-1.1},{1.7,-1.1},{-2.3,.4},{2.3,.4},{-1.2,1.5},{1.2,1.5},{0,-2},{0,2.1},{-2.6,-.6}}
	count := 0
	for depth in 1..<DUNGEON_DEPTH {
		beat := &run.story.beats[depth-1]
		if beat.resolution != .Aid || count >= len(offsets) do continue
		pos := center + offsets[count]
		pos.x=clamp(pos.x,f32(room.x)+1.3,f32(room.x+room.w)-1.3)
		pos.y=clamp(pos.y,f32(room.y)+1.3,f32(room.y+room.h)-1.3)
		max_hp := 1
		append(&run.story_runtime.guests,Story_Guest{
			depth=run.depth,beat_index=depth-1,role=beat.guest_role,variant=beat.guest_variant,name=beat.guest_name,
			motive=beat.guest_motive,dialogue=beat.dialogue,pos=pos,prev_pos=pos,
			motion=story_motion_make(pos,0,run.story.stream_seed~u64(depth)*0x51A70A11),resolution=.Aid,
			met=true,resolved=true,witness=true,alive=true,hp=max_hp,max_hp=max_hp,
		})
		count += 1
	}
}

@(private = "file")
story_position_available :: proc(run: ^Run, pos: Vec2, ignore_friendly := false) -> bool {
	if run == nil || blocked_for_radius(&run.dungeon,pos.x,pos.y,STORY_NPC_RADIUS) do return false
	if story_distance_sq(pos,run.player.pos) < .52 do return false
	if !ignore_friendly {
		for &guest in run.story_runtime.guests do if guest.depth==run.depth&&guest.alive&&story_distance_sq(pos,guest.pos)<.46 do return false
		soul:=&run.story_runtime.soul;if soul.present&&soul.alive&&story_distance_sq(pos,soul.pos)<.46 do return false
	}
	return true
}

@(private = "file")
story_near_position :: proc(run: ^Run, origin: Vec2, distance := f32(1.0)) -> Vec2 {
	offsets := [12]Vec2{{1,0},{-1,0},{0,1},{0,-1},{1,1},{-1,1},{1,-1},{-1,-1},{2,0},{-2,0},{0,2},{0,-2}}
	for off in offsets {
		candidate := origin + off*distance
		if story_position_available(run,candidate) do return candidate
	}
	return origin
}

story_populate_floor :: proc(run: ^Run) {
	if run == nil || !run.story_runtime.initialized || run.depth<1 || run.depth>STORY_BEAT_COUNT do return
	story_spawn_current_guest(run)
	story_spawn_lossless_soul(run)
	story_spawn_gate_witnesses(run)
	index := run.depth-1
	record := &run.story_runtime.relic_records[index]
	if !record.committed {
		record.choice_order = story_relic_choice_order(run,run.depth)
		run.story_runtime.requests.omen=true
	} else if !record.collected {
		run.story_runtime.relic={relic=run.story.relic,depth=run.depth,position=record.position,present=true,guidance=record.guidance,guardian=record.guardian,guidance_to_stairs=record.guidance_to_stairs}
		if record.guardian do story_spawn_relic_guardian(run,record.position)
	} else {
		run.story_runtime.relic={relic=run.story.relic,depth=run.depth,position=record.position,collected=true,guidance=record.guidance,guardian=record.guardian,guidance_to_stairs=record.guidance_to_stairs}
	}
}

story_relic_path_from_verb :: proc(verb: Story_Choice_Verb) -> Story_Relic_Path {
	switch verb {case .Aid:return .Aid;case .Bargain:return .Bargain;case .Defy:return .Defy}
	return .Unchosen
}

story_relic_choice_order :: proc(run: ^Run, depth: int) -> [STORY_CHOICE_COUNT]Story_Choice_Verb {
	order := [STORY_CHOICE_COUNT]Story_Choice_Verb{.Aid,.Bargain,.Defy}
	if run == nil do return order
	rng := rng_make(run.story.stream_seed~u64(depth)*0xA511E9B3,stream=17)
	for i:=len(order)-1;i>0;i-=1 {j:=rng_below(&rng,i+1);order[i],order[j]=order[j],order[i]}
	canonical := [STORY_CHOICE_COUNT]Story_Choice_Verb{.Aid,.Bargain,.Defy}
	if order == canonical do order=[STORY_CHOICE_COUNT]Story_Choice_Verb{.Bargain,.Defy,.Aid}
	return order
}

story_relic_choice_at :: proc(run: ^Run, row: int) -> (Story_Choice_Verb,bool) {
	if run==nil||run.depth<1||run.depth>STORY_BEAT_COUNT||row<0||row>=STORY_CHOICE_COUNT do return {},false
	record:=&run.story_runtime.relic_records[run.depth-1]
	return record.choice_order[row],true
}

story_relic_path_traits :: proc(path: Story_Relic_Path) -> (guidance,guardian: bool) {
	switch path {case .Aid:return true,false;case .Bargain:return true,true;case .Defy:return false,true;case .Unchosen:}
	return false,false
}

story_relic_fallback_position :: proc(run: ^Run, path: Story_Relic_Path) -> Vec2 {
	if run==nil do return {}
	if guest:=story_current_guest(run);guest!=nil {
		if candidate:=story_near_position(run,guest.pos);candidate!=guest.pos do return candidate
	}
	rooms:=dungeon_rooms(&run.dungeon)
	if len(rooms)==0 do return run.player.pos
	room_index:=len(rooms)-1
	if path==.Aid do room_index=clamp(1,0,len(rooms)-1)
	if path==.Bargain&&len(rooms)>3 do room_index=len(rooms)-2
	return population_room_point(&run.dungeon,rooms[room_index],&run.loot_rng)
}

story_spawn_relic_guardian :: proc(run: ^Run, position: Vec2) {
	if run==nil do return
	for &enemy in run.enemies do if enemy.hp>0&&enemy.name=="Relic Guardian" do return
	pos:=story_near_position(run,position,1.5)
	enemy:=enemy_make(pick_enemy_kind(&run.loot_rng,true),pos,run.depth)
	enemy.name="Relic Guardian"
	apply_story_enemy_stats(run,&enemy)
	apply_enemy_difficulty(&enemy,run.difficulty)
	promote_miniboss(&enemy,run.story.accent)
	enemy.max_hp=max(1,int(f32(enemy.max_hp)*1.45));enemy.hp=enemy.max_hp
	enemy.damage+=3+run.depth/2;enemy.xp+=24+run.depth*2;enemy.aggro_range+=3
	enemy_ensure_id(run,&enemy)
	append(&run.enemies,enemy)
}

story_commit_relic_path :: proc(run: ^Run, verb: Story_Choice_Verb) -> bool {
	if run==nil||!run.story_runtime.initialized||run.depth<1||run.depth>STORY_BEAT_COUNT do return false
	record:=&run.story_runtime.relic_records[run.depth-1]
	if record.committed do return false
	path:=story_relic_path_from_verb(verb);if path==.Unchosen do return false
	position:=story_relic_fallback_position(run,path)
	guidance,guardian:=story_relic_path_traits(path)
	record.committed=true;record.path=path;record.position=position;record.guidance=guidance;record.guardian=guardian;record.guidance_to_stairs=guidance
	run.story_runtime.relic={relic=run.story.relic,depth=run.depth,position=position,present=true,guidance=guidance,guardian=guardian,guidance_to_stairs=guidance}
	if guardian do story_spawn_relic_guardian(run,position)
	if guidance do _=story_build_guidance_path(run,position)
	story_set_guidance_wave_active(run,guidance)
	append(&run.numbers,Damage_Number{pos=run.player.pos,kind=.Text,text=guidance?"The relic answers with a path":"The relic light goes silent"})
	sfx_emit(run, .Story_Consequence)
	return true
}

story_relic_nearby :: proc(run: ^Run) -> bool {
	if run==nil||!run.story_runtime.relic.present||run.story_runtime.relic.collected do return false
	return story_distance_sq(run.player.pos,run.story_runtime.relic.position)<=STORY_RELIC_INTERACT_RANGE*STORY_RELIC_INTERACT_RANGE
}

story_request_relic_collection :: proc(run: ^Run) -> bool {
	if !story_relic_nearby(run) do return false
	run.story_runtime.requests.collect_relic=true
	return true
}

story_collect_relic_echo :: proc(run: ^Run) -> bool {
	if run==nil||!run.story_runtime.relic.present||run.story_runtime.relic.collected do return false
	relic:=&run.story_runtime.relic;relic.present=false;relic.collected=true
	if 1<=relic.depth&&relic.depth<=STORY_BEAT_COUNT do run.story_runtime.relic_records[relic.depth-1].collected=true
	append(&run.numbers,Damage_Number{pos=relic.position,kind=.Text,text="Relic echo recovered"})
	sfx_emit(run, .Relic_Recovered)
	story_refresh_relic_guidance(run)
	return true
}

story_aid_relic_streak_intact :: proc(run: ^Run) -> bool {
	if run==nil||!run.story_runtime.initialized do return false
	seen:=false
	for i in 0..<clamp(run.depth,1,STORY_BEAT_COUNT) {
		record:=run.story_runtime.relic_records[i]
		if !record.committed do continue
		seen=true
		if record.path!=.Aid do return false
	}
	return seen
}

story_relic_guidance_path :: proc(run: ^Run) -> [][2]int {
	if run==nil do return nil
	return run.story_runtime.guidance_path[:]
}

// Pygame records the current elapsed time the first frame guidance becomes
// active, so the crest always departs from the player's feet instead of
// inheriting an arbitrary amount of prior idle time.
story_set_guidance_wave_active :: proc(run: ^Run, active: bool) {
	if run == nil do return
	if active && !run.player.guidance_wave_active do run.player.guidance_idle_elapsed = 0
	if !active do run.player.guidance_idle_elapsed = 0
	run.player.guidance_wave_active = active
}

story_build_guidance_path :: proc(run: ^Run, target: Vec2) -> bool {
	if run==nil do return false
	clear(&run.story_runtime.guidance_path)
	start:=[2]int{int(run.player.pos.x),int(run.player.pos.y)}
	goal:=[2]int{int(target.x),int(target.y)}
	if !dungeon_in_bounds(start.x,start.y)||!dungeon_in_bounds(goal.x,goal.y) do return false
	visited:[MAP_W][MAP_H]bool;prev:[MAP_W][MAP_H][2]int;queue:[MAP_W*MAP_H][2]int
	head,tail:=0,0;queue[tail]=start;tail+=1;visited[start.x][start.y]=true
	dirs:=[4][2]int{{1,0},{-1,0},{0,1},{0,-1}};found:=false
	for head<tail {
		p:=queue[head];head+=1
		if p==goal {found=true;break}
		for dir in dirs {n:=p+dir;if !dungeon_in_bounds(n.x,n.y)||visited[n.x][n.y]||run.dungeon.tiles[n.x][n.y]==.Wall do continue;visited[n.x][n.y]=true;prev[n.x][n.y]=p;queue[tail]=n;tail+=1}
	}
	if !found do return false
	for p:=goal;;p=prev[p.x][p.y] {append(&run.story_runtime.guidance_path,p);if p==start do break}
	for i,j:=0,len(run.story_runtime.guidance_path)-1;i<j;i,j=i+1,j-1 do run.story_runtime.guidance_path[i],run.story_runtime.guidance_path[j]=run.story_runtime.guidance_path[j],run.story_runtime.guidance_path[i]
	return true
}

story_refresh_relic_guidance :: proc(run: ^Run) {
	if run==nil do return
	target,enabled:=story_route_target(run)
	story_set_guidance_wave_active(run,enabled)
	if !enabled {clear(&run.story_runtime.guidance_path);return}
	_=story_build_guidance_path(run,target)
}

story_nearby_guest :: proc(run: ^Run) -> ^Story_Guest {
	if run==nil do return nil
	best:=-1;best_sq:=STORY_GUEST_INTERACT_RANGE*STORY_GUEST_INTERACT_RANGE
	for &guest,i in run.story_runtime.guests {
		if guest.depth!=run.depth||guest.resolved||guest.witness||!guest.alive do continue
		d:=story_distance_sq(guest.pos,run.player.pos)
		if d<=best_sq&&line_of_sight(&run.dungeon,run.player.pos.x,run.player.pos.y,guest.pos.x,guest.pos.y) {best=i;best_sq=d}
	}
	return best>=0?&run.story_runtime.guests[best]:nil
}

story_mark_guest_met :: proc(run: ^Run, guest: ^Story_Guest) -> bool {
	if run==nil||guest==nil||guest.met do return false
	guest.met=true;run.story_runtime.guests_met+=1;return true
}

@(private = "file")
story_reveal_mercy_secrets :: proc(run: ^Run, origin: Vec2) -> int {
	revealed:=0
	for revealed<2 {
		best:=-1;best_sq:=f32(49)
		for &secret,i in run.secrets {if secret.opened||secret.revealed do continue;d:=story_distance_sq(secret.pos,origin);if d<=best_sq {best=i;best_sq=d}}
		if best<0 do break
		run.secrets[best].revealed=true;revealed+=1
	}
	return revealed
}

@(private = "file")
story_spawn_mercy_cache :: proc(run: ^Run, origin: Vec2) {
	pos:=story_near_position(run,origin)
	append(&run.secrets,Secret{pos=pos,kind=.Hidden_Cache,revealed=true})
}

@(private = "file")
story_spawn_mending_shrine :: proc(run: ^Run, origin: Vec2) {
	pos:=story_near_position(run,origin)
	tile:=[2]int{int(pos.x),int(pos.y)}
	if solid_prop_add(&run.dungeon,tile) do append(&run.shrines,Shrine{pos=pos,kind=.Mending})
}

@(private = "file")
story_spawn_choice_hunter :: proc(run: ^Run, origin: Vec2) {
	pos:=story_near_position(run,origin,1.4)
	enemy:=enemy_make(pick_enemy_kind(&run.loot_rng,true),pos,run.depth);enemy.name="Story-Marked Hunter"
	apply_story_enemy_stats(run,&enemy);apply_enemy_difficulty(&enemy,run.difficulty);enemy_ensure_id(run,&enemy);append(&run.enemies,enemy)
}

story_resolve_guest_choice :: proc(run: ^Run, guest: ^Story_Guest, verb: Story_Choice_Verb) -> bool {
	if run==nil||guest==nil||guest.resolved||guest.witness do return false
	_=story_mark_guest_met(run,guest)
	if !story_record_choice(&run.story,guest.depth,verb) do return false
	guest.resolved=true;guest.resolution=story_resolution_from_verb(verb);guest.ally=true;guest.max_hp=STORY_GUEST_ALLY_STATS.max_hp+run.depth*3;guest.hp=guest.max_hp
	room_npc_motion_wait(&guest.motion,guest.pos)
	run.story_runtime.choices_resolved+=1
	switch verb {
	case .Aid:
		run.player.hp=min(run.player.max_hp,run.player.hp+max(16,run.player.max_hp/5))
		run.player.mana=min(f32(run.player.max_mana),run.player.mana+f32(max(10,run.player.max_mana/4)))
		run.player.stamina=f32(run.player.max_stamina)
		if story_reveal_mercy_secrets(run,guest.pos)==0 do story_spawn_mercy_cache(run,guest.pos)
		story_spawn_mending_shrine(run,guest.pos)
	case .Bargain:
		price:=story_effect_clamped(run,.Blood_Price,0,.35)
		cost:=max(6,min(22,int(math.round(f32(run.player.max_hp)*(.08+price*.45)))))
		run.player.hp=max(1,run.player.hp-cost)
		slot:=rng_chance(&run.loot_rng,.5)?Item_Kind.Weapon:.Armor
		item:=make_equipment(&run.loot_rng,slot,.Rare,run=run);_=story_empower_equipment(run,&run.loot_rng,&item,true)
		append(&run.ground_items,Ground_Item{item=item,pos=story_near_position(run,guest.pos)})
	case .Defy:
		player_gain_xp(run,24+run.depth*3);story_spawn_choice_hunter(run,guest.pos)
	}
	append(&run.numbers,Damage_Number{pos=guest.pos,kind=.Text,text="Story changed"});sfx_emit(run, .Story_Consequence)
	return true
}

story_resolve_current_unanswered :: proc(run: ^Run) -> bool {
	if run==nil||!run.story_runtime.initialized do return false
	beat:=story_current_beat(run);if beat==nil||beat.resolution!=.Unresolved do return false
	if !story_record_unanswered(&run.story,run.depth) do return false
	if guest:=story_current_guest(run);guest!=nil {guest.resolved=true;guest.resolution=.Unanswered;guest.ally=false}
	return true
}

story_nearby_lossless_soul :: proc(run: ^Run) -> ^Lossless_Soul {
	if run==nil do return nil
	soul:=&run.story_runtime.soul
	if !soul.present||!soul.alive||story_distance_sq(soul.pos,run.player.pos)>STORY_GUEST_INTERACT_RANGE*STORY_GUEST_INTERACT_RANGE do return nil
	if !line_of_sight(&run.dungeon,run.player.pos.x,run.player.pos.y,soul.pos.x,soul.pos.y) do return nil
	return soul
}

story_nearby_garden_frog :: proc(run: ^Run) -> (tile: [2]int,room_index: int,found: bool) {
	if run==nil do return {},-1,false
	garden_room := -1
	if special,has:=special_room_for_kind(&run.dungeon,.Garden);has do garden_room=special.room_index
	for i in 0..<run.ambient_residents.count {
		frog:=&run.ambient_residents.items[i]
		if !frog.active||frog.kind!=.Garden_Frog do continue
		garden_room=frog.motion.room_index
		if story_distance_sq(frog.pos,run.player.pos)<=STORY_GARDEN_INTERACT_RANGE*STORY_GARDEN_INTERACT_RANGE&&
			line_of_sight(&run.dungeon,run.player.pos.x,run.player.pos.y,frog.pos.x,frog.pos.y) {
			return {int(frog.pos.x),int(frog.pos.y)},garden_room,true
		}
	}
	return {},garden_room,false
}

story_request_guest_dialogue :: proc(run: ^Run) -> bool {
	guest:=story_nearby_guest(run);if guest==nil do return false
	room_npc_motion_hold(&guest.motion,guest.pos,run.player.pos)
	_=story_mark_guest_met(run,guest)
	for &candidate,i in run.story_runtime.guests do if &candidate==guest {run.story_runtime.requests.guest=true;run.story_runtime.requests.guest_index=i;return true}
	return false
}

story_request_lossless_soul :: proc(run: ^Run) -> bool {
	soul:=story_nearby_lossless_soul(run);if soul==nil do return false
	room_npc_motion_hold(&soul.motion,soul.pos,run.player.pos)
	run.story_runtime.requests.soul=true;return true
}

story_request_garden_moonbloom :: proc(run: ^Run) -> bool {
	_,room,found:=story_nearby_garden_frog(run);if !found do return false
	index:=clamp(run.depth,1,STORY_BEAT_COUNT)-1
	if run.story_runtime.garden_games[index].outcome!=.None do return false
	for i in 0..<run.ambient_residents.count {
		frog:=&run.ambient_residents.items[i]
		if !frog.active||frog.kind!=.Garden_Frog||frog.motion.room_index!=room do continue
		if story_distance_sq(frog.pos,run.player.pos)<=STORY_GARDEN_INTERACT_RANGE*STORY_GARDEN_INTERACT_RANGE&&
			line_of_sight(&run.dungeon,run.player.pos.x,run.player.pos.y,frog.pos.x,frog.pos.y) {
			room_npc_motion_hold(&frog.motion,frog.pos,run.player.pos)
			break
		}
	}
	run.story_runtime.requests.garden=true;run.story_runtime.requests.garden_room=room;return true
}

story_resolve_lossless_soul :: proc(run: ^Run, verdict: Story_Soul_Verdict) -> bool {
	if run==nil||verdict==.Unresolved||!run.story_runtime.soul.present do return false
	index:=clamp(run.depth,1,STORY_BEAT_COUNT)-1;ledger:=&run.story_runtime.hall_ledgers[index]
	if ledger.verdict!=.Unresolved do return false
	ledger.valid=true;ledger.met=true;ledger.room_index=run.story_runtime.soul.room_index;ledger.verdict=verdict
	run.story_runtime.hall={seen=true,met=true,room_index=ledger.room_index,verdict=verdict}
	soul:=&run.story_runtime.soul;soul.met=true;soul.armed=true;soul.verdict=verdict;soul.max_hp=max(soul.max_hp,STORY_SOUL_ALLY_STATS.max_hp+run.depth*2);soul.hp=max(soul.hp,soul.max_hp)
	room_npc_motion_wait(&soul.motion,soul.pos)
	switch verdict {case .Preserve:effects:Story_Effects;effects[.Healing_Echo]=.05;story_add_effects(&run.story,effects);case .Release:effects:Story_Effects;effects[.Enemy_Pressure]=-.04;story_add_effects(&run.story,effects);case .Refuse,.Unresolved:}
	if (verdict==.Preserve||verdict==.Release)&&run.depth>=7 do _=story_learn_true_name(&run.story,.Liss)
	sfx_emit(run, .Story_Consequence);return true
}

story_request_epilogue :: proc(run: ^Run) -> bool {
	if run==nil||!run.story_runtime.initialized||run.depth<DUNGEON_DEPTH||!run.tyrant_dead||boss_alive(run)||run.story_runtime.epilogue_stage==.Completed do return false
	run.story_runtime.requests.epilogue=true;return true
}

story_final_stairs_requires_story :: proc(run: ^Run) -> bool {
	return run!=nil&&run.story_runtime.initialized&&run.depth>=DUNGEON_DEPTH&&player_near_stairs(run)
}

story_handle_final_stairs_request :: proc(run: ^Run) -> bool {
	if !story_final_stairs_requires_story(run) do return false
	if boss_alive(run) do return false
	if !run.tyrant_dead {append(&run.numbers,Damage_Number{pos=run.player.pos,kind=.Text,text="The Gate waits for the Tyrant's end"});return true}
	_=story_request_epilogue(run);return true
}

story_complete_bell_victory :: proc(run: ^Run) -> bool {
	if run==nil||run.story_runtime.epilogue_stage!=.Bell||run.story.flags.gate==.Unresolved||run.victory do return false
	run.story_runtime.epilogue_stage=.Completed;run.victory=true;sfx_emit(run, .Epilogue_Bell);sfx_emit(run, .Victory);return true
}

story_item_is_relic_touched :: proc(item: ^Item) -> bool {
	return item!=nil&&(item.name=="Relic-Touched Weapon"||item.name=="Relic-Touched Armor")
}

// --- Deterministic minigames ------------------------------------------------

story_minigame_title :: proc(kind: Story_Minigame_Kind) -> string {
	switch kind {case .Bind_The_Page:return "Bind the Page";case .Wake_The_Moonbloom:return "Wake the Moonbloom";case .Mirror_The_Unlost:return "Mirror the Unlost";case .None:}
	return ""
}

story_minigame_instruction :: proc(kind: Story_Minigame_Kind) -> string {
	switch kind {case .Bind_The_Page:return "Remember the lit runes, then repeat them in order.";case .Wake_The_Moonbloom:return "Touch each waking bloom before its light folds shut.";case .Mirror_The_Unlost:return "Turn two seals at a time and reunite every mirrored pair.";case .None:}
	return ""
}

story_minigame_sigil_name :: proc(id: Story_Sigil_Id) -> string {return STORY_SIGIL_NAMES[id]}

@(private = "file")
story_shuffle_sigils :: proc(values: []Story_Sigil_Id, rng: ^Pcg32) {for i:=len(values)-1;i>0;i-=1 {j:=rng_below(rng,i+1);values[i],values[j]=values[j],values[i]}}

@(private = "file")
story_next_garden_cell :: proc(state: ^Story_Minigame_State) -> int {
	salt:=u64(state.score*131+state.mistakes*313+state.revision*17)
	rng:=rng_make(state.seed~0x6A2D4E11~salt,stream=21);candidate:=rng_below(&rng,max(1,state.board_count))
	if state.board_count>1&&candidate==state.active_cell do candidate=(candidate+1+rng_below(&rng,state.board_count-1))%state.board_count
	return candidate
}

story_create_minigame :: proc(run: ^Run,kind: Story_Minigame_Kind,room_index: int,continuation: Story_Choice_Verb,has_continuation: bool) -> Story_Minigame_State {
	if run==nil||kind==.None do return {}
	run.story_runtime.minigame_counter+=1
	seed:=derive_seed(run.story.stream_seed,u64(run.depth)*4099~u64(run.story_runtime.minigame_counter)*257~u64(kind)*0x51A70A11)
	rng:=rng_make(seed,stream=20)
	state:=Story_Minigame_State{active=true,kind=kind,phase=.Ready,instance_id=run.story_runtime.minigame_counter,seed=seed,depth=run.depth,room_index=room_index,continuation=continuation,has_continuation=has_continuation,active_cell=-1,last_cell=-1}
	switch kind {
	case .Bind_The_Page:
		pool:=[6]Story_Sigil_Id{.Key,.Clock,.Sun,.Moon,.Sword,.Shield};story_shuffle_sigils(pool[:],&rng);state.board_count=6;for i in 0..<6 do state.board[i]=pool[i]
		state.sequence_count=min(6,3+max(0,run.depth-1)/3);state.goal=state.sequence_count
		for i in 0..<state.sequence_count {cell:=rng_below(&rng,state.board_count);if i>0&&cell==state.sequence[i-1] do cell=(cell+1+rng_below(&rng,state.board_count-1))%state.board_count;state.sequence[i]=cell}
	case .Wake_The_Moonbloom:
		pool:=[9]Story_Sigil_Id{.Sun,.Moon,.Star,.Flame,.Serpent,.Ouroboros,.Phoenix,.Dragon,.Cross};story_shuffle_sigils(pool[:],&rng);state.board_count=9;for i in 0..<9 do state.board[i]=pool[i]
		state.goal=min(8,6+max(0,run.depth-1)/5);state.active_cell=story_next_garden_cell(&state);state.target_time=STORY_GARDEN_TARGET_SECONDS
	case .Mirror_The_Unlost:
		pool:=[6]Story_Sigil_Id{.Infinity,.Key,.Clock,.Moon,.Phoenix,.Ouroboros};story_shuffle_sigils(pool[:],&rng);pairs:=run.depth<8?3:4;state.goal=pairs;state.board_count=pairs*2
		for i in 0..<pairs {state.board[i]=pool[i];state.board[i+pairs]=pool[i]};story_shuffle_sigils(state.board[:state.board_count],&rng)
	case .None:
	}
	return state
}

story_minigame_confirm_ready :: proc(state: ^Story_Minigame_State) -> bool {
	if state==nil||!state.active||state.phase!=.Ready||state.outcome!=.None do return false
	state.phase=.Preview;state.elapsed=0;state.revision+=1;return true
}

story_minigame_preview_duration :: proc(state: ^Story_Minigame_State) -> f32 {
	if state==nil do return 0
	return state.kind==.Bind_The_Page?.55*f32(state.sequence_count)+.55:.85
}

story_minigame_preview_cell :: proc(state: ^Story_Minigame_State) -> int {
	if state==nil||state.kind!=.Bind_The_Page||state.phase!=.Preview do return -1
	elapsed:=max(f32(0),state.elapsed-.30);index:=int(elapsed/.55);pulse:=math.mod(elapsed,.55)<.38
	if pulse&&0<=index&&index<state.sequence_count do return state.sequence[index]
	return -1
}

@(private = "file")
story_minigame_finish :: proc(state: ^Story_Minigame_State, won: bool) {
	if state==nil||state.outcome!=.None do return
	state.outcome=won?.Won:.Lost;state.phase=.Result;state.result_time=STORY_RESULT_SECONDS;state.active_cell=-1;state.target_time=0;state.lock_time=0;state.revision+=1
}

story_minigame_press :: proc(state: ^Story_Minigame_State, cell, expected_revision: int) -> bool {
	if state==nil||state.phase!=.Play||state.outcome!=.None||expected_revision!=state.revision||cell<0||cell>=state.board_count do return false
	state.last_cell=cell;state.feedback_time=.42
	switch state.kind {
	case .Bind_The_Page:
		expected:=state.step<state.sequence_count?state.sequence[state.step]:-1;state.last_correct=cell==expected
		if state.last_correct {state.step+=1;state.score=state.step;if state.step>=state.goal do story_minigame_finish(state,true)} else {state.mistakes+=1;state.time_left=max(f32(0),state.time_left-.65)}
	case .Wake_The_Moonbloom:
		state.last_correct=cell==state.active_cell
		if state.last_correct {state.score+=1;if state.score>=state.goal {story_minigame_finish(state,true)} else {state.active_cell=story_next_garden_cell(state);state.target_time=max(f32(1.15),STORY_GARDEN_TARGET_SECONDS-f32(state.score)*.055)}} else {state.mistakes+=1;state.time_left=max(f32(0),state.time_left-.45)}
	case .Mirror_The_Unlost:
		if state.lock_time>0||state.matched[cell] do return false
		for i in 0..<state.revealed_count do if state.revealed[i]==cell do return false
		if state.revealed_count==0 {state.revealed[0]=cell;state.revealed_count=1;state.last_correct=true;state.revision+=1;return true}
		first:=state.revealed[0];state.revealed[1]=cell;state.revealed_count=2;state.last_correct=state.board[first]==state.board[cell]
		if state.last_correct {state.matched[first]=true;state.matched[cell]=true;state.revealed_count=0;state.score+=1;if state.score>=state.goal do story_minigame_finish(state,true)} else {state.mistakes+=1;state.lock_time=STORY_SOUL_MISMATCH_SECONDS}
	case .None:return false
	}
	state.revision+=1;return true
}

story_minigame_tick :: proc(state: ^Story_Minigame_State, dt: f32) -> bool {
	if state==nil||!state.active do return false
	step_dt:=clamp(dt,f32(0),f32(.25));state.feedback_time=max(f32(0),state.feedback_time-step_dt)
	switch state.phase {
	case .Ready:return false
	case .Preview:
		state.elapsed+=step_dt
		if state.elapsed>=story_minigame_preview_duration(state) {state.phase=.Play;state.elapsed=0;switch state.kind {case .Bind_The_Page:state.time_left=7.5;case .Wake_The_Moonbloom:state.time_left=9;case .Mirror_The_Unlost:state.time_left=12;case .None:};state.revision+=1}
	case .Play:
		state.elapsed+=step_dt;state.time_left=max(f32(0),state.time_left-step_dt)
		if state.kind==.Wake_The_Moonbloom {state.target_time=max(f32(0),state.target_time-step_dt);if state.target_time<=0&&state.outcome==.None {state.mistakes+=1;state.active_cell=story_next_garden_cell(state);state.target_time=max(f32(1.15),STORY_GARDEN_TARGET_SECONDS-f32(state.score)*.055);state.last_cell=-1;state.last_correct=false;state.feedback_time=.28;state.revision+=1}}
		if state.kind==.Mirror_The_Unlost&&state.lock_time>0 {state.lock_time=max(f32(0),state.lock_time-step_dt);if state.lock_time<=0 {state.revealed_count=0;state.revision+=1}}
		if state.time_left<=0&&state.outcome==.None do story_minigame_finish(state,state.score>=state.goal)
	case .Result:state.result_time=max(f32(0),state.result_time-step_dt);return state.result_time<=0
	}
	return false
}

// --- App-owned panel/modal reducer -----------------------------------------

@(private = "file")
story_panel_set_text :: proc(panel: ^Story_Panel_State, text: string) {
	if panel==nil do return
	panel.text_len=min(len(text),len(panel.text));panel.text={}
	for i in 0..<panel.text_len do panel.text[i]=text[i]
	panel.node_elapsed=0
}

@(private = "file")
story_panel_format_text :: proc(panel: ^Story_Panel_State, template: string, tokens: []Story_Text_Token) {
	text:=story_format_text(template,tokens);defer delete(text);story_panel_set_text(panel,text)
}

app_story_panel_full_narration :: proc(app: ^App) -> string {
	if app==nil||!app.story_panel.active do return ""
	return string(app.story_panel.text[:app.story_panel.text_len])
}

@(private = "file")
story_narration_char_delay :: proc(byte: u8) -> f32 {
	if byte=='\n' do return .18/STORY_NARRATION_SPEED
	if byte=='.'||byte=='!'||byte=='?' do return .25/STORY_NARRATION_SPEED
	if byte==';'||byte==':' do return .16/STORY_NARRATION_SPEED
	if byte==',' do return .10/STORY_NARRATION_SPEED
	if byte==' '||byte=='\t' do return .012/STORY_NARRATION_SPEED
	return .026/STORY_NARRATION_SPEED
}

@(private = "file")
story_utf8_width :: proc(value: u8) -> int {if value<0x80 do return 1;if value&0xe0==0xc0 do return 2;if value&0xf0==0xe0 do return 3;if value&0xf8==0xf0 do return 4;return 1}

app_story_panel_narration_duration :: proc(app: ^App) -> f32 {
	if app==nil||!app.story_panel.active do return 0
	total:f32
	for i:=0;i<app.story_panel.text_len; {total+=story_narration_char_delay(app.story_panel.text[i]);i+=max(1,story_utf8_width(app.story_panel.text[i]))}
	return total
}

app_story_panel_visible_byte_count :: proc(app: ^App) -> int {
	if app==nil||!app.story_panel.active do return 0
	elapsed:=max(f32(0),app.story_panel.node_elapsed);total:f32;visible:=0
	for i:=0;i<app.story_panel.text_len; {width:=min(story_utf8_width(app.story_panel.text[i]),app.story_panel.text_len-i);total+=story_narration_char_delay(app.story_panel.text[i]);if total>elapsed do break;visible=i+width;i+=width}
	return visible
}

app_story_panel_visible_narration :: proc(app: ^App) -> string {
	if app==nil||!app.story_panel.active do return ""
	count:=app_story_panel_visible_byte_count(app);return string(app.story_panel.text[:count])
}

app_story_panel_narration_complete :: proc(app: ^App) -> bool {return app==nil||!app.story_panel.active||app_story_panel_visible_byte_count(app)>=app.story_panel.text_len}
app_story_panel_reveal :: proc(app: ^App) {if app==nil||!app.story_panel.active do return;app.story_panel.node_elapsed=max(app.story_panel.node_elapsed,app_story_panel_narration_duration(app)+.05)}

@(private = "file")
story_recent_answered_beat :: proc(run: ^Run) -> ^Story_Beat {
	if run==nil do return nil
	for i:=min(run.depth-1,STORY_BEAT_COUNT-1);i>=0;i-=1 {beat:=&run.story.beats[i];if beat.resolution==.Aid||beat.resolution==.Bargain||beat.resolution==.Defy do return beat}
	return nil
}

@(private = "file")
app_story_omen_text :: proc(app: ^App) {
	run:=&app.run;beat:=story_current_beat(run);if beat==nil {story_panel_set_text(&app.story_panel,"The dungeon waits in silence.");return}
	greeting:="";if run.depth==1 {greeting=run.story_runtime.run_number<=1?"A fresh page. -- N. Rue, for the Worms. ":fmt.tprintf("Page %d. I have written you before. -- N. Rue. ",run.story_runtime.run_number)}
	tokens:=[4]Story_Text_Token{{"greeting",greeting},{"beat_title",story_beat_title(beat)},{"summary",beat.summary},{"truth",story_beat_truth(beat)}}
	story_panel_format_text(&app.story_panel,"{greeting}{beat_title}. {summary} {truth}",tokens[:])
}

@(private = "file")
app_story_guest_text :: proc(app: ^App) {
	i:=app.story_panel.guest_index;if i<0||i>=len(app.run.story_runtime.guests) {story_panel_set_text(&app.story_panel,"The guest waits for an answer.");return}
	guest:=&app.run.story_runtime.guests[i];relic:=STORY_RELICS[app.run.story.relic]
	tokens:=[3]Story_Text_Token{{"guest_dialogue",guest.dialogue},{"relic_name",relic.name},{"relic_temptation",relic.temptation}}
	story_panel_format_text(&app.story_panel,"{guest_dialogue}\nThe {relic_name} stirs: {relic_temptation}.",tokens[:])
}

@(private = "file")
app_story_soul_reflection_text :: proc(app: ^App) {
	beat:=story_recent_answered_beat(&app.run)
	if beat==nil {story_panel_set_text(&app.story_panel,"'You have finished nothing yet. My father counted everything except me. Then only me.'\n'What shall I do with the memory you carry now?'");return}
	tokens:=[2]Story_Text_Token{{"title",story_beat_title(beat)},{"outcome",beat.outcome}}
	story_panel_format_text(&app.story_panel,"'Your last finished turning -- '{title}'. It says: {outcome}'\n'I keep what you refuse to lose. What shall I do with it?'",tokens[:])
}

@(private = "file")
app_story_soul_settled_text :: proc(app: ^App) {
	verdict:=app.run.story_runtime.hall.verdict;text:="The chimes hold their breath, waiting for your answer."
	switch verdict {case .Preserve:text="The hall keeps your memory whole -- pain and all. Nothing of you fades here.";case .Release:text="Your memory rests here lightly. It remains, yet it no longer rules your next turning.";case .Refuse:text="You kept your history your own. The mirror holds no copy of you.";case .Unresolved:}
	if (verdict==.Preserve||verdict==.Release)&&story_true_name_known(&app.run.story,.Liss) do text=fmt.tprintf("%s ...My name is Liss Voss. Keep that too. Names open what they love -- say mine at the door, not his.",text)
	story_panel_set_text(&app.story_panel,text)
}

@(private = "file")
app_story_rebuild_panel_text :: proc(app: ^App) {
	panel:=&app.story_panel
	switch panel.node {
	case .Relic_Choice:app_story_omen_text(app)
	case .Guest_Choice:app_story_guest_text(app)
	case .Epilogue_Gate:story_panel_set_text(panel,"The Toll-Keeper is finished. The Gate opens its ledger and asks the last question: what should an ending be?")
	case .Epilogue_Ending:resolved:=story_resolve_recorded_ending(&app.run.story);defer story_ending_result_destroy(&resolved);tokens:=[2]Story_Text_Token{{"ending_title",resolved.ending.title},{"ending_body",resolved.ending.body}};story_panel_format_text(panel,"{ending_title}\n\n{ending_body}",tokens[:])
	case .Epilogue_Bell:resolved:=story_resolve_recorded_ending(&app.run.story);defer story_ending_result_destroy(&resolved);tokens:=[1]Story_Text_Token{{"ending_coda",resolved.coda}};story_panel_format_text(panel,"{ending_coda}\nThe tenth bell waits.",tokens[:])
	case .Soul_Reflection:app_story_soul_reflection_text(app)
	case .Soul_Settled:app_story_soul_settled_text(app)
	case .None:story_panel_set_text(panel,"")
	}
}

app_story_restore_panel_text :: proc(app: ^App) {
	if app == nil || !app.story_panel.active do return
	elapsed := app.story_panel.elapsed
	node_elapsed := app.story_panel.node_elapsed
	cursor := app.story_panel.choice_cursor
	app_story_rebuild_panel_text(app)
	app.story_panel.elapsed = elapsed
	app.story_panel.node_elapsed = node_elapsed
	app.story_panel.choice_cursor = cursor
}

app_story_set_panel_node :: proc(app: ^App,node: Story_Panel_Node) -> bool {if app==nil||!app.story_panel.active||node==.None do return false;app.story_panel.node=node;app.story_panel.node_elapsed=0;app.story_panel.choice_cursor=0;app_story_rebuild_panel_text(app);return true}
app_story_close_panel :: proc(app: ^App) {if app==nil do return;app.story_panel={};app_clear_play_input(app)}
app_story_open_omen :: proc(app: ^App)->bool {if app==nil||!app.run.story_runtime.initialized||story_current_beat(&app.run)==nil do return false;app.story_panel={active=true,mandatory=true,kind=.Omen,node=.Relic_Choice,guest_index=-1};app_story_rebuild_panel_text(app);app_clear_play_input(app);return true}
app_story_open_guest_dialogue :: proc(app: ^App,guest_index:int)->bool {if app==nil||guest_index<0||guest_index>=len(app.run.story_runtime.guests) do return false;guest:=&app.run.story_runtime.guests[guest_index];if guest.witness||guest.resolved do return false;_=story_mark_guest_met(&app.run,guest);app.story_panel={active=true,kind=.Guest,node=.Guest_Choice,guest_index=guest_index};app_story_rebuild_panel_text(app);app_clear_play_input(app);return true}

app_story_open_epilogue :: proc(app: ^App)->bool {
	if app==nil||!app.run.story_runtime.initialized||app.run.story_runtime.epilogue_stage==.Completed do return false
	stage:=app.run.story_runtime.epilogue_stage;if stage==.Unstarted do stage=.Gate;app.run.story_runtime.epilogue_stage=stage
	node:=Story_Panel_Node.Epilogue_Gate;if stage==.Ending do node=.Epilogue_Ending;if stage==.Bell do node=.Epilogue_Bell
	app.story_panel={active=true,kind=.Epilogue,node=node,guest_index=-1};app_story_rebuild_panel_text(app);app_clear_play_input(app);return true
}

app_story_open_lossless_soul :: proc(app: ^App)->bool {
	if app==nil||!app.run.story_runtime.soul.present do return false
	index:=clamp(app.run.depth,1,STORY_BEAT_COUNT)-1;ledger:=&app.run.story_runtime.hall_ledgers[index];ledger.met=true;app.run.story_runtime.hall.met=true;app.run.story_runtime.soul.met=true
	node:=ledger.verdict==.Unresolved?Story_Panel_Node.Soul_Reflection:.Soul_Settled
	app.story_panel={active=true,kind=.Soul,node=node,guest_index=-1};app_story_rebuild_panel_text(app);app_clear_play_input(app)
	if ledger.verdict==.Unresolved&&app.run.story_runtime.soul_games[index].outcome==.None do _=app_story_start_minigame(app,.Mirror_The_Unlost,ledger.room_index)
	return true
}

app_story_panel_active :: proc(app: ^App)->bool {return app!=nil&&app.story_panel.active}
app_story_minigame_active :: proc(app: ^App)->bool {return app!=nil&&app.story_minigame.active}
app_play_modal_open :: proc(app: ^App)->bool {return app_story_panel_active(app)||app_story_minigame_active(app)}

app_story_current_speaker :: proc(app: ^App)->string {
	if app==nil||!app.story_panel.active do return ""
	switch app.story_panel.node {case .Guest_Choice:i:=app.story_panel.guest_index;if 0<=i&&i<len(app.run.story_runtime.guests) do return app.run.story_runtime.guests[i].name;case .Soul_Reflection,.Soul_Settled:return "Lossless Soul";case .Relic_Choice,.Epilogue_Gate,.Epilogue_Ending,.Epilogue_Bell:return "Nim Rue";case .None:}
	return "Nim Rue"
}

@(rodata)
STORY_RELIC_OPTION_LABELS := [Story_Choice_Verb]string{.Aid="Offer a gentle vow",.Bargain="Whisper a hidden bargain",.Defy="Refuse the omen"}
@(rodata)
STORY_RELIC_OPTION_DETAILS := [Story_Choice_Verb]string{.Aid="follow the relic trail without a guardian",.Bargain="gain guidance, accept a guardian and a debt",.Defy="find the guarded echo without a guiding light"}

app_story_panel_choices :: proc(app: ^App)->(result: Story_Panel_Choice_List) {
	if app==nil||!app.story_panel.active do return
	switch app.story_panel.node {
	case .Relic_Choice:
		for row in 0..<STORY_CHOICE_COUNT {verb,ok:=story_relic_choice_at(&app.run,row);if !ok do continue;result.items[result.count]={label=STORY_RELIC_OPTION_LABELS[verb],detail=STORY_RELIC_OPTION_DETAILS[verb],key=STORY_CHOICE_KEYS[verb],verb=verb,has_verb=true};result.count+=1}
	case .Guest_Choice:
		i:=app.story_panel.guest_index;if 0<=i&&i<len(app.run.story_runtime.guests) {beat:=story_beat_for_depth(&app.run.story,app.run.story_runtime.guests[i].depth);if beat!=nil do for verb in Story_Choice_Verb {choice:=beat.choices[verb];result.items[result.count]={label=choice.label,detail=choice.intent,key=STORY_CHOICE_KEYS[verb],verb=verb,has_verb=true};result.count+=1}}
	case .Epilogue_Gate:for verb in Story_Choice_Verb {choice:=STORY_GATE_CHOICES[verb];result.items[result.count]={label=choice.label,detail=choice.detail,key=STORY_CHOICE_KEYS[verb],verb=verb,has_verb=true};result.count+=1}
	case .Epilogue_Ending:result.items[0]={label="...",detail="",key="page"};result.count=1
	case .Epilogue_Bell:result.items[0]={label="Ring the tenth bell",detail="Close the entry",key="bell"};result.count=1
	case .Soul_Reflection:result.items[0]={label="Preserve it exactly",detail="Keep the memory whole, including its pain",key="soul_preserve",verdict=.Preserve,has_verdict=true};result.items[1]={label="Release its hold",detail="Let the memory remain without ruling the next choice",key="soul_release",verdict=.Release,has_verdict=true};result.items[2]={label="Refuse the mirror",detail="Carry your history without giving the hall another copy",key="soul_refuse",verdict=.Refuse,has_verdict=true};result.count=3
	case .Soul_Settled,.None:
	}
	return
}

app_story_art_identity :: proc(app: ^App)->(result: Story_Art_Identity) {
	if app==nil||!app.story_panel.active do return
	result.panel_kind=app.story_panel.kind;result.node=app.story_panel.node;result.archetype=app.run.player.archetype
	beat:=story_current_beat(&app.run);if beat!=nil {result.motif=beat.motif;result.has_motif=true}
	if app.run.story_runtime.initialized {result.relic=app.run.story.relic;result.has_relic=true}
	if app.story_panel.kind==.Guest {i:=app.story_panel.guest_index;if 0<=i&&i<len(app.run.story_runtime.guests) {guest:=&app.run.story_runtime.guests[i];result.guest_role=guest.role;result.guest_variant=guest.variant;result.has_guest=true}}
	if app.story_panel.node==.Epilogue_Ending||app.story_panel.node==.Epilogue_Bell {if verb,ok:=story_verb_from_resolution(app.run.story.flags.gate);ok {result.ending_verb=verb;result.has_ending=true}}
	return
}

app_story_start_minigame :: proc(app: ^App,kind:Story_Minigame_Kind,room_index:=-1,continuation:Story_Choice_Verb={},has_continuation:=false)->bool {
	if app==nil||kind==.None||app.story_minigame.active do return false
	index:=clamp(app.run.depth,1,STORY_BEAT_COUNT)-1
	switch kind {case .Bind_The_Page:if app.run.story_runtime.bind_results[index]!=.None do return false;case .Wake_The_Moonbloom:if app.run.story_runtime.garden_games[index].outcome!=.None do return false;case .Mirror_The_Unlost:if app.run.story_runtime.soul_games[index].outcome!=.None do return false;case .None:return false}
	app.story_minigame=story_create_minigame(&app.run,kind,room_index,continuation,has_continuation);app.story_minigame_cursor=0;app_clear_play_input(app);return app.story_minigame.active
}
app_story_start_bind_the_page :: proc(app:^App,verb:Story_Choice_Verb)->bool{return app_story_start_minigame(app,.Bind_The_Page,-1,verb,true)}
app_story_start_wake_the_moonbloom :: proc(app:^App,room_index:int)->bool{return app_story_start_minigame(app,.Wake_The_Moonbloom,room_index)}
app_story_start_mirror_the_unlost :: proc(app:^App,room_index:int)->bool{return app_story_start_minigame(app,.Mirror_The_Unlost,room_index)}

@(private = "file")
app_story_grant_minigame_reward :: proc(app:^App,kind:Story_Minigame_Kind) {player:=&app.run.player;switch kind {case .Bind_The_Page:player.hp=player.max_hp;player.discipline_melee_bonus+=1;case .Wake_The_Moonbloom:player.max_hp+=5;if player.hp>0 do player.hp=min(player.max_hp,player.hp+5);player.max_mana+=5;player.mana=min(f32(player.max_mana),player.mana+5);case .Mirror_The_Unlost:player.max_mana+=5;player.mana=min(f32(player.max_mana),player.mana+5);player.discipline_spell_bonus+=1;case .None:};sfx_emit(&app.run, .Story_Consequence)}

app_story_finalize_minigame :: proc(app:^App)->bool {
	if app==nil||!app.story_minigame.active||app.story_minigame.phase!=.Result||app.story_minigame.outcome==.None do return false
	state:=app.story_minigame;index:=clamp(state.depth,1,STORY_BEAT_COUNT)-1;new_result:=false
	switch state.kind {case .Bind_The_Page:if app.run.story_runtime.bind_results[index]==.None {app.run.story_runtime.bind_results[index]=state.outcome;new_result=true};case .Wake_The_Moonbloom:ledger:=&app.run.story_runtime.garden_games[index];if ledger.outcome==.None {ledger.valid=true;ledger.room_index=state.room_index;ledger.outcome=state.outcome;new_result=true};case .Mirror_The_Unlost:ledger:=&app.run.story_runtime.soul_games[index];if ledger.outcome==.None {ledger.valid=true;ledger.room_index=state.room_index;ledger.outcome=state.outcome;new_result=true};case .None:return false}
	app.story_minigame={};app.story_minigame_cursor=0
	if new_result&&state.outcome==.Won do app_story_grant_minigame_reward(app,state.kind)
	if state.kind==.Bind_The_Page&&state.has_continuation {_=story_commit_relic_path(&app.run,state.continuation);app_story_close_panel(app)}
	if state.kind==.Mirror_The_Unlost&&app.story_panel.active&&app.story_panel.node==.Soul_Reflection {app.story_panel.node_elapsed=0;app_story_rebuild_panel_text(app)}
	app_clear_play_input(app);return true
}

app_story_minigame_grid :: proc(app:^App)->(columns,rows:int) {if app==nil||!app.story_minigame.active do return 0,0;count:=app.story_minigame.board_count;columns=count==8?4:3;rows=(count+columns-1)/columns;return}

@(private = "file")
app_story_move_minigame_cursor :: proc(app:^App,horizontal,vertical:int) {columns,rows:=app_story_minigame_grid(app);if columns<=0||rows<=0 do return;count:=app.story_minigame.board_count;x:=app.story_minigame_cursor%columns;y:=app.story_minigame_cursor/columns;x=((x+horizontal)%columns+columns)%columns;y=((y+vertical)%rows+rows)%rows;candidate:=y*columns+x;if candidate>=count do candidate=count-1;app.story_minigame_cursor=clamp(candidate,0,max(0,count-1))}

@(private = "file")
app_story_reduce_minigame :: proc(app:^App,intent:Intent) {state:=&app.story_minigame;if intent.menu_index_valid do app.story_minigame_cursor=clamp(intent.menu_index,0,max(0,state.board_count-1));app_story_move_minigame_cursor(app,intent.menu_horizontal,intent.menu_delta);if !(intent.confirm||intent.pointer_confirm) do return;if state.phase==.Ready {_=story_minigame_confirm_ready(state);return};if state.phase==.Play do _=story_minigame_press(state,app.story_minigame_cursor,state.revision)}

@(private = "file")
app_story_choose_panel_option :: proc(app:^App,choice:Story_Panel_Choice) {
	switch app.story_panel.node {
	case .Relic_Choice:if !choice.has_verb do return;if (app.run.depth==5||app.run.depth==8||app.run.depth==9)&&app.run.story_runtime.bind_results[app.run.depth-1]==.None {_=app_story_start_bind_the_page(app,choice.verb);return};if story_commit_relic_path(&app.run,choice.verb) do app_story_close_panel(app)
	case .Guest_Choice:i:=app.story_panel.guest_index;if choice.has_verb&&0<=i&&i<len(app.run.story_runtime.guests)&&story_resolve_guest_choice(&app.run,&app.run.story_runtime.guests[i],choice.verb) do app_story_close_panel(app)
	case .Epilogue_Gate:if choice.has_verb&&story_record_gate_choice(&app.run.story,choice.verb) {app.run.story_runtime.epilogue_stage=.Ending;_=app_story_set_panel_node(app,.Epilogue_Ending)}
	case .Epilogue_Ending:app.run.story_runtime.epilogue_stage=.Bell;_=app_story_set_panel_node(app,.Epilogue_Bell)
	case .Epilogue_Bell:if story_complete_bell_victory(&app.run) do app_story_close_panel(app)
	case .Soul_Reflection:if choice.has_verdict&&story_resolve_lossless_soul(&app.run,choice.verdict) do _=app_story_set_panel_node(app,.Soul_Settled)
	case .Soul_Settled,.None:app_story_close_panel(app)
	}
}

@(private = "file")
app_story_reduce_panel :: proc(app:^App,intent:Intent) {if intent.back {if !app.story_panel.mandatory do app_story_close_panel(app);return};choices:=app_story_panel_choices(app);if choices.count>0 {if intent.menu_index_valid do app.story_panel.choice_cursor=clamp(intent.menu_index,0,choices.count-1);app.story_panel.choice_cursor=((app.story_panel.choice_cursor+intent.menu_delta)%choices.count+choices.count)%choices.count};if !(intent.confirm||intent.pointer_confirm) do return;if !app_story_panel_narration_complete(app) {app_story_panel_reveal(app);return};if choices.count<=0 {app_story_close_panel(app);return};app_story_choose_panel_option(app,choices.items[app.story_panel.choice_cursor])}

app_story_reduce_modal :: proc(app:^App,intent:Intent) {if app==nil do return;app_clear_play_input(app);if app.story_minigame.active {app_story_reduce_minigame(app,intent);return};if app.story_panel.active do app_story_reduce_panel(app,intent)}
app_story_tick_modal :: proc(app:^App,dt:f32) {if app==nil do return;if app.story_minigame.active {if story_minigame_tick(&app.story_minigame,dt) do _=app_story_finalize_minigame(app);return};if app.story_panel.active {app.story_panel.elapsed+=dt;app.story_panel.node_elapsed+=dt}}
app_story_runtime_reset :: proc(app:^App) {if app==nil do return;app.story_panel={};app.story_minigame={};app.story_minigame_cursor=0}

app_story_process_requests :: proc(app:^App,include_omen:=false)->bool {
	if app==nil||app.mode!=.Playing||app_play_modal_open(app) do return false
	requests:=&app.run.story_runtime.requests
	if requests.collect_relic {requests.collect_relic=false;_=story_collect_relic_echo(&app.run);app_clear_play_input(app);return true}
	if requests.epilogue {requests.epilogue=false;return app_story_open_epilogue(app)}
	if include_omen&&requests.omen {requests.omen=false;return app_story_open_omen(app)}
	if requests.guest {index:=requests.guest_index;requests.guest=false;return app_story_open_guest_dialogue(app,index)}
	if requests.soul {requests.soul=false;return app_story_open_lossless_soul(app)}
	if requests.garden {room:=requests.garden_room;requests.garden=false;return app_story_start_wake_the_moonbloom(app,room)}
	return false
}

// --- Friendly movement and combat ------------------------------------------

story_snapshot_friendly_npc_positions :: proc(run:^Run) {if run==nil do return;for &guest in run.story_runtime.guests do guest.prev_pos=guest.pos;soul:=&run.story_runtime.soul;soul.prev_pos=soul.pos}

story_tick_friendly_npc_movement :: proc(run:^Run,elapsed,dt:f32) {
	if run==nil do return
	for &guest in run.story_runtime.guests {
		if guest.depth!=run.depth||!guest.alive||guest.witness||guest.ally do continue
		hold:=!guest.resolved&&story_distance_sq(guest.pos,run.player.pos)<=STORY_NPC_HOLD_RANGE*STORY_NPC_HOLD_RANGE&&
			line_of_sight(&run.dungeon,run.player.pos.x,run.player.pos.y,guest.pos.x,guest.pos.y)
		room_npc_motion_tick(run,&guest.pos,&guest.motion,hold,false,elapsed,dt)
	}
	soul:=&run.story_runtime.soul
	if soul.present&&soul.alive&&!soul.armed {
		hold:=soul.verdict==.Unresolved&&story_distance_sq(soul.pos,run.player.pos)<=STORY_NPC_HOLD_RANGE*STORY_NPC_HOLD_RANGE&&
			line_of_sight(&run.dungeon,run.player.pos.x,run.player.pos.y,soul.pos.x,soul.pos.y)
		room_npc_motion_tick(run,&soul.pos,&soul.motion,hold,false,elapsed,dt)
	}
}

@(private = "file")
story_ally_target :: proc(run:^Run,home,pos:Vec2)->^Enemy {nearest:^Enemy;best:=STORY_NPC_LEASH*STORY_NPC_LEASH;for &enemy in run.enemies {if enemy.hp<=0||story_distance_sq(enemy.pos,home)>STORY_NPC_LEASH*STORY_NPC_LEASH do continue;distance:=story_distance_sq(enemy.pos,pos);if distance<best&&line_of_sight(&run.dungeon,pos.x,pos.y,enemy.pos.x,enemy.pos.y) {best=distance;nearest=&enemy}};return nearest}

@(private = "file")
story_tick_ally :: proc(run:^Run,pos:^Vec2,motion:^Story_Npc_Motion,attack_timer:^f32,stats:Story_Ally_Stats,dt:f32) {
	attack_timer^=max(f32(0),attack_timer^-dt)
	motion.dancing=false
	motion.holding=false
	target:=story_ally_target(run,motion.home,pos^)
	if target==nil {
		room_npc_motion_tick_toward(run,pos,motion,motion.home,stats.speed,run.player.sim_elapsed,dt)
		return
	}
	delta:=target.pos-pos^;distance:=math.hypot(delta.x,delta.y);if distance>.001 do motion.facing=delta/distance
	stop:=max(f32(.6),stats.attack_range-.15)
	if distance>stop {
		step:=min(distance-stop,stats.speed*dt);next:=pos^+motion.facing*step
		motion.target=target.pos
		moved:=false
		if !blocked_for_radius(&run.dungeon,next.x,next.y,STORY_NPC_RADIUS) {pos^=next;moved=true;motion.anim_time+=dt}
		room_npc_motion_set_moving(motion,moved)
		return
	}
	room_npc_motion_wait(motion,pos^)
	if attack_timer^<=0&&distance<=stats.attack_range&&line_of_sight(&run.dungeon,pos.x,pos.y,target.pos.x,target.pos.y) {dealt:=player_damage_enemy(run,target,stats.damage,stats.damage_type);if dealt>0 do append(&run.numbers,Damage_Number{pos=target.pos,value=dealt,kind=.Damage_Dealt});attack_timer^=stats.attack_cd}
}

story_tick_friendly_npc_combat :: proc(run:^Run,dt:f32) {
	if run==nil do return
	for &guest in run.story_runtime.guests {if guest.depth!=run.depth||guest.witness||!guest.resolved||!guest.ally||!guest.alive||guest.hp<=0 do continue;story_tick_ally(run,&guest.pos,&guest.motion,&guest.attack_timer,STORY_GUEST_ALLY_STATS,dt)}
	soul:=&run.story_runtime.soul;if soul.present&&soul.armed&&soul.alive&&soul.hp>0 do story_tick_ally(run,&soul.pos,&soul.motion,&soul.attack_timer,STORY_SOUL_ALLY_STATS,dt)
}

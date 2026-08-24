package archrogue

// MX-save's raylib-free document model. Filesystem ownership and worker
// scheduling stay in main.odin; this module owns schemas, checksums, migration,
// validation, profile/Chronicle operations, and explicit Run conversion.

import "core:encoding/hex"
import "core:encoding/json"
import "core:fmt"
import "core:math"
import "core:math/bits"
import "core:strings"

OPTIONS_DOCUMENT_SCHEMA_VERSION :: 2
PROFILE_DOCUMENT_SCHEMA_VERSION :: 2
PROFILE_DOCUMENT_SCHEMA_V1      :: 1
RUN_DOCUMENT_SCHEMA_VERSION     :: 2
RUN_DOCUMENT_SCHEMA_V1          :: 1
CHRONICLE_RECORD_SCHEMA_VERSION :: 1
LEGACY_OPTIONS_SCHEMA_VERSION   :: 1
PROFILE_MAX_GRANTED_ACHIEVEMENTS :: 64

PERSISTENCE_MAX_STRING_BYTES :: 4096
PERSISTENCE_OPTIONS_MAX_BYTES :: 256 * 1024
PERSISTENCE_PROFILE_MAX_BYTES :: 2 * 1024 * 1024
PERSISTENCE_RUN_MAX_BYTES     :: 10 * 1024 * 1024
CHRONICLE_MAX_RECORDS         :: 512
CHRONICLE_MAX_BOSSES          :: len(Boss_Id)
CHRONICLE_MAX_THEMES          :: DUNGEON_DEPTH

Persistence_Document_Kind :: enum u8 {
	Options,
	Profile,
	Run,
}

Persistence_Decode_Status :: enum u8 {
	Valid,
	Migrated,
	Missing,
	Corrupt,
	Future,
	Oversize,
}

Persistence_Request :: enum u8 {
	None,
	Resume,
	Save_Checkpoint,
	Save_Return_Title,
	Save_Quit,
	Abandon,
	Recover_Run,
	Quarantine_Run,
	Recover_Documents,
	Quarantine_Documents,
	Finalize_Death,
	Finalize_Victory,
}

Persistence_Error_Kind :: enum u8 {
	None,
	Encode,
	Write,
	Load,
	Corrupt,
	Future,
	Remove,
}

Run_Terminal_State :: enum u8 {
	Active,
	Death,
	Victory,
	Abandoned,
}

Run_Finalization_Phase :: enum u8 {
	None,
	Terminal_Marker,
	Profile_Committed,
}

Chronicle_Outcome :: enum u8 {
	Victory,
	Fallen,
}

Chronicle_Outcome_Filter :: enum u8 {
	All,
	Victories,
	Fallen,
}

Chronicle_Focus :: enum u8 {
	Outcome,
	Archetype,
	Difficulty,
	Timeline,
}

Chronicle_View_State :: struct {
	outcome:          Chronicle_Outcome_Filter,
	archetype_filter: int, // -1 means all
	difficulty_filter:int, // -1 means all
	focus:            Chronicle_Focus,
	selected:         int, // filtered, newest-first index
	scroll:           int,
}

Chronicle_Notable_Item :: struct {
	item_id:      string,
	display_name: string,
	rarity:       Rarity,
}

Chronicle_Record :: struct {
	record_schema_version: int,
	run_id:           string,
	outcome:          Chronicle_Outcome,
	archetype:        Archetype_Id,
	difficulty:       Difficulty_Id,
	seed:             u64,
	deepest_floor:    int,
	started_at_utc:   string,
	ended_at_utc:     string,
	active_ticks:     u64,
	final_level:      int,
	kills:            int,
	traps_triggered:  int,
	shrines_used:     int,
	secrets_opened:   int,
	bars_visited:     int,
	bars_toasted:     int,
	challenge_rooms_cleared: int,
	run_modifier:     Run_Modifier_Id,
	visited_theme_ids:[CHRONICLE_MAX_THEMES]string,
	visited_theme_count:int,
	defeated_boss_ids:[CHRONICLE_MAX_BOSSES]string,
	defeated_boss_count:int,
	notable_items:    [MAX_NOTABLE_LOOT]Chronicle_Notable_Item,
	notable_count:    int,
	cause_of_death:   string,
	story_faction_id: string,
	story_relic_id:   string,
	story_ending_id:  string,
}

Profile_State :: struct {
	profile_id:       string,
	revision:         u64,
	hell_unlocked:    bool,
	run_sequence:     u64,
	lifetime_started: u64,
	lifetime_descents:u64,
	lifetime_victories:u64,
	lifetime_kills:   u64,
	best_depth:       int,
	discovered_endings:[32]string,
	discovered_ending_count:int,
	chronicle:        [dynamic]Chronicle_Record,
	// Steam-parity lifetime aggregates (profile schema v2). Chronicle retention
	// prunes at 512 records, so lifetime achievement triggers keep their own
	// merge-safe union sets and counters here, keyed by stable save-id strings.
	victory_difficulty_ids: [len(Difficulty_Id)]string,
	victory_difficulty_count: int,
	victory_archetype_ids: [len(Archetype_Id)]string,
	victory_archetype_count: int,
	lifetime_boss_ids: [len(Boss_Id)]string,
	lifetime_boss_count: int,
	story_verb_ids: [len(Story_Choice_Verb)]string,
	story_verb_count: int,
	theme_ids_seen: [len(THEMES)]string,
	theme_seen_count: int,
	modifier_ids_seen: [len(Run_Modifier_Id)]string,
	modifier_seen_count: int,
	unique_item_ids_seen: [len(UNIQUE_DEFS)]string,
	unique_seen_count: int,
	lifetime_secrets: u64,
	lifetime_shrines: u64,
	lifetime_wall_touches: u64,
	granted_achievement_ids: [PROFILE_MAX_GRANTED_ACHIEVEMENTS]string,
	granted_achievement_count: int,
	owns_strings:     bool, // runtime-only; omitted from Profile_Payload
}

@(rodata)
ARCHETYPE_SAVE_IDS := [Archetype_Id]string{
	.Warden="warden", .Rogue="rogue", .Arcanist="arcanist",
	.Acolyte="acolyte", .Ranger="ranger",
}

@(rodata)
STORY_VERB_SAVE_IDS := [Story_Choice_Verb]string{
	.Aid="aid", .Bargain="bargain", .Defy="defy",
}

@(rodata)
MODIFIER_SAVE_IDS := [Run_Modifier_Id]string{
	.Blood_Moon="blood_moon", .Restless_Depths="restless_depths",
	.Treasure_Draught="treasure_draught", .Trap_Laced="trap_laced",
	.Thin_Veil="thin_veil", .Starved_Depths="starved_depths",
	.Elite_Hunt="elite_hunt", .Cursed_Bargains="cursed_bargains",
}

@(rodata)
FRAME_RATE_CAP_SAVE_IDS := [Frame_Rate_Cap]string{
	.FPS_30="fps_30", .FPS_60="fps_60", .FPS_90="fps_90",
	.FPS_120="fps_120", .Unlimited="unlimited",
}

@(rodata)
DIFFICULTY_SAVE_IDS := [Difficulty_Id]string{
	.Easy="easy", .Medium="medium", .Hard="hard", .Hell="hell",
}

@(rodata)
AUDIO_VOLUME_SAVE_IDS := [Audio_Volume]string{
	.Off="0", .Percent_10="10", .Percent_20="20", .Percent_30="30",
	.Percent_40="40", .Percent_50="50", .Percent_60="60", .Percent_70="70",
	.Percent_80="80", .Percent_90="90", .Full="100",
}

@(rodata)
INPUT_COMMAND_SAVE_IDS := [Input_Command]string{
	.None="none", .Up="up", .Down="down", .Left="left", .Right="right",
	.Confirm="confirm", .Back="back", .Tab="tab", .Help="help",
	.Interact="interact", .Inventory="inventory", .Character="character",
	.Ability_1="ability_1", .Ability_2="ability_2", .Ability_3="ability_3",
	.Ability_4="ability_4", .Ability_5="ability_5", .Ability_6="ability_6",
	.Minimap_Zoom_In="minimap_zoom_in", .Minimap_Zoom_Out="minimap_zoom_out",
}

@(rodata)
CONTROLLER_BUTTON_SAVE_IDS := [Controller_Button]string{
	.A="a", .B="b", .X="x", .Y="y", .Left_Bumper="left_bumper",
	.Right_Bumper="right_bumper", .Back="back", .Start="start",
	.Left_Stick="left_stick", .Right_Stick="right_stick",
	.Dpad_Up="dpad_up", .Dpad_Down="dpad_down",
	.Dpad_Left="dpad_left", .Dpad_Right="dpad_right",
}

@(rodata)
CONTROLLER_TRIGGER_SAVE_IDS := [Controller_Trigger]string{
	.Left="left_trigger", .Right="right_trigger",
}

@(rodata)
THEME_SAVE_IDS := [len(THEMES)]string{
	"crypt_of_ash", "fungal_catacombs", "frozen_reliquary", "sunken_scriptorium",
	"iron_ossuary", "moonless_vault", "bloodroot_halls", "gate_of_night",
}

@(rodata)
BOSS_SAVE_IDS := [Boss_Id]string{
	.Ash_Gallows="ash_gallows", .Mycelial_Matron="mycelial_matron",
	.Rime_Chanter="rime_chanter", .Void_Sentinel="void_sentinel",
	.Gate_Tyrant="gate_tyrant",
}

@(rodata)
ENEMY_SAVE_IDS := [Enemy_Kind]string{
	.Ghoul="ghoul", .Venom_Skitter="venom_skitter", .Bone_Imp="bone_imp",
	.Grave_Archer="grave_archer", .Cultist="cultist", .Crypt_Brute="crypt_brute",
	.Ash_Hound="ash_hound", .Rune_Sentinel="rune_sentinel", .Plague_Toad="plague_toad",
	.Hollow_Knight="hollow_knight", .Gate_Warden="gate_warden",
}

persistence_enemy_source_id :: proc(enemy:^Enemy)->string {
	if enemy==nil do return "unknown"
	if enemy.role==.Boss&&int(enemy.boss_id)>=0&&int(enemy.boss_id)<len(Boss_Id) do return BOSS_SAVE_IDS[enemy.boss_id]
	if int(enemy.kind)>=0&&int(enemy.kind)<len(Enemy_Kind) do return ENEMY_SAVE_IDS[enemy.kind]
	return "unknown_enemy"
}

persistence_cause_label :: proc(id:string)->string {
	for key,boss in BOSS_SAVE_IDS {if key==id do return BOSS_DEFS[boss].name}
	for key,enemy in ENEMY_SAVE_IDS {if key==id do return ENEMY_DEFS[enemy].name}
	switch id {case "trap":return "Dungeon trap";case "poison":return "Poison";case "enemy_projectile":return "Hostile projectile";case "hostile_magic":return "Hostile magic"}
	return "Unknown cause"
}

persistence_relic_label :: proc(id:string)->string {
	for relic in Story_Relic_Id {if id==fmt.tprintf("%v",relic) do return STORY_RELICS[relic].name}
	return "Unknown relic"
}

persistence_ending_label :: proc(id:string)->string {
	for archetype in Archetype_Id {for verb in Story_Choice_Verb {ending:=STORY_ENDINGS[archetype][verb];if ending.slug==id do return ending.title}}
	return "Unknown ending"
}

Option_Binding_DTO :: struct {
	input_id:   string,
	command_id: string,
}

Options_Payload :: struct {
	fullscreen:         bool,
	frame_rate_cap_id:  string,
	view_zoom:          f32,
	difficulty_id:      string,
	controller_enabled: bool,
	button_bindings:    [len(Controller_Button)]Option_Binding_DTO,
	trigger_bindings:   [len(Controller_Trigger)]Option_Binding_DTO,
	audio_enabled:      bool,   // compatibility field for pre-volume documents
	sfx_volume_id:      string, // additive 2026-08: absent in older documents
	music_volume_id:    string, // additive 2026-08: accepts legacy 25% steps
	lighting_enabled:   bool,
	mist_enabled:       bool,
	minimap_visible:    bool,
}

Legacy_Options_File_V1 :: struct {
	schema_version:     int,
	fullscreen:         bool,
	frame_rate_cap:     Frame_Rate_Cap,
	view_zoom:          f32,
	difficulty:         Difficulty_Id,
	hell_unlocked:      bool,
	controller_enabled: bool,
	gamepad_mapping:    Controller_Mapping,
	audio_enabled:      bool,
	lighting_enabled:   bool,
	mist_enabled:       bool,
	minimap_visible:    bool,
}

Options_Document :: struct {
	schema_version: int,
	game_release:   string,
	document_id:    string,
	revision:       u64,
	written_at_utc: string,
	payload_sha256: string,
	payload:        Options_Payload,
}

Profile_Payload :: struct {
	profile_id:       string,
	hell_unlocked:    bool,
	run_sequence:     u64,
	lifetime_started: u64,
	lifetime_descents:u64,
	lifetime_victories:u64,
	lifetime_kills:   u64,
	best_depth:       int,
	discovered_endings:[32]string,
	discovered_ending_count:int,
	chronicle:        [dynamic]Chronicle_Record,
	victory_difficulty_ids: [len(Difficulty_Id)]string,
	victory_difficulty_count: int,
	victory_archetype_ids: [len(Archetype_Id)]string,
	victory_archetype_count: int,
	lifetime_boss_ids: [len(Boss_Id)]string,
	lifetime_boss_count: int,
	story_verb_ids: [len(Story_Choice_Verb)]string,
	story_verb_count: int,
	theme_ids_seen: [len(THEMES)]string,
	theme_seen_count: int,
	modifier_ids_seen: [len(Run_Modifier_Id)]string,
	modifier_seen_count: int,
	unique_item_ids_seen: [len(UNIQUE_DEFS)]string,
	unique_seen_count: int,
	lifetime_secrets: u64,
	lifetime_shrines: u64,
	lifetime_wall_touches: u64,
	granted_achievement_ids: [PROFILE_MAX_GRANTED_ACHIEVEMENTS]string,
	granted_achievement_count: int,
}

// Retained schema-1 payload shape. Migration decodes and hash-verifies v1
// documents against this exact struct, then converts; do not evolve it.
Profile_Payload_V1 :: struct {
	profile_id:       string,
	hell_unlocked:    bool,
	run_sequence:     u64,
	lifetime_started: u64,
	lifetime_descents:u64,
	lifetime_victories:u64,
	lifetime_kills:   u64,
	best_depth:       int,
	discovered_endings:[32]string,
	discovered_ending_count:int,
	chronicle:        [dynamic]Chronicle_Record,
}

Profile_Document :: struct {
	schema_version: int,
	game_release:   string,
	document_id:    string,
	revision:       u64,
	written_at_utc: string,
	payload_sha256: string,
	payload:        Profile_Payload,
}

Profile_Document_V1 :: struct {
	schema_version: int,
	game_release:   string,
	document_id:    string,
	revision:       u64,
	written_at_utc: string,
	payload_sha256: string,
	payload:        Profile_Payload_V1,
}

Run_Save_Payload :: struct {
	active_ticks:   u64,
	started_at_utc: string,
	ended_at_utc:   string,
	terminal:       Run_Terminal_State,
	finalization:   Run_Finalization_Phase,
	seed:           u64,
	depth:          int,
	difficulty:     Difficulty_Id,
	dungeon:        Dungeon,
	player:         Player,
	enemies:        [dynamic]Enemy,
	next_enemy_id:  u32,
	next_familiar_id:u32,
	next_save_entity_id:u64,
	storm_cast_counter:u32,
	floor_epoch:    u32,
	projectiles:    [dynamic]Projectile,
	familiars:      [dynamic]Familiar,
	bells:          [dynamic]Ambush_Bell,
	ground_items:   [dynamic]Ground_Item,
	shopkeeper:     Shopkeeper,
	has_shopkeeper: bool,
	ambient_residents:Ambient_Room_Npc_Set,
	refuge:         Refuge_State,
	shop_requested: bool,
	loot_rng:       Pcg32,
	combat_rng:     Pcg32,
	dark_floor:     bool,
	theme_index:    int,
	explored:       [MAP_W][MAP_H]bool,
	boss_engaged:   bool,
	sealed:         [dynamic]Sealed_Tile,
	tyrant_dead:    bool,
	victory:        bool,
	kills:          int,
	modifier:       Run_Modifier_Id,
	plan:           [DUNGEON_DEPTH]Floor_Plan,
	story:          Story_State,
	story_runtime:  Story_Run_Runtime,
	story_panel:    Story_Panel_State,
	story_minigame: Story_Minigame_State,
	story_minigame_cursor:int,
	bars_visited:   int,
	bars_toasted:   int,
	challenge_rooms_cleared:int,
	traps:          [dynamic]Trap,
	shrines:        [dynamic]Shrine,
	secrets:        [dynamic]Secret,
	traps_triggered:int,
	shrines_used:   int,
	secrets_opened: int,
	notable_loot:   [MAX_NOTABLE_LOOT]Notable_Loot,
	notable_count:  int,
	visited_themes: [len(THEMES)]bool,
	defeated_bosses:[Boss_Id]bool,
	last_damage_source:string,
	wall_touches:   int,
	potions_used:   int, // schema v2: Steam achievement run facts must survive resume
	elites_killed:  int, // schema v2
}

// Retained schema-1 payload shape for migration decode + hash verification.
// Field-for-field the alpha.23 layout; do not evolve it.
Run_Save_Payload_V1 :: struct {
	active_ticks:   u64,
	started_at_utc: string,
	ended_at_utc:   string,
	terminal:       Run_Terminal_State,
	finalization:   Run_Finalization_Phase,
	seed:           u64,
	depth:          int,
	difficulty:     Difficulty_Id,
	dungeon:        Dungeon,
	player:         Player,
	enemies:        [dynamic]Enemy,
	next_enemy_id:  u32,
	next_familiar_id:u32,
	next_save_entity_id:u64,
	storm_cast_counter:u32,
	floor_epoch:    u32,
	projectiles:    [dynamic]Projectile,
	familiars:      [dynamic]Familiar,
	bells:          [dynamic]Ambush_Bell,
	ground_items:   [dynamic]Ground_Item,
	shopkeeper:     Shopkeeper,
	has_shopkeeper: bool,
	ambient_residents:Ambient_Room_Npc_Set,
	refuge:         Refuge_State,
	shop_requested: bool,
	loot_rng:       Pcg32,
	combat_rng:     Pcg32,
	dark_floor:     bool,
	theme_index:    int,
	explored:       [MAP_W][MAP_H]bool,
	boss_engaged:   bool,
	sealed:         [dynamic]Sealed_Tile,
	tyrant_dead:    bool,
	victory:        bool,
	kills:          int,
	modifier:       Run_Modifier_Id,
	plan:           [DUNGEON_DEPTH]Floor_Plan,
	story:          Story_State,
	story_runtime:  Story_Run_Runtime,
	story_panel:    Story_Panel_State,
	story_minigame: Story_Minigame_State,
	story_minigame_cursor:int,
	bars_visited:   int,
	bars_toasted:   int,
	challenge_rooms_cleared:int,
	traps:          [dynamic]Trap,
	shrines:        [dynamic]Shrine,
	secrets:        [dynamic]Secret,
	traps_triggered:int,
	shrines_used:   int,
	secrets_opened: int,
	notable_loot:   [MAX_NOTABLE_LOOT]Notable_Loot,
	notable_count:  int,
	visited_themes: [len(THEMES)]bool,
	defeated_bosses:[Boss_Id]bool,
	last_damage_source:string,
	wall_touches:   int,
}

Run_Document :: struct {
	schema_version: int,
	game_release:   string,
	document_id:    string,
	run_id:         string,
	revision:       u64,
	written_at_utc: string,
	payload_sha256: string,
	payload:        Run_Save_Payload,
}

Run_Document_V1 :: struct {
	schema_version: int,
	game_release:   string,
	document_id:    string,
	run_id:         string,
	revision:       u64,
	written_at_utc: string,
	payload_sha256: string,
	payload:        Run_Save_Payload_V1,
}

// Ownership-transferring v1 -> v2 conversion; the v1 payload is zeroed.
run_payload_from_v1 :: proc(v1: ^Run_Save_Payload_V1) -> Run_Save_Payload {
	if v1 == nil do return {}
	payload := Run_Save_Payload{
		active_ticks=v1.active_ticks, started_at_utc=v1.started_at_utc,
		ended_at_utc=v1.ended_at_utc, terminal=v1.terminal,
		finalization=v1.finalization, seed=v1.seed, depth=v1.depth,
		difficulty=v1.difficulty, dungeon=v1.dungeon, player=v1.player,
		enemies=v1.enemies, next_enemy_id=v1.next_enemy_id,
		next_familiar_id=v1.next_familiar_id, next_save_entity_id=v1.next_save_entity_id,
		storm_cast_counter=v1.storm_cast_counter, floor_epoch=v1.floor_epoch,
		projectiles=v1.projectiles, familiars=v1.familiars, bells=v1.bells,
		ground_items=v1.ground_items, shopkeeper=v1.shopkeeper,
		has_shopkeeper=v1.has_shopkeeper, ambient_residents=v1.ambient_residents,
		refuge=v1.refuge, shop_requested=v1.shop_requested, loot_rng=v1.loot_rng,
		combat_rng=v1.combat_rng, dark_floor=v1.dark_floor, theme_index=v1.theme_index,
		explored=v1.explored, boss_engaged=v1.boss_engaged, sealed=v1.sealed,
		tyrant_dead=v1.tyrant_dead, victory=v1.victory, kills=v1.kills,
		modifier=v1.modifier, plan=v1.plan, story=v1.story,
		story_runtime=v1.story_runtime, story_panel=v1.story_panel,
		story_minigame=v1.story_minigame, story_minigame_cursor=v1.story_minigame_cursor,
		bars_visited=v1.bars_visited, bars_toasted=v1.bars_toasted,
		challenge_rooms_cleared=v1.challenge_rooms_cleared,
		traps=v1.traps, shrines=v1.shrines, secrets=v1.secrets,
		traps_triggered=v1.traps_triggered, shrines_used=v1.shrines_used,
		secrets_opened=v1.secrets_opened, notable_loot=v1.notable_loot,
		notable_count=v1.notable_count, visited_themes=v1.visited_themes,
		defeated_bosses=v1.defeated_bosses, last_damage_source=v1.last_damage_source,
		wall_touches=v1.wall_touches,
	}
	v1^ = {}
	return payload
}

Document_Probe :: struct {
	schema_version: int,
	game_release:   string,
	document_id:    string,
	run_id:         string,
	revision:       u64,
	written_at_utc: string,
	payload_sha256: string,
}

persistence_json_options :: proc() -> json.Marshal_Options {
	return {
		pretty=true,
		use_spaces=true,
		spaces=2,
		sort_maps_by_key=true,
		use_enum_names=true,
	}
}

persistence_marshal :: proc(value: $T) -> ([]byte, bool) {
	data, err := json.marshal(value, persistence_json_options(), allocator=context.allocator)
	return data, err == nil
}

PERSISTENCE_SHA256_INITIAL := [8]u32{
	0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
	0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19,
}

PERSISTENCE_SHA256_ROUND := [64]u32{
	0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5,
	0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
	0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3,
	0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
	0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc,
	0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
	0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7,
	0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
	0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13,
	0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
	0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3,
	0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
	0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5,
	0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
	0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208,
	0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
}

@(private = "file")
persistence_sha256_transform :: proc(state: ^[8]u32, block: []byte) {
	words: [64]u32
	for i in 0 ..< 16 {
		offset := i * 4
		words[i] = u32(block[offset]) << 24 | u32(block[offset+1]) << 16 |
			u32(block[offset+2]) << 8 | u32(block[offset+3])
	}
	for i in 16 ..< 64 {
		x := words[i-15]
		y := words[i-2]
		sigma0 := bits.rotate_left32(x, 25) ~ bits.rotate_left32(x, 14) ~ (x >> 3)
		sigma1 := bits.rotate_left32(y, 15) ~ bits.rotate_left32(y, 13) ~ (y >> 10)
		words[i] = words[i-16] + sigma0 + words[i-7] + sigma1
	}

	a, b, c, d := state[0], state[1], state[2], state[3]
	e, f, g, h := state[4], state[5], state[6], state[7]
	for i in 0 ..< 64 {
		sum1 := bits.rotate_left32(e, 26) ~ bits.rotate_left32(e, 21) ~ bits.rotate_left32(e, 7)
		choose := g ~ (e & (f ~ g))
		temp1 := h + sum1 + choose + PERSISTENCE_SHA256_ROUND[i] + words[i]
		sum0 := bits.rotate_left32(a, 30) ~ bits.rotate_left32(a, 19) ~ bits.rotate_left32(a, 10)
		majority := (a & b) ~ (a & c) ~ (b & c)
		temp2 := sum0 + majority
		h, g, f, e, d, c, b, a = g, f, e, d + temp1, c, b, a, temp1 + temp2
	}
	state[0] += a
	state[1] += b
	state[2] += c
	state[3] += d
	state[4] += e
	state[5] += f
	state[6] += g
	state[7] += h
}

@(private = "file")
persistence_sha256_digest :: proc(data: []byte) -> (digest: [32]byte) {
	state := PERSISTENCE_SHA256_INITIAL
	offset := 0
	for len(data)-offset >= 64 {
		persistence_sha256_transform(&state, data[offset:offset+64])
		offset += 64
	}

	block: [64]byte
	remaining := len(data)-offset
	copy(block[:remaining], data[offset:])
	block[remaining] = 0x80
	if remaining >= 56 {
		persistence_sha256_transform(&state, block[:])
		block = {}
	}
	bit_length := u64(len(data)) * 8
	for i in 0 ..< 8 do block[63-i] = byte(bit_length >> u64(i*8))
	persistence_sha256_transform(&state, block[:])

	for word, i in state {
		digest[i*4] = byte(word >> 24)
		digest[i*4+1] = byte(word >> 16)
		digest[i*4+2] = byte(word >> 8)
		digest[i*4+3] = byte(word)
	}
	return
}

persistence_sha256 :: proc(data: []byte) -> string {
	digest := persistence_sha256_digest(data)
	encoded, err := hex.encode(digest[:], context.allocator)
	if err != .None do return ""
	return string(encoded)
}

persistence_json_preflight :: proc(data: []byte, max_bytes: int) -> bool {
	if len(data) == 0 || len(data) > max_bytes do return false
	in_string := false
	escaped := false
	string_bytes := 0
	for byte in data {
		if in_string {
			if escaped {
				escaped = false
				string_bytes += 1
			} else if byte == '\\' {
				escaped = true
			} else if byte == '"' {
				in_string = false
				string_bytes = 0
			} else {
				string_bytes += 1
			}
			if string_bytes > PERSISTENCE_MAX_STRING_BYTES do return false
		} else if byte == '"' {
			in_string = true
			string_bytes = 0
		}
	}
	return !in_string && !escaped
}

persistence_clone_string :: proc(value: string, allocator := context.allocator) -> string {
	if value == "" do return ""
	return strings.clone(value, allocator)
}

persistence_string_enum :: proc(ids: [$N]string, value: string, fallback: int) -> int {
	for id, index in ids {
		if id == value do return int(index)
	}
	return fallback
}

persistence_audio_volume_id :: proc(value: string, fallback: Audio_Volume) -> Audio_Volume {
	if index := persistence_string_enum(AUDIO_VOLUME_SAVE_IDS, value, -1); index >= 0 {
		return Audio_Volume(index)
	}
	// Music saves from the previous five-step contract retain their nearest 10%.
	switch value {
	case "off": return .Off
	case "25":  return .Percent_30
	case "75":  return .Percent_80
	}
	return fallback
}

options_payload_from_options :: proc(options: Options) -> Options_Payload {
	sfx_volume := audio_volume_normalize(options.sfx_volume, DEFAULT_SFX_VOLUME)
	if !options.audio_enabled do sfx_volume = .Off
	payload := Options_Payload{
		fullscreen=options.fullscreen,
		frame_rate_cap_id=FRAME_RATE_CAP_SAVE_IDS[frame_rate_cap_normalize(options.frame_rate_cap)],
		view_zoom=options.view_zoom,
		difficulty_id=DIFFICULTY_SAVE_IDS[difficulty_is_valid(options.difficulty) ? options.difficulty : DEFAULT_DIFFICULTY],
		controller_enabled=options.controller_enabled,
		audio_enabled=sfx_volume != .Off,
		sfx_volume_id=AUDIO_VOLUME_SAVE_IDS[sfx_volume],
		music_volume_id=AUDIO_VOLUME_SAVE_IDS[audio_volume_normalize(options.music_volume, DEFAULT_MUSIC_VOLUME)],
		lighting_enabled=options.lighting_enabled,
		mist_enabled=options.mist_enabled,
		minimap_visible=options.minimap_visible,
	}
	for button in Controller_Button {
		payload.button_bindings[button] = {
			input_id=CONTROLLER_BUTTON_SAVE_IDS[button],
			command_id=INPUT_COMMAND_SAVE_IDS[options.gamepad_mapping.gameplay_buttons[button]],
		}
	}
	for trigger in Controller_Trigger {
		payload.trigger_bindings[trigger] = {
			input_id=CONTROLLER_TRIGGER_SAVE_IDS[trigger],
			command_id=INPUT_COMMAND_SAVE_IDS[options.gamepad_mapping.triggers[trigger]],
		}
	}
	return payload
}

options_payload_destroy :: proc(payload: ^Options_Payload) {
	if payload == nil do return
	delete(payload.frame_rate_cap_id)
	delete(payload.difficulty_id)
	delete(payload.sfx_volume_id)
	delete(payload.music_volume_id)
	for &binding in payload.button_bindings {
		delete(binding.input_id)
		delete(binding.command_id)
	}
	for &binding in payload.trigger_bindings {
		delete(binding.input_id)
		delete(binding.command_id)
	}
	payload^ = {}
}

options_from_payload :: proc(payload: ^Options_Payload, hell_unlocked: bool) -> (Options, bool) {
	if payload == nil do return options_default(), false
	options := options_default()
	options.fullscreen = payload.fullscreen
	cap_index := persistence_string_enum(FRAME_RATE_CAP_SAVE_IDS, payload.frame_rate_cap_id, -1)
	difficulty_index := persistence_string_enum(DIFFICULTY_SAVE_IDS, payload.difficulty_id, -1)
	if cap_index < 0 || difficulty_index < 0 do return options, false
	options.frame_rate_cap = Frame_Rate_Cap(cap_index)
	options.view_zoom = payload.view_zoom
	options.difficulty = Difficulty_Id(difficulty_index)
	options.controller_enabled = payload.controller_enabled
	// Pre-volume documents carry only audio_enabled. New documents persist the
	// exact 10% step while retaining that boolean for backward compatibility.
	options.sfx_volume = persistence_audio_volume_id(
		payload.sfx_volume_id,
		payload.audio_enabled ? DEFAULT_SFX_VOLUME : Audio_Volume.Off,
	)
	options.audio_enabled = options.sfx_volume != .Off
	options.music_volume = persistence_audio_volume_id(payload.music_volume_id, DEFAULT_MUSIC_VOLUME)
	options.lighting_enabled = payload.lighting_enabled
	options.mist_enabled = payload.mist_enabled
	options.minimap_visible = payload.minimap_visible
	mapping := controller_default_mapping()
	for binding in payload.button_bindings {
		input_index := persistence_string_enum(CONTROLLER_BUTTON_SAVE_IDS, binding.input_id, -1)
		command_index := persistence_string_enum(INPUT_COMMAND_SAVE_IDS, binding.command_id, -1)
		if input_index < 0 || command_index < 0 do return options, false
		mapping.gameplay_buttons[Controller_Button(input_index)] = Input_Command(command_index)
	}
	for binding in payload.trigger_bindings {
		input_index := persistence_string_enum(CONTROLLER_TRIGGER_SAVE_IDS, binding.input_id, -1)
		command_index := persistence_string_enum(INPUT_COMMAND_SAVE_IDS, binding.command_id, -1)
		if input_index < 0 || command_index < 0 do return options, false
		mapping.triggers[Controller_Trigger(input_index)] = Input_Command(command_index)
	}
	options.gamepad_mapping = mapping
	options_normalize(&options, hell_unlocked)
	return options, true
}

legacy_options_default :: proc() -> Legacy_Options_File_V1 {
	options := options_default()
	return {
		schema_version=LEGACY_OPTIONS_SCHEMA_VERSION,
		fullscreen=options.fullscreen,
		frame_rate_cap=options.frame_rate_cap,
		view_zoom=options.view_zoom,
		difficulty=options.difficulty,
		hell_unlocked=false,
		controller_enabled=options.controller_enabled,
		gamepad_mapping=options.gamepad_mapping,
		audio_enabled=options.audio_enabled,
		lighting_enabled=options.lighting_enabled,
		mist_enabled=options.mist_enabled,
		minimap_visible=options.minimap_visible,
	}
}

persistence_encode_options :: proc(options: Options, revision: u64, written_at_utc: string) -> ([]byte, bool) {
	payload := options_payload_from_options(options)
	payload_bytes, ok := persistence_marshal(payload)
	if !ok do return nil, false
	hash_value := persistence_sha256(payload_bytes)
	delete(payload_bytes)
	if hash_value == "" do return nil, false
	defer delete(hash_value)
	document := Options_Document{
		schema_version=OPTIONS_DOCUMENT_SCHEMA_VERSION,
		game_release=VERSION,
		document_id="options",
		revision=revision,
		written_at_utc=written_at_utc,
		payload_sha256=hash_value,
		payload=payload,
	}
	return persistence_marshal(document)
}

persistence_decode_options :: proc(data: []byte, hell_unlocked := false) -> (
	options: Options,
	legacy_hell_unlocked: bool,
	revision: u64,
	status: Persistence_Decode_Status,
) {
	options = options_default()
	if !persistence_json_preflight(data, PERSISTENCE_OPTIONS_MAX_BYTES) do return options, false, 0, .Oversize
	probe: Document_Probe
	if err := json.unmarshal(data, &probe); err != nil do return options, false, 0, .Corrupt
	defer {
		delete(probe.game_release); delete(probe.document_id); delete(probe.run_id)
		delete(probe.written_at_utc); delete(probe.payload_sha256)
	}
	if probe.schema_version == LEGACY_OPTIONS_SCHEMA_VERSION && probe.document_id == "" {
		legacy := legacy_options_default()
		if err := json.unmarshal(data, &legacy); err != nil do return options, false, 0, .Corrupt
		if legacy.schema_version != LEGACY_OPTIONS_SCHEMA_VERSION do return options, false, 0, .Corrupt
		options = Options{
			fullscreen=legacy.fullscreen, frame_rate_cap=legacy.frame_rate_cap,
			view_zoom=legacy.view_zoom, difficulty=legacy.difficulty,
			controller_enabled=legacy.controller_enabled, gamepad_mapping=legacy.gamepad_mapping,
			audio_enabled=legacy.audio_enabled,
			sfx_volume=legacy.audio_enabled ? Audio_Volume.Full : Audio_Volume.Off,
			music_volume=DEFAULT_MUSIC_VOLUME,
			lighting_enabled=legacy.lighting_enabled,
			mist_enabled=legacy.mist_enabled, minimap_visible=legacy.minimap_visible,
		}
		options_normalize(&options, legacy.hell_unlocked)
		return options, legacy.hell_unlocked, 0, .Migrated
	}
	if probe.schema_version > OPTIONS_DOCUMENT_SCHEMA_VERSION do return options, false, 0, .Future
	if probe.schema_version != OPTIONS_DOCUMENT_SCHEMA_VERSION do return options, false, 0, .Corrupt
	document: Options_Document
	if err := json.unmarshal(data, &document); err != nil do return options, false, 0, .Corrupt
	defer {
		delete(document.game_release); delete(document.document_id)
		delete(document.written_at_utc); delete(document.payload_sha256)
		options_payload_destroy(&document.payload)
	}
	if document.document_id != "options" do return options, false, 0, .Corrupt
	payload_bytes, ok := persistence_marshal(document.payload)
	if !ok do return options, false, 0, .Corrupt
	computed := persistence_sha256(payload_bytes)
	delete(payload_bytes)
	defer delete(computed)
	if computed == "" || computed != document.payload_sha256 do return options, false, 0, .Corrupt
	decoded, valid := options_from_payload(&document.payload, hell_unlocked)
	if !valid do return options, false, 0, .Corrupt
	return decoded, false, document.revision, .Valid
}

chronicle_item_destroy :: proc(item: ^Chronicle_Notable_Item) {
	if item == nil do return
	delete(item.item_id)
	delete(item.display_name)
	item^ = {}
}

chronicle_record_destroy :: proc(record: ^Chronicle_Record) {
	if record == nil do return
	delete(record.run_id)
	delete(record.started_at_utc)
	delete(record.ended_at_utc)
	delete(record.cause_of_death)
	delete(record.story_faction_id)
	delete(record.story_relic_id)
	delete(record.story_ending_id)
	for i in 0 ..< clamp(record.visited_theme_count,0,len(record.visited_theme_ids)) do delete(record.visited_theme_ids[i])
	for i in 0 ..< clamp(record.defeated_boss_count,0,len(record.defeated_boss_ids)) do delete(record.defeated_boss_ids[i])
	for i in 0 ..< clamp(record.notable_count,0,len(record.notable_items)) do chronicle_item_destroy(&record.notable_items[i])
	record^ = {}
}

chronicle_record_clone :: proc(source: ^Chronicle_Record) -> Chronicle_Record {
	if source == nil do return {}
	result := source^
	result.run_id = persistence_clone_string(source.run_id)
	result.started_at_utc = persistence_clone_string(source.started_at_utc)
	result.ended_at_utc = persistence_clone_string(source.ended_at_utc)
	result.cause_of_death = persistence_clone_string(source.cause_of_death)
	result.story_faction_id = persistence_clone_string(source.story_faction_id)
	result.story_relic_id = persistence_clone_string(source.story_relic_id)
	result.story_ending_id = persistence_clone_string(source.story_ending_id)
	for i in 0 ..< result.visited_theme_count {
		result.visited_theme_ids[i] = persistence_clone_string(source.visited_theme_ids[i])
	}
	for i in 0 ..< result.defeated_boss_count {
		result.defeated_boss_ids[i] = persistence_clone_string(source.defeated_boss_ids[i])
	}
	for i in 0 ..< result.notable_count {
		result.notable_items[i].item_id = persistence_clone_string(source.notable_items[i].item_id)
		result.notable_items[i].display_name = persistence_clone_string(source.notable_items[i].display_name)
	}
	return result
}

profile_init :: proc(profile: ^Profile_State, profile_id: string) {
	if profile == nil do return
	profile^ = {}
	profile.profile_id = persistence_clone_string(profile_id)
	profile.chronicle = make([dynamic]Chronicle_Record, 0, 32)
	profile.owns_strings = true
}

profile_destroy :: proc(profile: ^Profile_State) {
	if profile == nil do return
	if profile.owns_strings {
		delete(profile.profile_id)
		for i in 0 ..< clamp(profile.discovered_ending_count,0,len(profile.discovered_endings)) do delete(profile.discovered_endings[i])
		for &record in profile.chronicle do chronicle_record_destroy(&record)
		for i in 0 ..< clamp(profile.victory_difficulty_count,0,len(profile.victory_difficulty_ids)) do delete(profile.victory_difficulty_ids[i])
		for i in 0 ..< clamp(profile.victory_archetype_count,0,len(profile.victory_archetype_ids)) do delete(profile.victory_archetype_ids[i])
		for i in 0 ..< clamp(profile.lifetime_boss_count,0,len(profile.lifetime_boss_ids)) do delete(profile.lifetime_boss_ids[i])
		for i in 0 ..< clamp(profile.story_verb_count,0,len(profile.story_verb_ids)) do delete(profile.story_verb_ids[i])
		for i in 0 ..< clamp(profile.theme_seen_count,0,len(profile.theme_ids_seen)) do delete(profile.theme_ids_seen[i])
		for i in 0 ..< clamp(profile.modifier_seen_count,0,len(profile.modifier_ids_seen)) do delete(profile.modifier_ids_seen[i])
		for i in 0 ..< clamp(profile.unique_seen_count,0,len(profile.unique_item_ids_seen)) do delete(profile.unique_item_ids_seen[i])
		for i in 0 ..< clamp(profile.granted_achievement_count,0,len(profile.granted_achievement_ids)) do delete(profile.granted_achievement_ids[i])
	}
	delete(profile.chronicle)
	profile^ = {}
}

// Bounded, deduplicating union add for the profile's stable-id string sets.
// Returns true when the id was newly added (the caller owns marking dirty).
profile_string_set_add :: proc(ids: []string, count: ^int, id: string) -> bool {
	if count == nil || id == "" do return false
	for i in 0 ..< clamp(count^,0,len(ids)) {
		if ids[i] == id do return false
	}
	if count^ < 0 || count^ >= len(ids) do return false
	ids[count^] = persistence_clone_string(id)
	count^ += 1
	return true
}

profile_string_set_contains :: proc(ids: []string, count: int, id: string) -> bool {
	if id == "" do return false
	for i in 0 ..< clamp(count,0,len(ids)) {
		if ids[i] == id do return true
	}
	return false
}

profile_unlock_hell :: proc(profile: ^Profile_State) -> bool {
	if profile == nil || profile.hell_unlocked do return false
	profile.hell_unlocked = true
	return true
}

profile_begin_run :: proc(profile: ^Profile_State, seed: u64) -> string {
	if profile != nil {
		profile.run_sequence += 1
		profile.lifetime_started += 1
		base := profile.profile_id != "" ? profile.profile_id : "local"
		return fmt.aprintf("%s-%016x-%016x", base, profile.run_sequence, seed)
	}
	return fmt.aprintf("local-%016x", seed)
}

profile_has_run :: proc(profile: ^Profile_State, run_id: string) -> bool {
	if profile == nil || run_id == "" do return false
	for record in profile.chronicle {
		if record.run_id == run_id do return true
	}
	return false
}

profile_record_ending :: proc(profile: ^Profile_State, ending_id: string) {
	if profile == nil || ending_id == "" do return
	for i in 0 ..< profile.discovered_ending_count {
		if profile.discovered_endings[i] == ending_id do return
	}
	if profile.discovered_ending_count >= len(profile.discovered_endings) do return
	profile.discovered_endings[profile.discovered_ending_count] = persistence_clone_string(ending_id)
	profile.discovered_ending_count += 1
}

profile_finalize_record :: proc(profile: ^Profile_State, record: ^Chronicle_Record) -> bool {
	if profile == nil || record == nil || record.run_id == "" || profile_has_run(profile, record.run_id) do return false
	profile.lifetime_descents += 1
	profile.lifetime_kills += u64(max(0, record.kills))
	profile.best_depth = max(profile.best_depth, record.deepest_floor)
	if record.outcome == .Victory {
		profile.lifetime_victories += 1
		profile.hell_unlocked = true
	}
	profile_record_ending(profile, record.story_ending_id)
	append(&profile.chronicle, chronicle_record_clone(record))
	if len(profile.chronicle) > CHRONICLE_MAX_RECORDS {
		chronicle_record_destroy(&profile.chronicle[0])
		ordered_remove(&profile.chronicle, 0)
	}
	return true
}

// Per-run facts the achievement funnel needs beyond the Chronicle record.
// Built from the live Run at the terminal-finalization choke point.
Run_Terminal_Facts :: struct {
	outcome:        Chronicle_Outcome,
	depth:          int,
	potions_used:   int,
	elites_killed:  int,
	challenge_rooms_cleared: int,
	wall_touches:   int,
	bar_pilgrim:    bool,
	gate_verb:      Story_Choice_Verb,
	gate_verb_valid: bool,
}

run_terminal_facts :: proc(run: ^Run, outcome: Chronicle_Outcome) -> Run_Terminal_Facts {
	if run == nil do return {}
	facts := Run_Terminal_Facts{
		outcome=outcome, depth=run.depth,
		potions_used=run.potions_used, elites_killed=run.elites_killed,
		challenge_rooms_cleared=run.challenge_rooms_cleared,
		wall_touches=run.wall_touches,
		// Mirrors maybe_summon_bar_dancer's all-bars-toasted condition.
		bar_pilgrim=run.bars_visited > 0 && run.bars_toasted >= run.bars_visited,
	}
	facts.gate_verb, facts.gate_verb_valid = story_verb_from_resolution(run.story.flags.gate)
	return facts
}

// Derive the gate verb from a recorded ending slug (used when seeding v1
// profiles, where only the Chronicle record survives).
persistence_verb_from_ending_id :: proc(ending_id: string) -> (Story_Choice_Verb, bool) {
	if ending_id == "" do return {}, false
	for archetype in Archetype_Id {
		for verb in Story_Choice_Verb {
			if STORY_ENDINGS[archetype][verb].slug == ending_id do return verb, true
		}
	}
	return {}, false
}

// Fold one finished run into the lifetime aggregates. Callers gate this on
// profile_finalize_record returning true so crash-recovery re-finalization by
// run_id can never double-apply; both mutations land in the same profile write.
profile_apply_terminal_facts :: proc(profile: ^Profile_State, record: ^Chronicle_Record, facts: ^Run_Terminal_Facts) {
	if profile == nil || record == nil || facts == nil do return
	if record.outcome == .Victory {
		_ = profile_string_set_add(profile.victory_difficulty_ids[:], &profile.victory_difficulty_count, DIFFICULTY_SAVE_IDS[record.difficulty])
		_ = profile_string_set_add(profile.victory_archetype_ids[:], &profile.victory_archetype_count, ARCHETYPE_SAVE_IDS[record.archetype])
	}
	for i in 0 ..< clamp(record.defeated_boss_count,0,len(record.defeated_boss_ids)) {
		_ = profile_string_set_add(profile.lifetime_boss_ids[:], &profile.lifetime_boss_count, record.defeated_boss_ids[i])
	}
	for i in 0 ..< clamp(record.visited_theme_count,0,len(record.visited_theme_ids)) {
		_ = profile_string_set_add(profile.theme_ids_seen[:], &profile.theme_seen_count, record.visited_theme_ids[i])
	}
	_ = profile_string_set_add(profile.modifier_ids_seen[:], &profile.modifier_seen_count, MODIFIER_SAVE_IDS[record.run_modifier])
	for i in 0 ..< clamp(record.notable_count,0,len(record.notable_items)) {
		item := &record.notable_items[i]
		if item.rarity != .Unique do continue
		_ = profile_string_set_add(profile.unique_item_ids_seen[:], &profile.unique_seen_count, item.item_id)
	}
	if facts.gate_verb_valid {
		_ = profile_string_set_add(profile.story_verb_ids[:], &profile.story_verb_count, STORY_VERB_SAVE_IDS[facts.gate_verb])
	}
	profile.lifetime_secrets += u64(max(0, record.secrets_opened))
	profile.lifetime_shrines += u64(max(0, record.shrines_used))
	profile.lifetime_wall_touches += u64(max(0, facts.wall_touches))
}

// One-time v1 -> v2 seeding: rebuild what the retained Chronicle records can
// prove. Counters seeded this way under-count anything beyond the 512-record
// retention window; wall touches and per-run potion/elite facts are not
// derivable from records and start at zero. Documented in STEAM.md S2.
profile_seed_aggregates_from_chronicle :: proc(profile: ^Profile_State) {
	if profile == nil do return
	for &record in profile.chronicle {
		facts := Run_Terminal_Facts{outcome=record.outcome, depth=record.deepest_floor}
		facts.gate_verb, facts.gate_verb_valid = persistence_verb_from_ending_id(record.story_ending_id)
		profile_apply_terminal_facts(profile, &record, &facts)
	}
}

profile_achievement_granted :: proc(profile: ^Profile_State, api_id: string) -> bool {
	if profile == nil do return false
	return profile_string_set_contains(profile.granted_achievement_ids[:], profile.granted_achievement_count, api_id)
}

profile_mark_achievement_granted :: proc(profile: ^Profile_State, api_id: string) -> bool {
	if profile == nil do return false
	return profile_string_set_add(profile.granted_achievement_ids[:], &profile.granted_achievement_count, api_id)
}

profile_merge :: proc(destination: ^Profile_State, incoming: ^Profile_State) {
	if destination == nil || incoming == nil do return
	destination.hell_unlocked = destination.hell_unlocked || incoming.hell_unlocked
	destination.run_sequence = max(destination.run_sequence, incoming.run_sequence)
	destination.lifetime_started = max(destination.lifetime_started, incoming.lifetime_started)
	destination.lifetime_descents = max(destination.lifetime_descents, incoming.lifetime_descents)
	destination.lifetime_victories = max(destination.lifetime_victories, incoming.lifetime_victories)
	destination.lifetime_kills = max(destination.lifetime_kills, incoming.lifetime_kills)
	destination.best_depth = max(destination.best_depth, incoming.best_depth)
	for i in 0 ..< incoming.discovered_ending_count do profile_record_ending(destination, incoming.discovered_endings[i])
	for &record in incoming.chronicle {
		if profile_has_run(destination, record.run_id) do continue
		append(&destination.chronicle, chronicle_record_clone(&record))
	}
	for len(destination.chronicle) > CHRONICLE_MAX_RECORDS {
		chronicle_record_destroy(&destination.chronicle[0])
		ordered_remove(&destination.chronicle, 0)
	}
	for i in 0 ..< clamp(incoming.victory_difficulty_count,0,len(incoming.victory_difficulty_ids)) do _ = profile_string_set_add(destination.victory_difficulty_ids[:], &destination.victory_difficulty_count, incoming.victory_difficulty_ids[i])
	for i in 0 ..< clamp(incoming.victory_archetype_count,0,len(incoming.victory_archetype_ids)) do _ = profile_string_set_add(destination.victory_archetype_ids[:], &destination.victory_archetype_count, incoming.victory_archetype_ids[i])
	for i in 0 ..< clamp(incoming.lifetime_boss_count,0,len(incoming.lifetime_boss_ids)) do _ = profile_string_set_add(destination.lifetime_boss_ids[:], &destination.lifetime_boss_count, incoming.lifetime_boss_ids[i])
	for i in 0 ..< clamp(incoming.story_verb_count,0,len(incoming.story_verb_ids)) do _ = profile_string_set_add(destination.story_verb_ids[:], &destination.story_verb_count, incoming.story_verb_ids[i])
	for i in 0 ..< clamp(incoming.theme_seen_count,0,len(incoming.theme_ids_seen)) do _ = profile_string_set_add(destination.theme_ids_seen[:], &destination.theme_seen_count, incoming.theme_ids_seen[i])
	for i in 0 ..< clamp(incoming.modifier_seen_count,0,len(incoming.modifier_ids_seen)) do _ = profile_string_set_add(destination.modifier_ids_seen[:], &destination.modifier_seen_count, incoming.modifier_ids_seen[i])
	for i in 0 ..< clamp(incoming.unique_seen_count,0,len(incoming.unique_item_ids_seen)) do _ = profile_string_set_add(destination.unique_item_ids_seen[:], &destination.unique_seen_count, incoming.unique_item_ids_seen[i])
	for i in 0 ..< clamp(incoming.granted_achievement_count,0,len(incoming.granted_achievement_ids)) do _ = profile_string_set_add(destination.granted_achievement_ids[:], &destination.granted_achievement_count, incoming.granted_achievement_ids[i])
	destination.lifetime_secrets = max(destination.lifetime_secrets, incoming.lifetime_secrets)
	destination.lifetime_shrines = max(destination.lifetime_shrines, incoming.lifetime_shrines)
	destination.lifetime_wall_touches = max(destination.lifetime_wall_touches, incoming.lifetime_wall_touches)
}

chronicle_record_matches :: proc(record: ^Chronicle_Record, view: ^Chronicle_View_State) -> bool {
	if record == nil || view == nil do return false
	if view.outcome == .Victories && record.outcome != .Victory do return false
	if view.outcome == .Fallen && record.outcome != .Fallen do return false
	if view.archetype_filter >= 0 && int(record.archetype) != view.archetype_filter do return false
	if view.difficulty_filter >= 0 && int(record.difficulty) != view.difficulty_filter do return false
	return true
}

chronicle_filtered_count :: proc(profile: ^Profile_State, view: ^Chronicle_View_State) -> int {
	if profile == nil || view == nil do return 0
	count := 0
	for &record in profile.chronicle {
		if chronicle_record_matches(&record, view) do count += 1
	}
	return count
}

chronicle_record_at :: proc(profile: ^Profile_State, view: ^Chronicle_View_State, filtered_index: int) -> ^Chronicle_Record {
	if profile == nil || view == nil || filtered_index < 0 do return nil
	seen := 0
	for i := len(profile.chronicle)-1; i >= 0; i -= 1 {
		record := &profile.chronicle[i]
		if !chronicle_record_matches(record, view) do continue
		if seen == filtered_index do return record
		seen += 1
	}
	return nil
}

profile_payload_from_profile :: proc(profile: ^Profile_State) -> Profile_Payload {
	if profile == nil do return {}
	return {
		profile_id=profile.profile_id,
		hell_unlocked=profile.hell_unlocked,
		run_sequence=profile.run_sequence,
		lifetime_started=profile.lifetime_started,
		lifetime_descents=profile.lifetime_descents,
		lifetime_victories=profile.lifetime_victories,
		lifetime_kills=profile.lifetime_kills,
		best_depth=profile.best_depth,
		discovered_endings=profile.discovered_endings,
		discovered_ending_count=profile.discovered_ending_count,
		chronicle=profile.chronicle,
		victory_difficulty_ids=profile.victory_difficulty_ids,
		victory_difficulty_count=profile.victory_difficulty_count,
		victory_archetype_ids=profile.victory_archetype_ids,
		victory_archetype_count=profile.victory_archetype_count,
		lifetime_boss_ids=profile.lifetime_boss_ids,
		lifetime_boss_count=profile.lifetime_boss_count,
		story_verb_ids=profile.story_verb_ids,
		story_verb_count=profile.story_verb_count,
		theme_ids_seen=profile.theme_ids_seen,
		theme_seen_count=profile.theme_seen_count,
		modifier_ids_seen=profile.modifier_ids_seen,
		modifier_seen_count=profile.modifier_seen_count,
		unique_item_ids_seen=profile.unique_item_ids_seen,
		unique_seen_count=profile.unique_seen_count,
		lifetime_secrets=profile.lifetime_secrets,
		lifetime_shrines=profile.lifetime_shrines,
		lifetime_wall_touches=profile.lifetime_wall_touches,
		granted_achievement_ids=profile.granted_achievement_ids,
		granted_achievement_count=profile.granted_achievement_count,
	}
}

profile_payload_destroy :: proc(payload: ^Profile_Payload) {
	if payload == nil do return
	profile := Profile_State{
		profile_id=payload.profile_id,
		discovered_endings=payload.discovered_endings,
		discovered_ending_count=payload.discovered_ending_count,
		chronicle=payload.chronicle,
		victory_difficulty_ids=payload.victory_difficulty_ids,
		victory_difficulty_count=payload.victory_difficulty_count,
		victory_archetype_ids=payload.victory_archetype_ids,
		victory_archetype_count=payload.victory_archetype_count,
		lifetime_boss_ids=payload.lifetime_boss_ids,
		lifetime_boss_count=payload.lifetime_boss_count,
		story_verb_ids=payload.story_verb_ids,
		story_verb_count=payload.story_verb_count,
		theme_ids_seen=payload.theme_ids_seen,
		theme_seen_count=payload.theme_seen_count,
		modifier_ids_seen=payload.modifier_ids_seen,
		modifier_seen_count=payload.modifier_seen_count,
		unique_item_ids_seen=payload.unique_item_ids_seen,
		unique_seen_count=payload.unique_seen_count,
		granted_achievement_ids=payload.granted_achievement_ids,
		granted_achievement_count=payload.granted_achievement_count,
		owns_strings=true,
	}
	payload^ = {}
	profile_destroy(&profile)
}

@(private = "file")
profile_state_counts_valid :: proc(profile: ^Profile_State) -> bool {
	if profile.victory_difficulty_count < 0 || profile.victory_difficulty_count > len(profile.victory_difficulty_ids) do return false
	if profile.victory_archetype_count < 0 || profile.victory_archetype_count > len(profile.victory_archetype_ids) do return false
	if profile.lifetime_boss_count < 0 || profile.lifetime_boss_count > len(profile.lifetime_boss_ids) do return false
	if profile.story_verb_count < 0 || profile.story_verb_count > len(profile.story_verb_ids) do return false
	if profile.theme_seen_count < 0 || profile.theme_seen_count > len(profile.theme_ids_seen) do return false
	if profile.modifier_seen_count < 0 || profile.modifier_seen_count > len(profile.modifier_ids_seen) do return false
	if profile.unique_seen_count < 0 || profile.unique_seen_count > len(profile.unique_item_ids_seen) do return false
	if profile.granted_achievement_count < 0 || profile.granted_achievement_count > len(profile.granted_achievement_ids) do return false
	return true
}

persistence_encode_profile :: proc(profile: ^Profile_State, revision: u64, written_at_utc: string) -> ([]byte, bool) {
	payload := profile_payload_from_profile(profile)
	payload_bytes, ok := persistence_marshal(payload)
	if !ok do return nil, false
	hash_value := persistence_sha256(payload_bytes)
	delete(payload_bytes)
	if hash_value == "" do return nil, false
	defer delete(hash_value)
	document := Profile_Document{
		schema_version=PROFILE_DOCUMENT_SCHEMA_VERSION,
		game_release=VERSION,
		document_id=profile != nil ? profile.profile_id : "",
		revision=revision,
		written_at_utc=written_at_utc,
		payload_sha256=hash_value,
		payload=payload,
	}
	return persistence_marshal(document)
}

@(private = "file")
persistence_profile_records_valid :: proc(profile: ^Profile_State) -> bool {
	for &record in profile.chronicle {
		if record.run_id == "" || record.notable_count < 0 || record.notable_count > MAX_NOTABLE_LOOT ||
			record.visited_theme_count < 0 || record.visited_theme_count > CHRONICLE_MAX_THEMES ||
			record.defeated_boss_count < 0 || record.defeated_boss_count > CHRONICLE_MAX_BOSSES {
			return false
		}
	}
	return true
}

// Schema-1 branch: hash-verify against the retained v1 payload shape, then
// seed the v2 lifetime aggregates from the retained Chronicle records. The
// caller persists the upgraded document on a .Migrated result.
@(private = "file")
persistence_decode_profile_v1 :: proc(data: []byte) -> (Profile_State, u64, Persistence_Decode_Status) {
	document: Profile_Document_V1
	if err := json.unmarshal(data, &document); err != nil do return {}, 0, .Corrupt
	delete(document.game_release)
	delete(document.document_id)
	delete(document.written_at_utc)
	defer delete(document.payload_sha256)
	destroy_v1_payload :: proc(payload: ^Profile_Payload_V1) {
		wrapper := Profile_Payload{
			profile_id=payload.profile_id,
			discovered_endings=payload.discovered_endings,
			discovered_ending_count=payload.discovered_ending_count,
			chronicle=payload.chronicle,
		}
		payload^ = {}
		profile_payload_destroy(&wrapper)
	}
	payload_bytes, ok := persistence_marshal(document.payload)
	if !ok {
		destroy_v1_payload(&document.payload)
		return {}, 0, .Corrupt
	}
	computed := persistence_sha256(payload_bytes)
	delete(payload_bytes)
	defer delete(computed)
	if computed == "" || computed != document.payload_sha256 {
		destroy_v1_payload(&document.payload)
		return {}, 0, .Corrupt
	}
	payload := document.payload
	document.payload = {}
	if payload.profile_id == "" || payload.discovered_ending_count < 0 ||
		payload.discovered_ending_count > len(payload.discovered_endings) || len(payload.chronicle) > CHRONICLE_MAX_RECORDS {
		destroy_v1_payload(&payload)
		return {}, 0, .Corrupt
	}
	profile := Profile_State{
		profile_id=payload.profile_id,
		revision=document.revision,
		hell_unlocked=payload.hell_unlocked,
		run_sequence=payload.run_sequence,
		lifetime_started=payload.lifetime_started,
		lifetime_descents=payload.lifetime_descents,
		lifetime_victories=payload.lifetime_victories,
		lifetime_kills=payload.lifetime_kills,
		best_depth=payload.best_depth,
		discovered_endings=payload.discovered_endings,
		discovered_ending_count=payload.discovered_ending_count,
		chronicle=payload.chronicle,
		owns_strings=true,
	}
	payload = {}
	if !persistence_profile_records_valid(&profile) {
		profile_destroy(&profile)
		return {}, 0, .Corrupt
	}
	profile_seed_aggregates_from_chronicle(&profile)
	return profile, document.revision, .Migrated
}

persistence_decode_profile :: proc(data: []byte) -> (Profile_State, u64, Persistence_Decode_Status) {
	if !persistence_json_preflight(data, PERSISTENCE_PROFILE_MAX_BYTES) do return {}, 0, .Oversize
	probe: Document_Probe
	if err := json.unmarshal(data, &probe); err != nil do return {}, 0, .Corrupt
	defer {
		delete(probe.game_release); delete(probe.document_id); delete(probe.run_id)
		delete(probe.written_at_utc); delete(probe.payload_sha256)
	}
	if probe.schema_version > PROFILE_DOCUMENT_SCHEMA_VERSION do return {}, 0, .Future
	if probe.schema_version == PROFILE_DOCUMENT_SCHEMA_V1 do return persistence_decode_profile_v1(data)
	if probe.schema_version != PROFILE_DOCUMENT_SCHEMA_VERSION do return {}, 0, .Corrupt
	document: Profile_Document
	if err := json.unmarshal(data, &document); err != nil do return {}, 0, .Corrupt
	delete(document.game_release)
	delete(document.document_id)
	delete(document.written_at_utc)
	defer delete(document.payload_sha256)
	payload_bytes, ok := persistence_marshal(document.payload)
	if !ok {
		profile_payload_destroy(&document.payload)
		return {}, 0, .Corrupt
	}
	computed := persistence_sha256(payload_bytes)
	delete(payload_bytes)
	defer delete(computed)
	if computed == "" || computed != document.payload_sha256 {
		profile_payload_destroy(&document.payload)
		return {}, 0, .Corrupt
	}
	payload := document.payload
	document.payload = {}
	if payload.profile_id == "" || payload.discovered_ending_count < 0 ||
		payload.discovered_ending_count > len(payload.discovered_endings) || len(payload.chronicle) > CHRONICLE_MAX_RECORDS {
		profile_payload_destroy(&payload)
		return {}, 0, .Corrupt
	}
	profile := Profile_State{
		profile_id=payload.profile_id,
		revision=document.revision,
		hell_unlocked=payload.hell_unlocked,
		run_sequence=payload.run_sequence,
		lifetime_started=payload.lifetime_started,
		lifetime_descents=payload.lifetime_descents,
		lifetime_victories=payload.lifetime_victories,
		lifetime_kills=payload.lifetime_kills,
		best_depth=payload.best_depth,
		discovered_endings=payload.discovered_endings,
		discovered_ending_count=payload.discovered_ending_count,
		chronicle=payload.chronicle,
		victory_difficulty_ids=payload.victory_difficulty_ids,
		victory_difficulty_count=payload.victory_difficulty_count,
		victory_archetype_ids=payload.victory_archetype_ids,
		victory_archetype_count=payload.victory_archetype_count,
		lifetime_boss_ids=payload.lifetime_boss_ids,
		lifetime_boss_count=payload.lifetime_boss_count,
		story_verb_ids=payload.story_verb_ids,
		story_verb_count=payload.story_verb_count,
		theme_ids_seen=payload.theme_ids_seen,
		theme_seen_count=payload.theme_seen_count,
		modifier_ids_seen=payload.modifier_ids_seen,
		modifier_seen_count=payload.modifier_seen_count,
		unique_item_ids_seen=payload.unique_item_ids_seen,
		unique_seen_count=payload.unique_seen_count,
		lifetime_secrets=payload.lifetime_secrets,
		lifetime_shrines=payload.lifetime_shrines,
		lifetime_wall_touches=payload.lifetime_wall_touches,
		granted_achievement_ids=payload.granted_achievement_ids,
		granted_achievement_count=payload.granted_achievement_count,
		owns_strings=true,
	}
	payload = {}
	if !persistence_profile_records_valid(&profile) || !profile_state_counts_valid(&profile) {
		profile_destroy(&profile)
		return {}, 0, .Corrupt
	}
	return profile, document.revision, .Valid
}

run_allocate_save_entity_id :: proc(run:^Run)->u64 {
	if run==nil do return 0
	run.next_save_entity_id+=1
	if run.next_save_entity_id==0 do run.next_save_entity_id=1
	return run.next_save_entity_id
}

run_ensure_persisted_entity_ids :: proc(run:^Run) {
	if run==nil do return
	for &projectile in run.projectiles {if projectile.entity_id==0 do projectile.entity_id=run_allocate_save_entity_id(run)}
	for &bell in run.bells {if bell.entity_id==0 do bell.entity_id=run_allocate_save_entity_id(run)}
	for &ground in run.ground_items {if ground.entity_id==0 do ground.entity_id=run_allocate_save_entity_id(run)}
	for &trap in run.traps {if trap.entity_id==0 do trap.entity_id=run_allocate_save_entity_id(run)}
	for &shrine in run.shrines {if shrine.entity_id==0 do shrine.entity_id=run_allocate_save_entity_id(run)}
	for &secret in run.secrets {if secret.entity_id==0 do secret.entity_id=run_allocate_save_entity_id(run)}
	for &guest in run.story_runtime.guests {if guest.entity_id==0 do guest.entity_id=run_allocate_save_entity_id(run)}
	if run.story_runtime.soul.present&&run.story_runtime.soul.entity_id==0 do run.story_runtime.soul.entity_id=run_allocate_save_entity_id(run)
}

run_save_payload_from_app :: proc(app: ^App) -> Run_Save_Payload {
	if app == nil do return {}
	run := &app.run
	story_runtime := run.story_runtime
	story_runtime.guidance_path = nil // derived navigation output
	panel := app.story_panel
	panel.text = {}
	panel.text_len = 0
	return {
		active_ticks=run.active_ticks,
		started_at_utc=run.started_at_utc,
		ended_at_utc=run.ended_at_utc,
		terminal=run.terminal,
		finalization=run.finalization,
		seed=run.seed, depth=run.depth, difficulty=run.difficulty,
		dungeon=run.dungeon, player=run.player,
		enemies=run.enemies, next_enemy_id=run.next_enemy_id,
		next_familiar_id=run.next_familiar_id, next_save_entity_id=run.next_save_entity_id,
		storm_cast_counter=run.storm_cast_counter,
		floor_epoch=run.floor_epoch, projectiles=run.projectiles, familiars=run.familiars,
		bells=run.bells, ground_items=run.ground_items,
		shopkeeper=run.shopkeeper, has_shopkeeper=run.has_shopkeeper,
		ambient_residents=run.ambient_residents, refuge=run.refuge,
		shop_requested=run.shop_requested, loot_rng=run.loot_rng, combat_rng=run.combat_rng,
		dark_floor=run.dark_floor, theme_index=run.theme_index, explored=run.explored,
		boss_engaged=run.boss_engaged, sealed=run.sealed, tyrant_dead=run.tyrant_dead,
		victory=run.victory, kills=run.kills, modifier=run.modifier, plan=run.plan,
		story=run.story, story_runtime=story_runtime, story_panel=panel,
		story_minigame=app.story_minigame, story_minigame_cursor=app.story_minigame_cursor,
		bars_visited=run.bars_visited, bars_toasted=run.bars_toasted,
		challenge_rooms_cleared=run.challenge_rooms_cleared,
		traps=run.traps, shrines=run.shrines, secrets=run.secrets,
		traps_triggered=run.traps_triggered, shrines_used=run.shrines_used,
		secrets_opened=run.secrets_opened, notable_loot=run.notable_loot,
		notable_count=run.notable_count, visited_themes=run.visited_themes,
		defeated_bosses=run.defeated_bosses, last_damage_source=run.last_damage_source,
		wall_touches=run.wall_touches,
		potions_used=run.potions_used, elites_killed=run.elites_killed,
	}
}

@(private = "file")
run_snapshot_clone_item :: proc(source: Item, allocator := context.allocator) -> Item {
	result := source
	result.name = persistence_clone_string(source.name, allocator)
	result.icon = persistence_clone_string(source.icon, allocator)
	return result
}

@(private = "file")
run_snapshot_clone_story :: proc(source: ^Story_State, allocator := context.allocator) -> Story_State {
	if source == nil do return {}
	result := source^
	result.title = persistence_clone_string(source.title, allocator)
	result.player_backstory = persistence_clone_string(source.player_backstory, allocator)
	result.objective = persistence_clone_string(source.objective, allocator)
	result.antagonist = persistence_clone_string(source.antagonist, allocator)
	for i in 0 ..< STORY_BEAT_COUNT {
		source_beat := &source.beats[i]
		beat := &result.beats[i]
		beat.guest_name = persistence_clone_string(source_beat.guest_name, allocator)
		beat.guest_motive = persistence_clone_string(source_beat.guest_motive, allocator)
		beat.dialogue = persistence_clone_string(source_beat.dialogue, allocator)
		beat.outcome = persistence_clone_string(source_beat.outcome, allocator)
		beat.summary = persistence_clone_string(source_beat.summary, allocator)
		for verb in Story_Choice_Verb {
			beat.choices[verb].label = persistence_clone_string(source_beat.choices[verb].label, allocator)
			beat.choices[verb].intent = persistence_clone_string(source_beat.choices[verb].intent, allocator)
			beat.choices[verb].outcome = persistence_clone_string(source_beat.choices[verb].outcome, allocator)
		}
	}
	for i in 0 ..< source.log.count do result.log.entries[i] = persistence_clone_string(source.log.entries[i], allocator)
	return result
}

// Capture only authoritative continuation state. Every slice and non-empty
// string in the returned payload is independently owned, so a save worker can
// validate and encode it without observing later simulation mutations.
run_save_payload_clone_from_app :: proc(app: ^App, allocator := context.allocator) -> Run_Save_Payload {
	if app == nil do return {}
	source := &app.run
	payload := run_save_payload_from_app(app)
	payload.started_at_utc = persistence_clone_string(source.started_at_utc, allocator)
	payload.ended_at_utc = persistence_clone_string(source.ended_at_utc, allocator)

	payload.player.weapon = run_snapshot_clone_item(source.player.weapon, allocator)
	payload.player.armor = run_snapshot_clone_item(source.player.armor, allocator)
	for i in 0 ..< BAG_CAPACITY do payload.player.bag[i] = run_snapshot_clone_item(source.player.bag[i], allocator)

	payload.enemies = make([dynamic]Enemy, len(source.enemies), len(source.enemies), allocator)
	copy(payload.enemies[:], source.enemies[:])
	for &enemy in payload.enemies do enemy.name = persistence_clone_string(enemy.name, allocator)
	payload.projectiles = make([dynamic]Projectile, len(source.projectiles), len(source.projectiles), allocator)
	copy(payload.projectiles[:], source.projectiles[:])
	payload.familiars = make([dynamic]Familiar, len(source.familiars), len(source.familiars), allocator)
	copy(payload.familiars[:], source.familiars[:])
	payload.bells = make([dynamic]Ambush_Bell, len(source.bells), len(source.bells), allocator)
	copy(payload.bells[:], source.bells[:])
	payload.ground_items = make([dynamic]Ground_Item, len(source.ground_items), len(source.ground_items), allocator)
	copy(payload.ground_items[:], source.ground_items[:])
	for &ground in payload.ground_items do ground.item = run_snapshot_clone_item(ground.item, allocator)
	payload.sealed = make([dynamic]Sealed_Tile, len(source.sealed), len(source.sealed), allocator)
	copy(payload.sealed[:], source.sealed[:])
	payload.traps = make([dynamic]Trap, len(source.traps), len(source.traps), allocator)
	copy(payload.traps[:], source.traps[:])
	payload.shrines = make([dynamic]Shrine, len(source.shrines), len(source.shrines), allocator)
	copy(payload.shrines[:], source.shrines[:])
	payload.secrets = make([dynamic]Secret, len(source.secrets), len(source.secrets), allocator)
	copy(payload.secrets[:], source.secrets[:])

	payload.shopkeeper.name = persistence_clone_string(source.shopkeeper.name, allocator)
	payload.shopkeeper.role = persistence_clone_string(source.shopkeeper.role, allocator)
	for i in 0 ..< SHOP_STOCK_CAPACITY do payload.shopkeeper.stock[i] = run_snapshot_clone_item(source.shopkeeper.stock[i], allocator)
	for i in 0 ..< DUNGEON_DEPTH {
		for risk in 0 ..< MAX_RISK_TAGS do payload.plan[i].risk_tags[risk] = persistence_clone_string(source.plan[i].risk_tags[risk], allocator)
		payload.plan[i].reward_hint = persistence_clone_string(source.plan[i].reward_hint, allocator)
	}

	payload.story = run_snapshot_clone_story(&source.story, allocator)
	payload.story_runtime.guests = make([dynamic]Story_Guest, len(source.story_runtime.guests), len(source.story_runtime.guests), allocator)
	copy(payload.story_runtime.guests[:], source.story_runtime.guests[:])
	for &guest in payload.story_runtime.guests {
		guest.name = persistence_clone_string(guest.name, allocator)
		guest.motive = persistence_clone_string(guest.motive, allocator)
		guest.dialogue = persistence_clone_string(guest.dialogue, allocator)
	}
	payload.story_runtime.guidance_path = nil
	for i in 0 ..< MAX_NOTABLE_LOOT {
		payload.notable_loot[i].item_id = persistence_clone_string(source.notable_loot[i].item_id, allocator)
		payload.notable_loot[i].name = persistence_clone_string(source.notable_loot[i].name, allocator)
	}
	payload.last_damage_source = persistence_clone_string(source.last_damage_source, allocator)
	return payload
}

run_save_payload_destroy :: proc(payload: ^Run_Save_Payload, allocator := context.allocator) {
	if payload == nil do return
	// Reuse the decoded-run ownership registry so this stays paired with every
	// string-bearing field as the save schema evolves.
	run, _, _, _ := run_take_payload(payload, allocator)
	run_destroy(&run, allocator)
}

persistence_encode_run_payload :: proc(payload: ^Run_Save_Payload, run_id: string, revision: u64, written_at_utc: string) -> ([]byte, bool) {
	if payload == nil || run_id == "" || !run_payload_validate(payload) do return nil, false
	payload_bytes, ok := persistence_marshal(payload^)
	if !ok do return nil, false
	hash_value := persistence_sha256(payload_bytes)
	delete(payload_bytes)
	if hash_value == "" do return nil, false
	defer delete(hash_value)
	document := Run_Document{
		schema_version=RUN_DOCUMENT_SCHEMA_VERSION,
		game_release=VERSION,
		document_id=run_id,
		run_id=run_id,
		revision=revision,
		written_at_utc=written_at_utc,
		payload_sha256=hash_value,
		payload=payload^,
	}
	return persistence_marshal(document)
}

persistence_encode_run :: proc(app: ^App, revision: u64, written_at_utc: string) -> ([]byte, bool) {
	if app == nil || app.run.run_id == "" do return nil, false
	run_ensure_persisted_entity_ids(&app.run)
	payload := run_save_payload_from_app(app)
	return persistence_encode_run_payload(&payload, app.run.run_id, revision, written_at_utc)
}

run_payload_validate :: proc(payload: ^Run_Save_Payload) -> bool {
	if payload == nil do return false
	if payload.depth < 1 || payload.depth > DUNGEON_DEPTH do return false
	if !difficulty_is_valid(payload.difficulty) do return false
	if int(payload.player.archetype) < 0 || int(payload.player.archetype) >= len(Archetype_Id) do return false
	if payload.theme_index < 0 || payload.theme_index >= len(THEMES) do return false
	if payload.dungeon.room_count < 0 || payload.dungeon.room_count > MAX_ROOMS_CAP do return false
	if payload.dungeon.special_room_count < 0 || payload.dungeon.special_room_count > MAX_SPECIAL_ROOMS do return false
	if len(payload.enemies) > 512 || len(payload.projectiles) > 512 || len(payload.familiars) > 64 ||
		len(payload.bells) > 64 || len(payload.ground_items) > 512 || len(payload.sealed) > MAP_W*MAP_H ||
		len(payload.traps) > 512 || len(payload.shrines) > 128 || len(payload.secrets) > 128 ||
		len(payload.story_runtime.guests) > STORY_BEAT_COUNT*2 {
		return false
	}
	if payload.notable_count < 0 || payload.notable_count > MAX_NOTABLE_LOOT do return false
	if payload.potions_used < 0 || payload.elites_killed < 0 do return false
	if payload.player.bag_count < 0 || payload.player.bag_count > BAG_CAPACITY do return false
	if payload.shopkeeper.stock_count < 0 || payload.shopkeeper.stock_count > SHOP_STOCK_CAPACITY do return false
	if payload.story.log.count<0||payload.story.log.count>STORY_LOG_CAP do return false
	for floor in payload.plan {if floor.risk_count<0||floor.risk_count>len(floor.risk_tags) do return false}
	if math.is_nan(payload.player.pos.x) || math.is_nan(payload.player.pos.y) ||
		math.is_inf(payload.player.pos.x) || math.is_inf(payload.player.pos.y) {
		return false
	}
	for i in 0 ..< len(payload.enemies) {
		enemy := &payload.enemies[i]
		if enemy.entity_id == 0 || math.is_nan(enemy.pos.x) || math.is_nan(enemy.pos.y) do return false
		for j in i+1 ..< len(payload.enemies) {
			if payload.enemies[j].entity_id == enemy.entity_id do return false
		}
	}
	max_save_id:u64
	for entity in payload.projectiles {if entity.entity_id==0 do return false;max_save_id=max(max_save_id,entity.entity_id)}
	for entity in payload.bells {if entity.entity_id==0 do return false;max_save_id=max(max_save_id,entity.entity_id)}
	for entity in payload.ground_items {if entity.entity_id==0 do return false;max_save_id=max(max_save_id,entity.entity_id)}
	for entity in payload.traps {if entity.entity_id==0 do return false;max_save_id=max(max_save_id,entity.entity_id)}
	for entity in payload.shrines {if entity.entity_id==0 do return false;max_save_id=max(max_save_id,entity.entity_id)}
	for entity in payload.secrets {if entity.entity_id==0 do return false;max_save_id=max(max_save_id,entity.entity_id)}
	for entity in payload.story_runtime.guests {if entity.entity_id==0 do return false;max_save_id=max(max_save_id,entity.entity_id)}
	if payload.story_runtime.soul.present {if payload.story_runtime.soul.entity_id==0 do return false;max_save_id=max(max_save_id,payload.story_runtime.soul.entity_id)}
	if payload.next_save_entity_id<max_save_id do return false
	return true
}

run_adopt_string :: proc(run: ^Run, value: string) {
	if run == nil || value == "" do return
	append(&run.save_owned_strings, value)
}

run_adopt_item_strings :: proc(run: ^Run, item: ^Item) {
	if run == nil || item == nil do return
	run_adopt_string(run, item.name)
	run_adopt_string(run, item.icon)
}

run_adopt_decoded_strings :: proc(run: ^Run, allocator := context.allocator) {
	if run == nil do return
	run.save_owned_strings = make([dynamic]string, 0, 128, allocator)
	run_adopt_item_strings(run, &run.player.weapon)
	run_adopt_item_strings(run, &run.player.armor)
	for i in 0 ..< clamp(run.player.bag_count,0,len(run.player.bag)) do run_adopt_item_strings(run, &run.player.bag[i])
	for &enemy in run.enemies do run_adopt_string(run, enemy.name)
	for &ground in run.ground_items do run_adopt_item_strings(run, &ground.item)
	run_adopt_string(run, run.shopkeeper.name)
	run_adopt_string(run, run.shopkeeper.role)
	for i in 0 ..< clamp(run.shopkeeper.stock_count,0,len(run.shopkeeper.stock)) do run_adopt_item_strings(run, &run.shopkeeper.stock[i])
	for &floor in run.plan {
		for i in 0 ..< clamp(floor.risk_count,0,len(floor.risk_tags)) do run_adopt_string(run, floor.risk_tags[i])
		run_adopt_string(run, floor.reward_hint)
	}
	for &beat in run.story.beats {
		run_adopt_string(run, beat.guest_name)
		run_adopt_string(run, beat.guest_motive)
		run_adopt_string(run, beat.dialogue)
		for &choice in beat.choices {
			run_adopt_string(run, choice.label)
			run_adopt_string(run, choice.intent)
			run_adopt_string(run, choice.outcome)
		}
		if !beat.outcome_owned do run_adopt_string(run, beat.outcome)
	}
	run_adopt_string(run, run.story.antagonist)
	for &guest in run.story_runtime.guests {
		run_adopt_string(run, guest.name)
		run_adopt_string(run, guest.motive)
		run_adopt_string(run, guest.dialogue)
	}
	for i in 0 ..< clamp(run.notable_count,0,len(run.notable_loot)) {
		run_adopt_string(run, run.notable_loot[i].item_id)
		run_adopt_string(run, run.notable_loot[i].name)
	}
	run_adopt_string(run, run.last_damage_source)
}

run_take_payload :: proc(payload: ^Run_Save_Payload, allocator := context.allocator) -> (run: Run, panel: Story_Panel_State, minigame: Story_Minigame_State, cursor: int) {
	if payload == nil do return
	run = Run{
		active_ticks=payload.active_ticks, started_at_utc=payload.started_at_utc,
		ended_at_utc=payload.ended_at_utc, terminal=payload.terminal,
		finalization=payload.finalization, seed=payload.seed, depth=payload.depth,
		difficulty=payload.difficulty, dungeon=payload.dungeon, player=payload.player,
		enemies=payload.enemies, next_enemy_id=payload.next_enemy_id,
		next_familiar_id=payload.next_familiar_id, next_save_entity_id=payload.next_save_entity_id,
		storm_cast_counter=payload.storm_cast_counter,
		floor_epoch=payload.floor_epoch, projectiles=payload.projectiles,
		familiars=payload.familiars, bells=payload.bells, ground_items=payload.ground_items,
		shopkeeper=payload.shopkeeper, has_shopkeeper=payload.has_shopkeeper,
		ambient_residents=payload.ambient_residents, refuge=payload.refuge,
		shop_requested=payload.shop_requested, loot_rng=payload.loot_rng,
		combat_rng=payload.combat_rng, dark_floor=payload.dark_floor,
		theme_index=payload.theme_index, explored=payload.explored,
		boss_engaged=payload.boss_engaged, sealed=payload.sealed,
		tyrant_dead=payload.tyrant_dead, victory=payload.victory, kills=payload.kills,
		modifier=payload.modifier, plan=payload.plan, story=payload.story,
		story_runtime=payload.story_runtime, bars_visited=payload.bars_visited,
		bars_toasted=payload.bars_toasted,
		challenge_rooms_cleared=payload.challenge_rooms_cleared,
		traps=payload.traps, shrines=payload.shrines, secrets=payload.secrets,
		traps_triggered=payload.traps_triggered, shrines_used=payload.shrines_used,
		secrets_opened=payload.secrets_opened, notable_loot=payload.notable_loot,
		notable_count=payload.notable_count, visited_themes=payload.visited_themes,
		defeated_bosses=payload.defeated_bosses,
		last_damage_source=payload.last_damage_source, wall_touches=payload.wall_touches,
		potions_used=payload.potions_used, elites_killed=payload.elites_killed,
	}
	panel = payload.story_panel
	minigame = payload.story_minigame
	cursor = payload.story_minigame_cursor
	payload^ = {}
	run_adopt_decoded_strings(&run, allocator)
	return
}

run_document_destroy :: proc(document: ^Run_Document) {
	if document == nil do return
	delete(document.game_release)
	delete(document.document_id)
	delete(document.run_id)
	delete(document.written_at_utc)
	delete(document.payload_sha256)
	if document.payload.started_at_utc != "" || document.payload.enemies != nil || document.payload.story.title != "" {
		run, _, _, _ := run_take_payload(&document.payload)
		run_destroy(&run)
	}
	document^ = {}
}

// Schema-1 branch: the stored hash covers the v1 payload marshal, so verify
// against the retained v1 shape before converting. Conversion moves ownership;
// the returned document is a normal v2 document with the new counters zeroed.
@(private = "file")
persistence_decode_run_v1 :: proc(data: []byte) -> (Run_Document, Persistence_Decode_Status) {
	v1: Run_Document_V1
	if err := json.unmarshal(data, &v1); err != nil do return {}, .Corrupt
	document := Run_Document{
		schema_version=RUN_DOCUMENT_SCHEMA_VERSION,
		game_release=v1.game_release,
		document_id=v1.document_id,
		run_id=v1.run_id,
		revision=v1.revision,
		written_at_utc=v1.written_at_utc,
		payload_sha256=v1.payload_sha256,
	}
	payload_bytes, ok := persistence_marshal(v1.payload)
	document.payload = run_payload_from_v1(&v1.payload)
	if !ok {
		run_document_destroy(&document)
		return {}, .Corrupt
	}
	computed := persistence_sha256(payload_bytes)
	delete(payload_bytes)
	defer delete(computed)
	if computed == "" || computed != document.payload_sha256 ||
		document.run_id == "" || document.run_id != document.document_id ||
		!run_payload_validate(&document.payload) {
		run_document_destroy(&document)
		return {}, .Corrupt
	}
	return document, .Migrated
}

persistence_decode_run :: proc(data: []byte) -> (Run_Document, Persistence_Decode_Status) {
	if !persistence_json_preflight(data, PERSISTENCE_RUN_MAX_BYTES) do return {}, .Oversize
	probe: Document_Probe
	if err := json.unmarshal(data, &probe); err != nil do return {}, .Corrupt
	defer {
		delete(probe.game_release); delete(probe.document_id); delete(probe.run_id)
		delete(probe.written_at_utc); delete(probe.payload_sha256)
	}
	if probe.schema_version > RUN_DOCUMENT_SCHEMA_VERSION do return {}, .Future
	if probe.schema_version == RUN_DOCUMENT_SCHEMA_V1 do return persistence_decode_run_v1(data)
	if probe.schema_version != RUN_DOCUMENT_SCHEMA_VERSION do return {}, .Corrupt
	document: Run_Document
	if err := json.unmarshal(data, &document); err != nil do return {}, .Corrupt
	if document.run_id == "" || document.run_id != document.document_id || !run_payload_validate(&document.payload) {
		run_document_destroy(&document)
		return {}, .Corrupt
	}
	payload_bytes, ok := persistence_marshal(document.payload)
	if !ok {
		run_document_destroy(&document)
		return {}, .Corrupt
	}
	computed := persistence_sha256(payload_bytes)
	delete(payload_bytes)
	if computed == "" || computed != document.payload_sha256 {
		delete(computed)
		run_document_destroy(&document)
		return {}, .Corrupt
	}
	delete(computed)
	return document, .Valid
}

app_install_run_document :: proc(app: ^App, document: ^Run_Document) -> bool {
	if app == nil || document == nil || document.run_id == "" || !run_payload_validate(&document.payload) do return false
	temporary, panel, minigame, cursor := run_take_payload(&document.payload)
	temporary.run_id = document.run_id
	document.run_id = ""
	temporary.revision = document.revision
	// Reconstruct presentation and derived gameplay queries from authoritative state.
	temporary.player.prev_pos = temporary.player.pos
	temporary.player.moving = false
	temporary.player.anim_time = 0
	temporary.player.hit_flash = 0
	temporary.player.hit_flash_duration = 0
	for &enemy in temporary.enemies {
		enemy.prev_pos = enemy.pos
		enemy.anim_time = 0
		enemy.hit_flash = 0
		enemy.hit_flash_duration = 0
		enemy.moving = false
	}
	for &projectile in temporary.projectiles {
		projectile.prev_pos = projectile.pos
		projectile.visual_age = 0
	}
	for &familiar in temporary.familiars {
		familiar.prev_pos = familiar.pos
		familiar.anim_time = 0
		familiar.moving = false
	}
	for &resident in temporary.ambient_residents.items do resident.prev_pos = resident.pos
	temporary.shopkeeper.prev_pos = temporary.shopkeeper.pos
	for &guest in temporary.story_runtime.guests do guest.prev_pos = guest.pos
	temporary.story_runtime.soul.prev_pos = temporary.story_runtime.soul.pos
	temporary.visible = {}
	temporary.nav = {}
	temporary.numbers = nil
	temporary.sfx = nil
	temporary.feel = nil
	temporary.story_runtime.guidance_path = nil
	refresh_visibility(&temporary)
	story_refresh_relic_guidance(&temporary)
	old := app.run
	app.run = temporary
	temporary = {}
	run_destroy(&old)
	app.story_panel = panel
	app.story_minigame = minigame
	app.story_minigame_cursor = cursor
	app_reset_run_ui_after_restore(app)
	return true
}

chronicle_record_from_run :: proc(run: ^Run, outcome: Chronicle_Outcome) -> Chronicle_Record {
	if run == nil do return {}
	record := Chronicle_Record{
		record_schema_version=CHRONICLE_RECORD_SCHEMA_VERSION,
		run_id=persistence_clone_string(run.run_id), outcome=outcome,
		archetype=run.player.archetype, difficulty=run.difficulty, seed=run.seed,
		deepest_floor=run.depth, started_at_utc=persistence_clone_string(run.started_at_utc),
		ended_at_utc=persistence_clone_string(run.ended_at_utc), active_ticks=run.active_ticks,
		final_level=run.player.level, kills=run.kills,
		traps_triggered=run.traps_triggered, shrines_used=run.shrines_used,
		secrets_opened=run.secrets_opened, bars_visited=run.bars_visited,
		bars_toasted=run.bars_toasted, challenge_rooms_cleared=run.challenge_rooms_cleared,
		run_modifier=run.modifier,
	}
	if outcome == .Fallen do record.cause_of_death = persistence_clone_string(run.last_damage_source)
	for visited, theme in run.visited_themes {
		if !visited || record.visited_theme_count >= CHRONICLE_MAX_THEMES do continue
		record.visited_theme_ids[record.visited_theme_count] = persistence_clone_string(THEME_SAVE_IDS[theme])
		record.visited_theme_count += 1
	}
	for boss in Boss_Id {
		if !run.defeated_bosses[boss] do continue
		record.defeated_boss_ids[record.defeated_boss_count] = persistence_clone_string(BOSS_SAVE_IDS[boss])
		record.defeated_boss_count += 1
	}
	for i in 0 ..< run.notable_count {
		notable := run.notable_loot[i]
		record.notable_items[i] = {
			item_id=persistence_clone_string(notable.item_id),
			display_name=persistence_clone_string(notable.name),
			rarity=notable.rarity,
		}
		record.notable_count += 1
	}
	if run.story_runtime.initialized {
		record.story_faction_id = fmt.aprintf("%v", run.story.faction)
		record.story_relic_id = fmt.aprintf("%v", run.story.relic)
		if outcome == .Victory {
			ending := story_resolve_recorded_ending(&run.story)
			if ending.valid do record.story_ending_id = persistence_clone_string(ending.ending.slug)
			story_ending_result_destroy(&ending)
		}
	}
	return record
}

persistence_document_probe :: proc(kind: Persistence_Document_Kind, data: []byte) -> (revision: u64, identity: string, status: Persistence_Decode_Status) {
	switch kind {
	case .Options:
		_, _, revision, status = persistence_decode_options(data)
		return revision, persistence_clone_string("options"), status
	case .Profile:
		profile, rev, decoded := persistence_decode_profile(data)
		if decoded == .Valid || decoded == .Migrated {
			identity = persistence_clone_string(profile.profile_id)
		}
		profile_destroy(&profile)
		return rev, identity, decoded
	case .Run:
		document, decoded := persistence_decode_run(data)
		if decoded == .Valid || decoded == .Migrated {
			revision = document.revision
			identity = persistence_clone_string(document.run_id)
		}
		run_document_destroy(&document)
		return revision, identity, decoded
	}
	return 0, "", .Corrupt
}

package archrogue

// Canonical committed asset loading. Optional manifest-backed packs degrade to
// placeholder rendering when unavailable so the game and headless tests remain
// robust, while static UI metadata stays type-checked in this package.

import "core:c"
import "core:encoding/json"
import "core:fmt"
import "core:mem"
import rl "../vendor/raylib"

Clip_Kind :: enum {
	Idle,
	Walk,
	Attack,
	Cast,
	Die,
	Dead,
	Pet,
	Dance,
	Preview_Idle,
}

CLIP_NAMES :: [Clip_Kind]string{
	.Idle = "idle",
	.Walk = "walk",
	.Attack = "attack",
	.Cast = "cast",
	.Die = "die",
	.Dead = "dead",
	.Pet = "pet",
	.Dance = "dance",
	.Preview_Idle = "preview_idle",
}

Actor_Clip :: struct {
	tex:    rl.Texture2D,
	frames: int,
	fps:    f32,
	loop:   bool,
	valid:  bool,
}

Actor_Sprites :: struct {
	cell:         int, // native PixelLab source-cell size; never import-resampled
	canvas_world: f32, // world px the square cell renders at
	anchor:       Vec2, // feet position as fraction of the cell
	clips:        [Clip_Kind]Actor_Clip,
	loaded:       bool,
}

ACTION_SLOT_COUNT :: 6

// Typed keys for the committed action-bar pack. `.Invalid` is the deliberate
// zero value: missing manifests/textures leave a harmless invalid asset for the
// renderer's procedural fallback instead of aliasing a real icon.
Action_Icon :: enum {
	Invalid,
	Slot_Frame,
	Warden_Bulwark_Slam,
	Warden_Guard_Bolt,
	Warden_Time_Skip,
	Warden_Guard_Step,
	Rogue_Killing_Blow,
	Rogue_Knife_Fan,
	Rogue_Ambush_Bell,
	Rogue_Shadow_Dash,
	Arcanist_Force_Slam,
	Arcanist_Arc_Bolt,
	Arcanist_Frost_Nova,
	Arcanist_Blink,
	Acolyte_Blood_Reap,
	Acolyte_Spirit_Bolt,
	Acolyte_Spirit_Call,
	Acolyte_Dark_Step,
	Ranger_Pinning_Strike,
	Ranger_Multishot,
	Ranger_Spirit_Beast,
	Ranger_Spirit_Beast_Angry,
	Ranger_Vault,
	Health_Potion,
	Mana_Potion,
}

@(rodata)
ACTION_ICON_KEYS := [Action_Icon]string{
	.Invalid                     = "",
	.Slot_Frame                  = "hud.action_slot",
	.Warden_Bulwark_Slam         = "hud.action.warden.bulwark_slam",
	.Warden_Guard_Bolt           = "hud.action.warden.guard_bolt",
	.Warden_Time_Skip            = "hud.action.warden.time_skip",
	.Warden_Guard_Step           = "hud.action.warden.guard_step",
	.Rogue_Killing_Blow          = "hud.action.rogue.killing_blow",
	.Rogue_Knife_Fan             = "hud.action.rogue.knife_fan",
	.Rogue_Ambush_Bell           = "hud.action.rogue.ambush_bell",
	.Rogue_Shadow_Dash           = "hud.action.rogue.shadow_dash",
	.Arcanist_Force_Slam         = "hud.action.arcanist.force_slam",
	.Arcanist_Arc_Bolt           = "hud.action.arcanist.arc_bolt",
	.Arcanist_Frost_Nova         = "hud.action.arcanist.frost_nova",
	.Arcanist_Blink              = "hud.action.arcanist.blink",
	.Acolyte_Blood_Reap          = "hud.action.acolyte.blood_reap",
	.Acolyte_Spirit_Bolt         = "hud.action.acolyte.spirit_bolt",
	.Acolyte_Spirit_Call         = "hud.action.acolyte.spirit_call",
	.Acolyte_Dark_Step           = "hud.action.acolyte.dark_step",
	.Ranger_Pinning_Strike       = "hud.action.ranger.pinning_strike",
	.Ranger_Multishot            = "hud.action.ranger.multishot",
	.Ranger_Spirit_Beast         = "hud.action.ranger.spirit_beast",
	.Ranger_Spirit_Beast_Angry   = "hud.action.ranger.spirit_beast_angry",
	.Ranger_Vault                = "hud.action.ranger.vault",
	.Health_Potion               = "hud.action.health_potion",
	.Mana_Potion                 = "hud.action.mana_potion",
}

@(rodata)
DEFAULT_ACTION_LOADOUTS := [Archetype_Id][ACTION_SLOT_COUNT]Action_Icon{
	.Warden = {
		.Warden_Bulwark_Slam, .Warden_Guard_Bolt, .Warden_Time_Skip,
		.Warden_Guard_Step, .Health_Potion, .Mana_Potion,
	},
	.Rogue = {
		.Rogue_Killing_Blow, .Rogue_Knife_Fan, .Rogue_Ambush_Bell,
		.Rogue_Shadow_Dash, .Health_Potion, .Mana_Potion,
	},
	.Arcanist = {
		.Arcanist_Force_Slam, .Arcanist_Arc_Bolt, .Arcanist_Frost_Nova,
		.Arcanist_Blink, .Health_Potion, .Mana_Potion,
	},
	.Acolyte = {
		.Acolyte_Blood_Reap, .Acolyte_Spirit_Bolt, .Acolyte_Spirit_Call,
		.Acolyte_Dark_Step, .Health_Potion, .Mana_Potion,
	},
	.Ranger = {
		.Ranger_Pinning_Strike, .Ranger_Multishot, .Ranger_Spirit_Beast,
		.Ranger_Vault, .Health_Potion, .Mana_Potion,
	},
}

Action_Icon_Asset :: struct {
	tex:    rl.Texture2D,
	size:   [2]int,
	valid:  bool,
}

Mobile_Hud_Asset_Id :: enum u8 {
	Joystick_Base,
	Joystick_Knob,
	Status_Bar_Frame,
}

MOBILE_HUD_ASSET_COUNT :: 3

Mobile_Hud_Asset_Def :: struct {
	file: string,
	size: [2]int,
}

@(rodata)
MOBILE_HUD_ASSET_DEFS := [Mobile_Hud_Asset_Id]Mobile_Hud_Asset_Def{
	.Joystick_Base = {file = "mobile_joystick_base.png", size = {256, 256}},
	.Joystick_Knob = {file = "mobile_joystick_knob.png", size = {192, 192}},
	.Status_Bar_Frame = {file = "mobile_status_bar_frame.png", size = {98, 455}},
}

Mobile_Hud_Asset :: struct {
	tex:   rl.Texture2D,
	size:  [2]int,
	valid: bool,
}

// MX.1 authored UI. The action bar remains a separate assets/hud pipeline;
// these IDs cover only reusable menu/HUD chrome and discipline presentation.
UI_Render_Mode :: enum u8 {
	Scale,
	Nine_Slice,
	Cover,
}

UI_Chrome_Id :: enum u8 {
	Menu_Background_Title,
	Menu_Background,
	Menu_Background_Frame,
	Menu_Logo_Title,
	Menu_Panel,
	Menu_Panel_Compact,
	Menu_Panel_Inset,
	Menu_Row,
	Menu_Row_Selected,
	Hud_Panel,
	Hud_Bar,
	Hud_Dock,
	Discipline_Panel_Warden,
	Discipline_Panel_Rogue,
	Discipline_Panel_Arcanist,
	Discipline_Panel_Acolyte,
	Discipline_Panel_Ranger,
	Minigame_Socket_Story,
	Minigame_Socket_Garden,
	Minigame_Socket_Soul,
	Story_Choice_Panel,
	Story_Relic_Socket,
	Chronicle_Ledger_Frame,
	Chronicle_Content_Panel,
	Chronicle_Filter_Panel,
	Chronicle_Unwritten_Ledger,
	Chronicle_Outcome_Seals,
}

UI_CHROME_COUNT :: 27
UI_DISCIPLINE_GLYPH_COUNT :: DISCIPLINE_COUNT
UI_STORY_SIGIL_COUNT :: len(Story_Sigil_Id)
UI_LOGO_DIAMOND_ATLAS_FILE :: "assets/ui/logo/diamond_atlas.png"
UI_LOGO_DIAMOND_FRAME_COUNT :: 16
UI_LOGO_DIAMOND_FRAME_SIZE :: [2]int{72, 74}
UI_LOGO_DIAMOND_ATLAS_SIZE :: [2]int{1152, 74}
UI_LOGO_DIAMOND_FPS :: f32(8)
UI_LOGO_DIAMOND_SOURCE_RECT :: [4]int{266, 24, 70, 74}
UI_GLYPH_ATLAS_FILE :: "assets/ui/glyph_atlas.png"
UI_GLYPH_ATLAS_CELL :: 32
UI_GLYPH_ATLAS_COLUMNS :: 10
UI_GLYPH_OUROBOROS_KEY :: "menu.glyph.sigil.ouroboros"

UI_Chrome_Def :: struct {
	key:                         string,
	file:                        string,
	render:                      UI_Render_Mode,
	source_size:                 [2]int,
	insets:                      [4]int, // left, top, right, bottom
	has_insets:                  bool,
	content_insets:              [4]int, // left, top, right, bottom
	has_content_insets:          bool,
	scale_insets_with_height:    bool,
	scale_insets_with_fit:       bool,
	tile_edges:                  bool,
	shrink_insets_below_height: int,
}

@(rodata)
UI_CHROME_DEFS := [UI_Chrome_Id]UI_Chrome_Def{
	.Menu_Background_Title = {
		key = "menu.background.title", file = "chrome/menu_background_title.png",
		render = .Cover, source_size = {400, 224},
	},
	.Menu_Background = {
		key = "menu.background", file = "chrome/menu_background.png",
		render = .Cover, source_size = {490, 300},
	},
	.Menu_Background_Frame = {
		key = "menu.background.frame", file = "chrome/menu_background_frame.png",
		render = .Nine_Slice, source_size = {382, 205},
		insets = {48, 44, 48, 44}, has_insets = true,
		content_insets = {42, 38, 42, 38}, has_content_insets = true,
		tile_edges = true,
	},
	.Menu_Logo_Title = {
		key = "menu.logo.title", file = "chrome/menu_logo_title.png",
		render = .Scale, source_size = {640, 122},
	},
	.Menu_Panel = {
		key = "menu.panel", file = "chrome/menu_panel.png",
		render = .Nine_Slice, source_size = {459, 268},
		insets = {18, 18, 18, 18}, has_insets = true,
		content_insets = {24, 22, 24, 22}, has_content_insets = true,
	},
	.Menu_Panel_Compact = {
		key = "menu.panel.compact", file = "chrome/menu_panel_compact.png",
		render = .Nine_Slice, source_size = {348, 274},
		insets = {21, 18, 21, 18}, has_insets = true,
		content_insets = {24, 22, 24, 22}, has_content_insets = true,
	},
	.Menu_Panel_Inset = {
		key = "menu.panel.inset", file = "chrome/menu_panel_inset.png",
		render = .Nine_Slice, source_size = {161, 81},
		insets = {14, 14, 14, 14}, has_insets = true,
		content_insets = {10, 8, 10, 8}, has_content_insets = true,
	},
	.Menu_Row = {
		key = "menu.row", file = "chrome/menu_row.png",
		render = .Nine_Slice, source_size = {623, 52},
		insets = {105, 10, 105, 10}, has_insets = true,
		content_insets = {92, 6, 92, 6}, has_content_insets = true,
		shrink_insets_below_height = 88,
	},
	.Menu_Row_Selected = {
		key = "menu.row.selected", file = "chrome/menu_row_selected.png",
		render = .Nine_Slice, source_size = {623, 52},
		insets = {105, 10, 150, 10}, has_insets = true,
		content_insets = {92, 6, 137, 6}, has_content_insets = true,
		shrink_insets_below_height = 88,
	},
	.Hud_Panel = {
		key = "hud.panel", file = "chrome/hud_panel.png",
		render = .Nine_Slice, source_size = {668, 108},
		insets = {10, 10, 10, 8}, has_insets = true,
		content_insets = {14, 8, 14, 8}, has_content_insets = true,
	},
	.Hud_Bar = {
		key = "hud.bar", file = "chrome/hud_bar.png",
		render = .Nine_Slice, source_size = {474, 66},
		insets = {22, 10, 22, 10}, has_insets = true,
		content_insets = {8, 4, 8, 4}, has_content_insets = true,
	},
	.Hud_Dock = {
		key = "hud.dock", file = "chrome/hud_dock.png",
		render = .Scale, source_size = {596, 123},
	},
	.Discipline_Panel_Warden = {
		key = "menu.panel.discipline.warden", file = "chrome/menu_panel_discipline_warden.png",
		render = .Nine_Slice, source_size = {600, 192},
		insets = {192, 0, 80, 0}, has_insets = true,
		content_insets = {188, 34, 84, 34}, has_content_insets = true,
		scale_insets_with_height = true,
	},
	.Discipline_Panel_Rogue = {
		key = "menu.panel.discipline.rogue", file = "chrome/menu_panel_discipline_rogue.png",
		render = .Nine_Slice, source_size = {600, 192},
		insets = {192, 0, 80, 0}, has_insets = true,
		content_insets = {192, 38, 84, 38}, has_content_insets = true,
		scale_insets_with_height = true,
	},
	.Discipline_Panel_Arcanist = {
		key = "menu.panel.discipline.arcanist", file = "chrome/menu_panel_discipline_arcanist.png",
		render = .Nine_Slice, source_size = {600, 192},
		insets = {192, 0, 76, 0}, has_insets = true,
		content_insets = {208, 34, 76, 34}, has_content_insets = true,
		scale_insets_with_height = true,
	},
	.Discipline_Panel_Acolyte = {
		key = "menu.panel.discipline.acolyte", file = "chrome/menu_panel_discipline_acolyte.png",
		render = .Nine_Slice, source_size = {600, 192},
		insets = {192, 0, 112, 0}, has_insets = true,
		content_insets = {204, 44, 72, 42}, has_content_insets = true,
		scale_insets_with_height = true,
	},
	.Discipline_Panel_Ranger = {
		key = "menu.panel.discipline.ranger", file = "chrome/menu_panel_discipline_ranger.png",
		render = .Nine_Slice, source_size = {600, 192},
		insets = {192, 0, 80, 0}, has_insets = true,
		content_insets = {192, 36, 80, 36}, has_content_insets = true,
		scale_insets_with_height = true,
	},
	.Minigame_Socket_Story = {
		key = "minigame.socket.story", file = "chrome/minigame_socket_story.png",
		render = .Scale, source_size = {256, 256},
		content_insets = {48, 48, 48, 48}, has_content_insets = true,
	},
	.Minigame_Socket_Garden = {
		key = "minigame.socket.garden", file = "chrome/minigame_socket_garden.png",
		render = .Scale, source_size = {256, 256},
		content_insets = {48, 48, 48, 48}, has_content_insets = true,
	},
	.Minigame_Socket_Soul = {
		key = "minigame.socket.soul", file = "chrome/minigame_socket_soul.png",
		render = .Scale, source_size = {256, 256},
		content_insets = {48, 48, 48, 48}, has_content_insets = true,
	},
	.Story_Choice_Panel = {
		key = "cutscene.choice.panel", file = "chrome/cutscene_choice_panel.png",
		render = .Nine_Slice, source_size = {640, 44},
		insets = {77, 6, 8, 6}, has_insets = true,
		content_insets = {80, 6, 10, 6}, has_content_insets = true,
		scale_insets_with_height = true,
	},
	.Story_Relic_Socket = {
		key = "cutscene.relic.socket", file = "chrome/cutscene_relic_socket.png",
		render = .Scale, source_size = {256, 256},
		content_insets = {64, 64, 64, 64}, has_content_insets = true,
	},
	.Chronicle_Ledger_Frame = {
		key = "chronicle.ledger.frame", file = "chronicle/ledger_frame.png",
		render = .Nine_Slice, source_size = {417, 321},
		insets = {76, 64, 76, 64}, has_insets = true,
		content_insets = {26, 24, 26, 24}, has_content_insets = true,
		tile_edges = true,
	},
	.Chronicle_Content_Panel = {
		key = "chronicle.content.panel", file = "chronicle/content_panel.png",
		render = .Nine_Slice, source_size = {528, 383},
		insets = {48, 44, 48, 44}, has_insets = true,
		content_insets = {26, 24, 26, 24}, has_content_insets = true,
	},
	.Chronicle_Filter_Panel = {
		key = "chronicle.filter.panel", file = "chronicle/filter_panel.png",
		render = .Nine_Slice, source_size = {355, 152},
		insets = {28, 24, 28, 24}, has_insets = true,
		content_insets = {18, 10, 18, 10}, has_content_insets = true,
		scale_insets_with_height = true,
	},

	.Chronicle_Unwritten_Ledger = {
		key = "chronicle.empty.ledger", file = "chronicle/unwritten_ledger.png",
		render = .Scale, source_size = {256, 256},
	},
	.Chronicle_Outcome_Seals = {
		key = "chronicle.outcome.seals", file = "chronicle/outcome_seals.png",
		render = .Scale, source_size = {256, 128},
	},
}

@(rodata)
UI_DISCIPLINE_PANELS := [Archetype_Id]UI_Chrome_Id{
	.Warden = .Discipline_Panel_Warden,
	.Rogue = .Discipline_Panel_Rogue,
	.Arcanist = .Discipline_Panel_Arcanist,
	.Acolyte = .Discipline_Panel_Acolyte,
	.Ranger = .Discipline_Panel_Ranger,
}

// Exact semantic-key mapping in Discipline_Id ordinal order. Keeping this typed
// registry beside the progression enum makes atlas-order drift fail in tests
// instead of silently displaying the wrong node art.
@(rodata)
UI_DISCIPLINE_GLYPH_KEYS := [Discipline_Id]string{
	.Warden_Bulwark = "menu.glyph.discipline.warden_bulwark",
	.Warden_Riposte = "menu.glyph.discipline.warden_riposte",
	.Warden_Aegis = "menu.glyph.discipline.warden_aegis",
	.Warden_Counter = "menu.glyph.discipline.warden_counter",
	.Warden_Bulwark_Ward = "menu.glyph.discipline.warden_bulwark_ward",
	.Warden_Riposte_Edge = "menu.glyph.discipline.warden_riposte_edge",
	.Warden_Iron_Vow = "menu.glyph.discipline.warden_iron_vow",
	.Warden_Reckoning = "menu.glyph.discipline.warden_reckoning",
	.Warden_Unbreakable = "menu.glyph.discipline.warden_unbreakable",
	.Warden_Final_Reckoning = "menu.glyph.discipline.warden_final_reckoning",
	.Warden_Smite = "menu.glyph.discipline.warden_smite",
	.Warden_Ward = "menu.glyph.discipline.warden_ward",
	.Warden_Judgment = "menu.glyph.discipline.warden_judgment",
	.Warden_Bulwark_Wave = "menu.glyph.discipline.warden_bulwark_wave",
	.Warden_Consecrate = "menu.glyph.discipline.warden_consecrate",
	.Warden_Stone_Aegis = "menu.glyph.discipline.warden_stone_aegis",
	.Warden_Divine_Wrath = "menu.glyph.discipline.warden_divine_wrath",
	.Warden_Unyielding = "menu.glyph.discipline.warden_unyielding",
	.Warden_Avatar_Of_Light = "menu.glyph.discipline.warden_avatar_of_light",
	.Warden_Eternal_Wall = "menu.glyph.discipline.warden_eternal_wall",
	.Rogue_Precision = "menu.glyph.discipline.rogue_precision",
	.Rogue_Smoke = "menu.glyph.discipline.rogue_smoke",
	.Rogue_Venom = "menu.glyph.discipline.rogue_venom",
	.Rogue_Shadowstep = "menu.glyph.discipline.rogue_shadowstep",
	.Rogue_Executioner = "menu.glyph.discipline.rogue_executioner",
	.Rogue_Night_Veil = "menu.glyph.discipline.rogue_night_veil",
	.Rogue_Crimson_Edge = "menu.glyph.discipline.rogue_crimson_edge",
	.Rogue_Phantom = "menu.glyph.discipline.rogue_phantom",
	.Rogue_Deathmark = "menu.glyph.discipline.rogue_deathmark",
	.Rogue_Umbral = "menu.glyph.discipline.rogue_umbral",
	.Rogue_Trap_Craft = "menu.glyph.discipline.rogue_trap_craft",
	.Rogue_Marksman = "menu.glyph.discipline.rogue_marksman",
	.Rogue_Venom_Trap = "menu.glyph.discipline.rogue_venom_trap",
	.Rogue_Sharpshot = "menu.glyph.discipline.rogue_sharpshot",
	.Rogue_Bear_Trap = "menu.glyph.discipline.rogue_bear_trap",
	.Rogue_Deadeye = "menu.glyph.discipline.rogue_deadeye",
	.Rogue_Trap_Master = "menu.glyph.discipline.rogue_trap_master",
	.Rogue_Eagle_Eye = "menu.glyph.discipline.rogue_eagle_eye",
	.Rogue_Ambush_Engineer = "menu.glyph.discipline.rogue_ambush_engineer",
	.Rogue_Assassin = "menu.glyph.discipline.rogue_assassin",
	.Arcanist_Splinter = "menu.glyph.discipline.arcanist_splinter",
	.Arcanist_Focus = "menu.glyph.discipline.arcanist_focus",
	.Arcanist_Permafrost = "menu.glyph.discipline.arcanist_permafrost",
	.Arcanist_Overload = "menu.glyph.discipline.arcanist_overload",
	.Arcanist_Glacial = "menu.glyph.discipline.arcanist_glacial",
	.Arcanist_Pierce = "menu.glyph.discipline.arcanist_pierce",
	.Arcanist_Blizzard = "menu.glyph.discipline.arcanist_blizzard",
	.Arcanist_Storm = "menu.glyph.discipline.arcanist_storm",
	.Arcanist_Absolute_Zero = "menu.glyph.discipline.arcanist_absolute_zero",
	.Arcanist_Arc_Tyrant = "menu.glyph.discipline.arcanist_arc_tyrant",
	.Arcanist_Charge = "menu.glyph.discipline.arcanist_charge",
	.Arcanist_Ward = "menu.glyph.discipline.arcanist_ward",
	.Arcanist_Chain_Lightning = "menu.glyph.discipline.arcanist_chain_lightning",
	.Arcanist_Ward_Mend = "menu.glyph.discipline.arcanist_ward_mend",
	.Arcanist_Tempest = "menu.glyph.discipline.arcanist_tempest",
	.Arcanist_Ward_Overload = "menu.glyph.discipline.arcanist_ward_overload",
	.Arcanist_Storm_Caller = "menu.glyph.discipline.arcanist_storm_caller",
	.Arcanist_Aegis = "menu.glyph.discipline.arcanist_aegis",
	.Arcanist_World_Storm = "menu.glyph.discipline.arcanist_world_storm",
	.Arcanist_Eternal_Aegis = "menu.glyph.discipline.arcanist_eternal_aegis",
	.Acolyte_Sanguine = "menu.glyph.discipline.acolyte_sanguine",
	.Acolyte_Veil = "menu.glyph.discipline.acolyte_veil",
	.Acolyte_Gravebind = "menu.glyph.discipline.acolyte_gravebind",
	.Acolyte_Ashen = "menu.glyph.discipline.acolyte_ashen",
	.Acolyte_Blood_Pact = "menu.glyph.discipline.acolyte_blood_pact",
	.Acolyte_Spirit_Host = "menu.glyph.discipline.acolyte_spirit_host",
	.Acolyte_Crimson_Maw = "menu.glyph.discipline.acolyte_crimson_maw",
	.Acolyte_Grave_Chorus = "menu.glyph.discipline.acolyte_grave_chorus",
	.Acolyte_Sanguine_Ascendant = "menu.glyph.discipline.acolyte_sanguine_ascendant",
	.Acolyte_Undying_Veil = "menu.glyph.discipline.acolyte_undying_veil",
	.Acolyte_Spirit_Call = "menu.glyph.discipline.acolyte_spirit_call",
	.Acolyte_Curse = "menu.glyph.discipline.acolyte_curse",
	.Acolyte_Wraith_Host = "menu.glyph.discipline.acolyte_wraith_host",
	.Acolyte_Decay = "menu.glyph.discipline.acolyte_decay",
	.Acolyte_Bone_Legion = "menu.glyph.discipline.acolyte_bone_legion",
	.Acolyte_Fragility = "menu.glyph.discipline.acolyte_fragility",
	.Acolyte_Wraith_Lord = "menu.glyph.discipline.acolyte_wraith_lord",
	.Acolyte_Doom = "menu.glyph.discipline.acolyte_doom",
	.Acolyte_Legion_Eternal = "menu.glyph.discipline.acolyte_legion_eternal",
	.Acolyte_Eternal_Doom = "menu.glyph.discipline.acolyte_eternal_doom",
	.Ranger_Snare = "menu.glyph.discipline.ranger_snare",
	.Ranger_Volley = "menu.glyph.discipline.ranger_volley",
	.Ranger_Beastmark = "menu.glyph.discipline.ranger_beastmark",
	.Ranger_Rapid = "menu.glyph.discipline.ranger_rapid",
	.Ranger_Thornfield = "menu.glyph.discipline.ranger_thornfield",
	.Ranger_Piercing_Volley = "menu.glyph.discipline.ranger_piercing_volley",
	.Ranger_Hunter_Drive = "menu.glyph.discipline.ranger_hunter_drive",
	.Ranger_Storm_Volley = "menu.glyph.discipline.ranger_storm_volley",
	.Ranger_Wild_Domination = "menu.glyph.discipline.ranger_wild_domination",
	.Ranger_Sky_Quiver = "menu.glyph.discipline.ranger_sky_quiver",
	.Ranger_Beast_Bond = "menu.glyph.discipline.ranger_beast_bond",
	.Ranger_Survival = "menu.glyph.discipline.ranger_survival",
	.Ranger_Pack_Tactics = "menu.glyph.discipline.ranger_pack_tactics",
	.Ranger_Camouflage = "menu.glyph.discipline.ranger_camouflage",
	.Ranger_Alpha = "menu.glyph.discipline.ranger_alpha",
	.Ranger_Pathfinder = "menu.glyph.discipline.ranger_pathfinder",
	.Ranger_Spirit_Companion = "menu.glyph.discipline.ranger_spirit_companion",
	.Ranger_Ambush = "menu.glyph.discipline.ranger_ambush",
	.Ranger_Primal_Lord = "menu.glyph.discipline.ranger_primal_lord",
	.Ranger_Ghost_Step = "menu.glyph.discipline.ranger_ghost_step",
}

UI_Chrome_Asset :: struct {
	tex:                         rl.Texture2D,
	render:                      UI_Render_Mode,
	source_size:                 [2]int,
	insets:                      [4]int,
	has_insets:                  bool,
	content_insets:              [4]int,
	has_content_insets:          bool,
	scale_insets_with_height:    bool,
	scale_insets_with_fit:       bool,
	tile_edges:                  bool,
	shrink_insets_below_height: int,
	valid:                       bool,
}

UI_Logo_Animation :: struct {
	tex:              rl.Texture2D,
	size:             [2]int,
	frame_size:       [2]int,
	frame_count:      int,
	fps:              f32,
	logo_source_rect: [4]int,
	loaded:           bool,
}

// Regions do not own GPU resources. UI_Glyph_Atlas owns exactly one texture;
// callers receive lightweight views and must never unload a view's texture.
UI_Glyph_Region :: struct {
	source:      rl.Rectangle,
	source_size: [2]int,
	valid:       bool,
}

UI_Glyph_Atlas :: struct {
	tex:         rl.Texture2D,
	size:        [2]int,
	disciplines: [Discipline_Id]UI_Glyph_Region,
	story_sigils: [Story_Sigil_Id]UI_Glyph_Region,
	ouroboros:   UI_Glyph_Region,
	loaded:      bool,
}

UI_Glyph_Asset :: struct {
	tex:         rl.Texture2D,
	source:      rl.Rectangle,
	source_size: [2]int,
	valid:       bool,
}

// Canonical world art metadata (already at tile-native scale).
World_Key :: enum {
	Floor,
	Shop_Floor,
	Bar_Floor,
	Garden_Floor,
	Quest_Floor,
	Lossless_Soul_Floor,
	Guiding_Overlay,
	Wall,
	Bar_Wall_L,
	Bar_Wall_R,
	Garden_Wall_L,
	Garden_Wall_R,
	Quest_Wall_L,
	Quest_Wall_R,
	Lossless_Soul_Wall_L,
	Lossless_Soul_Wall_R,
	Stairs,
	Door_Closed_L,
	Door_Closed_R,
	Door_Open_L,
	Door_Open_R,
	Wall_Face, // transient wall-touch clip (MX.5); frames start/end on wall_403
}

@(rodata)
WORLD_KEY_NAMES := [World_Key]string {
	.Floor                 = "floor",
	.Shop_Floor            = "shop_floor",
	.Bar_Floor             = "bar_floor",
	.Garden_Floor          = "garden_floor",
	.Quest_Floor           = "quest_floor",
	.Lossless_Soul_Floor   = "lossless_soul_floor",
	.Guiding_Overlay       = "guiding_overlay",
	.Wall                  = "wall",
	.Bar_Wall_L            = "wall_bar_left",
	.Bar_Wall_R            = "wall_bar_right",
	.Garden_Wall_L         = "wall_garden_left",
	.Garden_Wall_R         = "wall_garden_right",
	.Quest_Wall_L          = "wall_quest_room_left",
	.Quest_Wall_R          = "wall_quest_room_right",
	.Lossless_Soul_Wall_L  = "wall_lossless_soul_left",
	.Lossless_Soul_Wall_R  = "wall_lossless_soul_right",
	.Stairs        = "stairs",
	.Door_Closed_L = "door_closed",
	.Door_Closed_R = "door_closed_east",
	.Door_Open_L   = "door_open",
	.Door_Open_R   = "door_open_east",
	.Wall_Face     = "wall_face",
}

// Pick the authored visible face from the wall run around a doorway. Pygame's
// contract is x-axis flanks -> left face, y-axis flanks -> right face; an
// ambiguous/corner doorway deliberately falls back to left.
door_world_key :: proc(tile: Tile_Kind, x_axis, y_axis: bool) -> World_Key {
	right_face := y_axis && !x_axis
	if tile == .Open_Door {
		return right_face ? .Door_Open_R : .Door_Open_L
	}
	return right_face ? .Door_Closed_R : .Door_Closed_L
}

special_room_floor_world_key :: proc(kind: Special_Room_Kind) -> (World_Key, bool) {
	switch kind {
	case .Shop:                  return .Shop_Floor, true
	case .Bar:                   return .Bar_Floor, true
	case .Garden:                return .Garden_Floor, true
	case .Quest:                 return .Quest_Floor, true
	case .Hall_Of_Unlost_Echoes: return .Lossless_Soul_Floor, true
	case .None:
	}
	return .Floor, false
}

special_room_wall_world_key :: proc(kind: Special_Room_Kind, left_face: bool) -> (World_Key, bool) {
	switch kind {
	case .Bar:                   return left_face ? .Bar_Wall_L : .Bar_Wall_R, true
	case .Garden:                return left_face ? .Garden_Wall_L : .Garden_Wall_R, true
	case .Quest:                 return left_face ? .Quest_Wall_L : .Quest_Wall_R, true
	case .Hall_Of_Unlost_Echoes: return left_face ? .Lossless_Soul_Wall_L : .Lossless_Soul_Wall_R, true
	case .None, .Shop:
	}
	return .Wall, false
}

MAX_WORLD_FRAMES :: 10

// HD world sprite: `variants` are a per-tile static choice (10 wall faces,
// 4 floor slabs), `frames` are a time animation (stairs), optionally
// ping-pong. Drawn at TILE_W / ref_width so any source resolution spans
// exactly its authored tile footprint.
World_Sprite :: struct {
	variants:      [MAX_WORLD_FRAMES]rl.Texture2D,
	variant_count: int,
	frames:        [MAX_WORLD_FRAMES]rl.Texture2D,
	frame_count:   int,
	fps:           f32,
	ping_pong:     bool,
	anchor:        Vec2, // pixels in image space; lands on the tile center
	scale:         f32, // world px per image px
	tint:          f32, // theme tint strength
	loaded:        bool,
}

Item_Icon :: struct {
	tex:     rl.Texture2D,
	anchor:  Vec2, // fraction of the image
	world_h: f32, // world px the image height renders at
	loaded:  bool,
}

Prop_Key :: enum {
	Shop_Sign,
	Gold_Stack_1,
	Gold_Stack_2,
	Gold_Stack_3,
	Gold_Stack_4,
	Gold_Stack_5,
	Bar_Barrel,
	Bar_Table,
	Bar_Sconce_R,
	Bar_Sconce_L,
	Lossless_Soul_Mirror,
	Lossless_Soul_Chimes,
	Lossless_Soul_Brazier,
	Lossless_Soul_Reliquary,
	Shrine_Mending,
	Shrine_Insight,
	Shrine_War,
	Shrine_Haste,
	Shrine_Fortune,
	Shrine_Oath,
	Shrine_Twilight,
	Secret_Cache,
	Trap_Spike,
	Trap_Rune,
	Trap_Needle,
	Ambush_Bell,
}

@(rodata)
PROP_KEY_NAMES := [Prop_Key]string{
	.Shop_Sign    = "shop_sign",
	.Gold_Stack_1 = "gold_stack",
	.Gold_Stack_2 = "gold_stack_02",
	.Gold_Stack_3 = "gold_stack_03",
	.Gold_Stack_4 = "gold_stack_04",
	.Gold_Stack_5 = "gold_stack_05",
	.Bar_Barrel   = "bar_barrel",
	.Bar_Table    = "bar_table",
	.Bar_Sconce_R = "bar_wall_sconce_south_east",
	.Bar_Sconce_L = "bar_wall_sconce_south_west",
	.Lossless_Soul_Mirror    = "lossless_room_mirror",
	.Lossless_Soul_Chimes    = "lossless_room_chimes",
	.Lossless_Soul_Brazier   = "lossless_room_brazier",
	.Lossless_Soul_Reliquary = "lossless_room_reliquary",
	.Shrine_Mending  = "shrine_mending",
	.Shrine_Insight  = "shrine_insight",
	.Shrine_War      = "shrine_war",
	.Shrine_Haste    = "shrine_haste",
	.Shrine_Fortune  = "shrine_fortune",
	.Shrine_Oath     = "shrine_oath",
	.Shrine_Twilight = "shrine_twilight",
	.Secret_Cache    = "secret_cache",
	.Trap_Spike      = "trap_spike",
	.Trap_Rune       = "trap_rune",
	.Trap_Needle     = "trap_poison",
	.Ambush_Bell     = "ambush_bell",
}

Prop_Asset :: struct {
	tex:          rl.Texture2D,
	anchor:       Vec2,
	world_height: f32,
	loaded:       bool,
}

// MX-story authored panel art. Corpus-owned semantic keys live in
// story_content.odin; this file owns only their canonical self-contained paths,
// GPU storage, manifest validation, and renderer-facing resolution.
Story_Art_Usage :: enum u8 {
	Backdrop,
	Icon,
	Portrait,
}

Story_Choice_Icon_Id :: enum u8 {
	Aid,
	Bargain,
	Defy,
	Page,
	Soul_Preserve,
	Soul_Release,
	Soul_Refuse,
}

STORY_CHOICE_ICON_COUNT       :: 7
STORY_SUPPORT_BACKDROP_COUNT :: 1
STORY_ART_MANIFEST_FORMAT    :: 1
STORY_ART_ROOT               :: "assets/story"
STORY_ART_ASSET_COUNT        :: STORY_OMEN_ASSET_COUNT + STORY_GUEST_ASSET_COUNT +
	STORY_ENDING_ASSET_COUNT + STORY_RELIC_ASSET_COUNT + STORY_PORTRAIT_ASSET_COUNT +
	STORY_SUPPORT_BACKDROP_COUNT + STORY_CHOICE_ICON_COUNT
STORY_LOSSLESS_SOUL_BACKDROP_KEY  :: "stage.backdrop.lossless_soul"
STORY_LOSSLESS_SOUL_BACKDROP_FILE :: "backdrops/lossless_soul.png"

@(rodata)
STORY_CHOICE_ICON_NAMES := [Story_Choice_Icon_Id]string{
	.Aid = "aid",
	.Bargain = "bargain",
	.Defy = "defy",
	.Page = "page",
	.Soul_Preserve = "soul_preserve",
	.Soul_Release = "soul_release",
	.Soul_Refuse = "soul_refuse",
}

@(rodata)
STORY_CHOICE_ICON_ASSET_KEYS := [Story_Choice_Icon_Id]string{
	.Aid = "cutscene.choice.icon.aid",
	.Bargain = "cutscene.choice.icon.bargain",
	.Defy = "cutscene.choice.icon.defy",
	.Page = "cutscene.choice.icon.page",
	.Soul_Preserve = "cutscene.choice.icon.soul_preserve",
	.Soul_Release = "cutscene.choice.icon.soul_release",
	.Soul_Refuse = "cutscene.choice.icon.soul_refuse",
}

@(rodata)
STORY_CHOICE_ICON_FILES := [Story_Choice_Icon_Id]string{
	.Aid = "icons/choices/aid.png",
	.Bargain = "icons/choices/bargain.png",
	.Defy = "icons/choices/defy.png",
	.Page = "icons/choices/page.png",
	.Soul_Preserve = "icons/choices/soul_preserve.png",
	.Soul_Release = "icons/choices/soul_release.png",
	.Soul_Refuse = "icons/choices/soul_refuse.png",
}

@(rodata)
STORY_OMEN_ASSET_FILES := [Story_Motif_Id]string{
	.Crypt_Of_Ash = "backdrops/omens/crypt_of_ash.png",
	.Fungal_Catacombs = "backdrops/omens/fungal_catacombs.png",
	.Violet_Reliquary = "backdrops/omens/violet_reliquary.png",
	.Sunken_Bastion = "backdrops/omens/sunken_bastion.png",
	.Frozen_Ossuary = "backdrops/omens/frozen_ossuary.png",
	.Obsidian_Foundry = "backdrops/omens/obsidian_foundry.png",
	.Moonlit_Aquifer = "backdrops/omens/moonlit_aquifer.png",
	.Thornbound_Vault = "backdrops/omens/thornbound_vault.png",
}

@(rodata)
STORY_GUEST_BACKDROP_ASSET_FILES := [Story_Guest_Role_Id]string{
	.Oathless_Knight = "backdrops/guests/oathless_knight.png",
	.Grave_Witch = "backdrops/guests/grave_witch.png",
	.Drowned_Heir = "backdrops/guests/drowned_heir.png",
	.Ash_Pilgrim = "backdrops/guests/ash_pilgrim.png",
	.Mirror_Scribe = "backdrops/guests/mirror_scribe.png",
	.Antlered_Hunter = "backdrops/guests/antlered_hunter.png",
	.Mortuary_Broker = "backdrops/guests/mortuary_broker.png",
	.Lost_Cartographer = "backdrops/guests/lost_cartographer.png",
	.Bone_Mender = "backdrops/guests/bone_mender.png",
	.Furnace_Heretic = "backdrops/guests/furnace_heretic.png",
}

@(rodata)
STORY_ENDING_PANEL_ASSET_FILES := [Archetype_Id][Story_Choice_Verb]string{
	.Warden = {
		.Aid = "backdrops/endings/warden/the_held_door.png",
		.Bargain = "backdrops/endings/warden/the_fair_scale.png",
		.Defy = "backdrops/endings/warden/no_more_doors.png",
	},
	.Rogue = {
		.Aid = "backdrops/endings/rogue/the_emptied_market.png",
		.Bargain = "backdrops/endings/rogue/the_honest_purchase.png",
		.Defy = "backdrops/endings/rogue/the_standing_debt.png",
	},
	.Arcanist = {
		.Aid = "backdrops/endings/arcanist/the_answered_proof.png",
		.Bargain = "backdrops/endings/arcanist/the_restored_name.png",
		.Defy = "backdrops/endings/arcanist/the_standing_argument.png",
	},
	.Acolyte = {
		.Aid = "backdrops/endings/acolyte/the_true_funeral.png",
		.Bargain = "backdrops/endings/acolyte/the_returned_confession.png",
		.Defy = "backdrops/endings/acolyte/the_broken_bell.png",
	},
	.Ranger = {
		.Aid = "backdrops/endings/ranger/the_hunt_without_arrows.png",
		.Bargain = "backdrops/endings/ranger/the_next_white_thing.png",
		.Defy = "backdrops/endings/ranger/the_old_way.png",
	},
}

@(rodata)
STORY_RELIC_ICON_ASSET_FILES := [Story_Relic_Id]string{
	.Asterion_Nail = "icons/relics/asterion_nail.png",
	.Mire_Saints_Bell = "icons/relics/mire_saints_bell.png",
	.Lantern_Of_Unburied_Roads = "icons/relics/lantern_of_unburied_roads.png",
	.Crown_Of_Antlers_And_Teeth = "icons/relics/crown_of_antlers_and_teeth.png",
	.Mirror_Psalter = "icons/relics/mirror_psalter.png",
	.Cinder_Key_Of_Khar = "icons/relics/cinder_key_of_khar.png",
	.Wormscript_Map = "icons/relics/wormscript_map.png",
	.Vessel_Of_Last_Rain = "icons/relics/vessel_of_last_rain.png",
	.Oath_Eaters_Chain = "icons/relics/oath_eaters_chain.png",
	.Heartseed_Reliquary = "icons/relics/heartseed_reliquary.png",
}

@(rodata)
STORY_GUEST_PORTRAIT_ASSET_FILES := [Story_Guest_Role_Id][STORY_GUEST_VARIANTS]string{
	.Oathless_Knight = {"portraits/oathless_knight/ser_caldus.png", "portraits/oathless_knight/dame_vey.png", "portraits/oathless_knight/rook_of_voss.png"},
	.Grave_Witch = {"portraits/grave_witch/mother_hush.png", "portraits/grave_witch/edda_crowmilk.png", "portraits/grave_witch/vespera_thorne.png"},
	.Drowned_Heir = {"portraits/drowned_heir/prince_nerian.png", "portraits/drowned_heir/lysa_underwave.png", "portraits/drowned_heir/blue_lipped_child.png"},
	.Ash_Pilgrim = {"portraits/ash_pilgrim/harl_the_sooted.png", "portraits/ash_pilgrim/sister_kharra.png", "portraits/ash_pilgrim/old_ember_jesk.png"},
	.Mirror_Scribe = {"portraits/mirror_scribe/tallow_quill.png", "portraits/mirror_scribe/iosef_of_the_glass.png", "portraits/mirror_scribe/nim_rue.png"},
	.Antlered_Hunter = {"portraits/antlered_hunter/mael_whitehorn.png", "portraits/antlered_hunter/quiet_hart.png", "portraits/antlered_hunter/sable_of_the_moon_hunt.png"},
	.Mortuary_Broker = {"portraits/mortuary_broker/coin_eye_pell.png", "portraits/mortuary_broker/madam_nacre.png", "portraits/mortuary_broker/voss_factor_ilm.png"},
	.Lost_Cartographer = {"portraits/lost_cartographer/ammar_without_roads.png", "portraits/lost_cartographer/fen_chalkhand.png", "portraits/lost_cartographer/sella_of_the_fold.png"},
	.Bone_Mender = {"portraits/bone_mender/saint_not_yet.png", "portraits/bone_mender/mara_sutured.png", "portraits/bone_mender/kell_of_white_thread.png"},
	.Furnace_Heretic = {"portraits/furnace_heretic/brass_thumb_oren.png", "portraits/furnace_heretic/malk_the_quenched.png", "portraits/furnace_heretic/devra_cogprayer.png"},
}

Story_Art_Def :: struct {
	key:   string,
	file:  string,
	usage: Story_Art_Usage,
}

Story_Texture_Asset :: struct {
	tex:         rl.Texture2D,
	source_size: [2]int,
	valid:       bool,
}

Story_Art_Assets :: struct {
	omens:                 [Story_Motif_Id]Story_Texture_Asset,
	guest_backdrops:       [Story_Guest_Role_Id]Story_Texture_Asset,
	ending_panels:         [Archetype_Id][Story_Choice_Verb]Story_Texture_Asset,
	relic_icons:           [Story_Relic_Id]Story_Texture_Asset,
	guest_portraits:       [Story_Guest_Role_Id][STORY_GUEST_VARIANTS]Story_Texture_Asset,
	lossless_soul_backdrop: Story_Texture_Asset,
	choice_icons:           [Story_Choice_Icon_Id]Story_Texture_Asset,
	fallback:               Story_Texture_Asset,
	manifest_valid:         bool,
	loaded_count:           int,
}

// The story manifest deliberately contains only semantic identity, canonical
// relative PNG paths, and integrity metadata. Images remain optional at run
// time: a valid row whose file is absent or undecodable resolves to `.valid ==
// false`, allowing the renderer to keep its procedural fallback.
Story_Art_Manifest_Entry :: struct {
	file:   string,
	sha256: string,
}

Story_Art_Manifest :: struct {
	format_version: int,
	asset_count:    int,
	assets:         map[string]Story_Art_Manifest_Entry,
}

Assets :: struct {
	archetypes:                 [Archetype_Id]Actor_Sprites,
	enemies:                    [Enemy_Kind]Actor_Sprites,
	bosses:                     [Boss_Id]Actor_Sprites,
	familiar_wisp:              Actor_Sprites,
	familiar_crow:              Actor_Sprites,
	spirit_beast:               Actor_Sprites,
	shopkeeper:                 Actor_Sprites,
	bar_dancer:                 Actor_Sprites,
	garden_frog:                Actor_Sprites,
	story_guest:                Actor_Sprites,
	lossless_soul:              Actor_Sprites,
	action_icons:               [Action_Icon]Action_Icon_Asset,
	mobile_hud:                 [Mobile_Hud_Asset_Id]Mobile_Hud_Asset,
	action_loadouts:            [Archetype_Id][ACTION_SLOT_COUNT]Action_Icon,
	ranger_spirit_beast_attack: Action_Icon,
	world:                      [World_Key]World_Sprite,
	items:                      map[string]Item_Icon,
	props:                      [Prop_Key]Prop_Asset,
	ui_chrome:                  [UI_Chrome_Id]UI_Chrome_Asset,
	ui_logo_animation:          UI_Logo_Animation,
	ui_glyph_atlas:             UI_Glyph_Atlas,
	ui_font:                    rl.Font,
	ui_font_loaded:             bool,
	story:                      Story_Art_Assets,
	load_complete:              bool,
}

Assets_Load_Summary :: struct {
	actors:       int,
	action_icons: int,
	world:        int,
	items:        int,
	props:        int,
	ui:           int,
	story:        int,
	total:        int,
	ready:        bool,
}

// Clone raylib-owned bytes before returning so JSON parsing is independent of
// the platform file backend. Android resolves packaged assets through raylib;
// desktop keeps the same relative-path behavior.
@(private = "file")
assets_read_owned :: proc(path: string) -> ([]u8, bool) {
	data_size: c.int
	raw := rl.LoadFileData(fmt.ctprintf("%s", path), &data_size)
	if raw == nil || data_size <= 0 {
		if raw != nil do rl.UnloadFileData(raw)
		platform_log(fmt.tprintf("assets: failed to read %s", path))
		return nil, false
	}
	defer rl.UnloadFileData(raw)
	data := make([]u8, int(data_size), context.allocator)
	copy(data, raw[:int(data_size)])
	return data, true
}

@(private = "file")
assets_actor_texture_count :: proc(assets: ^Assets) -> (count: int) {
	if assets == nil do return
	count_sprites := proc(sprites: ^Actor_Sprites) -> (result: int) {
		if sprites == nil do return
		for clip in sprites.clips {
			if clip.tex.id != 0 do result += 1
		}
		return
	}
	for id in Archetype_Id do count += count_sprites(&assets.archetypes[id])
	for kind in Enemy_Kind do count += count_sprites(&assets.enemies[kind])
	for id in Boss_Id do count += count_sprites(&assets.bosses[id])
	count += count_sprites(&assets.familiar_wisp)
	count += count_sprites(&assets.familiar_crow)
	count += count_sprites(&assets.spirit_beast)
	count += count_sprites(&assets.shopkeeper)
	count += count_sprites(&assets.bar_dancer)
	count += count_sprites(&assets.garden_frog)
	count += count_sprites(&assets.story_guest)
	count += count_sprites(&assets.lossless_soul)
	return
}

@(private = "file")
assets_story_texture_count :: proc(assets: ^Assets) -> (count: int) {
	if assets == nil do return
	count_asset := proc(asset: ^Story_Texture_Asset) -> int {
		return asset != nil && asset.tex.id != 0 ? 1 : 0
	}
	for id in Story_Motif_Id do count += count_asset(&assets.story.omens[id])
	for id in Story_Guest_Role_Id do count += count_asset(&assets.story.guest_backdrops[id])
	for archetype in Archetype_Id do for verb in Story_Choice_Verb {
		count += count_asset(&assets.story.ending_panels[archetype][verb])
	}
	for id in Story_Relic_Id do count += count_asset(&assets.story.relic_icons[id])
	for role in Story_Guest_Role_Id do for variant in 0 ..< STORY_GUEST_VARIANTS {
		count += count_asset(&assets.story.guest_portraits[role][variant])
	}
	count += count_asset(&assets.story.lossless_soul_backdrop)
	for id in Story_Choice_Icon_Id do count += count_asset(&assets.story.choice_icons[id])
	count += count_asset(&assets.story.fallback)
	return
}

assets_load_summary :: proc(assets: ^Assets) -> (summary: Assets_Load_Summary) {
	if assets == nil do return
	summary.actors = assets_actor_texture_count(assets)
	for asset in assets.action_icons {
		if asset.tex.id != 0 do summary.action_icons += 1
	}
	for sprite in assets.world {
		for tex in sprite.variants do if tex.id != 0 do summary.world += 1
		for tex in sprite.frames do if tex.id != 0 do summary.world += 1
	}
	for _, item in assets.items {
		if item.tex.id != 0 do summary.items += 1
	}
	for prop in assets.props {
		if prop.tex.id != 0 do summary.props += 1
	}
	for asset in assets.ui_chrome {
		if asset.tex.id != 0 do summary.ui += 1
	}
	for asset in assets.mobile_hud {
		if asset.tex.id != 0 do summary.ui += 1
	}
	if assets.ui_logo_animation.tex.id != 0 do summary.ui += 1
	if assets.ui_glyph_atlas.tex.id != 0 do summary.ui += 1
	if assets.ui_font_loaded do summary.ui += 1
	summary.story = assets_story_texture_count(assets)
	summary.total = summary.actors + summary.action_icons + summary.world + summary.items +
		summary.props + summary.ui + summary.story
	summary.ready = assets.load_complete
	return
}

assets_loaded_texture_count :: proc(assets: ^Assets) -> int {
	return assets_load_summary(assets).total
}

assets_ready :: proc(assets: ^Assets) -> bool {
	return assets != nil && assets.load_complete
}

assets_log_load_summary :: proc(assets: ^Assets) {
	summary := assets_load_summary(assets)
	platform_log(fmt.tprintf(
		"assets: ready=%v textures=%d (actors=%d actions=%d world=%d items=%d props=%d ui=%d story=%d)",
		summary.ready,
		summary.total,
		summary.actors,
		summary.action_icons,
		summary.world,
		summary.items,
		summary.props,
		summary.ui,
		summary.story,
	))
}

// Stable flattened order used only by manifest tooling/validation. Runtime
// rendering stays on the typed accessors below, not integer slots.
story_art_def_at :: proc(index: int) -> (Story_Art_Def, bool) {
	if index < 0 || index >= STORY_ART_ASSET_COUNT do return {}, false
	cursor := index
	if cursor < STORY_OMEN_ASSET_COUNT {
		id := Story_Motif_Id(cursor)
		return {key = STORY_OMEN_ASSET_KEYS[id], file = STORY_OMEN_ASSET_FILES[id], usage = .Backdrop}, true
	}
	cursor -= STORY_OMEN_ASSET_COUNT
	if cursor < STORY_GUEST_ASSET_COUNT {
		id := Story_Guest_Role_Id(cursor)
		return {key = STORY_GUEST_BACKDROP_ASSET_KEYS[id], file = STORY_GUEST_BACKDROP_ASSET_FILES[id], usage = .Backdrop}, true
	}
	cursor -= STORY_GUEST_ASSET_COUNT
	if cursor < STORY_ENDING_ASSET_COUNT {
		archetype := Archetype_Id(cursor / STORY_CHOICE_COUNT)
		verb := Story_Choice_Verb(cursor % STORY_CHOICE_COUNT)
		return {
			key = STORY_ENDING_PANEL_ASSET_KEYS[archetype][verb],
			file = STORY_ENDING_PANEL_ASSET_FILES[archetype][verb],
			usage = .Backdrop,
		}, true
	}
	cursor -= STORY_ENDING_ASSET_COUNT
	if cursor < STORY_RELIC_ASSET_COUNT {
		id := Story_Relic_Id(cursor)
		return {key = STORY_RELIC_ICON_ASSET_KEYS[id], file = STORY_RELIC_ICON_ASSET_FILES[id], usage = .Icon}, true
	}
	cursor -= STORY_RELIC_ASSET_COUNT
	if cursor < STORY_PORTRAIT_ASSET_COUNT {
		role := Story_Guest_Role_Id(cursor / STORY_GUEST_VARIANTS)
		variant := cursor % STORY_GUEST_VARIANTS
		return {
			key = STORY_GUEST_PORTRAIT_ASSET_KEYS[role][variant],
			file = STORY_GUEST_PORTRAIT_ASSET_FILES[role][variant],
			usage = .Portrait,
		}, true
	}
	cursor -= STORY_PORTRAIT_ASSET_COUNT
	if cursor == 0 {
		return {
			key = STORY_LOSSLESS_SOUL_BACKDROP_KEY,
			file = STORY_LOSSLESS_SOUL_BACKDROP_FILE,
			usage = .Backdrop,
		}, true
	}
	cursor -= STORY_SUPPORT_BACKDROP_COUNT
	if cursor < STORY_CHOICE_ICON_COUNT {
		id := Story_Choice_Icon_Id(cursor)
		return {
			key = STORY_CHOICE_ICON_ASSET_KEYS[id],
			file = STORY_CHOICE_ICON_FILES[id],
			usage = .Icon,
		}, true
	}
	return {}, false
}

@(private = "file")
story_art_file_is_safe :: proc(file: string) -> bool {
	if len(file) < 5 || file[0] == '/' || file[len(file) - 1] == '/' do return false
	if file[len(file) - 4:] != ".png" do return false
	for index in 0 ..< len(file) {
		c := file[index]
		if c == '\\' || (c == '.' && index + 1 < len(file) && file[index + 1] == '.') {
			return false
		}
		if c == '/' {
			if index == 0 || file[index - 1] == '/' do return false
			continue
		}
		if !('a' <= c && c <= 'z') && !('0' <= c && c <= '9') &&
			c != '_' && c != '-' && c != '.' {
			return false
		}
	}
	return true
}

@(private = "file")
story_sha256_is_valid :: proc(value: string) -> bool {
	if len(value) != 64 do return false
	for c in value {
		if !('0' <= c && c <= '9') && !('a' <= c && c <= 'f') do return false
	}
	return true
}

story_art_registry_is_valid :: proc() -> bool {
	for index in 0 ..< STORY_ART_ASSET_COUNT {
		def, found := story_art_def_at(index)
		if !found || def.key == "" || !story_art_file_is_safe(def.file) do return false
		for previous in 0 ..< index {
			other, other_found := story_art_def_at(previous)
			if !other_found || other.key == def.key || other.file == def.file do return false
		}
	}
	_, past_end := story_art_def_at(STORY_ART_ASSET_COUNT)
	return !past_end
}

// Verify the JSON value shape before typed unmarshal. core:encoding/json
// defaults to JSON5 and accepts trailing values, so the strict story format
// explicitly selects JSON, requires EOF, and rejects every unknown root/entry
// field. No filesystem or raylib call occurs here.
@(private = "file")
story_manifest_json_shape_is_strict :: proc(data: []u8) -> bool {
	parser := json.make_parser_from_bytes(data, spec = .JSON, parse_integers = true)
	value, parse_err := json.parse_value(&parser)
	if parse_err != .None do return false
	defer json.destroy_value(value)
	if parser.curr_token.kind != .EOF do return false

	root, root_ok := value.(json.Object)
	if !root_ok || len(root) != 3 do return false
	format_value, format_found := root["format_version"]
	count_value, count_found := root["asset_count"]
	assets_value, assets_found := root["assets"]
	if !format_found || !count_found || !assets_found do return false
	format_version, format_ok := format_value.(json.Integer)
	asset_count, count_ok := count_value.(json.Integer)
	entries, entries_ok := assets_value.(json.Object)
	if !format_ok || !count_ok || !entries_ok ||
		int(format_version) != STORY_ART_MANIFEST_FORMAT ||
		int(asset_count) != STORY_ART_ASSET_COUNT || len(entries) != STORY_ART_ASSET_COUNT {
		return false
	}

	for _, entry_value in entries {
		entry, entry_ok := entry_value.(json.Object)
		if !entry_ok || len(entry) != 2 do return false
		file_value, file_found := entry["file"]
		sha_value, sha_found := entry["sha256"]
		if !file_found || !sha_found do return false
		file, file_ok := file_value.(json.String)
		sha, sha_ok := sha_value.(json.String)
		if !file_ok || !sha_ok || file == "" || sha == "" do return false
	}
	return true
}

story_manifest_matches_registry :: proc(manifest: ^Story_Art_Manifest) -> bool {
	if manifest == nil || !story_art_registry_is_valid() ||
		manifest.format_version != STORY_ART_MANIFEST_FORMAT ||
		manifest.asset_count != STORY_ART_ASSET_COUNT ||
		len(manifest.assets) != STORY_ART_ASSET_COUNT {
		return false
	}
	for index in 0 ..< STORY_ART_ASSET_COUNT {
		def, found := story_art_def_at(index)
		if !found do return false
		entry, entry_found := manifest.assets[def.key]
		if !entry_found || entry.file != def.file || !story_sha256_is_valid(entry.sha256) {
			return false
		}
	}
	return true
}

@(private = "file")
story_manifest_decode :: proc(
	data: []u8,
	manifest: ^Story_Art_Manifest,
	arena: ^mem.Dynamic_Arena,
) -> bool {
	if manifest == nil || arena == nil || !story_manifest_json_shape_is_strict(data) {
		return false
	}
	if err := json.unmarshal(
		data,
		manifest,
		spec = .JSON,
		allocator = mem.dynamic_arena_allocator(arena),
	); err != nil {
		return false
	}
	return story_manifest_matches_registry(manifest)
}

// Pure/headless validator shared by tests, CI, and the story-asset verifier.
story_manifest_validate_data :: proc(data: []u8) -> bool {
	arena: mem.Dynamic_Arena
	mem.dynamic_arena_init(&arena)
	defer mem.dynamic_arena_destroy(&arena)
	manifest: Story_Art_Manifest
	return story_manifest_decode(data, &manifest, &arena)
}

@(private = "file")
load_story_texture :: proc(
	manifest: ^Story_Art_Manifest,
	def: Story_Art_Def,
) -> (asset: Story_Texture_Asset) {
	entry, found := manifest.assets[def.key]
	if !found || entry.file != def.file do return
	asset.tex = rl.LoadTexture(fmt.ctprintf("%s/%s", STORY_ART_ROOT, entry.file))
	if asset.tex.id == 0 do return {}
	// Relic and choice icons have a fixed authored contract. A loadable but
	// wrongly-sized icon is still a bad optional image and must use fallback.
	if def.usage == .Icon && (asset.tex.width != 32 || asset.tex.height != 32) {
		rl.UnloadTexture(asset.tex)
		return {}
	}
	asset.source_size = {int(asset.tex.width), int(asset.tex.height)}
	asset.valid = true
	return
}

@(private = "file")
load_story_assets :: proc(assets: ^Assets) {
	if assets == nil do return
	assets_unload_story(assets)
	data, read_ok := assets_read_owned("assets/story/manifest.json")
	if !read_ok {
		platform_log(fmt.tprint("assets: no MX-story art manifest found, using procedural story fallbacks"))
		return
	}
	defer delete(data)

	arena: mem.Dynamic_Arena
	mem.dynamic_arena_init(&arena)
	defer mem.dynamic_arena_destroy(&arena)
	manifest: Story_Art_Manifest
	if !story_manifest_decode(data, &manifest, &arena) {
		platform_log(fmt.tprint("assets: story manifest does not match the strict typed MX-story registry"))
		return
	}
	assets.story.manifest_valid = true

	for id in Story_Motif_Id {
		asset := load_story_texture(&manifest, {
			key = STORY_OMEN_ASSET_KEYS[id], file = STORY_OMEN_ASSET_FILES[id], usage = .Backdrop,
		})
		assets.story.omens[id] = asset
		if asset.valid do assets.story.loaded_count += 1
	}
	for id in Story_Guest_Role_Id {
		asset := load_story_texture(&manifest, {
			key = STORY_GUEST_BACKDROP_ASSET_KEYS[id],
			file = STORY_GUEST_BACKDROP_ASSET_FILES[id],
			usage = .Backdrop,
		})
		assets.story.guest_backdrops[id] = asset
		if asset.valid do assets.story.loaded_count += 1
	}
	for archetype in Archetype_Id {
		for verb in Story_Choice_Verb {
			asset := load_story_texture(&manifest, {
				key = STORY_ENDING_PANEL_ASSET_KEYS[archetype][verb],
				file = STORY_ENDING_PANEL_ASSET_FILES[archetype][verb],
				usage = .Backdrop,
			})
			assets.story.ending_panels[archetype][verb] = asset
			if asset.valid do assets.story.loaded_count += 1
		}
	}
	for id in Story_Relic_Id {
		asset := load_story_texture(&manifest, {
			key = STORY_RELIC_ICON_ASSET_KEYS[id], file = STORY_RELIC_ICON_ASSET_FILES[id], usage = .Icon,
		})
		assets.story.relic_icons[id] = asset
		if asset.valid do assets.story.loaded_count += 1
	}
	for role in Story_Guest_Role_Id {
		for variant in 0 ..< STORY_GUEST_VARIANTS {
			asset := load_story_texture(&manifest, {
				key = STORY_GUEST_PORTRAIT_ASSET_KEYS[role][variant],
				file = STORY_GUEST_PORTRAIT_ASSET_FILES[role][variant],
				usage = .Portrait,
			})
			assets.story.guest_portraits[role][variant] = asset
			if asset.valid do assets.story.loaded_count += 1
		}
	}
	assets.story.lossless_soul_backdrop = load_story_texture(&manifest, {
		key = STORY_LOSSLESS_SOUL_BACKDROP_KEY,
		file = STORY_LOSSLESS_SOUL_BACKDROP_FILE,
		usage = .Backdrop,
	})
	if assets.story.lossless_soul_backdrop.valid do assets.story.loaded_count += 1
	for id in Story_Choice_Icon_Id {
		asset := load_story_texture(&manifest, {
			key = STORY_CHOICE_ICON_ASSET_KEYS[id], file = STORY_CHOICE_ICON_FILES[id], usage = .Icon,
		})
		assets.story.choice_icons[id] = asset
		if asset.valid do assets.story.loaded_count += 1
	}
}

// Release every texture owned by the story manifest exactly once. Safe to call
// repeatedly and on a zero-value Assets object while the raylib context lives.
assets_unload_story :: proc(assets: ^Assets) {
	if assets == nil do return
	unload := proc(asset: ^Story_Texture_Asset) {
		if asset.tex.id != 0 do rl.UnloadTexture(asset.tex)
		asset^ = {}
	}
	for id in Story_Motif_Id do unload(&assets.story.omens[id])
	for id in Story_Guest_Role_Id do unload(&assets.story.guest_backdrops[id])
	for archetype in Archetype_Id do for verb in Story_Choice_Verb {
		unload(&assets.story.ending_panels[archetype][verb])
	}
	for id in Story_Relic_Id do unload(&assets.story.relic_icons[id])
	for role in Story_Guest_Role_Id do for variant in 0 ..< STORY_GUEST_VARIANTS {
		unload(&assets.story.guest_portraits[role][variant])
	}
	unload(&assets.story.lossless_soul_backdrop)
	for id in Story_Choice_Icon_Id do unload(&assets.story.choice_icons[id])
	unload(&assets.story.fallback)
	assets.story = {}
}

story_guest_actor_sprites :: proc(assets: ^Assets) -> ^Actor_Sprites {
	if assets == nil do return nil
	return &assets.story_guest
}

lossless_soul_actor_sprites :: proc(assets: ^Assets) -> ^Actor_Sprites {
	if assets == nil do return nil
	return &assets.lossless_soul
}

story_omen_backdrop_asset :: proc(assets: ^Assets, id: Story_Motif_Id) -> ^Story_Texture_Asset {
	if assets == nil do return nil
	if int(id) < 0 || int(id) >= STORY_OMEN_ASSET_COUNT do return &assets.story.fallback
	return &assets.story.omens[id]
}

story_guest_backdrop_asset :: proc(assets: ^Assets, id: Story_Guest_Role_Id) -> ^Story_Texture_Asset {
	if assets == nil do return nil
	if int(id) < 0 || int(id) >= STORY_GUEST_ASSET_COUNT do return &assets.story.fallback
	return &assets.story.guest_backdrops[id]
}

story_ending_panel_asset :: proc(
	assets: ^Assets,
	archetype: Archetype_Id,
	verb: Story_Choice_Verb,
) -> ^Story_Texture_Asset {
	if assets == nil do return nil
	if int(archetype) < 0 || int(archetype) >= len(Archetype_Id) ||
		int(verb) < 0 || int(verb) >= STORY_CHOICE_COUNT {
		return &assets.story.fallback
	}
	return &assets.story.ending_panels[archetype][verb]
}

story_relic_icon_asset :: proc(assets: ^Assets, id: Story_Relic_Id) -> ^Story_Texture_Asset {
	if assets == nil do return nil
	if int(id) < 0 || int(id) >= STORY_RELIC_ASSET_COUNT do return &assets.story.fallback
	return &assets.story.relic_icons[id]
}

story_guest_portrait_asset :: proc(
	assets: ^Assets,
	role: Story_Guest_Role_Id,
	variant: int,
) -> ^Story_Texture_Asset {
	if assets == nil do return nil
	if int(role) < 0 || int(role) >= STORY_GUEST_ASSET_COUNT ||
		variant < 0 || variant >= STORY_GUEST_VARIANTS {
		return &assets.story.fallback
	}
	return &assets.story.guest_portraits[role][variant]
}

story_lossless_soul_backdrop_asset :: proc(assets: ^Assets) -> ^Story_Texture_Asset {
	if assets == nil do return nil
	return &assets.story.lossless_soul_backdrop
}

story_choice_icon_asset :: proc(
	assets: ^Assets,
	id: Story_Choice_Icon_Id,
) -> ^Story_Texture_Asset {
	if assets == nil do return nil
	if int(id) < 0 || int(id) >= STORY_CHOICE_ICON_COUNT do return &assets.story.fallback
	return &assets.story.choice_icons[id]
}

// Story_Panel_Choice exposes the short legacy choice key. Unknown keys (for
// example the procedural bell glyph) deliberately resolve to fallback.
story_choice_icon_asset_for_key :: proc(
	assets: ^Assets,
	key: string,
) -> ^Story_Texture_Asset {
	if assets == nil do return nil
	for id in Story_Choice_Icon_Id {
		if STORY_CHOICE_ICON_NAMES[id] == key do return &assets.story.choice_icons[id]
	}
	return &assets.story.fallback
}

@(private = "file")
story_art_asset_at :: proc(assets: ^Assets, index: int) -> ^Story_Texture_Asset {
	if assets == nil || index < 0 || index >= STORY_ART_ASSET_COUNT do return nil
	cursor := index
	if cursor < STORY_OMEN_ASSET_COUNT do return &assets.story.omens[Story_Motif_Id(cursor)]
	cursor -= STORY_OMEN_ASSET_COUNT
	if cursor < STORY_GUEST_ASSET_COUNT do return &assets.story.guest_backdrops[Story_Guest_Role_Id(cursor)]
	cursor -= STORY_GUEST_ASSET_COUNT
	if cursor < STORY_ENDING_ASSET_COUNT {
		return &assets.story.ending_panels[Archetype_Id(cursor / STORY_CHOICE_COUNT)][Story_Choice_Verb(cursor % STORY_CHOICE_COUNT)]
	}
	cursor -= STORY_ENDING_ASSET_COUNT
	if cursor < STORY_RELIC_ASSET_COUNT do return &assets.story.relic_icons[Story_Relic_Id(cursor)]
	cursor -= STORY_RELIC_ASSET_COUNT
	if cursor < STORY_PORTRAIT_ASSET_COUNT {
		return &assets.story.guest_portraits[Story_Guest_Role_Id(cursor / STORY_GUEST_VARIANTS)][cursor % STORY_GUEST_VARIANTS]
	}
	cursor -= STORY_PORTRAIT_ASSET_COUNT
	if cursor == 0 do return &assets.story.lossless_soul_backdrop
	cursor -= STORY_SUPPORT_BACKDROP_COUNT
	if cursor < STORY_CHOICE_ICON_COUNT do return &assets.story.choice_icons[Story_Choice_Icon_Id(cursor)]
	return &assets.story.fallback
}

// Tooling/debug resolver for full semantic manifest keys. Rendering code should
// prefer the typed O(1) accessors above; `known` remains true when an optional
// texture failed to load, while `asset.valid` reports GPU availability.
story_art_texture_for_key :: proc(
	assets: ^Assets,
	key: string,
) -> (asset: ^Story_Texture_Asset, known: bool) {
	if assets == nil do return nil, false
	for index in 0 ..< STORY_ART_ASSET_COUNT {
		def, found := story_art_def_at(index)
		if found && def.key == key do return story_art_asset_at(assets, index), true
	}
	return &assets.story.fallback, false
}

// JSON mirror of the canonical actor manifest schema.
@(private = "file")
Baked_Manifest :: struct {
	format:       int,
	native_cells: bool,
	cell:         int,
	actors:       map[string]Baked_Actor,
}
@(private = "file")
Baked_Actor :: struct {
	cell:          int,
	source_canvas: [2]int,
	canvas_world:  f32,
	anchor:        [2]f32,
	clips:         map[string]Baked_Clip,
}
@(private = "file")
Baked_Clip :: struct {
	frames: int,
	rows:   int,
	fps:    f32,
	loop:   bool,
	sha256: string,
}

assets_load :: proc(assets: ^Assets) {
	if assets == nil do return
	// A graphics-context rebuild may call load on either a live or fully released
	// set. Centralizing the reset prevents duplicate GPU ownership in both cases.
	assets_unload(assets)

	// Keep semantic slot identities available even when the optional texture
	// manifest is absent. Each unresolved icon remains `.valid == false`.
	assets.action_loadouts = DEFAULT_ACTION_LOADOUTS
	assets.ranger_spirit_beast_attack = .Ranger_Spirit_Beast_Angry

	data, read_ok := assets_read_owned("assets/actors/manifest.json")
	if !read_ok {
		platform_log(fmt.tprint("assets: actor manifest missing, using placeholder actors"))
	} else {
		defer delete(data)
		manifest: Baked_Manifest
		if err := json.unmarshal(data, &manifest); err != nil {
			platform_log(fmt.tprint("assets: manifest parse failed:", err))
		} else if manifest.format != 2 || !manifest.native_cells {
			platform_log(fmt.tprint("assets: actor manifest is not a native-resolution pack"))
		} else {
			for id in Archetype_Id {
				assets.archetypes[id] = load_actor_sprites(
					&manifest,
					ARCHETYPES[id].sprite,
					preview_only = true,
				)
			}
			for kind in Enemy_Kind {
				assets.enemies[kind] = load_actor_sprites(&manifest, ENEMY_DEFS[kind].sprite)
			}
			for id in Boss_Id {
				assets.bosses[id] = load_actor_sprites(&manifest, BOSS_DEFS[id].sprite)
			}
			assets.familiar_wisp = load_actor_sprites(&manifest, "familiar_wisp")
			assets.familiar_crow = load_actor_sprites(&manifest, "familiar_crow")
			assets.spirit_beast = load_actor_sprites(&manifest, "spirit_beast")
			assets.shopkeeper = load_actor_sprites(&manifest, "shopkeeper")
			assets.bar_dancer = load_actor_sprites(&manifest, "bar_dancer")
			assets.garden_frog = load_actor_sprites(&manifest, "garden_frog")
			assets.story_guest = load_actor_sprites(&manifest, "story_guest")
			assets.lossless_soul = load_actor_sprites(&manifest, "lossless_soul")
		}
	}
	load_action_assets(assets)
	load_mobile_hud_assets(assets)
	load_ui_assets(assets)
	load_ui_font(assets)
	load_story_assets(assets)
	load_world_assets(assets)
	load_prop_assets(assets)
	assets.load_complete = true
	assets_log_load_summary(assets)
}

@(private = "file")
Baked_Prop_Manifest :: struct {
	format: int,
	props:  map[string]Baked_Prop_Entry,
}

@(private = "file")
Baked_Prop_Entry :: struct {
	path:         string,
	anchor:       [2]f32,
	world_height: f32,
}

@(private = "file")
load_prop_assets :: proc(assets: ^Assets) {
	data, read_ok := assets_read_owned("assets/props/manifest.json")
	if !read_ok {
		platform_log(fmt.tprint("assets: prop manifest missing, using geometry fallbacks"))
		return
	}
	defer delete(data)
	manifest: Baked_Prop_Manifest
	if err := json.unmarshal(data, &manifest); err != nil {
		platform_log(fmt.tprint("assets: prop manifest parse failed:", err))
		return
	}
	for key in Prop_Key {
		entry, found := manifest.props[PROP_KEY_NAMES[key]]
		if !found do continue
		tex := rl.LoadTexture(fmt.ctprintf("assets/props/%s", entry.path))
		if tex.id == 0 do continue
		assets.props[key] = {tex = tex, anchor = entry.anchor, world_height = entry.world_height, loaded = true}
	}
}

// The active UI typeface. Loaded once at a large base size over the strict
// Latin-1 glyph contract enforced by tests/text_glyphs_test.odin, then scaled
// and uppercased through the ui_draw_text/ui_measure_text seam.
UI_FONT_FILE :: "assets/ui/fonts/EditUndoBRK.ttf"
UI_FONT_BASE_SIZE :: 96

@(private = "file")
load_ui_font :: proc(assets: ^Assets) {
	codepoints: [0xE0]rune
	for i in 0 ..< len(codepoints) do codepoints[i] = rune(0x20 + i)
	font := rl.LoadFontEx(UI_FONT_FILE, UI_FONT_BASE_SIZE, raw_data(codepoints[:]), i32(len(codepoints)))
	if font.texture.id == 0 || font.glyphCount <= 0 {
		platform_log(fmt.tprint("assets: UI font missing, using raylib default text"))
		ui_set_active_font({}, false)
		return
	}
	// Text draws at many scales; a large base plus trilinear mipmaps keeps
	// minified text readable and magnified headers acceptably smooth.
	rl.GenTextureMipmaps(&font.texture)
	rl.SetTextureFilter(font.texture, .TRILINEAR)
	assets.ui_font = font
	assets.ui_font_loaded = true
	ui_set_active_font(font, true)
}

// JSON mirror of the canonical action-HUD manifest schema.
@(private = "file")
Baked_Action_Manifest :: struct {
	format_version: int,
	icons:          map[string]Baked_Action_Icon,
	loadouts:       map[string][]string,
	variants:       map[string]string,
}

@(private = "file")
Baked_Action_Icon :: struct {
	file: string,
	size: [2]int,
}

action_icon_from_key :: proc(key: string) -> (Action_Icon, bool) {
	for icon in Action_Icon {
		if icon != .Invalid && ACTION_ICON_KEYS[icon] == key do return icon, true
	}
	return .Invalid, false
}

@(private = "file")
load_action_assets :: proc(assets: ^Assets) {
	data, read_ok := assets_read_owned("assets/hud/manifest.json")
	if !read_ok {
		platform_log(fmt.tprint("assets: action HUD manifest missing, using placeholder icons"))
		return
	}
	defer delete(data)

	manifest: Baked_Action_Manifest
	if err := json.unmarshal(data, &manifest); err != nil {
		platform_log(fmt.tprint("assets: action HUD manifest parse failed:", err))
		return
	}

	for icon in Action_Icon {
		if icon == .Invalid do continue
		entry, found := manifest.icons[ACTION_ICON_KEYS[icon]]
		if !found do continue
		tex := rl.LoadTexture(fmt.ctprintf("assets/hud/%s", entry.file))
		if tex.id == 0 do continue
		assets.action_icons[icon] = {tex = tex, size = entry.size, valid = true}
	}

	// The checked-in defaults above are also the missing/malformed-manifest
	// fallback. Valid manifest entries may replace individual semantic slots.
	for archetype in Archetype_Id {
		keys, found := manifest.loadouts[ARCHETYPES[archetype].sprite]
		if !found do continue
		for key, slot_index in keys {
			if slot_index >= ACTION_SLOT_COUNT do break
			if icon, valid := action_icon_from_key(key); valid {
				assets.action_loadouts[archetype][slot_index] = icon
			}
		}
	}

	if key, found := manifest.variants["ranger_spirit_beast_attack"]; found {
		if icon, valid := action_icon_from_key(key); valid {
			assets.ranger_spirit_beast_attack = icon
		}
	}
}

@(private = "file")
load_mobile_hud_assets :: proc(assets: ^Assets) {
	if assets == nil do return
	for id in Mobile_Hud_Asset_Id {
		def := MOBILE_HUD_ASSET_DEFS[id]
		tex := rl.LoadTexture(fmt.ctprintf("assets/hud/%s", def.file))
		if tex.id == 0 do continue
		assets.mobile_hud[id] = {tex = tex, size = def.size, valid = true}
	}
}

mobile_hud_asset :: proc(assets: ^Assets, id: Mobile_Hud_Asset_Id) -> ^Mobile_Hud_Asset {
	return &assets.mobile_hud[id]
}

// Renderer-facing accessors. `slot` is the player-facing hotkey number 1..6;
// invalid indices and missing textures return the shared zero-value asset.
action_icon_asset :: proc(assets: ^Assets, icon: Action_Icon) -> ^Action_Icon_Asset {
	return &assets.action_icons[icon]
}

action_icon_for_slot :: proc(
	assets: ^Assets,
	archetype: Archetype_Id,
	slot: int,
) -> ^Action_Icon_Asset {
	if slot < 1 || slot > ACTION_SLOT_COUNT do return &assets.action_icons[.Invalid]
	icon := assets.action_loadouts[archetype][slot - 1]
	return &assets.action_icons[icon]
}

action_slot_frame :: proc(assets: ^Assets) -> ^Action_Icon_Asset {
	return &assets.action_icons[.Slot_Frame]
}

ranger_spirit_beast_action_icon :: proc(
	assets: ^Assets,
	attacking: bool,
) -> ^Action_Icon_Asset {
	icon := attacking ? assets.ranger_spirit_beast_attack : .Ranger_Spirit_Beast
	return &assets.action_icons[icon]
}

@(private = "file")
ui_chrome_metadata :: proc(def: UI_Chrome_Def) -> UI_Chrome_Asset {
	return UI_Chrome_Asset {
		render = def.render,
		source_size = def.source_size,
		insets = def.insets,
		has_insets = def.has_insets,
		content_insets = def.content_insets,
		has_content_insets = def.has_content_insets,
		scale_insets_with_height = def.scale_insets_with_height,
		scale_insets_with_fit = def.scale_insets_with_fit,
		tile_edges = def.tile_edges,
		shrink_insets_below_height = def.shrink_insets_below_height,
	}
}

@(private = "file")
ui_expected_glyph_region :: proc(ordinal: int) -> [4]int {
	return {
		(ordinal % UI_GLYPH_ATLAS_COLUMNS) * UI_GLYPH_ATLAS_CELL,
		(ordinal / UI_GLYPH_ATLAS_COLUMNS) * UI_GLYPH_ATLAS_CELL,
		UI_GLYPH_ATLAS_CELL,
		UI_GLYPH_ATLAS_CELL,
	}
}

@(private = "file")
ui_glyph_region :: proc(ordinal: int) -> UI_Glyph_Region {
	region := ui_expected_glyph_region(ordinal)
	return UI_Glyph_Region {
		source = {
			x = f32(region[0]),
			y = f32(region[1]),
			width = f32(region[2]),
			height = f32(region[3]),
		},
		source_size = {UI_GLYPH_ATLAS_CELL, UI_GLYPH_ATLAS_CELL},
		valid = true,
	}
}

@(private = "file")
load_ui_assets :: proc(assets: ^Assets) {
	// Repeated loads are lifecycle-safe; callers still explicitly unload before
	// CloseWindow so every texture is released while the graphics context lives.
	assets_unload_ui(assets)

	for id in UI_Chrome_Id {
		def := UI_CHROME_DEFS[id]
		asset := ui_chrome_metadata(def)
		asset.tex = rl.LoadTexture(fmt.ctprintf("assets/ui/%s", def.file))
		asset.valid = asset.tex.id != 0
		assets.ui_chrome[id] = asset
	}

	logo_tex := rl.LoadTexture(fmt.ctprintf("%s", UI_LOGO_DIAMOND_ATLAS_FILE))
	assets.ui_logo_animation = {
		tex = logo_tex,
		size = UI_LOGO_DIAMOND_ATLAS_SIZE,
		frame_size = UI_LOGO_DIAMOND_FRAME_SIZE,
		frame_count = UI_LOGO_DIAMOND_FRAME_COUNT,
		fps = UI_LOGO_DIAMOND_FPS,
		logo_source_rect = UI_LOGO_DIAMOND_SOURCE_RECT,
		loaded = logo_tex.id != 0,
	}

	atlas_rows := (UI_DISCIPLINE_GLYPH_COUNT + UI_STORY_SIGIL_COUNT + UI_GLYPH_ATLAS_COLUMNS - 1) /
		UI_GLYPH_ATLAS_COLUMNS
	atlas_tex := rl.LoadTexture(fmt.ctprintf("%s", UI_GLYPH_ATLAS_FILE))
	assets.ui_glyph_atlas.tex = atlas_tex
	assets.ui_glyph_atlas.size = {
		UI_GLYPH_ATLAS_COLUMNS * UI_GLYPH_ATLAS_CELL,
		atlas_rows * UI_GLYPH_ATLAS_CELL,
	}
	if atlas_tex.id == 0 do return

	for id in Discipline_Id {
		assets.ui_glyph_atlas.disciplines[id] = ui_glyph_region(int(id))
	}
	for id in Story_Sigil_Id {
		ordinal := UI_DISCIPLINE_GLYPH_COUNT + int(id)
		assets.ui_glyph_atlas.story_sigils[id] = ui_glyph_region(ordinal)
	}
	assets.ui_glyph_atlas.ouroboros = assets.ui_glyph_atlas.story_sigils[.Ouroboros]
	assets.ui_glyph_atlas.loaded = true
}

// Explicitly release every texture owned by the MX.1 UI pack. Call this while
// the raylib window/context is still alive. Glyph regions are non-owning views,
// so the shared atlas is unloaded exactly once.
assets_unload_ui :: proc(assets: ^Assets) {
	if assets == nil do return
	for id in UI_Chrome_Id {
		if assets.ui_chrome[id].tex.id != 0 do rl.UnloadTexture(assets.ui_chrome[id].tex)
	}
	if assets.ui_logo_animation.tex.id != 0 do rl.UnloadTexture(assets.ui_logo_animation.tex)
	if assets.ui_glyph_atlas.tex.id != 0 do rl.UnloadTexture(assets.ui_glyph_atlas.tex)
	assets.ui_chrome = {}
	assets.ui_logo_animation = {}
	assets.ui_glyph_atlas = {}
}

ui_chrome_def :: proc(id: UI_Chrome_Id) -> UI_Chrome_Def {
	return UI_CHROME_DEFS[id]
}

ui_chrome_asset :: proc(assets: ^Assets, id: UI_Chrome_Id) -> ^UI_Chrome_Asset {
	return &assets.ui_chrome[id]
}

ui_discipline_panel :: proc(assets: ^Assets, archetype: Archetype_Id) -> ^UI_Chrome_Asset {
	return &assets.ui_chrome[UI_DISCIPLINE_PANELS[archetype]]
}

ui_discipline_glyph :: proc(assets: ^Assets, id: Discipline_Id) -> UI_Glyph_Asset {
	region := assets.ui_glyph_atlas.disciplines[id]
	return {
		tex = assets.ui_glyph_atlas.tex,
		source = region.source,
		source_size = region.source_size,
		valid = assets.ui_glyph_atlas.loaded && region.valid,
	}
}

ui_story_sigil_glyph :: proc(assets: ^Assets, id: Story_Sigil_Id) -> UI_Glyph_Asset {
	region := assets.ui_glyph_atlas.story_sigils[id]
	return {
		tex = assets.ui_glyph_atlas.tex,
		source = region.source,
		source_size = region.source_size,
		valid = assets.ui_glyph_atlas.loaded && region.valid,
	}
}

ui_ouroboros_glyph :: proc(assets: ^Assets) -> UI_Glyph_Asset {
	region := assets.ui_glyph_atlas.ouroboros
	return {
		tex = assets.ui_glyph_atlas.tex,
		source = region.source,
		source_size = region.source_size,
		valid = assets.ui_glyph_atlas.loaded && region.valid,
	}
}

// JSON mirror of the canonical world manifest schema.
@(private = "file")
Baked_World_Manifest :: struct {
	world: map[string]Baked_World_Entry,
	items: map[string]Baked_Item_Entry,
}
@(private = "file")
Baked_World_Entry :: struct {
	variants:  []string,
	frames:    []string,
	anchor:    [2]f32,
	ref_width: int,
	tint:      f32,
	fps:       f32,
	ping_pong: bool,
}
@(private = "file")
Baked_Item_Entry :: struct {
	file:    string,
	anchor:  [2]f32,
	world_h: f32,
}

@(private = "file")
load_world_assets :: proc(assets: ^Assets) {
	data, read_ok := assets_read_owned("assets/world/manifest.json")
	if !read_ok {
		platform_log(fmt.tprint("assets: world manifest missing, using debug geometry"))
		return
	}
	defer delete(data)
	manifest: Baked_World_Manifest
	if err := json.unmarshal(data, &manifest); err != nil {
		platform_log(fmt.tprint("assets: world manifest parse failed:", err))
		return
	}

	for key in World_Key {
		entry, found := manifest.world[WORLD_KEY_NAMES[key]]
		if !found do continue
		sprite: World_Sprite
		sprite.anchor = entry.anchor
		sprite.tint = entry.tint
		sprite.fps = entry.fps
		sprite.ping_pong = entry.ping_pong
		sprite.scale = entry.ref_width > 0 ? f32(TILE_W) / f32(entry.ref_width) : 1
		for file in entry.variants {
			if sprite.variant_count >= MAX_WORLD_FRAMES do break
			tex := load_world_texture(file)
			if tex.id == 0 do continue
			sprite.variants[sprite.variant_count] = tex
			sprite.variant_count += 1
		}
		for file in entry.frames {
			if sprite.frame_count >= MAX_WORLD_FRAMES do break
			tex := load_world_texture(file)
			if tex.id == 0 do continue
			sprite.frames[sprite.frame_count] = tex
			sprite.frame_count += 1
		}
		sprite.loaded = sprite.variant_count > 0 || sprite.frame_count > 0
		assets.world[key] = sprite
	}

	assets.items = make(map[string]Item_Icon)
	for key, entry in manifest.items {
		tex := rl.LoadTexture(fmt.ctprintf("assets/world/%s", entry.file))
		if tex.id == 0 do continue
		assets.items[key] = Item_Icon{tex = tex, anchor = entry.anchor, world_h = entry.world_h, loaded = true}
	}
}

// HD world art renders well below native size (512 px spanning 64-128 world
// px), so it needs mipmaps + trilinear or it shimmers during camera pans.
@(private = "file")
load_world_texture :: proc(file: string) -> rl.Texture2D {
	tex := rl.LoadTexture(fmt.ctprintf("assets/world/%s", file))
	if tex.id != 0 {
		rl.GenTextureMipmaps(&tex)
		rl.SetTextureFilter(tex, .TRILINEAR)
	}
	return tex
}

@(private = "file")
load_actor_texture :: proc(path:cstring,cell,frames,rows:int)->rl.Texture2D {
	if cell<=0||frames<=0||rows<=0 do return {}
	tex:=rl.LoadTexture(path)
	if tex.id==0 do return {}
	if int(tex.width)!=frames*cell||int(tex.height)!=rows*cell {
		platform_log(fmt.tprint("assets: actor sheet geometry mismatch:",path))
		rl.UnloadTexture(tex)
		return {}
	}
	// PixelLab actor pixels remain exact in GPU memory. Filtering is explicit so
	// platform defaults cannot silently blur or resample the authored pixel grid.
	rl.SetTextureFilter(tex,.POINT)
	return tex
}

@(private = "file")
load_actor_sprites :: proc(
	manifest: ^Baked_Manifest,
	name: string,
	preview_only: bool = false,
) -> (sprites: Actor_Sprites) {
	baked, found := manifest.actors[name]
	if !found do return sprites
	sprites.cell = baked.cell > 0 ? baked.cell : manifest.cell
	if baked.source_canvas[0]!=sprites.cell||baked.source_canvas[1]!=sprites.cell {
		platform_log(fmt.tprint("assets: actor source cell was resampled:",name))
		return sprites
	}
	sprites.canvas_world = baked.canvas_world
	sprites.anchor = baked.anchor
	clip_names := CLIP_NAMES
	for kind in Clip_Kind {
		clip, has := baked.clips[clip_names[kind]]
		if !has do continue
		// Keep metadata for lazy player activation even when startup loads only
		// the one-row carousel preview.
		sprites.clips[kind] = {{},clip.frames,clip.fps,clip.loop,false}
		if preview_only && kind != .Preview_Idle do continue
		path := fmt.ctprintf("assets/actors/%s/%s.png", name, clip_names[kind])
		rows:=clip.rows>0?clip.rows:(kind==.Preview_Idle?1:8)
		tex:=load_actor_texture(path,sprites.cell,clip.frames,rows)
		if tex.id==0 do continue
		sprites.clips[kind].tex=tex
		sprites.clips[kind].valid=true
	}
	// Social actors such as the bar dancer and garden frogs deliberately ship
	// only walk+dance. A valid authored clip is enough; the renderer chooses an
	// available fallback when a requested state is absent.
	sprites.loaded = false
	for clip in sprites.clips {
		if clip.valid {
			sprites.loaded = true
			break
		}
	}
	return sprites
}

// Keep only one playable archetype's complete 8-direction clip set resident.
// Five native-resolution one-row previews remain loaded for Select; switching
// archetypes between runs releases the previous full set before loading the new.
assets_activate_player :: proc(assets: ^Assets, selected: Archetype_Id) {
	if assets == nil do return
	for id in Archetype_Id {
		sprites := &assets.archetypes[id]
		for kind in Clip_Kind {
			if kind == .Preview_Idle do continue
			clip := &sprites.clips[kind]
			if clip.tex.id != 0 do rl.UnloadTexture(clip.tex)
			clip.tex = {}
			clip.valid = false
		}
	}

	sprites := &assets.archetypes[selected]
	name := ARCHETYPES[selected].sprite
	clip_names := CLIP_NAMES
	for kind in Clip_Kind {
		if kind == .Preview_Idle do continue
		clip := &sprites.clips[kind]
		if clip.frames <= 0 do continue
		path := fmt.ctprintf("assets/actors/%s/%s.png",name,clip_names[kind])
		clip.tex=load_actor_texture(path,sprites.cell,clip.frames,8)
		clip.valid=clip.tex.id!=0
	}
	sprites.loaded = sprites.clips[.Preview_Idle].valid
	for kind in Clip_Kind {
		if kind != .Preview_Idle && sprites.clips[kind].valid do sprites.loaded = true
	}
}

@(private = "file")
assets_unload_actor_textures :: proc(assets: ^Assets) {
	if assets == nil do return
	unload_sprites :: proc(sprites: ^Actor_Sprites) {
		for &clip in sprites.clips {
			if clip.tex.id != 0 do rl.UnloadTexture(clip.tex)
		}
		sprites^ = {}
	}
	for id in Archetype_Id do unload_sprites(&assets.archetypes[id])
	for kind in Enemy_Kind do unload_sprites(&assets.enemies[kind])
	for id in Boss_Id do unload_sprites(&assets.bosses[id])
	unload_sprites(&assets.familiar_wisp)
	unload_sprites(&assets.familiar_crow)
	unload_sprites(&assets.spirit_beast)
	unload_sprites(&assets.shopkeeper)
	unload_sprites(&assets.bar_dancer)
	unload_sprites(&assets.garden_frog)
	unload_sprites(&assets.story_guest)
	unload_sprites(&assets.lossless_soul)
}

// Release every GPU texture owned by Assets exactly once. Resetting all slots
// and the item map makes this idempotent and leaves assets_load a clean target
// for Android surface recreation.
assets_unload :: proc(assets: ^Assets) {
	if assets == nil do return
	for &asset in assets.action_icons {
		if asset.tex.id != 0 do rl.UnloadTexture(asset.tex)
	}
	for &asset in assets.mobile_hud {
		if asset.tex.id != 0 do rl.UnloadTexture(asset.tex)
	}
	for &sprite in assets.world {
		for &tex in sprite.variants {
			if tex.id != 0 do rl.UnloadTexture(tex)
		}
		for &tex in sprite.frames {
			if tex.id != 0 do rl.UnloadTexture(tex)
		}
	}
	for _, item in assets.items {
		if item.tex.id != 0 do rl.UnloadTexture(item.tex)
	}
	delete(assets.items)
	for &prop in assets.props {
		if prop.tex.id != 0 do rl.UnloadTexture(prop.tex)
	}
	assets_unload_ui(assets)
	assets_unload_actor_textures(assets)
	assets_unload_story(assets)
	if assets.ui_font_loaded do rl.UnloadFont(assets.ui_font)
	ui_set_active_font({}, false)
	assets^ = {}
}

// Compatibility shutdown hook retained for the existing desktop entry point.
// It now owns the complete lifecycle; the separately deferred UI unload is a
// safe no-op after this call.
assets_unload_actors :: proc(assets: ^Assets) {
	assets_unload(assets)
}

when ARCH_ROGUE_WEB {

// Re-resolve lazily fetched actors after their pack lands in MEMFS. Pack
// arrivals are rare, so re-parsing the small boot manifest here is cheaper
// than retaining it for the whole session.
assets_web_adopt_actors :: proc(assets: ^Assets, names: []string, active: Archetype_Id, active_valid: bool) {
	if assets == nil || len(names) == 0 do return
	data, read_ok := assets_read_owned("assets/actors/manifest.json")
	if !read_ok do return
	defer delete(data)
	manifest: Baked_Manifest
	if err := json.unmarshal(data, &manifest); err != nil {
		platform_log(fmt.tprint("assets: web pack manifest re-parse failed:", err))
		return
	}
	for name in names {
		if assets_web_adopt_archetype(assets, &manifest, name, active, active_valid) do continue
		if assets_web_adopt_slot(assets, &manifest, name) do continue
		platform_log(fmt.tprintf("assets: web pack delivered unknown actor %s", name))
	}
}

@(private = "file")
assets_web_adopt_archetype :: proc(assets: ^Assets, manifest: ^Baked_Manifest, name: string, active: Archetype_Id, active_valid: bool) -> bool {
	for id in Archetype_Id {
		if ARCHETYPES[id].sprite != name do continue
		// Previews shipped in the core payload; the full 8-direction set only
		// becomes GPU-resident for the archetype that is actually being played.
		if active_valid && id == active do assets_activate_player(assets, id)
		return true
	}
	return false
}

@(private = "file")
assets_web_adopt_slot :: proc(assets: ^Assets, manifest: ^Baked_Manifest, name: string) -> bool {
	for kind in Enemy_Kind {
		if ENEMY_DEFS[kind].sprite == name {
			assets_web_replace_sprites(&assets.enemies[kind], manifest, name)
			return true
		}
	}
	for id in Boss_Id {
		if BOSS_DEFS[id].sprite == name {
			assets_web_replace_sprites(&assets.bosses[id], manifest, name)
			return true
		}
	}
	switch name {
	case "familiar_wisp": assets_web_replace_sprites(&assets.familiar_wisp, manifest, name)
	case "familiar_crow": assets_web_replace_sprites(&assets.familiar_crow, manifest, name)
	case "spirit_beast": assets_web_replace_sprites(&assets.spirit_beast, manifest, name)
	case "shopkeeper": assets_web_replace_sprites(&assets.shopkeeper, manifest, name)
	case "bar_dancer": assets_web_replace_sprites(&assets.bar_dancer, manifest, name)
	case "garden_frog": assets_web_replace_sprites(&assets.garden_frog, manifest, name)
	case "story_guest": assets_web_replace_sprites(&assets.story_guest, manifest, name)
	case "lossless_soul": assets_web_replace_sprites(&assets.lossless_soul, manifest, name)
	case:
		return false
	}
	return true
}

@(private = "file")
assets_web_replace_sprites :: proc(slot: ^Actor_Sprites, manifest: ^Baked_Manifest, name: string) {
	for &clip in slot.clips {
		if clip.tex.id != 0 do rl.UnloadTexture(clip.tex)
	}
	slot^ = load_actor_sprites(manifest, name)
}

}

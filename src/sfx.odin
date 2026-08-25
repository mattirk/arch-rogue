package archrogue

// Raylib-free semantic sound-effect policy. Simulation emits meaning; the
// presentation audio layer owns files, variants, voice limits, and pitch.

Sfx_Bank :: enum {
	Ui_Navigate,
	Ui_Confirm,
	Ui_Back,
	Ui_Reject,
	Ui_Equip,
	Ui_Purchase,
	Run_Start,
	Level_Up,
	Victory,
	Story_Consequence,
	Relic_Recovered,
	Epilogue_Bell,
	Melee_Swing_Warden,
	Melee_Swing_Rogue,
	Melee_Swing_Arcanist,
	Melee_Swing_Acolyte,
	Melee_Swing_Ranger,
	Big_Hit_Charge,
	Big_Hit_Release,
	Dash_Cloth_Light,
	Dash_Armored,
	Dash_Arcane,
	Dash_Occult,
	Shield_Block,
	Player_Hurt_Light,
	Player_Hurt_Heavy,
	Player_Death,
	Bow_Release_Light,
	Bow_Release_Heavy,
	Arrow_Volley,
	Physical_Throw,
	Warden_Guard_Bolt,
	Arcane_Cast,
	Fire_Cast,
	Frost_Cast,
	Shadow_Cast,
	Warden_Time_Skip,
	Rogue_Bell_Cast,
	Rogue_Bell_Detonate,
	Rogue_Stealth,
	Arcanist_Nova,
	Acolyte_Spirit_Call,
	Ranger_Beast_Summon,
	Ranger_Beast_Command,
	Impact_Generic,
	Impact_Flesh,
	Impact_Armor,
	Impact_Heavy,
	Impact_Lethal,
	Impact_Bone_Lethal,
	Coin_Pickup_Light,
	Coin_Pickup_Medium,
	Item_Pickup_Common,
	Item_Pickup_Rare,
	Item_Pickup_Unique,
	Item_Pickup_Cursed,
	Item_Drop,
	Potion_Drink,
	Bar_Toast,
	Soulless_Clanker,
	Enemy_Attack_Light,
	Enemy_Attack_Brute,
	Enemy_Attack_Armored,
	Enemy_Bow_Release,
	Enemy_Arcane_Cast,
	Enemy_Poison_Cast,
	Boss_Engage,
	Boss_Defeat,
	Ash_Gallows_Cleave,
	Ash_Gallows_Nova,
	Mycelial_Spore_Volley,
	Rime_Frost_Fan,
	Void_Arcane_Lance,
	Gate_Tyrant_Strike,
	Gate_Tyrant_Volley,
	Door_Open,
	Lock_Denied,
	Boss_Gate_Close,
	Boss_Gate_Open,
	Stairs_Descend,
	Trap_Spike,
	Trap_Rune,
	Trap_Needle,
	Shrine_Mending,
	Shrine_Insight,
	Shrine_War,
	Shrine_Haste,
	Shrine_Fortune,
	Shrine_Oath,
	Shrine_Twilight,
	Secret_Unlock,
	Step_Boot_Hard,
	Step_Boot_Hard_Light,
	Step_Boot_Dirt,
	Step_Boot_Dirt_Light,
	Step_Boot_Grass,
	Step_Armor_Light,
	Step_Armor_Medium,
	Step_Armor_Heavy,
	Step_Creature_Heavy,
}

Sfx_Event_Kind :: enum {
	Play,
	Stop_Bank,
}

Sfx_Event :: struct {
	kind:       Sfx_Event_Kind,
	bank:       Sfx_Bank,
	pos:        Vec2,
	spatial:    bool,
	emitter_id: u64,
}

MAX_SFX_EVENTS_PER_FRAME :: 128

sfx_emit :: proc(
	run: ^Run,
	bank: Sfx_Bank,
	pos: Vec2 = {},
	spatial: bool = false,
	emitter_id: u64 = 0,
) {
	if run == nil || len(run.sfx) >= MAX_SFX_EVENTS_PER_FRAME do return
	append(&run.sfx, Sfx_Event{kind = .Play, bank = bank, pos = pos, spatial = spatial, emitter_id = emitter_id})
}

sfx_stop_bank :: proc(run: ^Run, bank: Sfx_Bank) {
	if run == nil do return
	event := Sfx_Event{kind = .Stop_Bank, bank = bank}
	if len(run.sfx) < MAX_SFX_EVENTS_PER_FRAME {
		append(&run.sfx, event)
		return
	}
	// Control events must survive a saturated combat frame. Sacrifice the newest
	// queued play rather than letting a cancelable/looping sound outlive its owner.
	replacement := -1
	for queued, index in run.sfx do if queued.kind == .Play do replacement = index
	if replacement >= 0 do run.sfx[replacement] = event
}

sfx_player_melee_bank :: proc(archetype: Archetype_Id) -> Sfx_Bank {
	switch archetype {
	case .Warden:   return .Melee_Swing_Warden
	case .Rogue:    return .Melee_Swing_Rogue
	case .Arcanist: return .Melee_Swing_Arcanist
	case .Acolyte:  return .Melee_Swing_Acolyte
	case .Ranger:   return .Melee_Swing_Ranger
	}
	return .Melee_Swing_Warden
}

sfx_player_dash_bank :: proc(archetype: Archetype_Id) -> Sfx_Bank {
	switch archetype {
	case .Warden:   return .Dash_Armored
	case .Rogue:    return .Dash_Cloth_Light
	case .Arcanist: return .Dash_Arcane
	case .Acolyte:  return .Dash_Occult
	case .Ranger:   return .Dash_Cloth_Light
	}
	return .Dash_Cloth_Light
}

sfx_item_pickup_bank :: proc(rarity: Rarity) -> Sfx_Bank {
	switch rarity {
	case .Common, .Magic, .Unidentified: return .Item_Pickup_Common
	case .Rare:                           return .Item_Pickup_Rare
	case .Unique, .Legendary:             return .Item_Pickup_Unique
	case .Cursed:                         return .Item_Pickup_Cursed
	}
	return .Item_Pickup_Common
}

sfx_trap_bank :: proc(kind: Trap_Kind) -> Sfx_Bank {
	switch kind {
	case .Spike:  return .Trap_Spike
	case .Rune:   return .Trap_Rune
	case .Needle: return .Trap_Needle
	}
	return .Trap_Spike
}

sfx_shrine_bank :: proc(kind: Shrine_Kind) -> Sfx_Bank {
	switch kind {
	case .Mending:  return .Shrine_Mending
	case .Insight:  return .Shrine_Insight
	case .War:      return .Shrine_War
	case .Haste:    return .Shrine_Haste
	case .Fortune:  return .Shrine_Fortune
	case .Oath:     return .Shrine_Oath
	case .Twilight: return .Shrine_Twilight
	}
	return .Shrine_Mending
}

sfx_ability_bank :: proc(ability: Ability_Id) -> Sfx_Bank {
	switch ability {
	case .Ember_Cleave:  return .Ash_Gallows_Cleave
	case .Ember_Nova:    return .Ash_Gallows_Nova
	case .Spore_Volley:  return .Mycelial_Spore_Volley
	case .Frost_Fan:     return .Rime_Frost_Fan
	case .Arcane_Lance:  return .Void_Arcane_Lance
	case .Gate_Strike:   return .Gate_Tyrant_Strike
	case .Shadow_Volley: return .Gate_Tyrant_Volley
	}
	return .Enemy_Attack_Light
}

sfx_enemy_attack_bank :: proc(enemy: ^Enemy) -> Sfx_Bank {
	if enemy == nil do return .Enemy_Attack_Light
	if enemy.ranged {
		#partial switch enemy.damage_type {
		case .Poison: return .Enemy_Poison_Cast
		case .Arcane, .Fire, .Frost, .Shadow, .Holy: return .Enemy_Arcane_Cast
		case: return .Enemy_Bow_Release
		}
	}
	if enemy.role == .Boss || enemy.role == .Miniboss || enemy.kind == .Crypt_Brute {
		return .Enemy_Attack_Brute
	}
	if enemy.kind == .Rune_Sentinel || enemy.kind == .Hollow_Knight || enemy.kind == .Gate_Warden {
		return .Enemy_Attack_Armored
	}
	return .Enemy_Attack_Light
}

sfx_enemy_impact_bank :: proc(enemy: ^Enemy, lethal: bool = false, heavy: bool = false) -> Sfx_Bank {
	if enemy == nil do return lethal ? .Impact_Lethal : .Impact_Generic
	bone := enemy.kind == .Bone_Imp || enemy.kind == .Grave_Archer
	armored := enemy.kind == .Rune_Sentinel || enemy.kind == .Hollow_Knight || enemy.kind == .Gate_Warden
	if lethal do return bone ? .Impact_Bone_Lethal : .Impact_Lethal
	if heavy || enemy.role == .Boss || enemy.role == .Miniboss || enemy.kind == .Crypt_Brute do return .Impact_Heavy
	if armored do return .Impact_Armor
	#partial switch enemy.kind {
	case .Ghoul, .Venom_Skitter, .Ash_Hound, .Plague_Toad: return .Impact_Flesh
	case: return .Impact_Generic
	}
}

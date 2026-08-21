package archrogue

// Steam achievement funnel (STEAM.md S2), porting the pygame design that
// mattered more than its list: one evaluation choke point over a flat facts
// view, declarative triggers, an idempotent granted cache in the profile, and
// retroactive startup grants. The 39 API ids and titles are the fixed contract
// with Steamworks App Admin (authored and verified there in the pygame era);
// trigger literals reference this codebase's stable save-id strings, pinned by
// tests against the content tables. This file stays raylib-free and
// Steam-free: the platform facade consumes what evaluation returns.

Achievement_Id :: enum u8 {
	Depth_3, Depth_5, Depth_8, Depth_10,
	First_Clear, Clears_10, Clear_Hard, Clear_Hell,
	Clear_Warden, Clear_Rogue, Clear_Arcanist, Clear_Acolyte, Clear_Ranger,
	Clear_Every_Archetype,
	Boss_Ash_Gallows, Boss_Mycelial_Matron, Boss_Rime_Chanter, Boss_Void_Sentinel, Boss_Gate_Tyrant,
	Boss_Bestiary,
	Gate_Aid, Gate_Bargain, Gate_Defy, Gate_All_Answers,
	Themes_All, Modifiers_All, Legendary_10,
	Secrets_25, Shrines_20, Kills_1000, Runs_50,
	Coop_Run, Coop_Clear,
	Depth_1_Death, Dry_Clear, Bar_Pilgrim,
	Wallfacer, Elite_Hunter, Challenger,
}

Achievement_Fact :: enum u8 {
	None,
	// Lifetime counters (profile).
	Best_Depth, Clears, Runs_Started, Lifetime_Kills,
	Lifetime_Secrets, Lifetime_Shrines, Lifetime_Wall_Touches, Coop_Clears,
	// Lifetime union sets (profile, stable save-id strings).
	Victory_Difficulties, Victory_Archetypes, Bosses_Defeated,
	Story_Verbs, Themes_Seen, Modifiers_Seen, Uniques_Seen,
	// Facts of the run that just ended (absent during retroactive startup
	// evaluation; conditions on them then fail closed).
	Run_Is_Death, Run_Is_Victory, Run_Depth, Run_Potions_Used,
	Run_Elites_Killed, Run_Challenge_Rooms, Run_Bar_Pilgrim, Run_Coop,
}

Achievement_Op :: enum u8 {
	None,
	Counter_At_Least,
	Counter_At_Most,
	Set_Contains,
	Set_Complete,
	Set_Size_At_Least,
	Flag_Set,
}

Achievement_Condition :: struct {
	fact:      Achievement_Fact,
	op:        Achievement_Op,
	threshold: int,
	literal:   string,
}

Achievement_Def :: struct {
	api_id:          string, // App Admin API name; the partner-site contract
	title:           string, // display title mirrored in App Admin
	conditions:      [2]Achievement_Condition,
	condition_count: int,
}

@(rodata)
ACHIEVEMENT_DEFS := [Achievement_Id]Achievement_Def{
	.Depth_3  = {api_id="ACH_DEPTH_3", title="Past the Threshold", conditions={{fact=.Best_Depth, op=.Counter_At_Least, threshold=3}, {}}, condition_count=1},
	.Depth_5  = {api_id="ACH_DEPTH_5", title="Halfway Buried", conditions={{fact=.Best_Depth, op=.Counter_At_Least, threshold=5}, {}}, condition_count=1},
	.Depth_8  = {api_id="ACH_DEPTH_8", title="Where the Light Fails", conditions={{fact=.Best_Depth, op=.Counter_At_Least, threshold=8}, {}}, condition_count=1},
	.Depth_10 = {api_id="ACH_DEPTH_10", title="At the Gate", conditions={{fact=.Best_Depth, op=.Counter_At_Least, threshold=10}, {}}, condition_count=1},
	.First_Clear = {api_id="ACH_FIRST_CLEAR", title="The Gate Answered", conditions={{fact=.Clears, op=.Counter_At_Least, threshold=1}, {}}, condition_count=1},
	.Clears_10   = {api_id="ACH_CLEARS_10", title="Ten Descents Deep", conditions={{fact=.Clears, op=.Counter_At_Least, threshold=10}, {}}, condition_count=1},
	.Clear_Hard  = {api_id="ACH_CLEAR_HARD", title="No Safety Nets", conditions={{fact=.Victory_Difficulties, op=.Set_Contains, literal="hard"}, {}}, condition_count=1},
	.Clear_Hell  = {api_id="ACH_CLEAR_HELL", title="Hell Held Nothing", conditions={{fact=.Victory_Difficulties, op=.Set_Contains, literal="hell"}, {}}, condition_count=1},
	.Clear_Warden   = {api_id="ACH_CLEAR_WARDEN", title="The Warden's Vigil", conditions={{fact=.Victory_Archetypes, op=.Set_Contains, literal="warden"}, {}}, condition_count=1},
	.Clear_Rogue    = {api_id="ACH_CLEAR_ROGUE", title="The Rogue's Exit", conditions={{fact=.Victory_Archetypes, op=.Set_Contains, literal="rogue"}, {}}, condition_count=1},
	.Clear_Arcanist = {api_id="ACH_CLEAR_ARCANIST", title="The Arcanist's Proof", conditions={{fact=.Victory_Archetypes, op=.Set_Contains, literal="arcanist"}, {}}, condition_count=1},
	.Clear_Acolyte  = {api_id="ACH_CLEAR_ACOLYTE", title="The Acolyte's Rite", conditions={{fact=.Victory_Archetypes, op=.Set_Contains, literal="acolyte"}, {}}, condition_count=1},
	.Clear_Ranger   = {api_id="ACH_CLEAR_RANGER", title="The Ranger's Mark", conditions={{fact=.Victory_Archetypes, op=.Set_Contains, literal="ranger"}, {}}, condition_count=1},
	.Clear_Every_Archetype = {api_id="ACH_CLEAR_EVERY_ARCHETYPE", title="Five Ways Down", conditions={{fact=.Victory_Archetypes, op=.Set_Complete}, {}}, condition_count=1},
	.Boss_Ash_Gallows     = {api_id="ACH_BOSS_ASH_GALLOWS", title="Ember Scars", conditions={{fact=.Bosses_Defeated, op=.Set_Contains, literal="ash_gallows"}, {}}, condition_count=1},
	.Boss_Mycelial_Matron = {api_id="ACH_BOSS_MYCELIAL_MATRON", title="Spore and Silence", conditions={{fact=.Bosses_Defeated, op=.Set_Contains, literal="mycelial_matron"}, {}}, condition_count=1},
	.Boss_Rime_Chanter    = {api_id="ACH_BOSS_RIME_CHANTER", title="The Ninth Bell Stilled", conditions={{fact=.Bosses_Defeated, op=.Set_Contains, literal="rime_chanter"}, {}}, condition_count=1},
	.Boss_Void_Sentinel   = {api_id="ACH_BOSS_VOID_SENTINEL", title="Unrunes the Guard", conditions={{fact=.Bosses_Defeated, op=.Set_Contains, literal="void_sentinel"}, {}}, condition_count=1},
	.Boss_Gate_Tyrant     = {api_id="ACH_BOSS_GATE_TYRANT", title="The Tyrant Kneels", conditions={{fact=.Bosses_Defeated, op=.Set_Contains, literal="gate_tyrant"}, {}}, condition_count=1},
	.Boss_Bestiary        = {api_id="ACH_BOSS_BESTIARY", title="Nothing Left Guarding", conditions={{fact=.Bosses_Defeated, op=.Set_Complete}, {}}, condition_count=1},
	.Gate_Aid     = {api_id="ACH_GATE_AID", title="You Offered Help", conditions={{fact=.Story_Verbs, op=.Set_Contains, literal="aid"}, {}}, condition_count=1},
	.Gate_Bargain = {api_id="ACH_GATE_BARGAIN", title="You Named a Price", conditions={{fact=.Story_Verbs, op=.Set_Contains, literal="bargain"}, {}}, condition_count=1},
	.Gate_Defy    = {api_id="ACH_GATE_DEFY", title="You Said No", conditions={{fact=.Story_Verbs, op=.Set_Contains, literal="defy"}, {}}, condition_count=1},
	.Gate_All_Answers = {api_id="ACH_GATE_ALL_ANSWERS", title="Every Answer Given", conditions={{fact=.Story_Verbs, op=.Set_Complete}, {}}, condition_count=1},
	.Themes_All    = {api_id="ACH_THEMES_ALL", title="Cartographer of the Dark", conditions={{fact=.Themes_Seen, op=.Set_Complete}, {}}, condition_count=1},
	.Modifiers_All = {api_id="ACH_MODIFIERS_ALL", title="Every Omen Read", conditions={{fact=.Modifiers_Seen, op=.Set_Complete}, {}}, condition_count=1},
	.Legendary_10  = {api_id="ACH_LEGENDARY_10", title="The Hoard Remembers", conditions={{fact=.Uniques_Seen, op=.Set_Size_At_Least, threshold=10}, {}}, condition_count=1},
	.Secrets_25 = {api_id="ACH_SECRETS_25", title="Nothing Stays Hidden", conditions={{fact=.Lifetime_Secrets, op=.Counter_At_Least, threshold=25}, {}}, condition_count=1},
	.Shrines_20 = {api_id="ACH_SHRINES_20", title="Devout Enough", conditions={{fact=.Lifetime_Shrines, op=.Counter_At_Least, threshold=20}, {}}, condition_count=1},
	.Kills_1000 = {api_id="ACH_KILLS_1000", title="A Thousand Reasons", conditions={{fact=.Lifetime_Kills, op=.Counter_At_Least, threshold=1000}, {}}, condition_count=1},
	.Runs_50    = {api_id="ACH_RUNS_50", title="It Keeps Calling", conditions={{fact=.Runs_Started, op=.Counter_At_Least, threshold=50}, {}}, condition_count=1},
	// Authored in App Admin; dormant until the MP milestone supplies co-op
	// facts (STEAM.md decision 1 schedules that before release).
	.Coop_Run   = {api_id="ACH_COOP_RUN", title="Someone Else's Torch", conditions={{fact=.Run_Coop, op=.Flag_Set}, {}}, condition_count=1},
	.Coop_Clear = {api_id="ACH_COOP_CLEAR", title="Two Out of Ten", conditions={{fact=.Coop_Clears, op=.Counter_At_Least, threshold=1}, {}}, condition_count=1},
	.Depth_1_Death = {api_id="ACH_DEPTH_1_DEATH", title="That Was Fast", conditions={{fact=.Run_Is_Death, op=.Flag_Set}, {fact=.Run_Depth, op=.Counter_At_Most, threshold=1}}, condition_count=2},
	.Dry_Clear     = {api_id="ACH_DRY_CLEAR", title="Sober Descent", conditions={{fact=.Run_Is_Victory, op=.Flag_Set}, {fact=.Run_Potions_Used, op=.Counter_At_Most, threshold=0}}, condition_count=2},
	.Bar_Pilgrim   = {api_id="ACH_BAR_PILGRIM", title="The Toast Pilgrimage", conditions={{fact=.Run_Bar_Pilgrim, op=.Flag_Set}, {}}, condition_count=1},
	.Wallfacer     = {api_id="ACH_WALLFACER", title="Wall Facer", conditions={{fact=.Lifetime_Wall_Touches, op=.Counter_At_Least, threshold=100}, {}}, condition_count=1},
	.Elite_Hunter  = {api_id="ACH_ELITE_HUNTER", title="Elite Hunt", conditions={{fact=.Run_Elites_Killed, op=.Counter_At_Least, threshold=10}, {}}, condition_count=1},
	.Challenger    = {api_id="ACH_CHALLENGER", title="Asked For It", conditions={{fact=.Run_Challenge_Rooms, op=.Counter_At_Least, threshold=3}, {}}, condition_count=1},
}

// The four Steam stats authored in App Admin (pygame achievements.py
// STAT_FACTS); names are the partner-site contract.
ACHIEVEMENT_STAT_NAMES := [4]string{"runs_started", "clears", "best_depth", "lifetime_kills"}

achievement_stat_value :: proc(profile: ^Profile_State, name: string) -> (i32, bool) {
	if profile == nil do return 0, false
	switch name {
	case "runs_started":  return i32(min(profile.lifetime_started, u64(max(i32)))), true
	case "clears":        return i32(min(profile.lifetime_victories, u64(max(i32)))), true
	case "best_depth":    return i32(clamp(profile.best_depth, 0, int(max(i32)))), true
	case "lifetime_kills":return i32(min(profile.lifetime_kills, u64(max(i32)))), true
	}
	return 0, false
}

Achievement_Facts :: struct {
	profile: ^Profile_State,
	has_run: bool,
	run:     Run_Terminal_Facts,
}

achievement_counter :: proc(facts: ^Achievement_Facts, fact: Achievement_Fact) -> (value: int, ok: bool) {
	if facts == nil || facts.profile == nil do return 0, false
	profile := facts.profile
	#partial switch fact {
	case .Best_Depth:           return profile.best_depth, true
	case .Clears:               return int(min(profile.lifetime_victories, u64(max(int)))), true
	case .Runs_Started:         return int(min(profile.lifetime_started, u64(max(int)))), true
	case .Lifetime_Kills:       return int(min(profile.lifetime_kills, u64(max(int)))), true
	case .Lifetime_Secrets:     return int(min(profile.lifetime_secrets, u64(max(int)))), true
	case .Lifetime_Shrines:     return int(min(profile.lifetime_shrines, u64(max(int)))), true
	case .Lifetime_Wall_Touches:return int(min(profile.lifetime_wall_touches, u64(max(int)))), true
	case .Coop_Clears:          return 0, true // MP-deferred fact; never satisfied yet
	case .Run_Depth:            if facts.has_run do return facts.run.depth, true
	case .Run_Potions_Used:     if facts.has_run do return facts.run.potions_used, true
	case .Run_Elites_Killed:    if facts.has_run do return facts.run.elites_killed, true
	case .Run_Challenge_Rooms:  if facts.has_run do return facts.run.challenge_rooms_cleared, true
	}
	return 0, false
}

achievement_flag :: proc(facts: ^Achievement_Facts, fact: Achievement_Fact) -> bool {
	if facts == nil do return false
	#partial switch fact {
	case .Run_Is_Death:    return facts.has_run && facts.run.outcome == .Fallen
	case .Run_Is_Victory:  return facts.has_run && facts.run.outcome == .Victory
	case .Run_Bar_Pilgrim: return facts.has_run && facts.run.bar_pilgrim
	case .Run_Coop:        return false // MP-deferred fact
	}
	return false
}

// Returns the profile-backed union set (ids slice, live count, capacity).
// Capacity doubles as the completion target: every set array is sized to its
// content table's cardinality, which the contract test pins.
achievement_set :: proc(facts: ^Achievement_Facts, fact: Achievement_Fact) -> (ids: []string, count: int, ok: bool) {
	if facts == nil || facts.profile == nil do return nil, 0, false
	profile := facts.profile
	#partial switch fact {
	case .Victory_Difficulties: return profile.victory_difficulty_ids[:], profile.victory_difficulty_count, true
	case .Victory_Archetypes:   return profile.victory_archetype_ids[:], profile.victory_archetype_count, true
	case .Bosses_Defeated:      return profile.lifetime_boss_ids[:], profile.lifetime_boss_count, true
	case .Story_Verbs:          return profile.story_verb_ids[:], profile.story_verb_count, true
	case .Themes_Seen:          return profile.theme_ids_seen[:], profile.theme_seen_count, true
	case .Modifiers_Seen:       return profile.modifier_ids_seen[:], profile.modifier_seen_count, true
	case .Uniques_Seen:         return profile.unique_item_ids_seen[:], profile.unique_seen_count, true
	}
	return nil, 0, false
}

achievement_condition_met :: proc(facts: ^Achievement_Facts, condition: ^Achievement_Condition) -> bool {
	if facts == nil || condition == nil do return false
	switch condition.op {
	case .Counter_At_Least:
		value, ok := achievement_counter(facts, condition.fact)
		return ok && value >= condition.threshold
	case .Counter_At_Most:
		value, ok := achievement_counter(facts, condition.fact)
		return ok && value <= condition.threshold
	case .Set_Contains:
		ids, count, ok := achievement_set(facts, condition.fact)
		return ok && profile_string_set_contains(ids, count, condition.literal)
	case .Set_Complete:
		ids, count, ok := achievement_set(facts, condition.fact)
		return ok && count >= len(ids)
	case .Set_Size_At_Least:
		_, count, ok := achievement_set(facts, condition.fact)
		return ok && count >= condition.threshold
	case .Flag_Set:
		return achievement_flag(facts, condition.fact)
	case .None:
	}
	return false
}

achievement_conditions_met :: proc(facts: ^Achievement_Facts, def: ^Achievement_Def) -> bool {
	if def == nil || def.condition_count <= 0 do return false
	for i in 0 ..< clamp(def.condition_count, 0, len(def.conditions)) {
		condition := def.conditions[i]
		if !achievement_condition_met(facts, &condition) do return false
	}
	return true
}

// Evaluate everything not yet in the granted cache. Returns the newly earned
// ids without marking them granted: the caller durably queues the Steam push
// first, then marks (profile_mark_achievement_granted) so a failed queue write
// re-evaluates later instead of silently losing the unlock.
achievements_evaluate :: proc(profile: ^Profile_State, has_run: bool, run_facts: Run_Terminal_Facts, newly: ^[len(Achievement_Id)]Achievement_Id) -> int {
	if profile == nil || newly == nil do return 0
	facts := Achievement_Facts{profile=profile, has_run=has_run, run=run_facts}
	count := 0
	for id in Achievement_Id {
		def := ACHIEVEMENT_DEFS[id]
		if profile_achievement_granted(profile, def.api_id) do continue
		if !achievement_conditions_met(&facts, &def) do continue
		newly[count] = id
		count += 1
	}
	return count
}

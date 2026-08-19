package archrogue

// MX-story deterministic core. Generation consumes only the derived STORY
// stream; recording choices is RNG-free. The module owns generated strings in
// Story_State and exposes story_state_destroy as the matching lifetime seam.
// No raylib types or calls belong here.

import "core:fmt"
import "core:math"
import "core:strings"

STORY_SALT   :: u64(0x53544f5259) // "STORY"
STORY_STREAM :: 12                // isolated after gameplay/presentation streams 0..11
STORY_LOG_CAP :: 12
STORY_MEMORY_ERASURE :: "------"

Story_Choice :: struct {
	verb:    Story_Choice_Verb,
	label:   string,
	intent:  string,
	outcome: string,
	effects: Story_Effects,
	flags:   [2]Story_Choice_Tag,
}

Story_Beat :: struct {
	depth:          int,
	dilemma:       Story_Dilemma_Id,
	motif:          Story_Motif_Id,
	guest_role:     Story_Guest_Role_Id,
	guest_variant:  int,
	guest_name:     string,
	guest_motive:   string,
	dialogue:       string,
	is_tether:      bool,
	tether_stage:   Story_Tether_Stage,
	choices:        [Story_Choice_Verb]Story_Choice,
	resolution:     Story_Resolution,
	outcome:        string,
	outcome_owned:  bool,
	summary:        string, // allocator-owned
}

Story_Flags :: struct {
	choice_tags:    [STORY_BEAT_COUNT][Story_Choice_Tag]bool,
	unanswered:     [STORY_BEAT_COUNT]bool,
	forsaken:       [STORY_BEAT_COUNT]bool,
	secret_revealed: bool,
	true_names:     [Story_True_Name]bool,
	crisis:         Story_Resolution,
	gate:           Story_Resolution,
}

Story_Log :: struct {
	entries: [STORY_LOG_CAP]string, // every live entry is allocator-owned
	count:   int,
}

Story_State :: struct {
	seed:             u64, // run seed, matching pygame StoryState.seed
	stream_seed:      u64, // derived seed for the isolated PCG story stream
	run_number:       int,
	archetype:        Archetype_Id,
	chapter_index:    int,
	faction:          Story_Faction_Id,
	rival_faction:    Story_Faction_Id,
	relic:            Story_Relic_Id,
	beats:            [STORY_BEAT_COUNT]Story_Beat,
	accent:           [4]u8,
	effects:          Story_Effects,
	flags:            Story_Flags,
	title:            string, // allocator-owned
	player_backstory: string, // allocator-owned
	objective:        string, // allocator-owned
	antagonist:       string,
	log:              Story_Log,
}

Story_Milestones :: struct {
	secret_revealed: bool,
	true_name_learned: bool,
	crisis_recorded: bool,
}

Story_Ending_Result :: struct {
	valid:   bool,
	verb:    Story_Choice_Verb,
	road:    Story_Road,
	ending:  Story_Ending,
	coda:    string, // allocator-owned when non-empty
}

Story_Text_Token :: struct {
	key:   string,
	value: string,
}

@(private = "file")
story_log_append_owned :: proc(log: ^Story_Log, text: string) {
	if log == nil do return
	if log.count >= STORY_LOG_CAP {
		if log.entries[0] != "" do delete(log.entries[0])
		for i in 1 ..< log.count {
			log.entries[i - 1] = log.entries[i]
		}
		log.count -= 1
		log.entries[log.count] = ""
	}
	log.entries[log.count] = text
	log.count += 1
}

@(private = "file")
story_log_append :: proc(log: ^Story_Log, text: string) {
	story_log_append_owned(log, strings.clone(text))
}

story_state_destroy :: proc(story: ^Story_State, allocator := context.allocator) {
	if story == nil do return
	if story.title != "" do delete(story.title, allocator)
	if story.player_backstory != "" do delete(story.player_backstory, allocator)
	if story.objective != "" do delete(story.objective, allocator)
	for i in 0 ..< STORY_BEAT_COUNT {
		beat := &story.beats[i]
		if beat.summary != "" do delete(beat.summary, allocator)
		if beat.outcome_owned && beat.outcome != "" do delete(beat.outcome, allocator)
	}
	for i in 0 ..< story.log.count {
		if story.log.entries[i] != "" do delete(story.log.entries[i], allocator)
	}
	story^ = {}
}

story_resolution_from_verb :: proc(verb: Story_Choice_Verb) -> Story_Resolution {
	switch verb {
	case .Aid:     return .Aid
	case .Bargain: return .Bargain
	case .Defy:    return .Defy
	}
	return .Unresolved
}

story_verb_from_resolution :: proc(resolution: Story_Resolution) -> (Story_Choice_Verb, bool) {
	#partial switch resolution {
	case .Aid:     return .Aid, true
	case .Bargain: return .Bargain, true
	case .Defy:    return .Defy, true
	case:          return {}, false
	}
}

story_pinned_dilemma :: proc(depth: int) -> (Story_Dilemma_Id, bool) {
	switch depth {
	case 5: return .Door_That_Remembers, true
	case 8: return .Gates_Confession, true
	case 9: return .Last_Guests_Mask, true
	}
	return {}, false
}

story_tether_stage_for_depth :: proc(depth: int) -> (Story_Tether_Stage, bool) {
	switch depth {
	case 1: return .Meet, true
	case 5: return .Reveal, true
	case 9: return .Crisis, true
	}
	return {}, false
}

@(private = "file")
story_dilemma_rotation :: proc(rng: ^Pcg32) -> [STORY_BEAT_COUNT]Story_Dilemma_Id {
	rotation: [STORY_BEAT_COUNT]Story_Dilemma_Id
	pool: [len(Story_Dilemma_Id) - 3]Story_Dilemma_Id
	pool_count := 0
	for id in Story_Dilemma_Id {
		if id == .Door_That_Remembers || id == .Gates_Confession || id == .Last_Guests_Mask do continue
		pool[pool_count] = id
		pool_count += 1
	}
	for i := pool_count - 1; i > 0; i -= 1 {
		j := rng_below(rng, i + 1)
		pool[i], pool[j] = pool[j], pool[i]
	}
	free_index := 0
	for depth in 1 ..= STORY_BEAT_COUNT {
		if pinned, ok := story_pinned_dilemma(depth); ok {
			rotation[depth - 1] = pinned
		} else {
			rotation[depth - 1] = pool[free_index]
			free_index += 1
		}
	}
	return rotation
}

@(private = "file")
story_modifier_bias :: proc(modifier: Run_Modifier_Id) -> (motifs: [2]Story_Motif_Id, count: int) {
	#partial switch modifier {
	case .Blood_Moon:
		motifs = {.Crypt_Of_Ash, .Violet_Reliquary}
	case .Trap_Laced:
		motifs = {.Obsidian_Foundry, .Thornbound_Vault}
	case .Treasure_Draught:
		motifs = {.Violet_Reliquary, .Moonlit_Aquifer}
	case .Thin_Veil:
		motifs = {.Frozen_Ossuary, .Moonlit_Aquifer}
	case .Cursed_Bargains:
		motifs = {.Thornbound_Vault, .Violet_Reliquary}
	case .Elite_Hunt:
		motifs = {.Sunken_Bastion, .Obsidian_Foundry}
	case:
		return {}, 0
	}
	return motifs, 2
}

@(private = "file")
story_theme_sequence :: proc(
	rng: ^Pcg32,
	starting_theme: Story_Motif_Id,
	modifier: Run_Modifier_Id,
) -> [STORY_BEAT_COUNT]Story_Motif_Id {
	sequence: [STORY_BEAT_COUNT]Story_Motif_Id
	sequence[0] = starting_theme
	bias, bias_count := story_modifier_bias(modifier)
	for i in 1 ..< STORY_BEAT_COUNT {
		if bias_count > 0 && rng_chance(rng, 0.45) {
			sequence[i] = bias[rng_below(rng, bias_count)]
		} else {
			sequence[i] = Story_Motif_Id(rng_below(rng, len(Story_Motif_Id)))
		}
	}
	return sequence
}

@(private = "file")
story_petitioner_role :: proc(
	rng: ^Pcg32,
	faction, rival: Story_Faction_Id,
) -> Story_Guest_Role_Id {
	orbits: [2]Story_Guest_Role_Id
	orbit_count := 0
	factions := [2]Story_Faction_Id{faction, rival}
	for id in factions {
		entry := STORY_FACTIONS[id]
		if entry.has_orbit {
			orbits[orbit_count] = entry.orbit_role
			orbit_count += 1
		}
	}
	if orbit_count > 0 && rng_chance(rng, 0.45) {
		return orbits[rng_below(rng, orbit_count)]
	}
	return Story_Guest_Role_Id(rng_below(rng, len(Story_Guest_Role_Id)))
}

story_guest_variant_for_name :: proc(role: Story_Guest_Role_Id, name: string) -> (int, bool) {
	for candidate, index in STORY_GUEST_TEMPLATES[role].names {
		if candidate == name do return index, true
	}
	return 0, false
}

@(private = "file")
story_choice_effect_vector :: proc(verb: Story_Choice_Verb, depth: int) -> Story_Effects {
	effects: Story_Effects
	depth_scale := min(f32(0.035), f32(depth) * 0.0025)
	switch verb {
	case .Aid:
		effects[.Enemy_Pressure] = -0.055 - depth_scale
		effects[.Shrine_Bonus] = 0.050 + depth_scale
		effects[.Secret_Bonus] = 0.030 + depth_scale / 2
		effects[.Damage_Resist] = 0.035 + depth_scale / 2
		effects[.Healing_Echo] = 0.025 + depth_scale / 2
	case .Bargain:
		effects[.Loot_Bonus] = 0.075 + depth_scale
		effects[.Trap_Bonus] = 0.045 + depth_scale / 2
		effects[.Curse_Bonus] = 0.035 + depth_scale / 2
		effects[.Relic_Power] = 0.040 + depth_scale / 2
		effects[.Blood_Price] = 0.025 + depth_scale / 2
	case .Defy:
		effects[.Enemy_Pressure] = 0.075 + depth_scale
		effects[.XP_Bonus] = 0.055 + depth_scale / 2
		effects[.Boss_Pressure] = 0.040 + depth_scale / 2
		effects[.Damage_Bonus] = 0.045 + depth_scale / 2
		effects[.Hunter_Pressure] = 0.045 + depth_scale / 2
	}
	return effects
}

@(private = "file")
story_choice_flags :: proc(verb: Story_Choice_Verb) -> [2]Story_Choice_Tag {
	switch verb {
	case .Aid:     return {.Mercy, .Witness}
	case .Bargain: return {.Bargain, .Marked}
	case .Defy:    return {.Defiance, .Wrath}
	}
	return {}
}

@(private = "file")
story_choices_for_beat :: proc(
	depth: int,
	dilemma_id: Story_Dilemma_Id,
	archetype: Archetype_Id,
) -> [Story_Choice_Verb]Story_Choice {
	choices: [Story_Choice_Verb]Story_Choice
	dilemma := STORY_DILEMMAS[dilemma_id]
	for verb in Story_Choice_Verb {
		intent := dilemma.intents[verb]
		outcome := dilemma.outcomes[verb]
		if depth == 9 {
			crisis := STORY_TETHERS[archetype].crisis_choices[verb]
			intent = crisis.intent
			outcome = crisis.outcome
		}
		choices[verb] = {
			verb = verb,
			label = STORY_CHOICE_LABELS[verb],
			intent = intent,
			outcome = outcome,
			effects = story_choice_effect_vector(verb, depth),
			flags = story_choice_flags(verb),
		}
	}
	return choices
}

// One complete 10-beat story. The caller passes the run seed directly; this
// procedure derives and owns the isolated PCG stream, so adding story draws can
// never perturb floor layout, population, loot, combat, or another subsystem.
story_generate :: proc(
	run_seed: u64,
	archetype: Archetype_Id,
	run_number := 1,
	starting_theme := Story_Motif_Id.Crypt_Of_Ash,
	run_modifier := Run_Modifier_Id.Restless_Depths,
) -> Story_State {
	story_seed := derive_seed(run_seed, STORY_SALT)
	rng := rng_make(story_seed, stream = STORY_STREAM)
	story := Story_State{
		seed = run_seed,
		stream_seed = story_seed,
		run_number = run_number,
		archetype = archetype,
		antagonist = "the Toll-Keeper",
	}
	story.chapter_index = rng_below(&rng, STORY_CHAPTERS_PER_ARC)
	story.faction = Story_Faction_Id(rng_below(&rng, len(Story_Faction_Id)))
	rival_pick := rng_below(&rng, len(Story_Faction_Id) - 1)
	if rival_pick >= int(story.faction) do rival_pick += 1
	story.rival_faction = Story_Faction_Id(rival_pick)
	story.relic = Story_Relic_Id(rng_below(&rng, len(Story_Relic_Id)))
	story.accent = STORY_FACTIONS[story.faction].color

	dilemmas := story_dilemma_rotation(&rng)
	themes := story_theme_sequence(&rng, starting_theme, run_modifier)
	tether := STORY_TETHERS[archetype]

	for depth in 1 ..= STORY_BEAT_COUNT {
		beat := &story.beats[depth - 1]
		beat.depth = depth
		beat.dilemma = dilemmas[depth - 1]
		beat.motif = themes[depth - 1]
		beat.choices = story_choices_for_beat(depth, beat.dilemma, archetype)

		if stage, tethered := story_tether_stage_for_depth(depth); tethered {
			tether_beat := tether.beats[stage]
			beat.is_tether = true
			beat.tether_stage = stage
			beat.guest_role = tether.role
			beat.guest_name = tether.name
			beat.guest_motive = tether_beat.motive
			beat.dialogue = tether_beat.speech
			beat.guest_variant, _ = story_guest_variant_for_name(tether.role, tether.name)
		} else {
			role := story_petitioner_role(&rng, story.faction, story.rival_faction)
			template := STORY_GUEST_TEMPLATES[role]
			pair_index := rng_below(&rng, STORY_GUEST_VARIANTS)
			variant := rng_below(&rng, STORY_GUEST_VARIANTS)
			beat.guest_role = role
			beat.guest_variant = variant
			beat.guest_name = template.names[variant]
			beat.guest_motive = template.pairs[pair_index].motive
			beat.dialogue = template.pairs[pair_index].speech
		}
		if depth == 8 do beat.dialogue = STORY_TYRANT_OFFERS[archetype]

		motif := STORY_MOTIFS[beat.motif]
		role_lower := STORY_GUEST_TEMPLATES[beat.guest_role].role_lower
		beat.summary = fmt.aprintf(
			"The %s: %s. %s, %s, waits -- %s.",
			motif.theme_name,
			motif.image,
			beat.guest_name,
			role_lower,
			STORY_DILEMMAS[beat.dilemma].setup,
		)
	}

	arc := STORY_ARCS[archetype]
	relic := STORY_RELICS[story.relic]
	faction := STORY_FACTIONS[story.faction]
	chapter := arc.chapters[story.chapter_index]
	story.title = fmt.aprintf("%s and the %s", chapter, relic.name)
	story.player_backstory = fmt.aprintf("The %s -- %s. %s", ARCHETYPES[archetype].name, chapter, arc.wound)
	story.objective = fmt.aprintf("Carry the %s to the Last Gate before %s claim it.", relic.name, faction.name)

	story_log_append_owned(&story.log, fmt.aprintf("Run %d story seed %d", run_number, story.seed))
	story_log_append(&story.log, story.player_backstory)
	story_log_append(&story.log, story.objective)
	return story
}

story_beat_for_depth :: proc(story: ^Story_State, depth: int) -> ^Story_Beat {
	if story == nil || depth < 1 || depth > STORY_BEAT_COUNT do return nil
	beat := &story.beats[depth - 1]
	if beat.depth != depth do return nil
	return beat
}

story_beat_title :: proc(beat: ^Story_Beat) -> string {
	if beat == nil do return ""
	return STORY_DILEMMAS[beat.dilemma].title
}

story_beat_truth :: proc(beat: ^Story_Beat) -> string {
	if beat == nil do return ""
	return STORY_DILEMMAS[beat.dilemma].truth
}

story_beat_theme_name :: proc(beat: ^Story_Beat) -> string {
	if beat == nil do return ""
	return STORY_MOTIFS[beat.motif].theme_name
}

@(private = "file")
story_round_effect :: proc(value: f32) -> f32 {
	return math.round(value * 10000) / 10000
}

story_add_effects :: proc(story: ^Story_State, effects: Story_Effects) {
	if story == nil do return
	for id in Story_Effect_Id {
		story.effects[id] = story_round_effect(story.effects[id] + effects[id])
	}
}

story_effect :: proc(story: ^Story_State, id: Story_Effect_Id) -> f32 {
	if story == nil do return 0
	return story.effects[id]
}

clamp_story_effect :: proc(value, minimum, maximum: f32) -> f32 {
	return clamp(value, minimum, maximum)
}

story_true_name_known :: proc(story: ^Story_State, name: Story_True_Name) -> bool {
	return story != nil && story.flags.true_names[name]
}

story_learn_true_name :: proc(story: ^Story_State, name: Story_True_Name) -> bool {
	if story == nil || story.flags.true_names[name] do return false
	story.flags.true_names[name] = true

	// Names have weight: erase the oldest memory except the current/latest line.
	for i in 0 ..< max(0, story.log.count - 1) {
		entry := story.log.entries[i]
		if entry == "" || entry == STORY_MEMORY_ERASURE do continue
		delete(story.log.entries[i])
		story.log.entries[i] = strings.clone(STORY_MEMORY_ERASURE)
		break
	}

	switch name {
	case .Sorn:
		story_log_append(&story.log, "His pride cracks. Sorn Voss -- the name, spent and spoken.")
	case .Liss:
		story_log_append(&story.log, "Her name is Liss Voss. The hall never lost it.")
	}
	return true
}

story_apply_choice_milestones :: proc(
	story: ^Story_State,
	depth: int,
	verb: Story_Choice_Verb,
) -> Story_Milestones {
	result: Story_Milestones
	if story == nil do return result
	if depth == 5 && !story.flags.secret_revealed {
		story.flags.secret_revealed = true
		story_log_append_owned(&story.log, fmt.aprintf("Remembered: %s", STORY_ARCS[story.archetype].secret))
		result.secret_revealed = true
	}
	if depth == 8 && (verb == .Defy || (verb == .Aid && story.archetype == .Acolyte)) {
		result.true_name_learned = story_learn_true_name(story, .Sorn)
	}
	if depth == 9 && story.flags.crisis == .Unresolved {
		story.flags.crisis = story_resolution_from_verb(verb)
		result.crisis_recorded = true
	}
	return result
}

story_record_choice :: proc(story: ^Story_State, depth: int, verb: Story_Choice_Verb) -> bool {
	beat := story_beat_for_depth(story, depth)
	if beat == nil || beat.resolution != .Unresolved do return false
	choice := beat.choices[verb]
	beat.resolution = story_resolution_from_verb(verb)
	beat.outcome = choice.outcome
	story_add_effects(story, choice.effects)
	for flag in choice.flags do story.flags.choice_tags[depth - 1][flag] = true
	story_log_append_owned(
		&story.log,
		fmt.aprintf("Depth %d: %s -- %s", depth, choice.label, choice.outcome),
	)
	_ = story_apply_choice_milestones(story, depth, verb)
	return true
}

story_record_unanswered :: proc(story: ^Story_State, depth: int) -> bool {
	beat := story_beat_for_depth(story, depth)
	if beat == nil || beat.resolution != .Unresolved do return false
	beat.resolution = .Unanswered
	beat.outcome = fmt.aprintf(
		"%s's plea went unanswered; the dungeon takes the silence as permission to harden its next rooms.",
		beat.guest_name,
	)
	beat.outcome_owned = true
	story.flags.unanswered[depth - 1] = true
	story.flags.forsaken[depth - 1] = true
	effects: Story_Effects
	effects[.Enemy_Pressure] = 0.045
	effects[.Trap_Bonus] = 0.035
	effects[.Curse_Bonus] = 0.015
	effects[.Boss_Pressure] = 0.025
	effects[.Hunter_Pressure] = 0.040
	story_add_effects(story, effects)
	story_log_append_owned(
		&story.log,
		fmt.aprintf("Depth %d: Unanswered -- %s", depth, beat.outcome),
	)
	return true
}

// Dominant verb over completed acts. Boundaries are strictly behind the
// supplied depth (D3 remains unwritten; D4 reads beats 1..3). Forsaken uses
// >=, and equal answered counts preserve aid > bargain > defy priority.
story_road :: proc(story: ^Story_State, depth: int) -> Story_Road {
	if story == nil do return .Unwritten
	act_break := 0
	boundaries := [3]int{3, 6, 9}
	for boundary in boundaries {
		if boundary < depth do act_break = boundary
	}
	if act_break <= 0 do return .Unwritten

	aid, bargain, defy, unanswered := 0, 0, 0, 0
	for i in 0 ..< act_break {
		#partial switch story.beats[i].resolution {
		case .Aid:        aid += 1
		case .Bargain:    bargain += 1
		case .Defy:       defy += 1
		case .Unanswered: unanswered += 1
		case:             // unresolved does not vote
		}
	}
	answered := aid + bargain + defy
	if unanswered >= max(1, answered) do return .Forsaken
	if answered <= 0 do return .Unwritten
	if aid >= bargain && aid >= defy do return .Witness
	if bargain >= defy do return .Debtor
	return .Defiant
}

story_crisis_verb :: proc(story: ^Story_State) -> (Story_Choice_Verb, bool) {
	if story == nil do return {}, false
	return story_verb_from_resolution(story.flags.crisis)
}

story_record_gate_choice :: proc(story: ^Story_State, verb: Story_Choice_Verb) -> bool {
	if story == nil || story.flags.gate != .Unresolved do return false
	story.flags.gate = story_resolution_from_verb(verb)
	ending := STORY_ENDINGS[story.archetype][verb]
	story_log_append_owned(&story.log, fmt.aprintf("The Tenth Bell: %s.", ending.title))
	return true
}

story_ending_for :: proc(archetype: Archetype_Id, verb: Story_Choice_Verb) -> Story_Ending {
	return STORY_ENDINGS[archetype][verb]
}

@(private = "file")
story_coda_append :: proc(builder: ^strings.Builder, part: string) {
	if part == "" do return
	if len(strings.to_string(builder^)) > 0 do strings.write_byte(builder, ' ')
	strings.write_string(builder, part)
}

story_resolve_ending :: proc(
	story: ^Story_State,
	verb: Story_Choice_Verb,
	depth := DUNGEON_DEPTH,
) -> Story_Ending_Result {
	if story == nil do return {}
	result := Story_Ending_Result{
		valid = true,
		verb = verb,
		road = story_road(story, depth),
		ending = STORY_ENDINGS[story.archetype][verb],
	}
	builder := strings.builder_make(context.allocator)
	defer strings.builder_destroy(&builder)
	if crisis, ok := story_crisis_verb(story); ok {
		story_coda_append(&builder, STORY_CRISIS_ECHOES[story.archetype][crisis])
	}
	if result.road == .Forsaken {
		story_coda_append(&builder, STORY_ENDING_FORSAKEN_CODAS[story.archetype])
	} else {
		story_coda_append(&builder, STORY_ENDING_ROAD_CODAS[result.road])
	}
	if verb == .Aid && story_true_name_known(story, .Liss) {
		story_coda_append(&builder, STORY_LISS_AID_CODA)
	}
	if len(strings.to_string(builder)) > 0 {
		result.coda = strings.clone(strings.to_string(builder))
	}
	return result
}

story_resolve_recorded_ending :: proc(
	story: ^Story_State,
	depth := DUNGEON_DEPTH,
) -> Story_Ending_Result {
	if story == nil do return {}
	verb, ok := story_verb_from_resolution(story.flags.gate)
	if !ok do return {}
	return story_resolve_ending(story, verb, depth)
}

story_ending_result_destroy :: proc(result: ^Story_Ending_Result) {
	if result == nil do return
	if result.coda != "" do delete(result.coda)
	result^ = {}
}

// Safe template substitution for panel narration. Known {tokens} are replaced;
// unknown or unterminated tokens remain byte-for-byte intact. Double braces
// follow Python format strings: {{ and }} become literal braces.
story_format_text :: proc(template: string, tokens: []Story_Text_Token) -> string {
	builder := strings.builder_make(context.allocator)
	defer strings.builder_destroy(&builder)
	for i := 0; i < len(template); {
		if template[i] == '{' {
			if i + 1 < len(template) && template[i + 1] == '{' {
				strings.write_byte(&builder, '{')
				i += 2
				continue
			}
			closing := -1
			for j := i + 1; j < len(template); j += 1 {
				if template[j] == '}' {
					closing = j
					break
				}
			}
			if closing < 0 {
				strings.write_string(&builder, template[i:])
				break
			}
			key := template[i + 1:closing]
			found := false
			for token in tokens {
				if token.key == key {
					strings.write_string(&builder, token.value)
					found = true
					break
				}
			}
			if !found do strings.write_string(&builder, template[i:closing + 1])
			i = closing + 1
			continue
		}
		if template[i] == '}' && i + 1 < len(template) && template[i + 1] == '}' {
			strings.write_byte(&builder, '}')
			i += 2
			continue
		}
		strings.write_byte(&builder, template[i])
		i += 1
	}
	return strings.clone(strings.to_string(builder))
}

// Stable semantic slugs and full manifest keys. These never derive from
// player-facing text at runtime, so punctuation/localization can change safely.
story_motif_slug :: proc(id: Story_Motif_Id) -> string {
	return STORY_MOTIFS[id].slug
}

story_guest_role_slug :: proc(id: Story_Guest_Role_Id) -> string {
	return STORY_GUEST_TEMPLATES[id].slug
}

story_guest_name_slug :: proc(id: Story_Guest_Role_Id, variant: int) -> (string, bool) {
	if variant < 0 || variant >= STORY_GUEST_VARIANTS do return "", false
	return STORY_GUEST_TEMPLATES[id].name_slugs[variant], true
}

story_relic_slug :: proc(id: Story_Relic_Id) -> string {
	return STORY_RELICS[id].slug
}

story_ending_slug :: proc(archetype: Archetype_Id, verb: Story_Choice_Verb) -> string {
	return STORY_ENDINGS[archetype][verb].slug
}

story_omen_asset_key :: proc(id: Story_Motif_Id) -> string {
	return STORY_OMEN_ASSET_KEYS[id]
}

story_guest_backdrop_asset_key :: proc(id: Story_Guest_Role_Id) -> string {
	return STORY_GUEST_BACKDROP_ASSET_KEYS[id]
}

story_guest_portrait_asset_key :: proc(id: Story_Guest_Role_Id, variant: int) -> (string, bool) {
	if variant < 0 || variant >= STORY_GUEST_VARIANTS do return "", false
	return STORY_GUEST_PORTRAIT_ASSET_KEYS[id][variant], true
}

story_relic_icon_asset_key :: proc(id: Story_Relic_Id) -> string {
	return STORY_RELIC_ICON_ASSET_KEYS[id]
}

story_ending_panel_asset_key :: proc(archetype: Archetype_Id, verb: Story_Choice_Verb) -> string {
	return STORY_ENDING_PANEL_ASSET_KEYS[archetype][verb]
}

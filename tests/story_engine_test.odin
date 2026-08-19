package archrogue_tests

// MX-story pure/headless acceptance. The source package is imported exactly as
// every other sim test imports it; no display, audio, filesystem, or raylib API
// is touched by these tests.

import "core:strings"
import "core:testing"
import ar "../src"

STORY_TEST_EPS :: f32(1e-5)

@(private = "file")
story_test_near :: proc(a, b: f32) -> bool {
	return abs(a - b) < STORY_TEST_EPS
}

@(private = "file")
story_test_same_generation :: proc(a, b: ^ar.Story_State) -> bool {
	return a.seed == b.seed &&
		a.stream_seed == b.stream_seed &&
		a.run_number == b.run_number &&
		a.archetype == b.archetype &&
		a.chapter_index == b.chapter_index &&
		a.faction == b.faction &&
		a.rival_faction == b.rival_faction &&
		a.relic == b.relic &&
		a.beats == b.beats &&
		a.accent == b.accent &&
		a.effects == b.effects &&
		a.flags == b.flags &&
		a.title == b.title &&
		a.player_backstory == b.player_backstory &&
		a.objective == b.objective &&
		a.antagonist == b.antagonist &&
		a.log == b.log
}

@(private = "file")
story_test_expect_unique :: proc(t: ^testing.T, values: []string, label: string) {
	for value, i in values {
		testing.expectf(t, value != "", "%s key %v is empty", label, i)
		for j in i + 1 ..< len(values) {
			testing.expectf(t, value != values[j], "%s keys %v and %v both use %s", label, i, j, value)
		}
	}
}

@(private = "file")
story_test_reset_resolutions :: proc(story: ^ar.Story_State) {
	for i in 0 ..< ar.STORY_BEAT_COUNT {
		story.beats[i].resolution = .Unresolved
	}
}

@(test)
mx_story_corpus_cardinalities_and_parallel_records :: proc(t: ^testing.T) {
	testing.expect(t, len(ar.Archetype_Id) == 5, "story corpus needs five archetype arcs")
	testing.expect(t, len(ar.STORY_ARCS) == 5, "arc table cardinality changed")
	chapter_count := 0
	for archetype in ar.Archetype_Id {
		arc := ar.STORY_ARCS[archetype]
		testing.expectf(t, arc.wound != "" && arc.oath != "" && arc.secret != "", "%v arc is incomplete", archetype)
		for chapter in arc.chapters {
			testing.expectf(t, chapter != "", "%v has an empty chapter", archetype)
			chapter_count += 1
		}
	}
	testing.expect(t, chapter_count == 15, "five arcs must expose fifteen chapters")

	testing.expect(t, len(ar.Story_Faction_Id) == 8 && len(ar.STORY_FACTIONS) == 8, "faction corpus must contain eight records")
	for id in ar.Story_Faction_Id {
		entry := ar.STORY_FACTIONS[id]
		testing.expectf(t, entry.name != "" && entry.epithet != "" && entry.agenda != "" && entry.taboo != "", "%v faction is incomplete", id)
		testing.expect(t, entry.color[3] == 255, "faction accents stay opaque")
	}

	testing.expect(t, len(ar.Story_Relic_Id) == 10 && len(ar.STORY_RELICS) == 10, "relic corpus must contain ten records")
	for id in ar.Story_Relic_Id {
		relic := ar.STORY_RELICS[id]
		testing.expectf(t, relic.name != "" && relic.form != "" && relic.temptation != "" && relic.doom != "", "%v relic is incomplete", id)
	}

	testing.expect(t, len(ar.Story_Guest_Role_Id) == 10 && len(ar.STORY_GUEST_TEMPLATES) == 10, "guest corpus must contain ten roles")
	name_count, pair_count := 0, 0
	for role in ar.Story_Guest_Role_Id {
		template := ar.STORY_GUEST_TEMPLATES[role]
		testing.expectf(t, template.role != "" && template.role_lower != "" && template.voice != "", "%v role metadata is incomplete", role)
		for variant in 0 ..< ar.STORY_GUEST_VARIANTS {
			testing.expectf(t, template.names[variant] != "" && template.name_slugs[variant] != "", "%v guest variant %v has no identity", role, variant)
			testing.expectf(t, template.pairs[variant].motive != "" && template.pairs[variant].speech != "", "%v motive/speech pair %v is incomplete", role, variant)
			name_count += 1
			pair_count += 1
		}
	}
	testing.expect(t, name_count == 30 && pair_count == 30, "ten guest roles need three names and three motive/speech pairs each")

	testing.expect(t, len(ar.Story_Dilemma_Id) == 12 && len(ar.STORY_DILEMMAS) == 12, "dilemma corpus must contain twelve records")
	for id in ar.Story_Dilemma_Id {
		dilemma := ar.STORY_DILEMMAS[id]
		testing.expectf(t, dilemma.title != "" && dilemma.setup != "" && dilemma.truth != "", "%v dilemma is incomplete", id)
		for verb in ar.Story_Choice_Verb {
			testing.expectf(t, dilemma.intents[verb] != "" && dilemma.outcomes[verb] != "", "%v/%v lacks authored choice text", id, verb)
		}
	}

	testing.expect(t, len(ar.Story_Motif_Id) == 8 && len(ar.STORY_MOTIFS) == 8, "location corpus must contain eight motifs")
	for id in ar.Story_Motif_Id {
		motif := ar.STORY_MOTIFS[id]
		testing.expectf(t, motif.theme_name == ar.THEMES[int(id)].name, "%v motif drifted from the typed theme order", id)
		testing.expect(t, motif.image != "" && motif.danger != "", "motif prose is incomplete")
	}

	testing.expect(t, len(ar.STORY_TETHERS) == 5 && len(ar.STORY_TYRANT_OFFERS) == 5, "every archetype needs a tether and Tyrant offer")
	for archetype in ar.Archetype_Id {
		tether := ar.STORY_TETHERS[archetype]
		testing.expectf(t, tether.name != "" && ar.STORY_TYRANT_OFFERS[archetype] != "", "%v tether/offer missing", archetype)
		for stage in ar.Story_Tether_Stage {
			testing.expectf(t, tether.beats[stage].motive != "" && tether.beats[stage].speech != "", "%v/%v tether beat missing", archetype, stage)
		}
		for verb in ar.Story_Choice_Verb {
			testing.expectf(t, tether.crisis_choices[verb].intent != "" && tether.crisis_choices[verb].outcome != "", "%v/%v crisis choice missing", archetype, verb)
		}
	}

	ending_count := 0
	for archetype in ar.Archetype_Id {
		for verb in ar.Story_Choice_Verb {
			ending := ar.STORY_ENDINGS[archetype][verb]
			testing.expectf(t, ending.title != "" && ending.body != "" && ending.slug != "", "%v/%v ending missing", archetype, verb)
			testing.expect(t, ar.STORY_CRISIS_ECHOES[archetype][verb] != "", "every crisis outcome needs an ending echo")
			ending_count += 1
		}
	}
	testing.expect(t, ending_count == 15, "five archetypes x three gate verbs must yield fifteen endings")
	for verb in ar.Story_Choice_Verb {
		testing.expect(t, ar.STORY_GATE_CHOICES[verb].label != "" && ar.STORY_GATE_CHOICES[verb].detail != "", "all three gate choices need label and detail")
	}
	for road in ar.Story_Road {
		if road == .Forsaken || road == .Unwritten do continue
		testing.expectf(t, ar.STORY_ENDING_ROAD_CODAS[road] != "", "%v road has no ending coda", road)
	}
	for archetype in ar.Archetype_Id {
		testing.expect(t, ar.STORY_ENDING_FORSAKEN_CODAS[archetype] != "", "every archetype needs a Forsaken coda")
	}
}

@(test)
mx_story_generation_is_repeatable_divergent_and_stream_isolated :: proc(t: ^testing.T) {
	seeds := [4]u64{7, 424242, 90210, 31337}
	for archetype in ar.Archetype_Id {
		for seed in seeds {
			a := ar.story_generate(seed, archetype, 11, .Crypt_Of_Ash, .Blood_Moon)
			b := ar.story_generate(seed, archetype, 11, .Crypt_Of_Ash, .Blood_Moon)
			testing.expectf(t, story_test_same_generation(&a, &b), "%v seed %v did not replay identically", archetype, seed)
			testing.expect(t, a.seed == seed, "public story seed remains the run seed")
			testing.expect(t, a.stream_seed == ar.derive_seed(seed, ar.STORY_SALT), "story stream must derive from the run seed")
			ar.story_state_destroy(&a)
			ar.story_state_destroy(&b)
		}
	}

	a := ar.story_generate(1, .Arcanist, 1, .Crypt_Of_Ash, .Blood_Moon)
	b := ar.story_generate(2, .Arcanist, 1, .Crypt_Of_Ash, .Blood_Moon)
	diverged := a.chapter_index != b.chapter_index || a.faction != b.faction || a.rival_faction != b.rival_faction || a.relic != b.relic || a.beats != b.beats
	testing.expect(t, diverged, "different run seeds should produce different story rolls")
	ar.story_state_destroy(&a)
	ar.story_state_destroy(&b)

	// Story generation owns a local derived stream. Interleaving it cannot move
	// a caller's gameplay PCG state or alter a deterministic run plan.
	caller := ar.rng_make(ar.derive_seed(77, 4), stream = 5)
	control := caller
	for _ in 0 ..< 5 do testing.expect(t, ar.rng_next(&caller) == ar.rng_next(&control), "control stream setup diverged")
	story := ar.story_generate(77, .Ranger, 3, .Moonlit_Aquifer, .Elite_Hunt)
	for _ in 0 ..< 32 {
		testing.expect(t, ar.rng_next(&caller) == ar.rng_next(&control), "story generation consumed the caller/gameplay RNG")
	}
	plan_before, modifier_before := ar.generate_run_plan(77)
	interleaved := ar.story_generate(77, .Warden)
	plan_after, modifier_after := ar.generate_run_plan(77)
	testing.expect(t, plan_before == plan_after && modifier_before == modifier_after, "story generation perturbed the run-plan stream")
	ar.story_state_destroy(&story)
	ar.story_state_destroy(&interleaved)
}

@(test)
mx_story_schedule_pins_tethers_and_authored_crisis :: proc(t: ^testing.T) {
	seeds := [3]u64{7, 2026, 424242}
	for archetype in ar.Archetype_Id {
		for seed in seeds {
			story := ar.story_generate(seed, archetype, 4, .Frozen_Ossuary, .Thin_Veil)
			tether := ar.STORY_TETHERS[archetype]
			testing.expect(t, len(story.beats) == 10, "story state must contain ten beats")
			testing.expect(t, story.beats[0].motif == .Frozen_Ossuary, "the selected first-floor theme must be preserved")
			for depth in 1 ..= ar.STORY_BEAT_COUNT {
				beat := &story.beats[depth - 1]
				testing.expectf(t, beat.depth == depth, "beat index %v carries depth %v", depth - 1, beat.depth)
				testing.expect(t, beat.summary != "" && ar.story_beat_title(beat) != "" && ar.story_beat_truth(beat) != "", "every beat needs composed/reveal prose")
				for verb in ar.Story_Choice_Verb {
					choice := beat.choices[verb]
					testing.expectf(t, choice.verb == verb && choice.label == ar.STORY_CHOICE_LABELS[verb], "D%v/%v choice identity drifted", depth, verb)
					testing.expect(t, choice.intent != "" && choice.outcome != "", "every beat choice needs intent and outcome")
				}
			}

			pins := [3]struct{depth: int, dilemma: ar.Story_Dilemma_Id}{{5, .Door_That_Remembers}, {8, .Gates_Confession}, {9, .Last_Guests_Mask}}
			for pin in pins do testing.expectf(t, story.beats[pin.depth - 1].dilemma == pin.dilemma, "D%v pinned dilemma changed", pin.depth)

			stages := [3]struct{depth: int, stage: ar.Story_Tether_Stage}{{1, .Meet}, {5, .Reveal}, {9, .Crisis}}
			for expected in stages {
				beat := story.beats[expected.depth - 1]
				tether_beat := tether.beats[expected.stage]
				testing.expectf(t, beat.is_tether && beat.tether_stage == expected.stage, "D%v is not the expected tether stage", expected.depth)
				testing.expect(t, beat.guest_role == tether.role && beat.guest_name == tether.name, "tether identity must remain fixed")
				testing.expect(t, beat.guest_motive == tether_beat.motive && beat.dialogue == tether_beat.speech, "tether motive/speech substitution changed")
			}
			testing.expect(t, story.beats[7].dialogue == ar.STORY_TYRANT_OFFERS[archetype], "D8 must substitute the archetype Tyrant offer")
			for verb in ar.Story_Choice_Verb {
				crisis := tether.crisis_choices[verb]
				choice := story.beats[8].choices[verb]
				testing.expectf(t, choice.intent == crisis.intent && choice.outcome == crisis.outcome, "%v D9/%v crisis prose changed", archetype, verb)
			}

			// Nine unpinned dilemma templates feed seven free depths without repeats.
			for i in 0 ..< ar.STORY_BEAT_COUNT {
				depth_i := i + 1
				if depth_i == 5 || depth_i == 8 || depth_i == 9 do continue
				for j in i + 1 ..< ar.STORY_BEAT_COUNT {
					depth_j := j + 1
					if depth_j == 5 || depth_j == 8 || depth_j == 9 do continue
					testing.expectf(t, story.beats[i].dilemma != story.beats[j].dilemma, "free dilemma repeated at D%v and D%v", depth_i, depth_j)
				}
			}
			ar.story_state_destroy(&story)
		}
	}
}

@(test)
mx_story_choice_vectors_flags_unanswered_and_milestones :: proc(t: ^testing.T) {
	story := ar.story_generate(7001, .Warden)
	defer ar.story_state_destroy(&story)

	aid := story.beats[0].choices[.Aid]
	testing.expect(t, story_test_near(aid.effects[.Enemy_Pressure], -0.0575), "D1 Aid enemy pressure changed")
	testing.expect(t, story_test_near(aid.effects[.Shrine_Bonus], 0.0525), "D1 Aid shrine vector changed")
	testing.expect(t, story_test_near(aid.effects[.Secret_Bonus], 0.03125), "D1 Aid secret vector changed")
	testing.expect(t, story_test_near(aid.effects[.Damage_Resist], 0.03625), "D1 Aid resist vector changed")
	testing.expect(t, story_test_near(aid.effects[.Healing_Echo], 0.02625), "D1 Aid healing vector changed")
	testing.expect(t, aid.flags == [2]ar.Story_Choice_Tag{.Mercy, .Witness}, "Aid tags changed")

	bargain := story.beats[9].choices[.Bargain]
	testing.expect(t, story_test_near(bargain.effects[.Loot_Bonus], 0.1000), "D10 Bargain loot vector changed")
	testing.expect(t, story_test_near(bargain.effects[.Blood_Price], 0.0375), "D10 Bargain blood vector changed")
	defy := story.beats[9].choices[.Defy]
	testing.expect(t, story_test_near(defy.effects[.Enemy_Pressure], 0.1000), "D10 Defy enemy vector changed")
	testing.expect(t, story_test_near(defy.effects[.Hunter_Pressure], 0.0575), "D10 Defy hunter vector changed")

	testing.expect(t, ar.story_record_choice(&story, 1, .Aid), "fresh D1 choice should record")
	testing.expect(t, !ar.story_record_choice(&story, 1, .Defy), "resolved beat must not double-apply")
	testing.expect(t, story.beats[0].resolution == .Aid && story.beats[0].outcome == aid.outcome, "choice resolution/outcome not retained")
	testing.expect(t, story.flags.choice_tags[0][.Mercy] && story.flags.choice_tags[0][.Witness], "depth-scoped Aid flags missing")
	testing.expect(t, story_test_near(ar.story_effect(&story, .Enemy_Pressure), -0.0575), "recording a choice must add its vector")

	testing.expect(t, ar.story_record_choice(&story, 5, .Bargain), "D5 choice should record")
	testing.expect(t, story.flags.secret_revealed, "D5 must reveal the canonical archetype secret")
	secret_logged := false
	for i in 0 ..< story.log.count {
		if strings.contains(story.log.entries[i], ar.STORY_ARCS[.Warden].secret) do secret_logged = true
	}
	testing.expect(t, secret_logged, "D5 reveal must enter the bounded story log")

	testing.expect(t, ar.story_record_choice(&story, 8, .Defy), "D8 Defy should record")
	testing.expect(t, ar.story_true_name_known(&story, .Sorn), "D8 Defy must learn Sorn's true name")
	testing.expect(t, story.log.entries[0] == ar.STORY_MEMORY_ERASURE, "learning a true name must erase the oldest eligible memory")
	testing.expect(t, !ar.story_learn_true_name(&story, .Sorn), "true names are learned once")

	testing.expect(t, ar.story_record_choice(&story, 9, .Bargain), "D9 crisis should record")
	crisis, crisis_ok := ar.story_crisis_verb(&story)
	testing.expect(t, crisis_ok && crisis == .Bargain && story.flags.crisis == .Bargain, "D9 must retain the crisis verb")

	unanswered := ar.story_generate(7002, .Rogue)
	defer ar.story_state_destroy(&unanswered)
	testing.expect(t, ar.story_record_unanswered(&unanswered, 2), "fresh beat should accept unanswered resolution")
	testing.expect(t, !ar.story_record_unanswered(&unanswered, 2) && !ar.story_record_choice(&unanswered, 2, .Aid), "unanswered resolution is idempotent and final")
	beat := unanswered.beats[1]
	testing.expect(t, beat.resolution == .Unanswered && beat.outcome_owned && strings.contains(beat.outcome, beat.guest_name), "unanswered beat needs its authored guest-specific outcome")
	testing.expect(t, unanswered.flags.unanswered[1] && unanswered.flags.forsaken[1], "unanswered/forsaken depth flags missing")
	testing.expect(t, story_test_near(unanswered.effects[.Enemy_Pressure], 0.045), "unanswered enemy pressure changed")
	testing.expect(t, story_test_near(unanswered.effects[.Trap_Bonus], 0.035), "unanswered trap pressure changed")
	testing.expect(t, story_test_near(unanswered.effects[.Curse_Bonus], 0.015), "unanswered curse pressure changed")
	testing.expect(t, story_test_near(unanswered.effects[.Boss_Pressure], 0.025), "unanswered boss pressure changed")
	testing.expect(t, story_test_near(unanswered.effects[.Hunter_Pressure], 0.040), "unanswered hunter pressure changed")

	acolyte := ar.story_generate(7003, .Acolyte)
	defer ar.story_state_destroy(&acolyte)
	testing.expect(t, ar.story_record_choice(&acolyte, 8, .Aid), "Acolyte D8 Aid should record")
	testing.expect(t, ar.story_true_name_known(&acolyte, .Sorn), "Acolyte Aid is the alternate Sorn-name route")
}

@(test)
mx_story_roads_use_completed_acts_forsaken_greater_equal_and_stable_ties :: proc(t: ^testing.T) {
	story := ar.story_generate(77, .Warden)
	defer ar.story_state_destroy(&story)
	testing.expect(t, ar.story_road(&story, 1) == .Unwritten && ar.story_road(&story, 3) == .Unwritten, "road does not exist before the first completed act")
	testing.expect(t, ar.story_road(&story, 4) == .Unwritten, "an unanswered empty act stays unwritten")

	story.beats[0].resolution = .Aid
	story.beats[1].resolution = .Bargain
	story.beats[2].resolution = .Defy
	testing.expect(t, ar.story_road(&story, 4) == .Witness, "three-way tie priority must be aid first")

	story.beats[0].resolution = .Bargain
	story.beats[1].resolution = .Defy
	story.beats[2].resolution = .Unresolved
	testing.expect(t, ar.story_road(&story, 4) == .Debtor, "bargain must beat defy on a tie when aid is behind")

	story.beats[0].resolution = .Defy
	story.beats[1].resolution = .Defy
	story.beats[2].resolution = .Aid
	testing.expect(t, ar.story_road(&story, 4) == .Defiant, "strict Defy majority must choose the Defiant road")

	story.beats[0].resolution = .Unanswered
	story.beats[1].resolution = .Aid
	story.beats[2].resolution = .Unresolved
	testing.expect(t, ar.story_road(&story, 4) == .Forsaken, "Forsaken must use unanswered >= answered")

	story.beats[0].resolution = .Unanswered
	story.beats[1].resolution = .Aid
	story.beats[2].resolution = .Bargain
	testing.expect(t, ar.story_road(&story, 4) == .Witness, "one unanswered does not override two answered; answered tie remains Aid-first")

	story_test_reset_resolutions(&story)
	for i in 0 ..< 3 do story.beats[i].resolution = .Aid
	for i in 3 ..< 6 do story.beats[i].resolution = .Bargain
	testing.expect(t, ar.story_road(&story, 7) == .Witness, "six-beat Aid/Bargain tie retains Aid priority")
	for i in 6 ..< 9 do story.beats[i].resolution = .Defy
	testing.expect(t, ar.story_road(&story, 10) == .Witness, "three-way act tally retains Aid priority")
}

@(test)
mx_story_all_fifteen_endings_gate_flags_and_codas_resolve :: proc(t: ^testing.T) {
	ending_titles: [ar.STORY_ENDING_ASSET_COUNT]string
	ending_keys: [ar.STORY_ENDING_ASSET_COUNT]string
	count := 0
	for archetype in ar.Archetype_Id {
		for verb in ar.Story_Choice_Verb {
			ending := ar.story_ending_for(archetype, verb)
			testing.expectf(t, ending.title != "" && ending.body != "", "%v/%v ending failed to resolve", archetype, verb)
			ending_titles[count] = ending.title
			ending_keys[count] = ar.story_ending_panel_asset_key(archetype, verb)
			story := ar.story_generate(9000 + u64(count), archetype)
			testing.expect(t, ar.story_record_gate_choice(&story, verb), "fresh Gate must accept one final verb")
			testing.expect(t, !ar.story_record_gate_choice(&story, verb), "Gate verb is immutable once chosen")
			resolved := ar.story_resolve_recorded_ending(&story, 1)
			testing.expect(t, resolved.valid && resolved.verb == verb && resolved.ending == ending, "recorded Gate choice selected the wrong ending")
			testing.expect(t, resolved.road == .Unwritten, "depth-one ending probe should have no completed road")
			ar.story_ending_result_destroy(&resolved)
			ar.story_state_destroy(&story)
			count += 1
		}
	}
	testing.expect(t, count == 15, "did not traverse all fifteen endings")
	story_test_expect_unique(t, ending_titles[:], "ending title")
	story_test_expect_unique(t, ending_keys[:], "ending panel")

	// Crisis echo, dominant road, then Liss's true-name rider compose in that
	// order for the epilogue context.
	witness := ar.story_generate(9100, .Warden)
	for depth in 1 ..= 9 do testing.expect(t, ar.story_record_choice(&witness, depth, .Aid), "Aid route setup failed")
	testing.expect(t, ar.story_learn_true_name(&witness, .Liss), "Liss helper should learn the name once")
	result := ar.story_resolve_ending(&witness, .Aid)
	testing.expect(t, result.valid && result.road == .Witness, "all-Aid run must resolve Witness")
	testing.expect(t, strings.contains(result.coda, ar.STORY_CRISIS_ECHOES[.Warden][.Aid]), "crisis echo missing from ending coda")
	testing.expect(t, strings.contains(result.coda, ar.STORY_ENDING_ROAD_CODAS[.Witness]), "Witness road coda missing")
	testing.expect(t, strings.contains(result.coda, ar.STORY_LISS_AID_CODA), "known Liss + Aid rider missing")
	ar.story_ending_result_destroy(&result)
	ar.story_state_destroy(&witness)

	// Exhaust every crisis echo against a stable Witness road.
	for archetype in ar.Archetype_Id {
		for crisis in ar.Story_Choice_Verb {
			story := ar.story_generate(9200 + u64(int(archetype) * 3 + int(crisis)), archetype)
			for i in 0 ..< 9 do story.beats[i].resolution = .Aid
			story.flags.crisis = ar.story_resolution_from_verb(crisis)
			resolved := ar.story_resolve_ending(&story, .Bargain)
			testing.expectf(t, strings.contains(resolved.coda, ar.STORY_CRISIS_ECHOES[archetype][crisis]), "%v/%v crisis echo not composed", archetype, crisis)
			testing.expect(t, strings.contains(resolved.coda, ar.STORY_ENDING_ROAD_CODAS[.Witness]), "road coda must compose beside crisis echo")
			ar.story_ending_result_destroy(&resolved)
			ar.story_state_destroy(&story)
		}
	}

	// Every archetype gets its own Forsaken cut and never the ordinary road line.
	for archetype in ar.Archetype_Id {
		story := ar.story_generate(9300 + u64(archetype), archetype)
		for i in 0 ..< 9 do story.beats[i].resolution = .Unanswered
		resolved := ar.story_resolve_ending(&story, .Defy)
		testing.expect(t, resolved.road == .Forsaken, "all-unanswered run must resolve Forsaken")
		testing.expectf(t, strings.contains(resolved.coda, ar.STORY_ENDING_FORSAKEN_CODAS[archetype]), "%v Forsaken coda missing", archetype)
		testing.expect(t, !strings.contains(resolved.coda, ar.STORY_ENDING_ROAD_CODAS[.Witness]), "Forsaken must replace ordinary road codas")
		ar.story_ending_result_destroy(&resolved)
		ar.story_state_destroy(&story)
	}
}

@(test)
mx_story_safe_token_substitution_preserves_unknown_tokens :: proc(t: ^testing.T) {
	tokens := [2]ar.Story_Text_Token{{"guest", "Nim Rue"}, {"depth", "8"}}
	formatted := ar.story_format_text(
		"{guest} waits at depth {depth}; {unknown} stays; {{Last Gate}}; {unterminated",
		tokens[:],
	)
	defer delete(formatted)
	testing.expect(
		t,
		formatted == "Nim Rue waits at depth 8; {unknown} stays; {Last Gate}; {unterminated",
		"known tokens should expand while unknown/malformed tokens survive",
	)

	unknown_only := ar.story_format_text("before {missing} after", nil)
	defer delete(unknown_only)
	testing.expect(t, unknown_only == "before {missing} after", "unknown token must remain byte-for-byte visible")
}

@(test)
mx_story_semantic_asset_keys_have_exact_cardinalities_and_stable_slugs :: proc(t: ^testing.T) {
	testing.expect(t, ar.STORY_OMEN_ASSET_COUNT == 8 && len(ar.STORY_OMEN_ASSET_KEYS) == 8, "omen asset registry needs eight keys")
	testing.expect(t, ar.STORY_GUEST_ASSET_COUNT == 10 && len(ar.STORY_GUEST_BACKDROP_ASSET_KEYS) == 10, "guest backdrop registry needs ten keys")
	testing.expect(t, ar.STORY_ENDING_ASSET_COUNT == 15, "ending panel registry needs fifteen keys")
	testing.expect(t, ar.STORY_RELIC_ASSET_COUNT == 10 && len(ar.STORY_RELIC_ICON_ASSET_KEYS) == 10, "relic icon registry needs ten keys")
	testing.expect(t, ar.STORY_PORTRAIT_ASSET_COUNT == 30, "portrait registry needs thirty role/name keys")

	omen_keys: [ar.STORY_OMEN_ASSET_COUNT]string
	guest_keys: [ar.STORY_GUEST_ASSET_COUNT]string
	relic_keys: [ar.STORY_RELIC_ASSET_COUNT]string
	ending_keys: [ar.STORY_ENDING_ASSET_COUNT]string
	portrait_keys: [ar.STORY_PORTRAIT_ASSET_COUNT]string

	for id in ar.Story_Motif_Id {
		omen_keys[int(id)] = ar.story_omen_asset_key(id)
		testing.expect(t, ar.story_motif_slug(id) == ar.STORY_MOTIFS[id].slug, "motif slug helper drifted from registry")
		testing.expect(t, strings.contains(omen_keys[int(id)], ar.story_motif_slug(id)), "omen key must carry its semantic motif slug")
	}
	for role in ar.Story_Guest_Role_Id {
		guest_keys[int(role)] = ar.story_guest_backdrop_asset_key(role)
		testing.expect(t, ar.story_guest_role_slug(role) == ar.STORY_GUEST_TEMPLATES[role].slug, "role slug helper drifted")
		for variant in 0 ..< ar.STORY_GUEST_VARIANTS {
			index := int(role) * ar.STORY_GUEST_VARIANTS + variant
			key, key_ok := ar.story_guest_portrait_asset_key(role, variant)
			slug, slug_ok := ar.story_guest_name_slug(role, variant)
			testing.expect(t, key_ok && slug_ok, "valid portrait variant rejected")
			testing.expect(t, strings.contains(key, ar.story_guest_role_slug(role)) && strings.contains(key, slug), "portrait key must identify role and person semantically")
			portrait_keys[index] = key
		}
	}
	if _, ok := ar.story_guest_portrait_asset_key(.Oathless_Knight, -1); ok do testing.expect(t, false, "negative portrait variant accepted")
	if _, ok := ar.story_guest_portrait_asset_key(.Oathless_Knight, ar.STORY_GUEST_VARIANTS); ok do testing.expect(t, false, "out-of-range portrait variant accepted")

	for relic in ar.Story_Relic_Id {
		relic_keys[int(relic)] = ar.story_relic_icon_asset_key(relic)
		testing.expect(t, ar.story_relic_slug(relic) == ar.STORY_RELICS[relic].slug, "relic slug helper drifted")
		testing.expect(t, strings.contains(relic_keys[int(relic)], ar.story_relic_slug(relic)), "relic key must carry its semantic slug")
	}
	ending_count := 0
	for archetype in ar.Archetype_Id {
		for verb in ar.Story_Choice_Verb {
			ending_keys[ending_count] = ar.story_ending_panel_asset_key(archetype, verb)
			testing.expect(t, ar.story_ending_slug(archetype, verb) == ar.STORY_ENDINGS[archetype][verb].slug, "ending slug helper drifted")
			testing.expect(t, strings.contains(ending_keys[ending_count], ar.story_ending_slug(archetype, verb)), "ending key must carry its semantic slug")
			ending_count += 1
		}
	}

	story_test_expect_unique(t, omen_keys[:], "omen")
	story_test_expect_unique(t, guest_keys[:], "guest backdrop")
	story_test_expect_unique(t, relic_keys[:], "relic icon")
	story_test_expect_unique(t, ending_keys[:], "ending panel")
	story_test_expect_unique(t, portrait_keys[:], "guest portrait")
}

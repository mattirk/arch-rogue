package archrogue_tests

// Headless contracts for presentation math. The renderer consumes these pure
// helpers, while authoritative LOS and deterministic simulation remain in Run.

import "core:testing"
import "core:math"
import ar "../src"

@(private = "file")
visual_near :: proc(a, b: f32, epsilon: f32 = 1e-4) -> bool {
	return abs(a - b) <= epsilon
}

@(test)
visual_world_sprite_layout_preserves_existing_world_art :: proc(t:^testing.T) {
	// The shared helper must preserve the original renderer's operations for
	// every world sprite, including non-floor anchors and fractional positions.
	for tile in ([3]ar.Vec2{{0,0},{-3.25,7.75},{39,47}}) {
		for anchor in ([3]ar.Vec2{{256,320},{32,48},{141,287}}) {
			for scale in ([3]f32{.125,.75,f32(ar.TILE_W)/448}) {
				position,size:=ar.visual_world_sprite_layout(tile,{512,384},anchor,scale)
				center:=ar.world_from_tile(tile+{.5,.5})
				testing.expect(t,position==ar.Vec2{center.x-anchor.x*scale,center.y-anchor.y*scale},"existing world anchors must not move")
				testing.expect(t,size==ar.Vec2{512*scale,384*scale},"existing world art must retain its uniform scale")
			}
		}
	}
}

@(test)
visual_turn_page_floor_matches_mist_chamber_slab :: proc(t:^testing.T) {
	// Both 512px masters have the same source silhouette, anchor and scale;
	// the asset verifier pins their pixels and matching manifest metadata.
	face:=[4]ar.Vec2{{256,176},{512,304},{256,432},{0,304}}
	corners:=[4]ar.Vec2{{0,0},{1,0},{1,1},{0,1}}
	for x in 0..<ar.TURN_PAGE_SIZE do for y in 0..<ar.TURN_PAGE_SIZE {
		tile:=ar.Vec2{f32(x),f32(y)}
		position,size:=ar.visual_world_sprite_layout(tile,{512,512},{256,320},f32(ar.TILE_W)/512)
		for pixel,i in face {
			actual:=position+pixel/512*size
			expected:=ar.world_from_tile(tile+corners[i])+ar.VISUAL_TURN_PAGE_SURFACE_OFFSET
			testing.expect(t,visual_near(actual.x,expected.x)&&visual_near(actual.y,expected.y),"floor face must span one 64x32 cell at the Mist chamber's surface elevation")
		}
		center:=position+ar.Vec2{256,320}/512*size
		expected:=ar.world_from_tile(tile+{.5,.5})
		testing.expect(t,visual_near(center.x,expected.x)&&visual_near(center.y,expected.y),"player feet retain the Mist chamber's anchor")
		top:=position+ar.Vec2{256,432}/512*size
		bottom:=position+ar.Vec2{256,512}/512*size
		testing.expect(t,visual_near(bottom.y-top.y,10),"the exposed slab must have the same 10-world-pixel thickness as the Mist chamber")
	}
}

@(test)
visual_turn_page_exposed_undersides_join_without_steps_at_any_zoom :: proc(t:^testing.T) {
	// Adjacent slabs meet at the same lower-edge pixel, not just the top face.
	for zoom in ([4]f32{.75,1.3,2.25,4}) {
		for axis in 0..<2 do for n in 0..<ar.TURN_PAGE_SIZE-1 {
			tile:=ar.Vec2{f32(n),9};neighbor:=tile
			neighbor[axis]+=1
			a,asize:=ar.visual_world_sprite_layout(tile,{512,512},{256,320},f32(ar.TILE_W)/512)
			b,bsize:=ar.visual_world_sprite_layout(neighbor,{512,512},{256,320},f32(ar.TILE_W)/512)
			bottom:=a+ar.Vec2{256,512}/512*asize
			side:=b+ar.Vec2{axis==0?0:512,384}/512*bsize
			pan:=ar.Vec2{-37.25,18.375}
			left:=(bottom-pan)*zoom;right:=(side-pan)*zoom
			testing.expect(t,visual_near(left.x,right.x,.001)&&visual_near(left.y,right.y,.001),"exposed slab edges must stay level through fractional zoom/pan")
		}
	}
}

@(test)
visual_turn_page_roll_is_bounded_smooth_and_keeps_the_board_in_frame :: proc(t:^testing.T) {
	center:=ar.world_from_tile({5,5})
	previous:=ar.visual_turn_page_motion(0)
	for frame in 0..=3600 {
		motion:=ar.visual_turn_page_motion(f32(frame)/60)
		testing.expect(t,abs(motion.rotation)<=8&&abs(motion.drift.y)<=3)
		testing.expect(t,abs(motion.rotation-previous.rotation)<.015&&abs(motion.drift.y-previous.drift.y)<.027,"motion must remain slow and continuous, including the turnarounds")
		for corner in ([4]ar.Vec2{{0,0},{10,0},{10,10},{0,10}}) {
			for side in ([2]f32{-2,8}) {
				point:=ar.visual_turn_page_motion_point(ar.world_from_tile(corner)+ar.Vec2{0,side},motion)-center
				testing.expect(t,abs(point.x)<340&&abs(point.y)<180,"posed slab and drift must fit the existing camera margins")
			}
		}
		previous=motion
	}
	testing.expect(t,visual_near(ar.visual_turn_page_motion(15).rotation,8))
	testing.expect(t,visual_near(ar.visual_turn_page_motion(45).rotation,-8))
	testing.expect(t,visual_near(previous.rotation,0)&&visual_near(previous.drift.y,0),"the minute-long cycle must close without a snap")
}

@(test)
visual_turn_page_motion_keeps_shared_edges_and_slab_lengths :: proc(t:^testing.T) {
	for age in ([4]f32{3,15,33,45}) do for zoom in ([3]f32{.75,1.3,4}) {
		motion:=ar.visual_turn_page_motion(age)
		for x in 0..<9 do for y in 0..<9 {
			a,asize:=ar.visual_world_sprite_layout({f32(x),f32(y)},{512,512},{256,320},.125)
			b,bsize:=ar.visual_world_sprite_layout({f32(x+1),f32(y)},{512,512},{256,320},.125)
			left:=ar.visual_turn_page_motion_point(a+ar.Vec2{256,512}/512*asize,motion)*zoom
			right:=ar.visual_turn_page_motion_point(b+ar.Vec2{0,384}/512*bsize,motion)*zoom
			testing.expect(t,visual_near(left.x,right.x,.001)&&visual_near(left.y,right.y,.001),"rotation must retain the shared underside join")
			top:=ar.visual_turn_page_motion_point(a+ar.Vec2{256,432}/512*asize,motion)*zoom
			d:=left-top
			testing.expect(t,visual_near(math.hypot(d.x,d.y),10*zoom,.001),"roll must not stretch slab thickness")
		}
	}
}

@(test)
visual_turn_page_motion_clock_survives_pages_retries_and_pause :: proc(t:^testing.T) {
	app:=turn_page_test_start(9)
	defer ar.run_destroy(&app.run)
	initial:=ar.visual_turn_page_motion_age(&app,1)
	testing.expect(t,initial==0)
	_=ar.turn_page_tick(&app,{},.25)
	age:=ar.visual_turn_page_motion_age(&app,1)
	testing.expect(t,visual_near(age,.25,.001))
	testing.expect(t,visual_near(ar.visual_turn_page_motion_age(&app,.5),age-ar.SIM_DT*.5,.001))
	app.story_minigame.score+=1
	ar.turn_page_begin_page(&app)
	testing.expect(t,ar.visual_turn_page_motion_age(&app,1)==age,"new pages must not restart the motion")
	ar.turn_page_wrong(&app,{4,4})
	testing.expect(t,ar.visual_turn_page_motion_age(&app,1)==age,"a wrong step must not reset the pose")
	app.mode=.Paused
	for alpha in ([3]f32{0,.5,1}) do testing.expect(t,ar.visual_turn_page_motion_age(&app,alpha)==age,"pause ignores changing render interpolation")
	app.story_minigame.active=false
	testing.expect(t,ar.visual_turn_page_motion_age(&app,1)==0,"other worlds must not acquire manuscript motion")
}

@(test)
visual_turn_page_parchment_stays_sparse_dim_and_slow :: proc(t:^testing.T) {
	testing.expect(t,ar.VISUAL_TURN_PAGE_PARCHMENT_COUNT==4,"the void has a fixed four-scrap budget")
	for seed in 0..<16 do for second in 2..=720 {
		for index in 0..<ar.VISUAL_TURN_PAGE_PARCHMENT_COUNT {
			particle:=ar.visual_turn_page_parchment(u64(seed),f32(second),index)
			next:=ar.visual_turn_page_parchment(u64(seed),f32(second)+ar.SIM_DT,index)
			delta:=next.offset-particle.offset
			testing.expect(t,particle.variant>=0&&particle.variant<3,"only the three parchment textures may be selected")
			testing.expect(t,particle.width>=14&&particle.width<=24,"distant scraps must remain small")
			testing.expect(t,particle.opacity>=.12&&particle.opacity<=.221,"parchment must stay much fainter than the floor")
			testing.expect(t,abs(particle.offset.x)<=450&&particle.offset.y>=-245&&particle.offset.y<=310,"orbits stay near the platform margins")
			testing.expect(t,math.hypot(delta.x,delta.y)<.55,"drift must remain below 33 world pixels per second")
			testing.expect(t,abs(next.rotation-particle.rotation)<.045,"tumbling must stay gentle and continuous")
			testing.expect(t,next.opacity==particle.opacity,"scraps must not pulse once the entry fade finishes")
			for other in 0..<index {
				separation:=particle.offset-ar.visual_turn_page_parchment(u64(seed),f32(second),other).offset
				testing.expect(t,math.hypot(separation.x,separation.y)>150,"slow phase drift must never bunch the four scraps together")
			}
		}
	}
	for index in ([4]int{-1,4,5,100}) {
		testing.expect(t,ar.visual_turn_page_parchment(97,30,index).opacity==0,"an invalid index must never add particles")
	}
}

@(test)
visual_turn_page_parchment_reconstructs_from_seed_and_saved_clock :: proc(t:^testing.T) {
	app:=turn_page_test_start(9)
	defer ar.run_destroy(&app.run)
	for _ in 0..<180 do _=ar.turn_page_tick(&app,{},ar.SIM_DT)
	age:=ar.visual_turn_page_motion_age(&app,1)
	seed:=app.story_minigame.seed
	before:[ar.VISUAL_TURN_PAGE_PARCHMENT_COUNT]ar.Visual_Turn_Page_Parchment
	for index in 0..<len(before) {
		before[index]=ar.visual_turn_page_parchment(seed,age,index)
		initial:=ar.visual_turn_page_parchment(seed,0,index)
		half:=ar.visual_turn_page_parchment(seed,1,index)
		full:=ar.visual_turn_page_parchment(seed,2,index)
		testing.expect(t,initial.opacity==0&&half.opacity>0&&half.opacity<full.opacity,"parchment must fade into the empty void")
		testing.expect(t,ar.visual_turn_page_parchment(seed,-1,index)==initial,"negative interpolation age must use the entry pose")
	}
	app.story_minigame.score+=1
	ar.turn_page_begin_page(&app)
	ar.turn_page_wrong(&app,{4,4})
	app.mode=.Paused
	for alpha in ([3]f32{0,.5,1}) do for index in 0..<len(before) {
		restored:=ar.visual_turn_page_parchment(seed,ar.visual_turn_page_motion_age(&app,alpha),index)
		testing.expect(t,restored==before[index],"page changes, retries and pause must retain the same background")
	}
	// Reconstruction needs neither accumulated particle positions nor gameplay
	// RNG state: sampling unrelated seeds/times cannot affect a restored view.
	for index in 0..<len(before) {
		_=ar.visual_turn_page_parchment(seed+1,900,index)
		testing.expect(t,ar.visual_turn_page_parchment(seed,age,index)==before[index])
		testing.expect(t,ar.visual_turn_page_parchment(seed+1,age,index).offset!=before[index].offset,"different manuscript seeds should vary the distant scraps")
	}
}

@(test)
visual_turn_page_void_glyph_leaves_long_empty_intervals :: proc(t:^testing.T) {
	testing.expect(t,ar.VISUAL_TURN_PAGE_VOID_GLYPH_COUNT==1,"only one distant glyph may be drawn")
	for seed in 0..<16 {
		seen:u8
		previous_side:f32
		for cycle in 0..<6 {
			start:=f32(cycle)*28
			peak:=ar.visual_turn_page_void_glyph(u64(seed),start+9)
			testing.expect(t,visual_near(peak.opacity,.055),"the faint glyph reaches its peak halfway through an 18-second appearance")
			testing.expect(t,peak.variant>=0&&peak.variant<3)
			seen|=u8(1)<<u8(peak.variant)
			if cycle>0 do testing.expect(t,peak.offset.x*previous_side<0,"each fully faded glyph moves to the opposite flank")
			previous_side=peak.offset.x
			testing.expect(t,ar.visual_turn_page_void_glyph(u64(seed),start).opacity==0,"every glyph must begin invisible")
			testing.expect(t,ar.visual_turn_page_void_glyph(u64(seed),start+15).opacity>0,"the glyph should still be fading during the 15-second review pose")
			for blank_frame in 0..<600 {
				trace:=ar.visual_turn_page_void_glyph(u64(seed),start+18+f32(blank_frame)/60)
				testing.expect(t,trace.opacity==0,"each appearance must be followed by ten seconds of completely empty void")
			}
		}
		testing.expect(t,seen==7,"the three historical motifs must all appear over successive cycles")
	}
}

@(test)
visual_turn_page_void_traces_stay_faint_bounded_and_continuous :: proc(t:^testing.T) {
	testing.expect(t,ar.VISUAL_TURN_PAGE_INK_WISP_COUNT==2,"only two broken ink wisps may be drawn")
	for seed in 0..<8 {
		previous:=ar.visual_turn_page_void_glyph(u64(seed),0)
		for frame in 1..=5400 {
			age:=f32(frame)/30
			glyph:=ar.visual_turn_page_void_glyph(u64(seed),age)
			testing.expect(t,glyph.opacity>=0&&glyph.opacity<=.0551)
			testing.expect(t,abs(glyph.opacity-previous.opacity)<.0005,"glyphs must fade smoothly through every appearance and empty interval")
			if glyph.opacity>0 {
				testing.expect(t,glyph.width>=130&&glyph.width<=180&&abs(glyph.rotation)<=15,"the incomplete glyph remains large and nearly still")
				testing.expect(t,abs(glyph.offset.x)>=300&&abs(glyph.offset.x)<=385&&abs(glyph.offset.y)>=75&&abs(glyph.offset.y)<=150,"glyph centers stay in the side void outside the slab")
				if previous.opacity>0 {
					delta:=glyph.offset-previous.offset
					testing.expect(t,math.hypot(delta.x,delta.y)<1.0/30.0,"a visible glyph must never jump or drift faster than one world pixel per second")
					testing.expect(t,glyph.variant==previous.variant&&glyph.width==previous.width,"motifs can only switch while fully invisible")
				}
			}
			previous=glyph
		}
		for second in 3..=720 {
			for index in 0..<2 {
				wisp:=ar.visual_turn_page_ink_wisp(u64(seed),f32(second),index)
				next:=ar.visual_turn_page_ink_wisp(u64(seed),f32(second)+ar.SIM_DT,index)
				delta:=next.offset-wisp.offset
				testing.expect(t,wisp.variant==0&&wisp.width>=65&&wisp.width<=110)
				testing.expect(t,wisp.opacity>=.025&&wisp.opacity<=.0451&&next.opacity==wisp.opacity,"ink must stay faint and never pulse after entering")
				testing.expect(t,abs(wisp.offset.x)<=450&&wisp.offset.y>=-235&&wisp.offset.y<=285)
				testing.expect(t,math.hypot(delta.x,delta.y)<.27&&abs(next.rotation-wisp.rotation)<.038,"wisps drift and turn gently along the outskirts")
				other:=ar.visual_turn_page_ink_wisp(u64(seed),f32(second),1-index)
				separation:=wisp.offset-other.offset
				testing.expect(t,math.hypot(separation.x,separation.y)>390,"opposing wisps must not bunch into a cloud")
			}
		}
	}
	for index in ([4]int{-1,2,3,99}) do testing.expect(t,ar.visual_turn_page_ink_wisp(97,9,index).opacity==0)
}

@(test)
visual_turn_page_void_traces_reconstruct_across_page_retry_and_pause :: proc(t:^testing.T) {
	app:=turn_page_test_start(9)
	defer ar.run_destroy(&app.run)
	for _ in 0..<180 do _=ar.turn_page_tick(&app,{},ar.SIM_DT)
	age:=ar.visual_turn_page_motion_age(&app,1)
	seed:=app.story_minigame.seed
	glyph:=ar.visual_turn_page_void_glyph(seed,age)
	wisps:[ar.VISUAL_TURN_PAGE_INK_WISP_COUNT]ar.Visual_Turn_Page_Trace
	for index in 0..<len(wisps) {
		wisps[index]=ar.visual_turn_page_ink_wisp(seed,age,index)
		initial:=ar.visual_turn_page_ink_wisp(seed,0,index)
		half:=ar.visual_turn_page_ink_wisp(seed,1.5,index)
		full:=ar.visual_turn_page_ink_wisp(seed,3,index)
		testing.expect(t,initial.opacity==0&&half.opacity>0&&half.opacity<full.opacity,"ink must enter over three seconds without appearing abruptly")
		testing.expect(t,ar.visual_turn_page_ink_wisp(seed,-1,index)==initial)
	}
	testing.expect(t,ar.visual_turn_page_void_glyph(seed,-1)==ar.visual_turn_page_void_glyph(seed,0))
	app.story_minigame.score+=1
	ar.turn_page_begin_page(&app)
	ar.turn_page_wrong(&app,{4,4})
	app.mode=.Paused
	for alpha in ([3]f32{0,.5,1}) {
		restored_age:=ar.visual_turn_page_motion_age(&app,alpha)
		testing.expect(t,ar.visual_turn_page_void_glyph(seed,restored_age)==glyph,"pause and page changes must not reset or replace the distant glyph")
		for index in 0..<len(wisps) {
			_=ar.visual_turn_page_ink_wisp(seed+1,900,index)
			testing.expect(t,ar.visual_turn_page_ink_wisp(seed,restored_age,index)==wisps[index],"ink reconstruction must not depend on sampling history or route state")
		}
	}
	_=ar.visual_turn_page_void_glyph(seed+1,900)
	testing.expect(t,ar.visual_turn_page_void_glyph(seed,age)==glyph)
}

@(test)
visual_turn_page_special_variants_have_a_hard_board_cap :: proc(t:^testing.T) {
	for seed in 0..<256 do for page in 0..<3 {
		state:=ar.Story_Minigame_State{seed=u64(seed),depth=5+seed%5,score=page,goal=3}
		variants:=ar.visual_turn_page_floor_variants(&state)
		counts:[6]int
		for column in variants do for variant in column {
			if variant<0||variant>=len(counts) {
				testing.expect(t,false,"invalid floor variant")
				return
			}
			counts[variant]+=1
		}
		testing.expect(t,counts[0]==85,"most slabs must remain plain")
		for variant in 1..<len(counts) {
			testing.expect(t,counts[variant]==3,"each special variant must occupy only three distinct cells")
		}
	}
}

@(test)
visual_turn_page_variants_remain_stable_through_play_and_result :: proc(t:^testing.T) {
	state:=ar.Story_Minigame_State{seed=9707,depth=9,score=2,goal=3,phase=.Preview}
	before:=ar.visual_turn_page_floor_variants(&state)
	for phase in ([2]ar.Story_Minigame_Phase{.Play,.Result}) {
		state.phase=phase;state.elapsed=10;state.step=6;state.mistakes=4
		if phase==.Result {state.score=state.goal;state.outcome=.Won}
		after:=ar.visual_turn_page_floor_variants(&state)
		for x in 0..<ar.TURN_PAGE_SIZE do for y in 0..<ar.TURN_PAGE_SIZE {
			testing.expect(t,after[x][y]==before[x][y],"progress, falls and a final win must retain each slab's decoration")
		}
	}
	state.score=1;changed:=0
	after:=ar.visual_turn_page_floor_variants(&state)
	for x in 0..<ar.TURN_PAGE_SIZE do for y in 0..<ar.TURN_PAGE_SIZE {
		if after[x][y]!=before[x][y] do changed+=1
	}
	testing.expect(t,changed>0,"new pages should vary the decorative layout")
}

@(test)
visual_ambient_darkens_with_depth_without_changing_dark_floor_level :: proc(t: ^testing.T) {
	depth_1 := ar.visual_ambient_level(1, false)
	depth_5 := ar.visual_ambient_level(5, false)
	depth_10 := ar.visual_ambient_level(ar.DUNGEON_DEPTH, false)
	testing.expectf(t, visual_near(depth_1, .576), "depth-1 ambient %.4f, want .576", depth_1)
	testing.expectf(t, visual_near(depth_10, .18), "depth-10 ambient %.4f, want .18", depth_10)
	testing.expect(t, depth_1 > depth_5 && depth_5 > depth_10, "normal floors must darken monotonically")
	for depth in 1 ..= ar.DUNGEON_DEPTH {
		testing.expect(t, visual_near(ar.visual_ambient_level(depth, true), .10), "dark-floor ambient must remain lantern-driven")
	}
	ambient := ar.visual_theme_ambient(&ar.THEMES[2], ar.DUNGEON_DEPTH, false)
	testing.expect(t, ambient[0] < ambient[2], "violet theme ambient must retain its authored color cast")
}

@(test)
visual_revelation_field_matches_pygame_falloff_and_los_holes :: proc(t: ^testing.T) {
	mask: [ar.MAP_W][ar.MAP_H]bool
	for x in 10 ..= 20 {
		for y in 10 ..= 20 do mask[x][y] = true
	}
	edge := ar.visual_fog_target(&mask, 10, 15)
	one_in := ar.visual_fog_target(&mask, 11, 15)
	deep := ar.visual_fog_target(&mask, 15, 15)
	testing.expectf(t, visual_near(edge, (1-.55)/1.7), "frontier value %.4f differs from authored falloff", edge)
	testing.expect(t, edge < one_in && one_in < deep && visual_near(deep, 1), "field must rise continuously into explored space")
	mask[15][15] = false
	testing.expect(t, ar.visual_fog_target(&mask, 15, 15) == 0, "unexplored/LOS-blocked tile must remain black")
	testing.expect(t, ar.visual_fog_target(nil, 15, 15) == 0, "nil mask must be safe")
}

@(test)
visual_fog_easing_is_frame_rate_independent :: proc(t: ^testing.T) {
	one_step := ar.visual_fog_ease(0, 1, .25)
	many_steps: f32
	for _ in 0 ..< 15 do many_steps = ar.visual_fog_ease(many_steps, 1, 1.0/60.0)
	testing.expectf(t, visual_near(one_step, many_steps, .021), "equivalent wall time diverged: %.4f vs %.4f", one_step, many_steps)
	testing.expect(t, ar.visual_fog_ease(.3, 1, 0) == .3, "zero dt must not move presentation state")
	testing.expect(t, ar.visual_live_visibility_ease(1,false,ar.SIM_DT)==0, "lost LOS must conceal light immediately")
	testing.expect(t, ar.visual_live_visibility_ease(0,true,ar.SIM_DT)>0, "new LOS should ease open")
}

@(test)
visual_wall_ghost_rejects_grazes_and_ramps_real_occlusion :: proc(t: ^testing.T) {
	testing.expect(t, ar.visual_ghost_coverage_contribution(.25, .9) == 0, "same-depth wall must not ghost")
	testing.expect(t, ar.visual_ghost_coverage_contribution(1, .02) == 0, "2%% corner graze must not ghost")
	covered := ar.visual_ghost_coverage_contribution(1, .70)
	target := ar.visual_ghost_target(covered)
	testing.expectf(t, visual_near(covered, .70), "full-depth coverage %.3f, want .70", covered)
	testing.expect(t, target > 0 && target < 1, "meaningful partial cover must yield a partial ghost")
	testing.expect(t, ar.visual_ghost_target(.90) == 1, "fully swallowed actor must reach full ghost")
	eased := ar.visual_ghost_ease(0, 1, 1.0/60.0)
	testing.expect(t, eased > .25 && eased < .30, "60 Hz ghost fade should match pygame's ~28%% pull")
	testing.expect(t,ar.VISUAL_RELIC_GHOST_SPRITE_ALPHA>ar.VISUAL_GHOST_SPRITE_ALPHA&&ar.VISUAL_RELIC_GHOST_SPRITE_ALPHA<=1,
		"small relic ghosts must remain more legible than actors without exceeding valid alpha")
	testing.expect(t,ar.VISUAL_RELIC_GHOST_AURA_ALPHA>ar.VISUAL_GHOST_AURA_ALPHA&&ar.VISUAL_RELIC_GHOST_AURA_ALPHA<=1,
		"relic wall aura must be stronger than the actor aura without exceeding valid alpha")
}

@(test)
visual_idle_clock_animates_without_touching_locomotion_phase :: proc(t: ^testing.T) {
	testing.expect(t,ar.visual_idle_clip_time(1,4)>ar.visual_idle_clip_time(.5,4),"idle render clock must advance with world time")
	testing.expect(t,ar.visual_idle_clip_time(1,4)!=ar.visual_idle_clip_time(1,5),"stable actor IDs should de-sync idle phases")
	clip,clip_time:=ar.visual_lossless_soul_clip(false,false,false,3,4)
	testing.expect(t,clip==.Dance&&clip_time==0,"unresolved waiting Soul must retain its deliberate still pose")
	clip,clip_time=ar.visual_lossless_soul_clip(true,false,false,3,4)
	testing.expect(t,clip==.Dance&&clip_time==4,"armed Soul must loop its only idle-capable clip after Mistbound")
	_,next_time:=ar.visual_lossless_soul_clip(true,false,false,3,5)
	testing.expect(t,next_time>clip_time,"armed Soul idle animation must advance with the world presentation clock")
	clip,clip_time=ar.visual_lossless_soul_clip(true,true,false,3,4)
	testing.expect(t,clip==.Walk&&clip_time==3,"armed Soul locomotion must retain its simulation animation clock")
	clip,clip_time=ar.visual_lossless_soul_clip(false,false,true,3,4)
	testing.expect(t,clip==.Dance&&clip_time==3,"explicit pre-verdict gestures must retain their simulation animation clock")
	testing.expect(t,ar.VISUAL_WALL_PAINTER_DEPTH_OFFSET>1,"walls/doors must deterministically paint after same-tile actors")
}

@(test)
visual_mist_parting_scales_with_speed_and_stays_bounded :: proc(t: ^testing.T) {
	testing.expect(t, ar.visual_mist_falloff(0) == 1, "parting must be full strength at the actor's feet")
	edge_sq := ar.VISUAL_MIST_CLEAR_RADIUS * ar.VISUAL_MIST_CLEAR_RADIUS
	testing.expect(t, ar.visual_mist_falloff(edge_sq) == 0, "parting must vanish at the authored radius")
	testing.expect(t, ar.visual_mist_falloff(edge_sq * 4) == 0, "far cells must stay untouched")
	mid := ar.visual_mist_falloff(edge_sq * .25)
	testing.expect(t, mid > 0 && mid < 1, "falloff must ramp continuously inside the radius")
	stand := ar.visual_mist_clear_target(1, 0)
	walk := ar.visual_mist_clear_target(1, 1)
	testing.expectf(t, visual_near(stand, ar.VISUAL_MIST_STAND_CLEAR), "standing parting %.3f", stand)
	testing.expectf(t, visual_near(walk, ar.VISUAL_MIST_WALK_CLEAR), "walking parting %.3f", walk)
	testing.expect(t, walk > stand, "movement must part more mist than presence alone")
	testing.expect(t, ar.visual_mist_speed_norm(ar.PLAYER_MOVE_SPEED) == 1, "reference walk speed must map to a full wake")
	testing.expect(t, ar.visual_mist_speed_norm(99) == 1, "dash bursts must not overdrive the wake")
}

@(test)
visual_mist_recovery_is_frame_rate_independent_and_lingers :: proc(t: ^testing.T) {
	one_step := ar.visual_mist_recover(1, .5)
	many: f32 = 1
	for _ in 0 ..< 30 do many = ar.visual_mist_recover(many, .5 / 30)
	testing.expectf(t, visual_near(one_step, many, .002), "recovery diverged across frame rates: %.4f vs %.4f", one_step, many)
	testing.expect(t, ar.visual_mist_recover(.8, 0) == .8, "zero dt must not refill mist")
	testing.expect(t, ar.visual_mist_recover(1, 1) > .5, "a wake must still read one second later")
	testing.expect(t, ar.visual_mist_recover(1, 10) < .05, "mist must eventually seep back everywhere")
}

@(test)
visual_mist_stamps_only_deepen_and_pushes_stay_clamped :: proc(t: ^testing.T) {
	risen := ar.visual_mist_approach(.2, .8, ar.SIM_DT)
	testing.expect(t, risen > .2 && risen < .8, "stamps must ease toward their target without overshoot")
	testing.expect(t, ar.visual_mist_approach(.6, .3, ar.SIM_DT) == .6, "a weaker stamp must not close an existing wake")
	ahead := ar.visual_mist_push_target({1, 0}, {ar.PLAYER_MOVE_SPEED, 0}, 1)
	testing.expect(t, ahead.x > ar.VISUAL_MIST_PUSH_RADIAL, "mist ahead of motion must be shoved outward harder than by presence")
	still := ar.visual_mist_push_target({0, 1}, {0, 0}, 1)
	testing.expect(t, still.y > 0 && abs(still.x) < 1e-5, "presence alone must still displace radially")
	clamped := ar.visual_mist_push_clamp({9, 0})
	testing.expectf(t, visual_near(clamped.x, ar.VISUAL_MIST_PUSH_MAX), "push must clamp to the encode range, got %.3f", clamped.x)
	decayed := ar.visual_mist_push_decay({.4, -.4}, 10)
	testing.expect(t, abs(decayed.x) < .01 && abs(decayed.y) < .01, "displaced mist must settle back")
	round_trip := (f32(ar.visual_mist_push_encode(.25)) / 255 * 2 - 1) * ar.VISUAL_MIST_PUSH_MAX
	testing.expectf(t, visual_near(round_trip, .25, .01), "push encode round trip drifted: %.4f", round_trip)
}

@(test)
visual_mist_zones_cover_a_seeded_subset_of_rooms :: proc(t: ^testing.T) {
	rng := ar.rng_make(77)
	d, ok := ar.dungeon_generate(&rng)
	testing.expect(t, ok, "dungeon must generate")
	zone_a: [ar.MAP_W][ar.MAP_H]f32
	zone_b: [ar.MAP_W][ar.MAP_H]f32
	seed := ar.visual_mist_zone_seed(1234, 3, 0)
	ar.visual_mist_zones(&d, seed, &zone_a)
	ar.visual_mist_zones(&d, seed, &zone_b)
	testing.expect(t, zone_a == zone_b, "zones must be deterministic for a floor seed")
	misty, clear, open_tiles := 0, 0, 0
	for x in 0 ..< ar.MAP_W {
		for y in 0 ..< ar.MAP_H {
			value := zone_a[x][y]
			testing.expect(t, value >= 0 && value <= 1, "zone values must stay normalized")
			if d.tiles[x][y] == .Wall do continue
			open_tiles += 1
			if value > .9 do misty += 1
			if value < .05 do clear += 1
		}
	}
	testing.expect(t, open_tiles > 0 && misty > 0, "at least one chamber must hold mist")
	testing.expect(t, clear > 0, "mist must never blanket a whole floor")
	zone_next: [ar.MAP_W][ar.MAP_H]f32
	ar.visual_mist_zones(&d, ar.visual_mist_zone_seed(1234, 4, 0), &zone_next)
	testing.expect(t, zone_next != zone_a, "each floor must deal its own mist banks")
}

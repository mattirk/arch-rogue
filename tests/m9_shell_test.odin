package archrogue_tests

// End-to-end, window-free M9 reducer and runtime seams. Pure table/math tests
// live beside their owning systems; these guard the way the shell composes
// pause/options, progression, shops, difficulty, and controller behavior.

import "core:math"
import "core:testing"
import ar "../src"

@(private = "file")
m9_commit_depth_one_omen :: proc(t: ^testing.T, app: ^ar.App) {
	_ = ar.app_story_process_requests(app, include_omen = true)
	testing.expect(t, app.story_panel.active && app.story_panel.mandatory, "fixture must reveal the mandatory depth-one omen")
	ar.app_story_panel_reveal(app)
	choices := ar.app_story_panel_choices(app)
	aid_row := -1
	for i in 0 ..< choices.count do if choices.items[i].verb == .Aid do aid_row = i
	testing.expect(t, aid_row >= 0, "mandatory omen must retain Aid")
	if aid_row >= 0 do ar.app_apply(app, ar.Intent{menu_index = aid_row, menu_index_valid = true, confirm = true})
	testing.expect(t, !app.story_panel.active && app.run.story_runtime.relic_records[0].committed, "fixture must commit the mandatory omen")
}

@(test)
m9_title_pause_and_nested_options_preserve_the_run :: proc(t:^testing.T) {
	app: ar.App
	ar.app_init(&app,ar.derive_seed(9201,0))
	defer ar.run_destroy(&app.run)

	ar.app_apply(&app,ar.Intent{menu_index=int(ar.Title_Action.Options),menu_index_valid=true,confirm=true})
	testing.expect(t,app.mode==.Options&&app.options_return==.Title,"title Options must remember its return screen")
	old_cap:=app.options.frame_rate_cap
	ar.app_apply(&app,ar.Intent{menu_index=1,menu_index_valid=true,menu_horizontal=1})
	testing.expect(t,app.options.frame_rate_cap!=old_cap,"options row must change the frame cap")
	testing.expect(t,ar.Platform_Effect.Apply_FPS in app.platform_effects&&ar.Platform_Effect.Save_Options in app.platform_effects,"option changes must request platform apply + persistence")
	ar.app_apply(&app,ar.Intent{back=true})
	testing.expect(t,app.mode==.Title,"title options must return to title")

	app.options.difficulty=.Hard
	ar.app_apply(&app,ar.Intent{menu_index=int(ar.Title_Action.New_Run),menu_index_valid=true,confirm=true})
	testing.expect(t,app.mode==.Select)
	ar.app_apply(&app,ar.Intent{menu_index=1,menu_index_valid=true,confirm=true})
	testing.expect(t,app.mode==.Playing&&app.run.player.archetype==.Rogue&&app.run.difficulty==.Hard,"new run must snapshot archetype and difficulty")
	m9_commit_depth_one_omen(t,&app)
	seed,depth:=app.run.seed,app.run.depth
	app.run.player.bolt_timer=1
	ar.app_apply(&app,ar.Intent{back=true})
	testing.expect(t,app.mode==.Paused,"Esc/back in play must pause")
	ar.app_tick(&app)
	testing.expect(t,app.run.player.bolt_timer==1,"pause must freeze simulation clocks")
	ar.app_apply(&app,ar.Intent{menu_index=1,menu_index_valid=true,confirm=true})
	testing.expect(t,app.mode==.Options&&app.options_return==.Paused,"pause Options must retain the active run origin")
	ar.app_apply(&app,ar.Intent{back=true})
	testing.expect(t,app.mode==.Paused)
	ar.app_apply(&app,ar.Intent{back=true})
	testing.expect(t,app.mode==.Playing&&app.run.seed==seed&&app.run.depth==depth,"resume must preserve the current run")

	ar.app_apply(&app,ar.Intent{back=true})
	ar.app_apply(&app,ar.Intent{menu_index=0,menu_index_valid=true,confirm=true,pointer_confirm=true})
	testing.expect(t,app.mode==.Playing&&app.mouse_input_blocked,"mouse Resume must consume its held click")
	ar.app_apply(&app,ar.Intent{mouse_walk=true,mouse_target=app.run.player.pos+ar.Vec2{3,0}})
	testing.expect(t,!app.mouse_walk,"held Resume click must not leak into movement")
	ar.app_apply(&app,ar.Intent{mouse_released=true})
	testing.expect(t,!app.mouse_input_blocked,"mouse release must restore gameplay input")
}

@(test)
m9_title_quit_is_app_owned :: proc(t:^testing.T) {
	app:ar.App
	ar.app_init(&app,9202)
	ar.app_apply(&app,ar.Intent{menu_index=int(ar.Title_Action.Quit),menu_index_valid=true,confirm=true})
	testing.expect(t,app.quit_requested,"Quit row must terminate through App state")
}

@(test)
m9_character_modal_pauses_navigates_and_spends_once :: proc(t:^testing.T) {
	app:ar.App
	ar.app_init(&app,9203)
	defer ar.run_destroy(&app.run)
	ar.run_start(&app.run,app.seed,.Warden)
	app.mode=.Playing
	app.run.player.memory_tokens=1
	app.inventory_open=true
	ar.app_apply(&app,ar.Intent{open_character=true})
	testing.expect(t,app.character_open&&!app.inventory_open&&!app.shop_open,"character sheet must own the modal slot")
	app.run.player.class_skill_timer=1
	ar.app_tick(&app)
	testing.expect(t,app.run.player.class_skill_timer==1,"character sheet must pause fixed-step clocks")

	ar.app_apply(&app,ar.Intent{tab=true})
	testing.expect(t,app.character_tab==.Disciplines)
	ar.app_apply(&app,ar.Intent{character_tab=.Overview,character_tab_valid=true})
	testing.expect(t,app.character_tab==.Overview,"keyboard/mouse tab selection must be absolute")
	ar.app_apply(&app,ar.Intent{character_tab=.Disciplines,character_tab_valid=true})
	ar.app_apply(&app,ar.Intent{menu_horizontal=99,menu_delta=99})
	testing.expect(t,app.discipline_column==ar.DISCIPLINE_PATHS_PER_ARCHETYPE-1&&app.discipline_degree==ar.DISCIPLINE_DEGREES-1,"discipline navigation must clamp at grid edges")
	ar.app_apply(&app,ar.Intent{menu_index=0,menu_index_valid=true,confirm=true})
	testing.expect(t,app.run.player.acquired_disciplines[.Warden_Bulwark]&&app.run.player.memory_tokens==0,"confirm must spend one token on the selected root")
	before:=app.run.player
	ar.app_apply(&app,ar.Intent{confirm=true})
	testing.expect(t,app.run.player==before,"reconfirming a chosen node must be mutation-free")
	app.character_open=false
	app.run.player.memory_tokens=1
	ar.app_apply(&app,ar.Intent{open_disciplines=true})
	testing.expect(t,app.character_open&&app.character_tab==.Disciplines,
		"the clickable Memory prompt must open the discipline tab directly")

	app.character_tab=.Disciplines
	app.discipline_column=3
	app.discipline_degree=4
	app.character_open=false
	app.mode=.Select
	app.select_index=int(ar.Archetype_Id.Rogue)
	ar.app_apply(&app,ar.Intent{confirm=true})
	testing.expect(t,app.character_tab==.Overview&&app.discipline_column==0&&app.discipline_degree==0,"new runs must reset character-sheet focus")
}

@(test)
m9_controls_capture_remaps_and_persists :: proc(t:^testing.T) {
	app:ar.App
	ar.app_init(&app,9204)
	app.mode=.Controls
	app.controls_index=1 // Ability 2
	ar.app_apply(&app,ar.Intent{confirm=true})
	testing.expect(t,app.controls_capture,"confirm must enter physical-input capture")
	ar.app_apply(&app,ar.Intent{remap_button=.A,remap_button_valid=true})
	testing.expect(t,!app.controls_capture,"successful mapping must leave capture")
	testing.expect(t,app.options.gamepad_mapping.gameplay_buttons[.A]==.Ability_2&&app.options.gamepad_mapping.gameplay_buttons[.X]==.None,"remap must move the command and clear its old binding")
	testing.expect(t,ar.Platform_Effect.Save_Options in app.platform_effects,"remaps must persist")

	ar.app_apply(&app,ar.Intent{confirm=true})
	ar.app_apply(&app,ar.Intent{remap_button=.Dpad_Up,remap_button_valid=true})
	testing.expect(t,app.controls_capture&&app.controls_status=="D-pad navigation is fixed","fixed D-pad input must be rejected without ending capture")
	ar.app_apply(&app,ar.Intent{back=true})
	testing.expect(t,!app.controls_capture&&app.mode==.Controls,"first Back must cancel capture")
	ar.app_apply(&app,ar.Intent{back=true})
	testing.expect(t,app.mode==.Options,"second Back must return to options")
}

@(test)
m9_controller_aim_snap_prefers_visible_target_near_stick_line :: proc(t:^testing.T) {
	run:ar.Run
	ar.run_start(&run,9205,.Warden)
	defer ar.run_destroy(&run)
	clear(&run.enemies)
	run.player.pos=ar.run_spawn_point(&run)
	run.player.prev_pos=run.player.pos
	target:=ar.enemy_make(.Ghoul,run.player.pos+ar.Vec2{1,.25},1)
	append(&run.enemies,target)
	tx,ty:=int(target.pos.x),int(target.pos.y)
	run.visible[tx][ty]=true
	snapped:=ar.controller_snap_aim(&run,{1,0})
	testing.expect(t,snapped.y>0&&abs(math.hypot(snapped.x,snapped.y)-1)<1e-4,"right-stick aim must snap to a visible target inside the aim cone")
	run.visible[tx][ty]=false
	testing.expect(t,ar.controller_snap_aim(&run,{1,0})==ar.Vec2{1,0},"hidden targets must never attract controller aim")
}

@(test)
m9_inventory_consumes_gamepad_tab_and_drop_semantics :: proc(t:^testing.T) {
	app:ar.App
	ar.app_init(&app,9206)
	defer ar.run_destroy(&app.run)
	ar.run_start(&app.run,app.seed,.Warden)
	app.mode=.Playing
	app.inventory_open=true
	app.inv_sort_mode=.Type
	app.run.player.bag[0]=ar.Item{kind=.Weapon,name="Spare Blade",power=2}
	app.run.player.bag_count=1
	ar.app_apply(&app,ar.Intent{tab=true})
	testing.expect(t,app.inv_sort_mode==.Rarity,"controller RB/Tab must cycle inventory sorting")
	ground_before:=len(app.run.ground_items)
	ar.app_apply(&app,ar.Intent{inv_drop=true})
	testing.expect(t,app.run.player.bag_count==0&&len(app.run.ground_items)==ground_before+1,"controller Y/Help must drop the selected bag row")
}

@(test)
m9_shop_modal_trades_scrolls_and_pauses :: proc(t:^testing.T) {
	app:ar.App
	ar.app_init(&app,9207)
	defer ar.run_destroy(&app.run)
	ar.run_start(&app.run,app.seed,.Warden)
	app.mode=.Playing
	room:=app.run.dungeon.rooms_buf[1]
	app.run.shopkeeper=ar.shopkeeper_make(app.run.seed,app.run.depth,room)
	app.run.shopkeeper.pos=app.run.player.pos
	app.run.has_shopkeeper=true
	app.run.player.gold=1000
	heal_before:=app.run.player.heal_potions
	price:=ar.shop_price(&app.run.shopkeeper,app.run.shopkeeper.stock[0])
	ar.app_apply(&app,ar.Intent{interact=true})
	testing.expect(t,app.shop_open&&app.shop_mode==.Buy,"interact near keeper must open Buy mode")
	app.run.player.melee_timer=1
	ar.app_tick(&app)
	testing.expect(t,app.run.player.melee_timer==1,"shop must pause the simulation")
	stock_before:=app.run.shopkeeper.stock_count
	ar.app_apply(&app,ar.Intent{confirm=true})
	testing.expect(t,app.run.player.heal_potions==heal_before+1&&app.run.player.gold==1000-price&&app.run.shopkeeper.stock_count==stock_before-1,"buy row must transact atomically through App")

	for i in 0..<ar.BAG_CAPACITY do app.run.player.bag[i]=ar.Item{kind=.Weapon,name="Trade Blade",power=i+1}
	app.run.player.bag_count=ar.BAG_CAPACITY
	ar.app_apply(&app,ar.Intent{tab=true})
	testing.expect(t,app.shop_mode==.Sell&&app.shop_index==0&&app.shop_scroll==0)
	ar.app_apply(&app,ar.Intent{menu_delta=ar.BAG_CAPACITY-1})
	testing.expect(t,app.shop_index==ar.BAG_CAPACITY-1&&app.shop_scroll==ar.BAG_CAPACITY-ar.SHOP_VISIBLE_ROWS,"shop selection must scroll late bag rows into view")
	gold_before:=app.run.player.gold
	ar.app_apply(&app,ar.Intent{confirm=true})
	testing.expect(t,app.run.player.bag_count==ar.BAG_CAPACITY-1&&app.run.player.gold>gold_before,"off-screen sell rows must remain usable after scrolling")
	ar.app_apply(&app,ar.Intent{back=true})
	testing.expect(t,!app.shop_open,"Back must close the shop before pausing the run")

	fixed_sign:=ar.shop_sign_position(&app.run.shopkeeper)
	app.run.shopkeeper.pos=fixed_sign+ar.Vec2{3,0}
	app.run.player.pos=fixed_sign
	ar.app_apply(&app,ar.Intent{interact=true})
	testing.expect(t,app.shop_open,"fixed Shop sign must remain a trade interaction when the live keeper wanders away")
	testing.expect(t,app.run.shopkeeper.motion.holding&&!app.run.shopkeeper.motion.moving&&!app.run.shopkeeper.motion.dancing,"sign trade must hold and face the live keeper")
}

@(test)
m9_dry_barrel_falls_through_to_loot_and_furnishings_are_solid :: proc(t:^testing.T) {
	bar_count:=0
	dry_interaction_checked:=false
	for seed in 1..=80 {
		run:ar.Run
		ar.run_start(&run,u64(seed),.Warden)
		special,has_bar:=ar.special_room_for_kind(&run.dungeon,.Bar)
		if !has_bar {
			ar.run_destroy(&run)
			continue
		}
		bar_count+=1
		layout:=ar.bar_furnishing_layout(&run.dungeon)
		room:=run.dungeon.rooms_buf[special.room_index]
		desired:=2+min(2,max(0,(room.w-2)*(room.h-2))/28)
		testing.expectf(t,layout.barrel_count>=1&&layout.barrel_count<=desired&&layout.table_count>=1&&layout.table_count<=desired,
			"bar room %v requested up to %v barrels/tables, got %v/%v",special.room_index,desired,layout.barrel_count,layout.table_count)
		testing.expect(t,layout.count==layout.barrel_count+layout.table_count&&layout.kinds[0]==.Barrel,
			"cached layout must be typed and keep its tapped barrel first")
		for i in 0..<layout.count {
			tile:=layout.tiles[i]
			center:=ar.Vec2{f32(tile.x)+.5,f32(tile.y)+.5}
			testing.expect(t,ar.blocked_for_radius(&run.dungeon,center.x,center.y),"bar furnishing must block actors")
			for &enemy in run.enemies do testing.expect(t,int(enemy.pos.x)!=tile.x||int(enemy.pos.y)!=tile.y,"enemy spawned under bar furniture")
			for &ground in run.ground_items do testing.expect(t,int(ground.pos.x)!=tile.x||int(ground.pos.y)!=tile.y,"loot spawned under bar furniture")
			for j in i+1..<layout.count {
				other:=layout.tiles[j]
				testing.expect(t,max(abs(tile.x-other.x),abs(tile.y-other.y))>=2,"bar furnishings must preserve a walkable aisle")
			}
		}

		if !dry_interaction_checked {
			barrel:=layout.tiles[0]
			neighbors:=[4]ar.Vec2{{f32(barrel.x)-.5,f32(barrel.y)+.5},{f32(barrel.x)+1.5,f32(barrel.y)+.5},{f32(barrel.x)+.5,f32(barrel.y)-.5},{f32(barrel.x)+.5,f32(barrel.y)+1.5}}
			placed:=false
			for candidate in neighbors {
				if !ar.blocked_for_radius(&run.dungeon,candidate.x,candidate.y,block_stairs=true) {
					run.player.pos=candidate
					run.player.prev_pos=candidate
					placed=true
					break
				}
			}
			testing.expect(t,placed,"barrel needs an adjacent drinking tile")
			if placed {
				for x in 0..<ar.MAP_W do for y in 0..<ar.MAP_H do if run.dungeon.tiles[x][y]==.Closed_Door do run.dungeon.tiles[x][y]=.Open_Door
				clear(&run.ground_items)
				clear(&run.sfx)
				run.refuge.bar_toasted=false
				run.player.hp=max(1,run.player.max_hp-5)
				run.player.stamina=0
				_ = ar.player_interact(&run)
				has_drink_cue:=false
				for cue in run.sfx do if cue==.Drink do has_drink_cue=true
				testing.expect(t,run.refuge.bar_toasted&&has_drink_cue,"first tapped-barrel interaction must toast and emit Drink")
				heal_before:=run.player.heal_potions
				append(&run.ground_items,ar.Ground_Item{item=ar.Item{kind=.Heal_Potion,name="Test Flask"},pos=run.player.pos})
				_ = ar.player_interact(&run)
				testing.expect(t,run.player.heal_potions==heal_before+1&&len(run.ground_items)==0,"spent barrel must fall through so nearby loot remains interactable")
				dry_interaction_checked=true
			}
		}
		ar.run_destroy(&run)
	}
	testing.expect(t,bar_count>0&&dry_interaction_checked,"sample must cover Bar layout and dry-barrel interaction")
}

@(test)
m9_special_actor_anchors_are_placement_only_and_population_reserved :: proc(t:^testing.T) {
	seen: [ar.Special_Room_Kind]bool
	for seed in 1..=80 {
		run:ar.Run
		ar.run_start(&run,u64(1000+seed),.Warden)
		for special in ar.special_rooms(&run.dungeon) {
			actors:=ar.special_room_actor_layout(&run.dungeon,special.kind)
			expected:=special.kind==.Garden?2:1
			testing.expectf(t,actors.count==expected,"%v room has %v actor anchors, want %v",special.kind,actors.count,expected)
			seen[special.kind]=true
			for i in 0..<actors.count {
				tile:=actors.tiles[i]
				pos:=ar.Vec2{f32(tile.x)+.5,f32(tile.y)+.5}
				testing.expect(t,ar.special_room_actor_occupies_tile(&run.dungeon,tile.x,tile.y),"actor layout lookup lost its anchor")
				testing.expect(t,ar.special_room_placement_reserved_occupies_tile(&run.dungeon,tile.x,tile.y),"actor anchor must reserve initial placement")
				testing.expect(t,!ar.special_room_reserved_occupies_tile(&run.dungeon,tile.x,tile.y),"actor anchor leaked into physical/nav reservations")
				testing.expect(t,!ar.blocked_for_radius(&run.dungeon,pos.x,pos.y),"departed actor anchor must not remain as ghost collision")
				for &enemy in run.enemies do testing.expect(t,int(enemy.pos.x)!=tile.x||int(enemy.pos.y)!=tile.y,"enemy spawned under a special-room actor")
				for &ground in run.ground_items do testing.expect(t,int(ground.pos.x)!=tile.x||int(ground.pos.y)!=tile.y,"loot spawned under a special-room actor")
			}
		}
		ar.run_destroy(&run)
	}
	testing.expect(t,seen[.Shop]&&seen[.Bar]&&seen[.Garden]&&seen[.Quest]&&seen[.Hall_Of_Unlost_Echoes],
		"sample must cover ordinary and story special actor layouts")
}

@(test)
m9_difficulty_changes_population_not_geometry_and_victory_unlocks_hell :: proc(t:^testing.T) {
	seed:=u64(9208)
	easy,hell:ar.Run
	ar.run_start(&easy,seed,.Warden,.Easy)
	defer ar.run_destroy(&easy)
	ar.run_start(&hell,seed,.Warden,.Hell)
	defer ar.run_destroy(&hell)
	// Geometry only: MX.5 furniture reservations live on the dungeon for
	// collision, and shrine odds legitimately read difficulty.
	testing.expect(t,ar.dungeon_geometry_equal(&easy.dungeon,&hell.dungeon),"difficulty must not perturb deterministic floor geometry")
	testing.expect(t,len(hell.enemies)>len(easy.enemies),"Hell must increase live population")
	easy_hp,hell_hp:=0,0
	for &enemy in easy.enemies do easy_hp+=enemy.max_hp
	for &enemy in hell.enemies do hell_hp+=enemy.max_hp
	testing.expect(t,hell_hp>easy_hp,"Hell enemy durability must be applied to spawned actors")

	app:ar.App
	ar.app_init(&app,seed)
	defer ar.run_destroy(&app.run)
	ar.run_start(&app.run,seed,.Warden)
	app.mode=.Playing
	m9_commit_depth_one_omen(t,&app)
	clear(&app.run.enemies)
	app.run.victory=true
	ar.app_tick(&app)
	testing.expect(t,app.mode==.Victory&&app.profile.hell_unlocked,"first clear must unlock Hell in profile state")
	testing.expect(t,app.persistence_request==.Finalize_Victory,"victory must request exactly-once terminal finalization")
	app.options.difficulty=.Hard
	app.mode=.Options
	app.options_return=.Title
	ar.app_apply(&app,ar.Intent{menu_index=3,menu_index_valid=true,menu_horizontal=1})
	testing.expect(t,app.options.difficulty==.Hell,"unlocked options cycle must expose Hell")
}

// Run via tools/capture_turn_page.sh --animation or
// tools/capture_turn_page_motion.sh; captures the real renderer.
package main

import "core:fmt"
import "core:mem"
import "core:os"
import ar "../src"
import rl "../vendor/raylib"

// The review fixture holds a revealed route in place so a full motion cycle
// can be judged without completing or timing out the minigame. Only this tool
// advances the staged player's clock; production rendering remains read-only.
draw_motion_review_frame :: proc(view: ^ar.View, app: ^ar.App, assets: ^ar.Assets, age: f32) {
	app.run.player.sim_elapsed=app.turn_page.return_player.sim_elapsed+age
	ar.view_update(view,1.0/30.0)
	ar.view_center_on_turn_page(view,app.run.player.pos)
	page_before:=app.turn_page;player_before:=app.run.player;minigame_before:=app.story_minigame
	ar.view_prepare_turn_page_motion(view,app,1)
	ar.draw_frame(view,app,assets,1)
	if page_before!=app.turn_page||player_before!=app.run.player||minigame_before!=app.story_minigame {
		panic("motion renderer mutated game state")
	}
}

verify_motion_review_camera :: proc(view: ^ar.View, app: ^ar.App) {
	posed:=view.camera;base:=view.turn_page_camera_base
	motion:=ar.visual_turn_page_motion(ar.visual_turn_page_motion_age(app,1))
	sample_tiles:=[5]ar.Vec2{{0,0},{10,0},{10,10},{0,10},app.run.player.pos}
	for tile in sample_tiles {
		point:=ar.world_from_tile(tile)
		expected:=rl.GetWorldToScreen2D(rl.Vector2(ar.visual_turn_page_motion_point(point,motion)),base)
		screen:=rl.GetWorldToScreen2D(rl.Vector2(point),posed)
		delta:=screen-expected
		if delta.x*delta.x+delta.y*delta.y>.00001 do panic("raylib motion disagrees with headless visual policy")
		transform:=ar.Mobile_Camera_Transform{ar.Vec2(posed.target),ar.Vec2(posed.offset),posed.zoom,posed.rotation}
		picked:=ar.mobile_screen_to_world(transform,ar.Vec2(screen))
		pick_delta:=picked-point
		if pick_delta.x*pick_delta.x+pick_delta.y*pick_delta.y>.00001 do panic("mobile picking disagrees with posed raylib camera")
	}
	ar.view_prepare_turn_page_motion(view,app,1)
	if view.camera!=posed do panic("motion camera preparation accumulated drift")
	// A fixture-only scene exit must recover the exact ordinary camera.
	app.story_minigame.active=false
	ar.view_prepare_turn_page_motion(view,app,1)
	if view.camera!=base||view.turn_page_camera_applied do panic("motion camera leaked into ordinary scene")
	app.story_minigame.active=true
	ar.view_prepare_turn_page_motion(view,app,1)
	if view.camera!=posed do panic("motion camera failed to restore staged pose")
	// Touch pinch and options update zoom while a posed camera is live. Clearing
	// that pose must retain the new zoom, and preparing it must retain the roll.
	base_zoom:=view.base_zoom
	ar.view_apply_base_zoom(view,base_zoom*1.1)
	zoom:=ar.effective_view_zoom(view.base_zoom,int(rl.GetRenderHeight()))
	if view.camera.zoom!=zoom||view.camera.rotation!=posed.rotation do panic("zoom lost current motion pose")
	ar.view_clear_turn_page_motion(view)
	if view.camera.zoom!=zoom do panic("clearing motion discarded updated zoom")
	ar.view_prepare_turn_page_motion(view,app,1)
	if view.camera.zoom!=zoom||view.camera.rotation!=posed.rotation do panic("motion preparation discarded updated zoom")
	ar.view_apply_base_zoom(view,base_zoom)
	if view.camera!=posed do panic("restoring review zoom changed motion pose")
}

capture_turn_page_motion :: proc(view: ^ar.View, app: ^ar.App, assets: ^ar.Assets, video_pipe, output_dir: string) {
	parchment:=&assets.world[.Turn_Page_Parchment]
	if parchment.variant_count!=3 do panic("motion review requires all three parchment variants")
	for i in 0..<parchment.variant_count {
		if parchment.variants[i].id==0 do panic("motion review parchment texture failed to load")
	}
	glyphs:=&assets.world[.Turn_Page_Void_Glyph]
	if glyphs.variant_count!=3 do panic("motion review requires all three distant glyph variants")
	for i in 0..<glyphs.variant_count {
		if glyphs.variants[i].id==0 do panic("motion review distant glyph texture failed to load")
	}
	wisp:=&assets.world[.Turn_Page_Ink_Wisp]
	if wisp.variant_count!=1||wisp.variants[0].id==0 do panic("motion review ink wisp texture failed to load")
	// Pause must hold one exact pose even if frame time and render alpha vary.
	// Compare actual frames too: distant details must share the paused clock.
	app.run.player.sim_elapsed=app.turn_page.return_player.sim_elapsed+9
	app.mode=.Paused
	ar.view_update(view,ar.SIM_DT)
	ar.view_center_on_turn_page(view,app.run.player.pos)
	ar.view_prepare_turn_page_motion(view,app,1)
	paused_camera:=view.camera
	paused_page:=app.turn_page;paused_player:=app.run.player;paused_minigame:=app.story_minigame
	ar.draw_frame(view,app,assets,1)
	paused_pixels:=rl.LoadImageFromScreen()
	if paused_pixels.data==nil||paused_pixels.format!=.UNCOMPRESSED_R8G8B8A8 do panic("unexpected paused review framebuffer")
	defer rl.UnloadImage(paused_pixels)
	paused_pixel_bytes:=int(paused_pixels.width*paused_pixels.height)*4
	alphas:=[3]f32{0,.25,1}
	for alpha in alphas {
		ar.view_update(view,.2)
		ar.view_center_on_turn_page(view,app.run.player.pos)
		ar.view_prepare_turn_page_motion(view,app,alpha)
		if view.camera!=paused_camera do panic("paused motion pose changed")
		ar.draw_frame(view,app,assets,alpha)
		if app.turn_page!=paused_page||app.run.player!=paused_player||app.story_minigame!=paused_minigame {
			panic("paused motion renderer mutated game state")
		}
		pixels:=rl.LoadImageFromScreen()
		if pixels.data==nil||pixels.width!=paused_pixels.width||pixels.height!=paused_pixels.height||pixels.format!=paused_pixels.format {
			panic("paused review framebuffer changed dimensions")
		}
		changed:=mem.compare((cast([^]u8)paused_pixels.data)[:paused_pixel_bytes],(cast([^]u8)pixels.data)[:paused_pixel_bytes])!=0
		rl.UnloadImage(pixels)
		if changed do panic("paused world or background continued animating")
	}
	app.mode=.Playing
	if video_pipe!="" {
		pipe,err:=os.open(video_pipe,os.O_WRONLY)
		if err!=nil do panic("cannot open motion video pipe")
		// Encode exactly 60 seconds at original speed. Frame readback streams
		// directly to ffmpeg; only the final movie and selected stills hit disk.
		for frame in 0..<1800 {
			draw_motion_review_frame(view,app,assets,f32(frame)/30)
			pixels:=rl.LoadImageFromScreen()
			if pixels.data==nil||pixels.width!=1280||pixels.height!=720||pixels.format!=.UNCOMPRESSED_R8G8B8A8 {
				panic("unexpected motion video framebuffer")
			}
			written,write_err:=os.write_ptr(pipe,pixels.data,int(pixels.width*pixels.height)*4)
			rl.UnloadImage(pixels)
			if write_err!=nil||written!=1280*720*4 do panic("motion video pipe write failed")
			if frame%300==0 do fmt.printf("Captured %d / 1800 motion frames\n",frame)
		}
		if close_err:=os.close(pipe);close_err!=nil do panic("motion video pipe close failed")
	}
	for mobile in 0..<2 {
		height:=mobile==0?720:800
		rl.SetWindowSize(1280,i32(height))
		view.mobile_mode=mobile==1
		if view.mobile_mode {
			layout,status:=ar.mobile_layout_build({surface_width=1280,surface_height=height,density=1,revision=1})
			view.mobile_layout=layout;view.mobile_layout_valid=status==.Valid
			if !view.mobile_layout_valid do panic("motion review mobile layout invalid")
		}
		// Let the window backend process the resize before taking its first still.
		draw_motion_review_frame(view,app,assets,0)
		// 9/37/65s show all three glyph peaks; 23s falls in the blank interval.
		ages:=[9]f32{0,9,15,23,30,37,45,60,65}
		for age in ages {
			draw_motion_review_frame(view,app,assets,age)
			verify_motion_review_camera(view,app)
			rl.TakeScreenshot(fmt.ctprintf("%s/turn_page_motion_%02d_1280x%d_mobile%d.png",output_dir,int(age),height,mobile))
		}
	}
	// Keep collapse fragments attached to the same rotated slab, and check the
	// actor's upright fall silhouette against the maximum roll in both layouts.
	if !ar.mx_story_stage_capture(app,.Turn_Page_Fall) do panic("motion fall staging failed")
	for mobile in 0..<2 {
		height:=mobile==0?720:800
		rl.SetWindowSize(1280,i32(height))
		view.mobile_mode=mobile==1
		draw_motion_review_frame(view,app,assets,15)
		draw_motion_review_frame(view,app,assets,15)
		rl.TakeScreenshot(fmt.ctprintf("%s/turn_page_motion_fall_1280x%d_mobile%d.png",output_dir,height,mobile))
	}
}

main :: proc() {
	rl.SetTraceLogLevel(.WARNING)
	rl.SetConfigFlags({.MSAA_4X_HINT})
	rl.InitWindow(1280,720,"Turn the Page - animation review")
	if !rl.IsWindowReady() do panic("capture needs an available desktop display")
	defer rl.CloseWindow()
	assets:=new(ar.Assets)
	ar.assets_load(assets)
	ar.assets_activate_player(assets,.Rogue)
	defer ar.assets_unload(assets)
	app:=new(ar.App)
	ar.app_init(app,9707)
	ar.run_start(&app.run,9707,.Rogue,.Medium,false)
	defer ar.run_destroy(&app.run)
	app.mode=.Playing
	if !ar.mx_story_stage_capture(app,.Turn_Page) do panic("staging failed")
	view:=new(ar.View)
	ar.view_init(view)
	ar.view_update(view,ar.SIM_DT)
	view.cursor_disabled=true
	defer ar.view_shutdown(view)
	if len(os.args)>1&&(os.args[1]=="--motion"||os.args[1]=="--motion-stills") {
		video_pipe:=""
		output_dir:="build/turn-page-captures/motion"
		argument:=2
		if os.args[1]=="--motion" {
			if len(os.args)<3 do panic("--motion requires a raw RGBA video pipe path")
			video_pipe=os.args[2]
			argument=3
		}
		for argument<len(os.args) {
			if os.args[argument]!="--output-dir"||argument+1>=len(os.args)||os.args[argument+1]=="" {
				panic("motion review accepts only --output-dir DIR after its mode and pipe")
			}
			output_dir=os.args[argument+1]
			argument+=2
		}
		capture_turn_page_motion(view,app,assets,video_pipe,output_dir)
		return
	}
	if len(os.args)>1&&os.args[1]=="--variants" {
		app.story_minigame.phase=.Play;app.story_minigame.step=-1
		app.turn_page.fall_active=false
		app.turn_page.route[app.turn_page.length-1]={20,20}
		app.run.player.pos={20.5,20.5};app.run.player.prev_pos=app.run.player.pos
		for x in 0..<ar.TURN_PAGE_SIZE do for y in 0..<ar.TURN_PAGE_SIZE {
			app.turn_page.tiles[x][y]=x==4&&y==4?.Hidden:.Gone
		}
		original:=assets.world[.Turn_Page_Hidden]
		defer assets.world[.Turn_Page_Hidden]=original
		if original.variant_count!=6 do panic("expected all six manuscript floor variants")
		labels:=[6]cstring{"Plain stone","Spilled ink","Wiped ink","Serpent scrawl","Key scrawl","Moon scrawl"}
		view.camera.zoom=4
		view.camera.target=rl.Vector2(ar.world_from_tile({4.5,4.5}))
		rl.BeginDrawing()
		rl.ClearBackground(ar.COLOR_BG)
		rl.DrawText("TURN THE PAGE - FLOOR VARIANTS",370,26,26,{200,213,224,255})
		for i in 0..<original.variant_count {
			assets.world[.Turn_Page_Hidden].variants[0]=original.variants[i]
			assets.world[.Turn_Page_Hidden].variant_count=1
			x:=220+i32(i%3)*420;y:=170+i32(i/3)*305
			view.camera.offset={f32(x),f32(y)}
			rl.BeginMode2D(view.camera)
			before:=app.turn_page;player_before:=app.run.player
			ar.draw_turn_page_world(view,app,assets,1)
			if before!=app.turn_page||player_before!=app.run.player do panic("render mutated game state")
			rl.EndMode2D()
			rl.DrawText(labels[i],x-rl.MeasureText(labels[i],22)/2,y+116,22,{170,188,199,255})
		}
		rl.EndDrawing()
		rl.TakeScreenshot("build/turn-page-captures/floor-variants.png")
		return
	}
	if len(os.args)>1&&os.args[1]=="--compare" {
		// Render isolated slabs and adjoining patches through the real floor
		// renderer, at identical zoom, placement and lighting in both panels.
		app.story_minigame.phase=.Play
		app.story_minigame.step=-1
		app.turn_page.fall_active=false
		app.turn_page.route[app.turn_page.length-1]={20,20}
		app.run.player.pos={20.5,20.5};app.run.player.prev_pos=app.run.player.pos
		for x in 0..<ar.TURN_PAGE_SIZE do for y in 0..<ar.TURN_PAGE_SIZE {
			app.turn_page.tiles[x][y]=(x==1&&y==1)||(x>=4&&x<=6&&y>=4&&y<=6)?.Hidden:.Gone
		}
		manuscript:=assets.world[.Turn_Page_Hidden]
		defer assets.world[.Turn_Page_Hidden]=manuscript
		view.camera.zoom=2.5
		view.camera.target=rl.Vector2(ar.world_from_tile({5.5,5.5}))
		rl.BeginDrawing()
		rl.ClearBackground(ar.COLOR_BG)
		for panel in 0..<2 {
			assets.world[.Turn_Page_Hidden]=panel==0?assets.world[.Lossless_Soul_Floor]:manuscript
			view.camera.offset={320+f32(panel)*640,450}
			rl.BeginMode2D(view.camera)
			before:=app.turn_page;player_before:=app.run.player
			ar.draw_turn_page_world(view,app,assets,1)
			if before!=app.turn_page||player_before!=app.run.player do panic("render mutated game state")
			rl.EndMode2D()
			label:=cstring(panel==0?"MIST CHAMBER":"TURN THE PAGE")
			rl.DrawText(label,320+i32(panel)*640-rl.MeasureText(label,26)/2,32,26,{200,213,224,255})
		}
		rl.DrawLine(640,32,640,625,{49,55,68,255})
		caption:=cstring("Same zoom, footprint, anchor and slab thickness")
		rl.DrawText(caption,640-rl.MeasureText(caption,20)/2,660,20,{170,188,199,255})
		rl.EndDrawing()
		rl.TakeScreenshot("build/turn-page-captures/tile-comparison.png")
		return
	}
	if len(os.args)>1&&os.args[1]=="--edge" {
		// Magnify both exposed platform edges without HUD or image resampling.
		view.camera.zoom=3
		view.camera.target=rl.Vector2(ar.world_from_tile({8,8}))
		view.camera.offset={640,200}
		rl.BeginDrawing()
		rl.ClearBackground(ar.COLOR_BG)
		rl.BeginMode2D(view.camera)
		ar.draw_turn_page_world(view,app,assets,1)
		rl.EndMode2D()
		rl.EndDrawing()
		rl.TakeScreenshot("build/turn-page-captures/edge-closeup.png")
		return
	}
	// Capture an actual simulation sequence at 60 Hz, including wrong-step
	// decision, floor fracture, fall, and retry. Two render frames per tick
	// exercise interpolation without altering authoritative state.
	for i in 0..<360 {
		if i%2==0 {
			if i==126 {
				forward:=ar.turn_page_center(app.turn_page.route[1])-ar.turn_page_center(app.turn_page.route[0])
				wrong:=ar.Vec2{forward.y,-forward.x}
				inward:=ar.Vec2{ar.TURN_PAGE_SIZE*.5,ar.TURN_PAGE_SIZE*.5}-app.run.player.pos
				if wrong.x*inward.x+wrong.y*inward.y<0 do wrong=-wrong
				_=ar.turn_page_dash(app,wrong)
			}
			_=ar.turn_page_tick(app,{},ar.SIM_DT)
		}
		ar.view_center_on_turn_page(view,app.run.player.pos)
		before:=app.turn_page;player_before:=app.run.player
		ar.view_prepare_turn_page_motion(view,app,f32(i%2)*.5)
		ar.draw_frame(view,app,assets,f32(i%2)*.5)
		if before!=app.turn_page||player_before!=app.run.player do panic("render mutated game state")
		rl.TakeScreenshot(fmt.ctprintf("build/turn-page-captures/animation/frames/%04d.png",i))
	}
}

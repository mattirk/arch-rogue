package archrogue

// Alternate manuscript world. The dungeon never ticks while this state owns
// input. Only the player's presentation fields below are borrowed and restored.
import "core:math"

TURN_PAGE_SIZE :: 10
TURN_PAGE_MAX_ROUTE :: 8
TURN_PAGE_FALL_SECONDS :: f32(.9)
// Falling follows foot contact. The combat radius (.42) left only .08 cells
// of lateral drift from a tile center; this footprint allows .38 cells.
TURN_PAGE_RADIUS :: f32(.12)
TURN_PAGE_SPEED :: f32(PLAYER_MOVE_SPEED)
TURN_PAGE_DASH_COOLDOWN :: f32(.35)

Turn_Page_Tile :: enum u8 {Hidden, Revealed_Safe, Confirmed, Wrong, Cracking, Falling, Gone}
Turn_Page_Profile :: struct {pages, length: int, reveal, budget, reset: f32}
Turn_Page_Player_Return :: struct {
	pos, prev_pos, facing, heading_stable: Vec2,
	moving: bool,
	heading_hold, anim_time, sim_elapsed, dash_timer: f32,
	visual_action: Visual_Action,
	action_time, action_duration: f32,
}
Turn_Page_State :: struct {
	version: int,
	route: [TURN_PAGE_MAX_ROUTE][2]int,
	gaps: [TURN_PAGE_MAX_ROUTE]bool,
	length: int,
	tiles: [TURN_PAGE_SIZE][TURN_PAGE_SIZE]Turn_Page_Tile,
	fall_cell: [2]int,
	fall_elapsed: f32,
	fall_active: bool,
	return_player: Turn_Page_Player_Return,
}

turn_page_profile :: proc(depth, page: int) -> Turn_Page_Profile {
	if depth >= 9 do return {3,8,1,42,.95}
	if depth >= 8 do return {3,6+page%2,1.25,40,1.15}
	return {2,5,1.5,26,1.25}
}
turn_page_center :: proc(cell: [2]int) -> Vec2 {return {f32(cell.x)+.5,f32(cell.y)+.5}}
app_story_turn_page_active :: proc(app: ^App) -> bool {
	return app_story_minigame_active(app) && app.story_minigame.kind == .Bind_The_Page
}
app_story_world_minigame_active :: proc(app: ^App) -> bool {
	return app_story_soul_hunt_active(app) || app_story_turn_page_active(app)
}

turn_page_capture_player :: proc(p: ^Player) -> Turn_Page_Player_Return {
	return {p.pos,p.prev_pos,p.facing,p.heading_stable,p.moving,p.heading_hold,p.anim_time,p.sim_elapsed,p.dash_timer,p.visual_action,p.action_time,p.action_duration}
}
turn_page_restore_player :: proc(p: ^Player, saved: Turn_Page_Player_Return) {
	p.pos=saved.pos;p.prev_pos=saved.prev_pos;p.facing=saved.facing;p.heading_stable=saved.heading_stable
	p.moving=saved.moving;p.heading_hold=saved.heading_hold;p.anim_time=saved.anim_time
	p.sim_elapsed=saved.sim_elapsed;p.dash_timer=saved.dash_timer;p.visual_action=saved.visual_action
	p.action_time=saved.action_time;p.action_duration=saved.action_duration
}

// Monotone cardinal paths cannot self-intersect. Gap edges are kept straight,
// leaving a full cell of support at both ends of every two-cell dash.
turn_page_generate :: proc(seed: u64, depth, page: int) -> (result: Turn_Page_State) {
	result.version=1;result.length=turn_page_profile(depth,page).length
	rng:=rng_make(derive_seed(seed,u64(page)+0x70616765),stream=43)
	if page>0 && depth>=8 do result.gaps[2]=true
	if page>0 && depth>=9 do result.gaps[5]=true
	result.route[0]={1,1}
	direction:=[2]int{1,0}
	for i in 1..<result.length {
		if !result.gaps[i-1] {direction={1,0};if rng_below(&rng,2)==1 do direction={0,1}}
		result.route[i]=result.route[i-1]+direction
	}
	flip_x:=rng_below(&rng,2)==1;flip_y:=rng_below(&rng,2)==1
	for i in 0..<result.length {
		if flip_x do result.route[i].x=TURN_PAGE_SIZE-1-result.route[i].x
		if flip_y do result.route[i].y=TURN_PAGE_SIZE-1-result.route[i].y
		cell:=result.route[i];result.tiles[cell.x][cell.y]=result.gaps[i]?.Gone:.Revealed_Safe
	}
	return
}
turn_page_route_valid :: proc(page: ^Turn_Page_State) -> bool {
	if page==nil || page.length<5 || page.length>TURN_PAGE_MAX_ROUTE do return false
	for i in 0..<page.length {
		cell:=page.route[i]
		if cell.x<1||cell.y<1||cell.x>=TURN_PAGE_SIZE-1||cell.y>=TURN_PAGE_SIZE-1 do return false
		for j in 0..<i do if page.route[j]==cell do return false
		if i>0 {d:=cell-page.route[i-1];if abs(d.x)+abs(d.y)!=1 do return false}
		if page.gaps[i] {
			if i==0||i==page.length-1||page.gaps[i-1]||page.gaps[i+1] do return false
			if cell-page.route[i-1]!=page.route[i+1]-cell do return false
		}
	}
	return true
}
turn_page_begin_page :: proc(app: ^App) {
	state:=&app.story_minigame;saved:=app.turn_page.return_player
	app.turn_page=turn_page_generate(state.seed,state.depth,state.score)
	app.turn_page.return_player=saved
	state.phase=.Preview;state.elapsed=0;state.step=0;state.revision+=1
	p:=&app.run.player;p.pos=turn_page_center(app.turn_page.route[0]);p.prev_pos=p.pos
	p.moving=false;p.dash_timer=0;p.visual_action=.None;p.action_time=0;p.action_duration=0
}
app_story_start_turn_page :: proc(app: ^App) {
	app.turn_page={return_player=turn_page_capture_player(&app.run.player)}
	app.story_panel={}
	turn_page_begin_page(app)
}

turn_page_wrong :: proc(app: ^App, cell: [2]int) {
	page:=&app.turn_page;state:=&app.story_minigame
	if page.fall_active||state.outcome!=.None do return
	page.fall_active=true;page.fall_elapsed=0;page.fall_cell=cell
	if cell.x>=0&&cell.y>=0&&cell.x<TURN_PAGE_SIZE&&cell.y<TURN_PAGE_SIZE do page.tiles[cell.x][cell.y]=.Wrong
	state.mistakes+=1;state.revision+=1;state.last_correct=false
	app.run.player.moving=false
	sfx_emit(&app.run,.Story_Consequence)
}

// Exact capsule-versus-cell distance: endpoint/edge and corner/segment
// minima, plus a slab intersection for a segment passing through the cell.
turn_page_sweep_touches_cell :: proc(start, finish: Vec2, cell: [2]int) -> bool {
 low:=Vec2{f32(cell.x),f32(cell.y)};high:=low+Vec2{1,1};delta:=finish-start
 enter:f32=0;leave:f32=1
 for axis in 0..<2 {
  if abs(delta[axis])<.000001 {
   if start[axis]<low[axis]||start[axis]>high[axis] {enter=1;leave=0;break}
  } else {
   a:=(low[axis]-start[axis])/delta[axis];b:=(high[axis]-start[axis])/delta[axis]
   enter=max(enter,min(a,b));leave=min(leave,max(a,b))
  }
 }
 if enter<=leave do return true
 radius_sq:=TURN_PAGE_RADIUS*TURN_PAGE_RADIUS
 for point in ([2]Vec2{start,finish}) {
  near:=Vec2{clamp(point.x,low.x,high.x),clamp(point.y,low.y,high.y)}
  d:=point-near;if d.x*d.x+d.y*d.y<radius_sq do return true
 }
 length_sq:=delta.x*delta.x+delta.y*delta.y
 if length_sq>.000001 {
  for corner in ([4]Vec2{low,{high.x,low.y},high,{low.x,high.y}}) {
   offset:=corner-start;t:=clamp((offset.x*delta.x+offset.y*delta.y)/length_sq,f32(0),f32(1))
   d:=corner-(start+delta*t);if d.x*d.x+d.y*d.y<radius_sq do return true
  }
 }
 return false
}

// Each short segment validates the complete swept radius. Short segments only
// order progress through cells; they are not point samples of collision.
Turn_Page_Sweep_Result :: enum {Clear, Blocked, Wrong}

turn_page_sweep_contact :: proc(app: ^App, start, finish: Vec2, dashing: bool) -> (Turn_Page_Sweep_Result,[2]int) {
 page:=&app.turn_page;state:=&app.story_minigame
 next:=min(state.step+1,page.length-1)
 if page.gaps[next] do next+=1
 result:=Turn_Page_Sweep_Result.Clear;wrong:[2]int
 for y in int(math.floor(min(start.y,finish.y)-TURN_PAGE_RADIUS))..=int(math.floor(max(start.y,finish.y)+TURN_PAGE_RADIUS)) {
  for x in int(math.floor(min(start.x,finish.x)-TURN_PAGE_RADIUS))..=int(math.floor(max(start.x,finish.x)+TURN_PAGE_RADIUS)) {
   cell:=[2]int{x,y}
   if !turn_page_sweep_touches_cell(start,finish,cell) do continue
   if x<0||y<0||x>=TURN_PAGE_SIZE||y>=TURN_PAGE_SIZE do return .Blocked,cell
   allowed,gap:=false,false
   for i in 0..=next {
    if page.route[i]==cell {gap=page.gaps[i];allowed=!gap||dashing;break}
   }
   // Empty space stops the segment before a wrong step can be committed.
   // Only authored, ordered route gaps can be crossed while airborne.
   if page.tiles[x][y]==.Gone&&!(dashing&&allowed&&gap) do return .Blocked,cell
   if !allowed&&result==.Clear {result=.Wrong;wrong=cell}
  }
 }
 return result,wrong
}

turn_page_move :: proc(app: ^App, delta: Vec2, dashing: bool) {
	page:=&app.turn_page;state:=&app.story_minigame;p:=&app.run.player
	start:=p.pos;distance:=math.hypot(delta.x,delta.y)
	steps:=max(1,int(math.ceil(distance/.04)))
	landing_step:=min(state.step+1,page.length-1)
	if page.gaps[landing_step] do landing_step+=1
	landing:=turn_page_center(page.route[landing_step])
	for n in 1..=steps {
		pos:=start+delta*(f32(n)/f32(steps))
		contact,wrong:=turn_page_sweep_contact(app,p.pos,pos,dashing)
		if contact==.Blocked do break
		if contact==.Wrong {turn_page_wrong(app,wrong);return}
		p.pos=pos
		next:=min(state.step+1,page.length-1)
		if page.gaps[next] do next+=1
		cell_at_pos:=[2]int{int(math.floor(pos.x)),int(math.floor(pos.y))}
		if cell_at_pos==page.route[next] {
			for i in state.step..=next {cell:=page.route[i];if !page.gaps[i] do page.tiles[cell.x][cell.y]=.Confirmed}
			state.step=next;state.revision+=1;state.last_correct=true
			if next==page.length-1 {
				state.score+=1;sfx_emit(&app.run,.Story_Consequence)
				if state.score>=state.goal {story_minigame_finish(state,true)} else {turn_page_begin_page(app)}
				return
			}
		}
		// Brake at the landing center along the dash direction, preserving
		// lateral foot placement. Requiring a near-exact center hit lets a valid
		// off-center dash overshoot its landing and fall off the far edge.
		if dashing&&state.step>=landing_step {
			d:=pos-landing
			if d.x*delta.x+d.y*delta.y>=0 do return
		}
	}
	if dashing {
		// A clipped or short dash still needs a fully supported landing. Do not
		// leave the player standing over a gap if another hole stopped the dash.
		for i in 0..<page.length do if page.gaps[i]&&turn_page_sweep_touches_cell(p.pos,p.pos,page.route[i]) {
			turn_page_wrong(app,page.route[i]);return
		}
	}
}
turn_page_dash :: proc(app: ^App, aim: Vec2) -> bool {
	if !app_story_turn_page_active(app)||app.story_minigame.phase!=.Play||app.turn_page.fall_active||app.run.player.dash_timer>0 do return false
	p:=&app.run.player;direction:=aim;length:=math.hypot(direction.x,direction.y)
	if length<.001 do return false
	direction/=length;p.facing=direction;p.prev_pos=p.pos
	p.dash_timer=TURN_PAGE_DASH_COOLDOWN
	player_start_visual_action(p,.Dash,PLAYER_DASH_ACTION_SECONDS)
	turn_page_move(app,direction*2.4,true)
	sfx_emit(&app.run,sfx_player_dash_bank(p.archetype),p.pos,spatial=true)
	return true
}
turn_page_tick :: proc(app: ^App, move: Vec2, dt: f32) -> bool {
	state:=&app.story_minigame;page:=&app.turn_page;p:=&app.run.player
	step_dt:=clamp(dt,f32(0),f32(.25))
	p.prev_pos=p.pos;p.moving=false;p.sim_elapsed+=step_dt
	p.dash_timer=max(f32(0),p.dash_timer-step_dt);player_tick_visual_action(p,step_dt)
	profile:=turn_page_profile(state.depth,state.score)
	if state.phase==.Result {
  if page.fall_active {
   page.fall_elapsed=min(TURN_PAGE_FALL_SECONDS,page.fall_elapsed+step_dt)
   turn_page_update_fall_tile(page)
  }
  state.result_time=max(f32(0),state.result_time-step_dt)
  return state.result_time<=0
 }
	state.elapsed+=step_dt
	if state.phase==.Preview {
		if state.elapsed>=profile.reveal {
			state.phase=.Play;state.elapsed=0
			for i in 0..<page.length {cell:=page.route[i];page.tiles[cell.x][cell.y]=page.gaps[i]?.Gone:(i==0?.Confirmed:.Hidden)}
		}
		return false
	}
	state.time_left=max(f32(0),state.time_left-step_dt)
	if state.time_left<=0 {story_minigame_finish(state,false);return false}
	if page.fall_active {
		page.fall_elapsed+=step_dt
		turn_page_update_fall_tile(page)
		if page.fall_elapsed>=profile.reset {
			// Retry the same route without a new reveal. Confirmed ink is erased.
			for i in 0..<page.length {c:=page.route[i];page.tiles[c.x][c.y]=page.gaps[i]?.Gone:.Hidden}
			page.fall_active=false;state.step=0
			c:=page.route[0];page.tiles[c.x][c.y]=.Confirmed
			p.pos=turn_page_center(c);p.prev_pos=p.pos;p.dash_timer=0;p.visual_action=.None
		}
		return false
	}
	magnitude:=math.hypot(move.x,move.y)
	if magnitude>.001 {
		direction:=move/magnitude;before:=p.pos
		turn_page_move(app,direction*TURN_PAGE_SPEED*step_dt*min(f32(1),magnitude),false)
		p.moving=!page.fall_active&&state.phase==.Play&&p.pos!=before
		if p.moving {
			p.facing=direction
			displacement:=p.pos-before
			p.anim_time+=walk_animation_advance(step_dt,TURN_PAGE_SPEED,math.hypot(displacement.x,displacement.y),TURN_PAGE_SPEED*step_dt)
		}
	}
	return false
}

app_story_normalize_turn_page_after_restore :: proc(app: ^App) {
	if !app_story_turn_page_active(app) do return
	if app.turn_page.version==1 do return
	// Legacy modal cells are never read as coordinates. Restart at page one
	// with the original chosen continuation and the real saved player state.
	state:=&app.story_minigame;state.score=0;state.step=0;state.outcome=.None
	profile:=turn_page_profile(state.depth,0);state.goal=profile.pages;state.time_left=profile.budget
	state.board_count=0;state.sequence_count=0
	app_story_start_turn_page(app)
}

turn_page_saved_state_valid :: proc(payload: ^Run_Save_Payload) -> bool {
	page:=&payload.turn_page;state:=&payload.story_minigame
	if page.version==0 do return true // legacy modal, migrated after installation
	if page.version!=1||!state.active||state.kind!=.Bind_The_Page||state.depth!=payload.depth do return false
	profile:=turn_page_profile(state.depth,state.score)
	if state.instance_id<=0||state.goal!=profile.pages||state.score<0||state.score>state.goal||state.mistakes<0 do return false
	if state.step<0||state.step>=page.length||!turn_page_route_valid(page) do return false
	generated:=turn_page_generate(state.seed,state.depth,min(state.score,state.goal-1))
	if page.route!=generated.route||page.gaps!=generated.gaps||page.length!=generated.length do return false
	if state.phase==.Ready do return false
	if (state.phase==.Result)!=(state.outcome!=.None) do return false
	if state.outcome==.Won&&state.score!=state.goal do return false
	if state.phase!=.Result&&state.score>=state.goal do return false
	saved:=page.return_player
	values:=[18]f32{state.elapsed,state.time_left,state.result_time,page.fall_elapsed,
		saved.pos.x,saved.pos.y,saved.prev_pos.x,saved.prev_pos.y,saved.facing.x,saved.facing.y,
		saved.heading_hold,saved.anim_time,saved.sim_elapsed,saved.dash_timer,saved.action_time,saved.action_duration,
		payload.player.prev_pos.x,payload.player.prev_pos.y}
	for v in values do if math.is_nan(v)||math.is_inf(v) do return false
	if state.time_left<0||state.time_left>profile.budget||page.fall_elapsed<0||page.fall_elapsed>profile.reset+.25||state.result_time<0 do return false
	if saved.dash_timer<0||saved.pos.x<0||saved.pos.y<0||saved.pos.x>=MAP_W||saved.pos.y>=MAP_H do return false
	if blocked_for_radius(&payload.dungeon,saved.pos.x,saved.pos.y,PLAYER_HIT_RADIUS,block_stairs=true) do return false
	pos:=payload.player.pos
	if pos.x<0||pos.y<0||pos.x>=TURN_PAGE_SIZE||pos.y>=TURN_PAGE_SIZE do return false
	for x in 0..<TURN_PAGE_SIZE do for y in 0..<TURN_PAGE_SIZE {
		if int(page.tiles[x][y])<0||int(page.tiles[x][y])>=len(Turn_Page_Tile) do return false
	}
	return true
}

turn_page_update_fall_tile :: proc(page: ^Turn_Page_State) {
 cell:=page.fall_cell
 if cell.x>=0&&cell.y>=0&&cell.x<TURN_PAGE_SIZE&&cell.y<TURN_PAGE_SIZE {
  page.tiles[cell.x][cell.y]=page.fall_elapsed>=TURN_PAGE_FALL_SECONDS?.Gone:(page.fall_elapsed>=.1?.Falling:.Cracking)
 }
}

package archrogue_tests

import "core:testing"
import ar "../src"

@(private = "file")
mx1_near :: proc(a, b: f32, epsilon: f32 = 1e-5) -> bool {
	return abs(a - b) < epsilon
}

@(test)
mx1_height_scale_preserves_normalized_vertical_fov :: proc(t: ^testing.T) {
	base := f32(2)
	heights := [?]int{360, 720, 1080, 1440}
	for height in heights {
		scale := ar.presentation_scale_for_height(height)
		effective := ar.effective_view_zoom(base, height)
		testing.expectf(t, mx1_near(scale, f32(height) / 720), "height %v scale %.5f", height, scale)
		testing.expectf(t, mx1_near(effective, base * scale), "height %v effective zoom %.5f", height, effective)
		testing.expectf(
			t,
			mx1_near(f32(height) / effective, 720 / base),
			"height %v changed normalized vertical FOV",
			height,
		)
	}
	testing.expect(t, mx1_near(ar.presentation_scale_for_height(0), 1.0 / 720), "zero height must use one physical pixel")
	testing.expect(t, mx1_near(ar.presentation_scale_for_height(-100), 1.0 / 720), "negative height must use one physical pixel")

	options := ar.options_default()
	stored := options.view_zoom
	_ = ar.effective_view_zoom(options.view_zoom, 1080)
	testing.expect(t, options.view_zoom == stored, "presentation scaling must not mutate stored option zoom")
}

@(test)
mx1_minimap_projection_uses_isometric_half_steps :: proc(t: ^testing.T) {
	center := ar.Vec2{80, 40}
	testing.expect(t, ar.minimap_project_relative({0, 0}, center, 1) == center)
	testing.expect(t, ar.minimap_project_relative({1, 0}, center, 1) == center + ar.Vec2{4, 2})
	testing.expect(t, ar.minimap_project_relative({0, 1}, center, 1) == center + ar.Vec2{-4, 2})
	testing.expect(t, ar.minimap_project_relative({1, 0}, center, 2.5) == center + ar.Vec2{10, 5})
	testing.expect(t, ar.minimap_project_relative({0, 1}, center, 0.5) == center + ar.Vec2{-2, 1})
}

@(test)
mx1_minimap_zoom_steps_clamps_and_resets :: proc(t: ^testing.T) {
	zoomed_in := ar.minimap_zoom_apply(ar.MINIMAP_ZOOM_DEFAULT, 1)
	testing.expect(t, mx1_near(zoomed_in, ar.MINIMAP_ZOOM_STEP), "one positive notch must multiply by the step")
	testing.expect(t, mx1_near(ar.minimap_zoom_apply(zoomed_in, -1), ar.MINIMAP_ZOOM_DEFAULT), "opposite notches must cancel")
	testing.expect(t, ar.minimap_zoom_apply(ar.MINIMAP_ZOOM_DEFAULT, 100) == ar.MINIMAP_ZOOM_MAX, "zoom must clamp high")
	testing.expect(t, ar.minimap_zoom_apply(ar.MINIMAP_ZOOM_DEFAULT, -100) == ar.MINIMAP_ZOOM_MIN, "zoom must clamp low")

	app: ar.App
	ar.app_init(&app, 17)
	app.mode = .Playing
	ar.app_apply(&app, ar.Intent{minimap_zoom = 1})
	testing.expect(t, mx1_near(app.minimap_zoom, ar.MINIMAP_ZOOM_STEP), "app intent must use multiplicative minimap zoom")
	app.minimap_zoom = ar.MINIMAP_ZOOM_MAX
	ar.app_reset_run_ui(&app)
	testing.expect(t, app.minimap_zoom == ar.MINIMAP_ZOOM_DEFAULT, "new-run UI reset must restore default minimap zoom")
}

@(test)
mx1_minimap_card_constants_match_reference :: proc(t: ^testing.T) {
	testing.expect(t, ar.MINIMAP_CARD_WIDTH == 172 && ar.MINIMAP_CARD_HEIGHT == 110)
	testing.expect(t, ar.MINIMAP_BASE_HALF_STEP_X == 4 && ar.MINIMAP_BASE_HALF_STEP_Y == 2)
}

@(test)
mx1_select_consumes_horizontal_navigation_with_wrap :: proc(t: ^testing.T) {
	app: ar.App
	ar.app_init(&app, 23)
	app.mode = .Select
	count := len(ar.Archetype_Id)

	app.select_index = 0
	ar.app_apply(&app, ar.Intent{menu_horizontal = -1})
	testing.expect(t, app.select_index == count - 1, "Left must wrap to the last archetype")
	ar.app_apply(&app, ar.Intent{menu_horizontal = 1})
	testing.expect(t, app.select_index == 0, "Right must wrap to the first archetype")
	ar.app_apply(&app, ar.Intent{menu_delta = 1, menu_horizontal = 1})
	testing.expect(t, app.select_index == 2, "Select must consume both navigation deltas")
}

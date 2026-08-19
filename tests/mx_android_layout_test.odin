package archrogue_tests

// MX-android — physical safe-area and touch-layout contracts. These tests stay
// raylib-free and use the same geometry that a platform renderer/hit tester will
// consume after every Android surface or inset revision.

import "core:math"
import "core:testing"
import ar "../src"

@(private = "file")
mx_android_expect_inside :: proc(
	t: ^testing.T,
	outer, inner: ar.Mobile_Rect,
	label: string,
) {
	testing.expectf(
		t,
		ar.mobile_rect_contains_rect(outer, inner),
		"%s must remain inside its owning rectangle: outer=%v inner=%v",
		label,
		outer,
		inner,
	)
}

@(private = "file")
mx_android_expect_minimum_target :: proc(
	t: ^testing.T,
	rect: ar.Mobile_Rect,
	minimum_px: f32,
	label: string,
) {
	testing.expectf(
		t,
		rect.width + 1e-4 >= minimum_px && rect.height + 1e-4 >= minimum_px,
		"%s is %.1fx%.1f px, below the %.1f px (48dp) target",
		label,
		rect.width,
		rect.height,
		minimum_px,
	)
}

@(test)
mx_android_safe_insets_use_edgewise_max_then_clamp :: proc(t: ^testing.T) {
	metrics := ar.Mobile_Display_Metrics{
		surface_width = 2400,
		surface_height = 1080,
		density = 2.5,
		cutout = {left = 180, top = -9, right = 20, bottom = 0},
		system_gesture = {left = 24, top = 16, right = 72, bottom = 36},
	}
	combined := ar.mobile_insets_union(metrics.cutout, metrics.system_gesture)
	testing.expect(
		t,
		combined == ar.Mobile_Pixel_Insets{180, 16, 72, 36},
		"each safe edge must independently keep the larger cutout/gesture inset",
	)

	safe := ar.mobile_safe_rect(metrics)
	testing.expect(
		t,
		safe == ar.Mobile_Rect{180, 16, 2148, 1028},
		"safe rectangle must be derived from the physical surface without rescaling",
	)

	// Broken vendor values cannot cross opposite edges or produce negative area.
	hostile := ar.mobile_insets_clamp(
		{left = 999, top = 999, right = 999, bottom = 999},
		100,
		50,
	)
	testing.expect(
		t,
		hostile == ar.Mobile_Pixel_Insets{99, 49, 0, 0},
		"clamping must retain a deterministic one-pixel safe rectangle",
	)
	hostile_safe := ar.mobile_safe_rect({
		surface_width = 100,
		surface_height = 50,
		cutout = {left = 999, top = 999, right = 999, bottom = 999},
	})
	testing.expect(t, hostile_safe == ar.Mobile_Rect{99, 49, 1, 1})
}

@(test)
mx_android_native_layout_covers_requested_landscape_classes :: proc(t: ^testing.T) {
	cases := [4]struct {
		name:    string,
		metrics: ar.Mobile_Display_Metrics,
	}{
		{
			name = "16:9 phone",
			metrics = {surface_width = 1920, surface_height = 1080, density = 2.0, revision = 11},
		},
		{
			name = "16:10 phone",
			metrics = {surface_width = 1920, surface_height = 1200, density = 2.0, revision = 12},
		},
		{
			name = "20:9 cutout phone",
			metrics = {
				surface_width = 2400,
				surface_height = 1080,
				density = 2.5,
				cutout = {left = 120},
				system_gesture = {right = 64, bottom = 24},
				revision = 13,
			},
		},
		{
			name = "tablet landscape",
			metrics = {
				surface_width = 2560,
				surface_height = 1600,
				density = 2.0,
				system_gesture = {left = 24, right = 24, bottom = 32},
				revision = 14,
			},
		},
	}

	for test_case in cases {
		layout, status := ar.mobile_layout_build(test_case.metrics)
		testing.expectf(t, status == .Valid, "%s layout status was %v", test_case.name, status)
		if status != .Valid do continue

		expected_display := ar.Mobile_Rect{
			0,
			0,
			f32(test_case.metrics.surface_width),
			f32(test_case.metrics.surface_height),
		}
		testing.expectf(t, layout.display_rect == expected_display, "%s changed the native surface", test_case.name)
		testing.expectf(t, layout.world_viewport == expected_display, "%s world must render edge-to-edge", test_case.name)
		testing.expectf(t, layout.revision == test_case.metrics.revision, "%s lost the layout revision", test_case.name)
		mx_android_expect_inside(t, layout.display_rect, layout.safe_rect, test_case.name)
		mx_android_expect_inside(t, layout.safe_rect, layout.left_rail, "left rail")
		mx_android_expect_inside(t, layout.safe_rect, layout.right_rail, "right rail")
		mx_android_expect_inside(t, layout.safe_rect, layout.gameplay_rect, "gameplay region")
		testing.expectf(t, !ar.mobile_rects_overlap(layout.left_rail, layout.gameplay_rect), "%s left rail overlaps gameplay", test_case.name)
		testing.expectf(t, !ar.mobile_rects_overlap(layout.right_rail, layout.gameplay_rect), "%s right rail overlaps gameplay", test_case.name)
		testing.expectf(t, !ar.mobile_rects_overlap(layout.left_rail, layout.right_rail), "%s rails overlap", test_case.name)

		minimum := f32(48) * ar.mobile_density(test_case.metrics)
		testing.expectf(t, layout.minimum_target_px + 1e-4 >= minimum, "%s target scale fell below 48dp", test_case.name)
		mx_android_expect_inside(t, layout.left_rail, layout.joystick, "joystick")
		mx_android_expect_minimum_target(t, layout.joystick, minimum, "joystick")
		testing.expectf(t,layout.joystick.x>layout.left_rail.x,
			"%s joystick must be inset to the right like the mobile mockup",test_case.name)
		testing.expectf(t,ar.mobile_rect_bottom(layout.joystick)<ar.mobile_rect_bottom(layout.left_rail),
			"%s joystick must be raised above the lower safe edge",test_case.name)

		testing.expect(t, len(layout.resource_bars) == 4, "mobile HUD must show XP plus health, mana, and stamina")
		for bar, i in layout.resource_bars {
			mx_android_expect_inside(t, layout.left_rail, bar, "resource bar")
			testing.expectf(t,bar.x>layout.left_rail.x&&bar.y>layout.left_rail.y,
				"%s resource stack must be inset down and right",test_case.name)
			testing.expectf(t, bar.height < layout.joystick.height && bar.width < bar.height,
				"%s resource bar must remain smaller and vertical", test_case.name)
			testing.expectf(t, math.abs(bar.width/bar.height-ar.MOBILE_STATUS_BAR_ASPECT) < 1e-4,
				"%s resource bar aspect no longer matches the authored frame", test_case.name)
			if i > 0 {
				testing.expectf(t, !ar.mobile_rects_overlap(layout.resource_bars[i-1],bar),
					"%s resource bars %v/%v overlap",test_case.name,i-1,i)
			}
		}

		for slot, i in layout.action_slots {
			mx_android_expect_inside(t, layout.right_rail, slot, "action slot")
			mx_android_expect_minimum_target(t, slot, minimum, "action slot")
			if i > 0 {
				testing.expectf(t, !ar.mobile_rects_overlap(layout.action_slots[i - 1], slot), "%s action slots %v/%v overlap", test_case.name, i - 1, i)
			}
		}

		utilities := [4]ar.Mobile_Rect{
			layout.inventory,
			layout.character,
			layout.pause,
			layout.interact,
		}
		for utility, i in utilities {
			mx_android_expect_inside(t, layout.gameplay_rect, utility, "utility control")
			mx_android_expect_minimum_target(t, utility, minimum, "utility control")
			if i > 0 {
				testing.expectf(t, !ar.mobile_rects_overlap(utilities[i - 1], utility), "%s utility controls %v/%v overlap", test_case.name, i - 1, i)
			}
		}
		lowest_action:=layout.action_slots[len(layout.action_slots)-1]
		testing.expectf(t,math.abs(ar.mobile_rect_center(layout.interact).y-ar.mobile_rect_center(lowest_action).y)<ar.MOBILE_GEOMETRY_EPSILON,
			"%s A button must align vertically with the mana-potion slot",test_case.name)
		testing.expectf(t,ar.mobile_rect_right(layout.interact)<ar.mobile_rect_right(layout.gameplay_rect),
			"%s A button must leave a wider gap to the action rail",test_case.name)

		focus_expected := ar.Vec2{
			layout.gameplay_rect.x + layout.gameplay_rect.width * .5,
			layout.gameplay_rect.y + layout.gameplay_rect.height * ar.CAMERA_FOCUS_Y,
		}
		testing.expectf(t, layout.world_focus == focus_expected, "%s focus must derive from unobstructed gameplay", test_case.name)
		testing.expectf(t, ar.mobile_rect_contains(layout.gameplay_rect, layout.world_focus), "%s focus escaped gameplay", test_case.name)
		for slot in layout.action_slots do testing.expect(t, !ar.mobile_rect_contains(slot, layout.world_focus), "action rail obscured camera focus")
		for utility in utilities do testing.expect(t, !ar.mobile_rect_contains(utility, layout.world_focus), "utility control obscured camera focus")
	}
}

@(test)
mx_android_layout_rejects_portrait_and_unusable_physical_targets :: proc(t: ^testing.T) {
	portrait, portrait_status := ar.mobile_layout_build({
		surface_width = 1080,
		surface_height = 1920,
		density = 3,
	})
	testing.expect(t, portrait_status == .Unsupported_Portrait, "gameplay must remain landscape-only")
	testing.expect(t, portrait.world_viewport == ar.Mobile_Rect{0, 0, 1080, 1920}, "portrait rejection must still report the native surface")

	_, tiny_status := ar.mobile_layout_build({
		surface_width = 640,
		surface_height = 360,
		density = 3,
	})
	testing.expect(t, tiny_status == .Too_Small, "layout must reject controls that cannot retain 48dp targets")
}

@(test)
mx_android_resource_fill_is_clamped_and_bottom_up :: proc(t: ^testing.T) {
	container := ar.Mobile_Rect{10, 20, 30, 100}
	empty := ar.mobile_resource_fill_rect(container, 0)
	quarter := ar.mobile_resource_fill_rect(container, .25)
	full := ar.mobile_resource_fill_rect(container, 1)
	below := ar.mobile_resource_fill_rect(container, -4)
	above := ar.mobile_resource_fill_rect(container, 4)

	testing.expect(t, empty == ar.Mobile_Rect{10, 120, 30, 0}, "empty resource must anchor at the bottom edge")
	testing.expect(t, quarter == ar.Mobile_Rect{10, 95, 30, 25}, "25% resource must occupy the bottom quarter")
	testing.expect(t, full == container, "full resource must cover the complete clipping silhouette")
	testing.expect(t, below == empty && above == full, "resource ratios must clamp to [0,1]")
	testing.expect(t, ar.mobile_rect_contains_rect(container, quarter), "fill clip must remain within the cap-aware container mask")
	testing.expect(t, math.abs(ar.mobile_rect_bottom(quarter) - ar.mobile_rect_bottom(container)) < 1e-5, "all partial fills must share the container bottom")
}

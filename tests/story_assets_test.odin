package archrogue_tests

// MX-story asset foundation acceptance. Story-art tests synthesize the exact
// manifest contract in memory so concurrent/generated PNG work is not a test
// prerequisite. Existing story actor sheets are inspected headlessly through
// their committed manifest and PNG headers; no raylib API or window is used.

import "core:crypto/sha2"
import "core:encoding/json"
import "core:fmt"
import "core:mem"
import "core:os"
import "core:testing"
import ar "../src"

STORY_TEST_SHA256 :: "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"

@(private = "file")
Story_Test_Manifest_Unknown_Root :: struct {
	format_version: int,
	asset_count:    int,
	assets:         map[string]ar.Story_Art_Manifest_Entry,
	unexpected:     bool,
}

@(private = "file")
Story_Test_Manifest_Entry_Extra :: struct {
	file:       string,
	sha256:     string,
	unexpected: bool,
}

@(private = "file")
Story_Test_Manifest_Unknown_Entry :: struct {
	format_version: int,
	asset_count:    int,
	assets:         map[string]Story_Test_Manifest_Entry_Extra,
}

@(private = "file")
Story_Test_Actor_Clip :: struct {
	frames: int,
	rows:   int,
	fps:    f32,
	loop:   bool,
	sha256: string,
}

@(private = "file")
Story_Test_Actor :: struct {
	cell:          int,
	source_canvas: [2]int,
	canvas_world:  f32,
	anchor:        [2]f32,
	clips:         map[string]Story_Test_Actor_Clip,
}

@(private = "file")
Story_Test_Actor_Manifest :: struct {
	format:       int,
	native_cells: bool,
	cell:         int,
	actors:       map[string]Story_Test_Actor,
}

@(private = "file")
story_test_manifest_make :: proc() -> ar.Story_Art_Manifest {
	manifest := ar.Story_Art_Manifest {
		format_version = ar.STORY_ART_MANIFEST_FORMAT,
		asset_count = ar.STORY_ART_ASSET_COUNT,
		assets = make(map[string]ar.Story_Art_Manifest_Entry, ar.STORY_ART_ASSET_COUNT),
	}
	for index in 0 ..< ar.STORY_ART_ASSET_COUNT {
		def, found := ar.story_art_def_at(index)
		assert(found)
		manifest.assets[def.key] = {file = def.file, sha256 = STORY_TEST_SHA256}
	}
	return manifest
}

@(private = "file")
story_test_manifest_destroy :: proc(manifest: ^ar.Story_Art_Manifest) {
	if manifest == nil do return
	delete(manifest.assets)
	manifest^ = {}
}

@(private = "file")
story_test_u32_be :: proc(data: []u8, offset: int) -> u32 {
	return u32(data[offset]) << 24 |
		u32(data[offset + 1]) << 16 |
		u32(data[offset + 2]) << 8 |
		u32(data[offset + 3])
}

@(private = "file")
story_test_png_size :: proc(data: []u8) -> ([2]int, bool) {
	valid := len(data) >= 24 &&
		data[0] == 0x89 && data[1] == 'P' && data[2] == 'N' && data[3] == 'G' &&
		data[4] == 0x0d && data[5] == 0x0a && data[6] == 0x1a && data[7] == 0x0a &&
		data[12] == 'I' && data[13] == 'H' && data[14] == 'D' && data[15] == 'R'
	if !valid do return {}, false
	return {
		int(story_test_u32_be(data, 16)),
		int(story_test_u32_be(data, 20)),
	}, true
}

@(private = "file")
story_test_sha256_hex :: proc(data: []u8) -> [sha2.DIGEST_SIZE_256 * 2]u8 {
	hasher: sha2.Context_256
	sha2.init_256(&hasher)
	sha2.update(&hasher, data)
	digest: [sha2.DIGEST_SIZE_256]u8
	sha2.final(&hasher, digest[:])

	digits := "0123456789abcdef"
	hex: [sha2.DIGEST_SIZE_256 * 2]u8
	for value, index in digest {
		hex[index * 2] = digits[int(value >> 4)]
		hex[index * 2 + 1] = digits[int(value & 0x0f)]
	}
	return hex
}

@(test)
mx_story_art_registry_covers_every_typed_semantic_key :: proc(t: ^testing.T) {
	testing.expect(t, ar.STORY_ART_ASSET_COUNT == 81, "73 corpus assets + one Lossless Soul backdrop + seven choice icons are required")
	testing.expect(t, ar.STORY_CHOICE_ICON_COUNT == 7, "legacy story panels expose seven authored choice glyphs")
	testing.expect(t, ar.story_art_registry_is_valid(), "story art keys/files must be complete, safe, and unique")

	usage_counts: [ar.Story_Art_Usage]int
	for index in 0 ..< ar.STORY_ART_ASSET_COUNT {
		def, found := ar.story_art_def_at(index)
		testing.expectf(t, found, "story art slot %v does not resolve", index)
		if found do usage_counts[def.usage] += 1
	}
	testing.expect(t, usage_counts[.Backdrop] == 34, "8 omen + 10 guest + 15 ending + 1 soul backdrops are required")
	testing.expect(t, usage_counts[.Icon] == 17, "10 relic + 7 choice icons are required")
	testing.expect(t, usage_counts[.Portrait] == 30, "ten roles x three named guest portraits are required")
	_, found_before := ar.story_art_def_at(-1)
	_, found_after := ar.story_art_def_at(ar.STORY_ART_ASSET_COUNT)
	testing.expect(t, !found_before && !found_after, "flattened registry must reject out-of-range slots")

	assets: ar.Assets
	resolved_count := 0
	for id in ar.Story_Motif_Id {
		asset, known := ar.story_art_texture_for_key(&assets, ar.STORY_OMEN_ASSET_KEYS[id])
		testing.expect(t, known && asset == ar.story_omen_backdrop_asset(&assets, id), "omen semantic key must resolve to its typed slot")
		testing.expect(t, ar.STORY_OMEN_ASSET_KEYS[id] == fmt.tprintf("story.omen.%s", ar.STORY_MOTIFS[id].slug), "omen key must derive from its stable corpus slug")
		testing.expect(t, ar.STORY_OMEN_ASSET_FILES[id] == fmt.tprintf("backdrops/omens/%s.png", ar.STORY_MOTIFS[id].slug), "omen path must derive from its stable corpus slug")
		resolved_count += 1
	}
	for role in ar.Story_Guest_Role_Id {
		asset, known := ar.story_art_texture_for_key(&assets, ar.STORY_GUEST_BACKDROP_ASSET_KEYS[role])
		testing.expect(t, known && asset == ar.story_guest_backdrop_asset(&assets, role), "guest backdrop semantic key must resolve to its typed slot")
		testing.expect(t, ar.STORY_GUEST_BACKDROP_ASSET_KEYS[role] == fmt.tprintf("story.guest.%s", ar.STORY_GUEST_TEMPLATES[role].slug), "guest backdrop key must derive from its stable role slug")
		testing.expect(t, ar.STORY_GUEST_BACKDROP_ASSET_FILES[role] == fmt.tprintf("backdrops/guests/%s.png", ar.STORY_GUEST_TEMPLATES[role].slug), "guest backdrop path must derive from its stable role slug")
		resolved_count += 1
	}
	for archetype in ar.Archetype_Id {
		for verb in ar.Story_Choice_Verb {
			asset, known := ar.story_art_texture_for_key(&assets, ar.STORY_ENDING_PANEL_ASSET_KEYS[archetype][verb])
			testing.expect(t, known && asset == ar.story_ending_panel_asset(&assets, archetype, verb), "ending semantic key must resolve to its typed slot")
			testing.expect(t, ar.STORY_ENDING_PANEL_ASSET_KEYS[archetype][verb] == fmt.tprintf("story.ending.%s.%s", ar.ARCHETYPES[archetype].sprite, ar.STORY_ENDINGS[archetype][verb].slug), "ending key must derive from archetype and ending slugs")
			testing.expect(t, ar.STORY_ENDING_PANEL_ASSET_FILES[archetype][verb] == fmt.tprintf("backdrops/endings/%s/%s.png", ar.ARCHETYPES[archetype].sprite, ar.STORY_ENDINGS[archetype][verb].slug), "ending path must derive from archetype and ending slugs")
			resolved_count += 1
		}
	}
	for relic in ar.Story_Relic_Id {
		asset, known := ar.story_art_texture_for_key(&assets, ar.STORY_RELIC_ICON_ASSET_KEYS[relic])
		testing.expect(t, known && asset == ar.story_relic_icon_asset(&assets, relic), "relic semantic key must resolve to its typed slot")
		testing.expect(t, ar.STORY_RELIC_ICON_ASSET_KEYS[relic] == fmt.tprintf("story.relic.%s", ar.STORY_RELICS[relic].slug), "relic key must derive from its stable corpus slug")
		testing.expect(t, ar.STORY_RELIC_ICON_ASSET_FILES[relic] == fmt.tprintf("icons/relics/%s.png", ar.STORY_RELICS[relic].slug), "relic path must derive from its stable corpus slug")
		resolved_count += 1
	}
	for role in ar.Story_Guest_Role_Id {
		for variant in 0 ..< ar.STORY_GUEST_VARIANTS {
			asset, known := ar.story_art_texture_for_key(&assets, ar.STORY_GUEST_PORTRAIT_ASSET_KEYS[role][variant])
			testing.expect(t, known && asset == ar.story_guest_portrait_asset(&assets, role, variant), "portrait semantic key must resolve to its typed slot")
			testing.expect(t, ar.STORY_GUEST_PORTRAIT_ASSET_KEYS[role][variant] == fmt.tprintf("story.portrait.%s.%s", ar.STORY_GUEST_TEMPLATES[role].slug, ar.STORY_GUEST_TEMPLATES[role].name_slugs[variant]), "portrait key must derive from role/name slugs")
			testing.expect(t, ar.STORY_GUEST_PORTRAIT_ASSET_FILES[role][variant] == fmt.tprintf("portraits/%s/%s.png", ar.STORY_GUEST_TEMPLATES[role].slug, ar.STORY_GUEST_TEMPLATES[role].name_slugs[variant]), "portrait path must derive from role/name slugs")
			resolved_count += 1
		}
	}
	soul, soul_known := ar.story_art_texture_for_key(&assets, ar.STORY_LOSSLESS_SOUL_BACKDROP_KEY)
	testing.expect(t, soul_known && soul == ar.story_lossless_soul_backdrop_asset(&assets), "Lossless Soul backdrop must resolve")
	resolved_count += 1
	for id in ar.Story_Choice_Icon_Id {
		asset, known := ar.story_art_texture_for_key(&assets, ar.STORY_CHOICE_ICON_ASSET_KEYS[id])
		testing.expect(t, known && asset == ar.story_choice_icon_asset(&assets, id), "choice semantic key must resolve to its typed slot")
		testing.expect(t, asset == ar.story_choice_icon_asset_for_key(&assets, ar.STORY_CHOICE_ICON_NAMES[id]), "short panel choice key must resolve to the same icon")
		testing.expect(t, ar.STORY_CHOICE_ICON_ASSET_KEYS[id] == fmt.tprintf("cutscene.choice.icon.%s", ar.STORY_CHOICE_ICON_NAMES[id]), "choice semantic key must retain the legacy panel vocabulary")
		testing.expect(t, ar.STORY_CHOICE_ICON_FILES[id] == fmt.tprintf("icons/choices/%s.png", ar.STORY_CHOICE_ICON_NAMES[id]), "choice icon path must derive from its short panel key")
		resolved_count += 1
	}
	testing.expect(t, resolved_count == ar.STORY_ART_ASSET_COUNT, "every manifest slot must be reachable through a typed accessor")

	unknown, known := ar.story_art_texture_for_key(&assets, "story.unknown")
	testing.expect(t, !known && unknown == &assets.story.fallback && !unknown.valid, "unknown semantic keys must use the zero-value fallback")
	testing.expect(t, ar.story_choice_icon_asset_for_key(&assets, "bell") == &assets.story.fallback, "un-authored panel glyphs remain procedural")
	testing.expect(t, ar.story_guest_portrait_asset(&assets, .Oathless_Knight, -1) == &assets.story.fallback, "invalid portrait variants must not index storage")
	testing.expect(t, ar.story_guest_actor_sprites(&assets) == &assets.story_guest, "story guest actor accessor must expose its dedicated sheet")
	testing.expect(t, ar.lossless_soul_actor_sprites(&assets) == &assets.lossless_soul, "Lossless Soul actor accessor must expose its dedicated sheet")
}

@(test)
mx_story_manifest_format_is_strict_self_contained_and_file_independent :: proc(t: ^testing.T) {
	manifest := story_test_manifest_make()
	defer story_test_manifest_destroy(&manifest)
	testing.expect(t, ar.story_manifest_matches_registry(&manifest), "synthetic expected-path manifest must match the typed registry")

	encoded, marshal_err := json.marshal(manifest, allocator = context.allocator)
	testing.expectf(t, marshal_err == nil, "synthetic story manifest did not marshal: %v", marshal_err)
	if marshal_err == nil {
		testing.expect(t, ar.story_manifest_validate_data(encoded), "strict validator must accept the exact generated schema")
		trailing := fmt.aprintf("%s true", string(encoded))
		testing.expect(t, !ar.story_manifest_validate_data(transmute([]u8)trailing), "trailing JSON values must be rejected")
		delete(trailing)
		delete(encoded)
	}

	wrong_path := story_test_manifest_make()
	first, _ := ar.story_art_def_at(0)
	entry := wrong_path.assets[first.key]
	entry.file = "../outside.png"
	wrong_path.assets[first.key] = entry
	testing.expect(t, !ar.story_manifest_matches_registry(&wrong_path), "traversal/non-canonical paths must be rejected")
	story_test_manifest_destroy(&wrong_path)

	bad_hash := story_test_manifest_make()
	entry = bad_hash.assets[first.key]
	entry.sha256 = "ABCDEFABCDEFABCDEFABCDEFABCDEFABCDEFABCDEFABCDEFABCDEFABCDEFABCD"
	bad_hash.assets[first.key] = entry
	testing.expect(t, !ar.story_manifest_matches_registry(&bad_hash), "checksums must be 64 lowercase hexadecimal digits")
	story_test_manifest_destroy(&bad_hash)

	extra_key := story_test_manifest_make()
	extra_key.assets["story.unexpected"] = {file = "unexpected.png", sha256 = STORY_TEST_SHA256}
	extra_key.asset_count += 1
	testing.expect(t, !ar.story_manifest_matches_registry(&extra_key), "extra semantic keys must be rejected")
	story_test_manifest_destroy(&extra_key)

	unknown_root := Story_Test_Manifest_Unknown_Root {
		format_version = manifest.format_version,
		asset_count = manifest.asset_count,
		assets = manifest.assets,
		unexpected = true,
	}
	encoded_root, root_err := json.marshal(unknown_root, allocator = context.allocator)
	testing.expectf(t, root_err == nil, "unknown-root probe did not marshal: %v", root_err)
	if root_err == nil {
		testing.expect(t, !ar.story_manifest_validate_data(encoded_root), "unknown root fields must be rejected")
		delete(encoded_root)
	}

	unknown_entry := Story_Test_Manifest_Unknown_Entry {
		format_version = ar.STORY_ART_MANIFEST_FORMAT,
		asset_count = ar.STORY_ART_ASSET_COUNT,
		assets = make(map[string]Story_Test_Manifest_Entry_Extra, ar.STORY_ART_ASSET_COUNT),
	}
	for index in 0 ..< ar.STORY_ART_ASSET_COUNT {
		def, _ := ar.story_art_def_at(index)
		unknown_entry.assets[def.key] = {
			file = def.file,
			sha256 = STORY_TEST_SHA256,
			unexpected = index == 0,
		}
	}
	encoded_entry, entry_err := json.marshal(unknown_entry, allocator = context.allocator)
	testing.expectf(t, entry_err == nil, "unknown-entry probe did not marshal: %v", entry_err)
	if entry_err == nil {
		testing.expect(t, !ar.story_manifest_validate_data(encoded_entry), "unknown asset-entry fields must be rejected")
		delete(encoded_entry)
	}
	delete(unknown_entry.assets)
}

@(test)
mx_story_committed_manifest_matches_every_png_and_hash :: proc(t: ^testing.T) {
	data, read_err := os.read_entire_file_from_path("assets/story/manifest.json", context.allocator)
	testing.expect(t, read_err == nil, "committed MX-story manifest is required")
	if read_err != nil do return
	defer delete(data)
	testing.expect(t, ar.story_manifest_validate_data(data), "committed MX-story manifest must satisfy the strict typed schema")

	arena: mem.Dynamic_Arena
	mem.dynamic_arena_init(&arena)
	defer mem.dynamic_arena_destroy(&arena)
	manifest: ar.Story_Art_Manifest
	parse_err := json.unmarshal(
		data,
		&manifest,
		spec = .JSON,
		allocator = mem.dynamic_arena_allocator(&arena),
	)
	testing.expectf(t, parse_err == nil, "committed MX-story manifest does not parse: %v", parse_err)
	if parse_err != nil do return
	testing.expect(t, ar.story_manifest_matches_registry(&manifest), "committed MX-story manifest must match every typed key and canonical path")

	verified := 0
	for index in 0 ..< ar.STORY_ART_ASSET_COUNT {
		def, def_found := ar.story_art_def_at(index)
		testing.expectf(t, def_found, "story art slot %v does not resolve", index)
		if !def_found do continue
		entry, entry_found := manifest.assets[def.key]
		testing.expectf(t, entry_found, "manifest is missing %v", def.key)
		if !entry_found do continue

		path := fmt.aprintf("assets/story/%s", entry.file)
		png, png_err := os.read_entire_file_from_path(path, context.allocator)
		testing.expectf(t, png_err == nil, "%v references missing PNG %v", def.key, path)
		if png_err == nil {
			size, png_ok := story_test_png_size(png)
			testing.expectf(t, png_ok, "%v is not a canonical PNG", path)
			if png_ok {
				switch def.usage {
				case .Icon:
					testing.expectf(t, size == [2]int{32, 32}, "%v icon dimensions are %v, expected 32x32", path, size)
				case .Portrait:
					testing.expectf(t, size[0] >= 48 && size[0] <= 256 && size[1] >= 64 && size[1] <= 256, "%v portrait dimensions are unreasonable: %v", path, size)
				case .Backdrop:
					testing.expectf(t, size == [2]int{640, 360}, "%v backdrop dimensions are %v, expected 640x360", path, size)
				}
			}
			hash_hex := story_test_sha256_hex(png)
			testing.expectf(t, string(hash_hex[:]) == entry.sha256, "%v sha256 does not match committed bytes", path)
			delete(png)
			verified += 1
		}
		delete(path)
	}
	testing.expectf(t, verified == ar.STORY_ART_ASSET_COUNT, "verified %v story PNGs, expected %v", verified, ar.STORY_ART_ASSET_COUNT)
}

@(test)
mx_story_existing_actor_sheets_match_loader_contract :: proc(t: ^testing.T) {
	data, read_err := os.read_entire_file_from_path("assets/actors/manifest.json", context.allocator)
	testing.expect(t, read_err == nil, "existing actor manifest is required")
	if read_err != nil do return
	defer delete(data)

	arena: mem.Dynamic_Arena
	mem.dynamic_arena_init(&arena)
	defer mem.dynamic_arena_destroy(&arena)
	manifest: Story_Test_Actor_Manifest
	parse_err := json.unmarshal(
		data,
		&manifest,
		spec = .JSON,
		allocator = mem.dynamic_arena_allocator(&arena),
	)
	testing.expectf(t, parse_err == nil, "actor manifest does not parse: %v", parse_err)
	if parse_err != nil do return
	testing.expect(t,manifest.format==2&&manifest.native_cells,"story actors require the native-resolution actor pack")

	expected := [3]struct {
		name:  string,
		cell:  int,
		clips: []string,
	}{
		{"story_guest", 180, []string{"idle", "walk", "dance"}},
		{"lossless_soul", 244, []string{"walk", "dance"}},
		{"mistbound_ghost", 156, []string{"idle"}},
	}
	for actor_expected in expected {
		actor, found := manifest.actors[actor_expected.name]
		testing.expectf(t, found, "actor manifest is missing %v", actor_expected.name)
		if !found do continue
		testing.expectf(t,actor.cell==actor_expected.cell&&actor.source_canvas==[2]int{actor.cell,actor.cell}&&actor.canvas_world>0,"%v actor was not preserved at its native %vpx resolution",actor_expected.name,actor_expected.cell)
		testing.expect(t, actor.anchor[0] > 0 && actor.anchor[1] > 0, "story actor anchor must be populated")
		testing.expectf(t, len(actor.clips) == len(actor_expected.clips), "%v clip inventory changed", actor_expected.name)
		for clip_name in actor_expected.clips {
			clip, clip_found := actor.clips[clip_name]
			testing.expectf(t, clip_found, "%v is missing %v", actor_expected.name, clip_name)
			if !clip_found do continue
			testing.expectf(t,clip.frames>0&&clip.rows==8&&clip.fps>0&&clip.loop&&len(clip.sha256)==64,"%v/%v native clip metadata is invalid",actor_expected.name,clip_name)
			path := fmt.aprintf("assets/actors/%s/%s.png", actor_expected.name, clip_name)
			png, png_err := os.read_entire_file_from_path(path, context.allocator)
			testing.expectf(t, png_err == nil, "%v references missing actor sheet %v", actor_expected.name, path)
			if png_err == nil {
				size, png_ok := story_test_png_size(png)
				testing.expectf(t, png_ok, "%v is not a canonical PNG", path)
				if png_ok {
					testing.expectf(t, size == [2]int{clip.frames * actor.cell, 8 * actor.cell}, "%v dimensions %v do not match %v frames x 8 directions at %vpx", path, size, clip.frames, actor.cell)
				}
				delete(png)
			}
			delete(path)
		}
	}
}

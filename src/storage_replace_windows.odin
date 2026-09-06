#+build windows

package archrogue

import win32 "core:sys/windows"

// MoveFileExW with WRITE_THROUGH does not return until the replacement has
// reached durable storage. Save artifacts always share one application-data
// directory, so this also preserves atomic same-volume replacement semantics.
storage_replace_write_through :: proc(source, destination: string) -> bool {
	// The conversion helper defaults to temp_allocator; these buffers are
	// explicitly freed below, so allocate them from the matching allocator.
	source_w := win32.utf8_to_utf16_alloc(source, context.allocator)
	defer delete(source_w)
	destination_w := win32.utf8_to_utf16_alloc(destination, context.allocator)
	defer delete(destination_w)
	if len(source_w) == 0 || len(destination_w) == 0 do return false
	flags := win32.MOVEFILE_REPLACE_EXISTING | win32.MOVEFILE_WRITE_THROUGH
	if win32.MoveFileExW(
		cstring16(raw_data(source_w)),
		cstring16(raw_data(destination_w)),
		flags,
	) {
		return true
	}
	return false
}

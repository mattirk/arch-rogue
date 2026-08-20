#+build !freestanding
package archrogue

import "core:c"
import "core:strings"
@(require)
import "core:sys/posix"

// Deliberately-quiet imports: every use sits inside the ARCH_ROGUE_ANDROID
// block, so plain desktop builds would otherwise flag them unused.
_ :: c
_ :: strings
_ :: posix

// Odin dev-2026-07 routes the Android subtarget through core:thread's Unix
// trampoline, which enables asynchronous POSIX cancellation before entering a
// thread procedure. Bionic intentionally omits pthread cancellation. Arch Rogue
// workers stop cooperatively through their bounded queue and are always joined,
// so cancellation state/type have no observable role. Export successful no-ops
// only for Android rather than weakening the desktop thread implementation.
when ARCH_ROGUE_ANDROID {

	platform_android_create_private_directory :: proc(path: string) -> bool {
		if path == "" do return false
		return posix.mkdir(
			strings.clone_to_cstring(path, context.temp_allocator),
			posix.S_IRWXU,
		) == .OK
	}

	platform_android_read_file_exact :: proc(path: string, destination: []byte) -> bool {
		if path == "" do return false
		fd := posix.open(
			strings.clone_to_cstring(path, context.temp_allocator),
			{.CLOEXEC},
		)
		if fd < 0 do return false
		ok := true
		offset: uint = 0
		for offset < len(destination) {
			count := posix.read(
				fd,
				raw_data(destination[offset:]),
				c.size_t(len(destination) - offset),
			)
			if count <= 0 {
				ok = false
				break
			}
			offset += uint(count)
		}
		if posix.close(fd) != .OK do ok = false
		return ok
	}

	platform_android_write_file_synced :: proc(path: string, data: []byte) -> bool {
		if path == "" do return false
		fd := posix.open(
			strings.clone_to_cstring(path, context.temp_allocator),
			{.WRONLY,.CREAT,.TRUNC,.CLOEXEC},
			{.IRUSR,.IWUSR},
		)
		if fd < 0 do return false
		ok := true
		offset: uint = 0
		for offset < len(data) {
			count := posix.write(
				fd,
				raw_data(data[offset:]),
				c.size_t(len(data) - offset),
			)
			if count <= 0 {
				ok = false
				break
			}
			offset += uint(count)
		}
		if ok && posix.fsync(fd) != .OK do ok = false
		if posix.close(fd) != .OK do ok = false
		return ok
	}

	platform_android_sync_directory :: proc(path: string) -> bool {
		if path == "" do return false
		fd := posix.open(
			strings.clone_to_cstring(path, context.temp_allocator),
			{.DIRECTORY,.CLOEXEC},
		)
		if fd < 0 do return false
		ok := posix.fsync(fd) == .OK
		if posix.close(fd) != .OK do ok = false
		return ok
	}

	platform_android_remove_file :: proc(path: string) -> bool {
		if path == "" do return false
		return posix.unlink(strings.clone_to_cstring(path, context.temp_allocator)) == .OK
	}

	platform_android_replace_file :: proc(source, destination: string) -> bool {
		if source == "" || destination == "" do return false
		return posix.rename(
			strings.clone_to_cstring(source, context.temp_allocator),
			strings.clone_to_cstring(destination, context.temp_allocator),
		) == 0
	}

	@(export, link_name="pthread_setcancelstate")
	platform_android_pthread_setcancelstate :: proc "c" (_: c.int, _: ^c.int) -> c.int {
		return 0
	}

	@(export, link_name="pthread_setcanceltype")
	platform_android_pthread_setcanceltype :: proc "c" (_: c.int, _: ^c.int) -> c.int {
		return 0
	}
}

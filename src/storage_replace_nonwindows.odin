#+build !windows

package archrogue

@(require)
import "core:os"

// POSIX rename replaces the destination atomically on the same filesystem.
// main.odin syncs the containing directory after every metadata transition.
storage_replace_write_through :: proc(source, destination: string) -> bool {
	when ARCH_ROGUE_ANDROID do return platform_android_replace_file(source,destination)
	return os.rename(source, destination) == nil
}

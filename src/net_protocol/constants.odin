// Shared Arch Rogue multiplayer protocol v4: constants, strict JSON, and the
// relay-facing control messages. Imported by the game and the relay; it must
// stay free of raylib, the game package, transports, and OS-only APIs.
package net_protocol

PROTOCOL_VERSION :: 4
SUBPROTOCOL      :: "arch-rogue.v4"
WS_PATH          :: "/mp"
HEALTH_PATH      :: "/healthz"

// One UTF-8 JSON object per WebSocket text message, counted in bytes.
MAX_MESSAGE_BYTES :: 256 * 1024

// Room codes are locators, not credentials: no 0/O/1/I so a code read aloud
// is unambiguous (arch-rogue-python/src/arch_rogue_protocol/wire.py).
ROOM_CODE_ALPHABET :: "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
ROOM_CODE_LENGTH   :: 4

NAME_MAX_CODEPOINTS :: 16
NAME_MAX_BYTES      :: NAME_MAX_CODEPOINTS * 4
GAME_ID_MAX_BYTES   :: 48
TOKEN_BYTES         :: 16 // 128 random bits
TOKEN_HEX_LENGTH    :: TOKEN_BYTES * 2
ERROR_MSG_MAX_BYTES :: 200

// Relay timing defaults carried forward from arch-rogue-python/server/config.py.
HELLO_TIMEOUT_MS       :: 10_000
RECONNECT_GRACE_MS     :: 30_000
ROOM_IDLE_TIMEOUT_MS   :: 600_000
HEARTBEAT_INTERVAL_MS  :: 5_000
LIVENESS_TIMEOUT_MS    :: 15_000
RESULT_DELIVERY_MS     :: 30_000
CONNECT_BUDGET_MS      :: 6_000
RECONNECT_BACKOFF_MIN_MS :: 500
RECONNECT_BACKOFF_MAX_MS :: 4_000
MAX_ROOMS              :: 128

SNAPSHOT_HZ :: 30
INTENT_HZ   :: 30

Role :: enum u8 {
	None,
	Host,
	Join,
}

ROLE_NAMES := [Role]string{
	.None = "",
	.Host = "host",
	.Join = "join",
}

// Stable room-local player identity: the host simulates p1, the joiner is p2.
PLAYER_IDS := [Role]string{
	.None = "",
	.Host = "p1",
	.Join = "p2",
}

// Symbolic content ids validated by both relay and clients. The game maps
// these onto its enums; tests pin the correspondence.
ARCHETYPE_KEYS := [5]string{"warden", "rogue", "arcanist", "acolyte", "ranger"}
DIFFICULTY_KEYS := [4]string{"easy", "medium", "hard", "hell"}

// Frozen verification-seal vocabulary and order from
// arch-rogue-python/src/arch_rogue/constants.py (SHARED_SIGIL_NAMES). Changing
// it changes every seal; it catches mistyped codes and is not authentication.
SEAL_SIGILS := [18]string{
	"serpent", "hammer", "skull", "star", "cross", "flame", "key", "map", "shield",
	"sword", "claw", "sun", "moon", "dragon", "phoenix", "ouroboros", "clock", "infinity",
}

Error_Code :: enum u8 {
	None,
	Run_Id_In_Use,
	Run_Not_Found,
	Run_Full,
	Server_Full,
	Bad_Version,
	Bad_Revision,
	Bad_Msg,
	Bad_State,
	Role_Forbidden,
	Timeout,
	Kicked,
	Rate_Limited,
	Host_Left,
}

ERROR_CODE_NAMES := [Error_Code]string{
	.None           = "",
	.Run_Id_In_Use  = "run_id_in_use",
	.Run_Not_Found  = "run_not_found",
	.Run_Full       = "run_full",
	.Server_Full    = "server_full",
	.Bad_Version    = "bad_version",
	.Bad_Revision   = "bad_revision",
	.Bad_Msg        = "bad_msg",
	.Bad_State      = "bad_state",
	.Role_Forbidden = "role_forbidden",
	.Timeout        = "timeout",
	.Kicked         = "kicked",
	.Rate_Limited   = "rate_limited",
	.Host_Left      = "host_left",
}

error_code_from_name :: proc(name: string) -> (Error_Code, bool) {
	for text, code in ERROR_CODE_NAMES {
		if code != .None && text == name do return code, true
	}
	return .None, false
}

archetype_key_valid :: proc(key: string) -> bool {
	for k in ARCHETYPE_KEYS do if k == key do return true
	return false
}

difficulty_key_valid :: proc(key: string) -> bool {
	for k in DIFFICULTY_KEYS do if k == key do return true
	return false
}

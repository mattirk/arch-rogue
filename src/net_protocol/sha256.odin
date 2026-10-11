package net_protocol

// Pure-Odin SHA-256 shared by the room-code seal, checkpoint digests, and the
// game's save checksums. Deliberately not core:crypto/hash: Odin's ARM
// hardware SHA path uses NEON SHA intrinsics that cannot be lowered for the
// Android armeabi-v7a target (observed in CI 2026-10-11), and these call sites
// need no acceleration.

import "core:math/bits"

@(private = "file")
SHA256_INITIAL := [8]u32{
	0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
	0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19,
}

@(private = "file")
SHA256_ROUND := [64]u32{

	0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5,
	0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
	0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3,
	0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
	0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc,
	0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
	0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7,
	0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
	0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13,
	0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
	0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3,
	0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
	0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5,
	0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
	0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208,
	0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
}

@(private = "file")
sha256_transform :: proc(state: ^[8]u32, block: []byte) {
	words: [64]u32
	for i in 0 ..< 16 {
		offset := i * 4
		words[i] = u32(block[offset]) << 24 | u32(block[offset+1]) << 16 |
			u32(block[offset+2]) << 8 | u32(block[offset+3])
	}
	for i in 16 ..< 64 {
		x := words[i-15]
		y := words[i-2]
		sigma0 := bits.rotate_left32(x, 25) ~ bits.rotate_left32(x, 14) ~ (x >> 3)
		sigma1 := bits.rotate_left32(y, 15) ~ bits.rotate_left32(y, 13) ~ (y >> 10)
		words[i] = words[i-16] + sigma0 + words[i-7] + sigma1
	}

	a, b, c, d := state[0], state[1], state[2], state[3]
	e, f, g, h := state[4], state[5], state[6], state[7]
	for i in 0 ..< 64 {
		sum1 := bits.rotate_left32(e, 26) ~ bits.rotate_left32(e, 21) ~ bits.rotate_left32(e, 7)
		choose := g ~ (e & (f ~ g))
		temp1 := h + sum1 + choose + SHA256_ROUND[i] + words[i]
		sum0 := bits.rotate_left32(a, 30) ~ bits.rotate_left32(a, 19) ~ bits.rotate_left32(a, 10)
		majority := (a & b) ~ (a & c) ~ (b & c)
		temp2 := sum0 + majority
		h, g, f, e, d, c, b, a = g, f, e, d + temp1, c, b, a, temp1 + temp2
	}
	state[0] += a
	state[1] += b
	state[2] += c
	state[3] += d
	state[4] += e
	state[5] += f
	state[6] += g
	state[7] += h
}

sha256_digest :: proc(data: []byte) -> (digest: [32]byte) {
	state := SHA256_INITIAL
	offset := 0
	for len(data)-offset >= 64 {
		sha256_transform(&state, data[offset:offset+64])
		offset += 64
	}

	block: [64]byte
	remaining := len(data)-offset
	copy(block[:remaining], data[offset:])
	block[remaining] = 0x80
	if remaining >= 56 {
		sha256_transform(&state, block[:])
		block = {}
	}
	bit_length := u64(len(data)) * 8
	for i in 0 ..< 8 do block[63-i] = byte(bit_length >> u64(i*8))
	sha256_transform(&state, block[:])
	for word, i in state {
		digest[i*4] = byte(word >> 24)
		digest[i*4+1] = byte(word >> 16)
		digest[i*4+2] = byte(word >> 8)
		digest[i*4+3] = byte(word)
	}
	return digest
}

sha256_hex :: proc(data: []byte, allocator := context.allocator) -> string {
	digest := sha256_digest(data)
	hex := "0123456789abcdef"
	out := make([]byte, 64, allocator)
	for b, i in digest {
		out[i*2] = hex[b >> 4]
		out[i*2+1] = hex[b & 0xf]
	}
	return string(out)
}

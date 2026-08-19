package archrogue

// Seeded PCG32 streams (hard rule 4): every piece of gameplay randomness
// flows from a run seed through derive_seed, never from global state.
// Same-seed runs must replay identically.

Pcg32 :: struct {
	state: u64,
	inc:   u64,
}

rng_make :: proc(seed: u64, stream: u64 = 0) -> Pcg32 {
	rng := Pcg32{0, (stream << 1) | 1}
	_ = rng_next(&rng)
	rng.state += seed
	_ = rng_next(&rng)
	return rng
}

// PCG-XSH-RR 64/32.
rng_next :: proc(rng: ^Pcg32) -> u32 {
	old := rng.state
	rng.state = old * 6364136223846793005 + rng.inc
	xorshifted := u32(((old >> 18) ~ old) >> 27)
	rot := u32(old >> 59)
	return (xorshifted >> rot) | (xorshifted << ((32 - rot) & 31))
}

// Uniform [0, n) without modulo bias (PCG reference rejection method).
rng_below :: proc(rng: ^Pcg32, n: int) -> int {
	assert(n > 0)
	bound := u32(n)
	threshold := (0 - bound) % bound
	for {
		v := rng_next(rng)
		if v >= threshold {
			return int(v % bound)
		}
	}
}

// Uniform [lo, hi), mirroring Python's randrange so ported call sites read 1:1.
rng_range :: proc(rng: ^Pcg32, lo, hi: int) -> int {
	return lo + rng_below(rng, hi - lo)
}

// Uniform [0, 1) with 24 bits of precision.
rng_f32 :: proc(rng: ^Pcg32) -> f32 {
	return f32(rng_next(rng) >> 8) * (1.0 / 16777216.0)
}

rng_chance :: proc(rng: ^Pcg32, p: f32) -> bool {
	return rng_f32(rng) < p
}

splitmix64 :: proc(x: u64) -> u64 {
	z := x + 0x9E3779B97F4A7C15
	z = (z ~ (z >> 30)) * 0xBF58476D1CE4E5B9
	z = (z ~ (z >> 27)) * 0x94D049BB133111EB
	return z ~ (z >> 31)
}

// Derived stream seeds: run seed -> per-floor / per-system seeds.
derive_seed :: proc(seed: u64, salt: u64) -> u64 {
	return splitmix64(seed ~ splitmix64(salt))
}

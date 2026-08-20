# Arch Rogue Android launcher icon

The approved launcher art is `arch_rogue_launcher_512.png`. It combines the
selected PixelLab etched-rune medallion from review job
`40d8d1ca-a128-4821-982b-d3e8e8c2cb6a` with the canonical first relic frame from
`assets/ui/logo/diamond_atlas.png`. The relic is uniformly scaled from its
trimmed `70x72` source to `60x62`, preserving the title logo's aspect ratio.
Pixels outside that centered relic overlay remain the original generated
medallion.

`arch_rogue_launcher_circle_128.png` preserves the generated circular cutout.
`arch_rogue_launcher_foreground_512.png` is the safe-zone-scaled transparent
adaptive-icon foreground. Density-specific Android resources are generated from
these sources with nearest-neighbor scaling to preserve the authored pixel art.

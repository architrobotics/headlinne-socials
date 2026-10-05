"""The studio reel: Pip on a built set, with cut-paper overlays on top.

Added in Oct 2026 when the founder sent four reels from @nocodealex and asked
for that look, with real-world news in place of the AI-tool topics and Pip in
place of the pixel mascot those reels use. What the reference does, and what
each module here is responsible for:

  voxel      the mascot as a blocky papercraft figure standing in the scene,
             not a flat sprite on blank paper. Pip's pixel grid is extruded
             into blocks, so every existing pose and prop carries over.
  sets       a full-bleed diorama behind every beat - a room, a street, a
             harbour, a map table - lit warm, with depth of field. The set
             changes when the chapter changes.
  overlay    the furniture laid over the set: a title on a crumpled strip of
             paper taped at both corners, a stat card with a counting figure,
             the spoken words one to three at a time on torn paper chips, a
             TV-style lower third, a rubber stamp, a comment box to close.
  direction  the per-reel art direction. The script writer picks a set, props
             and a costume for every beat from a closed vocabulary; this
             validates the choice and fills anything missing from the story
             itself, so no two reels are dressed the same and none is ever
             undressed.
  frames     the frame renderer, with the same interface as render.reel's
             ReelFrames so the geometry gate, the cover and the encoder do
             not care which style drew the reel.

The flat paper style is still there behind REEL_STYLE=paper.
"""

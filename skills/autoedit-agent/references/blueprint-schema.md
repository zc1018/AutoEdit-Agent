# Editor-neutral blueprint 2.0

UTF-8 JSON. All times are **seconds**, all output visual boundaries align to the
chosen integer FPS. Source paths are local, absolute or relative to this JSON.
Supported source video FPS can differ: FFmpeg normalizes it to the output FPS.

```json
{
  "schema_version": "2.0",
  "backend": "auto",
  "project": {"name": "Example", "fps": 30, "width": 1920, "height": 1080},
  "clips": [
    {
      "id": "shot-1", "media_type": "video", "source_path": "media/camera.mp4",
      "source_in_seconds": 2, "source_out_seconds": 7,
      "timeline_in_seconds": 0, "timeline_out_seconds": 5,
      "speed": 1, "volume": 1, "fit": "pad",
      "purpose": "Establish the scene", "confidence": 0.9
    },
    {
      "id": "image-1", "media_type": "image", "source_path": "media/photo.jpg",
      "timeline_in_seconds": 5, "timeline_out_seconds": 8,
      "purpose": "Explain the result"
    },
    {
      "id": "narration-1", "media_type": "audio", "source_path": "media/voice.wav",
      "source_in_seconds": 0, "source_out_seconds": 6,
      "timeline_in_seconds": 1, "timeline_out_seconds": 7,
      "volume": 1, "fade_in_seconds": 0.1, "fade_out_seconds": 0.2
    }
  ],
  "captions": [{"start_seconds": 1, "end_seconds": 4, "text": "An evidence-based caption"}],
  "notes": []
}
```

## Contract

`project`: nonempty `name`; integer `fps` (1–120, default 30); even positive
`width`/`height` up to 8192 (defaults 1920×1080). Fractional output frame rates are
not supported by this shared v2 subset; choose an integer output FPS explicitly.

`clips`: unique string `id`; `media_type` is `video`, `image`, or `audio`;
`source_path`; `timeline_in_seconds` and `timeline_out_seconds`. Source bounds
are required for video/audio. `(source_out-source_in)/speed` must equal timeline
duration within 0.001 seconds. Range checking uses FFprobe, not user-provided duration.
Minimum clip duration is 0.001 seconds; visual clips also need frame-aligned boundaries.

Defaults: speed=1 (range 0.25–4), volume=1 (range 0–8; 0 mutes), fit=`pad`,
fade_in_seconds=0 and fade_out_seconds=0. Fades affect AUDIO, not the picture;
they cannot overlap. Images have no source out-point, no speed change and no audio
fades; their duration is explicitly their target timeline range.

Visual clips form ONE continuous, nonoverlapping track starting at zero. The last
visual out-point defines delivery duration. Audio clips may overlap and start
independently, but must finish within the visual timeline. This supports BGM,
voiceover and sound effects; independent audio placement can implement planned
J/L cuts. Loops are explicit repeated audio clips, not an implicit forever-loop.

`captions`: sorted nonoverlapping objects with `start_seconds`, `end_seconds`,
`text`; each duration >= 0.001 seconds and within the visual timeline. SRT is
written in UTF-8. No blank lines inside one cue. No animation/style claims.

Optional editorial metadata per clip: `purpose`, `source_group`, `confidence`,
`notes`. These guide human/agent review; the renderer does not invent a shot,
infer confidence, or apply an effect from prose. Unknown executable fields fail
validation instead of disappearing. `fit=crop` means a CENTER crop in FFmpeg.
The Jianying adapter accepts only `pad`; check actual framing in its GUI.

## Migrating old Resolve 1.0 blueprints

Do not merely rename the schema and assume all operations survived.
1. Retain `project.name/fps/width/height`; remove `target_duration_seconds` and
   compare its intended duration with the new last visual out-point yourself.
2. Retain compatible clip source/target ranges and editorial metadata. Remove
   `video_track`/`audio_track`; explicitly flatten visuals only if no composition
   is lost. There is no automatic multi-track-to-one-track conversion.
3. Move narration/music entries into `clips` as explicit `media_type: audio`,
   with unique IDs, source ranges, target ranges and volume. Use real file lengths.
4. Convert captions to the shape above. Remove the old `tracks`, `narration` and
   `music` root keys. Set `schema_version` to `2.0` and validate with source probing.
5. Document Resolve-only operations as manual work or revise the plan with approval.
   A LUT, transition or stabilization request is NOT silently carried over.

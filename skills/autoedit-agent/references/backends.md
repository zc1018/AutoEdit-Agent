# Backends and delivery boundaries

| Capability | FFmpeg | Jianying adapter |
|---|---|---|
| Needs DaVinci Resolve / MCP | No | No |
| Result | H.264/AAC MP4, SRT, normalized blueprint, audit | New native draft, SRT, blueprint, audit |
| Editing model | Single visual sequence, cuts and stills | Native V1 with separately editable clips |
| Additional audio | Timed mixing, volume, audio fades | Separate native audio tracks, volume, fades |
| Speed | Constant 0.25–4, pitch-preserving atempo | Native retiming from source/target ranges |
| Framing | Center pad or crop, normalized canvas | Native default fitting; `pad` only |
| Captions | Soft MP4 track + SRT; optional libass burn-in | Native text segments + SRT |
| Automatic export | Yes, headless | Not implemented or promised |
| Runtime | Python 3.10+, ffmpeg, ffprobe | Python 3.10+, ffprobe, pyJianYingDraft 0.3.0 and its dependencies |

Both honor source selection and timing, but they are not pixel-identical renderers.
FFmpeg mixes without automatic normalization and applies a final peak limiter;
Jianying needs a listening check of its native mix. Color management, HDR tone
mapping, multicamera composition, transitions, LUTs, stabilization and advanced
keyframing are outside this implementation. Do not promise their automatic preservation.
The encoded FFmpeg output is yuv420p SDR-oriented; HDR sources need an explicitly
approved color workflow rather than an unverified HDR delivery claim.

## Jianying compatibility

This adapter targets **new Windows Jianying drafts**, not editing existing protected
drafts, not CapCut, and not an assured native macOS Jianying format. Upstream says
Linux/macOS can generate drafts but those drafts are intended for Windows Jianying
export. Newer app versions also restrict the upstream UI export mechanism. This
project deliberately does not use that UI mechanism.

Generated files are staging deliverables. Copy the complete `draft_directory`
reported by the command to the Windows app's configured draft root. Preserve the
absolute source-media paths or relink media on the receiving machine. There is
no automatic media bundling, app launch, draft-list refresh, or export button click.
Never replace an existing draft folder. Use a versioned new name.

A successful `draft_content.json` readback is **not** GUI compatibility testing.
Open it in the actual target app, inspect trims/retiming/audio/text/framing, and
export there. Record the app version and any incompatibility; do not silently
switch to FFmpeg unless the user authorizes the change.

## Verification reference

- FFmpeg documentation: https://ffmpeg.org/ffmpeg-filters.html
- pyJianYingDraft API and compatibility: https://github.com/GuanYixuan/pyJianYingDraft
- Pinned optional release: https://pypi.org/project/pyJianYingDraft/0.3.0/
- Agent Skills layout: https://agentskills.io/specification

Checked during the editor-neutral refactor, 2026-09-22. Upstream and app behavior
can change; the runtime doctor is not a guarantee of app-version compatibility.

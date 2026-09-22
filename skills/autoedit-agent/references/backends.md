# Backends and delivery boundaries

| Capability | FFmpeg | macOS Jianying adapter |
|---|---|---|
| Needs DaVinci Resolve / MCP | No | No |
| Result | H.264/AAC MP4, SRT, normalized blueprint, audit | macOS draft (`draft_info.json`), bundled `Resources/`, SRT, blueprint, audit |
| Editing model | Single visual sequence, cuts and stills | Native V1 with separately editable clips |
| Additional audio | Timed mixing, volume, audio fades | Separate native audio tracks, volume, fades |
| Speed | Constant 0.25–4, pitch-preserving atempo | Native retiming from source/target ranges |
| Framing | Center pad or crop, normalized canvas | Native default fitting; `pad` only |
| Captions | Soft MP4 track + SRT; optional libass burn-in | Native text segments + SRT |
| Automatic export | Yes, headless | Not implemented or promised |
| Runtime | Python 3.10+, ffmpeg, ffprobe | macOS + Python 3.10+, ffprobe, pyJianYingDraft 0.3.0 and its dependencies |

Both honor source selection and timing, but they are not pixel-identical renderers.
FFmpeg mixes without automatic normalization and applies a final peak limiter;
Jianying needs a listening check of its native mix. Color management, HDR tone
mapping, multicamera composition, transitions, LUTs, stabilization and advanced
keyframing are outside this implementation. Do not promise their automatic preservation.
The encoded FFmpeg output is yuv420p SDR-oriented; HDR sources need an explicitly
approved color workflow rather than an unverified HDR delivery claim.

## Jianying compatibility

This adapter targets **new macOS Jianying Pro desktop drafts**. It deliberately does
not target Windows Jianying, CapCut, existing encrypted/protected drafts, or automatic
GUI export. The upstream serializer is used only as a base timeline writer; AutoEdit
then converts staging output to the Mac entry filename `draft_info.json`, marks the
platform as `mac`, rebuilds media-pool records, and copies referenced media into
`Resources/` so Jianying's macOS sandbox can access them.

The default target library is `~/Movies/JianyingPro/User Data/Projects/com.lveditor.draft`.
Override it with `JY_DRAFT_ROOT` or `--draft-root`. The command still writes a NEW
staging delivery rather than mutating Jianying's library or `root_meta_info.json`;
with Jianying closed, copy the complete reported draft directory into the target root
and reopen/refresh the app. Never replace an existing draft folder.

A successful `draft_info.json` readback is **not** macOS GUI compatibility testing.
Open it in the actual target app, inspect trims/retiming/audio/text/framing, and
export there. Record the app version and any incompatibility; do not silently
switch to FFmpeg unless the user authorizes the change.

## Verification reference

- FFmpeg documentation: https://ffmpeg.org/ffmpeg-filters.html
- pyJianYingDraft base serializer: https://github.com/GuanYixuan/pyJianYingDraft
- macOS modern-draft compatibility reference: https://github.com/luoluoluo22/jianying-editor-skill
- macOS draft structure / sandbox reference: https://github.com/Vincentwei1021/video-shotcraft
- Pinned optional release: https://pypi.org/project/pyJianYingDraft/0.3.0/
- Agent Skills layout: https://agentskills.io/specification

Checked during the editor-neutral refactor, 2026-09-22. Upstream and app behavior
can change; the runtime doctor is not a guarantee of app-version compatibility.

---
name: autoedit-agent
description: End-to-end, source-safe video editing with a user-selected FFmpeg or Jianying backend, without DaVinci Resolve or MCP. Use for footage review, vlog and documentary editing, scripts, optional narration, timestamped edit blueprints, direct MP4 rendering, editable Jianying drafts, delivery audits, and pickup-shot recommendations.
---

# AutoEdit Agent

Turn real user-selected footage into an approved story, an editor-neutral blueprint,
and an audited deliverable. Never require DaVinci Resolve, its license, its API,
or an MCP server. All commands below run relative to THIS skill directory;
resolve its absolute path when the working directory differs.

## Select the deliverable first

- `ffmpeg`: default when unspecified; render `final.mp4` without opening a GUI.
- `jianying`: explicitly requested editable Windows Jianying draft; requires the
  optional `pyJianYingDraft` package. It does not mean automatic app export.
- `auto`: deterministically selects FFmpeg, never guesses from installed apps.

Honor a user's explicit backend. If it is unavailable, explain the missing
component; do not silently substitute another backend. A blueprint alone remains
possible, but label it as planning rather than a finished edit.

Read `references/backends.md` before choosing an implementation. CapCut and
macOS-native Jianying project compatibility are NOT claimed.

## Intake and approvals

Explain the flow briefly: inspect media → review evidence → script → optional
narration → blueprint → selected backend → audit → missing-shot advice.
Collect only missing media paths, topic, audience/platform, duration, aspect ratio,
output location, pacing preferences, narration policy, and backend. Do not impose
travel, a particular camera, a topic, or a voice. Reuse answers already provided.

Read-only inspection needs no repeated permission. Get approval for the creative
brief/story, then the blueprint, then the exact new output path before building.
The user may explicitly approve several stages together. API uploads, billable
calls, voice cloning and source derivatives require authorization. A build command's
`--approve` represents a real approval, not permission the agent may invent.

Never overwrite source media, existing output directories, or an existing draft.
Use a new versioned run directory for revisions. Do not delete previous deliveries.

## 1. Check and inventory

```bash
python scripts/autoedit.py doctor --backend ffmpeg
python scripts/autoedit.py scan --input "<media-folder>" --input "<music-folder>" --output "<existing-run>/media-manifest.json"
```

Scan accepts common video/audio/image files. A manifest is metadata, NOT visual
analysis or a transcript. Report unreadable files; don't discard entire cameras
or folders based on a few samples. Original sources are read-only.

After permission to create derivatives:

```bash
python scripts/autoedit.py extract --manifest "<run>/media-manifest.json" --output "<new-run-frames-dir>" --every 10 --max-per-video 24
```

Sampling covers the full source duration, not just the opening. Inspect frames
with the agent's available vision, and listen/transcribe only with authorized tools.
If more coverage is needed, extract additional intervals; do not invent content
between sample points. With no vision tool, provide a manual review worksheet.

Optional cloud analysis and TTS remain independent of the editor. Read
`references/configuration.md`. Never upload media or read a voice sample into an
API request just because environment variables exist.

## 2. Review, write, and decide narration

Create a timestamped evidence map: source, people/action, dialogue, story use,
technical risks, confidence, and unanswered factual questions. Review actual
footage rather than treating model labels as facts. Preview before saving.

Use the bundled `viral-video-writer` when installed, or write from the evidence map:
one core idea, possible structures, hook, development, payoff, voice and pacing.
Confirm the script. TTS is optional; existing narration, dialogue, music, captions,
or silence are valid. Never manufacture a real person's words or unseen events.

Narration and BGM become ordinary `media_type: audio` clips in the blueprint,
using the actual probed audio durations. Do not estimate timing from text length.

## 3. Make the editor-neutral blueprint

Read `references/blueprint-schema.md`. Use schema 2.0, local source paths, source
and timeline seconds. Every chosen shot should include its `purpose` and evidence
confidence. Vary shots when justified; do not fill unsupported script claims with
unrelated footage. Explicitly approve any crop, retiming, music, or muted audio.

Supported execution: one contiguous visual track with cuts, still images, timed
overlapping audio clips, volume/audio fades, constant speed changes and captions.
FFmpeg also supports center crop and burned subtitles. Do not add unsupported
transition/LUT/stabilization/PIP fields and assume they will run. Simplify with
approval or identify precise manual work in the editor.

```bash
python scripts/autoedit.py validate "<blueprint.json>"
python scripts/autoedit.py build "<blueprint.json>" --backend ffmpeg --output "<new-delivery-dir>" --dry-run
```

`validate --no-probe` checks structure only and is NOT a source-availability audit.
`--dry-run` probes sources but writes no files; inspect readiness and the actual
output path before seeking approval. Relative media paths resolve from the
blueprint's directory, not the current shell directory.

## 4. Execute only the selected backend

Direct FFmpeg output:

```bash
python scripts/autoedit.py build "<blueprint.json>" --backend ffmpeg --output "<new-delivery-dir>" --approve
```

Add `--burn-captions` only when permanent captions are desired and local libass
and suitable fonts are present; otherwise captions are an SRT sidecar and MP4
soft-subtitle track. Explain that some players do not automatically show soft subtitles.

Editable Jianying draft:

```bash
python scripts/autoedit.py doctor --backend jianying
python scripts/autoedit.py build "<blueprint.json>" --backend jianying --output "<new-draft-delivery-dir>" --approve
```

The JSON result gives `draft_directory`. Copy that complete NEW draft folder into
the Windows Jianying draft root, refresh/open it, inspect it, then export in the app.
Do not overwrite another folder while copying. Source paths are absolute and media
is not bundled: moving files/machines requires copying media and relinking paths.
Do not claim the app opened the draft unless observed. Do not parse, overwrite,
or attempt to bypass protection of a user's existing encrypted draft.

## 5. Verify, then recommend pickup shots

Read `audit.json`, the actual artifact, and the approved blueprint. FFmpeg success
means a file was produced, its frame count/canvas/duration/streams were checked,
and it decoded without errors. It does NOT establish that the story, lip-sync,
color, subjective audio quality, or Chinese font rendering is correct. Sample
boundaries, review subtitles, and listen to representative sections.

Jianying success means a JSON draft was written and read back for segment count
and duration; app compatibility remains pending a real editor check. Failure is
recorded in `FAILED.json` and must never be described as a finished delivery.

Compare script beats, the actual delivered timeline, and the COMPLETE reviewed
inventory before calling something missing. Report P0 (necessary for truth or
comprehension), P1 (material improvement), and P2 (optional polish). Each item
needs the missing information, source/timeline evidence, a concrete achievable
shot/sound request, and a no-reshoot alternative. First look for unused footage.
Preview the report before saving. State explicitly when nothing necessary is missing.

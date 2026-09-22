#!/usr/bin/env python3
"""Editor-neutral, source-safe editing CLI. Python 3.10+, FFmpeg/FFprobe.

No Resolve, MCP, model, or cloud dependency. Jianying is imported only on request.
All timestamps in the blueprint are seconds; draft timestamps are microseconds.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Any

VIDEO = {'.mp4', '.mov', '.mkv', '.avi', '.m4v', '.webm', '.mts', '.m2ts'}
AUDIO = {'.wav', '.mp3', '.m4a', '.aac', '.flac', '.ogg', '.aiff'}
IMAGE = {'.jpg', '.jpeg', '.png', '.webp', '.bmp'}


def run(args: list[str], *, cwd: Path | None = None, timeout: int = 3600) -> str:
    """Never invoke a shell; restrict media protocols at each input call site."""
    try:
        result = subprocess.run(args, cwd=cwd, capture_output=True, text=True,
                                encoding='utf-8', errors='replace', timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError(f'Cannot run {args[0]}: {exc}') from exc
    if result.returncode:
        raise ValueError(f'{args[0]} failed ({result.returncode}):\n{result.stderr[-4000:]}')
    return result.stdout


def probe(path: str | Path) -> dict[str, Any]:
    return json.loads(run(['ffprobe', '-v', 'error', '-protocol_whitelist', 'file,pipe',
                           '-show_format', '-show_streams', '-of', 'json', str(path)], timeout=60))


def stream(info: dict, kind: str) -> dict | None:
    return next((s for s in info.get('streams', []) if s.get('codec_type') == kind
                 and not s.get('disposition', {}).get('attached_pic')), None)


def number(value: Any, label: str, minimum: float = 0) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f'{label}: expected a JSON number')
    if not math.isfinite(value) or value < minimum:
        raise ValueError(f'{label}: expected a finite number >= {minimum}')
    return float(value)


def keys(obj: Any, allowed: set[str], label: str) -> None:
    if not isinstance(obj, dict):
        raise ValueError(f'{label}: expected an object')
    extra = set(obj) - allowed
    if extra:
        raise ValueError(f'{label}: unsupported fields: {sorted(extra)}; no silent omission')


def load_blueprint(path: Path, *, check_media: bool = True) -> tuple[dict, dict]:
    """Strict shared contract. A single contiguous visual track; timed audio layers."""
    data = json.loads(path.read_text(encoding='utf-8-sig'))
    keys(data, {'schema_version', 'project', 'clips', 'captions', 'notes', 'backend'}, 'blueprint')
    if data.get('schema_version') != '2.0':
        raise ValueError('Use schema_version "2.0"; see references/blueprint-schema.md for v1 migration')
    if data.get('backend', 'auto') not in {'auto', 'ffmpeg', 'jianying'}:
        raise ValueError('backend must be auto, ffmpeg, or jianying')
    project = data.get('project')
    keys(project, {'name', 'fps', 'width', 'height'}, 'project')
    if not isinstance(project.get('name'), str) or not project['name'].strip():
        raise ValueError('project.name must be nonempty')
    for field, default in [('fps', 30), ('width', 1920), ('height', 1080)]:
        value = project.setdefault(field, default)
        if type(value) is not int or value <= 0:
            raise ValueError(f'project.{field} must be a positive integer')
    if project['fps'] > 120 or max(project['width'], project['height']) > 8192:
        raise ValueError('Output is limited to 120 fps and 8192 pixels per side')
    if project['width'] % 2 or project['height'] % 2:
        raise ValueError('Output width and height must be even (H.264 yuv420p)')
    clips = data.get('clips')
    if not isinstance(clips, list) or not clips:
        raise ValueError('clips must be a nonempty list')
    seen, media = set(), {}
    for index, clip in enumerate(clips):
        keys(clip, {'id', 'media_type', 'source_path', 'source_in_seconds', 'source_out_seconds',
                    'timeline_in_seconds', 'timeline_out_seconds', 'speed', 'volume', 'fit',
                    'fade_in_seconds', 'fade_out_seconds', 'purpose', 'source_group', 'confidence',
                    'notes'}, f'clips[{index}]')
        cid = clip.get('id')
        if not isinstance(cid, str) or not cid or cid in seen:
            raise ValueError('Each clip needs a unique nonempty string id')
        seen.add(cid)
        kind = clip.get('media_type')
        if kind not in {'video', 'image', 'audio'}:
            raise ValueError(f'{cid}: media_type must be video, image or audio')
        raw_path = clip.get('source_path')
        if not isinstance(raw_path, str) or not raw_path or '://' in raw_path:
            raise ValueError(f'{cid}: source_path must be a local file')
        source = Path(raw_path).expanduser()
        source = (path.parent / source).resolve() if not source.is_absolute() else source.resolve()
        permitted = IMAGE if kind == 'image' else VIDEO if kind == 'video' else AUDIO | VIDEO
        if source.suffix.lower() not in permitted:
            raise ValueError(f'{cid}: unsupported source extension: {source.suffix}')
        clip['source_path'] = str(source)
        start = number(clip.get('timeline_in_seconds'), f'{cid}.timeline_in_seconds')
        end = number(clip.get('timeline_out_seconds'), f'{cid}.timeline_out_seconds')
        duration = end - start
        if duration < .001:
            raise ValueError(f'{cid}: duration must be >= 0.001 seconds')
        speed = number(clip.setdefault('speed', 1), f'{cid}.speed', .25)
        if speed > 4:
            raise ValueError(f'{cid}: speed must be between 0.25 and 4')
        if number(clip.setdefault('volume', 1), f'{cid}.volume') > 8:
            raise ValueError(f'{cid}: volume must be <= 8')
        fit = clip.setdefault('fit', 'pad')
        if fit not in {'pad', 'crop'} or (kind == 'audio' and fit != 'pad'):
            raise ValueError(f'{cid}: invalid fit policy')
        for field in ('fade_in_seconds', 'fade_out_seconds'):
            if number(clip.setdefault(field, 0), f'{cid}.{field}') > duration:
                raise ValueError(f'{cid}: audio fade exceeds clip duration')
        if clip['fade_in_seconds'] + clip['fade_out_seconds'] > duration:
            raise ValueError(f'{cid}: audio fades may not overlap')
        if kind == 'image':
            if speed != 1 or clip.get('source_in_seconds', 0) != 0 or 'source_out_seconds' in clip:
                raise ValueError(f'{cid}: images use timeline duration, not source range or retiming')
            if clip['fade_in_seconds'] or clip['fade_out_seconds']:
                raise ValueError(f'{cid}: images have no audio to fade')
            clip['volume'] = 0
        else:
            a = number(clip.get('source_in_seconds'), f'{cid}.source_in_seconds')
            b = number(clip.get('source_out_seconds'), f'{cid}.source_out_seconds')
            if b <= a or abs((b - a) / speed - duration) > .001:
                raise ValueError(f'{cid}: source range / speed must equal timeline duration')
        if kind != 'audio':
            for value in (start, end):
                if abs(value * project['fps'] - round(value * project['fps'])) > .001:
                    raise ValueError(f'{cid}: visual boundaries must align to output frames')
        if check_media:
            if not source.is_file():
                raise ValueError(f'{cid}: missing source file: {source}')
            if str(source) not in media:
                media[str(source)] = probe(source)
            info = media[str(source)]
            s = stream(info, 'audio' if kind == 'audio' else 'video')
            if s is None:
                raise ValueError(f'{cid}: requested media stream not found')
            if kind != 'image':
                available = s.get('duration', info.get('format', {}).get('duration'))
                try:
                    available = float(available)
                except (TypeError, ValueError):
                    raise ValueError(f'{cid}: cannot establish source duration') from None
                if not math.isfinite(available) or clip['source_out_seconds'] > available + .001:
                    raise ValueError(f'{cid}: source out-point exceeds media duration ({available})')
    visual = sorted((c for c in clips if c['media_type'] != 'audio'),
                    key=lambda c: c['timeline_in_seconds'])
    if not visual:
        raise ValueError('At least one video or image clip is required')
    cursor = 0.0
    for c in visual:
        if abs(c['timeline_in_seconds'] - cursor) > 1e-6:
            raise ValueError(f'{c["id"]}: visual gap/overlap; one contiguous track starting at zero is required')
        cursor = c['timeline_out_seconds']
    if any(c['timeline_out_seconds'] > cursor + 1e-6 for c in clips):
        raise ValueError('Audio may not extend beyond the visual timeline')
    captions = data.setdefault('captions', [])
    if not isinstance(captions, list):
        raise ValueError('captions must be a list')
    last = 0.0
    for cap in captions:
        keys(cap, {'start_seconds', 'end_seconds', 'text'}, 'caption')
        a = number(cap.get('start_seconds'), 'caption.start_seconds')
        b = number(cap.get('end_seconds'), 'caption.end_seconds')
        text = cap.get('text')
        if isinstance(text, str):
            text = text.replace('\r\n', '\n').replace('\r', '\n')
            cap['text'] = text
        if b - a < .001 or a < last or b > cursor + 1e-6:
            raise ValueError('Captions must be sorted, nonoverlapping and within the visual timeline')
        if not isinstance(text, str) or not text.strip() or '\x00' in text or '\n\n' in text:
            raise ValueError('Caption text must be nonempty and contain no NUL or blank line')
        last = b
    return data, media


def visuals(data: dict) -> list[dict]:
    return sorted((c for c in data['clips'] if c['media_type'] != 'audio'),
                  key=lambda c: c['timeline_in_seconds'])


def duration(c: dict) -> float:
    return c['timeline_out_seconds'] - c['timeline_in_seconds']


def write_json(path: Path, data: Any) -> None:
    with path.open('x', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write('\n')


def srt_text(captions: list[dict]) -> str:
    def stamp(seconds: float) -> str:
        total = round(seconds * 1000)
        h, total = divmod(total, 3600000)
        m, total = divmod(total, 60000)
        s, ms = divmod(total, 1000)
        return f'{h:02}:{m:02}:{s:02},{ms:03}'
    return ''.join(f'{i}\n{stamp(c["start_seconds"])} --> {stamp(c["end_seconds"])}\n'
                   f'{c["text"].replace(chr(13), "")}\n\n' for i, c in enumerate(captions, 1))


def audio_filter(c: dict) -> str:
    speed, factors = c['speed'], []
    while speed > 2:
        factors.append('atempo=2')
        speed /= 2
    while speed < .5:
        factors.append('atempo=0.5')
        speed /= .5
    factors += [f'atempo={speed:.10f}', f'volume={c["volume"]:.10f}',
                'aresample=48000', 'aformat=channel_layouts=stereo', 'apad',
                f'atrim=duration={duration(c):.10f}']
    if c['fade_in_seconds']:
        factors.append(f'afade=t=in:st=0:d={c["fade_in_seconds"]:.10f}')
    if c['fade_out_seconds']:
        factors.append(f'afade=t=out:st={duration(c)-c["fade_out_seconds"]:.10f}:d={c["fade_out_seconds"]:.10f}')
    return 'aresample=48000:async=1:first_pts=0,asetpts=PTS-STARTPTS,' + ','.join(factors)


def ffmpeg_build(data: dict, media: dict, out: Path, burn: bool) -> dict:
    project = data['project']
    w, h, fps = project['width'], project['height'], project['fps']
    visual = visuals(data)
    total = visual[-1]['timeline_out_seconds']
    base = ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-nostdin', '-n', '-threads', '2']
    with tempfile.TemporaryDirectory(prefix='_render-', dir=out) as temp:
        work = Path(temp)
        for index, c in enumerate(visual):
            cmd = base.copy()
            if c['media_type'] == 'image':
                cmd += ['-loop', '1', '-framerate', str(fps)]
            else:
                cmd += ['-ss', str(c['source_in_seconds'])]
            cmd += ['-protocol_whitelist', 'file,pipe', '-i', c['source_path']]
            info = media[c['source_path']]
            sound = stream(info, 'audio') if c['media_type'] == 'video' else None
            if sound is None or c['volume'] == 0:
                cmd += ['-f', 'lavfi', '-i', 'anullsrc=r=48000:cl=stereo']
                audio = '1:a:0'
            else:
                audio = f'0:{sound["index"]}'
            # FFmpeg auto-rotates decoded video. Scale to a common SAR and canvas.
            if c['fit'] == 'pad':
                scale = f'scale={w}:{h}:force_original_aspect_ratio=decrease:force_divisible_by=2,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2'
            else:
                scale = f'scale={w}:{h}:force_original_aspect_ratio=increase:force_divisible_by=2,crop={w}:{h}'
            vf = f'setpts=(PTS-STARTPTS)/{c["speed"]:.10f},{scale},setsar=1,fps={fps},format=yuv420p'
            cmd += ['-map', f'0:{stream(info, "video")["index"]}', '-map', audio,
                    '-vf', vf, '-af', audio_filter(c), '-filter_threads', '1',
                    '-t', str(duration(c)), '-r', str(fps), '-c:v', 'libx264',
                    '-preset', 'veryfast', '-crf', '20', '-threads', '2',
                    '-c:a', 'pcm_s16le', str(work / f'clip-{index:05}.mkv')]
            run(cmd)
        (work / 'concat.txt').write_text(''.join(f"file 'clip-{i:05}.mkv'\n" for i in range(len(visual))), encoding='utf-8')
        run(base + ['-f', 'concat', '-safe', '1', '-i', 'concat.txt', '-c', 'copy', 'assembled.mkv'], cwd=work)
        cmd = base + ['-i', str(work / 'assembled.mkv')]
        extra = [c for c in data['clips'] if c['media_type'] == 'audio']
        graph, labels = [], ['[0:a:0]']
        for index, c in enumerate(extra, 1):
            cmd += ['-ss', str(c['source_in_seconds']), '-t', str(c['source_out_seconds']-c['source_in_seconds']),
                    '-protocol_whitelist', 'file,pipe', '-i', c['source_path']]
            ai = stream(media[c['source_path']], 'audio')['index']
            delay = round(c['timeline_in_seconds'] * 48000)
            graph.append(f'[{index}:{ai}]{audio_filter(c)},adelay={delay}S:all=1[a{index}]')
            labels.append(f'[a{index}]')
        graph.append(''.join(labels) + f'amix=inputs={len(labels)}:duration=first:normalize=0,'
                     f'alimiter=limit=0.95:level=0:latency=1,atrim=duration={total:.10f}[audio]')
        (work / 'mix.txt').write_text(';\n'.join(graph), encoding='utf-8')
        has_captions = bool(data['captions'])
        if has_captions and not burn:
            cmd += ['-i', str(out / 'captions.srt')]
        cmd += ['-filter_complex_script', str(work / 'mix.txt'), '-filter_complex_threads', '1',
                '-map', '0:v:0', '-map', '[audio]']
        if has_captions and burn:
            # Fixed relative filename avoids Windows/Unicode filter-path escaping bugs.
            cmd += ['-vf', 'subtitles=filename=captions.srt', '-filter_threads', '1',
                    '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '20', '-threads', '2']
        else:
            cmd += ['-c:v', 'copy']
        if has_captions and not burn:
            cmd += ['-map', f'{len(extra)+1}:s:0', '-c:s', 'mov_text']
        cmd += ['-t', str(total), '-c:a', 'aac', '-b:a', '192k', '-ar', '48000',
                '-movflags', '+faststart', str(out / 'final.partial.mp4')]
        run(cmd, cwd=out)
    result = probe(out / 'final.partial.mp4')
    video, audio = stream(result, 'video'), stream(result, 'audio')
    actual = float(result['format']['duration'])
    frames = int(video.get('nb_frames', 0)) if video else 0
    if not video or not audio or (video['width'], video['height']) != (w, h) or frames != round(total*fps) or abs(actual-total) > max(.1, 2/fps):
        raise ValueError('Rendered file failed stream/canvas/duration audit; kept as final.partial.mp4')
    run(['ffmpeg', '-hide_banner', '-v', 'error', '-nostdin', '-xerror', '-i',
         str(out / 'final.partial.mp4'), '-f', 'null', '-'])
    (out / 'final.partial.mp4').rename(out / 'final.mp4')
    return {'status': 'rendered_and_decode_checked', 'backend': 'ffmpeg', 'file': str(out/'final.mp4'),
            'expected_duration_seconds': total, 'actual_duration_seconds': actual, 'video_frames': frames,
            'visual_clips': len(visual), 'additional_audio_clips': len(extra),
            'subtitle_mode': ('burn' if burn else 'soft') if has_captions else 'none',
            'human_review_required': ['story', 'sync and loudness', 'subtitle appearance', 'picture quality']}


def macos_jianying_root(override: str | Path | None = None) -> Path:
    """Target the native macOS Jianying Pro draft library, not the Windows layout."""
    if override:
        return Path(override).expanduser().resolve()
    if os.getenv('JY_DRAFT_ROOT'):
        return Path(os.environ['JY_DRAFT_ROOT']).expanduser().resolve()
    home = Path.home()
    candidates = [
        home/'Movies'/'JianyingPro'/'User Data'/'Projects'/'com.lveditor.draft',
        home/'Movies'/'JianyingPro Drafts',
    ]
    return next((p for p in candidates if p.is_dir()), candidates[0])


def _mac_platform(draft_root: Path) -> tuple[dict, bool]:
    """Reuse a local plaintext Mac platform fingerprint when one is available."""
    if draft_root.is_dir():
        for child in sorted(draft_root.iterdir()):
            info = child/'draft_info.json'
            if not info.is_file():
                continue
            try:
                platform = json.loads(info.read_text(encoding='utf-8')).get('platform', {})
            except (OSError, json.JSONDecodeError, UnicodeDecodeError):
                continue
            if isinstance(platform, dict) and platform.get('os') == 'mac':
                keep = {k: platform[k] for k in
                        ('os', 'app_version', 'device_id', 'hard_disk_id', 'mac_address')
                        if k in platform}
                return keep, bool(keep.get('device_id'))
    return {'os': 'mac', 'app_version': '5.9.0'}, False


def _safe_resource_name(name: str, used: set[str]) -> str:
    source = Path(name)
    stem, suffix = source.stem or 'media', source.suffix
    candidate, index = f'{stem}{suffix}', 2
    while candidate.casefold() in used:
        candidate = f'{stem}-{index}{suffix}'
        index += 1
    used.add(candidate.casefold())
    return candidate


def _macify_jianying_draft(draft_dir: Path, draft_name: str,
                           draft_root: Path) -> tuple[dict, list[str]]:
    """Convert the serializer staging output into a macOS Jianying draft."""
    content_path = draft_dir/'draft_content.json'
    meta_path = draft_dir/'draft_meta_info.json'
    content = json.loads(content_path.read_text(encoding='utf-8'))
    meta = json.loads(meta_path.read_text(encoding='utf-8'))
    platform, fingerprinted = _mac_platform(draft_root)
    for key in ('platform', 'last_modified_platform'):
        base = content.get(key) if isinstance(content.get(key), dict) else {}
        content[key] = {**base, **platform, 'os': 'mac'}

    resources = draft_dir/'Resources'
    resources.mkdir(exist_ok=False)
    future_resources = draft_root/draft_name/'Resources'
    used: set[str] = set()
    copied: dict[str, str] = {}
    total_size = 0
    for kind in ('videos', 'audios'):
        for material in content.get('materials', {}).get(kind, []):
            raw = material.get('path')
            if not raw:
                raise ValueError(f'Mac Jianying material in {kind} has no source path')
            source = Path(raw).expanduser().resolve()
            if not source.is_file():
                raise ValueError(f'Mac Jianying material missing before bundling: {source}')
            key = str(source)
            if key not in copied:
                name = _safe_resource_name(source.name, used)
                target = resources/name
                shutil.copy2(source, target)
                total_size += target.stat().st_size
                copied[key] = str(future_resources/name)
            material['path'] = copied[key]

    now_us = int(__import__('time').time() * 1_000_000)
    records = []
    for kind, default_type in (('videos', 'video'), ('audios', 'music')):
        for material in content.get('materials', {}).get(kind, []):
            records.append({
                'create_time': now_us//1_000_000,
                'duration': material.get('duration', 0),
                'extra_info': material.get('material_name') or material.get('name')
                              or Path(material['path']).name,
                'file_Path': material['path'],
                'height': material.get('height', 0),
                'id': hashlib.sha256((material['path']+str(now_us)).encode()).hexdigest()[:32],
                'import_time': now_us//1_000_000,
                'import_time_ms': now_us,
                'item_source': 1,
                'md5': '',
                'metetype': 'photo' if material.get('type') == 'photo' else default_type,
                'roughcut_time_range': {'duration': -1, 'start': -1},
                'sub_time_range': {'duration': -1, 'start': -1},
                'type': 0,
                'width': material.get('width', 0),
            })

    final_dir = draft_root/draft_name
    meta.update({
        'draft_fold_path': str(final_dir),
        'draft_root_path': str(draft_root),
        'draft_name': draft_name,
        'tm_draft_create': now_us,
        'tm_draft_modified': now_us,
        'tm_duration': content.get('duration', 0),
        'draft_timeline_materials_size': total_size,
        'draft_timeline_materials_size_': total_size,
    })
    groups = meta.setdefault('draft_materials', [])
    material_group = next((g for g in groups
                           if isinstance(g, dict) and g.get('type') == 0), None)
    if material_group is None:
        material_group = {'type': 0, 'value': []}
        groups.append(material_group)
    material_group['value'] = records

    text = json.dumps(content, ensure_ascii=False, indent=4)
    content_path.write_text(text, encoding='utf-8')
    (draft_dir/'draft_info.json').write_text(text, encoding='utf-8')
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=4), encoding='utf-8')
    warnings = []
    if not fingerprinted:
        warnings.append('No plaintext local Mac draft fingerprint found; verify this draft in Jianying.')
    if not draft_root.is_dir():
        warnings.append(f'Target macOS Jianying draft root does not exist yet: {draft_root}')
    return content, warnings


def jianying_build(data: dict, out: Path,
                   draft_root: str | Path | None = None) -> dict:
    """Build a self-contained draft specifically for macOS Jianying Pro."""
    import pyJianYingDraft as draft
    p = data['project']
    target_root = macos_jianying_root(draft_root)
    folder = draft.DraftFolder(str(out))
    draft_name = 'AutoEdit-' + out.name
    script = folder.create_draft(draft_name, p['width'], p['height'], fps=p['fps'],
                                 maintrack_adsorb=False, allow_replace=False)
    script.add_track(draft.TrackType.video, 'V1')
    us = lambda seconds: round(seconds * 1_000_000)
    ordered = visuals(data) + [c for c in data['clips'] if c['media_type'] == 'audio']
    for i, c in enumerate(ordered):
        target = draft.Timerange(us(c['timeline_in_seconds']), us(duration(c)))
        kwargs = {'volume': c['volume']}
        if c['media_type'] != 'image':
            kwargs['source_timerange'] = draft.Timerange(
                us(c['source_in_seconds']),
                us(c['source_out_seconds']-c['source_in_seconds']))
        if c['media_type'] == 'audio':
            name = f'A{i+1}'
            script.add_track(draft.TrackType.audio, name)
            segment = draft.AudioSegment(c['source_path'], target, **kwargs)
        else:
            name = 'V1'
            segment = draft.VideoSegment(c['source_path'], target, **kwargs)
        if c['fade_in_seconds'] or c['fade_out_seconds']:
            segment.add_fade(us(c['fade_in_seconds']), us(c['fade_out_seconds']))
        script.add_segment(segment, name)
    if data['captions']:
        script.add_track(draft.TrackType.text, 'Captions')
        for c in data['captions']:
            segment = draft.TextSegment(
                c['text'],
                draft.Timerange(us(c['start_seconds']),
                                us(c['end_seconds']-c['start_seconds'])),
                clip_settings=draft.ClipSettings(transform_y=-0.8))
            script.add_segment(segment, 'Captions')
    script.save()
    draft_dir = out/draft_name
    saved, warnings = _macify_jianying_draft(draft_dir, draft_name, target_root)
    segments = [s for t in saved['tracks'] for s in t['segments']]
    expected = len(data['clips']) + len(data['captions'])
    total = visuals(data)[-1]['timeline_out_seconds']
    if len(segments) != expected or abs(saved['duration']-us(total)) > 10:
        raise ValueError('macOS Jianying draft readback failed segment-count/duration audit')
    return {
        'status': 'macos_draft_written_not_editor_verified',
        'backend': 'jianying',
        'draft_directory': str(draft_dir),
        'target_draft_root': str(target_root),
        'expected_install_path': str(target_root/draft_name),
        'entry_file': str(draft_dir/'draft_info.json'),
        'segments': len(segments),
        'duration_seconds': total,
        'warnings': warnings,
        'human_review_required': [
            'This output targets macOS Jianying Pro and uses draft_info.json plus bundled Resources',
            'Copy the complete draft folder into target_draft_root while Jianying is closed, then reopen it',
            'Check media, framing, audio, captions, and draft visibility in the actual Mac app',
            'Export from Jianying manually; macOS GUI auto-export is not claimed',
        ],
    }


def doctor(backend: str, draft_root: str | Path | None = None) -> dict:
    checks = {name: bool(shutil.which(name)) for name in ('ffmpeg', 'ffprobe')}
    checks['pyJianYingDraft'] = importlib.util.find_spec('pyJianYingDraft') is not None
    chosen = 'ffmpeg' if backend == 'auto' else backend
    checks['backend'] = chosen
    checks['host_macos'] = sys.platform == 'darwin'
    if chosen == 'jianying':
        root = macos_jianying_root(draft_root)
        checks['target_draft_root'] = str(root)
        checks['target_draft_root_exists'] = root.is_dir()
        checks['ready'] = checks['ffprobe'] and checks['pyJianYingDraft'] and checks['host_macos']
    else:
        checks['ready'] = checks['ffprobe'] and checks['ffmpeg']
    checks['resolve_required'] = False
    return checks


def build(path: Path, output: Path, backend: str | None, *, dry_run: bool = False,
          burn: bool = False, draft_root: str | Path | None = None) -> dict:
    data, media = load_blueprint(path.resolve())
    chosen = backend or data.get('backend', 'auto')
    chosen = 'ffmpeg' if chosen == 'auto' else chosen
    out = output.expanduser().resolve()
    if chosen not in {'ffmpeg', 'jianying'}:
        raise ValueError('Unknown editing backend')
    if out.exists():
        raise ValueError('Output already exists; choose a NEW output directory (no overwrite)')
    if chosen == 'jianying':
        if burn or any(c['fit'] != 'pad' for c in data['clips']):
            raise ValueError('Jianying adapter supports native captions and fit=pad only; use FFmpeg for crop/burn')
    plan = {'backend': chosen, 'output': str(out), 'duration_seconds': visuals(data)[-1]['timeline_out_seconds'],
            'clips': len(data['clips']), 'captions': len(data['captions'])}
    if chosen == 'jianying':
        plan['target_draft_root'] = str(macos_jianying_root(draft_root))
    if dry_run:
        return dict(plan, status='dry_run_no_files_written', readiness=doctor(chosen, draft_root))
    if not doctor(chosen, draft_root)['ready']:
        raise ValueError(f'{chosen} dependencies unavailable; run doctor and install only the requested backend')
    # Import optional dependency before any output mutation.
    if chosen == 'jianying':
        try:
            __import__('pyJianYingDraft')
        except (ImportError, OSError) as exc:
            raise ValueError(f'Jianying dependency cannot load: {exc}') from exc
    out.mkdir(parents=True, exist_ok=False)
    try:
        write_json(out/'edit-blueprint.json', data)
        if data['captions']:
            (out/'captions.srt').write_text(srt_text(data['captions']), encoding='utf-8')
        audit = ffmpeg_build(data, media, out, burn) if chosen == 'ffmpeg' else jianying_build(data, out, draft_root)
        write_json(out/'audit.json', audit)
        return audit
    except Exception as exc:
        write_json(out/'FAILED.json', {'status': 'failed', 'backend': chosen, 'error': str(exc)})
        raise


def scan(paths: list[str], out: Path) -> dict:
    files = set()
    for raw in paths:
        p = Path(raw).expanduser().resolve()
        if not p.exists():
            raise ValueError(f'Scan input does not exist: {p}')
        files.update([p] if p.is_file() else (f for f in p.rglob('*') if f.is_file()))
    rows = []
    for p in sorted(files):
        ext = p.suffix.lower()
        kind = 'video' if ext in VIDEO else 'audio' if ext in AUDIO else 'image' if ext in IMAGE else None
        if kind is None:
            continue
        row = {'id': hashlib.sha256(str(p).encode()).hexdigest()[:16], 'source_path': str(p),
               'media_type': kind, 'size_bytes': p.stat().st_size}
        try:
            row['probe'] = probe(p)
        except ValueError as exc:
            row['error'] = str(exc)
        rows.append(row)
    write_json(out, {'media': rows, 'notice': 'Metadata only, not a visual review or transcript'})
    return {'manifest': str(out.resolve()), 'files': len(rows), 'errors': sum('error' in r for r in rows)}



def extract(manifest: Path, output: Path, every: float, maximum: int) -> dict:
    """Sample the whole video, not just its opening; no cloud calls."""
    if not math.isfinite(every) or every <= 0 or not 1 <= maximum <= 1000:
        raise ValueError('every must be positive; max-per-video must be in 1..1000')
    data = json.loads(manifest.read_text(encoding='utf-8'))
    out = output.expanduser().resolve()
    out.mkdir(parents=True, exist_ok=False)
    rows = []
    for entry in data['media']:
        if entry.get('error') or entry['media_type'] not in {'video', 'image'}:
            continue
        source = Path(entry['source_path']).resolve()
        # Treat the supplied manifest as untrusted; never use its ID as a path.
        if not source.is_file() or source.suffix.lower() not in VIDEO | IMAGE:
            raise ValueError(f'Invalid extraction source: {source}')
        identity = hashlib.sha256(str(source).encode()).hexdigest()[:16]
        seconds = float(entry.get('probe', {}).get('format', {}).get('duration', 0))
        if entry['media_type'] == 'video' and (not math.isfinite(seconds) or seconds <= 0):
            rows.append({'source_path': str(source), 'ok': False, 'error': 'No valid video duration'})
            continue
        count = min(maximum, max(1, math.ceil(seconds/every))) if entry['media_type'] == 'video' else 1
        for index in range(count):
            time = seconds*(index+.5)/count if entry['media_type'] == 'video' else 0
            image = out/f'{identity}-{index:04}.jpg'
            cmd = ['ffmpeg','-v','error','-nostdin','-n']
            if time:
                cmd += ['-ss', str(time)]
            cmd += ['-protocol_whitelist','file,pipe','-i',str(source),'-frames:v','1',
                    '-vf','scale=960:-2','-threads','1',str(image)]
            row = {'source_path':str(source),'time_seconds':time,'image_path':str(image)}
            try:
                run(cmd, timeout=120)
                row['ok'] = image.is_file() and image.stat().st_size > 0
            except ValueError as exc:
                row.update(ok=False, error=str(exc))
            rows.append(row)
    write_json(out/'frames-index.json', rows)
    return {'index':str(out/'frames-index.json'),'frames':sum(bool(r['ok']) for r in rows),
            'failed':sum(not r['ok'] for r in rows)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    d = sub.add_parser('doctor')
    d.add_argument('--backend', choices=['auto', 'ffmpeg', 'jianying'], default='auto')
    d.add_argument('--draft-root', type=Path, help='macOS Jianying Pro draft root override')
    s = sub.add_parser('scan')
    s.add_argument('--input', action='append', required=True)
    s.add_argument('--output', type=Path, required=True)
    e = sub.add_parser('extract')
    e.add_argument('--manifest', type=Path, required=True)
    e.add_argument('--output', type=Path, required=True)
    e.add_argument('--every', type=float, default=10)
    e.add_argument('--max-per-video', type=int, default=24)
    v = sub.add_parser('validate')
    v.add_argument('blueprint', type=Path)
    v.add_argument('--no-probe', action='store_true', help='Schema only; does NOT validate source availability')
    b = sub.add_parser('build')
    b.add_argument('blueprint', type=Path)
    b.add_argument('--backend', choices=['auto', 'ffmpeg', 'jianying'])
    b.add_argument('--output', type=Path, required=True, help='New delivery DIRECTORY, not an MP4 filename')
    b.add_argument('--dry-run', action='store_true')
    b.add_argument('--approve', action='store_true', help='Explicitly authorize the previewed new output')
    b.add_argument('--burn-captions', action='store_true', help='FFmpeg only; requires libass and local fonts')
    b.add_argument('--draft-root', type=Path, help='macOS Jianying Pro draft root override')
    args = parser.parse_args()
    try:
        if args.command == 'doctor':
            result = doctor(args.backend, args.draft_root)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0 if result['ready'] else 2
        if args.command == 'scan':
            result = scan(args.input, args.output)
        elif args.command == 'extract':
            result = extract(args.manifest, args.output, args.every, args.max_per_video)
        elif args.command == 'validate':
            data, _ = load_blueprint(args.blueprint.resolve(), check_media=not args.no_probe)
            result = {'status': 'schema_valid' if args.no_probe else 'schema_and_media_valid',
                      'clips': len(data['clips']), 'duration_seconds': visuals(data)[-1]['timeline_out_seconds']}
        else:
            if not args.dry_run and not args.approve:
                raise ValueError('Preview with --dry-run, then authorize the new output with --approve')
            result = build(args.blueprint, args.output, args.backend, dry_run=args.dry_run, burn=args.burn_captions,
                           draft_root=args.draft_root)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(json.dumps({'status': 'failed', 'error': str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())

"""Install editor-neutral skills by default; preserve old installs with backups."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import shutil
import uuid

DEFAULT_SKILLS = ('autoedit-agent', 'viral-video-writer')
LEGACY_SKILLS = ('davinci-autoedit-agent', 'davinci-resolve-editor')


def install(repo: Path, dest: Path, *, legacy: bool = False, force: bool = False,
            dry_run: bool = False) -> list[str]:
    repo, dest = repo.resolve(), dest.expanduser().resolve()
    names = DEFAULT_SKILLS + (LEGACY_SKILLS if legacy else ())
    # Validate every source and destination before making any changes.
    for name in names:
        source, target = repo/'skills'/name, dest/name
        if not (source/'SKILL.md').is_file():
            raise FileNotFoundError(f'Skill missing from repository: {source}')
        if target == source or dest == source or source in dest.parents:
            raise ValueError('Installation destination must not be inside a source skill')
    actions = []
    for name in names:
        source, target = repo/'skills'/name, dest/name
        if not (source/'SKILL.md').is_file():
            raise FileNotFoundError(f'Skill missing from repository: {source}')
        if target.exists() and not force:
            actions.append(f'skip {name}: exists; --force makes a backup before replacement')
            continue
        actions.append(f'install {name} -> {target}')
        if dry_run:
            continue
        dest.mkdir(parents=True, exist_ok=True)
        if target.exists():
            # Backups are outside the skills discovery root, so they do not duplicate triggers.
            stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
            backup_root = dest.parent/'skill-backups'
            backup_root.mkdir(parents=True, exist_ok=True)
            backup = backup_root/f'{name}-{stamp}-{uuid.uuid4().hex[:8]}'
            target.rename(backup)
            actions.append(f'backup {name} -> {backup}')
        shutil.copytree(source, target, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    if not legacy:
        for name in LEGACY_SKILLS:
            if (dest/name).exists():
                actions.append(f'legacy already installed: {name}; left untouched; invoke $autoedit-agent explicitly')
    return actions


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dest', type=Path,
                        default=Path(os.getenv('CODEX_HOME', Path.home()/'.codex'))/'skills')
    parser.add_argument('--include-legacy', action='store_true', help='Opt in to the old Resolve skills')
    parser.add_argument('--force', action='store_true', help='Back up and replace an existing skill')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    for line in install(Path(__file__).resolve().parents[1], args.dest.expanduser(),
                        legacy=args.include_legacy, force=args.force, dry_run=args.dry_run):
        print(line)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

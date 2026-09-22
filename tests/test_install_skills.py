"""Installer behavior with an isolated synthetic repository, not user skill folders."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('autoedit_installer', ROOT/'scripts/install_skills.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.repo, self.dest = self.root/'repo', self.root/'host/skills'
        for name in installer.DEFAULT_SKILLS + installer.LEGACY_SKILLS:
            source = self.repo/'skills'/name
            source.mkdir(parents=True)
            (source/'SKILL.md').write_text('new '+name, encoding='utf-8')

    def tearDown(self):
        self.tmp.cleanup()

    def test_default_excludes_resolve(self):
        installer.install(self.repo, self.dest)
        self.assertEqual({p.name for p in self.dest.iterdir()}, set(installer.DEFAULT_SKILLS))

    def test_legacy_is_opt_in(self):
        installer.install(self.repo, self.dest, legacy=True)
        self.assertEqual(len(list(self.dest.iterdir())), 4)

    def test_dry_run_creates_nothing(self):
        self.assertEqual(len(installer.install(self.repo, self.dest, dry_run=True)), 2)
        self.assertFalse(self.dest.exists())

    def test_force_keeps_original_backup_outside_discovery(self):
        installer.install(self.repo, self.dest)
        old = self.dest/'autoedit-agent/SKILL.md'
        old.write_text('user changes', encoding='utf-8')
        installer.install(self.repo, self.dest, force=True)
        backups = list((self.dest.parent/'skill-backups').glob('autoedit-agent-*/SKILL.md'))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(), 'user changes')
        self.assertEqual(old.read_text(), 'new autoedit-agent')

    def test_existing_skills_left_unchanged(self):
        installer.install(self.repo, self.dest, legacy=True)
        marker = self.dest/'autoedit-agent/SKILL.md'
        marker.write_text('keep', encoding='utf-8')
        installer.install(self.repo, self.dest)
        self.assertEqual(marker.read_text(), 'keep')
        self.assertTrue((self.dest/'davinci-resolve-editor/SKILL.md').exists())

    def test_cannot_install_into_source(self):
        for dest in (self.repo/'skills', self.repo/'skills/autoedit-agent/inside'):
            with self.assertRaises(ValueError):
                installer.install(self.repo, dest, force=True)
        self.assertTrue((self.repo/'skills/autoedit-agent/SKILL.md').is_file())

    def test_missing_source_fails_before_any_write(self):
        (self.repo/'skills/viral-video-writer/SKILL.md').unlink()
        with self.assertRaises(FileNotFoundError):
            installer.install(self.repo, self.dest)
        self.assertFalse(self.dest.exists())


if __name__ == '__main__':
    unittest.main()

import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ROOT = Path(__file__).resolve().parent.parent


class TestBuildContract(unittest.TestCase):
    """Smoke-тест согласованности путей Windows-сборки.

    Ловит расхождения между CI-workflow, scripts/build_exe.ps1 и спекой
    PyInstaller (например, когда workflow ждет один путь, а скрипт кладет другой).
    """

    def test_workflows_point_to_release_artifact(self):
        for name in ("build-exe.yml", "build-windows.yml"):
            text = (ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8")
            self.assertIn(
                "release/JARVIS.exe", text,
                f"{name}: CI должен загружать release/JARVIS.exe",
            )

    def test_build_script_copies_dist_to_release(self):
        text = (ROOT / "scripts" / "build_exe.ps1").read_text(encoding="utf-8")
        self.assertIn("dist\\jarvis_desktop.exe", text)
        self.assertIn("release", text)
        self.assertIn("JARVIS.exe", text)

    def test_desktop_spec_matches_dist_output(self):
        spec = (ROOT / "jarvis_desktop.spec").read_text(encoding="utf-8")
        match = re.search(r'name\s*=\s*"([^"]+)"', spec)
        self.assertIsNotNone(match, "в jarvis_desktop.spec нет имени exe")
        self.assertEqual(match.group(1), "jarvis_desktop")

    def test_autostart_default_targets_release_exe(self):
        text = (ROOT / "scripts" / "install_autostart.ps1").read_text(encoding="utf-8")
        self.assertIn("release\\JARVIS.exe", text)

    def test_cli_spec_entry_point_exists(self):
        """CLI-спека ссылается на реальный entry point и не требует vendor/."""
        spec = (ROOT / "jarvis.spec").read_text(encoding="utf-8")
        match = re.search(r'\["([^"]+\.py)"\]', spec)
        self.assertIsNotNone(match, "в jarvis.spec нет entry-файла")
        entry = ROOT / match.group(1)
        self.assertTrue(entry.exists(), f"jarvis.spec ссылается на несуществующий {match.group(1)}")
        self.assertNotIn("vendor", spec, "CLI-спека не должна требовать vendor/ (он есть только в CI)")
        self.assertIn('name="jarvis"', spec)

    def test_vendor_paths_consistent_between_spec_and_script(self):
        """Пути vendor/ в jarvis_desktop.spec должны совпадать с теми, куда качает build_exe.ps1."""
        spec = (ROOT / "jarvis_desktop.spec").read_text(encoding="utf-8")
        script = (ROOT / "scripts" / "build_exe.ps1").read_text(encoding="utf-8")
        for asset in ("vendor/stt_model", "vendor/piper"):
            self.assertIn(asset, spec, f"jarvis_desktop.spec должна собирать {asset}")
        for asset in ("vendor\\stt_model", "vendor\\piper"):
            self.assertIn(asset, script, f"build_exe.ps1 должна скачивать {asset}")

    def test_gitignore_covers_build_artifacts(self):
        """vendor/ и release/ создаются только сборкой и не должны попадать в git."""
        text = (ROOT / ".gitignore").read_text(encoding="utf-8")
        lines = {ln.strip() for ln in text.splitlines()}
        self.assertIn("vendor/", lines)
        self.assertIn("release/", lines)


if __name__ == "__main__":
    unittest.main()
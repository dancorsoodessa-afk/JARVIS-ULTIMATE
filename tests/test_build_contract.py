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


if __name__ == "__main__":
    unittest.main()
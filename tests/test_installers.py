import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "install" / "install.sh"
HERMES_INSTALLER = ROOT / "install" / "install-hermes.sh"
CODEX_INSTALLER = ROOT / "install" / "install-codex.sh"
ENGINE = ROOT / "scripts" / "codex_senior_consult.py"


class InstallerTests(unittest.TestCase):
    def setUp(self):
        if shutil.which("bash") is None:
            self.skipTest("bash is required for installer tests")
        if shutil.which("install") is None:
            self.skipTest("POSIX install command is required for installer tests")

    def run_installer(self, *args, env=None):
        return subprocess.run(
            ["bash", str(INSTALLER), *map(str, args)],
            cwd=ROOT,
            text=True,
            capture_output=True,
            env=env,
            timeout=20,
        )

    def test_both_installations_share_engine_but_keep_caller_frontends_distinct(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            hermes_home = root / "hermes"
            codex_home = root / "codex"
            bin_dir = root / "bin"
            env = os.environ.copy()
            env["HOME"] = str(root / "home")

            proc = self.run_installer(
                "--client", "both",
                "--hermes-home", hermes_home,
                "--codex-home", codex_home,
                "--bin-dir", bin_dir,
                env=env,
            )
            self.assertEqual(proc.returncode, 0, (proc.stdout, proc.stderr))

            cli = bin_dir / "codex-senior-consult"
            codex_skill = codex_home / "skills" / "codex-senior-consult"
            hermes_skill = hermes_home / "skills" / "codex-senior-consult"

            self.assertTrue(cli.is_file())
            self.assertTrue(os.access(cli, os.X_OK))
            self.assertEqual(cli.read_bytes(), ENGINE.read_bytes())

            self.assertEqual(
                (codex_skill / "SKILL.md").read_text(),
                (ROOT / "SKILL.md").read_text(),
            )
            self.assertEqual(
                (hermes_skill / "SKILL.md").read_text(),
                (ROOT / "integrations" / "hermes" / "SKILL.md").read_text(),
            )
            self.assertNotEqual(
                (codex_skill / "SKILL.md").read_text(),
                (hermes_skill / "SKILL.md").read_text(),
            )
            self.assertIn("metadata:\n  hermes:", (hermes_skill / "SKILL.md").read_text())

            for skill_root in (codex_skill, hermes_skill):
                self.assertEqual(
                    (skill_root / "scripts" / "codex_senior_consult.py").read_bytes(),
                    ENGINE.read_bytes(),
                )
                self.assertTrue((skill_root / "references" / "contracts.md").is_file())

            self.assertTrue((codex_skill / "agents" / "openai.yaml").is_file())
            self.assertTrue((hermes_skill / "references" / "verification-prompt.md").is_file())

            help_proc = subprocess.run(
                [str(cli), "--help"],
                text=True,
                capture_output=True,
                env=env,
                timeout=10,
            )
            self.assertEqual(help_proc.returncode, 0, help_proc.stderr)
            self.assertIn("build-bundle", help_proc.stdout)
            self.assertIn("preflight", help_proc.stdout)
            self.assertIn("consult", help_proc.stdout)
            self.assertIn("status", help_proc.stdout)

    def test_invalid_preflight_from_installed_cli_never_starts_codex(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bin_dir = root / "bin"
            env = os.environ.copy()
            env["HOME"] = str(root / "home")

            install_proc = self.run_installer(
                "--client", "hermes",
                "--hermes-home", root / "hermes",
                "--codex-home", root / "codex",
                "--bin-dir", bin_dir,
                env=env,
            )
            self.assertEqual(install_proc.returncode, 0, install_proc.stderr)

            fake_bin = root / "fake-bin"
            fake_bin.mkdir()
            marker = root / "codex-process-created"
            fake_codex = fake_bin / "codex"
            fake_codex.write_text(
                "#!/bin/sh\n"
                f"touch {marker!s}\n"
                "exit 99\n"
            )
            fake_codex.chmod(0o755)

            bundle = root / "invalid.json"
            bundle.write_text("{}\n")
            child_env = env.copy()
            child_env["PATH"] = f"{fake_bin}{os.pathsep}{child_env.get('PATH', '')}"

            proc = subprocess.run(
                [
                    str(bin_dir / "codex-senior-consult"),
                    "preflight",
                    "--mission-id", "installer-zero-process",
                    "--mode", "merge-gate",
                    "--bundle", str(bundle),
                ],
                text=True,
                capture_output=True,
                env=child_env,
                timeout=10,
            )
            self.assertEqual(proc.returncode, 2, (proc.stdout, proc.stderr))
            result = json.loads(proc.stdout)
            self.assertEqual(result["status"], "PREFLIGHT_INVALID")
            self.assertFalse(result["valid"])
            self.assertEqual(result["model_processes_consumed"], 0)
            self.assertFalse(marker.exists())

    def test_dry_run_and_shortcuts_do_not_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            env = os.environ.copy()
            env["HOME"] = str(root / "home")

            shared = [
                "--hermes-home", str(root / "hermes"),
                "--codex-home", str(root / "codex"),
                "--bin-dir", str(root / "bin"),
                "--dry-run",
            ]
            commands = [
                ["bash", str(INSTALLER), "--client", "both", *shared],
                ["bash", str(HERMES_INSTALLER), *shared],
                ["bash", str(CODEX_INSTALLER), *shared],
            ]
            for command in commands:
                with self.subTest(command=command[1]):
                    proc = subprocess.run(
                        command,
                        cwd=ROOT,
                        text=True,
                        capture_output=True,
                        env=env,
                        timeout=20,
                    )
                    self.assertEqual(proc.returncode, 0, (proc.stdout, proc.stderr))
                    self.assertIn("codex-senior-consult", proc.stdout)

            self.assertFalse((root / "hermes").exists())
            self.assertFalse((root / "codex").exists())
            self.assertFalse((root / "bin").exists())


if __name__ == "__main__":
    unittest.main()

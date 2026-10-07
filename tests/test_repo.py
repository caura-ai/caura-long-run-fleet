from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import simulate  # noqa: E402


class EnvironmentPrecedenceTests(unittest.TestCase):
    def test_current_name_wins(self) -> None:
        values = {"CAURA_API_URL": "https://new.example", "MEMCLAW_API_URL": "https://old.example"}  # legacy-name-ok: test pins supported env fallback
        self.assertEqual(
            simulate.read_compatible_env("CAURA_API_URL", "MEMCLAW_API_URL", environ=values),  # legacy-name-ok: test pins supported env fallback
            "https://new.example",
        )

    def test_blank_current_name_falls_back_to_non_empty_alias(self) -> None:
        values = {"CAURA_API_URL": "", "MEMCLAW_API_URL": "https://old.example"}  # legacy-name-ok: test pins supported env fallback
        self.assertEqual(
            simulate.read_compatible_env("CAURA_API_URL", "MEMCLAW_API_URL", environ=values),  # legacy-name-ok: test pins supported env fallback
            "https://old.example",
        )

    def test_default_is_used_when_both_names_are_empty(self) -> None:
        values = {"CAURA_API_URL": "", "MEMCLAW_API_URL": ""}  # legacy-name-ok: test pins supported env fallback
        self.assertEqual(
            simulate.read_compatible_env(
                "CAURA_API_URL", "MEMCLAW_API_URL", "https://default.example", values  # legacy-name-ok: test pins supported env fallback
            ),
            "https://default.example",
        )


class RepositoryContractTests(unittest.TestCase):
    def test_openclaw_config_is_valid_current_brand_json(self) -> None:
        config = json.loads((ROOT / "openclaw.json").read_text(encoding="utf-8"))
        server = config["mcp_servers"][0]
        self.assertEqual(server["name"], "caura")
        self.assertEqual(server["headers"]["X-API-Key"], "${CAURA_API_KEY}")
        self.assertEqual(server["url"], "http://localhost:8000/mcp")

    def test_dry_run_never_requires_gateway_or_caura(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "simulate.py",
                "--dry-run",
                "--days",
                "1",
                "9",
                "10",
                "--delay",
                "0",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Caura Long-Run Research Fleet", result.stdout)
        self.assertIn("Call caura_write", result.stdout)
        self.assertIn("DRY RUN -- would poll", result.stdout)
        self.assertNotIn("Sending prompt to gateway", result.stdout)

    def test_dry_run_uses_configured_fleet_id_in_every_prompt(self) -> None:
        env = dict(os.environ)
        env["CAURA_FLEET_ID"] = "configured-fleet"
        result = subprocess.run(
            [
                sys.executable,
                "simulate.py",
                "--dry-run",
                "--days",
                "1",
                "9",
                "10",
                "--delay",
                "0",
            ],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('fleet_ids: ["configured-fleet"]', result.stdout)
        self.assertIn('fleet_id: "configured-fleet"', result.stdout)
        self.assertIn("Memory pool: configured-fleet", result.stdout)
        self.assertNotIn('fleet_ids: ["fleet-longrun-research"]', result.stdout)

    def test_legacy_brand_gate_passes(self) -> None:
        result = subprocess.run(
            [sys.executable, "scripts/check_legacy_brand.py"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_local_link_gate_passes(self) -> None:
        result = subprocess.run(
            [sys.executable, "scripts/check_links.py"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_repository_settings_handoff_is_valid(self) -> None:
        result = subprocess.run(
            [sys.executable, "scripts/check_repository_settings.py"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_cross_agent_smoke_defaults_to_no_network(self) -> None:
        result = subprocess.run(
            [sys.executable, "scripts/cross_agent_smoke.py"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Dry run only. No network requests were made.", result.stdout)


class LauncherIntegrationTests(unittest.TestCase):
    def run_launcher(self, dotenv: str, expected_key: str) -> subprocess.CompletedProcess[str]:
        clean_env = dict(os.environ)
        clean_env.pop("CAURA_API_KEY", None)
        clean_env.pop("MEMCLAW_API_KEY", None)  # legacy-name-ok: test isolates supported env fallback
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as handle:
            handle.write(dotenv)
            env_path = Path(handle.name)
        try:
            child = (
                "import os,sys; "
                f"sys.exit(os.environ.get('CAURA_API_KEY') != {expected_key!r} "
                "or 'MEMCLAW_API_KEY' in os.environ)"  # legacy-name-ok: child must receive canonical env only
            )
            return subprocess.run(
                [
                    sys.executable,
                    "scripts/openclaw_with_caura_env.py",
                    "--env-file",
                    str(env_path),
                    "--config",
                    "openclaw.json",
                    "--",
                    sys.executable,
                    "-c",
                    child,
                ],
                cwd=ROOT,
                env=clean_env,
                capture_output=True,
                text=True,
                timeout=30,
            )
        finally:
            env_path.unlink()

    def test_canonical_key_wins_end_to_end(self) -> None:
        result = self.run_launcher(
            "CAURA_API_KEY=current-key\nMEMCLAW_API_KEY=legacy-key\n",  # legacy-name-ok: test pins supported env fallback
            "current-key",
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_blank_canonical_key_uses_legacy_fallback_end_to_end(self) -> None:
        result = self.run_launcher(
            "CAURA_API_KEY=\nMEMCLAW_API_KEY=legacy-key\n",  # legacy-name-ok: test pins supported env fallback
            "legacy-key",
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()

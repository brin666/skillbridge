"""Tests for the DeepSeek Harness (DSH) adapter.

Covers the multi-signal detection contract:

- ``dsh`` on PATH -> detected
- ``DSH_HOME`` pointing at a valid DSH Home -> detected
- default ``~/.dsh`` with real DSH signatures -> detected
- an empty ``~/.dsh`` -> NOT detected
- npx install without a global ``dsh`` executable but with a valid
  DSH Home -> detected
- ``~/.agents/skills`` is scanned
- Codex and DSH sharing one physical Skill path merge into a single
  Skill with both agents listed in ``installed_agents``
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.adapters.base import AgentAdapter
from backend.adapters.dsh import (
    DSH_HOME_SIGNATURES,
    DSHAdapter,
    is_valid_dsh_home,
    resolve_dsh_home,
)
from backend.core.agent_scanner import DEFAULT_ADAPTER_CLASSES, AgentScanner
from backend.core.preflight import PreflightChecker
from backend.core.skill_scanner import SkillScanner
from backend.models.agent import Agent


@contextmanager
def isolated_env(home: Path, dsh_home: str | None = None, extra: dict | None = None):
    """Isolate HOME/USERPROFILE/DSH_HOME for the duration of a test.

    ``DSH_HOME`` from the host environment is explicitly removed when
    ``dsh_home`` is None, because ``patch.dict(clear=False)`` only adds or
    overrides keys and would leak the host value into the test.
    """
    env = dict(extra or {})
    env["HOME"] = str(home)
    env["USERPROFILE"] = str(home)
    if dsh_home is not None:
        env["DSH_HOME"] = str(dsh_home)
    with mock.patch.dict(os.environ, env, clear=False):
        if dsh_home is None:
            os.environ.pop("DSH_HOME", None)
        yield


def make_valid_home(root: Path, signature: str = "profiles") -> Path:
    """Create a DSH Home that carries one real DSH signature."""
    home = root / "dsh-home"
    (home / signature).mkdir(parents=True, exist_ok=True)
    return home


def make_skill(root: Path, name: str, description: str = "Test description.") -> Path:
    skill_dir = root / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n",
        encoding="utf-8",
    )
    return skill_dir


class ResolveDshHomeTests(unittest.TestCase):
    def test_explicit_configuration_wins_over_env(self) -> None:
        configured = Path("C:/cfg/dsh")
        with mock.patch.dict(os.environ, {"DSH_HOME": "C:/env/dsh"}, clear=False):
            self.assertEqual(resolve_dsh_home(configured), configured)

    def test_env_wins_over_default(self) -> None:
        with mock.patch.dict(os.environ, {"DSH_HOME": "C:/env/dsh"}, clear=False):
            with mock.patch("pathlib.Path.home", return_value=Path("C:/users/tester")):
                self.assertEqual(resolve_dsh_home(), Path("C:/env/dsh"))

    def test_defaults_to_dot_dsh(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=False) as env:
            env.pop("DSH_HOME", None)
            with mock.patch("pathlib.Path.home", return_value=Path("C:/users/tester")):
                self.assertEqual(resolve_dsh_home(), Path("C:/users/tester/.dsh"))


class IsValidDshHomeTests(unittest.TestCase):
    def test_empty_or_missing_home_is_invalid(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertFalse(is_valid_dsh_home(root / "missing"))
            empty = root / "empty"
            empty.mkdir()
            self.assertFalse(is_valid_dsh_home(empty))

    def test_any_signature_marks_home_valid(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            for signature in DSH_HOME_SIGNATURES:
                with self.subTest(signature=signature):
                    home = Path(tmp) / signature.replace(".", "_")
                    (home / signature).mkdir(parents=True, exist_ok=True)
                    self.assertTrue(is_valid_dsh_home(home))


class DSHAdapterDetectionTests(unittest.TestCase):
    def test_detected_when_dsh_on_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            home.mkdir()
            with isolated_env(home), mock.patch("shutil.which", return_value=str(home / "dsh.exe")):
                adapter = DSHAdapter()
                self.assertTrue(adapter.detect())
                self.assertEqual(adapter.get_name(), "DeepSeek Harness")

    def test_detected_via_dsh_home_env(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            home.mkdir()
            dsh_home = make_valid_home(Path(tmp))
            with isolated_env(home, dsh_home=str(dsh_home)), mock.patch("shutil.which", return_value=None):
                self.assertTrue(DSHAdapter().detect())

    def test_detected_via_default_dot_dsh(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            (home / ".dsh" / "profiles").mkdir(parents=True)
            with isolated_env(home), mock.patch("shutil.which", return_value=None):
                self.assertTrue(DSHAdapter().detect())

    def test_empty_dot_dsh_is_not_detected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            (home / ".dsh").mkdir(parents=True)  # bare, no signatures
            with isolated_env(home), mock.patch("shutil.which", return_value=None):
                self.assertFalse(DSHAdapter().detect())

    def test_npx_install_without_dsh_exe_detected_via_home(self) -> None:
        # npx @deepseek-ai/dsh web leaves no global dsh.exe on PATH.
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            home.mkdir()
            dsh_home = make_valid_home(Path(tmp), signature="settings.yaml")
            with isolated_env(home, dsh_home=str(dsh_home)), mock.patch("shutil.which", return_value=None):
                adapter = DSHAdapter()
                self.assertTrue(adapter.detect())
                # Version detection failing must not affect installation state.
                self.assertIsNone(adapter.get_version())

    def test_detection_does_not_require_skill_roots(self) -> None:
        # A fresh DSH install has no ~/.agents/skills yet.
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            home.mkdir()
            dsh_home = make_valid_home(Path(tmp), signature="sessions")
            with isolated_env(home, dsh_home=str(dsh_home)), mock.patch("shutil.which", return_value=None):
                adapter = DSHAdapter()
                self.assertTrue(adapter.detect())
                self.assertEqual(adapter.get_skill_paths(), [])

    def test_explicit_dsh_home_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            home.mkdir()
            dsh_home = make_valid_home(Path(tmp))
            # No DSH_HOME env and no default ~/.dsh; only the explicit path.
            with isolated_env(home), mock.patch("shutil.which", return_value=None):
                adapter = DSHAdapter(dsh_home=dsh_home)
                self.assertTrue(adapter.detect())


class DSHAdapterSkillPathTests(unittest.TestCase):
    def test_agents_skills_is_scanned(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            skills_root = home / ".agents" / "skills"
            make_skill(skills_root, "pdf")
            dsh_home = make_valid_home(Path(tmp))
            with isolated_env(home, dsh_home=str(dsh_home)), mock.patch("shutil.which", return_value=None):
                adapter = DSHAdapter()
                self.assertTrue(adapter.detect())
                paths = adapter.get_skill_paths()
                self.assertEqual(paths, [str(skills_root.resolve())])
                skills = adapter.scan_skills()
                self.assertEqual([s.id for s in skills], ["pdf"])
                self.assertTrue(adapter.supports_skill(skills[0]))

    def test_capabilities_include_filesystem_shell_patch(self) -> None:
        self.assertEqual(DSHAdapter().capabilities(), ["filesystem", "shell", "patch"])


class DSHSharedSkillMergeTests(unittest.TestCase):
    def test_codex_and_dsh_merge_same_physical_skill(self) -> None:
        # Codex and DSH can both scan the same physical ~/.agents/skills
        # root. The unified Skill must be one entry whose installed_agents
        # contains both, and files must not be duplicated.
        with tempfile.TemporaryDirectory() as tmp:
            shared = Path(tmp) / "shared-skills"
            make_skill(shared, "pdf", "PDF tools")

            scanner = SkillScanner()
            skills = scanner.scan_agents(
                [
                    Agent(id="codex", name="Codex", installed=True, skill_paths=[str(shared)]),
                    Agent(id="dsh", name="DeepSeek Harness", installed=True, skill_paths=[str(shared)]),
                ]
            )
            self.assertEqual(len(skills), 1)
            skill = skills[0]
            self.assertEqual(skill.id, "pdf")
            self.assertEqual(sorted(skill.installed_agents), ["codex", "dsh"])
            self.assertEqual(skill.locations, {"codex": True, "dsh": True})
            self.assertEqual(skill.files.count("SKILL.md"), 1)


class DSHScannerIntegrationTests(unittest.TestCase):
    def test_scanner_registers_dsh_adapter(self) -> None:
        self.assertIn(DSHAdapter, DEFAULT_ADAPTER_CLASSES)

        scanner = AgentScanner()
        ids = {adapter.agent_id for adapter in scanner.adapters}
        self.assertIn("dsh", ids)
        dsh = next(a for a in scanner.adapters if a.agent_id == "dsh")
        self.assertIsInstance(dsh, AgentAdapter)
        self.assertEqual(dsh.get_name(), "DeepSeek Harness")

    def test_preflight_and_sync_resolve_dsh_adapter(self) -> None:
        # Target Agent "dsh" must resolve through the existing Preflight /
        # Safe Sync architecture without any DSH-specific copy logic.
        checker = PreflightChecker()
        adapter = checker._resolve_adapter("dsh")
        self.assertIsNotNone(adapter)
        self.assertEqual(adapter.agent_id, "dsh")
        self.assertEqual(adapter.get_name(), "DeepSeek Harness")


if __name__ == "__main__":
    unittest.main()

"""Tests for the install.sh and uninstall.sh lifecycle."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from ._helpers import INSTALL_SH, LITE_ROOT

UNINSTALL_SH = LITE_ROOT / "uninstall.sh"


def _has_bash_4plus() -> bool:
    """Probe whether the runtime bash is new enough to run install.sh.

    F62: install.sh (and uninstall.sh) require bash 4+ for `read -ra` and
    `arr+=()` syntax. macOS /bin/bash is 3.2.57 (last GPLv2), so the install
    script now exits early on macOS without a Homebrew bash upgrade. Tests
    that exercise the install/uninstall lifecycle should skip rather than
    fail when the host shell is too old — the behaviour under test is the
    bash script's logic, which itself enforces this same constraint at
    runtime. CI (Linux, bash 5.x) runs them; macOS dev runs skip them with
    a clear message instead of polluting the failure count.
    """
    try:
        out = subprocess.run(
            ["bash", "-c", 'echo "${BASH_VERSINFO[0]}"'],
            capture_output=True, text=True, timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return out.returncode == 0 and out.stdout.strip().isdigit() \
        and int(out.stdout.strip()) >= 4


class TestInstall(unittest.TestCase):
    def setUp(self) -> None:
        if not _has_bash_4plus():
            self.skipTest(
                "install.sh requires bash 4+ (F62); macOS /bin/bash is "
                "3.2.57. Install via `brew install bash` and re-run with "
                "/usr/local/bin/bash, or use Linux CI."
            )
        self.tmpdir = Path(tempfile.mkdtemp(prefix="trellis-install-"))

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _run_install(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["bash", str(INSTALL_SH), str(self.tmpdir), *args],
            capture_output=True,
            text=True,
            timeout=30,
        )

    def test_install_default_creates_runtime_and_agents(self) -> None:
        r = self._run_install("tester")
        self.assertEqual(r.returncode, 0, f"install failed: {r.stdout}\n{r.stderr}")
        self.assertTrue((self.tmpdir / ".trellis-lite").is_dir())
        self.assertTrue((self.tmpdir / "AGENTS.md").is_file())
        # init should have been called — .developer present
        self.assertTrue((self.tmpdir / ".trellis-lite/.developer").is_file())

    def test_install_claude_only(self) -> None:
        r = self._run_install("tester", "--platforms", "claude")
        self.assertEqual(r.returncode, 0)
        self.assertTrue((self.tmpdir / "CLAUDE.md").is_file())
        self.assertFalse((self.tmpdir / "AGENTS.md").exists())
        self.assertFalse((self.tmpdir / ".clinerules").exists())

    def test_install_cline_only(self) -> None:
        r = self._run_install("tester", "--platforms", "cline")
        self.assertEqual(r.returncode, 0)
        self.assertTrue((self.tmpdir / ".clinerules/trellis-lite.md").is_file())
        self.assertFalse((self.tmpdir / "CLAUDE.md").exists())
        self.assertFalse((self.tmpdir / ".qoder").exists())

    # ---- Platform parity: agents / commands / skills deployment ----------

    QODER_AGENTS = ("trellis-brainstorm.md", "trellis-implement.md", "trellis-check.md")
    QODER_SKILLS = ("trellis-brainstorm", "trellis-before-dev", "trellis-check", "trellis-update-spec")
    # Py-command skill wrappers: one per trellis.py subcommand except check
    # (the deep-workflow skill owns that name).
    QODER_COMMAND_SKILLS = ("trellis-context", "trellis-new", "trellis-start", "trellis-finish",
                            "trellis-archive", "trellis-doctor", "trellis-cancel", "trellis-list")
    TRELLIS_COMMANDS = ("context", "new", "start", "check", "finish", "archive", "doctor", "cancel", "list")

    def test_install_qoder_deploys_agents_and_skills(self) -> None:
        """--platforms qoder must ship 3 agents + 12 generated SKILL.md wrappers.

        4 deep-workflow skills are generated from the runtime
        .trellis-lite/skills/*.md bodies; 8 py-command wrappers are generated
        from templates/claude/commands/trellis-*.md (single command-map body
        source, shared with claude/opencode). Together they give Qoder the
        same /trellis-* slash entries as the other platforms.
        """
        r = self._run_install("tester", "--platforms", "qoder")
        self.assertEqual(r.returncode, 0, f"install failed: {r.stdout}\n{r.stderr}")
        for agent in self.QODER_AGENTS:
            self.assertTrue(
                (self.tmpdir / ".qoder/agents" / agent).is_file(),
                f".qoder/agents/{agent} must be installed",
            )
        for skill in self.QODER_SKILLS:
            skill_md = self.tmpdir / ".qoder/skills" / skill / "SKILL.md"
            self.assertTrue(skill_md.is_file(), f".qoder/skills/{skill}/SKILL.md must be generated")
            # Generated wrapper = frontmatter (name) + verbatim body from
            # .trellis-lite/skills/<name>.md. Assert both halves.
            content = skill_md.read_text()
            self.assertIn(f"name: {skill}", content)
            # Descriptions contain ': ' so the frontmatter must use a YAML
            # block scalar — strict parsers reject ': ' in plain scalars.
            self.assertIn("description: |", content)
            body = (self.tmpdir / ".trellis-lite/skills" / f"{skill.removeprefix('trellis-')}.md").read_text()
            self.assertIn(body, content, "SKILL.md must embed the verbatim skill body")
        # Py-command wrappers: byte-exact reconstruction against the Claude
        # source — frontmatter rebuilt (name + block-scalar description)
        # around the verbatim body.
        for cmd in self.QODER_COMMAND_SKILLS:
            skill_md = self.tmpdir / ".qoder/skills" / cmd / "SKILL.md"
            self.assertTrue(skill_md.is_file(), f".qoder/skills/{cmd}/SKILL.md must be generated")
            claude = (LITE_ROOT / "templates/claude/commands" / f"{cmd}.md").read_text()
            # body = everything the install awk keeps: one leading newline
            # is the closing '---' line terminator, which awk strips.
            _, front, body = claude.split("---", 2)
            body = body.removeprefix("\n")
            desc = next(
                line[len("description:"):].strip()
                for line in front.splitlines()
                if line.startswith("description:")
            )
            expected = (
                "---\n"
                f"name: {cmd}\n"
                "description: |\n"
                f"  {desc}\n"
                "---\n"
                f"{body}"
            )
            self.assertEqual(expected, skill_md.read_text(),
                             f"{cmd}/SKILL.md must rewrap the Claude body verbatim")
        # Exactly 12 skill dirs: 4 deep-workflow + 8 command wrappers, and no
        # duplicate trellis-check variant (the deep-workflow skill owns it).
        skill_dirs = sorted(p.name for p in (self.tmpdir / ".qoder/skills").iterdir() if p.is_dir())
        self.assertEqual(
            sorted(self.QODER_SKILLS + self.QODER_COMMAND_SKILLS),
            skill_dirs,
            ".qoder/skills must hold exactly the 12 trellis entries",
        )
        # Other platforms' artifacts must NOT be present
        self.assertFalse((self.tmpdir / ".opencode").exists())
        self.assertFalse((self.tmpdir / ".claude").exists())
        self.assertFalse((self.tmpdir / ".cline").exists())

    def test_install_cline_deploys_skills(self) -> None:
        """--platforms cline must ship .clinerules + 12 generated SKILL.md.

        Cline has no agents mechanism and no commands dir — skills under
        .cline/skills/ are its slash entries (/skill-name or description
        match), generated by the same install loop that serves Qoder.
        Byte-correctness is covered transitively: the qoder test asserts
        each wrapper against its source byte-for-byte, and the joint
        qoder+cline test below asserts the two platforms' wrappers are
        byte-identical — so cline wrappers matching qoder's are correct.
        """
        r = self._run_install("tester", "--platforms", "cline")
        self.assertEqual(r.returncode, 0, f"install failed: {r.stdout}\n{r.stderr}")
        self.assertTrue((self.tmpdir / ".clinerules/trellis-lite.md").is_file())
        for entry in self.QODER_SKILLS + self.QODER_COMMAND_SKILLS:
            skill_md = self.tmpdir / ".cline/skills" / entry / "SKILL.md"
            self.assertTrue(skill_md.is_file(), f".cline/skills/{entry}/SKILL.md must be generated")
        # Exactly 12 trellis-* dirs, nothing else
        skill_dirs = sorted(p.name for p in (self.tmpdir / ".cline/skills").iterdir() if p.is_dir())
        self.assertEqual(
            sorted(self.QODER_SKILLS + self.QODER_COMMAND_SKILLS),
            skill_dirs,
            ".cline/skills must hold exactly the 12 trellis entries",
        )
        # Cline gets no agents dir (no such mechanism) and no other platform
        # artifacts
        self.assertFalse((self.tmpdir / ".cline/agents").exists())
        self.assertFalse((self.tmpdir / ".qoder").exists())
        self.assertFalse((self.tmpdir / ".opencode").exists())
        self.assertFalse((self.tmpdir / ".claude").exists())

    def test_install_qoder_and_cline_skills_identical(self) -> None:
        """Both skills platforms must get byte-identical wrappers.

        install.sh runs ONE generation loop over every skills-platform
        target dir (.qoder/skills + .cline/skills), so the two installs
        must agree byte-for-byte on every one of the 12 SKILL.md files.
        """
        r = self._run_install("tester", "--platforms", "qoder,cline")
        self.assertEqual(r.returncode, 0, f"install failed: {r.stdout}\n{r.stderr}")
        self.assertTrue((self.tmpdir / "AGENTS.md").is_file())
        self.assertTrue((self.tmpdir / ".clinerules/trellis-lite.md").is_file())
        for entry in self.QODER_SKILLS + self.QODER_COMMAND_SKILLS:
            qoder_md = (self.tmpdir / ".qoder/skills" / entry / "SKILL.md").read_text()
            cline_md = (self.tmpdir / ".cline/skills" / entry / "SKILL.md").read_text()
            self.assertEqual(
                qoder_md, cline_md,
                f"{entry}/SKILL.md must be byte-identical across qoder and cline",
            )

    def test_install_claude_deploys_trellis_commands(self) -> None:
        """--platforms claude must ship the 9 flat trellis-*.md command files."""
        r = self._run_install("tester", "--platforms", "claude")
        self.assertEqual(r.returncode, 0, f"install failed: {r.stdout}\n{r.stderr}")
        for cmd in self.TRELLIS_COMMANDS:
            self.assertTrue(
                (self.tmpdir / ".claude/commands" / f"trellis-{cmd}.md").is_file(),
                f".claude/commands/trellis-{cmd}.md must be installed",
            )
        # Flat names only — no trellis/ subdirectory namespace
        self.assertFalse((self.tmpdir / ".claude/commands/trellis").exists())
        # No agents/commands dirs for other platforms
        self.assertFalse((self.tmpdir / ".qoder").exists())
        self.assertFalse((self.tmpdir / ".opencode").exists())

    def test_install_opencode_deploys_agents_and_commands(self) -> None:
        """--platforms opencode must ship 3 agents + 9 command files."""
        r = self._run_install("tester", "--platforms", "opencode")
        self.assertEqual(r.returncode, 0, f"install failed: {r.stdout}\n{r.stderr}")
        for agent in self.QODER_AGENTS:
            self.assertTrue(
                (self.tmpdir / ".opencode/agents" / agent).is_file(),
                f".opencode/agents/{agent} must be installed",
            )
        for cmd in self.TRELLIS_COMMANDS:
            self.assertTrue(
                (self.tmpdir / ".opencode/commands" / f"trellis-{cmd}.md").is_file(),
                f".opencode/commands/trellis-{cmd}.md must be installed",
            )
        self.assertFalse((self.tmpdir / ".qoder").exists())
        self.assertFalse((self.tmpdir / ".claude").exists())

    def test_install_cleans_template_runtime_files(self) -> None:
        """If the template was committed with stray runtime state, install must wipe it."""
        template_runtime = LITE_ROOT / ".trellis-lite"
        # Plant a stale .developer — install should remove it before init rewrites
        stale = template_runtime / ".developer"
        had_stale = stale.is_file()
        if not had_stale:
            stale.write_text("name=stale\n")
        try:
            r = self._run_install("tester")
            self.assertEqual(r.returncode, 0)
            # After install, .developer must reflect the new init (tester), not stale
            installed_dev = self.tmpdir / ".trellis-lite/.developer"
            self.assertTrue(installed_dev.is_file())
            self.assertIn("tester", installed_dev.read_text())
        finally:
            if not had_stale:
                stale.unlink(missing_ok=True)

    # ---- O16 coverage: re-install must not clobber existing .developer -----

    def test_install_preserves_existing_developer_on_reinstall(self) -> None:
        """O16: re-running install.sh on an already-initialized project must
        NOT silently overwrite the existing developer name. Only a fresh
        install (no .developer) runs init; subsequent installs skip it so
        users who changed their developer name explicitly are not surprised.
        """
        # First install — seeds .developer=tester
        r1 = self._run_install("tester")
        self.assertEqual(r1.returncode, 0, f"first install failed: {r1.stdout}\n{r1.stderr}")
        dev_file = self.tmpdir / ".trellis-lite/.developer"
        self.assertEqual(dev_file.read_text().strip(), "name=tester")

        # Second install with a different name — .developer must survive
        r2 = self._run_install("someone-else")
        self.assertEqual(r2.returncode, 0, f"second install failed: {r2.stdout}\n{r2.stderr}")
        self.assertEqual(
            dev_file.read_text().strip(),
            "name=tester",
            "second install must not overwrite existing .developer",
        )
        # And install should have surfaced a note about the skip.
        self.assertIn(".developer already set", r2.stdout)

    # ---- Docs/ deployment (reference material for agents and users) -----

    def test_install_deploys_docs(self) -> None:
        """Install must copy docs/ into the target with the uninstall marker."""
        r = self._run_install("tester")
        self.assertEqual(r.returncode, 0, f"install failed: {r.stdout}\n{r.stderr}")
        self.assertTrue((self.tmpdir / "docs").is_dir(), "docs/ must be created")
        # Marker file so uninstall can distinguish Trellis docs from a
        # pre-existing user docs/ dir.
        self.assertTrue(
            (self.tmpdir / "docs" / ".trellis-docs").is_file(),
            ".trellis-docs marker must be present",
        )
        # Sanity: at least one known doc shipped
        self.assertTrue(
            (self.tmpdir / "docs" / "best-practices.md").is_file(),
            "best-practices.md must ship in docs/",
        )

    def test_install_skips_existing_docs(self) -> None:
        """A pre-existing user docs/ dir must be preserved, not clobbered."""
        # Seed a user docs/ before install
        user_docs = self.tmpdir / "docs"
        user_docs.mkdir()
        keeper = user_docs / "my-notes.md"
        keeper.write_text("# My own docs\n")

        r = self._run_install("tester")
        self.assertEqual(r.returncode, 0, f"install failed: {r.stdout}\n{r.stderr}")
        self.assertIn("already exists", r.stdout)
        # User's file must survive untouched (no marker written by install)
        self.assertTrue(keeper.exists(), "user's docs/ content must be preserved")
        self.assertFalse(
            (user_docs / ".trellis-docs").exists(),
            "install must not write the marker into a pre-existing user docs/",
        )


class TestTemplates(unittest.TestCase):
    """Template-source invariants that need neither bash 4+ nor an install run."""

    COMMANDS = ("context", "new", "start", "check", "finish", "archive", "doctor", "cancel", "list")
    AGENTS = ("trellis-brainstorm.md", "trellis-implement.md", "trellis-check.md")

    def test_claude_and_opencode_commands_share_body(self) -> None:
        """Each opencode command must be byte-identical to its claude twin
        except for the allowed-tools frontmatter line, so the two sets can
        never drift apart when edited by hand. Claude bodies must use the
        flat /trellis-<cmd> spelling throughout (no /trellis: leftovers).
        """
        for cmd in self.COMMANDS:
            claude = (LITE_ROOT / "templates/claude/commands" / f"trellis-{cmd}.md").read_text()
            opencode = (LITE_ROOT / "templates/opencode/commands" / f"trellis-{cmd}.md").read_text()
            self.assertNotIn("/trellis:", claude, f"claude trellis-{cmd}.md still references /trellis:")
            expected = "".join(
                line for line in claude.splitlines(keepends=True)
                if not line.startswith("allowed-tools:")
            )
            self.assertEqual(
                expected, opencode,
                f"templates/opencode/commands/trellis-{cmd}.md drifted from "
                f"templates/claude/commands/trellis-{cmd}.md",
            )

    def test_agent_frontmatter_descriptions_avoid_plain_colon(self) -> None:
        """Plain-scalar YAML descriptions must not contain ': ' — the
        frontmatter is the machine-readable part and strict parsers
        (js-yaml/PyYAML/libyaml) reject it. Block scalars are exempt.
        """
        for plat in ("qoder", "opencode"):
            for agent in self.AGENTS:
                text = (LITE_ROOT / "templates" / plat / "agents" / agent).read_text()
                parts = text.split("---", 2)
                self.assertGreaterEqual(len(parts), 3, f"{plat}/agents/{agent}: missing frontmatter")
                for line in parts[1].splitlines():
                    if line.startswith("description:"):
                        value = line[len("description:"):].strip()
                        if not value.startswith(("|", ">")):
                            self.assertNotIn(
                                ": ", value,
                                f"{plat}/agents/{agent}: plain-scalar description "
                                "contains ': ' (invalid YAML)",
                            )


class TestUninstall(unittest.TestCase):
    def setUp(self) -> None:
        # F62: even though uninstall.sh itself is bash-3.2 safe, the
        # install_all() seed step below runs install.sh which gates on bash
        # 4+. Without this skip, every TestUninstall test errors out at
        # setUp because install cannot complete on macOS bash 3.2.
        if not _has_bash_4plus():
            self.skipTest(
                "install.sh requires bash 4+ (F62); TestUninstall setUp "
                "seeds with install.sh, so the whole class needs bash 4+."
            )
        self.tmpdir = Path(tempfile.mkdtemp(prefix="trellis-uninstall-"))
        # Initialize as a git repo so install.sh triggers the pre-commit hook
        # installation step (O9 fix path). Without .git/, install.sh silently
        # skips the hook step, leaving the uninstall cleanup code untested.
        result = subprocess.run(
            ["git", "init", "-q"],
            cwd=str(self.tmpdir), capture_output=True, text=True, timeout=10,
        )
        # If git isn't available or sandboxed, skip the entire class — without
        # .git/ the install script doesn't trigger hook installation, so the
        # tests that depend on hook cleanup would silently degrade to no-ops
        # and produce false positives.
        if result.returncode != 0:
            self.skipTest(
                f"git init failed (rc={result.returncode}); "
                f"TestUninstall requires git to seed .git/. stderr={result.stderr!r}"
            )
        # Seed .gitignore so install.sh triggers the runtime-files step
        # (it checks existence of .gitignore before adding entries).
        (self.tmpdir / ".gitignore").write_text("node_modules/\n")

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _run_uninstall(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["bash", str(UNINSTALL_SH), *args],
            cwd=str(self.tmpdir),
            capture_output=True,
            text=True,
            timeout=30,
        )

    def _install_all(self) -> None:
        subprocess.run(
            ["bash", str(INSTALL_SH), str(self.tmpdir), "tester", "--platforms", "all"],
            capture_output=True, text=True, timeout=30, check=True,
        )

    def test_uninstall_removes_runtime_and_entries(self) -> None:
        self._install_all()
        # Sanity: install populated everything
        for p in (".trellis-lite", "AGENTS.md", "CLAUDE.md", ".clinerules"):
            self.assertTrue((self.tmpdir / p).exists(), f"{p} should exist post-install")

        r = self._run_uninstall(str(self.tmpdir))
        self.assertEqual(r.returncode, 0, f"uninstall failed: {r.stdout}\n{r.stderr}")

        # Runtime and platform entries must be gone
        for p in (".trellis-lite", "AGENTS.md", "CLAUDE.md", ".clinerules"):
            self.assertFalse((self.tmpdir / p).exists(), f"{p} should be removed post-uninstall")

    # ---- Platform parity: agents / commands / skills cleanup -------------

    def test_uninstall_removes_platform_agent_and_command_dirs(self) -> None:
        """uninstall must remove .qoder/ (agents+skills), .cline/skills/,
        .opencode/ (agents+commands) and .claude/commands/ trellis-*
        commands — the full set install.sh deploys for platform parity —
        and take empty parent dirs with it.
        """
        self._install_all()
        # Sanity: the platform-parity artifacts exist post-install
        self.assertTrue((self.tmpdir / ".qoder/agents/trellis-implement.md").is_file())
        self.assertTrue((self.tmpdir / ".qoder/skills/trellis-check/SKILL.md").is_file())
        self.assertTrue((self.tmpdir / ".qoder/skills/trellis-context/SKILL.md").is_file())
        self.assertTrue((self.tmpdir / ".cline/skills/trellis-check/SKILL.md").is_file())
        self.assertTrue((self.tmpdir / ".cline/skills/trellis-context/SKILL.md").is_file())
        self.assertTrue((self.tmpdir / ".opencode/agents/trellis-implement.md").is_file())
        self.assertTrue((self.tmpdir / ".opencode/commands/trellis-context.md").is_file())
        self.assertTrue((self.tmpdir / ".claude/commands/trellis-context.md").is_file())

        r = self._run_uninstall(str(self.tmpdir))
        self.assertEqual(r.returncode, 0, f"uninstall failed: {r.stdout}\n{r.stderr}")

        # Platform dirs must be gone entirely (empty parents pruned)
        self.assertFalse((self.tmpdir / ".qoder").exists(), ".qoder/ must be removed")
        self.assertFalse((self.tmpdir / ".cline").exists(), ".cline/ must be removed")
        self.assertFalse((self.tmpdir / ".opencode").exists(), ".opencode/ must be removed")
        self.assertFalse((self.tmpdir / ".claude").exists(), ".claude/ must be removed")

    def test_uninstall_keeps_user_platform_files(self) -> None:
        """Only the trellis-* namespace is ours — user-created agents/skills/
        commands in the same platform dirs must survive uninstall.
        """
        self._install_all()
        user_agent = self.tmpdir / ".qoder/agents/my-own-agent.md"
        user_agent.parent.mkdir(parents=True, exist_ok=True)
        user_agent.write_text("---\nname: my-own-agent\n---\ncustom agent\n")
        user_skill = self.tmpdir / ".qoder/skills/my-own-skill/SKILL.md"
        user_skill.parent.mkdir(parents=True, exist_ok=True)
        user_skill.write_text("---\nname: my-own-skill\n---\ncustom skill\n")
        user_cline_skill = self.tmpdir / ".cline/skills/my-own-skill/SKILL.md"
        user_cline_skill.parent.mkdir(parents=True, exist_ok=True)
        user_cline_skill.write_text("---\nname: my-own-skill\n---\ncustom skill\n")
        user_oc_cmd = self.tmpdir / ".opencode/commands/my-own-command.md"
        user_oc_cmd.parent.mkdir(parents=True, exist_ok=True)
        user_oc_cmd.write_text("---\ndescription: mine\n---\ncustom command\n")
        user_cl_cmd = self.tmpdir / ".claude/commands/my-own-command.md"
        user_cl_cmd.parent.mkdir(parents=True, exist_ok=True)
        user_cl_cmd.write_text("---\ndescription: mine\n---\ncustom command\n")

        r = self._run_uninstall(str(self.tmpdir))
        self.assertEqual(r.returncode, 0, f"uninstall failed: {r.stdout}\n{r.stderr}")

        # Trellis artifacts gone, user files intact, non-empty dirs kept
        self.assertFalse((self.tmpdir / ".qoder/agents/trellis-brainstorm.md").exists())
        self.assertFalse((self.tmpdir / ".qoder/skills/trellis-check").exists())
        self.assertFalse((self.tmpdir / ".cline/skills/trellis-check").exists())
        self.assertFalse((self.tmpdir / ".opencode/commands/trellis-context.md").exists())
        self.assertFalse((self.tmpdir / ".claude/commands/trellis-context.md").exists())
        self.assertTrue(user_agent.is_file(), "user's .qoder/agents file must survive")
        self.assertTrue(user_skill.is_file(), "user's .qoder/skills file must survive")
        self.assertTrue(user_cline_skill.is_file(), "user's .cline/skills file must survive")
        self.assertTrue(user_oc_cmd.is_file(), "user's .opencode/commands file must survive")
        self.assertTrue(user_cl_cmd.is_file(), "user's .claude/commands file must survive")
        # .opencode had only commands; agents+trellis commands are gone but
        # the dir survives because my-own-command.md keeps it non-empty
        # (same for .claude/commands)
        self.assertTrue((self.tmpdir / ".opencode/commands").is_dir())
        self.assertTrue((self.tmpdir / ".claude/commands").is_dir())

    def test_uninstall_refuses_when_nothing_installed(self) -> None:
        """Empty dir with no Trellis artifacts must be rejected, not silently OK."""
        r = self._run_uninstall(str(self.tmpdir))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("does not appear to have Trellis Lite installed", r.stdout + r.stderr)

    def test_uninstall_default_target_is_cwd(self) -> None:
        """When called without args, uninstall operates on cwd."""
        self._install_all()
        # Run uninstall from inside the project, with no args
        r = subprocess.run(
            ["bash", str(UNINSTALL_SH)],
            cwd=str(self.tmpdir),
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(r.returncode, 0)
        self.assertFalse((self.tmpdir / ".trellis-lite").exists())

    def test_uninstall_keeps_other_files(self) -> None:
        """Uninstall must not touch unrelated files."""
        self._install_all()
        # Create a marker file
        marker = self.tmpdir / "user_data.txt"
        marker.write_text("important data")

        r = self._run_uninstall(str(self.tmpdir))
        self.assertEqual(r.returncode, 0)
        self.assertTrue(marker.exists(), "uninstall must not delete unrelated files")
        self.assertEqual(marker.read_text(), "important data")

    # ---- O9 coverage: .gitignore cleanup + pre-commit hook removal ------

    def test_uninstall_removes_gitignore_entries(self) -> None:
        """O9: uninstall must clean up the Trellis block in .gitignore added by install.sh."""
        self._install_all()
        gitignore = self.tmpdir / ".gitignore"
        # Sanity: install populated the .gitignore block
        content_before = gitignore.read_text()
        self.assertIn("# Trellis Lite runtime", content_before)
        self.assertIn(".trellis-lite/.developer", content_before)
        self.assertIn(".trellis-lite/.current-task", content_before)

        r = self._run_uninstall(str(self.tmpdir))
        self.assertEqual(r.returncode, 0, f"uninstall failed: {r.stdout}\n{r.stderr}")
        # Marker comment and Trellis entries must be gone
        content_after = gitignore.read_text()
        self.assertNotIn("# Trellis Lite runtime", content_after)
        self.assertNotIn(".trellis-lite/.developer", content_after)
        self.assertNotIn(".trellis-lite/.current-task", content_after)

    def test_uninstall_keeps_user_gitignore_entries(self) -> None:
        """Uninstall must preserve the user's own .gitignore entries."""
        self._install_all()
        gitignore = self.tmpdir / ".gitignore"
        # Append more user content AFTER the Trellis block
        with gitignore.open("a") as f:
            f.write("my-app/dist/\n")
            f.write("*.bak\n")

        r = self._run_uninstall(str(self.tmpdir))
        self.assertEqual(r.returncode, 0)
        content = gitignore.read_text()
        # User entries (before and after the Trellis block) must survive
        self.assertIn("node_modules/", content)
        self.assertIn("my-app/dist/", content)
        self.assertIn("*.bak", content)
        # Trellis block must be cleaned up
        self.assertNotIn("# Trellis Lite runtime", content)
        self.assertNotIn(".trellis-lite/.developer", content)
        self.assertNotIn(".trellis-lite/.current-task", content)

    def test_uninstall_removes_precommit_hook(self) -> None:
        """O9: uninstall must remove the pre-commit hook installed by install.sh."""
        self._install_all()
        hook = self.tmpdir / ".git/hooks/pre-commit"
        # Sanity: install populated the hook
        self.assertTrue(hook.is_file())
        self.assertIn("Trellis Lite", hook.read_text())

        r = self._run_uninstall(str(self.tmpdir))
        self.assertEqual(r.returncode, 0)
        self.assertFalse(hook.exists(), "Trellis's pre-commit hook must be removed")

    def test_uninstall_keeps_user_precommit_hook(self) -> None:
        """Uninstall must not touch a pre-commit hook that's NOT Trellis's."""
        self._install_all()  # Installs the Trellis hook first
        # Then the user overwrites it with their own hook (no "Trellis Lite" marker)
        hook = self.tmpdir / ".git/hooks/pre-commit"
        hook.write_text("#!/usr/bin/env bash\necho 'user hook — runs my linter'\n")
        hook.chmod(0o755)

        r = self._run_uninstall(str(self.tmpdir))
        self.assertEqual(r.returncode, 0)
        # User's hook must survive (uninstall only removes hooks containing "Trellis Lite")
        self.assertTrue(hook.exists(), "user's pre-commit hook must not be removed")
        self.assertNotIn("Trellis Lite", hook.read_text())

    # ---- Docs/ removal (marker-gated) ------

    def test_uninstall_removes_docs(self) -> None:
        """Uninstall must remove docs/ that install.sh deployed (marker present)."""
        self._install_all()
        docs = self.tmpdir / "docs"
        self.assertTrue(docs.is_dir(), "docs/ should exist post-install")
        self.assertTrue((docs / ".trellis-docs").is_file(), "marker should exist post-install")

        r = self._run_uninstall(str(self.tmpdir))
        self.assertEqual(r.returncode, 0, f"uninstall failed: {r.stdout}\n{r.stderr}")
        self.assertFalse(docs.exists(), "deployed docs/ must be removed on uninstall")

    def test_uninstall_keeps_user_docs(self) -> None:
        """Uninstall must NOT remove a pre-existing user docs/ (no marker)."""
        # Seed a user docs/ with no marker BEFORE install (install then skips it)
        user_docs = self.tmpdir / "docs"
        user_docs.mkdir()
        keeper = user_docs / "my-notes.md"
        keeper.write_text("# My own docs\n")

        self._install_all()  # install skips docs/ (already exists)
        self.assertFalse(
            (user_docs / ".trellis-docs").exists(),
            "install must not write marker into pre-existing user docs/",
        )

        r = self._run_uninstall(str(self.tmpdir))
        self.assertEqual(r.returncode, 0, f"uninstall failed: {r.stdout}\n{r.stderr}")
        # User docs/ must survive — no marker means uninstall must not touch it
        self.assertTrue(user_docs.is_dir(), "user docs/ must not be removed")
        self.assertTrue(keeper.exists(), "user docs/ content must be preserved")

    # ---- O11 coverage: user-edited .gitignore block -------------------

    def test_uninstall_handles_user_edited_gitignore(self) -> None:
        """O11 regression: user comments/blanks between Trellis entries must NOT
        prevent cleanup of subsequent .trellis-lite/.X lines.

        Install normally first (so uninstall accepts the directory), then
        mutate the .gitignore to inject a user comment + blank line between
        the two runtime entries. The original awk reset `skip` on every
        non-matching line, which leaked the second entry. The fix keeps
        skip=1 across intervening user lines.
        """
        # Install normally — populates .gitignore block + runtime + platforms
        self._install_all()
        gitignore = self.tmpdir / ".gitignore"
        original = gitignore.read_text()
        # Sanity: install wrote both entries contiguously
        self.assertIn(".trellis-lite/.developer\n.trellis-lite/.current-task", original)

        # Simulate a user editing the block: insert a comment + blank line
        # between the two Trellis-managed entries.
        edited = original.replace(
            ".trellis-lite/.developer\n.trellis-lite/.current-task",
            ".trellis-lite/.developer\n# user-added note between entries\n\n.trellis-lite/.current-task",
        )
        self.assertNotEqual(edited, original, "test precondition: replacement should mutate content")
        gitignore.write_text(edited, encoding="utf-8")

        r = self._run_uninstall(str(self.tmpdir))
        self.assertEqual(r.returncode, 0, f"uninstall failed: {r.stdout}\n{r.stderr}")
        content = gitignore.read_text()
        # All Trellis runtime lines must be gone (the regression manifested here)
        self.assertNotIn(".trellis-lite/.developer", content)
        self.assertNotIn(".trellis-lite/.current-task", content)
        self.assertNotIn("# Trellis Lite runtime", content)
        # User content (before, between, and after the block) must survive
        self.assertIn("node_modules/", content)
        self.assertIn("user-added note between entries", content)

    # ---- O14 coverage: grep must be anchored (false-positive guard) -----

    def test_uninstall_ignores_non_marker_mentions(self) -> None:
        """O14: a user comment that merely mentions 'Trellis Lite runtime' in
        prose must NOT be confused with the real marker comment.

        The original grep -q "# Trellis Lite runtime" matched anywhere in the
        file, so a line like '# Trellis Lite runtime monitoring explained'
        would falsely trigger the cleanup branch and print a misleading
        'removed Trellis Lite runtime entries' message even though nothing
        was actually changed. The fix anchors the grep (-x) and makes it
        literal (-F) so only the exact marker line enters the branch.
        """
        self._install_all()
        gitignore = self.tmpdir / ".gitignore"
        # Replace the real marker with a prose mention that happens to
        # contain the same substring (so unanchored grep would match).
        original = gitignore.read_text()
        self.assertIn("# Trellis Lite runtime\n", original)
        edited = original.replace(
            "# Trellis Lite runtime\n",
            "# Trellis Lite runtime monitoring explained below\n",
        )
        self.assertNotEqual(edited, original, "sanity: replacement should mutate")
        gitignore.write_text(edited, encoding="utf-8")

        r = self._run_uninstall(str(self.tmpdir))
        self.assertEqual(r.returncode, 0, f"uninstall failed: {r.stdout}\n{r.stderr}")
        # The .gitignore must NOT have been touched — the prose mention is
        # not a real marker, so neither the marker nor the runtime entries
        # should be removed.
        content = gitignore.read_text()
        self.assertIn("# Trellis Lite runtime monitoring explained below", content)
        self.assertIn(".trellis-lite/.developer", content)
        self.assertIn(".trellis-lite/.current-task", content)
        # And uninstall must not have printed the misleading "removed" line.
        self.assertNotIn("✓ .gitignore (removed Trellis Lite runtime entries)", r.stdout)
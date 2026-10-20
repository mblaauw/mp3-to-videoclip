"""Production-crew routing, role permissions, root loop contract and bootstrap safety.

No provider is contacted, no skill is loaded and no paid tool is called.
"""

import ast
import fnmatch
import hashlib
import importlib.util
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT / "opencode.json").read_text())
AGENTS = (
    "film-director",
    "music-editor",
    "short-film-writer",
    "visual-director",
    "visual-critic",
    "post-editor",
    "film-finisher",
)
SPECIALISTS = AGENTS[1:]
STAGES = (
    "clip-music-analysis",
    "clip-story",
    "clip-storyboard",
    "clip-art-direction",
    "clip-image-prompts",
    "clip-image-production",
    "clip-visual-review",
    "clip-edit-graphics",
    "clip-delivery",
)
SCRIPT = ROOT / "scripts/bootstrap_production.py"


def bootstrap_module():
    spec = importlib.util.spec_from_file_location("bootstrap_production", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def effective(permissions, action, resource):
    """Replay last-matching-wins wildcard rules the way the runtime resolves them."""
    effect = "unspecified"
    for rule in permissions:
        if fnmatch.fnmatchcase(action, rule["action"]) and fnmatch.fnmatchcase(
            resource, rule["resource"]
        ):
            effect = rule["effect"]
    return effect


def snapshot(root):
    return {
        str(p.relative_to(root)): (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns)
        for p in root.rglob("*")
        if p.is_file()
    }


def make_bundle(root, revision):
    """A minimal but valid production bundle: root files, original skills, cached recipes."""
    for name in ("LOOP.md", "AGENTS.md", "opencode.json"):
        shutil.copy2(ROOT / name, root / name)
    (root / "scripts").mkdir(parents=True, exist_ok=True)
    shutil.copy2(SCRIPT, root / "scripts" / SCRIPT.name)
    for name in ("clip-music-director", *STAGES):
        skill = root / ".opencode/skills" / name
        skill.mkdir(parents=True, exist_ok=True)
        (skill / "SKILL.md").write_text(f"---\nname: {name}\n---\nbody\n")
    vendor = root / ".opencode/vendor/runware-skills"
    (vendor / ".git").mkdir(parents=True, exist_ok=True)
    (vendor / ".git/HEAD").write_text(revision + "\n")
    for name in (
        "runware-run",
        "runware-models",
        "runware-prompting",
        "photoreal-stills",
        "character-consistency",
    ):
        recipe = vendor / "skills" / name
        recipe.mkdir(parents=True, exist_ok=True)
        (recipe / "SKILL.md").write_text(f"---\nname: {name}\n---\nrecipe\n")


def run_check(root):
    return subprocess.run(
        [sys.executable, f"scripts/{SCRIPT.name}", "--check"],
        cwd=root,
        capture_output=True,
        text=True,
    )


def test_loop_is_loaded_and_film_director_is_the_project_default():
    assert CONFIG["instructions"] == ["LOOP.md"]
    loop = (ROOT / "LOOP.md").read_text()
    assert len(loop.splitlines()) <= 120
    assert CONFIG["default_agent"] == "film-director"
    agents = CONFIG["agents"]
    assert set(agents) == set(AGENTS)
    assert agents["film-director"]["mode"] == "primary"
    systems = []
    for name in AGENTS:
        entry = agents[name]
        assert entry["description"] and entry["system"] and entry["permissions"]
        assert entry["mode"] == ("primary" if name == "film-director" else "subagent")
        assert "model" not in entry, "inherit the selected authenticated model"
        assert "clip-" in entry["system"], f"{name} must reference the existing stage skills"
        systems.append(entry["system"])
    assert len(set(systems)) == len(AGENTS), "each role needs its own production prompt"
    assert not (ROOT / "agent").exists(), "agents stay inline in opencode.json"
    assert not list(ROOT.glob("agents/*.md"))


def test_single_paid_coordinator_and_read_only_critic_and_writer():
    agents = CONFIG["agents"]
    assert effective(agents["film-director"]["permissions"], "runware_run", "*") == "ask"
    for name in SPECIALISTS:
        permissions = agents[name]["permissions"]
        assert effective(permissions, "runware_run", "*") == "deny", name
        assert effective(permissions, "runware_list_models", "*") == "deny", name
        assert effective(permissions, "subagent", "explore") == "deny", name
    for name in (
        "music-editor",
        "short-film-writer",
        "visual-critic",
        "post-editor",
        "film-finisher",
    ):
        assert effective(agents[name]["permissions"], "skill", "clip-image-production") == "deny", (
            name
        )
    assert effective(agents["visual-director"]["permissions"], "skill", "clip-image-prompts") == (
        "allow"
    )
    assert effective(agents["visual-director"]["permissions"], "skill", "clip-delivery") == "deny"
    for name in ("visual-critic", "short-film-writer"):
        permissions = agents[name]["permissions"]
        assert effective(permissions, "edit", "*") == "deny", name
        assert effective(permissions, "shell", "*") == "deny", name
        assert effective(permissions, "read", "*") == "allow", name
    assert effective(agents["visual-critic"]["permissions"], "skill", "clip-visual-review") == (
        "allow"
    )
    assert effective(agents["film-finisher"]["permissions"], "shell", "ffmpeg") == "allow"
    # The post-editor plans movement; it never renders the delivery and never spends.
    post = agents["post-editor"]["permissions"]
    assert effective(post, "skill", "clip-edit-graphics") == "allow"
    assert effective(post, "skill", "clip-delivery") == "deny"
    assert effective(post, "runware_run", "*") == "deny"
    assert effective(agents["visual-director"]["permissions"], "edit", "*") == "allow"
    for name in SPECIALISTS:
        assert effective(agents["film-director"]["permissions"], "subagent", name) == "allow", name
    assert effective(agents["film-director"]["permissions"], "subagent", "general") == "deny"


def test_loop_names_the_crew_stages_and_real_repository_paths():
    raw = (ROOT / "LOOP.md").read_text()
    loop = raw.replace("**", "")  # emphasis must not hide the contract wording
    for name in AGENTS:
        assert f"`{name}`" in loop, name
    for name in STAGES:
        assert f"`{name}`" in loop, name
    tokens = re.findall(r"`([^`\n]+)`", loop)
    linked = [
        token
        for token in tokens
        if re.fullmatch(r"[A-Za-z0-9_./-]+\.(md|py|json)", token)
        and token.startswith(("scripts/", "docs/", ".opencode/", "src/", "tests/"))
    ]
    assert linked, "the loop must cite real project paths"
    for token in linked:
        assert (ROOT / token).exists(), token
    for phrase in (
        "before brief approval",
        "before storyboard approval",
        "rollout",
        "composite",
        "clip backup",
        "style-test",
        "reviews.json",
        "not a security sandbox",
        "not budget enforcement",
        "build workflow",
        "25",
        "40",
    ):
        assert phrase in loop, phrase
    assert "clip-image-prompts" in loop
    assert "→" not in loop.split("Stage skills")[1].split("##")[0], "stages are not an arrow chain"


def test_bootstrap_agent_roster_matches_the_config_exactly():
    module = bootstrap_module()
    config_agents = CONFIG["agents"]
    assert list(module.AGENTS) == list(config_agents) == list(AGENTS)
    assert len(module.AGENTS) == 7, "the director plus six specialists"
    assert "post-editor" in module.AGENTS
    for name in module.AGENTS:
        expected = "primary" if name == "film-director" else "subagent"
        assert config_agents[name]["mode"] == expected, name


def test_bootstrap_flags_a_config_that_drops_or_invents_a_crew_role(tmp_path):
    make_bundle(tmp_path, bootstrap_module().REVISION)
    path = tmp_path / "opencode.json"
    original = json.loads(path.read_text())

    dropped = json.loads(json.dumps(original))
    del dropped["agents"]["post-editor"]
    path.write_text(json.dumps(dropped))
    missing = run_check(tmp_path)
    assert missing.returncode == 1
    assert "missing inline agent post-editor" in missing.stdout

    invented = json.loads(json.dumps(original))
    invented["agents"]["new-committee"] = invented["agents"]["film-finisher"]
    path.write_text(json.dumps(invented))
    extra = run_check(tmp_path)
    assert extra.returncode == 1
    assert "unknown inline agent new-committee" in extra.stdout


def test_critic_reviews_story_and_board_without_weakening_its_permissions():
    critic = CONFIG["agents"]["visual-critic"]
    permissions = critic["permissions"]
    for skill in ("clip-story", "clip-storyboard", "clip-visual-review"):
        assert effective(permissions, "skill", skill) == "allow", skill
    for skill in ("clip-image-prompts", "clip-image-production", "clip-edit-graphics"):
        assert effective(permissions, "skill", skill) == "deny", skill
    assert effective(permissions, "edit", "*") == "deny"
    assert effective(permissions, "shell", "*") == "deny"
    assert effective(permissions, "read", "*") == "allow"
    assert effective(permissions, "subagent", "explore") == "deny"
    assert effective(permissions, "runware_run", "*") == "deny"
    system = critic["system"].lower()
    assert "read-only" in system
    for mode in ("story", "board", "pixel"):
        assert mode in system, mode


def test_feedback_lanes_are_bounded_and_the_draft_owner_revises():
    loop = (ROOT / "LOOP.md").read_text()
    section = loop.split("## Feedback loop")[1].split("##")[0]
    for name in ("short-film-writer", "visual-director", "visual-critic", "music-editor"):
        assert f"`{name}`" in section, name
    assert "post-editor" in section
    assert "the writer's **one**" in section
    assert "`visual-director`'s **one**" in section, "the board revision is the visual-director's"
    assert "committee" in section
    assert "`film-director` alone" in section


def test_bootstrap_check_is_read_only_and_reports_missing_pieces(tmp_path):
    make_bundle(tmp_path, bootstrap_module().REVISION)
    before = snapshot(tmp_path)
    for _ in range(2):
        result = run_check(tmp_path)
        assert result.returncode == 0, result.stdout + result.stderr
        payload = json.loads(result.stdout)
        assert payload["ok"] is True
        assert set(payload["recipes_missing"]) == set(bootstrap_module().SELECTED)
        assert payload["pending_archive"] == []
    assert snapshot(tmp_path) == before

    (tmp_path / "LOOP.md").unlink()
    broken = run_check(tmp_path)
    assert broken.returncode == 1
    assert "LOOP.md" in broken.stdout
    (tmp_path / ".opencode/vendor/runware-skills/.git/HEAD").write_text("0" * 40 + "\n")
    assert "expected" in run_check(tmp_path).stdout


@pytest.mark.skipif(
    not (ROOT / ".opencode/vendor/runware-skills/.git/HEAD").is_file(),
    reason="the pinned vendor checkout is an optional local installation",
)
def test_real_tree_check_passes_without_writing_or_network():
    before = snapshot(ROOT / ".opencode/skills")
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--check"], cwd=ROOT, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["ok"] is True and payload["problems"] == []
    assert payload["cached_revision"] == bootstrap_module().REVISION
    assert payload["recipes_missing"] == [] and payload["pending_archive"] == []
    assert snapshot(ROOT / ".opencode/skills") == before


def test_check_path_has_no_shell_or_network_access():
    tree = ast.parse(SCRIPT.read_text())
    modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module.split(".")[0])
    assert modules == {"argparse", "json", "shutil", "subprocess", "pathlib", "__future__"}
    shellers = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for call in ast.walk(node):
            if (
                isinstance(call, ast.Attribute)
                and isinstance(call.value, ast.Name)
                and call.value.id == "subprocess"
            ):
                shellers.add(node.name)
    assert shellers == {"ensure_cached_recipes"}, shellers


def test_recipe_install_and_motion_archive_are_idempotent(tmp_path):
    module = bootstrap_module()
    root = tmp_path
    make_bundle(root, module.REVISION)
    installed = root / ".opencode/skills"
    assert module.install_recipes(root) == list(module.SELECTED)
    assert module.install_recipes(root) == []
    for name in module.SELECTED:
        assert (installed / name / "SKILL.md").is_file()

    (installed / "runware-run" / "SKILL.md").write_text("locally adapted\n")
    with pytest.raises(SystemExit, match="refusing to overwrite"):
        module.install_recipes(root)

    motion = installed / "animate-image"
    motion.mkdir()
    expected = b"---\nname: animate-image\n---\nmotion recipe\n"
    (motion / "SKILL.md").write_bytes(expected)
    moved = module.archive_motion_skills(root)
    assert moved == ["backups/unused-motion-skills/animate-image"]
    archive = root / "backups/unused-motion-skills/animate-image"
    assert (archive / "SKILL.md").read_bytes() == expected  # bytes preserved by the move
    assert not motion.exists()
    assert module.archive_motion_skills(root) == []
    motion.mkdir()
    (motion / "SKILL.md").write_text("a later copy\n")
    with pytest.raises(SystemExit, match="already exists"):
        module.archive_motion_skills(root)

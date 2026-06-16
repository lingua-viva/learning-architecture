"""
Mission Canvas — Skill Loader

Loads SKILL.md files (YAML frontmatter + markdown body).
Compatible with Hermes/agentskills.io format.

Usage:
    from lib.skill_loader import load_skill, load_skills_dir

    skill = load_skill("path/to/SKILL.md")
    # skill = {"name": "...", "description": "...", "version": "...", "body": "...", "references": [...]}

    skills = load_skills_dir("path/to/skills/")
    # List of all skills in directory tree

SKILL.md format:
    ---
    name: my-skill
    description: "What this skill does"
    version: 1.0.0
    platforms: [linux, macos]
    metadata:
      tags: [automation, orders]
    ---

    # Skill Title

    Instructions for the agent...

    ## References
    - `references/api.md`
"""

import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional


def _parse_frontmatter(content: str) -> tuple:
    """Split YAML frontmatter from markdown body.

    Returns (frontmatter_dict, body_string).
    """
    if not content.startswith("---"):
        return {}, content

    # Find closing ---
    end = content.find("---", 3)
    if end == -1:
        return {}, content

    frontmatter_raw = content[3:end].strip()
    body = content[end + 3:].strip()

    # Parse YAML frontmatter
    try:
        import yaml
        frontmatter = yaml.safe_load(frontmatter_raw) or {}
    except ImportError:
        # Fallback: basic key: value parsing
        frontmatter = {}
        for line in frontmatter_raw.split("\n"):
            if ":" in line:
                key, _, value = line.partition(":")
                frontmatter[key.strip()] = value.strip().strip('"').strip("'")
    except Exception:
        frontmatter = {}

    return frontmatter, body


def load_skill(path: str) -> Optional[Dict[str, Any]]:
    """Load a single SKILL.md file.

    Returns dict with:
        name, description, version, body, path, references, metadata
    """
    p = Path(path)
    if not p.exists():
        return None

    content = p.read_text(encoding="utf-8", errors="replace")
    frontmatter, body = _parse_frontmatter(content)

    skill_dir = p.parent

    # Discover references
    references = []
    refs_dir = skill_dir / "references"
    if refs_dir.is_dir():
        for ref_file in sorted(refs_dir.iterdir()):
            if ref_file.is_file() and ref_file.suffix in (".md", ".txt", ".yaml", ".json"):
                references.append({
                    "name": ref_file.stem,
                    "path": str(ref_file),
                    "size": ref_file.stat().st_size,
                })

    return {
        "name": frontmatter.get("name", skill_dir.name),
        "description": frontmatter.get("description", ""),
        "version": frontmatter.get("version", "0.0.0"),
        "platforms": frontmatter.get("platforms", []),
        "metadata": frontmatter.get("metadata", {}),
        "body": body,
        "path": str(p),
        "dir": str(skill_dir),
        "references": references,
    }


def load_skills_dir(directory: str) -> List[Dict[str, Any]]:
    """Load all skills from a directory tree.

    Looks for SKILL.md files at any depth.
    """
    root = Path(directory)
    if not root.is_dir():
        return []

    skills = []
    for skill_file in sorted(root.rglob("SKILL.md")):
        skill = load_skill(str(skill_file))
        if skill:
            skills.append(skill)
    return skills


def skill_matches_platform(skill: Dict[str, Any], platform: Optional[str] = None) -> bool:
    """Check if a skill is compatible with the current platform."""
    platforms = skill.get("platforms", [])
    if not platforms:
        return True  # No restriction = works everywhere
    if platform is None:
        import sys
        platform = {"linux": "linux", "darwin": "macos", "win32": "windows"}.get(sys.platform, sys.platform)
    return platform in platforms


def get_skill_reference(skill: Dict[str, Any], ref_name: str) -> Optional[str]:
    """Load the content of a skill reference file by name."""
    for ref in skill.get("references", []):
        if ref["name"] == ref_name:
            try:
                return Path(ref["path"]).read_text(encoding="utf-8", errors="replace")
            except Exception:
                return None
    return None

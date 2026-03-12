#!/bin/bash
set -euo pipefail

# Only run in remote (Claude Code on the web) environments
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

# Muninn boot: load profile + ops from Turso into the session.
# The remembering skill lives in the claude-skills repo, not here.
# Try known locations, then fetch if needed.

python3 - <<'PYEOF'
import sys, os

# Search order for the remembering skill
candidates = [
    # Sibling checkout (common in CCotw with multiple repos)
    os.path.join(os.environ.get("HOME", "/home/user"), "claude-skills", "remembering"),
    # Mounted skills (Claude.ai containers)
    "/mnt/skills/user/remembering",
    # Fallback: installed via pip or .pth
]

skill_dir = None
for path in candidates:
    if os.path.isfile(os.path.join(path, "scripts", "boot.py")):
        skill_dir = path
        break

if skill_dir is None:
    # Fetch remembering skill from GitHub
    import subprocess, tempfile
    try:
        tarball = os.path.join(tempfile.gettempdir(), "claude-skills.tar.gz")
        subprocess.run(
            ["curl", "-sL", "https://codeload.github.com/oaustegard/claude-skills/tar.gz/main", "-o", tarball],
            check=True, capture_output=True
        )
        extract_dir = os.path.join(tempfile.gettempdir(), "claude-skills-main")
        subprocess.run(["tar", "-xzf", tarball, "-C", tempfile.gettempdir()], check=True, capture_output=True)
        skill_dir = os.path.join(extract_dir, "remembering")
        if not os.path.isfile(os.path.join(skill_dir, "scripts", "boot.py")):
            raise FileNotFoundError("remembering skill not found in tarball")
    except Exception as e:
        print(f"Muninn boot skipped: could not locate remembering skill ({e})", file=sys.stderr)
        sys.exit(0)

sys.path.insert(0, skill_dir)

try:
    from scripts import boot
    print(boot())
except Exception as e:
    # Non-fatal: not all sessions need memory access
    print(f"Muninn boot skipped: {e}", file=sys.stderr)
PYEOF

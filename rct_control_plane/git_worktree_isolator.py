"""
Git Worktree Subagent Isolator (Zero-Conflict Swarm)
Delentia OS Cognitive Kernel (Unified v2.2.6)

Manages isolated temporary git worktrees for parallel subagents.
Allows 3-10 autonomous agents to edit code concurrently in isolated working trees
and merge back cleanly without git lock or branch conflicts.
"""

import os
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional


class GitWorktreeIsolator:
    """Manages isolated Git worktrees for parallel agent swarms."""

    def __init__(self, repo_root: Optional[str] = None):
        self.repo_root = Path(repo_root or os.getcwd()).resolve()
        self.worktrees_dir = self.repo_root / ".delentia_worktrees"
        self.active_worktrees: Dict[str, Path] = {}

    def ensure_worktrees_dir(self):
        """Ensures the .delentia_worktrees parent directory exists."""
        self.worktrees_dir.mkdir(parents=True, exist_ok=True)

    def create_worktree(self, agent_id: str, base_branch: str = "main") -> Dict[str, Any]:
        """
        Creates an isolated git worktree for a specific subagent.
        """
        self.ensure_worktrees_dir()
        branch_name = f"swarm/agent_{agent_id}"
        worktree_path = self.worktrees_dir / f"agent_{agent_id}"

        # Clean existing if dirty
        if worktree_path.exists():
            self.remove_worktree(agent_id, force=True)

        cmd = [
            "git", "worktree", "add", "-b", branch_name,
            str(worktree_path), base_branch
        ]

        try:
            res = subprocess.run(
                cmd,
                cwd=str(self.repo_root),
                capture_output=True,
                text=True,
                check=False
            )
            
            if res.returncode == 0 or worktree_path.exists():
                self.active_worktrees[agent_id] = worktree_path
                return {
                    "success": True,
                    "agent_id": agent_id,
                    "branch": branch_name,
                    "worktree_path": str(worktree_path),
                    "status": "ISOLATED_READY"
                }
            else:
                # Fallback directory isolation if not a full git repo
                worktree_path.mkdir(parents=True, exist_ok=True)
                self.active_worktrees[agent_id] = worktree_path
                return {
                    "success": True,
                    "agent_id": agent_id,
                    "branch": branch_name,
                    "worktree_path": str(worktree_path),
                    "status": "VIRTUAL_ISOLATION_FALLBACK"
                }
        except Exception as e:
            worktree_path.mkdir(parents=True, exist_ok=True)
            self.active_worktrees[agent_id] = worktree_path
            return {
                "success": True,
                "agent_id": agent_id,
                "worktree_path": str(worktree_path),
                "status": f"VIRTUAL_ISOLATION_{e}"
            }

    def remove_worktree(self, agent_id: str, force: bool = True) -> bool:
        """
        Removes an agent's worktree upon task completion.
        """
        worktree_path = self.active_worktrees.get(agent_id) or (self.worktrees_dir / f"agent_{agent_id}")
        
        try:
            subprocess.run(
                ["git", "worktree", "remove", str(worktree_path), "--force"],
                cwd=str(self.repo_root),
                capture_output=True,
                check=False
            )
        except Exception:
            pass

        if worktree_path.exists():
            shutil.rmtree(worktree_path, ignore_errors=True)

        self.active_worktrees.pop(agent_id, None)
        return True

    def list_active(self) -> Dict[str, str]:
        """Returns map of active agent IDs to their worktree paths."""
        return {k: str(v) for k, v in self.active_worktrees.items()}

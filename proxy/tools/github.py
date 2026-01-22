"""
GitHub tool for Claude Code Proxy.

Provides controlled access to GitHub operations with:
- Branch protection (block pushes to main/master by default)
- Repository access controls
- Credential management
"""

import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Body
from pydantic import BaseModel, Field

from config import settings
from .base import ToolResponse, ToolError

# Tool metadata for discovery
TOOL_INFO = {
    "name": "github",
    "description": "GitHub operations with branch protection and access controls",
    "version": "1.0.0",
    "cli_command": "proxy-github",
    "blocked_branches": settings.github_blocked_branches,
    "features": [
        "Branch protection (configurable blocked branches)",
        "Push with automatic credential injection",
        "Pull/fetch operations",
        "Repository cloning",
        "Status and branch information",
    ],
}

router = APIRouter()


# Request/Response Models
class PushRequest(BaseModel):
    """Request model for git push operations."""
    remote: str = Field(default="origin", description="Remote name")
    branch: str = Field(..., description="Branch to push to")
    force: bool = Field(default=False, description="Force push (still respects branch blocks)")
    set_upstream: bool = Field(default=False, description="Set upstream tracking")
    repo_path: str = Field(default="/home/claude/workspace", description="Repository path")


class PullRequest(BaseModel):
    """Request model for git pull operations."""
    remote: str = Field(default="origin", description="Remote name")
    branch: Optional[str] = Field(default=None, description="Branch to pull (default: current)")
    rebase: bool = Field(default=False, description="Use rebase instead of merge")
    repo_path: str = Field(default="/home/claude/workspace", description="Repository path")


class FetchRequest(BaseModel):
    """Request model for git fetch operations."""
    remote: str = Field(default="origin", description="Remote name")
    branch: Optional[str] = Field(default=None, description="Specific branch to fetch")
    all_remotes: bool = Field(default=False, description="Fetch all remotes")
    prune: bool = Field(default=False, description="Prune deleted remote branches")
    repo_path: str = Field(default="/home/claude/workspace", description="Repository path")


class CloneRequest(BaseModel):
    """Request model for git clone operations."""
    url: str = Field(..., description="Repository URL to clone")
    destination: Optional[str] = Field(default=None, description="Destination directory")
    branch: Optional[str] = Field(default=None, description="Branch to clone")
    depth: Optional[int] = Field(default=None, description="Create shallow clone with depth")


class BranchRequest(BaseModel):
    """Request model for branch operations."""
    name: Optional[str] = Field(default=None, description="Branch name for create/delete")
    delete: bool = Field(default=False, description="Delete the branch")
    checkout: bool = Field(default=False, description="Checkout the branch after creation")
    repo_path: str = Field(default="/home/claude/workspace", description="Repository path")


def is_branch_blocked(branch: str) -> bool:
    """Check if a branch is in the blocked list."""
    # Normalize branch name (remove refs/heads/ prefix if present)
    normalized = branch.replace("refs/heads/", "")
    return normalized in settings.github_blocked_branches


def is_repo_allowed(repo_url: str) -> bool:
    """Check if repository access is allowed."""
    # If no allowed repos specified, check blocked repos
    if not settings.github_allowed_repos:
        for blocked in settings.github_blocked_repos:
            if blocked in repo_url:
                return False
        return True

    # Check against allowed repos
    for allowed in settings.github_allowed_repos:
        if allowed in repo_url:
            return True
    return False


def inject_credentials(url: str) -> str:
    """Inject GitHub token into repository URL if available."""
    if not settings.github_token:
        return url

    # Handle HTTPS URLs
    if url.startswith("https://github.com"):
        return url.replace("https://github.com", f"https://{settings.github_token}@github.com")
    elif url.startswith("https://") and "github" in url:
        # Handle other GitHub URLs
        return re.sub(r"https://([^@]+@)?", f"https://{settings.github_token}@", url)

    return url


def run_git_command(args: list[str], cwd: Optional[str] = None, env: Optional[dict] = None) -> tuple[bool, str, str]:
    """Run a git command and return (success, stdout, stderr)."""
    full_env = os.environ.copy()
    if env:
        full_env.update(env)

    # Add token to environment for credential helper
    if settings.github_token:
        full_env["GIT_ASKPASS"] = "echo"
        full_env["GIT_USERNAME"] = "x-access-token"
        full_env["GIT_PASSWORD"] = settings.github_token

    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=300,  # 5 minute timeout
            env=full_env,
        )
        return result.returncode == 0, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return False, "", "Command timed out after 5 minutes"
    except Exception as e:
        return False, "", str(e)


# Endpoints

@router.get("/")
async def github_info():
    """Get GitHub tool information and configuration."""
    return {
        **TOOL_INFO,
        "configuration": {
            "blocked_branches": settings.github_blocked_branches,
            "has_token": bool(settings.github_token),
            "allowed_repos": settings.github_allowed_repos or "all",
            "blocked_repos": settings.github_blocked_repos or "none",
        },
    }


@router.get("/help")
async def github_help():
    """Get detailed help for all GitHub endpoints."""
    return {
        "tool": "github",
        "description": TOOL_INFO["description"],
        "endpoints": {
            "GET /github/": "Get tool info and configuration",
            "GET /github/help": "This help message",
            "GET /github/status": "Get git status for repository",
            "GET /github/branches": "List branches",
            "GET /github/remotes": "List remotes",
            "POST /github/push": "Push changes (with branch protection)",
            "POST /github/pull": "Pull changes from remote",
            "POST /github/fetch": "Fetch from remote",
            "POST /github/clone": "Clone a repository",
            "POST /github/branch": "Create, delete, or list branches",
            "GET /github/blocked-branches": "List blocked branches",
            "POST /github/check-push": "Check if a push would be allowed",
        },
        "cli_usage": {
            "command": "proxy-github",
            "examples": [
                "proxy-github status",
                "proxy-github push origin feature-branch",
                "proxy-github pull",
                "proxy-github clone https://github.com/user/repo",
                "proxy-github branches",
            ],
        },
    }


@router.get("/status")
async def git_status(repo_path: str = Query(default="/home/claude/workspace")):
    """Get git status for the repository."""
    success, stdout, stderr = run_git_command(
        ["status", "--porcelain", "-b"],
        cwd=repo_path,
    )

    if not success:
        raise HTTPException(status_code=400, detail=f"Git status failed: {stderr}")

    # Parse status output
    lines = stdout.strip().split("\n") if stdout.strip() else []
    branch_line = lines[0] if lines else ""
    file_lines = lines[1:] if len(lines) > 1 else []

    # Parse branch info
    branch = "unknown"
    tracking = None
    if branch_line.startswith("## "):
        branch_info = branch_line[3:]
        if "..." in branch_info:
            parts = branch_info.split("...")
            branch = parts[0]
            tracking = parts[1].split()[0] if len(parts) > 1 else None
        else:
            branch = branch_info.split()[0]

    # Parse file status
    files = {"staged": [], "modified": [], "untracked": []}
    for line in file_lines:
        if len(line) >= 2:
            index_status = line[0]
            work_status = line[1]
            filename = line[3:]

            if index_status in "MADRC":
                files["staged"].append({"status": index_status, "file": filename})
            if work_status == "M":
                files["modified"].append(filename)
            if index_status == "?" and work_status == "?":
                files["untracked"].append(filename)

    return {
        "branch": branch,
        "tracking": tracking,
        "is_blocked_branch": is_branch_blocked(branch),
        "files": files,
        "clean": len(file_lines) == 0,
    }


@router.get("/branches")
async def list_branches(
    repo_path: str = Query(default="/home/claude/workspace"),
    all_branches: bool = Query(default=False, alias="all"),
):
    """List git branches."""
    args = ["branch", "--format=%(refname:short)|%(upstream:short)|%(HEAD)"]
    if all_branches:
        args.append("-a")

    success, stdout, stderr = run_git_command(args, cwd=repo_path)

    if not success:
        raise HTTPException(status_code=400, detail=f"Failed to list branches: {stderr}")

    branches = []
    current = None
    for line in stdout.strip().split("\n"):
        if not line:
            continue
        parts = line.split("|")
        name = parts[0]
        upstream = parts[1] if len(parts) > 1 and parts[1] else None
        is_current = parts[2] == "*" if len(parts) > 2 else False

        branch_info = {
            "name": name,
            "upstream": upstream,
            "current": is_current,
            "blocked": is_branch_blocked(name),
        }
        branches.append(branch_info)

        if is_current:
            current = name

    return {
        "current": current,
        "branches": branches,
        "blocked_branches": settings.github_blocked_branches,
    }


@router.get("/remotes")
async def list_remotes(repo_path: str = Query(default="/home/claude/workspace")):
    """List git remotes."""
    success, stdout, stderr = run_git_command(["remote", "-v"], cwd=repo_path)

    if not success:
        raise HTTPException(status_code=400, detail=f"Failed to list remotes: {stderr}")

    remotes = {}
    for line in stdout.strip().split("\n"):
        if not line:
            continue
        parts = line.split()
        if len(parts) >= 2:
            name = parts[0]
            url = parts[1]
            remote_type = parts[2].strip("()") if len(parts) > 2 else "unknown"

            if name not in remotes:
                remotes[name] = {"name": name, "urls": {}}
            remotes[name]["urls"][remote_type] = url

    return {"remotes": list(remotes.values())}


@router.get("/blocked-branches")
async def get_blocked_branches():
    """Get list of blocked branches."""
    return {
        "blocked_branches": settings.github_blocked_branches,
        "description": "These branches cannot be pushed to through the proxy",
    }


@router.post("/check-push")
async def check_push(request: PushRequest):
    """Check if a push operation would be allowed without executing it."""
    blocked = is_branch_blocked(request.branch)

    return {
        "allowed": not blocked,
        "branch": request.branch,
        "reason": f"Branch '{request.branch}' is protected" if blocked else None,
        "blocked_branches": settings.github_blocked_branches,
    }


@router.post("/push")
async def git_push(request: PushRequest):
    """
    Push changes to remote with branch protection.

    Blocked branches (default: main, master) cannot be pushed to.
    """
    # Check branch protection
    if is_branch_blocked(request.branch):
        raise HTTPException(
            status_code=403,
            detail={
                "error": "BRANCH_PROTECTED",
                "message": f"Cannot push to protected branch '{request.branch}'",
                "blocked_branches": settings.github_blocked_branches,
                "suggestion": "Create a feature branch and submit a pull request instead",
            },
        )

    # Build push command
    args = ["push"]
    if request.set_upstream:
        args.append("-u")
    if request.force:
        args.append("--force-with-lease")  # Safer than --force

    args.extend([request.remote, request.branch])

    success, stdout, stderr = run_git_command(args, cwd=request.repo_path)

    if not success:
        raise HTTPException(status_code=400, detail=f"Push failed: {stderr}")

    return ToolResponse(
        success=True,
        message=f"Successfully pushed to {request.remote}/{request.branch}",
        data={
            "remote": request.remote,
            "branch": request.branch,
            "output": stdout + stderr,
        },
    ).to_dict()


@router.post("/pull")
async def git_pull(request: PullRequest):
    """Pull changes from remote."""
    args = ["pull"]
    if request.rebase:
        args.append("--rebase")

    args.append(request.remote)
    if request.branch:
        args.append(request.branch)

    success, stdout, stderr = run_git_command(args, cwd=request.repo_path)

    if not success:
        raise HTTPException(status_code=400, detail=f"Pull failed: {stderr}")

    return ToolResponse(
        success=True,
        message="Pull completed successfully",
        data={"output": stdout + stderr},
    ).to_dict()


@router.post("/fetch")
async def git_fetch(request: FetchRequest):
    """Fetch from remote."""
    args = ["fetch"]

    if request.all_remotes:
        args.append("--all")
    else:
        args.append(request.remote)
        if request.branch:
            args.append(request.branch)

    if request.prune:
        args.append("--prune")

    success, stdout, stderr = run_git_command(args, cwd=request.repo_path)

    if not success:
        raise HTTPException(status_code=400, detail=f"Fetch failed: {stderr}")

    return ToolResponse(
        success=True,
        message="Fetch completed successfully",
        data={"output": stdout + stderr},
    ).to_dict()


@router.post("/clone")
async def git_clone(request: CloneRequest):
    """Clone a repository."""
    # Check repository access
    if not is_repo_allowed(request.url):
        raise HTTPException(
            status_code=403,
            detail={
                "error": "REPO_NOT_ALLOWED",
                "message": "Access to this repository is not allowed",
            },
        )

    # Inject credentials
    auth_url = inject_credentials(request.url)

    args = ["clone"]
    if request.branch:
        args.extend(["-b", request.branch])
    if request.depth:
        args.extend(["--depth", str(request.depth)])

    args.append(auth_url)
    if request.destination:
        args.append(request.destination)

    success, stdout, stderr = run_git_command(args, cwd="/home/claude/workspace")

    if not success:
        # Don't leak credentials in error message
        safe_stderr = stderr.replace(settings.github_token, "***") if settings.github_token else stderr
        raise HTTPException(status_code=400, detail=f"Clone failed: {safe_stderr}")

    return ToolResponse(
        success=True,
        message=f"Successfully cloned {request.url}",
        data={
            "url": request.url,
            "destination": request.destination,
            "branch": request.branch,
        },
    ).to_dict()


@router.post("/branch")
async def manage_branch(request: BranchRequest):
    """Create, delete, or manage branches."""
    if request.delete:
        if not request.name:
            raise HTTPException(status_code=400, detail="Branch name required for deletion")

        # Check if trying to delete a protected branch
        if is_branch_blocked(request.name):
            raise HTTPException(
                status_code=403,
                detail=f"Cannot delete protected branch '{request.name}'",
            )

        success, stdout, stderr = run_git_command(
            ["branch", "-d", request.name],
            cwd=request.repo_path,
        )

        if not success:
            raise HTTPException(status_code=400, detail=f"Failed to delete branch: {stderr}")

        return ToolResponse(
            success=True,
            message=f"Deleted branch '{request.name}'",
        ).to_dict()

    elif request.name:
        # Create new branch
        if request.checkout:
            args = ["checkout", "-b", request.name]
        else:
            args = ["branch", request.name]

        success, stdout, stderr = run_git_command(args, cwd=request.repo_path)

        if not success:
            raise HTTPException(status_code=400, detail=f"Failed to create branch: {stderr}")

        return ToolResponse(
            success=True,
            message=f"Created branch '{request.name}'" + (" and checked out" if request.checkout else ""),
        ).to_dict()

    else:
        # List branches (redirect to list endpoint)
        return await list_branches(repo_path=request.repo_path)

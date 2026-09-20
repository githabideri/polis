#!/usr/bin/env python3
"""
Migrate vibe-kanban tasks to beads_rust issues.

Usage:
    1. First install beads_rust: curl -fsSL "https://raw.githubusercontent.com/Dicklesworthstone/beads_rust/main/install.sh" | bash
    2. Initialize beads: br init --prefix polis
    3. Run this script: python3 scripts/migrate-kanban-to-beads.py

This script creates beads issues from the vibe-kanban export below.
"""

import subprocess
import json
import sys
from typing import Optional

# Vibe-kanban tasks export (from MCP query 2026-01-24)
TASKS = [
    # TODO tasks
    {
        "id": "a808aaba-f405-405b-9137-e1e30f670cfc",
        "title": "Anvil smithing: Verify sound effects playing",
        "status": "todo",
        "description": "Sound effect code exists but was not verified during testing (game was muted). Test with audio enabled.",
        "type": "task",
        "priority": 2,
        "labels": ["anvil", "audio"]
    },
    {
        "id": "537e639a-b351-4fe6-830a-add83f79655c",
        "title": "Anvil smithing: Fix hammer animation not playing",
        "status": "todo",
        "description": "The 'hit' animation starts once but doesn't visibly play during smithing. Use PolisAnimationHelpers looping pattern.",
        "type": "bug",
        "priority": 1,
        "labels": ["anvil", "animation"]
    },
    {
        "id": "f8c585d2-e1a8-400e-9087-3b8518143a48",
        "title": "Anvil smithing: Bot should walk to anvil before starting",
        "status": "todo",
        "description": "Bot stays at current position and manipulates voxels remotely. Should pathfind to adjacent position first.",
        "type": "bug",
        "priority": 2,
        "labels": ["anvil", "pathfinding"]
    },
    {
        "id": "9ba40397-0d2b-45b6-81f1-ee0079fc1a63",
        "title": "Audit actions for silent failures",
        "status": "todo",
        "description": "Some actions return Ok:true but fail silently. LastAction should reflect actual outcome. Audit: goto, mine, activate, interact, pickup, container ops.",
        "type": "task",
        "priority": 1,
        "labels": ["reliability", "actions"]
    },
    {
        "id": "44068dd3-a34d-47f8-ab57-4929a8629fa3",
        "title": "Handle CanCollect false for ~1s after item spawn",
        "status": "todo",
        "description": "Pickup fails for ~1 second after item spawns due to VS spawn protection. Add retry with backoff or document required wait.",
        "type": "bug",
        "priority": 2,
        "labels": ["pickup", "timing"]
    },
    {
        "id": "f73a7a5c-8727-49c6-bbc2-aa7aeca3142a",
        "title": "Investigate pickup 'inventory full' after drop",
        "status": "todo",
        "description": "Pickup fails with 'inventory full' immediately after drop freed space. Possible stale inventory state.",
        "type": "bug",
        "priority": 2,
        "labels": ["pickup", "inventory"]
    },
    {
        "id": "ed4c650c-fef4-4461-a80d-410160989442",
        "title": "Fix tall grass targeting to ground instead of air",
        "status": "todo",
        "description": "Using gotolook on tall grass targets the grass block (in air) instead of ground below. Scan downward for solid block.",
        "type": "bug",
        "priority": 2,
        "labels": ["targeting", "pathfinding"]
    },
    {
        "id": "a917a866-9db5-44fd-bcb7-e7e0f220df24",
        "title": "Fix activate LOS rejecting doors when adjacent",
        "status": "todo",
        "description": "Activate returns 'No line of sight' for doors/partial blocks even when adjacent. Add adjacency fallback or multi-point raytrace.",
        "type": "bug",
        "priority": 2,
        "labels": ["activate", "los"]
    },
    {
        "id": "77d84bcb-6d66-44a3-974c-cc5ea3a61ed3",
        "title": "Verify chicken butcher meat drops",
        "status": "todo",
        "description": "Butchering chickens only yielded feathers, not meat. May not be bug - drops are rare. Test with multiple chickens.",
        "type": "task",
        "priority": 3,
        "labels": ["butcher", "testing"]
    },
    {
        "id": "401ad91f-8320-42d3-b05e-57414dca53fc",
        "title": "Fix butcher animation not playing visually",
        "status": "todo",
        "description": "Mining loop FIXED. Butcher action is instant (no OnTick) so looping isn't the issue. TriggerButcherAnimation() doesn't produce visible result.",
        "type": "bug",
        "priority": 2,
        "labels": ["animation", "butcher"]
    },
    {
        "id": "abd0b5a0-be70-4a8b-af4e-f31a5ae32909",
        "title": "Test and fix webui-v2",
        "status": "todo",
        "description": "Web UI at tools/webui-v2/ shows 'Disconnected' despite harness running. Investigate polling/connection issues.",
        "type": "bug",
        "priority": 3,
        "labels": ["webui", "tooling"]
    },

    # IN REVIEW tasks (treat as in_progress with review label)
    {
        "id": "b2ed31c7-3071-4d62-9877-09822f22b6e2",
        "title": "Loop Animation - general fix",
        "status": "in_progress",
        "description": "Fix all-bot-animations-only-play-once problem. PolisAnimationHelpers added. Apply to remaining actions.",
        "type": "task",
        "priority": 1,
        "labels": ["animation", "review"]
    },
    {
        "id": "b02d8437-0fd1-4ad9-8666-2238b574a1c3",
        "title": "Project planning phase 2",
        "status": "in_progress",
        "description": "Comprehensive project status overview. Codebase ~13,200 lines C#, 18 action primitives. Roadmap options A/B/C presented.",
        "type": "epic",
        "priority": 2,
        "labels": ["planning", "review"]
    },
    {
        "id": "442bc715-898f-4f4d-85da-90244d97cab4",
        "title": "Research game block and item name handling",
        "status": "in_progress",
        "description": "Download VS wiki lists (Block_codes, Item_codes, Entity_codes). Analyze poliscli and improve game element accessibility.",
        "type": "task",
        "priority": 3,
        "labels": ["research", "review"]
    },

    # DONE tasks (create as closed)
    {
        "id": "b82e4d48-b78c-405b-9fe5-3566d996bb8f",
        "title": "Anvil Smithing: Implement Option A",
        "status": "closed",
        "description": "Implemented direct voxel manipulation for bot smithing ALL recipes. Completed.",
        "type": "feature",
        "priority": 1,
        "labels": ["anvil"],
        "close_reason": "Implemented direct voxel manipulation successfully"
    },
    {
        "id": "b7f61387-90d0-4b17-ad1f-694b04c68fc6",
        "title": "Merge pending branches and clean up worktrees",
        "status": "closed",
        "description": "Merged vk/8ddb-fix-clayform-ani, vk/65a5-research-game-bl. Removed stale worktrees.",
        "type": "task",
        "priority": 2,
        "labels": ["git"],
        "close_reason": "All branches merged, worktrees cleaned"
    },
    {
        "id": "c93b8bbd-bc35-408d-973a-7f6df897660a",
        "title": "Test clayform progressive animation",
        "status": "closed",
        "description": "Verified clayform places voxels progressively with visible animation.",
        "type": "task",
        "priority": 2,
        "labels": ["clayform", "testing"],
        "close_reason": "Verified working with screenshots"
    },
    {
        "id": "8861dedb-145d-4f7a-91a3-b3c522908159",
        "title": "Fix clayform instant voxel placement",
        "status": "closed",
        "description": "Fixed clayform placing all voxels in single frame. Added time-based throttling.",
        "type": "bug",
        "priority": 1,
        "labels": ["clayform"],
        "close_reason": "Fixed with tick-based timing"
    },
    {
        "id": "3e6821d0-3426-45bb-9950-7ad8d7fb407f",
        "title": "Implement Anvil Smithing Option E",
        "status": "closed",
        "description": "Implemented helve hammer emulation. Works for iron blooms and 'plate'/'blistersteel' recipes.",
        "type": "feature",
        "priority": 1,
        "labels": ["anvil"],
        "close_reason": "Superseded by Option A (direct voxel manipulation)"
    },
    {
        "id": "0923e479-a556-4dd8-85d2-8bfbd503dd86",
        "title": "Research anvil smithing mechanics",
        "status": "closed",
        "description": "Analyzed VS anvil state machine, temperature, voxels, recipes. Produced implementation plan.",
        "type": "task",
        "priority": 1,
        "labels": ["anvil", "research"],
        "close_reason": "Research complete, led to Option A implementation"
    },
    {
        "id": "b4e64586-9a6a-4c12-8e5a-5c5844100c89",
        "title": "Implement barrel sealing",
        "status": "closed",
        "description": "Implemented seal command for barrel pickling/fermentation.",
        "type": "feature",
        "priority": 2,
        "labels": ["barrel"],
        "close_reason": "Implemented and tested"
    },
    {
        "id": "96875ba0-f621-4350-ac65-cf84af941d17",
        "title": "Implement knapping action",
        "status": "closed",
        "description": "Implemented knap command for flint/stone tool creation.",
        "type": "feature",
        "priority": 2,
        "labels": ["knapping"],
        "close_reason": "Implemented with BFS voxel chipping"
    },
    {
        "id": "4e423d40-57d1-413d-91b0-91eb86c16945",
        "title": "Implement clay forming action",
        "status": "closed",
        "description": "Implemented clayform command for clay working.",
        "type": "feature",
        "priority": 2,
        "labels": ["clayform"],
        "close_reason": "Implemented with progressive animation"
    },
    {
        "id": "47338aaa-b90d-4397-bafe-e1affb47c176",
        "title": "Implement fruit press action",
        "status": "closed",
        "description": "Implemented press command for fruit press operation.",
        "type": "feature",
        "priority": 2,
        "labels": ["press"],
        "close_reason": "Implemented with animation"
    },
    {
        "id": "72ff1c3f-d4e1-406d-8a9b-ec237ac4f509",
        "title": "Implement quern grinding action",
        "status": "closed",
        "description": "Implemented grind command for quern workstations.",
        "type": "feature",
        "priority": 2,
        "labels": ["quern"],
        "close_reason": "Implemented with count/duration options"
    },
    {
        "id": "b76a229f-9465-4bd1-a40f-3b6c783c6fde",
        "title": "Add ignite command for IIgnitable blocks",
        "status": "closed",
        "description": "Implemented ignite for firepits and other ignitable blocks.",
        "type": "feature",
        "priority": 2,
        "labels": ["firepit"],
        "close_reason": "Implemented"
    },
    {
        "id": "9a2f118c-e41d-4f79-ad52-e6193c684422",
        "title": "Fix CLI targets --query not filtering",
        "status": "closed",
        "description": "Fixed poliscli targets --query parameter to properly filter by block code.",
        "type": "bug",
        "priority": 2,
        "labels": ["cli"],
        "close_reason": "Fixed query parameter wiring"
    },
    {
        "id": "340962e2-da04-4d88-bdfc-d804efe92d56",
        "title": "Fix bot loot not triggering carcass transformation",
        "status": "closed",
        "description": "Fixed loot command to trigger entity-to-carcass-block transformation.",
        "type": "bug",
        "priority": 1,
        "labels": ["loot", "butcher"],
        "close_reason": "Fixed - carcass block now spawns after loot"
    },
    {
        "id": "c25d5ca8-d572-4629-be55-33c6c95b7b8e",
        "title": "Fix berry bush harvest autocollect to bot inventory",
        "status": "closed",
        "description": "Fixed harvest --autocollect to route items to bot inventory, not player.",
        "type": "bug",
        "priority": 1,
        "labels": ["harvest"],
        "close_reason": "Fixed inventory routing"
    },
    {
        "id": "a5ed0149-d49a-467e-95ca-5e9d939b3412",
        "title": "Fix bot goto overshooting target",
        "status": "closed",
        "description": "Fixed goto overshooting target by ~0.5-1 block.",
        "type": "bug",
        "priority": 1,
        "labels": ["goto", "pathfinding"],
        "close_reason": "Fixed - stops within 0.25 blocks"
    },

    # CANCELLED
    {
        "id": "54d78229-607a-4b6c-a2f3-d6de89ff7a58",
        "title": "test webui (superseded)",
        "status": "closed",
        "description": "Superseded by 'Test and fix webui-v2' task.",
        "type": "task",
        "priority": 3,
        "labels": ["webui"],
        "close_reason": "Superseded by more detailed task"
    },
]

def run_br(args: list[str], check: bool = True) -> subprocess.CompletedProcess:
    """Run br command."""
    cmd = ["br"] + args
    print(f"  Running: {' '.join(cmd)}")
    return subprocess.run(cmd, capture_output=True, text=True, check=check)

def create_issue(task: dict) -> Optional[str]:
    """Create a beads issue from a vibe-kanban task."""
    title = task["title"]
    desc = task.get("description", "")
    issue_type = task.get("type", "task")
    priority = task.get("priority", 2)
    labels = task.get("labels", [])
    status = task.get("status", "open")
    close_reason = task.get("close_reason", "")

    # Create the issue
    args = [
        "create",
        title,
        "-t", issue_type,
        "-p", str(priority),
        "--json"
    ]

    if desc:
        args.extend(["-d", desc])

    for label in labels:
        args.extend(["-l", label])

    result = run_br(args, check=False)

    if result.returncode != 0:
        print(f"    ERROR: {result.stderr}")
        return None

    # Parse the created issue ID
    try:
        output = json.loads(result.stdout)
        issue_id = output.get("id") or output.get("issue", {}).get("id")
    except json.JSONDecodeError:
        # Try to extract ID from text output
        for line in result.stdout.split("\n"):
            if "polis-" in line:
                parts = line.split()
                for part in parts:
                    if part.startswith("polis-"):
                        issue_id = part
                        break
        else:
            print(f"    Could not parse issue ID from: {result.stdout}")
            return None

    print(f"    Created: {issue_id}")

    # Update status if not open
    if status == "in_progress":
        run_br(["update", issue_id, "--status", "in_progress"], check=False)
        print(f"    Updated status: in_progress")
    elif status == "closed":
        close_args = ["close", issue_id]
        if close_reason:
            close_args.extend(["--reason", close_reason])
        run_br(close_args, check=False)
        print(f"    Closed: {close_reason[:50]}...")

    return issue_id

def main():
    # Check if br is available
    try:
        subprocess.run(["br", "--version"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("ERROR: br (beads_rust) is not installed.")
        print("Install with: curl -fsSL 'https://raw.githubusercontent.com/Dicklesworthstone/beads_rust/main/install.sh' | bash")
        sys.exit(1)

    # Check if .beads exists
    import os
    if not os.path.exists(".beads"):
        print("ERROR: .beads directory not found.")
        print("Initialize with: br init --prefix polis")
        sys.exit(1)

    print(f"\nMigrating {len(TASKS)} tasks from vibe-kanban to beads...\n")

    # Group by status for progress
    by_status = {}
    for task in TASKS:
        status = task["status"]
        if status not in by_status:
            by_status[status] = []
        by_status[status].append(task)

    created = 0
    failed = 0

    for status in ["open", "in_progress", "closed"]:
        # Map vibe-kanban status to our grouping
        status_tasks = by_status.get(status, [])
        if status == "open":
            status_tasks = by_status.get("todo", [])

        if not status_tasks:
            continue

        print(f"\n=== {status.upper()} ({len(status_tasks)} tasks) ===\n")

        for task in status_tasks:
            print(f"Creating: {task['title'][:60]}...")
            issue_id = create_issue(task)
            if issue_id:
                created += 1
            else:
                failed += 1

    print(f"\n{'='*50}")
    print(f"Migration complete: {created} created, {failed} failed")
    print(f"\nNext steps:")
    print(f"  1. Run 'br ready' to see open issues")
    print(f"  2. Run 'bv' for kanban TUI (if installed)")
    print(f"  3. Run 'br sync' to export to JSONL")
    print(f"  4. Commit .beads/ to git")

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Import historical (closed) issues from vibe-kanban into beads.

These are added with their original creation timestamps so they appear
chronologically before the open issues.

Usage:
    python3 scripts/import-historical-issues.py
    br sync --import-only
"""

import json
import os
import hashlib
from datetime import datetime

JSONL_PATH = ".beads/issues.jsonl"

# Historical issues from vibe-kanban (done + cancelled)
# Timestamps are from the original vibe-kanban creation dates
HISTORICAL_ISSUES = [
    # Done issues (chronologically ordered by creation)
    {
        "title": "create tasks out of known issues",
        "description": "Created meaningful assortment of tasks from KNOWN_ISSUES.md, grouped where it made sense.",
        "created_at": "2026-01-21T19:51:19.228Z",
        "status": "closed",
        "issue_type": "task",
        "priority": 2,
        "labels": ["setup"],
        "close_reason": "Completed - tasks created"
    },
    {
        "title": "Fix bot goto overshooting target by ~1 block",
        "description": "Fixed goto overshooting target by ~0.5-1 block. Bot now stops within 0.25 blocks of target.",
        "created_at": "2026-01-21T20:49:06.307Z",
        "status": "closed",
        "issue_type": "bug",
        "priority": 1,
        "labels": ["goto", "pathfinding"],
        "close_reason": "Fixed - stops within 0.25 blocks"
    },
    {
        "title": "Fix bot loot not triggering carcass transformation",
        "description": "Fixed loot command to trigger entity-to-carcass-block transformation after emptying corpse.",
        "created_at": "2026-01-21T22:05:38.238Z",
        "status": "closed",
        "issue_type": "bug",
        "priority": 1,
        "labels": ["loot", "butcher"],
        "close_reason": "Fixed - carcass block now spawns"
    },
    {
        "title": "Fix berry bush harvest autocollect to bot inventory",
        "description": "Fixed harvest --autocollect to route items to bot inventory instead of player.",
        "created_at": "2026-01-21T22:04:21.954Z",
        "status": "closed",
        "issue_type": "bug",
        "priority": 1,
        "labels": ["harvest"],
        "close_reason": "Fixed inventory routing"
    },
    {
        "title": "Fix CLI targets --query not filtering",
        "description": "Fixed poliscli targets --query parameter to properly filter results by block code.",
        "created_at": "2026-01-21T23:09:40.896Z",
        "status": "closed",
        "issue_type": "bug",
        "priority": 2,
        "labels": ["cli"],
        "close_reason": "Fixed query parameter wiring"
    },
    {
        "title": "check if everything is in main",
        "description": "Verified repo state - everything in main as expected.",
        "created_at": "2026-01-22T00:06:57.866Z",
        "status": "closed",
        "issue_type": "task",
        "priority": 3,
        "labels": ["git"],
        "close_reason": "Verified clean"
    },
    {
        "title": "Add ignite command for IIgnitable blocks",
        "description": "Implemented /polis ignite command for firepits and other ignitable blocks.",
        "created_at": "2026-01-22T00:12:40.796Z",
        "status": "closed",
        "issue_type": "feature",
        "priority": 2,
        "labels": ["firepit"],
        "close_reason": "Implemented"
    },
    {
        "title": "investigate quern interaction",
        "description": "Investigated quern mechanics, wrote implementation plan in docs/research/phase-2/.",
        "created_at": "2026-01-22T00:24:52.661Z",
        "status": "closed",
        "issue_type": "task",
        "priority": 2,
        "labels": ["quern", "research"],
        "close_reason": "Research complete"
    },
    {
        "title": "Implement quern grinding action",
        "description": "Implemented grind command for quern workstations with --count and --duration options.",
        "created_at": "2026-01-22T00:30:19.357Z",
        "status": "closed",
        "issue_type": "feature",
        "priority": 2,
        "labels": ["quern"],
        "close_reason": "Implemented with animation"
    },
    {
        "title": "Fix stale main-chest container registry",
        "description": "Fixed stale container registry after firepit was placed at registered location.",
        "created_at": "2026-01-22T00:51:40.064Z",
        "status": "closed",
        "issue_type": "bug",
        "priority": 2,
        "labels": ["container"],
        "close_reason": "Fixed registry cleanup"
    },
    {
        "title": "Implement fruit press action",
        "description": "Implemented press command for fruit press operation with animation.",
        "created_at": "2026-01-22T01:02:54.248Z",
        "status": "closed",
        "issue_type": "feature",
        "priority": 2,
        "labels": ["press"],
        "close_reason": "Implemented"
    },
    {
        "title": "Implement clay forming action",
        "description": "Implemented clayform command for clay working with progressive animation.",
        "created_at": "2026-01-22T01:02:54.299Z",
        "status": "closed",
        "issue_type": "feature",
        "priority": 2,
        "labels": ["clayform"],
        "close_reason": "Implemented"
    },
    {
        "title": "Implement knapping action",
        "description": "Implemented knap command for flint/stone tool creation with BFS voxel chipping.",
        "created_at": "2026-01-22T01:02:54.362Z",
        "status": "closed",
        "issue_type": "feature",
        "priority": 2,
        "labels": ["knapping"],
        "close_reason": "Implemented"
    },
    {
        "title": "Implement barrel sealing action",
        "description": "Implemented seal command for barrel pickling/fermentation.",
        "created_at": "2026-01-22T01:02:54.498Z",
        "status": "closed",
        "issue_type": "feature",
        "priority": 2,
        "labels": ["barrel"],
        "close_reason": "Implemented and tested"
    },
    {
        "title": "Research anvil smithing mechanics",
        "description": "Analyzed VS anvil state machine, temperature, voxels, recipes. Produced implementation plan with Options A-E.",
        "created_at": "2026-01-22T01:10:13.584Z",
        "status": "closed",
        "issue_type": "task",
        "priority": 1,
        "labels": ["anvil", "research"],
        "close_reason": "Research complete - led to Option A"
    },
    {
        "title": "everything in git in main?",
        "description": "Verified repo is in order after worktree work.",
        "created_at": "2026-01-22T01:11:50.437Z",
        "status": "closed",
        "issue_type": "task",
        "priority": 3,
        "labels": ["git"],
        "close_reason": "Verified"
    },
    {
        "title": "Implement Anvil Smithing Option E (Helve Hammer)",
        "description": "Implemented helve hammer emulation. Works for iron blooms and plate/blistersteel recipes only.",
        "created_at": "2026-01-22T15:58:26.133Z",
        "status": "closed",
        "issue_type": "feature",
        "priority": 1,
        "labels": ["anvil"],
        "close_reason": "Superseded by Option A (direct voxel manipulation)"
    },
    {
        "title": "Add timed animation to clayform action",
        "description": "Converted PolisClayFormAction from instant to timed with progressive voxels.",
        "created_at": "2026-01-22T16:37:03.841Z",
        "status": "closed",
        "issue_type": "task",
        "priority": 2,
        "labels": ["clayform", "animation"],
        "close_reason": "Implemented"
    },
    {
        "title": "phase 2 - overview of project progress",
        "description": "Summarized project status, contrasted with vision/roadmap, made suggestions.",
        "created_at": "2026-01-22T16:45:07.351Z",
        "status": "closed",
        "issue_type": "task",
        "priority": 2,
        "labels": ["planning"],
        "close_reason": "Overview complete"
    },
    {
        "title": "Fix clayform instant voxel placement",
        "description": "Fixed clayform placing all voxels in single frame. Added time-based throttling.",
        "created_at": "2026-01-22T18:16:18.931Z",
        "status": "closed",
        "issue_type": "bug",
        "priority": 1,
        "labels": ["clayform"],
        "close_reason": "Fixed with tick-based timing"
    },
    {
        "title": "Test clayform progressive animation",
        "description": "Verified clayform places voxels progressively with visible animation via screenshots.",
        "created_at": "2026-01-22T18:52:25.161Z",
        "status": "closed",
        "issue_type": "task",
        "priority": 2,
        "labels": ["clayform", "testing"],
        "close_reason": "Verified working"
    },
    {
        "title": "Merge pending branches and clean up worktrees",
        "description": "Merged vk/8ddb-fix-clayform-ani, vk/65a5-research-game-bl. Removed stale worktrees.",
        "created_at": "2026-01-22T20:12:49.011Z",
        "status": "closed",
        "issue_type": "task",
        "priority": 2,
        "labels": ["git"],
        "close_reason": "All branches merged"
    },
    {
        "title": "Anvil Smithing: Implement Option A (Direct Voxel)",
        "description": "Implemented direct voxel manipulation for bot smithing ALL recipes.",
        "created_at": "2026-01-23T21:24:29.068Z",
        "status": "closed",
        "issue_type": "feature",
        "priority": 1,
        "labels": ["anvil"],
        "close_reason": "Implemented successfully"
    },
    # Cancelled
    {
        "title": "test webui (superseded)",
        "description": "Superseded by 'Test and fix webui-v2' task.",
        "created_at": "2026-01-21T20:00:18.339Z",
        "status": "closed",
        "issue_type": "task",
        "priority": 3,
        "labels": ["webui"],
        "close_reason": "Superseded by more detailed task"
    },
]

def generate_id(title: str, created_at: str) -> str:
    """Generate a beads-style ID from title and timestamp."""
    # Use first few chars of hash of title+timestamp
    data = f"{title}{created_at}".encode()
    h = hashlib.sha256(data).hexdigest()
    return f"polis-{h[:3]}"

def main():
    if not os.path.exists(JSONL_PATH):
        print(f"ERROR: {JSONL_PATH} not found. Run 'br init' first.")
        return

    # Read existing issues
    existing_ids = set()
    with open(JSONL_PATH, 'r') as f:
        for line in f:
            if line.strip():
                issue = json.loads(line)
                existing_ids.add(issue.get('id', ''))

    print(f"Found {len(existing_ids)} existing issues")

    # Add historical issues
    added = 0
    with open(JSONL_PATH, 'a') as f:
        for issue_data in HISTORICAL_ISSUES:
            issue_id = generate_id(issue_data['title'], issue_data['created_at'])

            # Skip if ID collision (unlikely but check)
            if issue_id in existing_ids:
                issue_id = f"{issue_id}h"  # Add suffix for historical

            issue = {
                "id": issue_id,
                "title": issue_data['title'],
                "description": issue_data.get('description', ''),
                "status": issue_data.get('status', 'closed'),
                "issue_type": issue_data.get('issue_type', 'task'),
                "priority": issue_data.get('priority', 2),
                "labels": issue_data.get('labels', []),
                "created_at": issue_data['created_at'],
                "updated_at": issue_data['created_at'],
                "created_by": "mf",
                "close_reason": issue_data.get('close_reason', ''),
            }

            f.write(json.dumps(issue) + '\n')
            added += 1
            print(f"  Added: {issue_id} - {issue_data['title'][:50]}...")

    print(f"\nAdded {added} historical issues to {JSONL_PATH}")
    print("\nNext step: run 'br sync --import-only' to import into database")

if __name__ == "__main__":
    main()

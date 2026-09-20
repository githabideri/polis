# Vintage Story modding (btca-backed reference library)

When answering Vintage Story modding questions, prefer evidence from btca (repo source) over memory/guessing.

## btca usage policy (automatic)
If the user asks a Vintage Story modding question and has NOT pasted the relevant code/logs:
1) Choose the best btca resource (see routing below).
2) Run: `btca ask -r <resource> -q "<question>"`
3) Answer with:
   - the chosen resource name
   - file paths and symbol/method/class names mentioned
   - short quotes/snippets only (don’t paste huge blocks)
4) If the result is ambiguous or incomplete, run exactly ONE more btca query against the next-best repo and reconcile.

If the user DID paste code/logs, only use btca to confirm API semantics or find canonical patterns, not to restate what’s already in the paste.

## Execution timeout (agent runners)
btca queries often take longer than default command timeouts in automation shells. When running btca via an agent or CLI wrapper, set the command timeout to **at least 120 seconds** (prefer **240 seconds**) so queries complete without repeated retries. This is a runner/agent timeout setting, not a btca flag.

## Important limitation
btca searches git repo contents. It does NOT “search GitHub Issues text” (issue discussions are not stored in the git repo). For issues, use GitHub search / web.

## Resource map (btca -r names)
Core / authoritative (default here):
- vsapi: canonical API behavior (GuiDialog, GuiComposer, GuiElement*, focus/mouse capture, input, ESC handling)
- vssurvivalmod: vanilla usage patterns; real dialogs; scroll lists; open/close patterns
- vscreativemod: tooling/editor-style dialogs and flows
- vsessentialsmod: more official patterns + integration style

Official learning / templates:
- vsmodexamples: clean examples
- vsmodtemplate: mod/project/build structure reference
- howto_example_mod: minimal mod structure reference (older but readable)

Advanced / edge cases / workflow:
- vs_imgui: robust input/cursor capture patterns under stress
- magic_gui_editor: live rebuild/recompose workflow patterns

Domain feature references (use when the question is about these systems):
- vsquest: quest systems; quest lists/menus; progression UX
- vsvillage: villagers; management screens; entity-like lists; interaction dialogs
- jaunt: mounts/riding/travel mechanics (use for “mounting in VS” related features)
- prospect_together: client UI/overlay + sync patterns
- electricity: larger system mod; assorted dialogs/config patterns

## Routing heuristics (decision tree)
Default order when unsure: vsapi → vssurvivalmod.

Pick vsapi when:
- the question is about “what does the API do”, “where is X implemented”, or exact semantics/behavior
- focus, mouse-grab/cursor capture, keyboard handling, ESC behavior is involved

Pick vssurvivalmod when:
- the question is “how does vanilla do it”, “give me an example dialog that…”, UI conventions

Pick vscreativemod when:
- it’s tooling/editor style UI flow, or survivalmod doesn’t have a comparable pattern

Pick vsmodtemplate / vsmodexamples when:
- build structure, mod skeleton, project layout, “how to structure a mod”, example patterns

Pick vs_imgui when:
- input handling is weird and you need a “stress tested” example (cursor capture, layering, event routing)

Pick magic_gui_editor when:
- question is specifically about rebuilding/recomposing GUI live / iteration workflow

Domain routing:
- quests/journal/objectives screens → vsquest (after vsapi if API semantics matter)
- villagers/NPC management screens → vsvillage
- mounts/riding/travel mechanics → jaunt
- “UI overlay + sync updates” → prospect_together

## Multi-repo answers
When needed, do it in two passes:
1) vsapi for canonical behavior
2) one usage/example repo for “how it’s applied” (usually vssurvivalmod, else the domain repo)
Then synthesize, and label which repo supports which claim.

"""Oikistes autonomy gate + tool-surface tests (pure logic, no network).
The gate is the security boundary of the service: the model proposes,
this table disposes. Every (preset, tool) cell is asserted."""
import sys, os, argparse
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))

import oikistes

fails = 0
def check(name, cond):
    global fails
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        fails += 1

args = argparse.Namespace(harness="http://127.0.0.1:1", uid="x",
                          llm="http://127.0.0.1:1",
                          llm_model="test", alt_llm="", alt_model="",
                          datadir="/tmp/oik-test")
oik = oikistes.Oikistes(args)

READONLY = {"state", "scan", "screenshot", "events", "autonomy"}
# strict: reads only
for t in READONLY:
    check("strict allows %s" % t, oik.check_tool(t, "strict"))
for t in ("mission", "give", "command"):
    check("strict denies %s" % t, not oik.check_tool(t, "strict"))
# guarded: reads + mission + give
for t in READONLY | {"mission", "give"}:
    check("guarded allows %s" % t, oik.check_tool(t, "guarded"))
check("guarded denies command", not oik.check_tool("command", "guarded"))
# free: everything
for t in READONLY | {"mission", "give", "command"}:
    check("free allows %s" % t, oik.check_tool(t, "free"))
# unknown tool: denied everywhere
for preset in ("strict", "guarded", "free"):
    check("%s denies unknown tool" % preset,
          not oik.check_tool("teleport-to-moon", preset))
# denial message shape (the model sees this as an observation)
obs = oik.do_tool("command", {"cmd": "stop"}, "strict")
check("denial observation is a string the model can read",
      obs.startswith("DENIED"))

print("%d failed" % fails)
sys.exit(1 if fails else 0)

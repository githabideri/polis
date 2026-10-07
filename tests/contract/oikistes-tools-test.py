#!/usr/bin/env python3
"""
Lane B (2026-10-07) contract test: the Oikistes query + zone tools.

Pure: no network (the Polis client is stubbed; the harness http_json
is patched so body() resolves its presence without a socket).

Verifies the autonomy gate (query is read-only and strict-allowed;
zone is guarded+ at the tool level, and the per-sub split - list/show
read, define/remove/rename write - is enforced at dispatch time,
where the arguments are visible), the argument parsing of the query
tool (zone form vs 'x z [radius]' coordinate form), and the compact
targets digest (PascalCase and camelCase payloads, cap, the 400-char
ceiling).

Run:  python3 tests/contract/oikistes-tools-test.py
"""
import sys, os, argparse
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "..", "scripts"))

import oikistes

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("ok   %s" % name)
    else:
        FAIL += 1
        print("FAIL %s  %s" % (name, detail))


args = argparse.Namespace(harness="http://127.0.0.1:1", uid="x",
                          llm="http://127.0.0.1:1", llm_model="test",
                          alt_llm="", alt_model="", datadir="/tmp/oik-contract")
oik = oikistes.Oikistes(args)

# body() resolves its presence through the module http_json - stub it
# to a live body (no socket, no spawn)
oik.bot = 7
oikistes.http_json = lambda *a, **k: {"Data": {"bots": [{"id": 7}]}}


class StubPolis:
    base = "http://127.0.0.1:1"

    def __init__(self):
        self.cmd_calls = []
        self.get_calls = []

    def cmd(self, c, a=(), bot=None, t=120, actor=""):
        self.cmd_calls.append((c, list(a)))
        return {"Ok": True, "Message": "ok", "Data": {}}

    def get(self, path, params=None, timeout=15):
        self.get_calls.append((path, dict(params or {})))
        return {"Ok": True,
                "Blocks": [{"Code": "game:fruitingbush-grown-corn",
                            "Pos": [512016, 155, 512012]},
                           {"Code": "game:granite",
                            "Pos": [512017, 155, 512012]}],
                "Entities": [{"Code": "game:EntityPlayerBot", "Id": 7,
                              "Pos": [512016, 155, 512012]}]}


# --- autonomy gate (tool level) ----------------------------------------------
check("strict allows query (read-only)",
      oik.check_tool("query", "strict"))
check("strict denies zone (writes are never strict)",
      not oik.check_tool("zone", "strict"))
check("guarded allows zone (list/show read)",
      oik.check_tool("zone", "guarded"))
check("free allows zone", oik.check_tool("zone", "free"))
check("unknown tool still denied",
      not oik.check_tool("zone-rename", "free"))

# --- zone: the per-sub gate (dispatch level) ----------------------------------
oik.polis = StubPolis()

obs = oik.do_tool("zone", {"sub": "define",
                           "args": ["z", "1", "2", "3", "4", "5", "6",
                                    "7"]}, "guarded")
check("guarded denies zone define (write)",
      obs.startswith("DENIED") and not oik.polis.cmd_calls, obs)

obs = oik.do_tool("zone", {"sub": "list"}, "guarded")
check("guarded allows zone list (read)",
      oik.polis.cmd_calls == [("zone-list", [])], obs)

obs = oik.do_tool("zone", {"sub": "show", "args": ["z"]}, "strict")
check("strict denies zone show (the tool is not strict-allowed)",
      obs.startswith("DENIED"), obs)

oik.polis = StubPolis()
obs = oik.do_tool("zone", {"sub": "define",
                           "args": ["z", "1", "2", "3", "4", "5", "6",
                                    "7"]}, "free")
check("free allows zone define",
      oik.polis.cmd_calls == [("zone-define",
                               ["z", "1", "2", "3", "4", "5", "6",
                                "7"])], obs)

oik.polis = StubPolis()
obs = oik.do_tool("zone", {"sub": "rename", "args": ["a"]}, "free")
check("rename with one arg: argument-count guard (no command sent)",
      "missing arguments" in obs and oik.polis.cmd_calls == [], obs)

oik.polis = StubPolis()
obs = oik.do_tool("zone", {"sub": "rename",
                           "args": ["a", "b"]}, "free")
check("free allows zone rename (Lane A's command)",
      oik.polis.cmd_calls == [("zone-rename", ["a", "b"])], obs)

oik.polis = StubPolis()
obs = oik.do_tool("zone", {"sub": "wat"}, "free")
check("unknown zone subcommand rejected",
      "unknown subcommand" in obs and oik.polis.cmd_calls == [], obs)

# --- query: argument parsing ----------------------------------------------------
qa = oikistes._query_args
check("zone form with keys",
      qa(["my", "zone", "mode=blocks", "code=bush"]) ==
      {"target": "my zone", "mode": "blocks", "code": "bush"})
check("coordinate form x z [radius]",
      qa(["512016", "512011", "8"]) ==
      {"target": "512016 512011", "radius": "8"})
check("coordinate form x z (radius defaults downstream)",
      qa(["512016", "512011"]) == {"target": "512016 512011"})
check("single bare integer is the radius",
      qa(["berries", "12"]) == {"target": "berries", "radius": "12"})
check("digits inside a zone name stay in the name",
      qa(["site-2", "radius=4"]) == {"target": "site-2", "radius": "4"})
check("key radius beats the bare third integer",
      qa(["512016", "512011", "8", "radius=4"]) ==
      {"target": "512016 512011", "radius": "4"})

# --- query: zone form against the stubbed endpoint -----------------------------
oik.polis = StubPolis()
obs = oik.do_tool("query", qa(["berries", "mode=blocks",
                               "code=fruitingbush"]), "strict")
path, params = oik.polis.get_calls[0]
check("zone form calls /polis/targets with zone= and the operator uid",
      path == "/polis/targets" and params.get("zone") == "berries"
      and params.get("playerUid") == "x"
      and params.get("mode") == "blocks"
      and params.get("codeContains") == "fruitingbush",
      str(params))
check("digest is compact and case-tolerant",
      obs.startswith("targets: 3")
      and "fruitingbush-grown-corn@512016,155,512012" in obs
      and "granite@512017,155,512012" in obs
      and "EntityPlayerBot(id=7)@512016,155,512012" in obs
      and len(obs) <= 400, obs)

# the 27B passes a JSON object with the zone= key (the endpoint's own
# parameter name is the shape it reaches for) - same result as the
# positional form
oik.polis.get_calls.clear()
obs2 = oik.do_tool("query", {"zone": "berries", "mode": "all"}, "strict")
path2, params2 = oik.polis.get_calls[0]
check("zone= object key works (the 27B shape)",
      path2 == "/polis/targets" and params2.get("zone") == "berries"
      and params2.get("mode") == "all" and obs2 == obs,
      str((params2, obs2)))

# further alias shapes the 27B reaches for
obs3 = oik.do_tool("query", {"zonename": "berries", "mode": "all"},
                   "strict")
check("zonename= alias works", obs3 == obs, obs3)
oik.polis.cmd_calls.clear()
obs4 = oik.do_tool("zone", {"cmd": "list"}, "guarded")
check("zone cmd= alias reaches zone-list (guarded read)",
      ("zone-list", []) in oik.polis.cmd_calls and "DENIED" not in obs4,
      str((oik.polis.cmd_calls, obs4)))

# --- query: the digest's ceiling ------------------------------------------------
d = oikistes._targets_digest(
    {"Blocks": [{"Code": "game:stone", "Pos": [i, 0, i]}
                for i in range(50)]}, cap=12)
check("digest caps its line list and reports the remainder",
      d.count("stone@") == 12 and "(+38 more)" in d, d)
d = oikistes._targets_digest(
    {"blocks": [{"code": "game:stone", "pos": [i, 0, i]}
                for i in range(50)]}, cap=12)
check("digest tolerates camelCase payloads",
      d.count("stone@") == 12, d)
d = oikistes._targets_digest({"Blocks": []}, cap=12)
check("empty scan reads as a state, not an error",
      d == "targets: 0 (blocks=0 entities=0)", d)

print()
print("oikistes-tools-test: %d passed, %d failed" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)

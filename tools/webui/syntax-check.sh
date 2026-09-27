#!/usr/bin/env bash
# ESM syntax gate for the web ui (2026-09-27, 14th pass):
# `node --check` parses as CJS/script and can miss module-level constructs;
# acorn with sourceType:module is the real check. Run before every deploy:
#   tools/webui/syntax-check.sh
# The 2026-09-27 incident: a stray top-level '}' (from an edit) passed
# node --check but killed the whole module in the browser — the UI loaded
# dead (no polling, no wiring) with zero visible errors.
set -e
cd "$(dirname "$0")"
ACORN=$(npm root -g 2>/dev/null)/acorn
if [ ! -d "$ACORN" ]; then
    d=$(mktemp -d)
    npm i --prefix "$d" --no-audit --no-fund acorn >/dev/null 2>&1 || true
    [ -d "$d/node_modules/acorn" ] && ACORN="$d/node_modules/acorn"
fi
if [ ! -d "$ACORN" ]; then echo "acorn not installable (no network?) — cannot check" >&2; exit 2; fi
node -e "
const acorn = require('$ACORN');
const fs = require('fs');
let fail = 0;
for (const f of fs.readdirSync('js').sort()) {
    if (!f.endsWith('.js')) continue;
    try {
        acorn.parse(fs.readFileSync('js/' + f, 'utf8'), { ecmaVersion: 2022, sourceType: 'module' });
        console.log(f + ': OK');
    } catch (e) {
        console.log(f + ': FAIL — ' + e.message); fail = 1;
    }
}
process.exit(fail);
"

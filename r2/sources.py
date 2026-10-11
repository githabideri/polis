"""
R2 source map - the estate's survival knowledge: a material word
bridged to the block family that yields it and how it is extracted.

2026-10-11 incident: `gather flint x10` was rejected "no flint
resource with sufficient observed quantity" - not because flint was
absent, but because the observation ledger names a flint vein by its
first-seen block code (`ore-flint-andesite` -> material
"flint-andesite") and nothing told the compiler that `ore-flint-*`
IS flint. Sticks are not a block family at all: the item drops from
leaf blocks when they are chopped. This table encodes that bridge.

Pure module: no I/O. The live mission compiler (scripts/r2-live-mission.py)
compiles gather goals with it, the plan validator (r2/plancheck.py)
accepts a claim word when the measured drop code matches a source's
drop family, and the reflex (tests/reflex/sources-test.py) pins it.

Entries are verified against the game registry (1.22.7, scanned
2026-10-11): `families` are the block code prefixes that yield the
item when extracted, `drops` the item codes the ledger can observe
after extraction. The table is deliberately modest (early game): it is
survival knowledge, not world state - world state stays in the world
model.
"""


class Source:
    """One row of the map: what a material word means in the world."""

    def __init__(self, material, families, drops, kind="mine",
                 loose=(), tool=None, aliases=(), hand_families=()):
        self.material = material        # canonical claim word ("flint")
        self.families = tuple(families)  # block code prefixes ("ore-flint-")
        self.drops = tuple(drops)        # drop item codes / prefixes
        self.kind = kind                 # mine | chop | forage | harvestcrop
        self.loose = tuple(loose)        # loose ground-item codes (pickup)
        self.tool = tool                 # item required in the right hand
        self.aliases = tuple(aliases)    # other words that name this
        # 2026-10-11: the families breakable BEFORE a metal pickaxe
        # exists (hand/knife). A source may serve two eras - flint
        # comes from loose ground blocks early and from the ore vein
        # after M9; the allocator prefers the hand families and only
        # touches the rest when a pickaxe is in the cargo.
        self.hand_families = tuple(hand_families)

    def families_str(self):
        """The Job.expect comma list for the search/extract jobs."""
        return ",".join(list(self.families) + list(self.loose))

    def matches_code(self, code):
        """Does a (raw) block code belong to one of this source's
        block families?"""
        return any(fam_match(code, f) for f in self.families)

    def matches_drop(self, code):
        """Could this drop item code be the yield of extracting this
        source? (The validator's claim check for source-mapped
        materials: the ledger names the vein by block, the goal names
        the material.)"""
        c = _norm(code)
        if not c:
            return False
        return (c == self.material or c in self.aliases
                or any(fam_match(c, d) for d in self.drops)
                or any(fam_match(c, f) for f in self.families))

    def describe(self):
        return self.material


def _norm(code):
    """Registry normalization: lowercase, namespace prefix stripped
    (the live state serializes `game:<code>`)."""
    if not code:
        return ""
    c = str(code).strip().lower()
    if ":" in c:
        c = c.split(":", 1)[1]
    return c


def fam_match(code, family):
    """Family matching with the engine's snow-suffix tolerance: a
    trailing-'-' family is a prefix, a bare family is exact (plus its
    `-free` snow-covered twin - the world appends `-free` to a
    snow-capped block, it is not a different thing)."""
    c = _norm(code)
    if not c or not family:
        return False
    f = str(family).strip().lower()
    if f.endswith("-"):
        return c.startswith(f)
    return c == f or c == f + "-free"


def fam_match_resource(rec, families):
    """Family matching against a WORLD-MODEL resource record, which
    stores the CLASSIFIED material, not the raw block code
    (2026-10-11: classify strips the kind prefix - the ore block
    `ore-flint-claystone` becomes kind=ore, material=flint-claystone -
    so the family `ore-flint-` no longer matches the stored code and
    the search-derived gather resolution saw a world full of flint
    ore it could not name). Unknown-kind records keep the full code as
    their material and match as before. Matches the stored code and,
    where the kind is a classified prefix, the reconstructed raw code
    (`kind-material`)."""
    codes = []
    if isinstance(rec, str):
        codes = [rec]
    else:
        codes = [getattr(rec, "code", None) or ""]
        kind = getattr(rec, "kind", None)
        mat = getattr(rec, "material", None)
        if kind and mat and kind != "block":
            codes.append("%s-%s" % (kind, mat))
    out = False
    for f in families:
        if not f or not str(f).endswith("-"):
            continue
        f = str(f).strip().lower()
        for c in codes:
            c = str(c).lower()
            if c == f[:-1] or c.startswith(f):
                out = True
    return out


#: the map, in canonical order (early game first). Verified against
#: the live 1.22.7 registry 2026-10-11.
SOURCES = {
    "flint": Source(
        "flint", families=("ore-flint-", "looseflints-"),
        drops=("flint",), kind="mine",
        # 1.22: ore blocks need a pickaxe (copper tier, M9); the early
        # knives come from looseflints-* ground blocks (broken by hand/
        # knife into flint stones) - both families live here on purpose
        # so the same `gather flint` serves both eras.
        aliases=("flintstone",),
        hand_families=("looseflints-",)),
    "stick": Source(
        # 2026-10-11: leavesbranchy- ONLY. Plain leaves-* drop nothing
        # (measured live: a mined leaves-grown1-birch produced zero
        # sticks and the knife craft died on the empty grid). Every
        # leavesbranchy-* variant drops exactly 1 stick.
        "stick", families=("leavesbranchy-",),
        drops=("stick",), loose=("stick",), kind="chop"),
    "wood": Source(
        "wood", families=("log-grown-", "log-placed-", "wood-"),
        drops=("log-", "wood-"), kind="chop"),
    "cattail": Source(
        "cattail", families=("tallplant-coopersreed-",),
        drops=("cattailtops", "cattailroot"), kind="mine",
        tool="knife-generic-flint",
        aliases=("cattailtops", "cattailroot", "coopersreed", "reeds")),
    "drygrass": Source(
        # 2026-10-11 (G12 solved, ildasm-verified on 1.22.7): tallgrass
        # is CUT, not harvested. BlockBehaviorCuttableTallGrass.OnBlockBroken
        # fires when the breaker's active tool is a knife: the block drops
        # the knife-conditional loot (drygrass - the drop table entry with
        # Tool=Knife; ToRandomItemstackForPlayer matches it against the
        # actor's tool) and transitions to the "eaten" stub (regrows over
        # days). Without a knife the grass is destroyed, no drops - same
        # as vanilla. The knife gate lives in the mine action
        # (PolisMineBlockAction), so this source is kind=mine with the
        # knife tool; the harvestcrop command refuses all tallgrass.
        "drygrass", families=("tallgrass-",),
        drops=("drygrass",), kind="mine",
        tool="knife-generic-flint",
        # all tallgrass is hand-era (knife cut) - no pickaxe gate
        hand_families=("tallgrass-",),
        aliases=("dry grass", "tallgrass", "grass")),
    # 2026-10-11 (1.22.7 flora, vs-codes): all ten berry types collapsed
    # into ONE block family, fruitingbush-{state}-{type}-{cover} (state
    # wild/grown, cover free/snow), and the fruit is one `fruit` item
    # with fruit-{type} variants (there is no plain `berry` item). The
    # 1.21 bushes (big/smallberrybush) stay in the families for old
    # worlds; their type-named items (blueberry, whitecurrant, ...) are
    # the legacy drops. "cranberry" stays as an alias for continuity.
    "berry": Source(
        "berry", families=("fruitingbush-", "bigberrybush-",
                            "smallberrybush-"),
        drops=("fruit-", "blueberry", "whitecurrant", "cranberry",
               "redcurrant", "blackcurrant", "blackberry", "raspberry",
               "strawberry", "cloudberry", "beautyberry"), kind="forage",
        aliases=("berries", "berry", "currant", "blueberry",
                 "cranberry")),
    "dirt": Source(
        "dirt", families=("soil-", "dirt"),
        drops=("soil-", "dirt"), kind="mine",
        aliases=("soil", "earth")),
    "granite": Source(
        "granite", families=("rock-granite", "crackedrock-granite"),
        drops=("stone-granite", "granite"), kind="mine"),
    "stone": Source(
        "stone", families=("rock-stone",),
        drops=("stone-", "stone"), kind="mine"),
    "clay": Source(
        "clay", families=("rawclay-",),
        drops=("rawclay-", "clay"), kind="mine"),
    "sand": Source(
        "sand", families=("sand-",),
        drops=("sand-", "sand"), kind="mine"),
}

#: the canonical material words, in table order (operator-facing text)
MATERIALS = tuple(SOURCES)


def lookup(word):
    """Material word / item code / block code -> Source (or None).

    Three passes, most specific first: exact word/alias, then block
    family, then drop code. A goal object that names a BLOCK in the
    world ("tallplant-coopersreed-land-normal-free") lands on the
    source that yields it - the 2026-10-11 failure mode was that the
    goal named the material and the ledger named the block.
    """
    w = _norm(word)
    if not w:
        return None
    for s in SOURCES.values():
        if w == s.material or w in s.aliases:
            return s
    for s in SOURCES.values():
        if s.matches_code(w):
            return s
    for s in SOURCES.values():
        if s.matches_drop(w):
            return s
    return None


_PRETTY = (
    # (prefix, plain name) - the honest failure text speaks the
    # operator's language, not the registry's
    ("grass", "grass"),
    ("fern", "ferns"),
    ("soil-", "soil"),
    ("dirt", "soil"),
    ("leavesbranchy-grown1-birch", "birch branchy leaves"),
    ("leavesbranchy-", "branchy leaves"),
    ("leaves-grown1-birch", "birch leaves"),
    ("leaves-", "leaves"),
    ("tallplant-coopersreed-", "cooper's reed (cattail)"),
    ("tallplant-", "tall plant"),
    ("ore-flint-", "flint ore"),
    ("fruitingbush-", "fruiting bush"),
    ("rock-granite", "granite rock"),
    ("rock-stone", "stone"),
    ("rock-sandstone-", "sandstone"),
    ("sand-", "sand"),
    ("log-", "logs"),
)


def _pretty(code):
    c = _norm(code)
    for prefix, name in _PRETTY:
        if prefix.endswith("-"):
            if c.startswith(prefix):
                return name
        elif c == prefix or c == prefix + "-free":
            return name
    return c or "unknown"


def scan_report(counter, material):
    """The honest failure text: what the rings actually held.
    `counter` is {block code: count} over the final (widest scanned)
    ring's census."""
    total = sum(counter.values())
    seen = [_pretty(c) for c, _ in
            sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))]
    uniq = []
    for name in seen:
        if name not in uniq:
            uniq.append(name)
    return ("scanned %d blocks in all directions: %s; no %s"
            % (total, ", ".join(uniq[:6]) or "nothing", material))


def _fam_of_cluster(rec, families):
    """True if the resource record matches any of the (prefix) family
    globs - via fam_match_resource (the record holds the classified
    material, the families name the raw block codes)."""
    return fam_match_resource(rec, families)


def compile_gather_plan(clusters, goal, src, bot_pos=None, inv=None):
    """The deterministic gather compile for a source-mapped material.

    clusters: world-model records already filtered to this source's
    block families (distance ordering happens here). goal: the gather
    Goal. bot_pos: (x, z) for distance ordering (optional). inv: the
    bot's inventory (optional) - 2026-10-11: families outside the
    source's hand_families (e.g. flint ORE) need a metal pickaxe and
    are excluded until one is in the cargo (the engine refuses the
    bare-hand mine; pre-M9 the only flint is loose ground flint).
    Within an era, the hand families are allocated before the tool
    families.

    Two shapes:
      direct  - the ledger covers the quantity: one gather job per
                cluster, allocated nearest-first (the build mine-prep
                allocation pattern; no oversample - gather's quantity
                IS the claim).
      search  - the ledger lacks it: [search, gather] - the
                expanding-ring scan first, then the extract resolves
                its target at runtime against what the search
                registered (the found cells are not knowable at
                compile time, so the extract job carries the family
                globs, not a resource id).

    Returns (jobs, note) - a list of job dicts ready for Job.from_dict
    and the human-facing note for the run JSON.
    """
    n = max(1, int(goal.n or 1))

    def dist(r):
        if bot_pos is None or not r.centroid:
            return 0
        return (abs(int(r.centroid[0]) - int(bot_pos[0]))
                + abs(int(r.centroid[2]) - int(bot_pos[1])))

    # 2026-10-11: era-aware allocation (docstring). The hand families
    # come first; the tool families only join the plan when a
    # pickaxe is in the cargo.
    # 2026-10-11 (M3): exposed-before-roofed key (see the else below)
    _mk = lambda r: (0 if getattr(r, "mineable_cells", None) else 1, dist(r))
    hand_fams = getattr(src, "hand_families", None)
    if hand_fams:
        has_pickaxe = any(
            str(k).split(":")[-1].lower().startswith("pickaxe-")
            for k in (inv or {}))
        hand = [r for r in clusters
                if _fam_of_cluster(r, hand_fams)]
        tool = [r for r in clusters if r not in hand]
        if not has_pickaxe:
            tool = []
        cands = (sorted(hand, key=_mk)
                 + sorted(tool, key=_mk))
    # 2026-10-11 (M3): exposed clusters (scan-time mineable subset) rank
    # before roofed ones; a covered cluster costs an extra clear step
    # at execution and can exhaust a small job's budget (the birch's
    # branchy layer sits under its plain-leaf canopy). Covered clusters
    # still join - the executor clears the cover.
    else:
        cands = sorted(clusters, key=_mk)
    total = sum(int(r.observed_quantity or 0) for r in cands)

    if cands and total >= n:
        # the allocation cap grows as the cluster count shrinks - a
        # single-cluster world must not be capped below its own need
        # (the build mine-prep's 2026-10-07/10-10 lessons).
        per_cluster_cap = max(40, n // max(1, len(cands)))
        jobs = []
        need = n
        for r in cands:
            if need <= 0:
                break
            q = int(r.observed_quantity or 0)
            if q <= 0:
                continue
            take = min(need, q, per_cluster_cap)
            if take <= 0:
                continue
            jobs.append({
                "id": "j%d" % (len(jobs) + 1),
                "type": "gather",
                "source": r.id,
                "material": src.material,
                "quantity": take,
                "tool": src.tool,
                "origin": "deterministic",
            })
            need -= take
        return jobs, ("direct extract: the ledger covers %d of %d %s "
                      "(%d cluster%s)"
                      % (total, n, src.material, len(jobs),
                         "" if len(jobs) == 1 else "s"))
    # search-first: the world model lacks the quantity (or is empty)
    jobs = [
        {"id": "j1", "type": "search", "material": src.material,
         "expect": src.families_str(), "quantity": n,
         "origin": "deterministic"},
        {"id": "j2", "type": "gather", "material": src.material,
         "expect": src.families_str(),
         "quantity": n,
         "tool": src.tool,
         "plant": (src.families[0] + "*"
                   if src.kind == "forage" else None),
         "depends_on": ["j1"],
         "origin": "deterministic"},
    ]
    return jobs, ("search->extract: the ledger holds %d of %d %s "
                  "observed - search the rings first"
                  % (total, n, src.material))

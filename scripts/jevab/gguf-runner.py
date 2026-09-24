#!/usr/bin/env python3
"""gguf-runner.py -- Decider-2B readout over a llama.cpp GGUF checkpoint.

Same prompts, slots, and temperature as the bf16 torch path (decider.infer.Decider,
state_first layout, T=1.3): the prompt is built with the reference transformers
tokenizer (decider.prompt.build), the GGUF vocabulary is verified to re-encode it
to identical tokens, then llama.cpp executes the forward pass and the option
logits are read from the full-vocab logit row at the answer slot (the last
prompt position) -- exactly the computation the torch path does
(h[slot] @ lm_head[letters]ᵀ, softmax(./T)), with quantized weights in place
of bf16.

Usage (on the A/B container, vdec venv with llama-cpp-python installed):
  gguf-runner.py --gguf /var/jevab/weights/decider-2b-Q4_K_M.gguf \
      --sets /var/jevab/corpus/data/*.json --tag decider-q4 --out results/decider-q4.json
  add --smoke 5 for interface validation.

Output mirrors ab-runner.py: summary dict per tag plus a .rows.json sidecar.
"""
import argparse
import ctypes
import glob
import importlib.util
import json
import os
import sys
import time

import numpy

WEIGHTS = "/var/jevab/weights/decider-2b"
T = 1.3                    # decider_config.json "temperature" (state_first)
MAX_CTX_TOKENS = 1536      # Decider.decide_batch default
MAX_OPTIONS = 255          # decider_config.json
DECODE_CHUNK = 512

sys.path.insert(0, WEIGHTS)
from decider.prompt import build as dprompt_build, letter_ids, MAX_OPTIONS as DP_MAX  # noqa: E402
from decider.infer import Example, Q  # noqa: E402
from transformers import AutoTokenizer  # noqa: E402


class _NoShuffle:
    """ab-runner's no-shuffle rng: keeps option order as given."""
    def shuffle(self, x): pass
    def sample(self, xs, k): return xs[:k]


def _load_ab_module():
    spec = importlib.util.spec_from_file_location("ab_runner", "/var/jevab/ab-runner.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# --------------------------------------------------------------------------
# llama.cpp engine (pattern: semif_phase1/llamacpp_backend.py)
# --------------------------------------------------------------------------
_LIB = None
_MODEL = None

def _lib():
    global _LIB
    if _LIB is None:
        import llama_cpp
        llama_cpp.llama_backend_init()
        _LIB = llama_cpp
    return _LIB


def _load_model(gguf: str, threads: int, context_tokens: int):
    global _MODEL
    lib = _lib()
    params = lib.llama_model_default_params()
    params.n_gpu_layers = 0
    model = lib.llama_model_load_from_file(gguf.encode("utf-8"), params)
    if not model:
        raise RuntimeError(f"llama.cpp failed to load {gguf}")
    _MODEL = model
    return model


class Engine:
    """One llama.cpp context; per-row clear + prefill + slot logit row."""

    def __init__(self, model, context_tokens: int, threads: int):
        lib = _lib()
        params = lib.llama_context_default_params()
        params.n_ctx = context_tokens
        params.n_seq_max = 1
        params.n_outputs_max = 1
        params.n_threads = threads
        params.n_threads_batch = threads
        self.model = model
        self.lib = lib
        self.context = lib.llama_init_from_model(model, params)
        if not self.context:
            raise RuntimeError("llama.cpp failed to create the context")
        self.memory = lib.llama_get_memory(self.context)
        if not self.memory:
            lib.llama_free(self.context)
            self.context = None
            raise RuntimeError("llama.cpp returned no context memory")
        self.vocab = lib.llama_model_get_vocab(model)
        self.vocab_size = lib.llama_n_vocab(self.vocab)

    def close(self):
        if self.context:
            self.lib.llama_free(self.context)
            self.context = None

    def tokenize(self, text: str):
        lib, vocab = self.lib, self.vocab
        data = text.encode("utf-8")
        needed = lib.llama_tokenize(vocab, data, len(data), None, 0, False, True)
        if needed < 0:
            needed = -needed
        tokens = (lib.llama_token * needed)()
        written = lib.llama_tokenize(vocab, data, len(data), tokens, needed, False, True)
        if written < 0:
            raise RuntimeError("GGUF tokenizer rejected the prompt")
        return list(tokens[:written])

    def piece(self, token: int) -> bytes:
        buf = ctypes.create_string_buffer(64)
        written = self.lib.llama_token_to_piece(self.vocab, token, buf, len(buf), 0, True)
        if written < 0:
            raise RuntimeError(f"cannot render token {token}")
        return buf.raw[:written]

    def prefill_logits(self, tokens: list[int]):
        """Clear memory, decode the whole sequence, return the full-vocab logit
        row at the last position (the answer slot)."""
        lib = self.lib
        lib.llama_memory_clear(self.memory, True)   # void in this API; wipe data too
        ctx = self.context
        total = len(tokens)
        last = total - 1
        for offset in range(0, total, DECODE_CHUNK):
            chunk = tokens[offset:offset + DECODE_CHUNK]
            batch = lib.llama_batch_init(len(chunk), 0, 1)
            try:
                for i in range(len(chunk)):
                    batch.token[i] = chunk[i]
                    batch.pos[i] = offset + i
                    batch.n_seq_id[i] = 1
                    batch.seq_id[i][0] = 0
                    batch.logits[i] = int(offset + i == last)
                batch.n_tokens = len(chunk)
                if lib.llama_decode(ctx, batch):
                    raise RuntimeError("llama_decode failed (raise --ctx if prompts grew)")
            finally:
                lib.llama_batch_free(batch)
        ptr = lib.llama_get_logits_ith(ctx, -1)
        if not ptr:
            raise RuntimeError("no logits returned for the slot position")
        row = numpy.ctypeslib.as_array(
            ctypes.cast(ptr, ctypes.POINTER(ctypes.c_float)), shape=(self.vocab_size,)).copy()
        return row


class GgufDecider:
    def __init__(self, gguf: str, threads: int = 4, context_tokens: int = 4096):
        self.tok = AutoTokenizer.from_pretrained(WEIGHTS)
        self.letters = letter_ids(self.tok)
        model = _load_model(gguf, threads, context_tokens)
        self.engine = Engine(model, context_tokens, threads)
        self.mismatches = 0

        # fail early if the GGUF vocabulary is not the reference tokenizer's own
        probe = "probe evidence"
        ref = self.tok.encode(probe, add_special_tokens=False)
        if self.engine.tokenize(probe) != ref:
            raise RuntimeError("GGUF vocabulary disagrees with the reference tokenizer")
        for j, L in enumerate("ABCD"):
            enc = self.tok.encode(L, add_special_tokens=False)
            if len(enc) != 1 or self.engine.piece(enc[0]) != L.encode():
                raise RuntimeError(f"letter {L} is not a shared single token")

    def decide(self, state: str, options: list, q: str) -> dict:
        item = dprompt_build(
            Example(state, [Q(q, list(options), 0)], "infer"),
            self.tok, _NoShuffle(),
            max_options=min(MAX_OPTIONS, DP_MAX), max_ctx_tokens=MAX_CTX_TOKENS,
            layout="state_first")
        ids, slot, nopts = item["ids"], item["slots"][0], item["nopts"][0]
        assert slot == len(ids) - 1, f"slot {slot} != last pos {len(ids)-1}; runner assumes trailing slot"
        text = self.tok.decode(ids)
        if self.engine.tokenize(text) != ids:
            self.mismatches += 1
            return {"ok": False, "note": "tokenization mismatch",
                    "probs": {o: 0.0 for o in options}, "choice": None, "ms": 0.0}

        ts = time.perf_counter()
        try:
            row = self.engine.prefill_logits(ids)
        except RuntimeError as e:
            return {"ok": False, "note": str(e),
                    "probs": {o: 0.0 for o in options}, "choice": None,
                    "ms": (time.perf_counter() - ts) * 1000.0}
        ms = (time.perf_counter() - ts) * 1000.0

        lps = numpy.array([float(row[t]) for t in self.letters[:nopts]], dtype=numpy.float32)
        m = lps.max()
        e = numpy.exp((lps - m) / T)          # softmax(logits / T), as in the torch path
        probs = {o: float(v) for o, v in zip(options, e / e.sum())}
        choice = max(probs, key=probs.get)
        return {"ok": True, "note": "", "probs": probs, "choice": choice, "ms": ms}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gguf", required=True)
    ap.add_argument("--sets", required=True)
    ap.add_argument("--tag", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--ctx", type=int, default=4096)
    ap.add_argument("--smoke", type=int, default=0)
    args = ap.parse_args()

    ab = _load_ab_module()
    rows = ab.load_rows(args.sets)
    if args.smoke:
        seen, sel = set(), []
        for r in rows:
            if r["mission"] not in seen:
                seen.add(r["mission"])
                sel.append(r)
        rows = sel[:args.smoke]
    print(f"loaded {len(rows)} rows", file=sys.stderr)

    dec = GgufDecider(args.gguf, args.threads, args.ctx)

    # warmup (first decode compiles/allocates kernels)
    probe = dec.decide("probe state", ["a", "b"], "q?")
    print(f"warmup: ok={probe['ok']} note={probe['note']!r} ms={probe['ms']:.0f}", file=sys.stderr)
    if not probe["ok"]:
        print("FATAL: warmup failed", file=sys.stderr)
        sys.exit(2)

    out_rows = []
    t0 = time.perf_counter()
    for r in rows:
        d = dec.decide(r["state"], r["options"], ab.CHOICE_Q)
        r["ms"] = d["ms"]
        r["probs"] = {o: float(d["probs"].get(o, 0.0)) for o in r["options"]}
        r["choice"] = d["choice"]
        out_rows.append(r)
        print(f"  {args.tag} {r['set']}#{r['step']}: {r['choice']} "
              f"p_oracle={r['probs'][r['oracle']]:.3f} ok={d['ok']} ms={r['ms']:.0f}",
              file=sys.stderr)

    wall = time.perf_counter() - t0
    ok_rows = [r for r in out_rows if r["choice"] is not None]
    s = ab._by_mission(ok_rows, ab.summarize(ok_rows, args.tag))
    s["rows_total"] = len(out_rows)
    s["rows_ok"] = len(ok_rows)
    s["tokenize_mismatches"] = dec.mismatches
    s["wall_s"] = round(wall, 1)
    s["gguf"] = os.path.basename(args.gguf)

    out = {"corpus": args.sets, "rows": len(out_rows), "models": {args.tag: s}}
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(out, f, indent=1)
    with open(args.out + ".rows.json", "w") as f:
        json.dump(out_rows, f, indent=1)
    print(json.dumps(s, indent=1))


if __name__ == "__main__":
    main()

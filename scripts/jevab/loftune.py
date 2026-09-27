#!/usr/bin/env python3
"""loftune.py -- LoRA fine-tune of the Decider-2B onto the 7-option
polis action set (2026-09-25, the 12 GB 3060).

Trains a LoRA adapter on top of the current Decider checkpoint
(Qwen3.5-2B, already task-tuned on 4-5 options) so the model can
SELECT the new options (pickup_item, place_block) instead of only
assigning them mass -- the measured detector-not-selector gap.

Prompt contract = decider-service.py /prompt, exactly:
  Context:\n{state}\n\nQuestion: {CHOICE_Q}\nOptions:\n(A) opt1\n...\nAnswer: (
Target = the single oracle-letter token after the prefill (the readout
reads exactly one letter from n_probs; T=1.3 is applied at serving).

Split: groups = (family, oracle) kept together (related records leak
otherwise); 80/20 train/holdout, fixed seed. The holdout is the
evaluation set (top-1 + mean p(oracle) over the letter subset, matching
the serving readout).

Usage (the 3060 model container ft-venv, GPU):
  python3 loftune.py --model /root/ft-models/decider-2b \
      --rows /root/ft-models/ft-rows-2026-09-25.json \
      --out /root/ft-out/decider-7opt [--merge] [--epochs 4] [--lr 1e-4]
"""
import argparse
import json
import math
import random
import time
from collections import defaultdict

import torch
from torch.utils.data import Dataset


CHOICE_Q = ("Given the bot's current game state, choose the single best "
            "action for the bot to execute next.")


def build_prompt(state, options):
    lines = "\n".join("(%s) %s" % (chr(65 + i), o) for i, o in enumerate(options))
    return ("Context:\n%s\n\nQuestion: %s\nOptions:\n%s\nAnswer: ("
            % (state, CHOICE_Q, lines))


def letter_of(options, oracle):
    return chr(65 + options.index(oracle))


class Rows(Dataset):
    def __init__(self, rows, tok, seq=512):
        self.rows, self.tok, self.seq = rows, tok, seq

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, i):
        r = self.rows[i]
        p = build_prompt(r["state"], r["options"])
        t = letter_of(r["options"], r["oracle"])
        ids = self.tok(p, add_special_tokens=False)["input_ids"]
        ids = ids[-(self.seq - 1):]
        tgt_ids = self.tok(t, add_special_tokens=False)["input_ids"][:1]
        input_ids = torch.tensor(ids + tgt_ids, dtype=torch.long)
        labels = torch.full((len(input_ids)), -100, dtype=torch.long)
        labels[-1] = tgt_ids[0]
        return {"input_ids": input_ids, "labels": labels,
                "letter": tgt_ids[0], "options": r["options"],
                "oracle": r["oracle"]}


def collate_one(item):
    """Padding-free single sample (the Qwen3.5 hybrid forward trips on
    left-padded batches on this stack; rows are short, batch-1 is fine)."""
    return {"input_ids": item["input_ids"].unsqueeze(0),
            "attention_mask": torch.ones(1, item["input_ids"].shape[0],
                                         dtype=torch.long),
            "labels": item["labels"].unsqueeze(0),
            "meta": (item["letter"], item["options"], item["oracle"])}


def letter_probs(model, ids, am, letters):
    """Serving-style readout: softmax over the option-letter token
    subset only (T=1.0; T=1.3 applied downstream)."""
    out = model(input_ids=ids, attention_mask=am, return_dict=True)
    logits = out.logits[:, -1] # (B, V)
    sub = torch.stack([logits[:, i] for i in letters], dim=1) # (B, N)
    return torch.softmax(sub, dim=1)


def evaluate(model, ds, tok, device, batch=1):
    n = len(ds)
    idx = list(range(n))
    correct, p_oracle_sum, letters_by_row = 0, 0.0, []
    for i in range(0, n, batch):
        for j in idx[i:i + batch]:
            b = collate_one(ds[j])
            ids, am = b["input_ids"].to(device), b["attention_mask"].to(device)
            letter, options, oracle = b["meta"]
            letter_ids = [tok(o_, add_special_tokens=False)["input_ids"][0]
                          for o_ in options]
            letters = torch.tensor(letter_ids, device=device)
            with torch.no_grad():
                probs = letter_probs(model, ids, am, letters).cpu()[0]
            k = list(options).index(oracle)
            letters_by_row.append([p.item() for p in probs])
            p_oracle_sum += probs[k].item()
            if int(probs.argmax().item()) == k:
                correct += 1
    return {"n": n, "top1": correct / n,
            "mean_p_oracle": p_oracle_sum / n,
            "letters": letters_by_row}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--rows", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--epochs", type=int, default=12)
    ap.add_argument("--lr", type=float, default=2e-5)
    ap.add_argument("--batch", type=int, default=4)
    ap.add_argument("--grad-accum", type=int, default=2)
    ap.add_argument("--seq", type=int, default=512)
    ap.add_argument("--r", type=int, default=8)
    ap.add_argument("--alpha", type=int, default=16)
    ap.add_argument("--seed", type=int, default=20260925)
    ap.add_argument("--holdout-frac", type=float, default=0.2)
    ap.add_argument("--val-rows", default=None,
                    help="separate validation world (generated with a "
                         "different seed/ranges). When given: train on ALL "
                         "--rows, evaluate/early-stop on this file instead "
                         "of the internal holdout. THE overfitting guard: "
                         "adoption requires the val world to improve too.")
    ap.add_argument("--patience", type=int, default=3,
                    help="early-stop: stop after this many epochs without a "
                         ">=0.01 improvement of val mean_p_oracle (the "
                         "memory-law lock-in tripwire)")
    ap.add_argument("--merge-only", action="store_true",
                    help="skip training; load the adapter from --out, merge "
                         "into the base, write --out-merged")
    ap.add_argument("--merge", action="store_true",
                    help="merge the adapter into a full HF checkpoint at --out-merged")
    ap.add_argument("--out-merged", default=None)
    a = ap.parse_args()

    if a.merge_only:
        from transformers import AutoModelForCausalLM, AutoTokenizer
        from peft import PeftModel
        base = AutoModelForCausalLM.from_pretrained(
            a.model, torch_dtype=torch.bfloat16)
        full = PeftModel.from_pretrained(base, a.out).merge_and_unload()
        outm = a.out_merged or (a.out + "-merged")
        full.save_pretrained(outm)
        tok = AutoTokenizer.from_pretrained(a.out)
        tok.save_pretrained(outm)
        print("merged checkpoint:", outm, flush=True)
        return

    torch.manual_seed(a.seed)
    random.seed(a.seed)
    rows = json.load(open(a.rows))
    rows = [r for r in rows if r["oracle"] in r["options"]]
    print("rows:", len(rows), flush=True)

    from transformers import AutoModelForCausalLM, AutoTokenizer
    tok = AutoTokenizer.from_pretrained(a.model)
    t0 = time.time()
    model = AutoModelForCausalLM.from_pretrained(
        a.model, torch_dtype=torch.bfloat16)
    print("loaded in %.1fs; params: %.2fB" % (
        time.time() - t0, sum(p.numel() for p in model.parameters()) / 1e9),
        flush=True)
    model.to("cuda:0")

    from peft import LoraConfig, get_peft_model
    cfg = LoraConfig(r=a.r, lora_alpha=a.alpha, lora_dropout=0.05,
                     bias="none", target_modules="all-linear")
    model = get_peft_model(model, cfg)
    model.print_trainable_parameters()
    model.gradient_checkpointing_enable()

    # split: with --val-rows the whole --rows file trains and the external
    # validation world scores; otherwise grouped 80/20 as before
    if a.val_rows:
        val = json.load(open(a.val_rows))
        val = [r for r in val if r["oracle"] in r["options"]]
        train_idx, hold_idx = list(range(len(rows))), [i for i in range(len(val))]
        val_rows = val
        print("training on ALL %d rows; external val world: %d rows" %
              (len(rows), len(val)), flush=True)
    else:
        val_rows = None
        groups = defaultdict(list)
        for i, r in enumerate(rows):
            groups[(r.get("family") or r.get("mission") or "?", r["oracle"])].append(i)
        gkeys = sorted(groups)
        random.shuffle(gkeys)
        hold = int(len(gkeys) * a.holdout_frac)
        hold_groups = set(gkeys[:hold])
        train_idx = [i for g in gkeys for i in groups[g] if g not in hold_groups]
        hold_idx = [i for g in hold_groups for i in groups[g]]
        print("groups: %d; train %d / holdout %d" %
              (len(gkeys), len(train_idx), len(hold_idx)), flush=True)
    tr, te = Rows([rows[i] for i in train_idx], tok, a.seq), \
        Rows([val_rows[i] if val_rows else rows[i] for i in hold_idx], tok, a.seq)

    opt = torch.optim.AdamW(
        [p for p in model.parameters() if p.requires_grad], lr=a.lr,
        weight_decay=0.0)
    total = a.epochs * math.ceil(len(tr) / (a.batch * a.grad_accum))
    warm = int(total * 0.05)

    def lr_lambda(step):
        if step < warm:
            return step / max(warm, 1)
        return max(0.0, 1 - (step - warm) / max(total - warm, 1))
    sched = torch.optim.lr_scheduler.LambdaLR(opt, lr_lambda)

    dev = "cuda:0"
    micro = [tr[i] for i in range(len(tr))]
    best = {"top1": 0.0, "mean_p_oracle": 0.0}
    stale = 0
    for ep in range(1, a.epochs + 1):
        random.shuffle(micro)
        model.train()
        t0 = time.time()
        run_loss, steps = 0.0, 0
        opt.zero_grad()
        for i, item in enumerate(micro):
            b = collate_one(item)
            out = model(input_ids=b["input_ids"].to(dev),
                        attention_mask=b["attention_mask"].to(dev),
                        labels=b["labels"].to(dev))
            (out.loss / a.grad_accum).backward()
            run_loss += out.loss.item()
            steps += 1
            if (i + 1) % a.grad_accum == 0 or (i + 1) == len(micro):
                torch.nn.utils.clip_grad_norm_(
                    [p for p in model.parameters() if p.requires_grad], 1.0)
                opt.step()
                sched.step()
                opt.zero_grad()
        model.eval()
        with torch.no_grad():
            ev = evaluate(model, te, tok, dev)
        el = run_loss / max(steps, 1)
        print("epoch %d: loss %.4f val top1 %.3f val mean_p_oracle %.3f (%.0fs)"
              % (ep, el, ev["top1"], ev["mean_p_oracle"], time.time() - t0),
              flush=True)
        # selection + early-stop on val mean_p_oracle (memory-law tripwire:
        # lock-in begins as per-row p crosses 0.5 while top-1 may still look fine)
        if ev["mean_p_oracle"] > best["mean_p_oracle"] + 0.01:
            best = ev
            best["epoch"] = ep
            stale = 0
            unmerged = model if hasattr(model, "base_model") else model
            unmerged.save_pretrained(a.out)
            tok.save_pretrained(a.out)
        else:
            stale += 1
            if stale >= a.patience:
                print("early stop at epoch %d (no val p_oracle improvement "
                      "for %d epochs)" % (ep, stale), flush=True)
                break
        # (the best adapter is already on disk from the epoch that set it)
    print("best val: top1 %.3f p_oracle %.3f (epoch %s)" % (
        best["top1"], best["mean_p_oracle"], best.get("epoch")), flush=True)

    if a.merge:
        from peft import PeftModel
        base = AutoModelForCausalLM.from_pretrained(
            a.model, torch_dtype=torch.bfloat16)
        full = PeftModel.from_pretrained(base, a.out).merge_and_unload()
        outm = a.out_merged or (a.out + "-merged")
        full.save_pretrained(outm)
        tok.save_pretrained(outm)
        print("merged checkpoint:", outm, flush=True)


if __name__ == "__main__":
    main()

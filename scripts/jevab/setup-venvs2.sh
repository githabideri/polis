#!/bin/bash
# (Re)build the two A/B venvs on the CPU batch box. Idempotent. Python 3.13 (Debian 13),
# torch-CPU wheels. Decider runs with use_graphs=False (no CUDA); its model code
# is the package shipped inside the weights dir. SemIf is the public repo
# TheoLeeCJ/SemIf, used via PYTHONPATH (its pyproject is unusable upstream).
set -x
cd /var/jevab
rm -rf vdec vsem
python3 -m venv vdec
./vdec/bin/python -m ensurepip --upgrade || exit 1
./vdec/bin/pip install -q torch --index-url https://download.pytorch.org/whl/cpu || exit 1
./vdec/bin/pip install -q transformers || exit 1
python3 -m venv vsem
./vsem/bin/python -m ensurepip --upgrade || exit 1
./vsem/bin/pip install -q torch --index-url https://download.pytorch.org/whl/cpu || exit 1
./vsem/bin/pip install -q transformers || exit 1
echo SETUP2-DONE
touch /var/jevab/setup2-done

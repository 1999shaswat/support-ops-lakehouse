#!/bin/bash
set -e

source ../.venv/bin/activate
python generate_dimensions.py --outdir ../data/dimensions --n-companies 25

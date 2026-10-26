#!/bin/bash
set -e

source ../.venv/bin/activate
python generate_dimensions.py --outdir ../data/entities --n-companies 25

#!/bin/bash
set -e

source ../.venv/bin/activate

MODE="${1:-}"

case "$MODE" in
    backfill)
        python generate_facts_stream.py backfill \
            --dim-dir ../data/dimensions \
            --landing ../data/landing \
            --days 1000 --tickets-per-day 10
        aws s3 sync ../data s3://support-ops-lakehouse-data --profile s3-uploader
        echo "[SUCCESS] Backfill complete."
        ;;
    live)
        trap 'kill 0' EXIT

        echo "Generator started. Starting continuous S3 sync..."

        python generate_facts_stream.py live \
            --dim-dir ../data/dimensions \
            --landing ../data/landing \
            --interval 10 --batch-size 10 --iterations 30 &
        
        # Continuous sync loop
        while true; do
            aws s3 sync ../data/landing s3://support-ops-lakehouse-data/landing --profile s3-uploader
            sleep 10
        done
        ;;
    *)
        echo "Usage: $0 {backfill|live}"
        exit 1
        ;;
esac

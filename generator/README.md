# Fake data generators for the ticket-support schema

## 1. Dimensions (direct/batch import)

```
pip install faker --break-system-packages
python generate_dimensions.py --outdir ../data/dimensions --n-companies 25
```

Writes `dim_region.csv`, `dim_date.csv`, `dim_product.csv`, `dim_customer.csv`,
`dim_agent.csv`, plus a `_keys.json` manifest the fact generator reads so IDs
actually join correctly.

Upload this folder to a Volume and `COPY INTO` each dim table directly — no
Auto Loader needed, these are full-snapshot loads.

Note: `dim_agent` intentionally understaffs **Technical Support** (10 agents
vs 14-28 in other teams). The fact generator routes ~35% of ticket volume
there on purpose. That mismatch is what will actually produce a shuffle/skew
problem when you group or join on `agent_id`/`team` in Silver — you don't
need to fake the skew diagnosis, it'll be real.

## 2. Facts (streaming / Auto Loader)

Two simulated source systems land in different subfolders under the same
root, with deliberately different shapes:

- `zendesk_export`: JSON lines, ISO-8601 timestamps, ~3% missing `agent_id`
  (unassigned queue)
- `legacy_crm`: CSV, epoch-millis timestamps, different field names
  (`ticketId`, `custId`, `assignedAgent`...), ~8% missing agent, ~2%
  duplicate re-exported rows

**Backfill mode** (most of what you need for building Bronze/Silver):
```
python generate_facts_stream.py backfill \
    --dim-dir ../data/dimensions \
    --landing ../data/landing \
    --days 1000 --tickets-per-day 100
```
Writes historical `tickets_created/`, `tickets_resolved/`, and
`ticket_transfers/` events, partitioned by `source=`/`dt=`. Point Auto
Loader's `cloudFiles` source at `tickets_created/` and `tickets_resolved/`
separately (different schemas per source, so land them in Bronze as two
raw tables, unify in Silver).

**`fact_ticket` is an accumulating snapshot**: each ticket appears first as
a `created` event (resolved fields null), then ~95% get a second `resolved`
event some days later, arriving as a *separate file, separate load*. This
is what forces a real `MERGE INTO ... WHEN MATCHED UPDATE` in Silver rather
than a plain append — matching what an accumulating snapshot fact actually
requires.

**Live/trickle mode** (to actually demo Auto Loader detecting new files,
e.g. for your README demo clip):
```
python generate_facts_stream.py live \
    --dim-dir ../data/dimensions \
    --landing ../data/landing \
    --interval 10 --batch-size 5 --iterations 30
```

Run this in one terminal while a Structured Streaming read against
`./data/landing` is active in a notebook — new files show up every
10 seconds.

Syncing folder to s3:

```
while true; do 
  aws s3 sync ../data/landing s3://support-ops-lakehouse-data/landing --profile s3-uploader
  sleep 10
done
```

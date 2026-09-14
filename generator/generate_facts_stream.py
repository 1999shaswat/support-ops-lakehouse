"""
Generates fact_ticket / fact_ticket_transfer as event files landing in
per-source folders, for Auto Loader ingestion.

Two simulated source systems, deliberately inconsistent:
  - zendesk_export : JSON lines, ISO-8601 timestamps, field names close to your schema
  - legacy_crm      : CSV, epoch-millis timestamps, different field names,
                       occasionally missing agent assignment, occasional
                       duplicate ticket_id rows (re-exports)

fact_ticket is an ACCUMULATING SNAPSHOT: each ticket lands first as a
'created' record (resolved fields null), then some tickets later get a
second 'resolved' event for the same ticket_id -> forces a real MERGE INTO
in Silver instead of append-only.

Team skew is intentional: Technical Support (10 agents, from dim_agent) is
made to receive ~35% of ticket volume -> real shuffle/skew during any
groupBy/join on agent_id or team, for Milestone 3.

Usage:
    # one-shot historical backfill (most of what you need for Bronze dev)
    python generate_facts_stream.py backfill --landing ./data/landing --days 45 --tickets-per-day 250

    # live trickle mode, to actually demo Auto Loader picking up new files
    python generate_facts_stream.py live --landing ./data/landing --interval 10 --batch-size 5
"""

import argparse
import csv
import io
import json
import os
import random
import time
import uuid
from datetime import datetime, timedelta, timezone

random.seed(7)

PRIORITIES = ["Low", "Medium", "High", "Urgent"]
PRIORITY_WEIGHTS = [0.35, 0.35, 0.20, 0.10]
SLA_HOURS = {"Low": 72, "Medium": 48, "High": 24, "Urgent": 4}
TRANSFER_REASONS = ["miscategorization", "scope_ambiguity", "escalation", "other"]
CATEGORY_BY_PRODUCT_CAT = {
    "Core Platform": ["Bug", "How-to", "Performance Issue"],
    "Integrations": ["Integration Issue", "Bug", "How-to"],
    "Billing": ["Billing Question", "Bug"],
    "Mobile": ["Bug", "How-to", "Performance Issue"],
    "Analytics": ["Bug", "Feature Request", "How-to"],
}


def load_keys(dim_dir):
    with open(f"{dim_dir}/_keys.json") as f:
        return json.load(f)


def pick_category(product_id, product_categories):
    prod_cat = product_categories.get(product_id, "Core Platform")
    return random.choice(CATEGORY_BY_PRODUCT_CAT[prod_cat])


def pick_agent(agents, skew_team="Technical Support", skew_prob=0.35):
    """Skew ticket assignment toward one understaffed team on purpose."""
    if random.random() < skew_prob:
        pool = [a for a in agents if a[1] == skew_team]
        if pool:
            return random.choice(pool)
    return random.choice(agents)


def gen_ticket_created(keys, event_date):
    ticket_id = f"T{uuid.uuid4().hex[:10]}"
    customer_id = random.choice(keys["customer_ids"])
    product_id = random.choice(keys["product_ids"])
    agent_id, team = pick_agent(keys["agents"])
    priority = random.choices(PRIORITIES, weights=PRIORITY_WEIGHTS)[0]
    created_at = event_date + timedelta(
        hours=random.randint(0, 23), minutes=random.randint(0, 59)
    )
    return {
        "ticket_id": ticket_id,
        "customer_id": customer_id,
        "product_id": product_id,
        "ticket_category": pick_category(product_id, keys["product_categories"]),
        "agent_id": agent_id,
        "team": team,
        "priority": priority,
        "created_at": created_at,
        "sla_target_hours": SLA_HOURS[priority],
    }


def gen_ticket_resolved(ticket):
    # Resolution time correlated with priority, with heavy-tail stragglers
    base_hours = {"Low": 40, "Medium": 20, "High": 10, "Urgent": 3}[ticket["priority"]]
    duration_hours = max(0.5, random.gauss(base_hours, base_hours * 0.6))
    resolved_at = ticket["created_at"] + timedelta(hours=duration_hours)
    sla_breached = duration_hours > ticket["sla_target_hours"]
    csat = None if random.random() < 0.4 else random.randint(1, 5)  # not everyone rates
    return {
        "ticket_id": ticket["ticket_id"],
        "resolved_at": resolved_at,
        "resolution_duration_hours": round(duration_hours, 2),
        "sla_breached": sla_breached,
        "csat": csat,
    }


def gen_transfer(ticket_id, event_dt):
    from_team, to_team = random.sample(
        list(
            {
                "Tier1 Support",
                "Tier2 Support",
                "Technical Support",
                "Billing Support",
                "Escalations",
            }
        ),
        2,
    )
    return {
        "ticket_id": ticket_id,
        "from_team": from_team,
        "to_team": to_team,
        "transfer_at": event_dt,
        "transfer_reason": random.choices(
            TRANSFER_REASONS, weights=[0.3, 0.25, 0.35, 0.10]
        )[0],
    }


# ---------- source-specific serialization (the "messy" part) ----------


def write_zendesk_created(rows, path):
    """JSON lines, ISO timestamps, mostly clean, occasional null agent (unassigned queue)."""
    with open(path, "w") as f:
        for t in rows:
            rec = {
                "ticket_id": t["ticket_id"],
                "customer_id": t["customer_id"],
                "product_id": t["product_id"],
                "ticket_category": t["ticket_category"],
                "agent_id": t["agent_id"] if random.random() > 0.03 else None,
                "priority": t["priority"],
                "created_at": t["created_at"].isoformat(),
                "sla_target_hours": t["sla_target_hours"],
                "_source": "zendesk_export",
            }
            f.write(json.dumps(rec) + "\n")


def write_legacy_created(rows, path):
    """CSV, epoch-millis timestamps, different field names, duplicate re-export rows."""
    fieldnames = [
        "ticketId",
        "custId",
        "prodId",
        "issueType",
        "assignedAgent",
        "prio",
        "created_epoch_ms",
        "sla_hrs",
    ]
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for t in rows:
            epoch_ms = int(
                t["created_at"].replace(tzinfo=timezone.utc).timestamp() * 1000
            )
            w.writerow(
                {
                    "ticketId": t["ticket_id"],
                    "custId": t["customer_id"],
                    "prodId": t["product_id"],
                    "issueType": t["ticket_category"],
                    "assignedAgent": t["agent_id"] if random.random() > 0.08 else "",
                    "prio": t["priority"].upper(),
                    "created_epoch_ms": epoch_ms,
                    "sla_hrs": t["sla_target_hours"],
                }
            )
            if random.random() < 0.02:  # ~2% duplicate re-export, same values
                w.writerow(
                    {
                        "ticketId": t["ticket_id"],
                        "custId": t["customer_id"],
                        "prodId": t["product_id"],
                        "issueType": t["ticket_category"],
                        "assignedAgent": (
                            t["agent_id"] if random.random() > 0.08 else ""
                        ),
                        "prio": t["priority"].upper(),
                        "created_epoch_ms": epoch_ms,
                        "sla_hrs": t["sla_target_hours"],
                    }
                )


def write_resolved_events(rows, path, source):
    with open(path, "w") as f:
        for r in rows:
            if source == "zendesk_export":
                rec = {
                    "ticket_id": r["ticket_id"],
                    "resolved_at": r["resolved_at"].isoformat(),
                    "resolution_duration_hours": r["resolution_duration_hours"],
                    "sla_breached": r["sla_breached"],
                    "csat": r["csat"],
                    "_source": source,
                }
            else:
                rec = {
                    "ticketId": r["ticket_id"],
                    "resolved_epoch_ms": int(
                        r["resolved_at"].replace(tzinfo=timezone.utc).timestamp() * 1000
                    ),
                    "duration_hrs": r["resolution_duration_hours"],
                    "breached": int(r["sla_breached"]),
                    "csat": r["csat"] if r["csat"] else "",
                }
            f.write(json.dumps(rec) + "\n")


def write_transfers(rows, path):
    with open(path, "w") as f:
        for t in rows:
            rec = dict(t)
            rec["transfer_at"] = rec["transfer_at"].isoformat()
            f.write(json.dumps(rec) + "\n")


# ---------- orchestration ----------


def run_day(
    keys, day_date, tickets_per_day, landing, resolve_within_days=5, transfer_prob=0.15
):
    created = [gen_ticket_created(keys, day_date) for _ in range(tickets_per_day)]
    split = len(created) // 2
    zendesk_tickets, legacy_tickets = created[:split], created[split:]

    day_str = day_date.strftime("%Y-%m-%d")
    zdir = f"{landing}/tickets_created/source=zendesk_export/dt={day_str}"
    ldir = f"{landing}/tickets_created/source=legacy_crm/dt={day_str}"
    os.makedirs(zdir, exist_ok=True)
    os.makedirs(ldir, exist_ok=True)
    write_zendesk_created(zendesk_tickets, f"{zdir}/part-{uuid.uuid4().hex[:8]}.jsonl")
    write_legacy_created(legacy_tickets, f"{ldir}/part-{uuid.uuid4().hex[:8]}.csv")

    # transfers, sourced only from zendesk for simplicity
    transferred = [t for t in created if random.random() < transfer_prob]
    if transferred:
        tdir = f"{landing}/ticket_transfers/dt={day_str}"
        os.makedirs(tdir, exist_ok=True)
        transfer_events = [
            gen_transfer(
                t["ticket_id"],
                t["created_at"] + timedelta(hours=random.uniform(0.5, 20)),
            )
            for t in transferred
        ]
        write_transfers(transfer_events, f"{tdir}/part-{uuid.uuid4().hex[:8]}.jsonl")

    return created  # caller tracks these to emit resolved events later


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="mode", required=True)

    bf = sub.add_parser("backfill")
    bf.add_argument("--landing", default="./data/landing")
    bf.add_argument("--dim-dir", default="./data/dimensions")
    bf.add_argument("--days", type=int, default=45)
    bf.add_argument("--tickets-per-day", type=int, default=250)
    bf.add_argument(
        "--start", default=None, help="YYYY-MM-DD, defaults to (today - days)"
    )

    live = sub.add_parser("live")
    live.add_argument("--landing", default="./data/landing")
    live.add_argument("--dim-dir", default="./data/dimensions")
    live.add_argument(
        "--interval", type=int, default=10, help="seconds between batches"
    )
    live.add_argument("--batch-size", type=int, default=5)
    live.add_argument("--iterations", type=int, default=30)

    args = ap.parse_args()
    keys = load_keys(args.dim_dir)

    if args.mode == "backfill":
        start = (
            datetime.fromisoformat(args.start)
            if args.start
            else datetime.now() - timedelta(days=args.days)
        )
        pending_resolution = []  # (ticket, resolve_on_date)

        for i in range(args.days):
            day = start + timedelta(days=i)
            created = run_day(keys, day, args.tickets_per_day, args.landing)
            for t in created:
                delay_days = max(0, round(random.gauss(3, 2)))
                pending_resolution.append((t, day + timedelta(days=delay_days)))

        # emit resolved events, grouped back by day, split by source like creation was
        by_resolve_day = {}
        for t, rday in pending_resolution:
            by_resolve_day.setdefault(rday.date(), []).append(t)

        for rday, tickets in by_resolve_day.items():
            resolved = [
                gen_ticket_resolved(t) for t in tickets if random.random() > 0.05
            ]  # ~5% never resolved (still open)
            split = len(resolved) // 2
            day_str = rday.strftime("%Y-%m-%d")
            zdir = f"{args.landing}/tickets_resolved/source=zendesk_export/dt={day_str}"
            ldir = f"{args.landing}/tickets_resolved/source=legacy_crm/dt={day_str}"
            os.makedirs(zdir, exist_ok=True)
            os.makedirs(ldir, exist_ok=True)
            if resolved[:split]:
                write_resolved_events(
                    resolved[:split],
                    f"{zdir}/part-{uuid.uuid4().hex[:8]}.jsonl",
                    "zendesk_export",
                )
            if resolved[split:]:
                write_resolved_events(
                    resolved[split:],
                    f"{ldir}/part-{uuid.uuid4().hex[:8]}.jsonl",
                    "legacy_crm",
                )

        total_created = sum(1 for _ in pending_resolution)
        print(
            f"Backfill complete: {args.days} days, ~{args.tickets_per_day}/day, "
            f"{total_created} tickets created under {args.landing}"
        )

    elif args.mode == "live":
        print(
            f"Streaming {args.batch_size} tickets every {args.interval}s "
            f"into {args.landing} — point Auto Loader at this path now."
        )
        for i in range(args.iterations):
            today = datetime.now()
            run_day(keys, today, args.batch_size, args.landing)
            print(
                f"[{datetime.now().strftime('%H:%M:%S')}] wrote batch {i+1}/{args.iterations}"
            )
            time.sleep(args.interval)


if __name__ == "__main__":
    main()

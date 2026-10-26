"""
Generates dim_* tables as CSVs.
Usage:
    python generate_dimensions.py --outdir ./data/entities
"""
import argparse
import csv
import random
from datetime import date, timedelta
from faker import Faker
import re

fake = Faker()
random.seed(42)
Faker.seed(42)

# ---------- dim_region ----------
REGIONS = [
    ("R01", "North America East", "United States", "America/New_York", -5),
    ("R02", "North America West", "United States", "America/Los_Angeles", -8),
    ("R03", "UK & Ireland", "United Kingdom", "Europe/London", 0),
    ("R04", "DACH", "Germany", "Europe/Berlin", 1),
    ("R05", "Nordics", "Sweden", "Europe/Stockholm", 1),
    ("R06", "ANZ", "Australia", "Australia/Sydney", 10),
    ("R07", "India", "India", "Asia/Kolkata", 5.5),
    ("R08", "LATAM", "Brazil", "America/Sao_Paulo", -3),
]

def write_dim_region(outdir):
    path = f"{outdir}/regions.csv"
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["region_id", "region_name", "country", "timezone", "utc_offset"])
        w.writerows(REGIONS)
    return path

# ---------- dim_date ----------
def write_dim_date(outdir, start="2023-01-01", end="2026-12-31"):
    path = f"{outdir}/dim_date.csv"
    d0 = date.fromisoformat(start)
    d1 = date.fromisoformat(end)
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date_id", "full_date", "day", "day_name", "week", "month", "month_name", "quarter", "year", "is_weekend"])
        d = d0
        while d <= d1:
            date_id = int(d.strftime("%Y%m%d"))
            w.writerow([
                date_id,
                d.isoformat(),
                d.day,
                d.strftime("%A"),
                d.isocalendar()[1],
                d.month,
                d.strftime("%B"),
                (d.month - 1) // 3 + 1,
                d.year,
                int(d.weekday() >= 5),
            ])
            d += timedelta(days=1)
    return path

# ---------- dim_product ----------
CATEGORIES = {
    "Core Platform": ["Workspace", "Reporting Engine", "API Gateway", "Admin Console"],
    "Integrations": ["Salesforce Connector", "Slack Connector", "Webhook Service"],
    "Billing": ["Invoicing", "Subscription Manager", "Payment Gateway"],
    "Mobile": ["iOS App", "Android App"],
    "Analytics": ["Dashboard Builder", "Data Export", "Alerting"],
}
SEGMENTS = ["SMB", "Mid-Market", "Enterprise"]
CONTACT_RANGES = {
    "SMB": (2, 5),
    "Mid-Market": (6, 15),
    "Enterprise": (18, 45),
}

def write_dim_product(outdir):
    path = f"{outdir}/products.csv"
    rows = []
    pid = 1
    for cat, products in CATEGORIES.items():
        for p in products:
            rows.append((f"P{pid:03d}", p, cat))
            pid += 1
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["product_id", "product_name", "product_category"])
        w.writerows(rows)
    return path, [r[0] for r in rows], {r[0]: r[2] for r in rows}  # {product_id: product_category}

# ---------- dim_customer ----------
def domain_from_company(name):
    slug = re.sub(r"[^a-z0-9]", "", name.lower().split(",")[0])[:20]
    return f"{slug}.com"

def quotas(n):
    """Generate segment quotas dynamically."""
    parts = [pow(2, i) for i in range(len(SEGMENTS) - 1, -1, -1)]  # exponential weights
    parts = [x * random.uniform(0.85, 1.15) for x in parts]
    total = sum(parts)
    q = [round(n * x / total) for x in parts]
    q[0] += n - sum(q)
    return dict(zip(SEGMENTS, q))

def build_companies(n_companies, region_ids):
    segment_quotas = quotas(n_companies)
    companies = []
    cid = 1
    for segment, count in segment_quotas.items():
        for _ in range(count):
            name = fake.company()
            companies.append({
                "company_id": f"COM{cid:05d}",
                "company_name": name,
                "domain": domain_from_company(name),
                "segment": segment,
                "region": random.choice(region_ids),
            })
            cid += 1
    random.shuffle(companies)
    return companies

def write_dim_company(outdir, companies):
    path = f"{outdir}/companies.csv"
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["company_id", "company_name", "domain", "customer_segment", "region_id"])
        for c in companies:
            w.writerow([c["company_id"], c["company_name"], c["domain"], c["segment"], c["region"]])
    return path

def write_dim_customer(outdir, companies):
    customer_ids = []
    path = f"{outdir}/customers.csv"
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["customer_id", "contact_name", "email", "company_id"])
        i = 1
        for company in companies:
            lo, hi = CONTACT_RANGES[company["segment"]]
            n_contacts = random.randint(lo, hi)
            for _ in range(n_contacts):
                cust_id = f"CUS{i:06d}"
                contact_name = fake.name()
                first, last = contact_name.lower().split()[0], contact_name.lower().split()[-1]
                email = f"{first}.{last}@{company['domain']}"
                w.writerow([cust_id, contact_name, email, company["company_id"]])
                customer_ids.append(cust_id)
                i += 1

    return path, customer_ids

# ---------- dim_agent ----------
# Deliberately skewed team sizes -> Technical Support is understaffed relative to
# the ticket volume it will receive (set in generate_facts_stream.py) for shuffle/skew diagnosis
TEAMS = {
    "Tier1 Support": 28,
    "Technical Support": 10,  # small team, will get a disproportionate ticket share
    "Billing Support": 14,
    "Tier2 Support": 16,
    "Escalations": 6,
}
LEVELS = {"Tier1 Support": "L1", "Billing Support": "L1", "Tier2 Support": "L2", "Technical Support": "L2", "Escalations": "L3"}

COMPANY_DOMAIN = "meridianworks.com"

def agent_email(name):
    first, last = name.lower().split()[0], name.lower().split()[-1]
    return f"{first}.{last}@{COMPANY_DOMAIN}"

def write_dim_agent(outdir, region_ids):
    path = f"{outdir}/agents.csv"
    rows = []
    aid = 1
    for team, count in TEAMS.items():
        lead_idx = random.randrange(count)
        for i in range(count):
            agent_id = f"A{aid:05d}"
            agent_name = fake.name()
            rows.append((
                agent_id,
                agent_name,
                agent_email(agent_name),
                random.choice(region_ids),
                team,
                LEVELS[team],
                int(i == lead_idx),
            ))
            aid += 1
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["agent_id", "agent_name", "email", "region_id", "team", "team_level", "team_lead"])
        w.writerows(rows)
    return path, [(r[0], r[4]) for r in rows]  # (agent_id, team)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", default="./data/entities")
    ap.add_argument("--n-companies", type=int, default=25)
    args = ap.parse_args()

    import os
    os.makedirs(args.outdir, exist_ok=True)

    write_dim_region(args.outdir)
    # write_dim_date(args.outdir)
    _, product_ids, product_categories = write_dim_product(args.outdir)
    region_ids = [r[0] for r in REGIONS]
    companies = build_companies(args.n_companies, region_ids)
    write_dim_company(args.outdir, companies)
    _, customer_ids = write_dim_customer(args.outdir, companies)
    _, agent_team_pairs = write_dim_agent(args.outdir, region_ids)

    print(f"Wrote dimensions to {args.outdir}")
    print(f"  products: {len(product_ids)}, customers: {len(customer_ids)}, agents: {len(agent_team_pairs)}")

    # Manifest for the fact generator to consume without re-deriving keys
    import json
    with open(f"{args.outdir}/_keys.json", "w") as f:
        json.dump(
            {
                "product_ids": product_ids,
                "product_categories": product_categories,  # {product_id: product_category}
                "customer_ids": customer_ids,
                "agents": agent_team_pairs,  # [agent_id, team]
            },
            f)

if __name__ == "__main__":
    main()

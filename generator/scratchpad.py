# Online Python compiler (interpreter) to run Python online.
# Write Python 3 code in this online editor and run it.
import random
from faker import Faker

fake = Faker()
random.seed(42)
Faker.seed(42)

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
region_ids = [r[0] for r in REGIONS]

def domain_from_company(name):
    import re
    slug = re.sub(r"[^a-z0-9]", "", name.lower().split(",")[0])[:20]
    return f"{slug}.com"

SEGMENT_QUOTAS = {"SMB": 14, "Mid-Market": 7, "Enterprise": 4}
companies = []
cid = 1
for segment, count in SEGMENT_QUOTAS.items():
    for _ in range(count):
        name = fake.company()
        companies.append({
            "company_id": f"CO{cid:05d}",
            "company_name": name,
            "domain": domain_from_company(name),
            "segment": segment,
            "region": random.choice(region_ids),
        })
        cid += 1
random.shuffle(companies)
for c in companies:
    print(c)
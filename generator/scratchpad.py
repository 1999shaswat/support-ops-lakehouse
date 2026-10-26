import csv
from datetime import date, timedelta


def write_dim_date(start="2023-01-01", end="2026-12-31"):
    path = f"./dim_date.csv"
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

write_dim_date()
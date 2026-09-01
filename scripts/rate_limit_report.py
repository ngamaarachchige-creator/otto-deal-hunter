"""Summarizes the rate_limit_events history (see backend/scrapers/rate_limit_state.py)
so patterns in Riyasewana/Ikman's blocking behavior become visible over time —
which hours of day get hit, how often, from which environment, and how the
cooldown lengths have escalated. Run anytime: `python scripts/rate_limit_report.py`.
"""
import os
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.database import get_db_connection


def main():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT host, hit_at, cooldown_seconds, source_env, status_code "
        "FROM rate_limit_events ORDER BY hit_at ASC"
    )
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()

    if not rows:
        print("No rate-limit events recorded yet.")
        return

    print(f"Total recorded hits: {len(rows)}")
    print(f"First hit: {rows[0]['hit_at']}")
    print(f"Last hit:  {rows[-1]['hit_at']}\n")

    by_host = defaultdict(list)
    for r in rows:
        by_host[r["host"]].append(r)

    for host, events in by_host.items():
        print(f"=== {host} ({len(events)} hits) ===")

        env_counts = Counter(e["source_env"] for e in events)
        print(f"  By environment: {dict(env_counts)}")

        status_counts = Counter(e["status_code"] for e in events)
        print(f"  By status code: {dict(status_counts)}")

        # Hour-of-day histogram (UTC, as stored)
        hour_counts = Counter()
        for e in events:
            hit_at = str(e["hit_at"])
            if "T" in hit_at:
                hour = hit_at.split("T")[1][:2]
            elif " " in hit_at:
                hour = hit_at.split(" ")[1][:2]
            else:
                continue
            hour_counts[hour] += 1
        if hour_counts:
            print("  By hour (UTC):")
            for hour in sorted(hour_counts):
                bar = "#" * hour_counts[hour]
                print(f"    {hour}:00  {bar} ({hour_counts[hour]})")

        cooldowns = [e["cooldown_seconds"] for e in events if e["cooldown_seconds"]]
        if cooldowns:
            avg_min = sum(cooldowns) / len(cooldowns) / 60
            max_min = max(cooldowns) / 60
            print(f"  Cooldown lengths: avg {avg_min:.0f}min, max {max_min:.0f}min")

        print(f"  Most recent 5 hits:")
        for e in events[-5:]:
            print(f"    {e['hit_at']} | {e['source_env']} | status={e['status_code']} | cooldown={e['cooldown_seconds']}s")
        print()


if __name__ == "__main__":
    main()

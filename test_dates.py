from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import dateparser
from calendar_utils import parse_date_range, find_free_slots

# Test the date parsing
date_phrase = "in three weeks"
print(f"\nTesting date phrase: {date_phrase}")
start_dt, end_dt = parse_date_range(date_phrase)
print(f"Start: {start_dt}")
print(f"End: {end_dt}")

# Test specific days
wednesday = start_dt
while wednesday.weekday() != 2:  # 2 is Wednesday
    wednesday += timedelta(days=1)
friday = wednesday + timedelta(days=2)

print(f"\nLooking for slots between:")
print(f"Wednesday: {wednesday}")
print(f"Friday: {friday}")

# Test slot finding with minimal test data
busy = []  # Empty busy list for testing
slots = find_free_slots(
    busy=busy,
    start=wednesday,
    end=friday,
    duration_min=30,
    earliest=9,  # 9 AM
    latest=17,   # 5 PM
)

print(f"\nFound slots:")
for start, end in slots:
    print(f"{start} -> {end}") 
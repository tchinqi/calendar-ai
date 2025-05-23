from backend.calendar_utils import parse_date_range, find_free_slots
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

def test_slot_finding():
    # Test the date parsing
    date_phrase = "in three weeks"
    print(f"\n1. Testing date parsing for: {date_phrase}")
    start_dt, end_dt = parse_date_range(date_phrase)
    print(f"Date range: {start_dt} -> {end_dt}")
    
    # Get Wednesday and Friday of that week
    wednesday = start_dt
    while wednesday.weekday() != 2:  # 2 is Wednesday
        wednesday += timedelta(days=1)
    friday = wednesday + timedelta(days=2)
    
    print(f"\n2. Looking for slots between:")
    print(f"Wednesday: {wednesday}")
    print(f"Friday: {friday}")
    
    # Test with empty calendar first
    print("\n3. Testing with empty calendar:")
    slots = find_free_slots(
        busy=[],
        start=wednesday,
        end=friday,
        duration_min=30,
        earliest=9,  # 9 AM
        latest=17    # 5 PM
    )
    
    print(f"\n4. Found {len(slots)} slots:")
    for start, end in slots:
        print(f"{start.astimezone(ZoneInfo('Europe/Stockholm')).strftime('%Y-%m-%d %H:%M')} -> {end.astimezone(ZoneInfo('Europe/Stockholm')).strftime('%H:%M')}")

if __name__ == "__main__":
    test_slot_finding() 
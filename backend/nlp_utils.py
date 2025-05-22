import re, calendar
from datetime import datetime, timedelta, time
from dateparser.search import search_dates
from zoneinfo import ZoneInfo
import dateparser

LOCAL_TZ = ZoneInfo("Europe/Stockholm")

# ── number words → int ─────────────────────────────
_NUM_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}

def _extract_count(prompt: str) -> int:
    m = re.search(r"\b(\d+)\s+slots?\b", prompt, re.I)
    if m:
        return max(1, int(m.group(1)))
    m = re.search(r"\b(" + "|".join(_NUM_WORDS) + r")\s+slots?\b", prompt, re.I)
    return _NUM_WORDS.get(m.group(1).lower(), 1) if m else 1

# ── hour helper ────────────────────────────────────
def _to_24h(hour: int, meridiem: str | None) -> int:
    if meridiem:
        meridiem = meridiem.lower()
        if meridiem.startswith("p") and hour != 12:
            hour += 12
        if meridiem.startswith("a") and hour == 12:
            hour = 0
    else:
        # If no AM/PM specified and hour is 1-7, assume PM
        if 1 <= hour <= 7:
            hour += 12
        # If hour is 8-12, assume AM
        elif 8 <= hour <= 12:
            if hour == 12:
                hour = 0
    return hour % 24

# ── next <weekday> parse ─────────────────────────────
_WEEKDAY_RE = re.compile(
    r"\bnext\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", re.I
)

def _next_weekday(prompt: str) -> datetime | None:
    m = _WEEKDAY_RE.search(prompt)
    if not m:
        return None
    target = m.group(1).capitalize()
    idx = list(calendar.day_name).index(target)
    today = datetime.now(LOCAL_TZ).date()
    diff = (idx - today.weekday() + 7) % 7 or 7
    return datetime.combine(today + timedelta(days=diff), time.min)

# ── dateparser settings ─────────────────────────────
_DATE_SETTINGS = {
    "PREFER_DATES_FROM": "future",
    "RELATIVE_BASE": datetime.now(LOCAL_TZ),
    "TIMEZONE": str(LOCAL_TZ),
    "RETURN_AS_TIMEZONE_AWARE": True,
    "PREFER_DAY_OF_MONTH": "first"
}

# ── main extractor ─────────────────────────────────

def extract_parameters(prompt: str) -> dict:
    now = datetime.now(LOCAL_TZ)
    today = now.date()
    
    print(f"\n🔍 NLP Debug: Parsing prompt: '{prompt}'")
    print(f"Current time (local): {now}")
    
    out = {
        "start":    now,
        "end":      now + timedelta(days=7),
        "duration": 20,  # Default to 20 minutes
        "earliest": 9,    # Default work day start
        "latest":   17,   # Default work day end
        "count":    1,
    }

    # Duration - look for this first to set default if not found
    m = re.search(r"(\d+)\s*[-\s]?(minutes?|mins?|hours?|h)\b", prompt, re.I)
    if m:
        val = int(m.group(1))
        out["duration"] = val * 60 if m.group(2).lower().startswith("h") else val
        print(f"Detected duration: {out['duration']} minutes")
    else:
        print(f"Using default duration: {out['duration']} minutes")

    # Check for month specification
    month_match = re.search(r"\b(in|during|for)\s+(january|february|march|april|may|june|july|august|september|october|november|december)\b", prompt, re.I)
    if month_match:
        month_name = month_match.group(2).lower()
        months = ['january', 'february', 'march', 'april', 'may', 'june', 
                 'july', 'august', 'september', 'october', 'november', 'december']
        month_num = months.index(month_name) + 1
        
        # Get the year that puts this month in the future
        target_year = now.year
        if month_num < now.month:
            target_year += 1
            
        # Set start to the first of the month
        start_date = datetime(target_year, month_num, 1, tzinfo=LOCAL_TZ)
        
        # Set end to the first of the next month
        if month_num == 12:
            end_date = datetime(target_year + 1, 1, 1, tzinfo=LOCAL_TZ)
        else:
            end_date = datetime(target_year, month_num + 1, 1, tzinfo=LOCAL_TZ)
            
        print(f"Detected month range: {start_date.date()} to {end_date.date()}")
        
        out["start"] = start_date.replace(hour=out["earliest"], minute=0, second=0, microsecond=0)
        out["end"] = end_date.replace(hour=out["latest"], minute=0, second=0, microsecond=0)
        return out

    # Handle specific date ranges with "between DATE and DATE"
    date_range_match = re.search(r"\bbetween\s+(.+?)\s+and\s+(.+?)(?:\s|$)", prompt, re.I)
    if date_range_match:
        date1, date2 = date_range_match.groups()
        
        # Try to parse both dates
        start_date = dateparser.parse(date1, settings=_DATE_SETTINGS)
        if not start_date:
            print(f"Could not parse start date: {date1}")
            return out
            
        # For the end date, we need to ensure it uses the same month context as the start date
        # if only day numbers are provided
        if re.match(r'^\d+$', date2.strip()):  # If end date is just a number
            # Use the same month and year as start_date
            try:
                day = int(date2.strip())
                end_date = start_date.replace(day=day)
                # If the day would make end_date before start_date, move to next month
                if end_date < start_date:
                    if end_date.month == 12:
                        end_date = end_date.replace(year=end_date.year + 1, month=1)
                    else:
                        end_date = end_date.replace(month=end_date.month + 1)
            except ValueError:
                print(f"Invalid day number for end date: {date2}")
                return out
        else:
            # Try to parse normally
            end_date = dateparser.parse(date2, settings=_DATE_SETTINGS)
            
        if not end_date:
            print(f"Could not parse end date: {date2}")
            return out
            
        print(f"Detected date range: {start_date.date()} to {end_date.date()}")
        
        # Validate the range
        if end_date < start_date:
            print(f"Warning: End date {end_date.date()} is before start date {start_date.date()}")
            # Try to fix by assuming same month as start date
            if end_date.month != start_date.month:
                end_date = end_date.replace(month=start_date.month)
                if end_date < start_date:  # If still before, try next month
                    if end_date.month == 12:
                        end_date = end_date.replace(year=end_date.year + 1, month=1)
                    else:
                        end_date = end_date.replace(month=end_date.month + 1)
                print(f"Adjusted to: {start_date.date()} to {end_date.date()}")
            
        # Set the start and end times
        out["start"] = start_date.replace(hour=out["earliest"], minute=0, second=0, microsecond=0)
        # Add one day to end_date to include the full day
        out["end"] = end_date.replace(hour=out["latest"], minute=0, second=0, microsecond=0) + timedelta(days=1)
        return out

    # Handle date ranges between weekdays
    between_match = re.search(r"\bbetween\s+(\w+)\s+and\s+(\w+)\b", prompt, re.I)
    if between_match:
        day1, day2 = between_match.groups()
        weekdays = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
        
        # Convert day names to indices
        try:
            idx1 = next(i for i, day in enumerate(weekdays) if day.startswith(day1.lower()))
            idx2 = next(i for i, day in enumerate(weekdays) if day.startswith(day2.lower()))
            
            # Find next occurrence of the first day
            start = now
            while start.weekday() != idx1:
                start += timedelta(days=1)
            
            # If we're looking for next week specifically
            if "next week" in prompt.lower():
                # If we're already in the target week, move to next week
                target_week = (now + timedelta(days=7)).isocalendar().week
                if start.isocalendar().week != target_week:
                    while start.isocalendar().week != target_week:
                        start += timedelta(days=1)
            
            # Set the end date to the second day
            end = start
            while end.weekday() != idx2:
                end += timedelta(days=1)
            
            # Set to work hours
            out["start"] = start.replace(hour=out["earliest"], minute=0, second=0, microsecond=0)
            out["end"] = end.replace(hour=out["latest"], minute=0, second=0, microsecond=0) + timedelta(days=1)
            print(f"Date range: {weekdays[idx1].capitalize()} to {weekdays[idx2].capitalize()}")
            print(f"Window: {out['start']} → {out['end']}")
            
        except StopIteration:
            print(f"Warning: Could not parse weekday names: {day1}, {day2}")
            
    # Handle "next week" without specific days
    elif re.search(r"\bnext\s+week\b", prompt, re.I):
        print("Detected: next week")
        # Find next Monday
        start = now
        while start.weekday() != 0:  # 0 is Monday
            start += timedelta(days=1)
        # Set to start of work day
        start = start.replace(hour=out["earliest"], minute=0, second=0, microsecond=0)
        out["start"] = start
        out["end"] = start + timedelta(days=7)
        print(f"Next week window: {start} → {out['end']}")
    
    # Handle single specific weekday
    else:
        for i, day in enumerate(['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']):
            if re.search(fr"\bnext\s+{day}\b", prompt, re.I):
                print(f"Detected: next {day}")
                # Find next occurrence of this weekday
                start = now
                while start.weekday() != i:
                    start += timedelta(days=1)
                # If it's the same weekday and we're looking for "next", add a week
                if start.date() == today and "next" in prompt.lower():
                    start += timedelta(days=7)
                # Set to start of work day
                out["start"] = start.replace(hour=out["earliest"], minute=0, second=0, microsecond=0)
                out["end"] = out["start"] + timedelta(days=1)
                print(f"{day.capitalize()} window: {out['start']} → {out['end']}")
                break

    # Handle lunch hours preference
    if "lunch" in prompt.lower():
        print("Detected lunch hours preference")
        # We'll handle this by adjusting the time windows later

    # After / before hour filters
    aft = re.search(r"\bafter\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b", prompt, re.I)
    bef = re.search(r"\bbefore\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b", prompt, re.I)
    
    if aft:
        hour = int(aft.group(1))
        minute = int(aft.group(2)) if aft.group(2) else 0
        out["earliest"] = _to_24h(hour, aft.group(3))
        if minute:  # If minutes were specified
            out["start"] = out["start"].replace(minute=minute)
        print(f"Detected earliest: {out['earliest']}:{minute:02d}")
        # If we're looking for slots today and it's already past the earliest time,
        # adjust earliest to current hour
        if out["start"].date() == today and now.hour > out["earliest"]:
            out["earliest"] = now.hour
            print(f"Adjusted earliest to current hour: {out['earliest']}:00")

    if bef:
        hour = int(bef.group(1))
        minute = int(bef.group(2)) if bef.group(2) else 0
        out["latest"] = _to_24h(hour, bef.group(3))
        if minute:  # If minutes were specified
            out["end"] = out["end"].replace(minute=minute)
        print(f"Detected latest: {out['latest']}:{minute:02d}")
        # Ensure latest is after earliest
        if out["latest"] <= out["earliest"]:
            out["latest"] = max(out["earliest"] + 1, out["latest"] + 12)
            print(f"Adjusted latest to ensure after earliest: {out['latest']}:00")

    # Slot count
    out["count"] = _extract_count(prompt)
    print(f"Requested slots: {out['count']}")
    
    # Ensure start time is at the beginning of work hours
    if out["start"].hour < out["earliest"]:
        out["start"] = out["start"].replace(hour=out["earliest"], minute=0, second=0, microsecond=0)
        print(f"Adjusted start to work hours: {out['start']}")
    
    print("\nFinal parameters:")
    print(f"Start: {out['start']}")
    print(f"End: {out['end']}")
    print(f"Work hours: {out['earliest']}:00 - {out['latest']}:00")
    print(f"Duration: {out['duration']} minutes")
    print(f"Slots needed: {out['count']}")
    
    return out

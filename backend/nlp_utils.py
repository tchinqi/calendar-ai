import re, calendar
from datetime import datetime, timedelta, time, timezone
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
    """Extract the number of slots requested from the prompt.
    
    Examples:
    - "3 slots" -> 3
    - "three slots" -> 3
    - "Find me 2 slots" -> 2
    - "3 one-hour slots" -> 3
    - "3 30-minute slots" -> 3
    - "two two-hour slots" -> 2
    - "2 1 hour slots" -> 2
    - "2 1-hour slots" -> 2
    """
    print(f"\n🔢 Extracting slot count from: '{prompt}'")
    
    # First try word numbers at start of string or with slots
    word_patterns = [
        r"^(" + "|".join(_NUM_WORDS) + r")\s+",  # Word number at start
        r"\b(" + "|".join(_NUM_WORDS) + r")\s+(?:(?:\d+[-\s]*hour|one-hour|two-hour|hour|minute|min|thirty|thirty-minute|30-minute|45-minute)\s+)?slots?\b"  # Word number with optional duration
    ]
    
    for pattern in word_patterns:
        m = re.search(pattern, prompt, re.I)
        if m:
            count = _NUM_WORDS.get(m.group(1).lower(), 1)
            print(f"Found word slot count: {count}")
            return count
    
    # Then try numeric digits with various patterns
    num_patterns = [
        r"\b(\d+)\s+(?:(?:\d+[-\s]*hour|one-hour|two-hour|hour|minute|min|thirty|thirty-minute|30-minute|45-minute)\s+)?slots?\b",  # "3 one-hour slots", "2 1-hour slots"
        r"^(\d+)\s+",  # Number at start of string
        r"\b(\d+)\s+slots?\b",  # Basic "X slots"
    ]
    
    for pattern in num_patterns:
        m = re.search(pattern, prompt, re.I)
        if m:
            count = max(1, int(m.group(1)))
            print(f"Found numeric slot count: {count}")
            return count
    
    print("No slot count found, defaulting to 1")
    return 1

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
        "end":      now + timedelta(days=30),  # Look ahead 30 days by default instead of 7
        "duration": _extract_duration(prompt),  # Use new duration extraction
        "earliest": 9,    # Default work day start
        "latest":   17,   # Default work day end
        "count":    _extract_count(prompt),  # Extract count immediately and store it
        "allowed_days": None,  # List of allowed weekday indices (0=Monday, 6=Sunday) or None for all days
    }

    # Check for "Nth week of month" patterns with optional year
    week_of_month = re.search(r"\b(first|second|third|fourth|last|1st|2nd|3rd|4th)\s+week\s+(?:of\s+)?(january|february|march|april|may|june|july|august|september|october|november|december)(?:\s+(\d{4}))?\b", prompt, re.I)
    if week_of_month:
        week_spec = week_of_month.group(1).lower()
        month_name = week_of_month.group(2).lower()
        specified_year = int(week_of_month.group(3)) if week_of_month.group(3) else None
        
        # Convert ordinal words to numbers
        week_map = {
            'first': 1, '1st': 1,
            'second': 2, '2nd': 2,
            'third': 3, '3rd': 3,
            'fourth': 4, '4th': 4,
            'last': -1
        }
        week_num = week_map[week_spec]
        
        # Get month number
        months = ['january', 'february', 'march', 'april', 'may', 'june', 
                 'july', 'august', 'september', 'october', 'november', 'december']
        month_num = months.index(month_name) + 1
        
        # Get the year - use specified year if provided, otherwise use 2025
        if specified_year:
            target_year = specified_year  # Use exactly what was specified
            print(f"Using specified year {target_year} for {week_spec} week of {month_name}")
        else:
            target_year = 2025  # Default to 2025 for all future dates
            print(f"No year specified, using 2025 for {week_spec} week of {month_name}")
        
        print(f"\n📅 Selected year {target_year} for {week_spec} week of {month_name}")
        
        # Get the first day of the month with the final year
        first_day = datetime(target_year, month_num, 1, tzinfo=LOCAL_TZ)
        
        # Find the first Monday of the month
        while first_day.weekday() != 0:  # 0 is Monday
            first_day += timedelta(days=1)
            
        # Calculate the target week's Monday
        if week_num > 0:
            target_monday = first_day + timedelta(weeks=(week_num - 1))
        else:  # Last week
            # Get the last day of the month
            if month_num == 12:
                last_day = datetime(target_year + 1, 1, 1, tzinfo=LOCAL_TZ) - timedelta(days=1)
            else:
                last_day = datetime(target_year, month_num + 1, 1, tzinfo=LOCAL_TZ) - timedelta(days=1)
            # Go back to the last Monday
            while last_day.weekday() != 0:
                last_day -= timedelta(days=1)
            target_monday = last_day
            
        # Set the time window for the week
        out["start"] = target_monday.replace(hour=out["earliest"], minute=0, second=0, microsecond=0)
        out["end"] = (target_monday + timedelta(days=5)).replace(hour=out["latest"], minute=0, second=0, microsecond=0)
        out["allowed_days"] = list(range(5))  # Monday-Friday only
        
        print(f"Final date range:")
        print(f"- Start: {out['start'].strftime('%Y-%m-%d %H:%M %Z')} ({out['start'].strftime('%A')})")
        print(f"- End: {out['end'].strftime('%Y-%m-%d %H:%M %Z')} ({out['end'].strftime('%A')})")
        print("Set to weekdays only (Monday-Friday)")
        return out

    # If no specific date is mentioned in the prompt, look for slots starting from tomorrow
    if not any(word in prompt.lower() for word in ['today', 'tomorrow', 'next week', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday', 'january', 'february', 'march', 'april', 'may', 'june', 'july', 'august', 'september', 'october', 'november', 'december']):
        tomorrow = now.date() + timedelta(days=1)
        out["start"] = datetime.combine(tomorrow, time(hour=out["earliest"]), tzinfo=LOCAL_TZ)
        out["end"] = out["start"] + timedelta(days=30)
        print(f"No specific date mentioned, looking from tomorrow: {out['start'].date()}")

    # Check for "mid month" or similar phrases
    middle_month_match = re.search(r"\b(?:middle|mid)(?:\s+of)?\s+(january|february|march|april|may|june|july|august|september|october|november|december)\b", prompt, re.I)
    if middle_month_match:
        month_name = middle_month_match.group(1).lower()
        months = ['january', 'february', 'march', 'april', 'may', 'june', 
                 'july', 'august', 'september', 'october', 'november', 'december']
        month_num = months.index(month_name) + 1
        
        # Get the year that puts this month in the future
        target_year = now.year
        if month_num < now.month or (month_num == now.month and now.day > 20):
            target_year += 1
            
        # For middle of month, use 10th to 20th
        start_date = datetime(target_year, month_num, 10, tzinfo=LOCAL_TZ)
        end_date = datetime(target_year, month_num, 20, tzinfo=LOCAL_TZ)
        
        print(f"\n📅 Detected middle of {month_name.capitalize()}:")
        print(f"- Start: {start_date.strftime('%Y-%m-%d')}")
        print(f"- End: {end_date.strftime('%Y-%m-%d')}")
        
        # Set the time window
        out["start"] = start_date.replace(hour=out["earliest"], minute=0, second=0, microsecond=0)
        # Include the full end day
        out["end"] = end_date.replace(hour=out["latest"], minute=0, second=0, microsecond=0) + timedelta(days=1)
        return out

    # Handle time range with "between HH:MM and HH:MM" format or "X-Y(am|pm)" format
    time_range_match = re.search(r"\bbetween\s+(\d{1,2})(?::(\d{2}))?\s*(?:and|to|-)\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b|\b(\d{1,2})\s*-\s*(\d{1,2})\s*(am|pm)\b", prompt, re.I)
    if time_range_match:
        if time_range_match.group(1):  # First format: "between X and Y"
            start_hour = int(time_range_match.group(1))
            start_min = int(time_range_match.group(2)) if time_range_match.group(2) else 0
            end_hour = int(time_range_match.group(3))
            end_min = int(time_range_match.group(4)) if time_range_match.group(4) else 0
            meridiem = time_range_match.group(5)
        else:  # Second format: "X-Ypm"
            start_hour = int(time_range_match.group(6))
            start_min = 0
            end_hour = int(time_range_match.group(7))
            end_min = 0
            meridiem = time_range_match.group(8)
        
        # Convert to 24-hour format
        out["earliest"] = _to_24h(start_hour, meridiem)
        out["latest"] = _to_24h(end_hour, meridiem)
        
        # Update start and end times
        out["start"] = out["start"].replace(hour=out["earliest"], minute=start_min)
        out["end"] = out["end"].replace(hour=out["latest"], minute=end_min)
        
        print(f"Detected time range: {out['earliest']}:{start_min:02d} - {out['latest']}:{end_min:02d}")

    # Check for day-of-week constraints
    days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    day_pattern = r"\b(" + "|".join(days) + r")\b"
    found_days = re.findall(day_pattern, prompt.lower())
    
    # If we found specific days, use only those
    if found_days:
        out["allowed_days"] = [days.index(day) for day in found_days]
        print(f"Detected allowed days: {[days[i] for i in out['allowed_days']]}")

    # Handle "weekday" or "weekdays" to mean Monday-Friday
    if re.search(r"\b(?:week|work)days?\b", prompt, re.I):
        out["allowed_days"] = list(range(5))  # Monday-Friday
        print("Detected weekdays (Monday-Friday)")
    
    # Handle "weekend" to mean Saturday-Sunday
    if re.search(r"\bweekends?\b", prompt, re.I):
        out["allowed_days"] = [5, 6]  # Saturday-Sunday
        print("Detected weekend days (Saturday-Sunday)")

    # Check for month specification with optional year
    month_match = re.search(r"\b(?:in|during|for)?\s*(january|february|march|april|may|june|july|august|september|october|november|december)(?:\s+(\d{4}))?\b", prompt, re.I)
    if month_match:
        month_name = month_match.group(1).lower()
        specified_year = int(month_match.group(2)) if month_match.group(2) else None
        months = ['january', 'february', 'march', 'april', 'may', 'june', 
                 'july', 'august', 'september', 'october', 'november', 'december']
        month_num = months.index(month_name) + 1
        
        # Get the year - use specified year if provided, otherwise find next occurrence
        target_year = now.year
        if specified_year:
            target_year = specified_year  # Use exactly what was specified
        else:
            # Calculate the target date
            target_date = datetime(target_year, month_num, 1, tzinfo=LOCAL_TZ)
            
            # If the target date has passed, increment year
            if target_date < now:
                print(f"Target month ({target_date.strftime('%Y-%m')}) has passed, looking in {target_year + 1}")
                target_year += 1
            else:
                print(f"Using current year {target_year} for {month_name}")
            
        # Set start to first of month
        start_date = datetime(target_year, month_num, 1, tzinfo=LOCAL_TZ)
        
        # Set end to first of next month
        if month_num == 12:
            end_date = datetime(target_year + 1, 1, 1, tzinfo=LOCAL_TZ)
        else:
            end_date = datetime(target_year, month_num + 1, 1, tzinfo=LOCAL_TZ)
            
        print(f"\n📅 Detected month range for {month_name} {target_year}:")
        print(f"- Start: {start_date.strftime('%Y-%m-%d')} ({start_date.strftime('%A')})")
        print(f"- End: {end_date.strftime('%Y-%m-%d')} ({end_date.strftime('%A')})")
        
        # Set the time window and ensure we only look at weekdays
        out["start"] = start_date.replace(hour=out["earliest"], minute=0, second=0, microsecond=0)
        out["end"] = end_date.replace(hour=out["latest"], minute=0, second=0, microsecond=0)
        out["allowed_days"] = list(range(5))  # Monday-Friday only
        print("Set to weekdays only (Monday-Friday)")
        return out

    # Handle "tomorrow" specifically
    if "tomorrow" in prompt.lower():
        tomorrow = now + timedelta(days=1)
        out["start"] = tomorrow.replace(hour=out["earliest"], minute=0, second=0, microsecond=0)
        out["end"] = tomorrow.replace(hour=out["latest"], minute=0, second=0, microsecond=0)
        print(f"Detected tomorrow: {out['start'].date()}")

    # Handle "X weeks from now" or "in X weeks"
    weeks_pattern = r"\b(?:in|after)\s+(\d+|" + "|".join(_NUM_WORDS) + r")\s+weeks?\b|\b(\d+|" + "|".join(_NUM_WORDS) + r")\s+weeks?\s+(?:from\s+now|ahead|away|from\s+today)\b"
    weeks_match = re.search(weeks_pattern, prompt, re.I)
    
    target_week_offset = 0
    if weeks_match:
        num_str = (weeks_match.group(1) or weeks_match.group(2)).lower()
        try:
            num_weeks = _NUM_WORDS.get(num_str)
            if num_weeks is None:
                num_weeks = int(num_str)
        except ValueError:
            print(f"Warning: Could not parse week number: {num_str}")
            num_weeks = 1
            
        target_week_offset = num_weeks
        print(f"Detected: {num_weeks} weeks from now")
    elif "next week" in prompt.lower():
        target_week_offset = 1
        print("Detected: next week")
    
    # Handle date ranges between weekdays with week offset
    between_match = re.search(r"\bbetween\s+(\w+)\s+and\s+(\w+)\b", prompt, re.I)
    if between_match:
        day1, day2 = between_match.groups()
        weekdays = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
        
        # Convert day names to indices
        try:
            idx1 = next(i for i, day in enumerate(weekdays) if day.startswith(day1.lower()))
            idx2 = next(i for i, day in enumerate(weekdays) if day.startswith(day2.lower()))
            
            # Start from today + week offset
            start = now + timedelta(weeks=target_week_offset)
            # Find the first occurrence of day1 in the target week
            while start.weekday() != idx1:
                if start.weekday() > idx1:
                    # If we've passed the target day, move to next week
                    start += timedelta(days=(7 - start.weekday()) + idx1)
                else:
                    start += timedelta(days=1)
            
            # Find the occurrence of day2 in the same week
            end = start
            while end.weekday() != idx2:
                if end.weekday() > idx2:
                    # If we've passed the target day, move to next week
                    end += timedelta(days=(7 - end.weekday()) + idx2)
                else:
                    end += timedelta(days=1)
            
            # Set work hours
            out["start"] = start.replace(hour=out["earliest"], minute=0, second=0, microsecond=0)
            out["end"] = end.replace(hour=out["latest"], minute=0, second=0, microsecond=0) + timedelta(days=1)
            
            # Set allowed days
            if idx1 <= idx2:
                out["allowed_days"] = list(range(idx1, idx2 + 1))
            else:
                out["allowed_days"] = list(range(idx1, 7)) + list(range(0, idx2 + 1))
            
            print(f"Date range: {weekdays[idx1].capitalize()} to {weekdays[idx2].capitalize()}")
            print(f"Window: {out['start']} → {out['end']}")
            print(f"Allowed days: {[weekdays[i] for i in out['allowed_days']]}")
            
            # Handle lunch time constraints
            if "after lunch" in prompt.lower():
                print("Detected: after lunch specification")
                lunch_end_hour = 13
                lunch_end_minute = 15
                out["earliest"] = lunch_end_hour
                out["start"] = out["start"].replace(hour=lunch_end_hour, minute=lunch_end_minute)
                print(f"Adjusted start time to after lunch: {out['start']}")
            
            return out
            
        except StopIteration:
            print(f"Warning: Could not parse weekday names: {day1}, {day2}")

    # Handle "after DATE" format
    after_date = re.search(r"\bafter\s+(?:the\s+)?(\d+)(?:st|nd|rd|th)?\s+(?:of\s+)?(january|february|march|april|may|june|july|august|september|october|november|december)\b", prompt, re.I)
    if after_date:
        day = int(after_date.group(1))
        month_name = after_date.group(2).lower()
        months = ['january', 'february', 'march', 'april', 'may', 'june', 
                 'july', 'august', 'september', 'october', 'november', 'december']
        month_num = months.index(month_name) + 1
        
        # Get the year that puts this date in the future
        target_year = now.year
        target_date = datetime(target_year, month_num, day, tzinfo=LOCAL_TZ)
        if target_date < now:
            target_year += 1
            target_date = datetime(target_year, month_num, day, tzinfo=LOCAL_TZ)
            
        print(f"\n🔍 Debug: Date parsing:")
        print(f"Input date: {month_name.capitalize()} {day}")
        print(f"Target date: {target_date.date()}")
        
        # Set start to the day after the specified date
        out["start"] = (target_date + timedelta(days=1)).replace(hour=out["earliest"], minute=0, second=0, microsecond=0)
        
        # For multiple slots, extend the search range based on count
        slot_count = _extract_count(prompt)
        # Search a much longer period - 3 months by default, or more if we need more slots
        days_to_search = max(90, slot_count * 10)  # Much longer search window - 3 months minimum
        out["end"] = (out["start"] + timedelta(days=days_to_search)).replace(hour=out["latest"], minute=0, second=0, microsecond=0)
        
        print(f"\n📅 Search Parameters:")
        print(f"- Start date: {out['start'].strftime('%Y-%m-%d %H:%M')} ({out['start'].strftime('%A')})")
        print(f"- End date: {out['end'].strftime('%Y-%m-%d %H:%M')} ({out['end'].strftime('%A')})")
        print(f"- Search duration: {days_to_search} days ({days_to_search/7:.1f} weeks)")
        print(f"- Slots needed: {slot_count}")
        print(f"- Work hours: {out['earliest']:02d}:00 - {out['latest']}:00")
        print(f"- Time zone: {LOCAL_TZ}")
        print(f"- Duration per slot: {out['duration']} minutes")
        
        return out

    # Handle specific dates like "June 13th" or "13th of June"
    specific_date = re.search(r"\b(january|february|march|april|may|june|july|august|september|october|november|december)\s+(\d+)(?:st|nd|rd|th)?\b|\b(\d+)(?:st|nd|rd|th)?\s+(?:of\s+)?(january|february|march|april|may|june|july|august|september|october|november|december)\b", prompt, re.I)
    
    if specific_date:
        # Extract month and day from either format
        if specific_date.group(1):  # "June 13th" format
            month_name = specific_date.group(1).lower()
            day = int(specific_date.group(2))
        else:  # "13th of June" format
            month_name = specific_date.group(4).lower()
            day = int(specific_date.group(3))
            
        months = ['january', 'february', 'march', 'april', 'may', 'june', 
                 'july', 'august', 'september', 'october', 'november', 'december']
        month_num = months.index(month_name) + 1
        
        # Get the year that puts this date in the future
        target_year = now.year
        target_date = datetime(target_year, month_num, day, tzinfo=LOCAL_TZ)
        if target_date < now:
            target_year += 1
            target_date = datetime(target_year, month_num, day, tzinfo=LOCAL_TZ)
            
        print(f"Detected specific date: {target_date.date()}")
        
        # Set the time window for this specific day
        out["start"] = target_date.replace(hour=out["earliest"], minute=0, second=0, microsecond=0)
        out["end"] = target_date.replace(hour=out["latest"], minute=0, second=0, microsecond=0)
        
        # Handle lunch time constraints
        if "after lunch" in prompt.lower():
            print("Detected: after lunch specification")
            # Set start time to 13:15 (typical end of lunch)
            lunch_end_hour = 13
            lunch_end_minute = 15
            out["earliest"] = lunch_end_hour  # Update earliest to ensure no slots before lunch
            out["start"] = out["start"].replace(hour=lunch_end_hour, minute=lunch_end_minute)
            print(f"Adjusted start time to after lunch: {out['start']}")
        elif "before lunch" in prompt.lower():
            print("Detected: before lunch specification")
            # Set end time to 11:30 (typical start of lunch)
            lunch_start_hour = 11
            lunch_start_minute = 30
            out["latest"] = lunch_start_hour  # Update latest to ensure no slots during/after lunch start
            out["end"] = out["end"].replace(hour=lunch_start_hour, minute=lunch_start_minute)
            print(f"Adjusted end time to before lunch: {out['end']}")
        
        return out

    # Handle specific date ranges with "between DATE and DATE" or "DATE - DATE" or "DATE to DATE"
    date_range_match = re.search(r"\bbetween\s+(.+?)\s+and\s+(.+?)(?:\s|$)", prompt, re.I)
    if not date_range_match:
        # Try other date range formats
        date_range_match = re.search(r"(\d+(?:st|nd|rd|th)?\s+(?:of\s+)?[a-zA-Z]+|\b[a-zA-Z]+\s+\d+(?:st|nd|rd|th)?)\s*[-–—]\s*(\d+(?:st|nd|rd|th)?\s+(?:of\s+)?[a-zA-Z]+|\b[a-zA-Z]+\s+\d+(?:st|nd|rd|th)?)", prompt, re.I)
        if not date_range_match:
            date_range_match = re.search(r"(\d+(?:st|nd|rd|th)?\s+(?:of\s+)?[a-zA-Z]+|\b[a-zA-Z]+\s+\d+(?:st|nd|rd|th)?)\s+to\s+(\d+(?:st|nd|rd|th)?\s+(?:of\s+)?[a-zA-Z]+|\b[a-zA-Z]+\s+\d+(?:st|nd|rd|th)?)", prompt, re.I)
    
    if date_range_match:
        date1, date2 = date_range_match.groups()
        print(f"Detected date range: '{date1}' to '{date2}'")
        
        # Try to parse both dates
        start_date = dateparser.parse(date1, settings=_DATE_SETTINGS)
        if not start_date:
            print(f"Could not parse start date: {date1}")
            return out
            
        # For the end date, we need to ensure it uses the same year context as the start date
        end_date = dateparser.parse(date2, settings={
            **_DATE_SETTINGS,
            "RELATIVE_BASE": start_date  # Use start_date as reference for end_date
        })
            
        if not end_date:
            print(f"Could not parse end date: {date2}")
            return out
            
        print(f"Initial parsed date range: {start_date.date()} to {end_date.date()}")
        
        # Ensure dates are in the future
        if start_date < now:
            # Move both dates to next year
            start_date = start_date.replace(year=now.year + 1)
            end_date = end_date.replace(year=now.year + 1)
            print(f"Moved dates to next year: {start_date.date()} to {end_date.date()}")
        
        # Validate the range
        if end_date < start_date:
            print(f"Warning: End date {end_date.date()} is before start date {start_date.date()}")
            # If in different years, try adjusting end_date to same year as start_date
            end_date = end_date.replace(year=start_date.year)
            if end_date < start_date:  # If still before, try next month
                if end_date.month < start_date.month:
                    # Try next year
                    end_date = end_date.replace(year=end_date.year + 1)
            print(f"Adjusted to: {start_date.date()} to {end_date.date()}")
            
        # Set the start and end times
        out["start"] = start_date.replace(hour=out["earliest"], minute=0, second=0, microsecond=0)
        # Include the full end day
        out["end"] = end_date.replace(hour=out["latest"], minute=0, second=0, microsecond=0)
        print(f"Final date range: {out['start']} to {out['end']}")
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
        # Calculate the start of next week (next Monday)
        today = now.date()
        days_until_monday = (7 - today.weekday()) % 7
        if days_until_monday == 0:  # If today is Monday, we want next Monday
            days_until_monday = 7
            
        next_monday = today + timedelta(days=days_until_monday)
        start = datetime.combine(next_monday, time(hour=out["earliest"]), tzinfo=LOCAL_TZ)
        
        # Set the window to the full work week
        out["start"] = start
        out["end"] = start + timedelta(days=5)  # Look through Friday
        out["allowed_days"] = list(range(5))  # Monday-Friday only
        
        print(f"Next week window: {out['start'].date()} → {out['end'].date()}")
        print("Set to weekdays only (Monday-Friday)")
        return out

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

    # After all date/time processing, handle lunch time constraints
    if "after lunch" in prompt.lower():
        print("Detected: after lunch specification")
        # Set start time to 13:15 (typical end of lunch)
        lunch_end_hour = 13
        lunch_end_minute = 15
        out["earliest"] = lunch_end_hour  # Update earliest to ensure no slots before lunch
        out["start"] = out["start"].replace(hour=lunch_end_hour, minute=lunch_end_minute)
        print(f"Adjusted start time to after lunch: {out['start']}")
    elif "before lunch" in prompt.lower():
        print("Detected: before lunch specification")
        # Set end time to 11:30 (typical start of lunch)
        lunch_start_hour = 11
        lunch_start_minute = 30
        out["latest"] = lunch_start_hour  # Update latest to ensure no slots during/after lunch start
        out["end"] = out["end"].replace(hour=lunch_start_hour, minute=lunch_start_minute)
        print(f"Adjusted end time to before lunch: {out['end']}")

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
    
    print("\nFinal parameters:")
    print(f"Start: {out['start']}")
    print(f"End: {out['end']}")
    print(f"Work hours: {out['earliest']}:00 - {out['latest']}:00")
    print(f"Duration: {out['duration']} minutes")
    print(f"Slots needed: {out['count']}")
    
    return out

def parse_schedule_request(prompt: str) -> dict | None:
    """Parse a request to view schedule/events.
    Returns None if the prompt is not a schedule viewing request.
    Otherwise returns a dict with start and end dates for fetching events.
    """
    now = datetime.now(LOCAL_TZ)
    today = now.date()
    
    # Initialize output
    out = {
        "start": None,
        "end": None,
        "description": ""  # Human readable description of the time range
    }
    
    # Check if this is a schedule viewing request
    if not re.search(r"\b(?:show|view|see|get|what(?:'s| is))?\s+(?:the\s+)?(?:schedule|calendar|events?)\b", prompt, re.I):
        return None
        
    # Handle "today"
    if "today" in prompt.lower():
        out["start"] = now.replace(hour=0, minute=0, second=0, microsecond=0)
        out["end"] = now.replace(hour=23, minute=59, second=59)
        out["description"] = "today's schedule"
        return out
        
    # Handle "tomorrow"
    if "tomorrow" in prompt.lower():
        tomorrow = now + timedelta(days=1)
        out["start"] = tomorrow.replace(hour=0, minute=0, second=0, microsecond=0)
        out["end"] = tomorrow.replace(hour=23, minute=59, second=59)
        out["description"] = "tomorrow's schedule"
        return out
        
    # Handle specific months
    month_match = re.search(r"\b(january|february|march|april|may|june|july|august|september|october|november|december)\b", prompt, re.I)
    if month_match:
        month_name = month_match.group(1).lower()
        months = ['january', 'february', 'march', 'april', 'may', 'june', 
                 'july', 'august', 'september', 'october', 'november', 'december']
        month_num = months.index(month_name) + 1
        
        # Get the year that puts this month in the future
        target_year = now.year
        if month_num < now.month:
            target_year += 1
            
        # Set start to first of month
        start_date = datetime(target_year, month_num, 1, tzinfo=LOCAL_TZ)
        
        # Set end to first of next month
        if month_num == 12:
            end_date = datetime(target_year + 1, 1, 1, tzinfo=LOCAL_TZ)
        else:
            end_date = datetime(target_year, month_num + 1, 1, tzinfo=LOCAL_TZ)
            
        out["start"] = start_date
        out["end"] = end_date
        out["description"] = f"schedule for {month_name}"
        return out
        
    # Handle "next week"
    if re.search(r"\bnext\s+week\b", prompt, re.I):
        # Find next Monday
        start = now
        while start.weekday() != 0:  # 0 is Monday
            start += timedelta(days=1)
        out["start"] = start.replace(hour=0, minute=0, second=0, microsecond=0)
        out["end"] = (start + timedelta(days=7)).replace(hour=23, minute=59, second=59)
        out["description"] = "schedule for next week"
        return out
        
    # Handle "this week"
    if re.search(r"\bthis\s+week\b", prompt, re.I):
        # Find previous Monday
        start = now
        while start.weekday() != 0:  # 0 is Monday
            start -= timedelta(days=1)
        out["start"] = start.replace(hour=0, minute=0, second=0, microsecond=0)
        out["end"] = (start + timedelta(days=7)).replace(hour=23, minute=59, second=59)
        out["description"] = "schedule for this week"
        return out
        
    # Handle specific dates like "June 13th" or "13th of June"
    specific_date = re.search(r"\b(january|february|march|april|may|june|july|august|september|october|november|december)\s+(\d+)(?:st|nd|rd|th)?\b|\b(\d+)(?:st|nd|rd|th)?\s+(?:of\s+)?(january|february|march|april|may|june|july|august|september|october|november|december)\b", prompt, re.I)
    
    if specific_date:
        # Extract month and day from either format
        if specific_date.group(1):  # "June 13th" format
            month_name = specific_date.group(1).lower()
            day = int(specific_date.group(2))
        else:  # "13th of June" format
            month_name = specific_date.group(4).lower()
            day = int(specific_date.group(3))
            
        months = ['january', 'february', 'march', 'april', 'may', 'june', 
                 'july', 'august', 'september', 'october', 'november', 'december']
        month_num = months.index(month_name) + 1
        
        # Get the year that puts this date in the future
        target_year = now.year
        target_date = datetime(target_year, month_num, day, tzinfo=LOCAL_TZ)
        if target_date < now:
            target_year += 1
            target_date = datetime(target_year, month_num, day, tzinfo=LOCAL_TZ)
            
        out["start"] = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
        out["end"] = target_date.replace(hour=23, minute=59, second=59)
        out["description"] = f"schedule for {month_name} {day}"
        return out
    
    # Default to today if no specific time range found
    out["start"] = now.replace(hour=0, minute=0, second=0, microsecond=0)
    out["end"] = now.replace(hour=23, minute=59, second=59)
    out["description"] = "today's schedule"
    return out

def _extract_duration(prompt: str) -> int:
    """Extract duration in minutes from the prompt.
    
    Examples:
    - "1 hour" -> 60
    - "one hour" -> 60
    - "1-hour" -> 60
    - "two hour" -> 120
    - "2 hours" -> 120
    - "30 minutes" -> 30
    - "30 mins" -> 30
    - "1 hour slot" -> 60
    - "2 1-hour slots" -> 60
    """
    # First check for "an hour" or similar
    if re.search(r"\ban?\s+hour\b", prompt, re.I):
        return 60
        
    # Check for "X-hour" or "X hour" format with both digits and words
    patterns = [
        # Digit formats for hours
        r"(\d+)\s*[-\s]*hours?\s*(?:slot|meeting|chunk)?\b",  # "2 hours", "2-hour", "2 hour slot"
        r"\b(\d+)\s+\d+[-\s]*hours?\s*(?:slot|meeting|chunk)?\b",  # "2 1-hour slots"
        # Word formats for hours
        r"\b(" + "|".join(_NUM_WORDS) + r")\s*[-\s]*hours?\s*(?:slot|meeting|chunk)?\b",  # "two hours", "two-hour slot"
        # Minute formats
        r"(\d+)\s*[-\s]*(?:minutes?|mins?)\s*(?:slot|meeting|chunk)?\b",  # "30 minutes", "30 mins", "30 min slot"
    ]
    
    for pattern in patterns:
        m = re.search(pattern, prompt, re.I)
        if m:
            val = m.group(1).lower()
            # Try word number first
            num = _NUM_WORDS.get(val)
            if num is None:
                # Then try numeric
                try:
                    num = int(val)
                except ValueError:
                    continue
            
            # Convert to minutes
            if "hour" in pattern:
                return num * 60
            else:
                return num
    
    # Look for hour mentions without explicit numbers
    if re.search(r"\bhour\s*(?:slot|meeting|chunk)?\b", prompt, re.I):
        return 60
                
    # Default to 30 minutes
    return 30

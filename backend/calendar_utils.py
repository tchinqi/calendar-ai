from datetime import datetime, timedelta, time, timezone
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from config import WORKDAY_START, WORKDAY_END
from zoneinfo import ZoneInfo
import dateparser
from typing import Tuple, Optional

LOCAL_TZ = ZoneInfo("Europe/Stockholm")

def parse_date_range(date_phrase: str) -> Tuple[datetime, datetime]:
    """
    Parse natural language date expressions and return start and end datetimes.
    Examples: 'next week', 'tomorrow', 'next monday', 'in three weeks', 'last week of july', 'end of july'
    
    Returns:
        Tuple of (start_datetime, end_datetime) in the local timezone
    """
    print(f"\nDebug: Parsing date phrase: {date_phrase}")
    
    date_phrase_lower = date_phrase.lower()
    
    # Special handling for "last week of", "end of", or just "end" month phrases
    if any(phrase in date_phrase_lower for phrase in ["last week of", "end of", " end "]):
        # Extract month name if present
        words = date_phrase_lower.split()
        month_name = None
        for word in words:
            parsed_date = dateparser.parse(word)
            if parsed_date and parsed_date.month != datetime.now(LOCAL_TZ).month:
                month_name = word
                break
        
        if month_name:
            # Parse the first day of the mentioned month
            base_date = dateparser.parse(
                f"1 {month_name}",
                settings={
                    'TIMEZONE': str(LOCAL_TZ),
                    'RETURN_AS_TIMEZONE_AWARE': True,
                    'RELATIVE_BASE': datetime.now(LOCAL_TZ)
                }
            )
            
            if base_date:
                # Move to the next month and subtract one week
                if base_date.month == 12:
                    next_month = base_date.replace(year=base_date.year + 1, month=1)
                else:
                    next_month = base_date.replace(month=base_date.month + 1)
                
                last_week_start = next_month - timedelta(days=7)
                
                # Adjust to start of week (Monday)
                while last_week_start.weekday() != 0:
                    last_week_start -= timedelta(days=1)
                
                start_date = last_week_start.replace(hour=0, minute=0, second=0, microsecond=0)
                end_date = (start_date + timedelta(days=7)).replace(hour=23, minute=59, second=59, microsecond=999999)
                
                print(f"Debug: Returning last week of month range: {start_date} -> {end_date}")
                return (start_date, end_date)
    
    # Parse the base date from the phrase
    base_date = dateparser.parse(
        date_phrase,
        settings={
            'TIMEZONE': str(LOCAL_TZ),
            'RETURN_AS_TIMEZONE_AWARE': True,
            'RELATIVE_BASE': datetime.now(LOCAL_TZ)
        }
    )
    
    print(f"Debug: Initial base date parsed as: {base_date}")
    
    if not base_date:
        raise ValueError(f"Could not parse date from phrase: {date_phrase}")
    
    # For "week" related phrases
    if 'week' in date_phrase_lower:
        print("Debug: Detected week-related phrase")
        
        # For "in X weeks" or "X weeks from now", add weeks but don't adjust to start of week
        if 'from now' in date_phrase_lower or 'in' in date_phrase_lower:
            words = date_phrase_lower.split()
            try:
                # Look for number words and convert them
                number_words = {'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5}
                for i, word in enumerate(words):
                    if word in number_words and i + 1 < len(words) and 'week' in words[i + 1]:
                        num_weeks = number_words[word]
                        print(f"Debug: Found word number {word} = {num_weeks} weeks")
                        base_date = datetime.now(LOCAL_TZ) + timedelta(weeks=num_weeks)
                        break
                    elif word.isdigit() and i + 1 < len(words) and 'week' in words[i + 1]:
                        num_weeks = int(word)
                        print(f"Debug: Found numeric {num_weeks} weeks")
                        base_date = datetime.now(LOCAL_TZ) + timedelta(weeks=num_weeks)
                        break
            except (ValueError, IndexError) as e:
                print(f"Debug: Error parsing weeks: {e}")
                pass
            
            print(f"Debug: Final base date after week adjustment: {base_date}")
            
            # For "X weeks from now", return just that day
            start_date = base_date.replace(hour=0, minute=0, second=0, microsecond=0)
            end_date = base_date.replace(hour=23, minute=59, second=59, microsecond=999999)
            print(f"Debug: Returning single day range: {start_date} -> {end_date}")
            return (start_date, end_date)
            
        # For other week-related phrases (next week, etc.), adjust to start of week
        while base_date.weekday() != 0:  # 0 is Monday
            base_date -= timedelta(days=1)
        
        start_date = base_date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = (base_date + timedelta(days=7)).replace(hour=23, minute=59, second=59, microsecond=999999)
        print(f"Debug: Returning week range: {start_date} -> {end_date}")
        return (start_date, end_date)
    
    # For single day phrases, return that full day
    start_date = base_date.replace(hour=0, minute=0, second=0, microsecond=0)
    end_date = base_date.replace(hour=23, minute=59, second=59, microsecond=999999)
    print(f"Debug: Returning single day range: {start_date} -> {end_date}")
    return (start_date, end_date)

# ──────────────────────────────────────────────
# Time‑zone helpers
# ──────────────────────────────────────────────

def _to_local(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=LOCAL_TZ)
    return dt.astimezone(LOCAL_TZ)


def _to_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _rfc3339(dt: datetime) -> str:
    """Return an RFC‑3339 string in UTC for Google Calendar API."""
    return _to_utc(dt).isoformat()

# ──────────────────────────────────────────────
# Google API service
# ──────────────────────────────────────────────

def get_service(creds):
    return build("calendar", "v3", credentials=creds, cache_discovery=False)

# ──────────────────────────────────────────────
# Fetch events → list[(utc_start, utc_end)]
# ──────────────────────────────────────────────

def list_events(service, calendar_id: str, start_dt: datetime, end_dt: datetime):
    events = (
        service.events()
        .list(
            calendarId=calendar_id,
            timeMin=_rfc3339(start_dt),
            timeMax=_rfc3339(end_dt),
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
        .get("items", [])
    )

    # Define events to ignore (case insensitive)
    ignore_titles = {
        "focus",
        "home"  # Don't block home office times by default
    }

    # Define events that block the entire day
    block_day_titles = {
        "public holiday",
        "school closed",
        "ooo",
        "national holiday",
        "summer gathering",
        "parental leave",
        "cannes",
        "event",
        "vacation",
        "out of office",
        "midsummer eve",  # Swedish holiday
        "midsummer",      # Include variations
        "midsommar",      # Swedish spelling
        "holiday",        # Generic holiday
        "helgdag"         # Swedish for holiday
    }

    busy: list[tuple[datetime, datetime]] = []
    for ev in events:
        summary = ev.get("summary", "(No title)")
        summary_lower = summary.lower()
        
        # Skip events with ignored titles (exact matches only)
        if summary_lower in ignore_titles:
            print(f"⚠️  skipping ignored event: {summary}")
            continue

        # Handle all-day events
        if "date" in ev["start"] and "date" in ev["end"]:
            # Block if it matches block_day_titles or contains certain keywords
            should_block = (
                any(title in summary_lower for title in block_day_titles) or
                "gathering" in summary_lower or
                "holiday" in summary_lower or
                "ooo" in summary_lower.replace(" ", "") or  # Match OOO with or without spaces
                "vacation" in summary_lower or  # Block any vacation events
                "out of office" in summary_lower or  # Block any out of office events
                "event" in summary_lower  # Block any all-day events with "event" in the title
            )
            
            if should_block:
                print(f"🚫 blocking entire day for: {summary}")
                # Convert date string to datetime and block the full day
                start_date = datetime.fromisoformat(ev["start"]["date"])
                end_date = datetime.fromisoformat(ev["end"]["date"])  # Note: end date is exclusive
                
                # For multi-day events, block each day in the range
                current_date = start_date
                while current_date < end_date:  # Use < since end_date is exclusive
                    print(f"  - Blocking {current_date.isoformat()}")
                    day_start = datetime.combine(current_date, time.min, tzinfo=LOCAL_TZ)
                    day_end = datetime.combine(current_date, time.max, tzinfo=LOCAL_TZ)
                    busy.append((_to_utc(day_start), _to_utc(day_end)))
                    current_date += timedelta(days=1)
            else:
                print(f"⚠️  skipping non-blocking all-day event: {summary}")
            continue

        # Handle regular events
        s_raw = ev["start"].get("dateTime") or ev["start"]["date"]
        e_raw = ev["end"].get("dateTime")   or ev["end"]["date"]
        
        try:
            # Parse the raw datetime strings and ensure they're timezone aware
            s_dt = datetime.fromisoformat(s_raw)
            e_dt = datetime.fromisoformat(e_raw)
            
            # If the times don't have timezone info, assume they're in LOCAL_TZ
            if s_dt.tzinfo is None:
                s_dt = s_dt.replace(tzinfo=LOCAL_TZ)
            if e_dt.tzinfo is None:
                e_dt = e_dt.replace(tzinfo=LOCAL_TZ)
            
            # Convert to local time for display
            s_local = s_dt.astimezone(LOCAL_TZ)
            e_local = e_dt.astimezone(LOCAL_TZ)
            
            print(f"Adding event: {summary} ({s_local.strftime('%Y-%m-%d %H:%M')} → {e_local.strftime('%H:%M')})")
            
            # Store in UTC
            busy.append((_to_utc(s_dt), _to_utc(e_dt)))
        except Exception as e:
            print(f"⚠️  skipped malformed event: {summary} ({s_raw} – {e_raw}): {str(e)}")
    
    # Sort busy periods by start time
    busy.sort()
    
    print("\n🗓️ Calendar Events:")
    for ev_start, ev_end in busy:
        start_local = _to_local(ev_start)
        end_local = _to_local(ev_end)
        print(f"- {start_local.strftime('%Y-%m-%d %H:%M')} → {end_local.strftime('%H:%M')}")
    
    return busy

# ──────────────────────────────────────────────
# Split any window into equal‑length chunks
# ──────────────────────────────────────────────

def split_window_into_chunks(win_start, win_end, chunk_minutes):
    """Split a time window into equal-length chunks.
    
    Args:
        win_start: Start datetime (in local time)
        win_end: End datetime (in local time)
        chunk_minutes: Length of each chunk in minutes
        
    Returns:
        List of (chunk_start, chunk_end) tuples in local time
    """
    chunks = []
    cur = win_start
    delta = timedelta(minutes=chunk_minutes)
    
    print(f"\n🔍 Splitting window from {win_start.strftime('%H:%M')} to {win_end.strftime('%H:%M')} into {chunk_minutes}-minute chunks")
    print(f"Window duration: {(win_end - win_start).total_seconds() / 60:.0f} minutes")
    
    while cur + delta <= win_end:
        chunk = (cur, cur + delta)
        print(f"  Added chunk: {cur.strftime('%H:%M')} → {(cur + delta).strftime('%H:%M')}")
        chunks.append(chunk)
        cur += delta  # Move to next slot without buffer
        
    print(f"Found {len(chunks)} chunks in this window")
    return chunks

# ──────────────────────────────────────────────
# Free‑slot scanner (works entirely in UTC)
# ──────────────────────────────────────────────

def merge_overlapping_meetings(meetings):
    """Merge any overlapping meetings into single blocks."""
    if not meetings:
        return []
    
    # Sort by start time
    sorted_meetings = sorted(meetings, key=lambda x: x[0])
    merged = [sorted_meetings[0]]
    
    for current in sorted_meetings[1:]:
        previous = merged[-1]
        # If current meeting overlaps with previous or starts within 1 minute
        if current[0] <= previous[1] + timedelta(minutes=1):
            # Merge them by keeping the later end time
            merged[-1] = (previous[0], max(previous[1], current[1]))
        else:
            merged.append(current)
    
    return merged

def is_swedish_holiday(date: datetime) -> bool:
    """Check if a given date is a Swedish holiday."""
    # Convert to local time and get month/day
    local_date = _to_local(date)
    month = local_date.month
    day = local_date.day
    
    # Define Swedish holidays
    swedish_holidays = {
        # Fixed dates
        (6, 20): "Midsummer Eve",  # June 20
        (6, 21): "Midsummer Day",  # June 21
        (12, 24): "Christmas Eve",
        (12, 25): "Christmas Day",
        (12, 26): "Boxing Day",
        (12, 31): "New Year's Eve",
        (1, 1): "New Year's Day",
        (1, 6): "Epiphany",
        (5, 1): "Labour Day",
        (6, 6): "National Day"
    }
    
    return (month, day) in swedish_holidays

def find_free_slots(busy, start, end, duration_min, earliest, latest, allowed_days=None):
    """Return list of (slot_start_utc, slot_end_utc). All day‑logic is done in LOCAL_TZ
    so that times are correctly handled in Stockholm time.
    
    Args:
        busy: List of (start, end) tuples representing busy times in UTC
        start: Start datetime to look for slots
        end: End datetime to look for slots
        duration_min: Minimum duration of slots in minutes
        earliest: Earliest hour of day to consider (in local time, 0-23)
        latest: Latest hour of day to consider (in local time, 0-23)
        allowed_days: List of allowed weekday indices (0=Monday, 6=Sunday) or None for all weekdays
    """
    print(f"\n🔍 Debug: Finding slots with parameters:")
    print(f"Start (UTC): {start}")
    print(f"End (UTC): {end}")
    print(f"Duration: {duration_min} minutes")
    print(f"Hours: {earliest}:00 - {latest}:00 (local time)")
    print(f"Total search window: {(end - start).days} days")
    if allowed_days is not None:
        days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        print(f"Allowed days: {[days[i] for i in allowed_days]}")
    
    # Convert everything to local time for processing
    start_loc = _to_local(start)
    end_loc = _to_local(end)
    busy_loc = [(_to_local(s), _to_local(e)) for s, e in busy]
    
    # Sort busy times
    busy_loc.sort()
    
    # Ensure start and end times respect the hour constraints
    start_loc = start_loc.replace(hour=earliest, minute=0)
    end_loc = end_loc.replace(hour=latest, minute=0)
    
    print(f"\nSearch window in local time:")
    print(f"Start (local): {start_loc}")
    print(f"End (local): {end_loc}")
    
    print("\nBusy periods (local time):")
    for b_start, b_end in busy_loc:
        print(f"- {b_start.strftime('%Y-%m-%d %H:%M')} → {b_end.strftime('%H:%M')}")

    free = []
    delta = timedelta(minutes=duration_min)
    cur = start_loc
    days_checked = 0
    days_skipped = 0
    days_with_slots = 0
    slots_found_today = 0
    total_slots_found = 0

    while cur < end_loc:
        days_checked += 1
        slots_found_today = 0
        
        # Skip days that aren't in allowed_days
        if allowed_days is not None and cur.weekday() not in allowed_days:
            days_skipped += 1
            print(f"\n⏩ Skipping non-allowed day: {cur.date()} ({cur.strftime('%A')})")
            # Move to next day
            cur += timedelta(days=1)
            cur = datetime.combine(cur.date(), time(hour=earliest), tzinfo=LOCAL_TZ)
            continue
            
        # Skip weekends if no allowed_days specified (maintain default behavior)
        if allowed_days is None and cur.weekday() >= 5:
            days_skipped += 1
            print(f"\n⏩ Skipping weekend day: {cur.date()} ({cur.strftime('%A')})")
            # Move to next day
            cur += timedelta(days=1)
            cur = datetime.combine(cur.date(), time(hour=earliest), tzinfo=LOCAL_TZ)
            continue
            
        # Skip Swedish holidays
        if is_swedish_holiday(cur):
            days_skipped += 1
            print(f"\n⏩ Skipping Swedish holiday: {cur.date()}")
            # Move to next day
            cur += timedelta(days=1)
            cur = datetime.combine(cur.date(), time(hour=earliest), tzinfo=LOCAL_TZ)
            continue
            
        # Set up the day's boundaries in local time - strictly enforce time constraints
        day_start = datetime.combine(cur.date(), time(hour=earliest, minute=0), tzinfo=LOCAL_TZ)
        day_end = datetime.combine(cur.date(), time(hour=latest, minute=0), tzinfo=LOCAL_TZ)
        
        print(f"\n📅 Checking {cur.strftime('%A')}, {cur.date()}:")
        print(f"Day window: {day_start.strftime('%H:%M')} - {day_end.strftime('%H:%M')} (local)")

        # Get busy blocks for current day and sort them
        day_busy = []
        for b_start, b_end in busy_loc:
            # Only include events that overlap with our search window
            if b_end.date() >= cur.date() and b_start.date() <= cur.date():
                # Clip the event times to our search window for this day
                clipped_start = max(b_start, day_start)
                clipped_end = min(b_end, day_end)
                if clipped_start.date() == cur.date():  # Only include if start is on current day
                    day_busy.append((clipped_start, clipped_end))
        
        # Merge overlapping meetings
        day_busy = merge_overlapping_meetings(sorted(day_busy))
        
        if day_busy:
            print(f"Found {len(day_busy)} meetings/blocks for this day:")
            for b_start, b_end in day_busy:
                print(f"  - 🚫 {b_start.strftime('%H:%M')} → {b_end.strftime('%H:%M')}")
        else:
            print("No meetings/blocks for this day! 🎉")

        # Instead of looking for gaps between meetings, try each possible slot
        slot_start = day_start
        while slot_start + delta <= day_end:
            slot_end = slot_start + delta
            
            # Check if this slot overlaps with any busy time
            is_free = True
            for busy_start, busy_end in day_busy:
                # A slot overlaps if it starts before a busy period ends AND ends after a busy period starts
                if (slot_start < busy_end and slot_end > busy_start):
                    print(f"❌ Slot {slot_start.strftime('%H:%M')} → {slot_end.strftime('%H:%M')} overlaps with busy time {busy_start.strftime('%H:%M')} → {busy_end.strftime('%H:%M')}")
                    is_free = False
                    break
            
            if is_free:
                slot = (_to_utc(slot_start), _to_utc(slot_end))
                print(f"✅ Found slot: {slot_start.strftime('%H:%M')} → {slot_end.strftime('%H:%M')} ({duration_min} min)")
                free.append(slot)
                slots_found_today += 1
                total_slots_found += 1
            
            # Move to next potential slot start time - use the requested duration
            slot_start += timedelta(minutes=duration_min)  # No extra buffer needed

        if slots_found_today > 0:
            days_with_slots += 1
            print(f"📊 Found {slots_found_today} slots for {cur.date()}")

        # Move to next day
        cur += timedelta(days=1)
        cur = datetime.combine(cur.date(), time(hour=earliest), tzinfo=LOCAL_TZ)

    print("\n🔍 Pre-filtering stats:")
    print(f"- Total slots found: {total_slots_found}")
    print(f"- Days with slots: {days_with_slots}")
    print(f"- Days checked: {days_checked}")
    print(f"- Weekend days skipped: {days_skipped}")

    # Filter slots to ensure they meet the time constraints
    filtered_free = []
    slots_filtered = 0
    for slot_start, slot_end in free:
        slot_start_local = _to_local(slot_start)
        slot_end_local = _to_local(slot_end)
        
        # Verify the slot is within the requested hours
        if (earliest <= slot_start_local.hour < latest and 
            earliest <= slot_end_local.hour <= latest):
            filtered_free.append((slot_start, slot_end))
        else:
            slots_filtered += 1
            print(f"⚠️ Filtered out slot at {slot_start_local.strftime('%Y-%m-%d %H:%M')} (outside work hours)")
    
    # Sort slots by date/time
    filtered_free.sort()
    
    print(f"\n📊 Final Search Summary:")
    print(f"- Days checked: {days_checked}")
    print(f"- Weekend days skipped: {days_skipped}")
    print(f"- Days with slots found: {days_with_slots}")
    print(f"- Total slots found: {len(filtered_free)}")
    print(f"- Slots filtered out: {slots_filtered}")
    
    if not filtered_free:
        print("\n❌ No slots found matching your criteria. Try different dates or times.")
        return []

    print(f"\n✨ Available Slots:")
    for slot_start, slot_end in filtered_free:
        start_local = _to_local(slot_start)
        end_local = _to_local(slot_end)
        duration = (end_local - start_local).total_seconds() / 60
        print(f"- {start_local.strftime('%Y-%m-%d %H:%M')} → {end_local.strftime('%H:%M')} ({duration:.0f} min)")

    return filtered_free

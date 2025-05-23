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
    Examples: 'next week', 'tomorrow', 'next monday', 'in three weeks'
    
    Returns:
        Tuple of (start_datetime, end_datetime) in the local timezone
    """
    print(f"\nDebug: Parsing date phrase: {date_phrase}")
    
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
    if 'week' in date_phrase.lower():
        print("Debug: Detected week-related phrase")
        
        # For "in X weeks" or "X weeks from now", add weeks but don't adjust to start of week
        if 'from now' in date_phrase.lower() or 'in' in date_phrase.lower():
            words = date_phrase.lower().split()
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
        "out of office"
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
            s_dt = datetime.fromisoformat(s_raw)
            e_dt = datetime.fromisoformat(e_raw)
            print(f"Adding event: {summary} ({_to_local(s_dt).strftime('%H:%M')} → {_to_local(e_dt).strftime('%H:%M')})")
            busy.append((_to_utc(s_dt), _to_utc(e_dt)))
        except Exception:
            print(f"⚠️  skipped malformed event: {summary} ({s_raw} – {e_raw})")
    
    # Sort busy periods by start time
    busy.sort()
    
    print("\n🗓️ Calendar Events:")
    for ev_start, ev_end in busy:
        start_local = _to_local(ev_start)
        end_local = _to_local(ev_end)
        print(f"- {start_local.strftime('%Y-%m-%d %H:%M')} → {end_local.strftime('%H:%M')}")
    
    # Merge any busy periods that are very close together (less than minimum viable gap)
    min_gap = timedelta(minutes=1)  # Minimum gap we consider viable between meetings
    merged = []
    if busy:
        current = busy[0]
        for next_period in busy[1:]:
            if _to_local(next_period[0]) - _to_local(current[1]) < min_gap:
                # Merge the periods
                current = (current[0], max(current[1], next_period[1]))
            else:
                merged.append(current)
                current = next_period
        merged.append(current)
        busy = merged
        
        print("\nMerged Events (after combining overlaps):")
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
    buffer = timedelta(minutes=15)  # 15-minute buffer between slots
    
    print(f"\n🔍 Splitting window from {win_start.strftime('%H:%M')} to {win_end.strftime('%H:%M')} into {chunk_minutes}-minute chunks")
    print(f"Window duration: {(win_end - win_start).total_seconds() / 60:.0f} minutes")
    
    while cur + delta <= win_end:
        chunk = (cur, cur + delta)
        chunks.append(chunk)
        print(f"  Added chunk: {cur.strftime('%H:%M')} → {(cur + delta).strftime('%H:%M')}")
        # Move to next potential slot start time, with a buffer
        cur += delta + buffer
    
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

def find_free_slots(busy, start, end, duration_min, earliest, latest):
    """Return list of (slot_start_utc, slot_end_utc). All day‑logic is done in LOCAL_TZ
    so that times are correctly handled in Stockholm time.
    
    Args:
        busy: List of (start, end) tuples representing busy times in UTC
        start: Start datetime to look for slots
        end: End datetime to look for slots
        duration_min: Minimum duration of slots in minutes
        earliest: Earliest hour of day to consider (in local time, 0-23)
        latest: Latest hour of day to consider (in local time, 0-23)
    """
    print(f"\n🔍 Debug: Finding slots with parameters:")
    print(f"Start (UTC): {start}")
    print(f"End (UTC): {end}")
    print(f"Duration: {duration_min} minutes")
    print(f"Hours: {earliest}:00 - {latest}:00 (local time)")
    print(f"Total search window: {(end - start).days} days")
    
    # Convert everything to local time for processing
    start_loc = _to_local(start)
    end_loc = _to_local(end)
    busy_loc = [(_to_local(s), _to_local(e)) for s, e in busy]
    
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
        
        # Skip weekends
        if cur.weekday() >= 5:  # 5 is Saturday, 6 is Sunday
            days_skipped += 1
            print(f"\n⏩ Skipping weekend day: {cur.date()} ({cur.strftime('%A')})")
            # Move to next day
            cur += timedelta(days=1)
            cur = datetime.combine(cur.date(), time(hour=earliest), tzinfo=LOCAL_TZ)
            continue
            
        # Set up the day's boundaries in local time
        day_start = datetime.combine(cur.date(), time(hour=earliest), tzinfo=LOCAL_TZ)
        day_end = datetime.combine(cur.date(), time(hour=latest), tzinfo=LOCAL_TZ)

        # Don't look before the overall start time or after the overall end time
        day_start = max(day_start, start_loc)
        day_end = min(day_end, end_loc)
        
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
        day_busy = merge_overlapping_meetings(day_busy)
        
        if day_busy:
            print(f"Found {len(day_busy)} meetings/blocks for this day:")
            for b_start, b_end in day_busy:
                print(f"  - 🚫 {b_start.strftime('%H:%M')} → {b_end.strftime('%H:%M')}")
        else:
            print("No meetings/blocks for this day! 🎉")

        # Start from the beginning of the work day
        pointer = day_start

        # Process each busy block
        for b_start, b_end in day_busy:
            # If there's a gap before this meeting that's long enough
            gap = b_start - pointer
            gap_minutes = gap.total_seconds() / 60
            if gap_minutes >= duration_min:
                # Only consider the gap if it ends before the work day ends
                gap_end = min(b_start, day_end)
                if gap_end > pointer:
                    # For each gap that's long enough, create multiple slots if possible
                    slot_start = pointer
                    while slot_start + delta <= gap_end:
                        slot = (_to_utc(slot_start), _to_utc(slot_start + delta))
                        print(f"✅ Found slot: {_to_local(slot[0]).strftime('%H:%M')} → {_to_local(slot[1]).strftime('%H:%M')} ({duration_min} min)")
                        free.append(slot)
                        slots_found_today += 1
                        total_slots_found += 1
                        # Move to next potential slot start time, with a buffer
                        slot_start += timedelta(minutes=45)  # Add 15-minute buffer between slots
            pointer = max(pointer, b_end)

        # Check for gap after last meeting to end of work day
        if pointer < day_end:
            final_gap = day_end - pointer
            final_gap_minutes = final_gap.total_seconds() / 60
            if final_gap_minutes >= duration_min:
                # Create multiple slots in the end-of-day gap if possible
                slot_start = pointer
                while slot_start + delta <= day_end:
                    slot = (_to_utc(slot_start), _to_utc(slot_start + delta))
                    print(f"✅ Found end-of-day slot: {_to_local(slot[0]).strftime('%H:%M')} → {_to_local(slot[1]).strftime('%H:%M')} ({duration_min} min)")
                    free.append(slot)
                    slots_found_today += 1
                    total_slots_found += 1
                    # Move to next potential slot start time, with a buffer
                    slot_start += timedelta(minutes=45)  # Add 15-minute buffer between slots

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
    
    if filtered_free:
        print(f"\n✨ Available Slots:")
        for slot_start, slot_end in filtered_free:
            start_local = _to_local(slot_start)
            end_local = _to_local(slot_end)
            duration = (end_local - start_local).total_seconds() / 60
            print(f"- {start_local.strftime('%Y-%m-%d %H:%M')} → {end_local.strftime('%H:%M')} ({duration:.0f} min)")
    else:
        print("\n❌ No available slots found that match all criteria:")
        print("- Must be on a weekday")
        print(f"- Must be between {earliest:02d}:00 and {latest:02d}:00")
        print(f"- Must have at least {duration_min} minutes available")
        print("- Must not conflict with any calendar events")

    return filtered_free

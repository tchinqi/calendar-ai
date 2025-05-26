from datetime import datetime
from zoneinfo import ZoneInfo
from nlp_utils import parse_schedule_request
from debug_events import _get_creds, list_events
from config import THOR_CAL_ID
from googleapiclient.discovery import build

def get_schedule(prompt: str) -> dict:
    """Get Thor's schedule for the requested time range."""
    # Parse the schedule request
    parsed = parse_schedule_request(prompt)
    if not parsed:
        return {
            "error": "Could not understand schedule request. Try asking something like 'Show me Thor's schedule for today' or 'What's on the calendar for July?'"
        }
    
    # Get calendar service
    creds = _get_creds()
    service = build("calendar", "v3", credentials=creds, cache_discovery=False)
    
    # Convert dates to ISO format for the API
    start_iso = parsed["start"].astimezone(ZoneInfo("UTC")).isoformat()
    end_iso = parsed["end"].astimezone(ZoneInfo("UTC")).isoformat()
    
    # Get events
    events = list_events(service, THOR_CAL_ID, start_iso, end_iso)
    
    # Format events for display
    formatted_events = []
    for event in events:
        # Get start and end times
        start = event["start"].get("dateTime") or event["start"].get("date")
        end = event["end"].get("dateTime") or event["end"].get("date")
        
        # Convert to datetime objects in local timezone
        start_dt = datetime.fromisoformat(start).astimezone(ZoneInfo("Europe/Stockholm"))
        end_dt = datetime.fromisoformat(end).astimezone(ZoneInfo("Europe/Stockholm"))
        
        # Format the event
        formatted_events.append({
            "summary": event.get("summary", "(No title)"),
            "start": start_dt.strftime("%Y-%m-%d %H:%M"),
            "end": end_dt.strftime("%H:%M") if start_dt.date() == end_dt.date() else end_dt.strftime("%Y-%m-%d %H:%M"),
            "is_all_day": "date" in event["start"]
        })
    
    return {
        "description": parsed["description"],
        "events": formatted_events,
        "start": parsed["start"].isoformat(),
        "end": parsed["end"].isoformat()
    } 
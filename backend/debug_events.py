from config import THOR_CAL_ID
#!/usr/bin/env python3
"""
debug_events.py – sanity-check Google Calendar fetch

Usage
─────
# list all accessible calendars (IDs & names)
python backend/debug_events.py --list-cal

# show Thor’s next-7-days events
python backend/debug_events.py --calendar "Thor Olof Philogène" --days 7

# explicit range on Thor’s calendar
python backend/debug_events.py --calendar thor@example.com --start 2025-05-26 --end 2025-05-27
"""
import argparse, datetime as dt, pathlib, pickle, sys
from zoneinfo import ZoneInfo
from dateutil.parser import parse as dtparse, isoparse

from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

# ── config ─────────────────────────────────────────────────────
SCOPES       = ["https://www.googleapis.com/auth/calendar.readonly"]
CREDS_JSON   = "backend/credentials.json"
TOKEN_FILE   = pathlib.Path("backend/token.pickle")
LOCAL_TZ     = ZoneInfo("Europe/Stockholm")          # Thor’s zone


# ── credentials ────────────────────────────────────────────────
def _get_creds() -> Credentials:
    creds: Credentials | None = None
    if TOKEN_FILE.exists():
        creds = pickle.loads(TOKEN_FILE.read_bytes())

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDS_JSON, SCOPES)
            creds = flow.run_local_server(port=8080)
        TOKEN_FILE.write_bytes(pickle.dumps(creds))
    return creds


# ── helpers ────────────────────────────────────────────────────
def _iso(dt_obj: dt.datetime) -> str:
    if dt_obj.tzinfo is None:
        dt_obj = dt_obj.replace(tzinfo=LOCAL_TZ)
    return dt_obj.astimezone(ZoneInfo("UTC")).isoformat()


def list_events(svc, cal_id, start_iso, end_iso):
    return (
        svc.events()
        .list(
            calendarId=cal_id,
            timeMin=start_iso,
            timeMax=end_iso,
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
        .get("items", [])
    )


# ── main ───────────────────────────────────────────────────────
def main(argv=None):
    argv = argv or sys.argv[1:]
    p = argparse.ArgumentParser(description="Dump raw calendar events.")
    p.add_argument("--list-cal", action="store_true", help="List all accessible calendars")
    p.add_argument("--calendar", help="Calendar name or ID (default: primary)")
    p.add_argument("--days", type=int, help="Events in the next N days")
    p.add_argument("--start", help="Start (YYYY-MM-DD or ISO)")
    p.add_argument("--end",   help="End   (YYYY-MM-DD or ISO)")
    args = p.parse_args(argv)

    creds   = _get_creds()
    service = build("calendar", "v3", credentials=creds, cache_discovery=False)

    # ── list calendars and exit ────────────────────────────────
    cal_items = service.calendarList().list().execute().get("items", [])
    if args.list_cal:
        print("\nAccessible calendars:\n")
        for c in cal_items:
            print(f"• {c['summary']:<40}  id: {c['id']}")
        return

    # ── choose calendar ────────────────────────────────────────
    cal_id = THOR_CAL_ID
    if args.calendar:
        # match by exact id or case-insensitive summary
        for c in cal_items:
            if c["id"] == args.calendar or c["summary"].lower() == args.calendar.lower():
                cal_id = c["id"]
                break
        else:
            sys.exit(f"❌ Calendar '{args.calendar}' not found. Use --list-cal to view options.")

    # ── date range ─────────────────────────────────────────────
    if args.days:
        start_dt = dt.datetime.now(LOCAL_TZ).replace(hour=0, minute=0, second=0, microsecond=0)
        end_dt   = start_dt + dt.timedelta(days=args.days)
    elif args.start and args.end:
        start_dt = dtparse(args.start)
        end_dt   = dtparse(args.end)
        if start_dt.tzinfo is None:
            start_dt = start_dt.replace(tzinfo=LOCAL_TZ)
        if end_dt.tzinfo is None:
            end_dt = end_dt.replace(tzinfo=LOCAL_TZ)
    else:
        p.error("Provide either --days N  or  --start X --end Y.")

    # ── fetch & print events ──────────────────────────────────
    events = list_events(service, cal_id, _iso(start_dt), _iso(end_dt))
    if not events:
        print("No events found.")
        return

    cal_name = next((c["summary"] for c in cal_items if c["id"] == cal_id), cal_id)
    print(f"\nEvents for calendar: {cal_name}\n{start_dt} → {end_dt} ({LOCAL_TZ})\n")
    for ev in events:
        summary = ev.get("summary", "(No title)")
        s = ev["start"].get("dateTime") or ev["start"]["date"]
        e = ev["end"].get("dateTime")   or ev["end"]["date"]
        s_dt = isoparse(s).astimezone(LOCAL_TZ)
        e_dt = isoparse(e).astimezone(LOCAL_TZ)
        print(f"• {summary:30} {s_dt:%Y-%m-%d %H:%M} → {e_dt:%H:%M}")


if __name__ == "__main__":
    main()

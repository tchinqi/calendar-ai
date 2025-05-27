import os, pathlib, pickle
from flask import Flask, redirect, url_for, session, request, jsonify, send_from_directory, make_response
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from datetime import datetime, timezone, timedelta
from calendar_utils import split_window_into_chunks, _to_local, _to_utc

from config         import SCOPES, DEFAULT_SLOT_MINUTES
from nlp_utils      import extract_parameters
from calendar_utils import get_service, list_events, find_free_slots, create_event
from config         import THOR_CAL_ID
from view_schedule  import get_schedule

import os
os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"   # dev-only, remove in prod

app = Flask(__name__, static_folder="../frontend", static_url_path="")
app.secret_key = os.getenv("FLASK_SECRET", "dev-secret")

CREDS_FILE = pathlib.Path("token.pickle")
CLIENT_CONFIG = "backend/credentials.json"   # downloaded from Google Cloud Console

def format_time_slot(start_local, end_local, start_utc, end_utc, duration_mins):
    """Format time slot in a clean, text-based format"""
    return f"""Date: {start_local.strftime('%Y-%m-%d')}
Duration: {duration_mins} minutes
CET: {start_local.strftime('%H:%M')} - {end_local.strftime('%H:%M')}
UTC: {start_utc.strftime('%H:%M')} - {end_utc.strftime('%H:%M')}"""

# ---------- auth helpers ----------
def save_creds(creds):
    CREDS_FILE.write_bytes(pickle.dumps(creds))

def load_creds():
    return pickle.loads(CREDS_FILE.read_bytes()) if CREDS_FILE.exists() else None

# ---------- routes ----------
@app.route("/")
def root():
    return app.send_static_file("index.html")

@app.route("/authorize")
def authorize():
    flow = Flow.from_client_secrets_file(
        CLIENT_CONFIG, scopes=SCOPES,
        redirect_uri=url_for("oauth2callback", _external=True)
    )
    auth_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent"
    )
    session["state"] = state
    return redirect(auth_url)

@app.route("/oauth2callback")
def oauth2callback():
    state = session["state"]
    flow = Flow.from_client_secrets_file(
        CLIENT_CONFIG, scopes=SCOPES,
        state=state,
        redirect_uri=url_for("oauth2callback", _external=True)
    )
    flow.fetch_token(authorization_response=request.url)
    creds = flow.credentials
    save_creds(creds)
    return redirect(url_for("root"))

@app.route("/free-slots", methods=["POST"])
def free_slots():
    creds = load_creds()
    if not creds or not creds.valid:
        return jsonify({"auth": False}), 401

    params = extract_parameters(request.json.get("prompt", ""))
    print("\n🔎 NLP extracted parameters:")
    print(f"- Duration: {params['duration']} minutes")
    print(f"- Count: {params['count']} slots")
    print(f"- Start: {params['start'].strftime('%Y-%m-%d %H:%M %Z')}")
    print(f"- End: {params['end'].strftime('%Y-%m-%d %H:%M %Z')}")
    print(f"- Earliest: {params['earliest']}:00")
    print(f"- Latest: {params['latest']}:00")
    if params.get('allowed_days'):
        days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        print(f"- Allowed days: {[days[i] for i in params['allowed_days']]}")

    duration = params["duration"]
    start, end = params["start"], params["end"]
    need_n = params["count"]  # Get count directly from params

    print(f"\n🎯 Searching for {need_n} slots of {duration} minutes each")
    print(f"Search window: {start.strftime('%Y-%m-%d')} to {end.strftime('%Y-%m-%d')}")

    service = get_service(creds)
    busy = list_events(service, THOR_CAL_ID, start, end)
    slots = find_free_slots(
        busy, start, end,
        duration, params["earliest"], params["latest"],
        allowed_days=params.get("allowed_days")
    )
    
    print(f"\n📊 Found {len(slots)} initial free windows")
    
    # Split each free window into chunks of the requested duration
    chunks = []
    for w_start, w_end in slots:
        # Convert to local time for better readability
        w_start_local = _to_local(w_start)
        w_end_local = _to_local(w_end)
        print(f"\nSplitting window: {w_start_local.strftime('%Y-%m-%d %H:%M')} → {w_end_local.strftime('%H:%M')}")
        # Take all possible chunks from this window
        window_chunks = list(split_window_into_chunks(w_start_local, w_end_local, duration))
        print(f"Found {len(window_chunks)} chunks in this window")
        chunks.extend(window_chunks)

    # Sort chunks by start time
    chunks.sort(key=lambda x: x[0])
    print(f"\n📈 Total chunks available: {len(chunks)}")

    # Take the requested number of chunks, spread across different days if possible
    chosen = []
    seen_dates = set()
    print(f"\n🎯 Attempting to select {need_n} slots from {len(chunks)} available chunks")
    
    # First pass: Try to get slots from different days
    for chunk in chunks:
        chunk_date = chunk[0].date()
        if len(chosen) < need_n and chunk_date not in seen_dates:
            chosen.append(chunk)
            seen_dates.add(chunk_date)
            print(f"Selected slot {len(chosen)}/{need_n} (different day): {chunk[0].strftime('%Y-%m-%d %H:%M')} → {chunk[1].strftime('%H:%M')}")
    
    # Second pass: If we still need more slots, take any remaining slots
    if len(chosen) < need_n:
        print(f"Still need {need_n - len(chosen)} more slots, taking any available slots")
        remaining_chunks = [c for c in chunks if c not in chosen]  # Only consider unchosen chunks
        
        for chunk in remaining_chunks:
            if len(chosen) >= need_n:
                break
                
            # For slots on the same day, just ensure they don't overlap
            can_add = True
            chunk_start, chunk_end = chunk
            chunk_date = chunk_start.date()
            
            # Check against existing chosen slots for this day
            day_slots = [s for s in chosen if s[0].date() == chunk_date]
            for existing_start, existing_end in day_slots:
                # Only check for direct overlap, no buffer needed
                if (chunk_start < existing_end and chunk_end > existing_start):
                    can_add = False
                    print(f"Skipping slot {chunk_start.strftime('%H:%M')}-{chunk_end.strftime('%H:%M')} due to overlap")
                    break
            
            if can_add:
                chosen.append(chunk)
                print(f"Selected slot {len(chosen)}/{need_n} (same day allowed): {chunk_start.strftime('%Y-%m-%d %H:%M')} → {chunk_end.strftime('%H:%M')}")

    # Sort chosen slots by date/time
    chosen.sort(key=lambda x: x[0])
    print(f"\n✨ Selected {len(chosen)} slots out of {len(chunks)} available chunks")

    # Format response as clean text
    if not chosen:
        response_text = "No available slots found."
    else:
        formatted_slots = []
        for i, (s, e) in enumerate(chosen, 1):
            s_utc = _to_utc(s)
            e_utc = _to_utc(e)
            # Simple, clean format that's easy to parse
            slot_text = (
                f"Slot {i}\n"
                f"{s.strftime('%Y-%m-%d')}\n"
                f"{s.strftime('%A')} | {s.strftime('%H:%M')}-{e.strftime('%H:%M')} | "
                f"{s_utc.strftime('%H:%M')}-{e_utc.strftime('%H:%M')} UTC"
            )
            formatted_slots.append(slot_text)
        
        response_text = "\n\n".join(formatted_slots)
    
    # Return plain text response
    response = make_response(response_text)
    response.headers["Content-Type"] = "text/plain; charset=utf-8"
    return response

@app.route("/view-schedule", methods=["POST"])
def view_schedule():
    creds = load_creds()
    if not creds or not creds.valid:
        return jsonify({"auth": False}), 401

    prompt = request.json.get("prompt", "")
    result = get_schedule(prompt)
    
    if "error" in result:
        return jsonify(result), 400
        
    # Format response as clean text
    formatted_events = []
    for event in result["events"]:
        if event["is_all_day"]:
            event_text = f"{event['start'][:10]} (All day) - {event['summary']}"
        else:
            if event["start"][:10] == event["end"][:10]:  # Same day
                event_text = f"{event['start']} - {event['end']} - {event['summary']}"
            else:  # Multi-day event
                event_text = f"{event['start']} → {event['end']} - {event['summary']}"
        formatted_events.append(event_text)
    
    response_text = f"📅 {result['description'].capitalize()}\n\n"
    if not formatted_events:
        response_text += "No events found."
    else:
        response_text += "\n".join(formatted_events)
    
    # Return plain text response
    response = make_response(response_text)
    response.headers["Content-Type"] = "text/plain; charset=utf-8"
    return response

@app.route("/create-event", methods=["POST"])
def create_calendar_event():
    creds = load_creds()
    if not creds or not creds.valid:
        return jsonify({"auth": False}), 401

    try:
        data = request.json
        prompt = data.get("prompt", "")
        attendees = data.get("attendees", [])
        
        # Extract event details from the prompt
        # Format: "Create event [title] from [start] to [end]"
        import re
        match = re.match(r"(?i)create\s+event\s+(.+?)\s+from\s+(.+?)\s+to\s+(.+)$", prompt)
        if not match:
            return jsonify({
                "error": "Could not understand event creation request. Please use format: 'Create event [title] from [start] to [end]'"
            }), 400
            
        title = match.group(1)
        start_str = match.group(2)
        end_str = match.group(3)
        
        # Parse the datetime strings
        from datetime import datetime
        from zoneinfo import ZoneInfo
        
        # Parse datetime strings in local timezone
        local_tz = ZoneInfo("Europe/Stockholm")
        start_dt = datetime.strptime(start_str, "%Y-%m-%d %H:%M").replace(tzinfo=local_tz)
        end_dt = datetime.strptime(end_str, "%Y-%m-%d %H:%M").replace(tzinfo=local_tz)
        
        # Create the event
        service = get_service(creds)
        event = create_event(service, THOR_CAL_ID, title, start_dt, end_dt, attendees=attendees)
        
        return jsonify({
            "success": True,
            "event": {
                "id": event["id"],
                "title": event["summary"],
                "start": start_dt.isoformat(),
                "end": end_dt.isoformat(),
                "attendees": attendees
            }
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 400

# ---------- dev helpers ----------
@app.route("/<path:path>")
def static_proxy(path):
    return send_from_directory(app.static_folder, path)

if __name__ == "__main__":
    print("✅ Starting Flask app...")  # Add this line
    app.run(debug=True, port=8080)

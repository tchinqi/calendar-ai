import os, pathlib, pickle
from flask import Flask, redirect, url_for, session, request, jsonify, send_from_directory, make_response
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from datetime import datetime, timezone
from calendar_utils import split_window_into_chunks, _to_local, _to_utc

from config         import SCOPES, DEFAULT_SLOT_MINUTES
from nlp_utils      import extract_parameters
from calendar_utils import get_service, list_events, find_free_slots
from config         import THOR_CAL_ID

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
    print("🔎 NLP extracted:", params)
    duration = params["duration"]
    start, end = params["start"], params["end"]
    need_n = params.get("count", 1)

    service = get_service(creds)
    busy = list_events(service, THOR_CAL_ID, start, end)
    slots = find_free_slots(
        busy, start, end,
        duration, params["earliest"], params["latest"]
    )
    
    # Split each free window into chunks of the requested duration
    chunks = []
    for w_start, w_end in slots:
        # Convert to local time for better readability
        w_start_local = _to_local(w_start)
        w_end_local = _to_local(w_end)
        print(f"\nSplitting window: {w_start_local.strftime('%H:%M')} → {w_end_local.strftime('%H:%M')}")
        # Take all possible chunks from this window
        for chunk_start, chunk_end in split_window_into_chunks(w_start_local, w_end_local, duration):
            print(f"  Found chunk: {chunk_start.strftime('%H:%M')} → {chunk_end.strftime('%H:%M')}")
            chunks.append((chunk_start, chunk_end))

    # Sort chunks by start time
    chunks.sort(key=lambda x: x[0])
    print(f"\nTotal chunks found: {len(chunks)}")

    # Take the requested number of chunks, spread across different days if possible
    chosen = []
    seen_dates = set()
    for chunk in chunks:
        chunk_date = chunk[0].date()
        # If we haven't seen this date before, or we haven't found enough slots yet
        if chunk_date not in seen_dates or len(chosen) < need_n:
            chosen.append(chunk)
            seen_dates.add(chunk_date)
            if len(chosen) >= need_n:
                break

    # Format response as clean text
    if not chosen:
        response_text = "No available slots found."
    else:
        formatted_slots = []
        for i, (s, e) in enumerate(chosen, 1):
            s_utc = _to_utc(s)
            e_utc = _to_utc(e)
            duration_mins = int((e - s).total_seconds() / 60)
            slot_text = f"\nSlot {i}:\n" + format_time_slot(s, e, s_utc, e_utc, duration_mins)
            formatted_slots.append(slot_text)
        
        response_text = "Available slots:" + "\n".join(formatted_slots)
    
    # Return plain text response
    response = make_response(response_text)
    response.headers["Content-Type"] = "text/plain; charset=utf-8"
    return response

# ---------- dev helpers ----------
@app.route("/<path:path>")
def static_proxy(path):
    return send_from_directory(app.static_folder, path)

if __name__ == "__main__":
    print("✅ Starting Flask app...")  # Add this line
    app.run(debug=True, port=8080)

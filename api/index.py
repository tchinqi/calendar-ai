from flask import Flask, request, jsonify
import sys
import os

# Add the backend directory to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.calendar_utils import list_events, find_free_slots, get_service
from backend.nlp_utils import parse_date_range
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

app = Flask(__name__)

@app.route('/api/find-slots', methods=['POST'])
def find_slots():
    try:
        data = request.json
        query = data.get('query')
        duration = data.get('duration', 30)  # Default 30 minutes
        
        # Parse the date range from the query
        start_dt, end_dt = parse_date_range(query)
        
        # Get calendar events
        service = get_service()
        busy_times = list_events(service, 'primary', start_dt, end_dt)
        
        # Find free slots
        free_slots = find_free_slots(
            busy_times,
            start_dt,
            end_dt,
            duration,
            9,  # Default workday start
            17  # Default workday end
        )
        
        # Format the response
        formatted_slots = []
        local_tz = ZoneInfo("Europe/Stockholm")
        for start, end in free_slots:
            start_local = start.astimezone(local_tz)
            end_local = end.astimezone(local_tz)
            formatted_slots.append({
                'start': start_local.isoformat(),
                'end': end_local.isoformat(),
                'duration': duration
            })
            
        return jsonify({
            'slots': formatted_slots,
            'query': query,
            'date_range': {
                'start': start_dt.isoformat(),
                'end': end_dt.isoformat()
            }
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/')
def home():
    return 'Calendar Slot Finder API is running!'

# For local development
if __name__ == '__main__':
    app.run(debug=True) 
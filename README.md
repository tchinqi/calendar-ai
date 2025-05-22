# Calendar Slot Finder

A smart calendar assistant that finds available meeting slots using natural language queries. Built with Python (Flask) backend and a clean HTML/CSS frontend.

## Features

- Natural language date/time parsing
  - "Find me a 30-minute slot next week"
  - "Is there a slot between June 2nd and 6th?"
  - "20-minute slot in June after 2 PM"
- Smart calendar handling
  - Respects existing meetings with buffer times
  - Handles all-day events and holidays
  - Skips weekends automatically
  - Proper timezone support (CET/UTC)
- Clean, modern UI
  - Step-by-step interface
  - Example queries
  - Responsive design

## Setup

1. Clone the repository:
```bash
git clone [repository-url]
cd calendar-slot-finder
```

2. Create and activate a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Set up Google Calendar API:
   - Go to [Google Cloud Console](https://console.cloud.google.com)
   - Create a new project
   - Enable the Google Calendar API
   - Create OAuth 2.0 credentials
   - Download the credentials and save as `backend/credentials.json`

5. Run the application:
```bash
python backend/app.py
```

6. Open http://localhost:8080 in your browser

## Usage

1. Click "Authorize Access" to connect your Google Calendar
2. Enter your query in natural language
3. Click "Find Slots" to see available time slots

Example queries:
- "Find me a 30-minute slot next week"
- "Is there a slot between June 2nd and 6th?"
- "20-minute slot tomorrow morning"
- "Any slots next Monday after 2 PM?"

## Configuration

Key settings can be found in `backend/config.py`:
- `WORKDAY_START`: Default start of workday (9 AM)
- `WORKDAY_END`: Default end of workday (5 PM)
- `DEFAULT_SLOT_MINUTES`: Default meeting duration (20 minutes)

## Development

The project structure:
```
calendar-slot-finder/
├── backend/
│   ├── app.py              # Flask application
│   ├── calendar_utils.py   # Calendar handling logic
│   ├── nlp_utils.py        # Natural language processing
│   └── config.py           # Configuration
├── frontend/
│   ├── index.html          # Main UI
│   └── main.js             # Frontend logic
└── requirements.txt        # Python dependencies
```

## Security Notes

- The application uses OAuth 2.0 for secure Google Calendar access
- Credentials are stored locally in `token.pickle`
- For production deployment:
  - Remove `OAUTHLIB_INSECURE_TRANSPORT` setting
  - Set proper `FLASK_SECRET`
  - Use HTTPS
  - Add proper error handling and rate limiting

## License

MIT License - See LICENSE file for details

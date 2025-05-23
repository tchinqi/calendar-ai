import dateparser
from datetime import datetime
from zoneinfo import ZoneInfo

LOCAL_TZ = ZoneInfo("Europe/Stockholm")

def test_parse():
    date_phrase = "in three weeks"
    print(f"\nParsing: {date_phrase}")
    
    base_date = dateparser.parse(
        date_phrase,
        settings={
            'TIMEZONE': str(LOCAL_TZ),
            'RETURN_AS_TIMEZONE_AWARE': True,
            'RELATIVE_BASE': datetime.now(LOCAL_TZ)
        }
    )
    
    print(f"Base date: {base_date}")
    
    if not base_date:
        print("Failed to parse date")
        return
        
    print(f"Day of week: {base_date.strftime('%A')}")
    print(f"Is timezone aware: {base_date.tzinfo is not None}")

if __name__ == "__main__":
    test_parse() 
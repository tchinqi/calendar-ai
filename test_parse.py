from backend.calendar_utils import parse_date_range

try:
    start, end = parse_date_range("in three weeks")
    print(f"\nSuccess!")
    print(f"Start date: {start}")
    print(f"End date: {end}")
except Exception as e:
    print(f"Error: {str(e)}") 
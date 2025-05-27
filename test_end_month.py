from backend.calendar_utils import parse_date_range

def test_phrase(phrase):
    print(f"\nTesting phrase: '{phrase}'")
    try:
        start, end = parse_date_range(phrase)
        print(f"Start date: {start}")
        print(f"End date: {end}")
    except Exception as e:
        print(f"Error: {str(e)}")

# Test various end of month phrases
test_phrase("end of july")
test_phrase("last week of july")
test_phrase("end july") 
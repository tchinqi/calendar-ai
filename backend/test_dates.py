from nlp_utils import extract_parameters
from datetime import datetime
from zoneinfo import ZoneInfo

def test_prompt(prompt):
    print(f"\nTesting prompt: '{prompt}'")
    params = extract_parameters(prompt)
    print(f"Start:    {params['start']}")
    print(f"End:      {params['end']}")
    print(f"Duration: {params['duration']} minutes")
    print(f"Hours:    {params['earliest']}:00 - {params['latest']}:00")
    print(f"Count:    {params['count']} slots")
    return params

# Test various prompts
test_prompt("Find me a 30 minute slot next week")
test_prompt("Find me a slot tomorrow morning")
test_prompt("I need a 45 minute slot after 2pm today")
test_prompt("2 hour meeting next Monday") 
import subprocess
from datetime import date, datetime, timedelta

FIELD_SEP = "\x1f"
RECORD_SEP = "\x1e"
TIMEOUT_SECONDS = 30

PERMISSION_MESSAGE = (
    "Calendar access isn't allowed yet. Allow it when macOS asks "
    "(or in System Settings → Privacy & Security → Automation)."
)
TIMEOUT_MESSAGE = "Calendar didn't respond in time. If macOS asked for permission, allow it and try again."

SCRIPT = """
on pad(n)
    if n < 10 then return "0" & n
    return n as text
end pad

on stamp(d)
    return (year of d as text) & "-" & my pad(month of d as integer) & "-" & my pad(day of d) & "T" & my pad(hours of d) & ":" & my pad(minutes of d)
end stamp

set fieldSep to character id 31
set recordSep to character id 30
set startOfToday to current date
set time of startOfToday to 0
set endOfTomorrow to startOfToday + (2 * days)
set output to {}
tell application "Calendar"
    repeat with cal in calendars
        set calName to name of cal
        set matches to (every event of cal whose start date >= startOfToday and start date < endOfTomorrow)
        repeat with ev in matches
            set evTitle to summary of ev
            if evTitle is missing value then set evTitle to "Untitled event"
            set end of output to evTitle & fieldSep & my stamp(start date of ev) & fieldSep & (allday event of ev as text) & fieldSep & calName
        end repeat
    end repeat
end tell
set AppleScript's text item delimiters to recordSep
return output as text
"""


class CalendarAccessError(Exception):
    pass


def run_script():
    try:
        result = subprocess.run(
            ["osascript", "-"], input=SCRIPT, capture_output=True, text=True, timeout=TIMEOUT_SECONDS,
        )
    except FileNotFoundError:
        raise CalendarAccessError("Calendar reading needs macOS (osascript wasn't found).")
    except subprocess.TimeoutExpired:
        raise CalendarAccessError(TIMEOUT_MESSAGE)
    if result.returncode != 0:
        error = result.stderr.strip()
        if "-1743" in error or "Not authorized" in error or "not allowed" in error.lower():
            raise CalendarAccessError(PERMISSION_MESSAGE)
        if "-1712" in error:
            raise CalendarAccessError(TIMEOUT_MESSAGE)
        detail = error.splitlines()[-1] if error else f"exit code {result.returncode}"
        raise CalendarAccessError(f"Couldn't read Calendar: {detail}")
    return result.stdout.rstrip("\n")


def parse_events(raw):
    events = []
    for record in raw.split(RECORD_SEP) if raw else []:
        fields = record.split(FIELD_SEP)
        if len(fields) != 4:
            continue
        title, start, all_day, calendar = fields
        try:
            start = datetime.strptime(start, "%Y-%m-%dT%H:%M")
        except ValueError:
            continue
        events.append({
            "title": " ".join(title.split()) or "Untitled event",
            "start": start,
            "all_day": all_day.strip().lower() == "true",
            "calendar": calendar,
        })
    return sorted(events, key=lambda event: (event["start"].date(), not event["all_day"], event["start"]))


def fetch_events():
    return parse_events(run_script())


def events_on(events, day):
    return [event for event in events if event["start"].date() == day]


def todays_events(events):
    return events_on(events, date.today())


def tomorrows_events(events):
    return events_on(events, date.today() + timedelta(days=1))


def format_time(event):
    return "all day" if event["all_day"] else event["start"].strftime("%-I:%M %p")


if __name__ == "__main__":
    try:
        events = fetch_events()
    except CalendarAccessError as e:
        print(e)
        raise SystemExit(1)
    for label, day_events in (("Today", todays_events(events)), ("Tomorrow", tomorrows_events(events))):
        print(f"{label}:")
        for event in day_events or []:
            print(f"  {format_time(event):>8}  {event['title']}  ({event['calendar']})")
        if not day_events:
            print("  nothing scheduled")

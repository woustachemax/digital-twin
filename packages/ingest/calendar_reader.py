import threading
from datetime import date, datetime, time, timedelta

PERMISSION_TIMEOUT_SECONDS = 60

PERMISSION_MESSAGE = (
    "Calendar access isn't allowed yet. Allow it when macOS asks "
    "(or in System Settings → Privacy & Security → Calendars)."
)
WRITE_ONLY_MESSAGE = (
    "I can only add calendar events right now, not read them. Switch me to Full Access in "
    "System Settings → Privacy & Security → Calendars."
)
TIMEOUT_MESSAGE = "macOS is still waiting for you to allow calendar access. Allow it when it asks, then try again."
UNAVAILABLE_MESSAGE = "Calendar reading needs pyobjc-framework-EventKit (pip install pyobjc-framework-EventKit)."


class CalendarAccessError(Exception):
    pass


def load_eventkit():
    try:
        import EventKit
        from Foundation import NSDate
    except ImportError:
        raise CalendarAccessError(UNAVAILABLE_MESSAGE)
    return EventKit, NSDate


def request_access(EventKit, store):
    granted = {}
    done = threading.Event()

    def completion(ok, error):
        granted["ok"] = bool(ok)
        done.set()

    if hasattr(store, "requestFullAccessToEventsWithCompletion_"):
        store.requestFullAccessToEventsWithCompletion_(completion)
    else:
        store.requestAccessToEntityType_completion_(EventKit.EKEntityTypeEvent, completion)
    if not done.wait(PERMISSION_TIMEOUT_SECONDS):
        raise CalendarAccessError(TIMEOUT_MESSAGE)
    return granted.get("ok", False)


def ensure_access(EventKit, store, allow_prompt=False):
    status = EventKit.EKEventStore.authorizationStatusForEntityType_(EventKit.EKEntityTypeEvent)
    if status == EventKit.EKAuthorizationStatusFullAccess:
        return
    if status == EventKit.EKAuthorizationStatusNotDetermined and allow_prompt and request_access(EventKit, store):
        return
    if status == EventKit.EKAuthorizationStatusWriteOnly:
        raise CalendarAccessError(WRITE_ONLY_MESSAGE)
    raise CalendarAccessError(PERMISSION_MESSAGE)


def to_datetime(nsdate):
    return datetime.fromtimestamp(nsdate.timeIntervalSince1970())


def convert_events(ek_events, range_start):
    events = []
    for event in ek_events or []:
        start_date = event.startDate()
        if start_date is None:
            continue
        start = to_datetime(start_date)
        all_day = bool(event.isAllDay())
        if all_day and start < range_start:
            start = range_start
        calendar = event.calendar()
        events.append({
            "title": " ".join((event.title() or "").split()) or "Untitled event",
            "start": start,
            "all_day": all_day,
            "calendar": calendar.title() if calendar is not None else "",
        })
    return sorted(events, key=lambda e: (e["start"].date(), not e["all_day"], e["start"]))


def request_permission():
    EventKit, _ = load_eventkit()
    ensure_access(EventKit, EventKit.EKEventStore.alloc().init(), allow_prompt=True)


def fetch_events(allow_prompt=False):
    EventKit, NSDate = load_eventkit()
    store = EventKit.EKEventStore.alloc().init()
    ensure_access(EventKit, store, allow_prompt)
    range_start = datetime.combine(date.today(), time.min)
    range_end = range_start + timedelta(days=2)
    predicate = store.predicateForEventsWithStartDate_endDate_calendars_(
        NSDate.dateWithTimeIntervalSince1970_(range_start.timestamp()),
        NSDate.dateWithTimeIntervalSince1970_(range_end.timestamp()),
        None,
    )
    return convert_events(store.eventsMatchingPredicate_(predicate), range_start)


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
        events = fetch_events(allow_prompt=True)
    except CalendarAccessError as e:
        print(e)
        raise SystemExit(1)
    for label, day_events in (("Today", todays_events(events)), ("Tomorrow", tomorrows_events(events))):
        print(f"{label}:")
        for event in day_events:
            print(f"  {format_time(event):>8}  {event['title']}  ({event['calendar']})")
        if not day_events:
            print("  nothing scheduled")

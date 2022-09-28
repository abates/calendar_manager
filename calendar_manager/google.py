#!/usr/bin/env python3

import datetime
import json

import os.path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

import typing

from .calendar import Calendar, Event, EventFilter, LOCAL_TIMEZONE

# If modifying these scopes, delete the file token.json.
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/calendar",
]


MAX_PER_PAGE=100

def _decode_date(data):
    if "dateTime" in data:
        return datetime.datetime.fromisoformat(data["dateTime"]), False
    elif "date" in data:
        date = datetime.datetime.fromisoformat(data["date"])
        date = datetime.datetime(date.year, date.month, date.day, tzinfo=LOCAL_TIMEZONE)
        return date, True
    raise ValueError("Invalid data for date")

def _encode_date(start:datetime.datetime, end:datetime.datetime, all_day:bool):
    if all_day:
        start = {"date": start.strftime("%Y-%m-%d")}
        end = {"date": end.strftime("%Y-%m-%d")}
    else:
        start = {"dateTime": start.isoformat()}
        end = {"dateTime": end.isoformat()}

    return start, end

class GoogleClient:
    METADATA_HEADER = "## BEGIN METADATA"

    class CalendarAdapter(Calendar):
        class Event(Event):
            def __post_init__(self):
                self._body = {}

            @classmethod
            def from_body(cls, body):
                description = ""
                metadata = {}
                lines = body.get("description", "").split("\n")
                for i, line in enumerate(lines):
                    if line == GoogleClient.METADATA_HEADER:
                        metadata = json.loads("\n".join(lines[i+1:]))
                        break
                    description += line + "\n"

                start, all_day = _decode_date(body["start"])
                end, _ = _decode_date(body["end"])
                event = cls(
                    id=body["id"],
                    title=body["summary"],
                    start=start,
                    end=end,
                    all_day=all_day,
                    description=description.rstrip(),
                    metadata=metadata
                )
                event._body = body
                return event
            
            def encode(self):
                start, end = _encode_date(self.start, self.end, self.all_day)
                description = self.description
                if self.metadata:
                    description += "\n" + GoogleClient.METADATA_HEADER + "\n" + json.dumps(self.metadata)

                body = {
                    "start": start,
                    "end": end,
                    "summary": self.title,
                    "description": description,
                }
                return body

        def __init__(self, metadata, events_service):
            self._id = metadata["id"]
            self.metadata = metadata
            self.service = events_service

        @property
        def id(self) -> str:
            return self._id

        def events(self, event_filter:EventFilter = None):
            if event_filter is None:
                event_filter = EventFilter()

            start = event_filter.start
            if start is None:
                start = datetime.datetime(datetime.MINYEAR, 1, 1, tzinfo=datetime.timezone.utc)
            
            end = event_filter.end
            if end is None:
                end = datetime.datetime(datetime.MAXYEAR, 12, 31, tzinfo=datetime.timezone.utc)

            if start.tzinfo is None or end.tzinfo is None:
                raise ValueError("Timezone is required for both start and end times")

            def iterate_results():
                for event in GoogleClient.iterate_results(
                    self.service.list, 
                    calendarId=self.id,
                    timeMin=start.isoformat(),
                    timeMax=end.isoformat(),
                    showDeleted=False,
                    singleEvents=True,
                    orderBy="startTime",
                    ):
                    if event["status"] in ["confirmed", "tenative"]:
                        yield self.Event.from_body(event)
            return filter(event_filter, iterate_results())

        def create_event(self, **kwargs):
            return GoogleClient.CalendarAdapter.Event(**kwargs)

        def save_event(self, event):
            if event.id:
                self.update_event(event)
            else:
                self.add_event(event)

        def update_event(self, event):
            self.service.update(
                calendarId=self.id,
                eventId=event.id,
                body=event.encode()
            ).execute()

        def add_event(self, event):
            event._body = self.service.insert(
                calendarId=self.id,
                body=event.encode(),
            ).execute()
            event.id = event._body["id"]

        def delete_event(self, id: str) -> None:
            resp = self.service.delete(
                calendarId=self.id,
                eventId=id,
            ).execute()

        def get_event(self, id):
            return self.Event.from_body(self.service.get(calendarId=self.id, eventId=id).execute())

    @staticmethod
    def iterate_results(resource, **kwargs):
        result = resource(**kwargs).execute()
        while result is not None:
            for r in result["items"]:
                yield r
            
            if "nextPageToken" in result:
                result = resource(pageToken=result["nextPageToken"], **kwargs).execute()
            else:
                result = None

    def __init__(self, token_file, credentials_file):
        # If there are no (valid) credentials available, let the user log in.
        creds = None
        if os.path.exists(token_file):
            creds = Credentials.from_authorized_user_file(token_file, SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not path.exists(credentials_file):
                    raise ValueError(
                        "Missing crednetials file. Create a credentials file on the "
                        "Google dashboard and download it to " + credentials_file
                    )

                flow = InstalledAppFlow.from_client_secrets_file(credentials_file, SCOPES)
                creds = flow.run_local_server(port=0)
            # Save the credentials for the next run
            with open(token_file, 'w') as token:
                token.write(creds.to_json())

        self.mail = build('gmail', 'v1', credentials=creds)

        self._calendars = {}
        self.cal = build('calendar', 'v3', credentials=creds)

    def get_calendars(self) -> typing.Iterable[Calendar]:
        for metadata in GoogleClient.iterate_results(self.cal.calendarList().list):
            if metadata["summary"] not in self._calendars:
                adapter = GoogleClient.CalendarAdapter(self.cal.calendars().get(calendarId=metadata["id"]))
                self._calendars[metadata["summary"]] = adapter
            yield self._calendars[metadata["summary"]]

    def get_calendar(self, name:str) -> "Calendar":
        if name not in self._calendars:
            resource = self.cal.calendarList().list
            for metadata in GoogleClient.iterate_results(resource):
                cal_name = metadata["summary"]
                if cal_name not in self._calendars:
                    adapter = GoogleClient.CalendarAdapter(metadata, self.cal.events())
                    self._calendars[cal_name] = adapter

        return self._calendars[name]

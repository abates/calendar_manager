

from abc import ABC, abstractmethod
from dataclasses import dataclass, fields, field
import datetime
from enum import IntEnum
from typing import  Any, Iterator, List

LOCAL_TIMEZONE = datetime.datetime.now().astimezone().tzinfo

Weekday = IntEnum('Weekdays', 'sunday monday tuesday wednesday thursday friday saturday', start=0)

@dataclass
class Event:
    id:str
    title:str
    start:datetime.datetime
    end:datetime.datetime
    all_day:bool = False
    description:str = ""
    metadata:dict = field(default_factory=dict)

    def matches(self, other:"Event"):
        return self.title == other.title and self.start == other.start and self.end == other.end

    def update(self, **kwargs):
        for name, value in kwargs.items():
            setattr(self, name, value)

    def __iter__(self):
        for field in fields(self):
            yield (field.name, getattr(self, field.name))

    def __str__(self):
        output = f"{self.title}\n"
        if self.all_day:
            fmt = "%b %d, %Y"
            output += f"{self.start.strftime(fmt)} - All Day Event"
        else:
            fmt = "%b %d, %Y %I:%M%p"
            output += f"Start: {self.start.strftime(fmt)} End: {self.end.strftime(fmt)}\n"

        for line in self.description.split("\n"):
            output += f"    {line}\n"
        output += "\n"
        return output

@dataclass
class EventFilter:
    src_calendar:str = None
    start:datetime.datetime = None
    end:datetime.datetime = None
    weekday:Weekday = None

    def __call__(self, event:Event) -> bool:
        return all([
            (not self.start or self.start <= event.start),
            (not self.end or event.end <= self.end),
            (not self.weekday or self.weekday == event.start.weekday),
            (not self.src_calendar or event.metadata.get("src_calendar", None) == self.src_calendar),
        ])

@dataclass
class SyncConfig:
    src_calendar:str
    title:str = None
    sync_start:datetime.datetime = None
    start_time:datetime.time = None
    start_offset:datetime.timedelta = None
    sync_end:datetime.datetime = None
    end_time:datetime.time = None
    end_offset:datetime.timedelta = None

class Calendar(ABC):
    @property
    @abstractmethod
    def id(self) -> str:
        pass

    @abstractmethod
    def events(self, event_filter:EventFilter = None) -> Iterator[Event]:
        pass

    @abstractmethod
    def add_event(self, event:Event) -> None:
        pass

    @abstractmethod
    def get_event(self, id:Any) -> Event:
        pass

    @abstractmethod
    def create_event(self, **kwargs) -> Event:
        pass

    @abstractmethod
    def update_event(self, event:Event) -> None:
        pass

    @abstractmethod
    def delete_event(self, id:str) -> None:
        pass

    def has_event(self, search:Event):
        start = datetime.datetime(search.start.year, search.start.month, search.start.day, tzinfo=search.start.tzinfo)
        end = start.replace(hour=23, minute=59)
        events:Iterator[Event] = self.events(EventFilter(start=start, end=end))
        for event in events:
            if event.matches(search):
                return True
        return False

    def sync_from(self, src_events:List[Event], config:SyncConfig):
        existing_ids = {}
        duplicates = []
        for event in self.events(EventFilter(
            start=config.sync_start if config.sync_start else datetime.datetime.utcnow().astimezone(), 
            end=(config.sync_end if config.sync_end else datetime.datetime.utcnow().astimezone() + datetime.timedelta(days=30)),
            src_calendar=config.src_calendar
        )):
            if event.metadata.get("src_id") in existing_ids:
                duplicates.append(event.id)
            else:
                existing_ids[event.metadata.get("src_id")] = event.id

        for event in src_events:
            details = dict(event)
            details.pop("id")

            if config.title:
                details["title"] = config.title
            
            if config.start_time:
                # TODO: set the time, don't replace the whole thing
                details["start"] = event.start.replace(hour=config.start_time.hour, minute=config.start_time.minute)
            
            if config.start_offset:
                details["start"] = details["start"] + config.start_offset

            if config.end_time:
                # TODO: set the time, don't replace the whole thing
                details["end"] = event.end.replace(hour=config.end_time.hour, minute=config.end_time.minute)
            
            if config.end_offset:
                details["end"] = details["end"] + config.end_offset

            details["metadata"] = {
                "src_calendar": config.src_calendar,
                "src_id": event.id
            }

            if event.id in existing_ids:
                event = self.get_event(existing_ids.pop(event.id))
                event.update(**details)
                self.update_event(event)
            else:
                details["id"] = None
                event = self.create_event(**details)
                if not self.has_event(event):
                    self.add_event(event)

        if existing_ids:
            for id in existing_ids.values():
                self.delete_event(id)

        if duplicates:
            for id in duplicates:
                self.delete_event(id)
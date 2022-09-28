from typing import Callable, Iterator
from .calendar import Calendar, Event, EventFilter

class StaticCalendar(Calendar):
    def __init__(self, id:str, events:Iterator[Event]):
        self._id = id
        self._events = {event.id: event for event in events}

    @property
    def id(self) -> str:
        return self._id

    def events(self, event_filter:EventFilter=None) -> Iterator[Event]:
        if event_filter is None:
            event_filter = EventFilter()

        return filter(event_filter, self._events.values())

    def add_event(self, event:Event) -> None:
        raise NotImplemented("StaticCalendars cannot be modified")

    def get_event(self, id:str) -> Event:
        return self._events[id]

    def create_event(self, **kwargs) -> Event:
        raise NotImplemented("StaticCalendars cannot be modified")

    def update_event(self, event:Event) -> None:
        raise NotImplemented("StaticCalendars cannot be modified")

    def delete_event(self, id:str) -> None:
        raise NotImplemented("StaticCalendars cannot be modified")

class WebpageCalendar(StaticCalendar):
    def __init__(self, url:str, table_selector:str, row_parser:Callable=None, row_map:dict=None):
        self.url = url
        self.table_selector = table_selector
        self.row_parser = row_parser
        self.row_map = row_map
        self._last_id = 0
        events = self.scrape()

        super().__init__(url, events)

    def scrape(self):
        try:
            import requests
            from bs4 import BeautifulSoup
        except ImportError as ex:
            raise ImportError("Both BeautifulSoup and requests are required to use the WebpageCalendar") from ex
        
        events = []
        html = requests.get(self.url).text
        document = BeautifulSoup(html, 'html.parser')

        table = document.select_one(self.table_selector)
        for row in table.find_all("tr"):
            cells = [cell.text for cell in row.find_all("td")]
            if cells:
                fields = {}
                if self.row_parser:
                    fields = self.row_parser(cells)
                else:
                    for field, value in self.row_map.items():
                        if isinstance(value, int):
                            fields[field] = cells[value]
                        elif callable(value):
                            fields[field] = value(cells)
                        else:
                            raise ValueError(f"Can't handle field {field} row_map must be a mapping of fields to integers or callables")
                fields["id"] = f"{self.url}:{self._last_id}"
                self._last_id += 1
                events.append(Event(**fields))
        return events


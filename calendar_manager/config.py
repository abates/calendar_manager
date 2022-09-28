import appdirs
from os import path, makedirs

from .google import GoogleClient

from . import APP_NAME

class Config:
    __instance : "Config" = None

    @classmethod
    def get(cls) -> "Config":
        if Config.__instance:
            return Config.__instance
        return Config()

    def __new__(cls) -> "Config":
        if not Config.__instance:
            instance = object.__new__(Config)
            instance.__init__()
            Config.__instance = instance
        return Config.__instance

    def __init__(self):
        if Config.__instance:
            return

        self._dir = appdirs.user_data_dir(APP_NAME)

        if not path.exists(self._dir):
            makedirs(self._dir)
        
        self.credentials_file = path.join(self._dir, "credentials.json")
        self.token_file = path.join(self._dir, "token.json")
        self.client = GoogleClient(self.token_file, self.credentials_file)

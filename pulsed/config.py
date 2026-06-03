
import json 
import os

_STORAGE: dict = {}
def _init():
    config = {"port": {}}
    if os.path.exists("config.json"):
        try:
            with open("config.json", "r") as file:
                config = json.load(file)
        except json.JSONDecodeError:
                #config = {"port": {}}
                pass
    global _STORAGE
    _STORAGE = config

_init()
def get_storage():
    global _STORAGE
    return _STORAGE

def dump_to_file(file_name: str = "config.json"):
    with open(file_name, 'w') as f:
        json.dump(_STORAGE, f, indent=4)


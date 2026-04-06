import base64
import binascii
import json
import os


class AIHubConfig:

    CONFIG_PATH = os.path.expanduser("~/.aihubkr-cli/config.json")
    _instance = None

    @staticmethod
    def get_instance():
        if AIHubConfig._instance is None:
            AIHubConfig._instance = AIHubConfig()
            AIHubConfig._instance.load_from_disk()
        return AIHubConfig._instance

    def __init__(self):
        self.config_db = {}

    def load_from_disk(self) -> bool:
        if self != AIHubConfig._instance:
            raise RuntimeError("Singleton class. Use get_instance() instead.")

        if not os.path.exists(AIHubConfig.CONFIG_PATH):
            self.config_db = {}
            return True

        try:
            with open(AIHubConfig.CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)

            self.config_db = {}
            for key in data.keys():
                self.config_db[key] = base64.b64decode(data.get(key)).decode()
            return True
        except (FileNotFoundError, json.JSONDecodeError, binascii.Error, UnicodeDecodeError):
            self.config_db = {}
            return False

    def save_to_disk(self) -> None:
        if self != AIHubConfig._instance:
            raise RuntimeError("Singleton class. Use get_instance() instead.")

        os.makedirs(os.path.dirname(AIHubConfig.CONFIG_PATH), exist_ok=True)

        save_config = {}
        for key in self.config_db.keys():
            save_config[key] = base64.b64encode(
                self.config_db.get(key).encode()
            ).decode()

        with open(AIHubConfig.CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(save_config, f)

    def clear(self, save: bool = True) -> None:
        if self != AIHubConfig._instance:
            raise RuntimeError("Singleton class. Use get_instance() instead.")

        if save and os.path.exists(AIHubConfig.CONFIG_PATH):
            os.remove(AIHubConfig.CONFIG_PATH)
        self.config_db = {}

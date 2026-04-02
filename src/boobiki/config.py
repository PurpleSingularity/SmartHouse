from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_prefix": "BOOBIKI_"}

    host: str = "0.0.0.0"
    port: int = 8000
    device_name: str = ""
    data_dir: str = "./data"
    fast_transfer_ttl_hours: int = 6
    fast_transfer_dir: str = "./fast_transfer_storage"
    storage_dir: str = "./storage"
    mdns_service_type: str = "_boobiki._tcp.local."

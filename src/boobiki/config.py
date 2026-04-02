import logging
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ec import SECP256R1, generate_private_key
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)
from py_vapid import b64urlencode
from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)


def load_or_generate_vapid(data_dir: str) -> tuple[str, str]:
    """Return (private_key_pem_path, public_key_b64url).

    Generates ECDSA P-256 keys on first run. Saves private key as PEM file
    so pywebpush can load it via Vapid.from_file().
    """
    data_path = Path(data_dir)
    pem_path = data_path / "vapid_private.pem"
    pub_path = data_path / "vapid_public.txt"

    if pem_path.exists() and pub_path.exists():
        pub_b64 = pub_path.read_text(encoding="utf-8").strip()
        return str(pem_path), pub_b64

    data_path.mkdir(parents=True, exist_ok=True)
    private_key = generate_private_key(SECP256R1())
    pem_bytes = private_key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption())
    pem_path.write_bytes(pem_bytes)

    public_bytes = private_key.public_key().public_bytes(
        Encoding.X962, PublicFormat.UncompressedPoint
    )
    pub_b64 = b64urlencode(public_bytes)
    pub_path.write_text(pub_b64, encoding="utf-8")

    logger.info("Generated new VAPID key pair in %s", data_path)
    return str(pem_path), pub_b64


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
    vapid_email: str = "boobiki@localhost"
    vapid_private_key: str = ""
    vapid_public_key: str = ""

import os
import secrets
import stat

import yaml
from yaml.loader import SafeLoader
import streamlit_authenticator as stauth

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

AUTH_CONFIG_PATH = os.getenv("PSR_AUTH_CONFIG", os.path.join(BASE_DIR, "auth.yaml"))
DEFAULT_USERNAME = os.getenv("PSR_AUTH_USERNAME", "admin")
DEFAULT_COOKIE_NAME = os.getenv("PSR_COOKIE_NAME", "psr_auth")
DEFAULT_COOKIE_EXPIRY_DAYS = float(os.getenv("PSR_COOKIE_EXPIRY_DAYS", "30"))


def _chmod_600(path: str) -> None:
    try:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    except Exception:
        pass


def load_auth_config() -> dict:
    if not os.path.exists(AUTH_CONFIG_PATH):
        return {}
    with open(AUTH_CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.load(f, Loader=SafeLoader) or {}


def ensure_auth_config() -> dict:
    """
    Single-User Auth:
    - nutzt GUI_PASSWORD aus .env als Initial-Passwort
    - schreibt beim ersten Start eine auth.yaml mit gehashtem Passwort + Cookie-Key
    """
    cfg = load_auth_config()
    if cfg.get("credentials") and cfg.get("cookie"):
        return cfg

    password = os.getenv("GUI_PASSWORD")
    if not password:
        raise RuntimeError("GUI_PASSWORD ist nicht gesetzt (in .env oder als Environment Variable).")

    cookie_key = os.getenv("PSR_COOKIE_KEY") or secrets.token_urlsafe(32)

    cfg = {
        "cookie": {"expiry_days": DEFAULT_COOKIE_EXPIRY_DAYS, "key": cookie_key, "name": DEFAULT_COOKIE_NAME},
        "credentials": {
            "usernames": {
                DEFAULT_USERNAME: {
                    "email": "",
                    "first_name": "Plex",
                    "last_name": "User",
                    "password": password,  # wird gleich gehasht
                }
            }
        },
    }

    # pre-hash (damit nichts im Klartext gespeichert bleibt)
    stauth.Hasher.hash_passwords(cfg["credentials"])

    with open(AUTH_CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.dump(cfg, f, default_flow_style=False, allow_unicode=True)

    _chmod_600(AUTH_CONFIG_PATH)
    return cfg

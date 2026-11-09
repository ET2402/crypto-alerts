"""Berichten versturen via een Telegram-bot."""
import os
import requests

TOKEN = os.environ.get("TELEGRAM_TOKEN", "").strip()
DRY_RUN = os.environ.get("DRY_RUN") == "1"


def _api(method, **params):
    r = requests.post(f"https://api.telegram.org/bot{TOKEN}/{method}", data=params, timeout=30)
    r.raise_for_status()
    return r.json()


def resolve_chat_id(state):
    """Chat-ID uit secret, uit state, of uit het eerste bericht dat je de bot stuurde."""
    cid = os.environ.get("TELEGRAM_CHAT_ID", "").strip() or state.get("chat_id")
    if cid or DRY_RUN:
        return cid
    if not TOKEN:
        raise RuntimeError("TELEGRAM_TOKEN ontbreekt: voeg het toe als Secret in GitHub.")
    upd = _api("getUpdates").get("result", [])
    for u in reversed(upd):
        msg = u.get("message") or u.get("channel_post")
        if msg:
            state["chat_id"] = str(msg["chat"]["id"])
            return state["chat_id"]
    raise RuntimeError("Geen chat gevonden: stuur eerst /start naar je bot in Telegram en start de run opnieuw.")


def send(state, text):
    if DRY_RUN or not TOKEN:
        print("---- TELEGRAM (niet verstuurd) ----\n" + text)
        return
    _api("sendMessage", chat_id=resolve_chat_id(state), text=text, disable_web_page_preview="true")

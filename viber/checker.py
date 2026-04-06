import time
from viber.bot_api import ViberBotAPI
from viber.utils import format_phone_number


class ViberChecker:
    """Checks phone numbers by sending contacts via the Viber Bot API."""

    def __init__(self, bot_api: ViberBotAPI):
        self.bot_api = bot_api
        self.from_id = None

    def setup(self) -> str:
        """Initialize: set webhook and retrieve own user ID. Returns the user ID."""
        wh = self.bot_api.set_webhook()
        if wh.get("status") != 0:
            raise RuntimeError(f"Webhook setup failed: {wh.get('status_message', wh)}")

        info = self.bot_api.get_account_info()
        if info.get("status") != 0:
            raise RuntimeError(f"get_account_info failed: {info.get('status_message', info)}")

        members = info.get("members", [])
        if not members:
            raise RuntimeError("No members found in account info")

        self.from_id = members[0]["id"]
        return self.from_id

    def check_numbers(self, phone_numbers: list, delay: float = 0.5) -> list:
        """
        Send each phone number as a contact to the channel.

        Returns list of dicts:
        [
            {"phone": "+1234...", "status": "sent"|"error", "detail": "...", "raw": {...}},
            ...
        ]

        NOTE: A "sent" status means the contact was posted to the channel.
        To determine if the number is actually on Viber, open the channel in Viber
        and check which contacts resolve as Viber users.
        """
        if not self.from_id:
            self.setup()

        results = []
        total = len(phone_numbers)

        for i, phone in enumerate(phone_numbers, 1):
            formatted = format_phone_number(phone)
            resp = self.bot_api.send_contact(self.from_id, formatted)

            status = "sent" if resp.get("status") == 0 else "error"
            detail = (
                resp.get("status_message", "ok")
                if status == "sent"
                else resp.get("status_message", "unknown error")
            )

            results.append({
                "phone": formatted,
                "status": status,
                "detail": detail,
                "message_token": resp.get("message_token", ""),
                "raw": resp,
            })

            if i < total:
                time.sleep(delay)

        return results

    def get_subscriber_details(self, subscriber_ids: list) -> list:
        """
        Fetch details (name, avatar, online status) for known subscriber IDs.
        Returns list of dicts with: id, name, avatar_url, online_status, online_status_text
        """
        # First get online status for all IDs
        online_data = {}
        if subscriber_ids:
            online_resp = self.bot_api.get_online(subscriber_ids)
            for user in online_resp.get("users", []):
                status_map = {0: "online", 1: "offline", 2: "undisclosed", 3: "error", 4: "not_a_member"}
                online_data[user["id"]] = {
                    "online_status": user.get("online_status", -1),
                    "online_status_text": status_map.get(user.get("online_status", -1), "unknown"),
                    "last_online": user.get("last_online", 0),
                }

        # Then get details for each
        results = []
        for uid in subscriber_ids:
            detail_resp = self.bot_api.get_user_details(uid)
            user = detail_resp.get("user", {})
            online = online_data.get(uid, {"online_status": -1, "online_status_text": "unknown", "last_online": 0})

            results.append({
                "id": uid,
                "name": user.get("name", ""),
                "avatar_url": user.get("avatar", ""),
                "country": user.get("country", ""),
                "language": user.get("language", ""),
                "api_version": user.get("api_version", 0),
                "online_status": online["online_status"],
                "online_status_text": online["online_status_text"],
                "last_online": online["last_online"],
            })
            time.sleep(0.3)

        return results

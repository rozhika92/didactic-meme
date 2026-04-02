import requests
import time


class ViberBotAPI:
    """Wrapper for the official Viber Bot/Channel REST API."""

    BASE_URL = "https://chatapi.viber.com/pa"

    def __init__(self, auth_token: str):
        self.auth_token = auth_token
        self.session = requests.Session()
        self.session.headers.update({"X-Viber-Auth-Token": auth_token})

    def _post(self, endpoint: str, payload: dict) -> dict:
        """Make a POST request to the Viber API with error handling."""
        payload["auth_token"] = self.auth_token
        try:
            resp = self.session.post(
                f"{self.BASE_URL}/{endpoint}", json=payload, timeout=10
            )
            resp.raise_for_status()
            return resp.json()
        except requests.Timeout:
            return {"status": -1, "status_message": "Request timed out"}
        except requests.ConnectionError:
            return {"status": -1, "status_message": "Connection error"}
        except requests.RequestException as e:
            return {"status": -1, "status_message": str(e)}

    def set_webhook(self, url: str = "https://httpbin.org/post", event_types: list = None) -> dict:
        """POST /set_webhook — Required on first use to activate the bot."""
        return self._post("set_webhook", {
            "url": url,
            "event_types": event_types or ["failed"],
            "send_name": False,
            "send_photo": False,
        })

    def get_account_info(self) -> dict:
        """POST /get_account_info — Returns account info including members list."""
        return self._post("get_account_info", {})

    def send_contact(self, from_id: str, phone_number: str, name: str = "contact") -> dict:
        """POST /post — Send a contact message to the channel."""
        return self._post("post", {
            "from": from_id,
            "type": "contact",
            "contact": {
                "name": name,
                "phone_number": phone_number,
            },
        })

    def get_online(self, ids: list) -> dict:
        """
        POST /get_online — Check online status of subscriber IDs.
        online_status values: 0=online, 1=offline, 2=undisclosed, 3=error, 4=not_a_member
        """
        return self._post("get_online", {"ids": ids})

    def get_user_details(self, user_id: str) -> dict:
        """
        POST /get_user_details — Get detailed info about a subscriber.
        Returns: name, avatar, id, country, language, api_version, etc.
        Only works for users who have subscribed to the bot.
        """
        return self._post("get_user_details", {"id": user_id})

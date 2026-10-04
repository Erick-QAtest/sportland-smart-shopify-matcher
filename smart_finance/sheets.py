from __future__ import annotations

from urllib.parse import quote


class GoogleSheetsReader:
    """Minimal read-only Google Sheets values reader.

    Uses the same service-account pattern already used by Sportland Smart.
    No writes are implemented by design.
    """

    SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]

    def __init__(self, spreadsheet_id: str, service_account_file: str):
        try:
            from google.auth.transport.requests import AuthorizedSession
            from google.oauth2.service_account import Credentials
        except ImportError as exc:
            raise RuntimeError(
                "Missing Google dependencies. Install requirements-finance.txt"
            ) from exc
        credentials = Credentials.from_service_account_file(
            service_account_file, scopes=self.SCOPES
        )
        self.session = AuthorizedSession(credentials)
        self.spreadsheet_id = spreadsheet_id

    def read(self, a1_range: str) -> list[list[str]]:
        encoded = quote(a1_range, safe="!:$'")
        url = (
            f"https://sheets.googleapis.com/v4/spreadsheets/{self.spreadsheet_id}"
            f"/values/{encoded}?majorDimension=ROWS&valueRenderOption=UNFORMATTED_VALUE"
        )
        response = self.session.get(url, timeout=30)
        response.raise_for_status()
        return response.json().get("values", [])

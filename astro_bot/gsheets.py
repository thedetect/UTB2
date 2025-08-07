from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Optional, List
from datetime import datetime

import gspread
from google.oauth2.service_account import Credentials

HEADERS = [
    "ID",
    "Имя",
    "Дата рождения",
    "Время рождения",
    "Место",
    "Дата регистрации",
    "Оплата",
    "Сумма",
    "Дата оплаты",
    "Реферальная ссылка",
    "Количество рефералов",
    "Оплатившие реф",
    "Количество выданных дней",
    "Платил",
]


@dataclass
class SheetConfig:
    spreadsheet_id: str
    credentials_path: Optional[str]
    credentials_json: Optional[str]
    worksheet_name: str = "Users"


class GoogleSheetClient:
    def __init__(self, cfg: SheetConfig):
        self.cfg = cfg
        self.client: Optional[gspread.Client] = None
        self.sheet = None

    def init(self) -> None:
        if not self.cfg.spreadsheet_id:
            return
        creds: Optional[Credentials] = None
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        if self.cfg.credentials_json:
            info = json.loads(self.cfg.credentials_json)
            creds = Credentials.from_service_account_info(info, scopes=scopes)
        elif self.cfg.credentials_path and os.path.exists(self.cfg.credentials_path):
            creds = Credentials.from_service_account_file(self.cfg.credentials_path, scopes=scopes)
        else:
            raise RuntimeError("Не заданы учетные данные Google Service Account")
        self.client = gspread.authorize(creds)
        doc = self.client.open_by_key(self.cfg.spreadsheet_id)
        try:
            self.sheet = doc.worksheet(self.cfg.worksheet_name)
        except gspread.WorksheetNotFound:
            self.sheet = doc.add_worksheet(title=self.cfg.worksheet_name, rows=100, cols=len(HEADERS))
        self._ensure_headers()

    def _ensure_headers(self) -> None:
        current = self.sheet.row_values(1)
        if current != HEADERS:
            self.sheet.update("A1", [HEADERS])

    def _find_row_index(self, user_id: int) -> Optional[int]:
        try:
            cell = self.sheet.find(str(user_id))
            return cell.row if cell.col == 1 else None
        except gspread.CellNotFound:
            return None

    @staticmethod
    def _fmt_date(iso_str: Optional[str]) -> str:
        if not iso_str:
            return ""
        try:
            dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
            return dt.strftime("%d.%m.%Y")
        except Exception:
            return iso_str

    def upsert_user(
        self,
        user_id: int,
        name: str,
        birth_date: str,
        birth_time: str,
        birth_place: str,
        created_at_iso: Optional[str],
        is_paid: bool,
        amount: Optional[float],
        paid_at: Optional[str],
        ref_link: str,
        referrals_count: int,
        paid_referrals_count: int,
        given_days: int,
        ever_paid: bool,
    ) -> None:
        if not self.sheet:
            return
        row = [
            str(user_id),
            name or "",
            birth_date or "",
            birth_time or "",
            birth_place or "",
            self._fmt_date(created_at_iso),
            "Да" if is_paid else "Нет",
            ("{:.2f}".format(amount) if amount else ""),
            self._fmt_date(paid_at),
            ref_link or "",
            str(referrals_count),
            str(paid_referrals_count),
            str(given_days),
            "Да" if ever_paid else "Нет",
        ]
        idx = self._find_row_index(user_id)
        if idx:
            self.sheet.update(f"A{idx}:N{idx}", [row])
        else:
            self.sheet.append_row(row, value_input_option="USER_ENTERED")
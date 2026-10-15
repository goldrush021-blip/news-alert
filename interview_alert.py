import os
import re
import sys
from datetime import datetime, timedelta, timezone

import requests

KST = timezone(timedelta(hours=9))

SHEET_ID = os.environ.get("SHEET_ID", "1TxbFMxaNSxPoMTzg21c-xSwzc5hObSrc7RC-w2Jw5_E")
TAB_NAME = "장원혁"
HEADER_SCAN_ROWS = 10

# 헤더명으로 컬럼을 찾고, 못 찾으면 열 문자(fallback)를 사용
INTERVIEW_HEADER = "1차 면접"
INTERVIEW_FALLBACK = "AI"
FIELDS = {
    "company": (["기업명", "업체", "회사"], "C"),
    "position": (["포지션명", "포지션"], "D"),
    "name": (["후보자명", "후보명", "이름", "성명"], "F"),
    "phone": (["연락처", "휴대폰", "핸드폰"], "K"),
}


def col_to_index(col):
    n = 0
    for ch in col.upper():
        n = n * 26 + ord(ch) - 64
    return n - 1


def parse_date(text, today):
    """'10/15(목)' -> date. 연도는 올해, 6개월 넘게 과거면 내년으로 본다."""
    m = re.search(r"(\d{1,2})\s*/\s*(\d{1,2})", text or "")
    if not m:
        return None
    month, day = int(m.group(1)), int(m.group(2))
    for year in (today.year, today.year + 1):
        try:
            d = datetime(year, month, day).date()
        except ValueError:
            return None
        if d >= today - timedelta(days=180):
            return d
    return None


def find_columns(rows):
    """(헤더 행 index, {field: 열 index}) 반환. 1차 면접 헤더가 있는 행을 헤더로 본다."""
    for r, row in enumerate(rows[:HEADER_SCAN_ROWS]):
        for c, cell in enumerate(row):
            if cell.replace(" ", "") == INTERVIEW_HEADER.replace(" ", ""):
                cols = {"interview": c}
                for field, (keywords, fallback) in FIELDS.items():
                    idx = next(
                        (i for i, h in enumerate(row) if any(k in h for k in keywords)),
                        col_to_index(fallback),
                    )
                    cols[field] = idx
                return r, cols
    # 헤더를 못 찾으면 열 문자로 대체
    cols = {"interview": col_to_index(INTERVIEW_FALLBACK)}
    for field, (_, fallback) in FIELDS.items():
        cols[field] = col_to_index(fallback)
    return 0, cols


def get(row, idx):
    return row[idx].strip() if idx < len(row) else ""


def collect(rows, target):
    header_row, cols = find_columns(rows)
    today = datetime.now(KST).date()
    found = []
    for row in rows[header_row + 1:]:
        d = parse_date(get(row, cols["interview"]), today)
        if d == target:
            found.append({f: get(row, cols[f]) for f in ("company", "position", "name", "phone")})
    return found


def build_message(label, target, items):
    wd = "월화수목금토일"[target.weekday()]
    lines = [f"📞 {label} 1차 면접 {len(items)}건 ({target.month}/{target.day}({wd}))", ""]
    lines.append("후보자에게 통화 + 문자 필요합니다.")
    lines.append("")
    for i, it in enumerate(items, 1):
        lines.append(f"[{i}] {it['name'] or '(이름 없음)'}  {it['phone']}")
        lines.append(f"    {it['company']} / {it['position']}")
    return "\n".join(lines)


def fetch_rows():
    from google.oauth2 import service_account
    from google.auth.transport.requests import AuthorizedSession
    import json

    info = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"])
    creds = service_account.Credentials.from_service_account_info(
        info, scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"]
    )
    session = AuthorizedSession(creds)
    rng = requests.utils.quote(f"'{TAB_NAME}'!A1:AZ3000", safe="")
    r = session.get(
        f"https://sheets.googleapis.com/v4/spreadsheets/{SHEET_ID}/values/{rng}",
        params={"valueRenderOption": "FORMATTED_VALUE"},
        timeout=30,
    )
    r.raise_for_status()
    return r.json().get("values", [])


def find_chat_id(token):
    """TELEGRAM_CHAT_ID가 없으면 봇에게 마지막으로 온 메시지의 chat id를 사용."""
    r = requests.get(f"https://api.telegram.org/bot{token}/getUpdates", timeout=10)
    r.raise_for_status()
    for upd in reversed(r.json().get("result", [])):
        chat = (upd.get("message") or {}).get("chat")
        if chat:
            return str(chat["id"])
    raise RuntimeError("chat id를 찾을 수 없습니다. 봇에게 먼저 메시지를 보내세요.")


def send_telegram(text):
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ.get("TELEGRAM_CHAT_ID") or find_chat_id(token)
    r = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data={"chat_id": chat_id, "text": text, "disable_web_page_preview": True},
        timeout=10,
    )
    r.raise_for_status()


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "today"  # eve | today
    now = datetime.now(KST).date()
    if mode == "eve":
        target, label = now + timedelta(days=1), "내일"
    else:
        target, label = now, "오늘"
    items = collect(fetch_rows(), target)
    print(f"{mode}: {target} 면접 {len(items)}건")
    if items:
        send_telegram(build_message(label, target, items))
        print("텔레그램 전송 완료")


if __name__ == "__main__":
    main()

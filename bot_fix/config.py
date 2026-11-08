import os
from pathlib import Path
from dotenv import load_dotenv

# 이 파일과 같은 폴더의 .env 를 항상 사용하고, 윈도우 환경변수보다 .env 값을 우선한다
CONFIG_DIR = str(Path(__file__).resolve().parent)
load_dotenv(Path(CONFIG_DIR) / ".env", override=True)

# Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
ALLOWED_USER_IDS = [int(x) for x in os.getenv("ALLOWED_USER_IDS", "").split(",") if x.strip()]

# SMTP (변수 이름은 기존 HIWORKS_* 를 그대로 사용 — 값만 구글로 바꾸면 된다)
HIWORKS_EMAIL = os.getenv("HIWORKS_EMAIL", "")
HIWORKS_PASSWORD = os.getenv("HIWORKS_PASSWORD", "")
HIWORKS_SMTP_HOST = os.getenv("HIWORKS_SMTP_HOST", "smtp.hiworks.com")
HIWORKS_SMTP_PORT = int(os.getenv("HIWORKS_SMTP_PORT", "465"))

# Hiworks 주소록 API (GroupWare)
HIWORKS_COMPANY_ID = os.getenv("HIWORKS_COMPANY_ID", "")
HIWORKS_API_KEY = os.getenv("HIWORKS_API_KEY", "")

# Claude API
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# 발신자 정보
SENDER_NAME = os.getenv("SENDER_NAME", "장원혁")
SENDER_EMAIL = HIWORKS_EMAIL

# 회사소개서 PDF 경로
PDF_PATH = os.getenv("PDF_PATH", r"C:\Users\wonbong\Desktop\재문 순재 영상 및 자료\업사이드 자료\업사이드\업사이드ｖ１회사소개서.pdf")

# 데이터베이스
DB_PATH = os.getenv("DB_PATH", "contacts.db")

# vCard 저장 폴더 (리멤버 임포트용)
VCARD_EXPORT_DIR = os.getenv("VCARD_EXPORT_DIR", "vcards")

# 폴링 간격 (초)
POLL_INTERVAL_SECONDS = 300  # 5분

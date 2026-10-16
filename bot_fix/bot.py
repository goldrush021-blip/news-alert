"""
업사이드 명함 자동화 텔레그램 봇
- 명함 사진 수신 → Claude Vision OCR → 하이웍스 이메일 발송 + PDF 첨부
- 하이웍스 주소록 자동 등록 (담당자 이름 + 회사명 한글)
- 리멤버용 vCard 자동 생성
- 5분마다 미처리 명함 재처리
"""
import os
import json
import time
import logging
import asyncio
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)

from config import TELEGRAM_BOT_TOKEN, ALLOWED_USER_IDS, POLL_INTERVAL_SECONDS
from card_ocr import extract_contact_from_image, format_contact_summary
from email_sender import send_company_intro_email
from contact_manager import add_to_hiworks_contacts, export_vcard
from database import (
    init_db, save_contact, mark_email_sent,
    mark_hiworks_synced, mark_vcard_exported,
    get_pending_email, get_pending_hiworks, get_contact_by_id
)

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
    handlers=[
        logging.FileHandler("bot.log", encoding="utf-8"),
        logging.StreamHandler(),
    ]
)
log = logging.getLogger(__name__)

CARD_DIR = "card_images"
os.makedirs(CARD_DIR, exist_ok=True)

# 임시 OCR 결과 저장 (confirm 대기용)
pending_contacts: dict[int, dict] = {}


# 최근 발송한 주소 기록 (중복 발송 방지, 파일에 저장해서 재시작해도 유지)
SENT_LOG = "sent_recent.json"
DUP_WINDOW_SECONDS = 24 * 3600


def _load_sent() -> dict:
    try:
        with open(SENT_LOG, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _already_sent(email: str) -> bool:
    ts = _load_sent().get(email.strip().lower())
    return bool(ts) and (time.time() - ts) < DUP_WINDOW_SECONDS


def _record_sent(email: str):
    data = _load_sent()
    now = time.time()
    data = {k: v for k, v in data.items() if now - v < DUP_WINDOW_SECONDS}
    data[email.strip().lower()] = now
    with open(SENT_LOG, "w", encoding="utf-8") as f:
        json.dump(data, f)


def is_allowed(user_id: int) -> bool:
    if not ALLOWED_USER_IDS:
        return True
    return user_id in ALLOWED_USER_IDS


# ─── 명령어 핸들러 ─────────────────────────────────────────────────────────────

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id):
        return
    await update.message.reply_text(
        "👋 업사이드 명함 자동화 봇입니다.\n\n"
        "📌 사용법\n"
        "1. 명함 사진을 전송하면 OCR로 연락처를 추출합니다.\n"
        "2. 내용 확인 후 이메일 발송 여부를 선택하세요.\n"
        "3. 하이웍스 주소록에 자동으로 등록됩니다.\n"
        "4. 리멤버용 vCard 파일도 자동 생성됩니다.\n\n"
        "📋 명령어\n"
        "/start - 시작\n"
        "/list  - 저장된 연락처 목록\n"
        "/send  - 직접 이메일 발송 (이름 | 이메일 | 직책)\n"
        "/help  - 도움말"
    )


async def cmd_send(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """직접 이메일 발송: /send 이름 이메일 [직책]  또는  /send 이름 | 이메일 | 직책"""
    if not is_allowed(update.effective_user.id):
        return

    import re as _re
    args = update.message.text.partition(" ")[2].strip()
    if not args:
        await update.message.reply_text(
            "사용법:\n"
            "`/send 이름 이메일`\n"
            "`/send 이름 | 이메일 | 직책`\n\n"
            "예시: `/send 홍길동 hong@company.com`\n"
            "예시: `/send 홍길동 | hong@company.com | 부장`",
            parse_mode="Markdown",
        )
        return

    # 이메일 주소를 정규식으로 직접 추출
    email_match = _re.search(r'[\w.\-]+@[\w.\-]+\.[a-zA-Z]{2,}', args)
    if not email_match:
        await update.message.reply_text("❌ 이메일 주소를 찾을 수 없습니다.\n예시: `/send 홍길동 hong@company.com`", parse_mode="Markdown")
        return
    email = email_match.group()

    # 이메일 제거 후 나머지에서 이름·직책 파싱
    rest = _re.sub(_re.escape(email), "", args)
    rest_parts = [p.strip() for p in rest.replace("|", " ").split() if p.strip()]
    name = rest_parts[0] if rest_parts else ""
    position = rest_parts[1] if len(rest_parts) >= 2 else ""

    if _already_sent(email):
        await update.message.reply_text(f"⚠️ {email} 로는 이미 최근에 발송했습니다. 중복 발송을 막았습니다.")
        return

    msg = await update.message.reply_text(f"📤 {email} 으로 발송 중...")
    try:
        send_company_intro_email(email, name or "담당자", position)
        _record_sent(email)
        contact_id = save_contact(
            name=name or "",
            company_kr="", company_en="",
            email=email, phone="", position=position,
            department="", raw_text=f"수동 발송: {args}", card_image_path="",
        )
        # 발송 완료 표시: 이게 없으면 poll_pending 이 5분 뒤 같은 메일을 또 보낸다
        mark_email_sent(contact_id)
        greeting = f"{name} {position}님" if position else (f"{name}님" if name else "담당자님")
        await msg.edit_text(f"✅ 발송 완료!\n📧 수신: {greeting} ({email})")
    except Exception as e:
        log.error("직접 발송 실패: %s", e)
        await msg.edit_text(f"❌ 발송 실패: {e}")


async def cmd_list(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id):
        return
    from database import get_all_contacts
    contacts = get_all_contacts()
    if not contacts:
        await update.message.reply_text("저장된 연락처가 없습니다.")
        return
    lines = ["📋 *저장된 연락처 목록*\n"]
    for c in contacts[:20]:
        company = c["company_kr"] or c["company_en"] or ""
        email_status = "✅" if c["email_sent"] else "⏳"
        lines.append(
            f"{email_status} [{c['id']}] {c['name']} | {company}\n"
            f"   📧 {c['email'] or '없음'}"
        )
    await update.message.reply_text(
        "\n".join(lines), parse_mode="Markdown"
    )


# ─── 명함 사진 수신 ───────────────────────────────────────────────────────────

async def handle_photo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id):
        return

    msg = await update.message.reply_text("🔍 명함을 분석하고 있습니다...")

    photo = update.message.photo[-1]
    file = await ctx.bot.get_file(photo.file_id)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    image_path = os.path.join(CARD_DIR, f"{timestamp}_{photo.file_id}.jpg")
    await file.download_to_drive(image_path)

    try:
        contact = extract_contact_from_image(image_path)
        contact["_image_path"] = image_path
        user_id = update.effective_user.id
        pending_contacts[user_id] = contact

        summary = format_contact_summary(contact)
        company = contact.get("company_kr") or contact.get("company_en", "")

        keyboard = [
            [
                InlineKeyboardButton("✅ 맞습니다", callback_data=f"confirm_{user_id}"),
                InlineKeyboardButton("✏️ 수정", callback_data=f"edit_{user_id}"),
            ],
            [InlineKeyboardButton("❌ 취소", callback_data=f"cancel_{user_id}")],
        ]

        email_notice = (
            "📧 이메일로 회사소개서를 발송합니다.\n"
            "⚠️ 이메일 주소 꼭 확인하세요 (1/i, 5/s, 0/O 혼동 주의)"
            if contact.get('email') else
            "⚠️ 이메일 주소를 찾지 못했습니다. 수정 버튼으로 직접 입력해주세요."
        )
        await msg.edit_text(
            f"📇 *명함 인식 결과*\n\n{summary}\n\n{email_notice}\n\n내용이 맞나요?",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown",
        )
    except Exception as e:
        log.exception("OCR 오류")
        await msg.edit_text(f"❌ 명함 인식 중 오류가 발생했습니다.\n{e}")


# ─── 인라인 버튼 콜백 ──────────────────────────────────────────────────────────

async def handle_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    action, uid_str = query.data.rsplit("_", 1)
    user_id = int(uid_str)

    if action == "cancel":
        pending_contacts.pop(user_id, None)
        await query.edit_message_text("❌ 취소했습니다.")
        return

    if action == "edit":
        await query.edit_message_text(
            "✏️ 이름과 이메일을 입력해 주세요.\n\n"
            "형식: `이름 | 이메일`\n"
            "예시: `홍길동 | hong@samsung.com`",
            parse_mode="Markdown",
        )
        ctx.user_data["awaiting_edit"] = True
        return

    if action == "confirm":
        contact = pending_contacts.pop(user_id, None)
        if not contact:
            await query.edit_message_text("❌ 만료된 요청입니다.")
            return

        await query.edit_message_text("⚙️ 처리 중...")
        await _process_confirmed_contact(query, contact)


async def handle_text_edit(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """수동 수정 텍스트 입력 처리"""
    if not ctx.user_data.get("awaiting_edit"):
        return

    ctx.user_data["awaiting_edit"] = False
    user_id = update.effective_user.id
    contact = pending_contacts.get(user_id, {})

    import re as _re
    text = update.message.text.strip()
    # 이메일 직접 추출
    email_match = _re.search(r'[\w.\-]+@[\w.\-]+\.[a-zA-Z]{2,}', text)
    if email_match:
        contact["email"] = email_match.group()
        name_part = _re.sub(_re.escape(email_match.group()), "", text).replace("|", "").strip()
        if name_part:
            contact["name"] = name_part
    else:
        parts = [p.strip() for p in text.split("|")]
        if len(parts) >= 1 and parts[0]:
            contact["name"] = parts[0]
        if len(parts) >= 2 and parts[1]:
            contact["email"] = parts[1]

    pending_contacts[user_id] = contact
    summary = format_contact_summary(contact)
    keyboard = [[
        InlineKeyboardButton("✅ 맞습니다", callback_data=f"confirm_{user_id}"),
        InlineKeyboardButton("❌ 취소", callback_data=f"cancel_{user_id}"),
    ]]
    await update.message.reply_text(
        f"📇 *수정된 내용*\n\n{summary}\n\n확인해주세요:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown",
    )


async def _process_confirmed_contact(query, contact: dict):
    """연락처 저장 → 이메일 발송 → 하이웍스 주소록 → vCard 생성"""
    results = []
    name = contact.get("name", "담당자")
    company = contact.get("company_kr") or contact.get("company_en", "")
    email = contact.get("email", "")

    # 1. DB 저장
    contact_id = save_contact(
        name=name,
        company_kr=contact.get("company_kr", ""),
        company_en=contact.get("company_en", ""),
        email=email,
        phone=contact.get("phone", ""),
        position=contact.get("position", ""),
        department=contact.get("department", ""),
        raw_text=contact.get("raw_text", ""),
        card_image_path=contact.get("_image_path", ""),
    )
    results.append(f"💾 DB 저장: ✅")

    # 2. 이메일 발송
    if email and _already_sent(email):
        mark_email_sent(contact_id)
        results.append(f"📧 이메일: ⚠️ 최근 발송 이력 있어 건너뜀 ({email})")
    elif email:
        try:
            send_company_intro_email(email, name, contact.get("position", ""))
            _record_sent(email)
            mark_email_sent(contact_id)
            results.append(f"📧 이메일 발송: ✅ ({email})")
        except Exception as e:
            log.error("이메일 발송 실패: %s", e)
            results.append(f"📧 이메일 발송: ❌ ({e})")
    else:
        results.append("📧 이메일: ⚠️ 주소 없음 (건너뜀)")

    # 3. 하이웍스 주소록
    try:
        ok = add_to_hiworks_contacts(contact)
        if ok:
            mark_hiworks_synced(contact_id)
            results.append(f"🗂 하이웍스 주소록: ✅ ({name} | {company})")
        else:
            results.append("🗂 하이웍스 주소록: ⚠️ (API 키 미설정 또는 오류)")
    except Exception as e:
        log.error("하이웍스 주소록 오류: %s", e)
        results.append(f"🗂 하이웍스 주소록: ❌ ({e})")

    # 4. vCard 생성 (리멤버 임포트용)
    try:
        vcard_path = export_vcard(contact, contact_id)
        mark_vcard_exported(contact_id)
        results.append(f"📱 vCard 생성: ✅ ({os.path.basename(vcard_path)})")
    except Exception as e:
        results.append(f"📱 vCard 생성: ❌ ({e})")

    await query.edit_message_text(
        f"✅ *처리 완료* — {name} | {company}\n\n" + "\n".join(results),
        parse_mode="Markdown",
    )


# ─── 5분 폴링: 미처리 항목 재시도 ────────────────────────────────────────────

async def poll_pending(context: ContextTypes.DEFAULT_TYPE):
    log.info("폴링: 미처리 이메일 확인 중...")

    for c in get_pending_email():
        if _already_sent(c["email"]):
            mark_email_sent(c["id"])
            continue
        try:
            send_company_intro_email(c["email"], c["name"])
            _record_sent(c["email"])
            mark_email_sent(c["id"])
            log.info("재발송 성공: %s (%s)", c["name"], c["email"])
        except Exception as e:
            log.error("재발송 실패 [%s]: %s", c["id"], e)

    for c in get_pending_hiworks():
        contact_dict = dict(c)
        try:
            ok = add_to_hiworks_contacts(contact_dict)
            if ok:
                mark_hiworks_synced(c["id"])
                log.info("하이웍스 주소록 재등록 성공: %s", c["name"])
        except Exception as e:
            log.error("하이웍스 재등록 실패 [%s]: %s", c["id"], e)


# ─── 진입점 ───────────────────────────────────────────────────────────────────

def main():
    init_db()
    log.info("봇 시작...")

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_start))
    app.add_handler(CommandHandler("list", cmd_list))
    app.add_handler(CommandHandler("send", cmd_send))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_edit))

    # 5분 폴링 등록
    app.job_queue.run_repeating(poll_pending, interval=POLL_INTERVAL_SECONDS, first=60)

    log.info("봇이 실행되었습니다. (폴링 간격: %d초)", POLL_INTERVAL_SECONDS)
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()

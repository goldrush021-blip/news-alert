import logging
import smtplib
import ssl
import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from email.header import Header
from email.utils import formataddr
from config import (
    HIWORKS_EMAIL, HIWORKS_PASSWORD, HIWORKS_SMTP_HOST,
    HIWORKS_SMTP_PORT, SENDER_NAME, PDF_PATH
)

log = logging.getLogger(__name__)


EMAIL_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<style>
  body {{
    font-family: '맑은 고딕', 'Malgun Gothic', Arial, sans-serif;
    font-size: 16px; color: #222; line-height: 2.2;
    margin: 0; padding: 0; background: #fff;
  }}
  .wrap {{ max-width: 660px; padding: 40px 28px; }}
  p {{ margin: 0 0 28px 0; }}
  .section-title {{ margin: 36px 0 16px 0; font-weight: bold; font-size: 16px; }}
  ul {{ margin: 0 0 28px 0; padding-left: 22px; }}
  ul li {{ margin-bottom: 14px; line-height: 1.9; }}
  .sig {{ margin-top: 44px; border-top: 1px solid #ccc; padding-top: 22px; color: #444; line-height: 2.2; }}
</style>
</head>
<body>
<div class="wrap">

<p>안녕하세요, {recipient_greeting}.<br>
업사이드(UP-SIDE) {sender_name} 과장입니다.</p>

<br>

<p>저희 업사이드(UP-SIDE)는 자체 개발한 '인재 전용 매칭 시스템'을 기반으로 직무경력, 산업경험, 필수역량 등 세부 조건별로 정밀 분석하며,</p>

<p>이를 통해 JD의 핵심 조건과 최대 99% 수준까지 부합하는 검증된 인재를 빠르게 선별 추천해 드리고 있습니다. 현재 호텔, 코스메틱, 헬스케어·바이오, F&amp;B, 생활소비재, R&D, 통신·IT, 반도체 등 다양한 산업군에서 다수의 채용 프로젝트를 성공적으로 수행하고 있습니다.</p>

<br>

<p class="section-title">[업사이드(UP-SIDE)만의 인재 채용 솔루션]</p>

<ul>
  <li><strong>신속한 후보자 확보:</strong> 자체 매칭 시스템을 통해 핵심 인재를 빠르게 발굴합니다.</li>
  <li><strong>입체적 인재 선별:</strong> 직무 역량뿐만 아니라 귀사의 조직문화(Culture-fit)에 부합하는 인재를 선별합니다.</li>
  <li><strong>채용 검증 절차 최적화:</strong> 정제된 인재를 추천해 드려 서류 검토 및 검증 시간을 대폭 줄여드립니다.</li>
  <li><strong>합리적이고 유연한 조건:</strong> 수수료율은 고객사의 상황에 맞춰 유연하게 협의 가능합니다.</li>
</ul>

<br>

<p>현재 채용 중이시거나 향후 진행 예정인 포지션의 JD를 전달해 주시면, 저희가 추천해드리는 후보자들을 기존 채용 채널과 편하게 비교·검증해 보시는 것만으로도 훨씬 더 우수한 인재를 선발하시는 데 좋은 선택지가 될 것으로 생각되며,</p>

<p>귀사의 채용 고민을 함께 나누고, 성장에 꼭 필요한 핵심 인재를 연결하는 채용 파트너가 되겠습니다. 긍정적인 검토와 답변을 기다리겠습니다.</p>

<div class="sig">
  감사합니다.<br><br>
  <strong>장원혁</strong> 과장 드림<br>
  업사이드(UP-SIDE)<br><br>
  T. 010-5002-5129<br>
  E. goldrush021@up-side.co.kr
</div>

</div>
</body>
</html>
"""


def _ssl_context(host: str) -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    if "hiworks" in host.lower():
        # 하이웍스 구형 인증서 호환 (기존 동작 유지). 구글 등 다른 서버는 정상 검증한다.
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        ctx.set_ciphers("DEFAULT@SECLEVEL=1")
    return ctx


def send_company_intro_email(recipient_email: str, recipient_name: str = "담당자", recipient_position: str = "") -> str:
    """SMTP(.env 의 HIWORKS_SMTP_HOST/PORT)로 회사소개서 이메일 발송.

    성공하면 사용한 서버("host:port")를 돌려준다. 발송은 딱 한 번만 시도한다
    (예전처럼 여러 포트를 돌려가며 재시도하면 같은 메일이 중복 발송될 수 있다).
    """
    msg = MIMEMultipart("alternative")
    msg["Subject"] = Header("[헤드헌팅] 업사이드(UP-SIDE) 인재 전용 매칭 시스템 기반 헤드헌팅 회사소개서 송부드립니다.", "utf-8")
    msg["From"] = formataddr((str(Header(SENDER_NAME, "utf-8")), HIWORKS_EMAIL))
    msg["To"] = formataddr((str(Header(recipient_name, "utf-8")), recipient_email))
    msg["Bcc"] = HIWORKS_EMAIL  # 본인 받은 메일함에서 발송 내역 확인용

    greeting = f"{recipient_name} {recipient_position}님" if recipient_position else f"{recipient_name} 매니저님"

    html_body = EMAIL_HTML_TEMPLATE.format(
        recipient_greeting=greeting,
        sender_name=SENDER_NAME,
        sender_email=HIWORKS_EMAIL,
    )

    msg_related = MIMEMultipart("related")
    msg_related.attach(MIMEText(html_body, "html", "utf-8"))

    msg.attach(msg_related)

    if os.path.exists(PDF_PATH):
        with open(PDF_PATH, "rb") as f:
            pdf_attachment = MIMEApplication(f.read(), _subtype="pdf")
            filename = os.path.basename(PDF_PATH)
            pdf_attachment.add_header(
                "Content-Disposition", "attachment",
                filename=("utf-8", "", filename)
            )
            msg.attach(pdf_attachment)
    else:
        log.warning("회사소개서 PDF를 찾을 수 없어 첨부 없이 발송합니다: %s", PDF_PATH)

    host, port = HIWORKS_SMTP_HOST, HIWORKS_SMTP_PORT
    ctx = _ssl_context(host)
    log.info("메일 발송: %s -> %s (서버 %s:%s)", HIWORKS_EMAIL, recipient_email, host, port)

    sent = False
    try:
        if port == 465:
            with smtplib.SMTP_SSL(host, port, context=ctx, timeout=30) as server:
                server.login(HIWORKS_EMAIL, HIWORKS_PASSWORD)
                server.send_message(msg)
                sent = True
        else:
            with smtplib.SMTP(host, port, timeout=30) as server:
                server.ehlo()
                server.starttls(context=ctx)
                server.ehlo()
                server.login(HIWORKS_EMAIL, HIWORKS_PASSWORD)
                server.send_message(msg)
                sent = True
    except Exception as e:
        if not sent:
            raise Exception(f"{host}:{port} 발송 실패: {e}") from e
        # 이미 발송됐는데 연결을 닫다가 난 오류: 실패로 처리하면 5분 뒤 재발송되므로 성공으로 본다
        log.warning("발송 후 연결 종료 중 오류(발송은 완료됨): %s", e)

    return f"{host}:{port}"

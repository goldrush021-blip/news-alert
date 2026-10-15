// 1차 면접 텔레그램 알림 (Google Apps Script)
// 전날 18:00 / 당일 09:00 (KST)에 '장원혁' 탭의 '1차 면접' 날짜를 읽어 텔레그램으로 알림

const SHEET_ID = '1TxbFMxaNSxPoMTzg21c-xSwzc5hObSrc7RC-w2Jw5_E';
const TAB_NAME = '장원혁';
const INTERVIEW_HEADER = '1차 면접';
const TZ = 'Asia/Seoul';

// 헤더명으로 찾고, 못 찾으면 fallback 열(0부터: C=2, D=3, F=5, K=10)을 사용
const FIELDS = {
  company: { keys: ['기업명', '업체', '회사'], fallback: 2 },
  position: { keys: ['포지션명', '포지션'], fallback: 3 },
  name: { keys: ['후보자명', '후보명', '이름', '성명'], fallback: 5 },
  phone: { keys: ['연락처', '휴대폰', '핸드폰'], fallback: 10 },
};

function notifyEve() { notify_(1, '내일'); }
function notifyToday() { notify_(0, '오늘'); }

function notify_(offsetDays, label) {
  const target = kstDate_(offsetDays);
  const items = collect_(target);
  console.log(label + ' 면접 ' + items.length + '건');
  if (items.length) sendTelegram_(buildMessage_(label, target, items));
}

// 시간 트리거 설치: 이 함수를 한 번만 실행
function createTriggers() {
  ScriptApp.getProjectTriggers().forEach(t => ScriptApp.deleteTrigger(t));
  ScriptApp.newTrigger('notifyEve').timeBased().atHour(18).everyDays(1).inTimezone(TZ).create();
  ScriptApp.newTrigger('notifyToday').timeBased().atHour(9).everyDays(1).inTimezone(TZ).create();
}

function kstDate_(offsetDays) {
  const d = new Date(Date.now() + offsetDays * 86400000);
  const [y, m, day] = Utilities.formatDate(d, TZ, 'yyyy-M-d').split('-').map(Number);
  return { y: y, m: m, d: day, wd: Number(Utilities.formatDate(d, TZ, 'u')) };
}

function parseMD_(text) {
  const m = String(text || '').match(/(\d{1,2})\s*\/\s*(\d{1,2})/);
  return m ? { m: Number(m[1]), d: Number(m[2]) } : null;
}

function collect_(target) {
  const sheet = SpreadsheetApp.openById(SHEET_ID).getSheetByName(TAB_NAME);
  const rows = sheet.getDataRange().getDisplayValues();
  let headerRow = 0, interviewCol = -1;
  for (let r = 0; r < Math.min(10, rows.length) && interviewCol < 0; r++) {
    const c = rows[r].findIndex(h => h.replace(/\s/g, '') === INTERVIEW_HEADER.replace(/\s/g, ''));
    if (c >= 0) { headerRow = r; interviewCol = c; }
  }
  if (interviewCol < 0) throw new Error("'" + INTERVIEW_HEADER + "' 헤더를 찾을 수 없습니다.");
  const header = rows[headerRow];
  const col = {};
  Object.keys(FIELDS).forEach(f => {
    const i = header.findIndex(h => FIELDS[f].keys.some(k => h.indexOf(k) >= 0));
    col[f] = i >= 0 ? i : FIELDS[f].fallback;
  });
  const items = [];
  for (let r = headerRow + 1; r < rows.length; r++) {
    const md = parseMD_(rows[r][interviewCol]);
    if (md && md.m === target.m && md.d === target.d) {
      const o = {};
      Object.keys(col).forEach(f => o[f] = String(rows[r][col[f]] || '').trim());
      items.push(o);
    }
  }
  return items;
}

function buildMessage_(label, t, items) {
  const wd = '월화수목금토일'[t.wd - 1];
  const lines = ['📞 ' + label + ' 1차 면접 ' + items.length + '건 (' + t.m + '/' + t.d + '(' + wd + '))', '',
    '후보자에게 통화 + 문자 필요합니다.', ''];
  items.forEach((it, i) => {
    lines.push('[' + (i + 1) + '] ' + (it.name || '(이름 없음)') + '  ' + it.phone);
    lines.push('    ' + it.company + ' / ' + it.position);
  });
  return lines.join('\n');
}

function findChatId_(token) {
  const res = JSON.parse(UrlFetchApp.fetch('https://api.telegram.org/bot' + token + '/getUpdates').getContentText());
  const upd = (res.result || []).reverse().find(u => u.message && u.message.chat);
  if (!upd) throw new Error('chat id를 찾을 수 없습니다. 봇에게 먼저 메시지를 보내세요.');
  return String(upd.message.chat.id);
}

function sendTelegram_(text) {
  const props = PropertiesService.getScriptProperties();
  const token = props.getProperty('TELEGRAM_BOT_TOKEN');
  if (!token) throw new Error('스크립트 속성 TELEGRAM_BOT_TOKEN이 없습니다.');
  const chatId = props.getProperty('TELEGRAM_CHAT_ID') || findChatId_(token);
  UrlFetchApp.fetch('https://api.telegram.org/bot' + token + '/sendMessage', {
    method: 'post',
    payload: { chat_id: chatId, text: text, disable_web_page_preview: 'true' },
  });
}

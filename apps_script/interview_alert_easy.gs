// 1차 면접 텔레그램 알림 (개인 Apps Script 버전: script.google.com 에서 따로 생성)
// 공유 시트는 수정하지 않고, 읽기만 합니다. 사용자 계정에 시트 열람 권한만 있으면 됩니다.
// 전날 12:00, 전날 18:00, 당일 09:00, 당일 13:00 (KST)에 자동으로 알림이 갑니다.

const SHEET_ID = '1TxbFMxaNSxPoMTzg21c-xSwzc5hObSrc7RC-w2Jw5_E';
const TAB_NAME = '장원혁';
const INTERVIEW_HEADER = '1차 면접';
const TZ = 'Asia/Seoul';

// 헤더명으로 찾고, 못 찾으면 fallback 열(0부터: C=2, D=3, F=5, K=10)을 사용
const FIELDS = {
  company: { keys: ['기업명', '업체', '회사'], fallback: 2 },
  position: { keys: ['포지션명', '포지션'], fallback: 3 },
  name: { keys: ['후보자명', '후보명', '이름', '성명'], fallback: 5 },
  phone: { keys: ['후보 전화번호', '전화번호', '연락처', '휴대폰', '핸드폰'], fallback: 10 },
};

// ===== 설정값: 아래 두 줄만 채우세요 (chat id는 비워도 됨) =====
const BOT_TOKEN = '여기에_텔레그램_봇_토큰';
const CHAT_ID = '';

// ===== 1. 처음 설정: 이 함수를 한 번만 실행 =====
// 토큰 저장 + 매일 자동 실행 등록 + 확인 메시지 전송
function setup() {
  if (!BOT_TOKEN || BOT_TOKEN.indexOf('여기에') === 0) throw new Error('위쪽 BOT_TOKEN 줄에 봇 토큰을 먼저 넣으세요.');
  const props = PropertiesService.getScriptProperties();
  props.setProperty('TELEGRAM_BOT_TOKEN', BOT_TOKEN);
  props.setProperty('TELEGRAM_CHAT_ID', CHAT_ID || findChatId_(BOT_TOKEN));
  createTriggers();
  sendTelegram_('✅ 면접 알림 설정 완료. 면접 전날 12시·18시, 당일 9시·13시에 알려드립니다.');
  console.log('설정 완료. 텔레그램에 확인 메시지가 갔는지 확인하세요.');
}

// ===== 2. 지금 바로 보내기 (테스트/수동 실행) =====
function sendTodayNow() { console.log('오늘 면접 ' + notify_(0, '오늘') + '건'); }
function sendTomorrowNow() { console.log('내일 면접 ' + notify_(1, '내일') + '건'); }

// ===== 자동 실행 =====
function notifyEve() { notify_(1, '내일'); }
function notifyToday() { notify_(0, '오늘'); }

// 전날 12시·18시, 당일 9시·13시 (시간 트리거는 해당 시각 안에 실행됨)
function createTriggers() {
  ScriptApp.getProjectTriggers().forEach(t => ScriptApp.deleteTrigger(t));
  [[12, 'notifyEve'], [18, 'notifyEve'], [9, 'notifyToday'], [13, 'notifyToday']].forEach(function (x) {
    ScriptApp.newTrigger(x[1]).timeBased().atHour(x[0]).everyDays(1).inTimezone(TZ).create();
  });
}

function notify_(offsetDays, label) {
  const target = kstDate_(offsetDays);
  const items = collect_(target);
  console.log(label + ' 면접 ' + items.length + '건');
  if (items.length) sendTelegram_(buildMessage_(label, target, items));
  return items.length;
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
  if (!sheet) throw new Error("'" + TAB_NAME + "' 탭을 찾을 수 없습니다.");
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
  const phoneRe = /01[016789][-\s]?\d{3,4}[-\s]?\d{4}/;
  const items = [];
  for (let r = headerRow + 1; r < rows.length; r++) {
    const md = parseMD_(rows[r][interviewCol]);
    if (md && md.m === target.m && md.d === target.d) {
      const o = {};
      Object.keys(col).forEach(f => o[f] = String(rows[r][col[f]] || '').trim());
      // 전화번호 칸이 번호 모양이 아니면 같은 행에서 번호 모양의 값을 직접 찾는다
      if (!phoneRe.test(o.phone)) {
        const hit = rows[r].find(c => phoneRe.test(c));
        o.phone = hit ? hit.match(phoneRe)[0] : '';
      }
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
  if (!upd) throw new Error('chat id를 찾을 수 없습니다. 텔레그램에서 봇에게 먼저 메시지를 보낸 뒤 다시 설정하세요.');
  return String(upd.message.chat.id);
}

function sendTelegram_(text) {
  const props = PropertiesService.getScriptProperties();
  const token = props.getProperty('TELEGRAM_BOT_TOKEN');
  if (!token) throw new Error("먼저 메뉴 '면접 알림 > 1. 처음 설정'을 실행하세요.");
  const chatId = props.getProperty('TELEGRAM_CHAT_ID') || findChatId_(token);
  UrlFetchApp.fetch('https://api.telegram.org/bot' + token + '/sendMessage', {
    method: 'post',
    payload: { chat_id: chatId, text: text, disable_web_page_preview: 'true' },
  });
}

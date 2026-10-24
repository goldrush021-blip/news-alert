// 1차 면접 텔레그램 알림 (구글 시트 메뉴 버전)
// 시트 상단에 '면접 알림' 메뉴가 생기고, 메뉴를 눌러 설정/실행합니다.
// 전날 18:00 / 당일 09:00 (KST)에 자동으로도 알림이 갑니다.

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

// ===== 시트 메뉴 =====
function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu('면접 알림')
    .addItem('1. 처음 설정 (한 번만)', 'setup')
    .addSeparator()
    .addItem('오늘 면접 지금 보내기', 'menuToday')
    .addItem('내일 면접 지금 보내기', 'menuEve')
    .addToUi();
}

function menuToday() { runNow_(0, '오늘'); }
function menuEve() { runNow_(1, '내일'); }

function runNow_(offsetDays, label) {
  const ui = SpreadsheetApp.getUi();
  try {
    const n = notify_(offsetDays, label);
    ui.alert(n ? label + ' 면접 ' + n + '건을 텔레그램으로 보냈습니다.' : label + ' 1차 면접이 없습니다.');
  } catch (e) {
    ui.alert('실패: ' + e.message);
  }
}

// ===== 처음 설정: 토큰 입력 + 자동 실행 등록 + 테스트 메시지 =====
function setup() {
  const ui = SpreadsheetApp.getUi();
  const props = PropertiesService.getScriptProperties();

  const t = ui.prompt('텔레그램 봇 토큰', 'BotFather에서 받은 토큰을 붙여넣으세요.', ui.ButtonSet.OK_CANCEL);
  if (t.getSelectedButton() !== ui.Button.OK) return;
  const token = t.getResponseText().trim();
  if (!token) { ui.alert('토큰이 비어 있습니다.'); return; }
  props.setProperty('TELEGRAM_BOT_TOKEN', token);

  const c = ui.prompt('텔레그램 chat id',
    '모르면 비워두세요. (봇에게 먼저 아무 메시지나 한 번 보낸 상태여야 자동으로 찾습니다)', ui.ButtonSet.OK_CANCEL);
  if (c.getSelectedButton() !== ui.Button.OK) return;
  const typed = c.getResponseText().trim();
  try {
    props.setProperty('TELEGRAM_CHAT_ID', typed || findChatId_(token));
    createTriggers();
    sendTelegram_('✅ 면접 알림 설정 완료. 매일 09:00(오늘 면접) / 18:00(내일 면접)에 알려드립니다.');
    ui.alert('설정 완료! 텔레그램에 확인 메시지가 갔는지 보세요.');
  } catch (e) {
    ui.alert('설정 실패: ' + e.message);
  }
}

// ===== 자동 실행 =====
function notifyEve() { notify_(1, '내일'); }
function notifyToday() { notify_(0, '오늘'); }

function createTriggers() {
  ScriptApp.getProjectTriggers().forEach(t => ScriptApp.deleteTrigger(t));
  ScriptApp.newTrigger('notifyEve').timeBased().atHour(18).everyDays(1).inTimezone(TZ).create();
  ScriptApp.newTrigger('notifyToday').timeBased().atHour(9).everyDays(1).inTimezone(TZ).create();
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

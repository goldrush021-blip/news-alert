import os
import json
import re
import requests
import hashlib
from datetime import datetime

KEYWORDS = [
    "산업재해 사망",
    "중대재해 사망",
    "작업중 사망",
    "산업현장 사망사고",
    "추락 사망사고",
    "끼임 사망사고",
    "감전 사망사고",
    "화재 사망사고",
    "건설현장 사망",
    "공장 사망사고",
    "업무중 사망",
    "근로자 사망",
]
SENT_FILE = "sent_articles.json"
MAX_SAVED = 2000

def load_sent_ids():
    if os.path.exists(SENT_FILE):
        with open(SENT_FILE,"r",encoding="utf-8") as f: return set(json.load(f))
    return set()

def save_sent_ids(sent_ids):
    with open(SENT_FILE,"w",encoding="utf-8") as f:
        json.dump(list(sent_ids)[-MAX_SAVED:],f,ensure_ascii=False)

def search_naver_news(query,client_id,client_secret,display=5):
    url="https://openapi.naver.com/v1/search/news.json"
    headers={"X-Naver-Client-Id":client_id,"X-Naver-Client-Secret":client_secret}
    params={"query":query,"display":display,"sort":"date"}
    try:
        r=requests.get(url,headers=headers,params=params,timeout=10)
        if r.status_code==200: return r.json().get("items",[])
    except Exception as e: print(f"[검색 실패] {e}")
    return []

def get_kakao_access_token(key,refresh):
    try:
        r=requests.post("https://kauth.kakao.com/oauth/token",
            data={"grant_type":"refresh_token","client_id":key,"refresh_token":refresh},timeout=10)
        d=r.json()
        if "access_token" in d: return d["access_token"],d.get("refresh_token")
        print(f"[카카오 오류] {d}")
    except Exception as e: print(f"[카카오 실패] {e}")
    return None,None

def send_kakao_message(token,text):
    try:
        template={"object_type":"text","text":text[:2000],"link":{"web_url":"https://news.naver.com","mobile_web_url":"https://news.naver.com"}}
        r=requests.post("https://kapi.kakao.com/v2/api/talk/memo/default/send",
            headers={"Authorization":f"Bearer {token}","Content-Type":"application/x-www-form-urlencoded"},
            data={"template_object":json.dumps(template,ensure_ascii=False)},timeout=10)
        if r.status_code==200: return True
        print(f"[전송 오류] {r.status_code}: {r.text}")
    except Exception as e: print(f"[전송 실패] {e}")
    return False

def clean_html(text):
    text=re.sub(r"<[^>]+>","",text)
    for a,b in [("&quot;",'"'),("&amp;","&"),("&lt;","<"),("&gt;",">"),("&#39;","'"),("&nbsp;"," ")]: text=text.replace(a,b)
    return text.strip()

def article_id(link): return hashlib.md5(link.encode()).hexdigest()

def main():
    naver_id=os.environ["NAVER_CLIENT_ID"]
    naver_secret=os.environ["NAVER_CLIENT_SECRET"]
    kakao_key=os.environ["KAKAO_REST_API_KEY"]
    kakao_refresh=os.environ["KAKAO_REFRESH_TOKEN"]
    access_token,new_refresh=get_kakao_access_token(kakao_key,kakao_refresh)
    if not access_token: print("카카오 토큰 발급 실패"); return
    if new_refresh: print(f"[갱신 REFRESH TOKEN] {new_refresh}")
    sent_ids=load_sent_ids()
    new_articles=[]
    seen_links=set()
    for keyword in KEYWORDS:
        for item in search_naver_news(keyword,naver_id,naver_secret):
            link=item.get("link","")
            aid=article_id(link)
            if aid not in sent_ids and link not in seen_links:
                seen_links.add(link); sent_ids.add(aid)
                new_articles.append({"title":clean_html(item.get("title","")),"description":clean_html(item.get("description",""))[:120],"link":link})
    print(f"새 기사 {len(new_articles)}건")
    if not new_articles:
        save_sent_ids(sent_ids); return
    now_str=datetime.now().strftime("%m/%d %H:%M")
    for i in range(0,len(new_articles),5):
        batch=new_articles[i:i+5]
        lines=[f"\U0001f6a8 인사사고 뉴스 [{now_str}]\n"]
        for j,art in enumerate(batch,1):
            lines.append(f"[{j}] {art['title']}")
            if art["description"]: lines.append(f"   {art['description']}...")
            lines.append(f"   \U0001f517 {art['link']}"); lines.append("")
        ok=send_kakao_message(access_token,"\n".join(lines))
        print(f"배치 {i//5+1}: {'완료' if ok else '실패'}")
    save_sent_ids(sent_ids)
    print("완료.")

if __name__=="__main__": main()

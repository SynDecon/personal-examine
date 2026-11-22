from __future__ import annotations

import base64
import html as html_lib
import re
from urllib.parse import quote, urljoin, urlsplit

import requests
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

from .parser import parse_exam_batch_id, parse_semester_id

AUTH_BASE = "http://39.164.230.243:9527"
EAMS_BASE = "http://39.164.230.243:91"
SERVICE_URL = f"{EAMS_BASE}/eams/login.action"
EXAM_SHELL_URL = f"{EAMS_BASE}/eams/stdExamTable.action"
EXAM_TABLE_URL = f"{EAMS_BASE}/eams/stdExamTable!examTable.action"
AES_KEY = b"jsmituluzhou2024"
TIMEOUT = 30


class LoginError(RuntimeError):
    pass


class FetchError(RuntimeError):
    pass


def _request(session: requests.Session, method: str, url: str, **kwargs):
    try:
        return session.request(method, url, timeout=TIMEOUT, **kwargs)
    except requests.RequestException as exc:
        # 公开仓库的 Actions 日志会公开，URL 里的 ids 参数是学号，不能带进异常信息
        raise FetchError(f"请求失败 {method} {url.split('?')[0]}: {type(exc).__name__}") from None


def _truthy(value) -> bool:
    return value not in (None, False, 0, "", "0", "false", "False")


def _headers(referer: str | None = None) -> dict[str, str]:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
        ),
        "Accept": "application/json, text/plain, */*",
    }
    if referer:
        headers["Referer"] = referer
        headers["Origin"] = AUTH_BASE
    return headers


def _encrypt_password(password: str) -> str:
    cipher = AES.new(AES_KEY, AES.MODE_ECB)
    encrypted = cipher.encrypt(pad(password.encode("utf-8"), AES.block_size))
    return base64.b64encode(encrypted).decode("ascii")


def _follow_cas_landing(session: requests.Session, response: requests.Response) -> tuple[requests.Response, str]:
    if response.status_code != 200:
        return response, "no-200"
    text = response.text
    jump = re.search(
        r"location\.(?:href\s*=\s*|replace\s*\(\s*)[\"']([^\"']+)[\"']", text, re.I
    )
    if jump:
        target = urljoin(response.url, html_lib.unescape(jump.group(1)))
        return _request(session, "GET", target, headers=_headers()), "js-jump"
    meta = re.search(
        r"http-equiv=[\"']refresh[\"'][^>]*content=[\"'][^\"']*url=([^\"'>]+)", text, re.I
    )
    if meta:
        target = urljoin(response.url, html_lib.unescape(meta.group(1).strip()))
        return _request(session, "GET", target, headers=_headers()), "meta-refresh"

    for item in re.finditer(r"(?:href|action)=[\"']([^\"']+)[\"']", text, re.I):
        candidate = html_lib.unescape(item.group(1))
        if "ticket=" in candidate.lower():
            return _request(session, "GET", urljoin(response.url, candidate), headers=_headers()), "link-ticket"

    ticket_id = re.search(r"[\"'](ST-[A-Za-z0-9._-]{6,})[\"']", text)
    if ticket_id:
        sep = "&" if "?" in SERVICE_URL else "?"
        target = f"{SERVICE_URL}{sep}ticket={ticket_id.group(1)}"
        return _request(session, "GET", target, headers=_headers()), "var-ticket"

    tag = re.search(r"<form[^>]*>", text, re.I)
    tag_text = tag.group(0) if tag else ""
    action = re.search(r"action=[\"']([^\"']*)[\"']", tag_text, re.I)
    method = re.search(r"method=[\"']([^\"']+)[\"']", tag_text, re.I)
    action_url = urljoin(response.url, html_lib.unescape(action.group(1))) if action and action.group(1) else response.url
    data = {}
    for item in re.finditer(r"<input[^>]*>", text, re.I):
        name = re.search(r"name=[\"']([^\"']+)[\"']", item.group(0), re.I)
        value = re.search(r"value=[\"']([^\"']*)[\"']", item.group(0), re.I)
        if name:
            data[name.group(1)] = html_lib.unescape(value.group(1)) if value else ""
    if tag and ("ticket" in data or "ticket" in action_url.lower()):
        if (method.group(1).lower() if method else "get") == "post":
            return _request(session, "POST", action_url, data=data, headers=_headers()), "form-ticket"
        return _request(session, "GET", action_url, params=data, headers=_headers()), "form-ticket"
    return response, "none"


def _cas_probe(response: requests.Response, note: str, session: requests.Session) -> str:
    text = response.text
    chains = " > ".join(f"{hop.status_code}{urlsplit(hop.url).path}" for hop in response.history + [response])
    title = re.search(r"<title>(.*?)</title>", text, re.S | re.I)
    inputs = re.findall(r"<input[^>]*name=[\"']([^\"']+)[\"']", text, re.I)
    form_action = re.search(r"<form[^>]*action=[\"']([^\"']+)", text, re.I)
    action_path = urlsplit(html_lib.unescape(form_action.group(1))).path if form_action else ""
    keywords = ",".join(
        word for word in ("登录", "无效", "未注册", "未授权", "过期") if word in text
    )
    return (
        f"cas={chains} note={note} len={len(text)} "
        f"title={title.group(1).strip()[:30] if title else ''} "
        f"inputs={','.join(inputs[:8])} action={action_path} kw={keywords} "
        f"ticket={'ticket' in text.lower()} href_ticket={'ticket=' in text.lower()} "
        f"st={'ST-' in text} cookies={','.join(sorted(session.cookies.keys()))}"
    )


def create_session(username: str, password: str) -> requests.Session:
    session = requests.Session()
    session.headers.update(_headers())

    captcha = _request(session, "GET", f"{AUTH_BASE}/authserver/captcha")
    try:
        state = captcha.json().get("data", {}).get("state", "")
    except ValueError as exc:
        raise LoginError(f"获取登录 state 失败，HTTP {captcha.status_code}") from exc

    payload = {
        "username": username,
        "password": _encrypt_password(password),
        "captcha": "",
        "authType": "normal",
        "state": state,
        "remeberMe": "0",
        "serviceUrl": SERVICE_URL,
    }
    response = _request(
        session,
        "POST",
        f"{AUTH_BASE}/authserver/login/signin",
        json=payload,
        headers=_headers(f"{AUTH_BASE}/#/authserver/login"),
    )
    try:
        body = response.json()
    except ValueError as exc:
        raise LoginError(f"登录接口返回非 JSON，HTTP {response.status_code}") from exc
    if body.get("code") != 0:
        raise LoginError(f"登录失败: {body.get('message') or body}")

    data = body.get("data") or {}
    blocks = []
    if _truthy(data.get("secAuth")):
        blocks.append("二次认证")
    if _truthy(data.get("noSingleLogin")):
        blocks.append("单处登录确认")
    if str(data.get("editPwd", "0")) in {"1", "2", "3"}:
        blocks.append("强制修改密码")
    if _truthy(data.get("showInfo")):
        blocks.append("完善资料")
    if _truthy(data.get("userInfoConfim")):
        blocks.append("身份信息确认")
    if blocks:
        raise LoginError("密码正确，但登录被额外校验拦截：" + "、".join(blocks))

    token = data.get("token") or ""
    if token:
        for name in ("congress", "token"):
            session.cookies.set(name, quote(token, safe=""), domain="39.164.230.243", path="/")
        session.cookies.set(
            "user", quote('{"username":"%s"}' % username, safe=""), domain="39.164.230.243", path="/"
        )

    try:
        raw_cookies = response.raw.headers.getlist("Set-Cookie")
    except AttributeError:
        raw_cookies = []
    set_names = sorted({item.split("=", 1)[0].strip() for item in raw_cookies if "=" in item})
    session.signin_probe = (
        f"setcookies={','.join(set_names)} token_len={len(token)} "
        f"dots={token.count('.')} plus={'+' in token}"
    )

    probes = []
    for service in (SERVICE_URL, f"{EAMS_BASE}/eams/homeExt.action"):
        cas_url = f"{AUTH_BASE}/authserver/authz/cas/login?service={quote(service, safe='')}"
        cas_headers = _headers(f"{AUTH_BASE}/authserver/login")
        if token:
            cas_headers["Authorization"] = f"Bearer {token}"
        landing = _request(session, "GET", cas_url, headers=cas_headers)
        landing, note = _follow_cas_landing(session, landing)
        probes.append(_cas_probe(landing, note, session))
        if note != "none":
            break
    session.cas_probe = " || ".join(probes)

    _request(session, "GET", SERVICE_URL, headers=_headers(f"{AUTH_BASE}/authserver/login"))
    home = _request(session, "GET", f"{EAMS_BASE}/eams/homeExt.action", headers=_headers())
    home.encoding = "utf-8"
    session.eams_probe = (
        f"home={home.status_code}{urlsplit(home.url).path} len={len(home.text)} "
        f"mytable={'courseTableForStd' in home.text} login={'统一身份认证' in home.text}"
    )
    return session


def _looks_like_login(text: str) -> bool:
    return "统一身份认证" in text or "authserver/login" in text


def _is_exam_page(text: str) -> bool:
    return "考场座位号" in text and 'class="griddata' in text


_DIAG_MARKERS = (
    "考场座位号",
    "学年学期",
    "semesterBar",
    "gridtable",
    "TaskActivity",
    "courseTableForStd",
    "stdExamTable",
    "Central Authentication Service",
    "统一身份认证",
    "无权",
    "权限",
    "登录",
    "超时",
    "错误",
    "异常",
)


def _diag(response: requests.Response) -> str:
    text = response.text
    title = re.search(r"<title>(.*?)</title>", text, re.S | re.I)
    chain = ">".join(
        f"{hop.status_code}{urlsplit(hop.url).path}" for hop in response.history + [response]
    )
    marks = ",".join(word for word in _DIAG_MARKERS if word in text)
    return (
        f"{chain} len={len(text)} rows={text.count('class=\"griddata')} "
        f"title={(title.group(1).strip()[:30] if title else '')} marks={marks} "
        f"ctype={response.headers.get('Content-Type', '')}"
    )


def fetch_exam_table(session: requests.Session) -> str:
    probes: list[str] = []
    headers = {"Referer": f"{EAMS_BASE}/eams/homeExt.action"}
    semester_id: str | None = None
    batch_id: str | None = None

    def hit(response: requests.Response, label: str) -> str:
        session.exam_probe = (
            f"hit={label} semester={semester_id} batch={batch_id} | " + " | ".join(probes)
        )
        return response.text

    def get(url: str, label: str, params: dict | None = None) -> requests.Response:
        response = _request(session, "GET", url, params=params, headers=headers)
        response.encoding = "utf-8"
        probes.append(f"{label}={_diag(response)}")
        if _looks_like_login(response.text):
            raise LoginError("未获得教务系统会话，登录流程未生效")
        return response

    # 课表页是同一会话下已知可用的参照，也能顺带拿到当前学期 ID
    course = get(f"{EAMS_BASE}/eams/courseTableForStd.action", "course")
    semester_id = parse_semester_id(course.text)

    shell = get(EXAM_SHELL_URL, "shell")
    if _is_exam_page(shell.text):
        return hit(shell, "shell")
    semester_id = semester_id or parse_semester_id(shell.text)
    batch_id = parse_exam_batch_id(shell.text)

    # 外壳页只负责加载，表格由 examBatch.id 对应的子页面渲染
    if batch_id:
        table = get(
            EXAM_TABLE_URL, f"table-batch{batch_id}", {"examBatch.id": batch_id}
        )
        if _is_exam_page(table.text):
            return hit(table, f"table-batch{batch_id}")
        semester_id = semester_id or parse_semester_id(table.text)

    table = get(EXAM_TABLE_URL, "table")
    if _is_exam_page(table.text):
        return hit(table, "table")
    semester_id = semester_id or parse_semester_id(table.text)

    form = {"project.id": "1"}
    if semester_id:
        form["semester.id"] = semester_id

    submitted = _request(
        session, "POST", EXAM_SHELL_URL, data=form, headers={"Referer": EXAM_SHELL_URL}
    )
    submitted.encoding = "utf-8"
    probes.append("shell-post=" + _diag(submitted))
    if _looks_like_login(submitted.text):
        raise LoginError("提交学期条件后要求重新登录")
    if _is_exam_page(submitted.text):
        return hit(submitted, "shell-post")

    posted_batch = parse_exam_batch_id(submitted.text)
    if posted_batch and posted_batch != batch_id:
        batch_id = posted_batch
        table = get(
            EXAM_TABLE_URL,
            f"table-posted-batch{posted_batch}",
            {"examBatch.id": posted_batch},
        )
        if _is_exam_page(table.text):
            return hit(table, f"table-posted-batch{posted_batch}")

    raise FetchError(
        "考试页中没有找到「考场座位号」表格；"
        f"semester={semester_id} batch={batch_id}；" + " | ".join(probes) + " | "
        f"{getattr(session, 'signin_probe', '')} | "
        f"{getattr(session, 'cas_probe', '')} | {getattr(session, 'eams_probe', '')}"
    )
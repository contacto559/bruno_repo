#!/usr/bin/env python3
"""Telegram -> Cursor Cloud Agents bridge (one worker per area).

Canonical logic from the Sylvia bridge: follow-up agent id reinjection,
model retry, TELEGRAM_DOCUMENT, expandable replies.
Identity and the prompt come from prompt_wrapper.py in the repo root
when that file exists. Does not share another area bot token.
"""
from __future__ import annotations

import argparse
import asyncio
import html
import json
import os
import re
import sys
import time
from datetime import datetime
import importlib.util
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from telegram import InputFile, Update
from telegram.constants import ChatAction, ParseMode
from telegram.error import BadRequest, TimedOut
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

# Uploads (PDF) need longer than PTB defaults (media_write_timeout=20s).
DOC_CONNECT_TIMEOUT = 30.0
DOC_READ_TIMEOUT = 120.0
DOC_WRITE_TIMEOUT = 120.0
DOC_SEND_RETRIES = 2

# Agent final message line → bridge attaches file on My Machines disk.
# TELEGRAM_DOCUMENT: G:\path\file.pdf | optional caption
TELEGRAM_DOC_LINE = re.compile(
    r"^TELEGRAM_DOCUMENT:\s*(.+?)(?:\s*\|\s*(.*))?$",
    re.IGNORECASE | re.MULTILINE,
)
TELEGRAM_DOC_BLOCK = re.compile(
    r"<<<TELEGRAM_DOCUMENT>>>\s*path:\s*(.+?)\s*(?:caption:\s*(.*?)\s*)?<<<END>>>",
    re.IGNORECASE | re.DOTALL,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENV = ROOT / ".env"

_AREA_PROMPT = None
_AREA_TRIED = False


def _area_prompt():
    """Load repo-root prompt_wrapper.py once. None if the area has no file."""
    global _AREA_PROMPT, _AREA_TRIED
    if _AREA_TRIED:
        return _AREA_PROMPT
    _AREA_TRIED = True
    path = ROOT / "prompt_wrapper.py"
    if not path.is_file():
        return None
    spec = importlib.util.spec_from_file_location("area_prompt_wrapper", path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _AREA_PROMPT = module
    return module


def active_plan_prefix() -> str:
    area = _area_prompt()
    custom = getattr(area, "PLAN_PREFIX", None) if area else None
    if isinstance(custom, str) and custom.strip():
        return custom
    return PLAN_PREFIX


API_BASE = "https://api.cursor.com/v1"
TG_MAX = 3900
# Long replies: first paragraph stays visible; the rest is Telegram expandable.
EXPANDABLE_MIN = 800
TERMINAL = frozenset({"FINISHED", "ERROR", "CANCELLED", "EXPIRED"})

# chat_id -> last agent id. Same chat continues that agent so a follow-up
# ("desde Wherex", "ayer a las 6") keeps the day and the sender.
# Dropped after FOLLOW_IDLE_SECONDS of silence so the thread does not grow all day.
FOLLOW_IDLE_SECONDS = 45 * 60
LAST_AGENT: dict[int, str] = {}
LAST_SEEN: dict[int, float] = {}
# chat_id -> "agent" | "plan". Sticky until /new, /agent, or /plan without text.
LAST_MODE: dict[int, str] = {}

# ---------- Busy-state / pending-queue -----------------------------------
# One run per chat. Text messages received while busy are queued (one slot).
# Media messages cannot be queued (Telegram file IDs expire) → ask resend.
_CHAT_BUSY: set[int] = set()
_CHAT_PENDING: dict[int, dict] = {}
_PENDING_ACK = (
    "Lo anoto. En cuanto te responda lo proceso. "
    "Si me mandas otro antes, reemplaza este."
)
_PENDING_REPLACE_ACK = "Reemplacé el anterior. Lo proceso cuando termine."
_MEDIA_BUSY_REPLY = (
    "Estoy con tu mensaje anterior. Cuando termine, mándame eso de nuevo."
)
# ---------- end busy-state -----------------------------------------------

PLAN_PREFIX = (
    "This run is Cursor Plan mode. Explore and draft a plan only. "
    "Do not edit files, do not restart services, do not run destructive commands. "
    "After CreatePlan, your final message MUST be the full plan in Chilean "
    "commercial Spanish (overview, steps, files, risks). "
    "Do not reply with a one-line status like 'revisando'.\n\n"
)
# My Machines worker writes plan cards here (not in run.result).
AGENT_STORES = Path.home() / ".local" / "state" / "cursor" / "agent-stores" / "cursor_agent_stores"
PLAN_OUTBOUND = ROOT / "media" / "outbound"

# Injected on every create/follow-up. UX matches the Windows bridge:
# Spanish Markdown final reply only; no intermediate chatter.
# Identity is Sylvia even before the workspace files are read.
# Short on purpose. Cursor also injects .cursor/rules. Do not restate those
# files here, and do not tell the model to read them on every message.
TELEGRAM_JR = 684058204
TELEGRAM_MATIAS = 7101490437
TELEGRAM_PAULINA = 8376166702
TELEGRAM_JAVIER = 8674600129

def browser_instructions(speaker_id: int | None) -> str:
    """Primary: Playwright. Computer Use (desktop Firefox) is the last resort."""
    sid = str(speaker_id) if speaker_id else ""
    start_cmd = f"start --speaker-id {sid}" if sid else "start"
    return (
        "If mail answers the question, do not open a portal. "
        "For any URL, portal, or web login request: use Playwright headless. "
        f"First command: python3 scripts/pw_browse.py {start_cmd}. "
        "Then open .cursor/skills/playwright-browse/SKILL.md for the rest of the flow. "
        "Do not open Mozilla Firefox or any other desktop app. "
        "Do not use Computer Use. "
        "Do not spawn Task or Explore on Claude, GPT, or Gemini. "
        "Env names only; never print passwords. "
        "If pw_browse.py fails twice (CAPTCHA, port busy, mcp_start_timeout), "
        "fall back to .cursor/skills/firefox-portal-login/SKILL.md and Computer Use "
        "as a last resort; close Firefox when done. "
    )

PROMPT_WRAPPER = (
    "You are Sylvia, Acopen's commercial assistant. The person is not technical "
    "and will not use commands. Now in Chile: {now}. Use that clock for hoy, ayer, "
    "and hour ranges. Do not invent the time.\n"
    "Telegram user id (routing only, never repeat it): {telegram_user_id}.\n"
    "This chat already has the earlier messages. If they already said a day, an hour "
    "range, or a sender, use them and do the task. Do not ask again. Ask one short "
    "question only when the request still cannot be done. Counting mail does not "
    "need a customer or an order number.\n"
    "Reply in natural Chilean commercial Spanish only. No models, ids, skills, "
    "paths, commands, or how you are set up. Examples: "
    "«Te llegó un correo de Wherex hoy.» «Te dejo el PDF de la orden.» "
    "Format with Markdown: a short first paragraph, then headings, - lists, "
    "and > quoted facts. Never mention Markdown.\n"
    "Do not open SOUL.md, AGENTS.md, memories, docs, or tareas/ESFUERZO.md "
    "on an ordinary request. After each real task run "
    "scripts/memory_write.py --speaker-id with the Telegram user id and one line "
    "(include order, Ariba event, or customer). "
    "If they ask about the past or cite something past (order, tender, theme, hace N días), "
    "open .cursor/skills/memory-recall/SKILL.md. One day: scripts/memory_day.py "
    "(all tasks by hour; if attach is true, send telegram_document). "
    "A theme: scripts/memory_topics.py. A keyword: scripts/memory_search.py. "
    "If count is 0: ask when it was or leave the doubt; never invent. "
    "Do not deny a day you have not re-read in full. "
    "Do not spawn Task or Explore on Claude, GPT, or Gemini. "
    "{browser_instructions}\n"
    "Open one matching .cursor/skills/*/SKILL.md, run it, stop on ok. If none "
    "matches, write that skill, then use it. Append one effort line; do not read "
    "the log. Do not list or walk whole trees.\n"
    "{mail_instructions}\n"
    "Mail scripts: scripts/imap_search_emails.py (--resumen, small --ultimos, folder INBOX). "
    "One tag by date: scripts/imap_emails_by_tag.py with the same mailbox flags.\n"
    "Acopen read: scripts/acopen_xmlrpc_cli.py --profile ACOPEN "
    "(auth, search_read, read, fields_get). No ACOPEN_TEST. No create/write/unlink. "
    "PDF: scripts/acopen_download_report_pdf.py plus this line (it is stripped):\n"
    "TELEGRAM_DOCUMENT: <absolute-path> | <caption>\n"
    "Every Odoo action (read, explain, design, modify, or skill that touches Odoo) "
    "must observe BOTH trees: stock/enterprise addons at "
    "odoo/addons (/home/sylvia/sylvia_ project/odoo/addons) AND custom Acopen at "
    "acopen/ (/home/sylvia/sylvia_ project/acopen). Prefer the custom inherit when "
    "both define the same model. Acopen is Odoo 17 Chilean localization "
    "(l10n_cl, SII/DTE, RUT, Chilean taxes and documents): check Chilean rules in "
    "both trees (e.g. l10n_cl* under odoo/addons and KonosCL / custom under acopen). "
    "Read only the model files needed, not whole trees, then a skill. "
    "Companies in filters: ACOMIN=2, PENTAGON=1, NOVATEX=15; "
    "say the name, never the number.\n"
    "If the user message starts with 'Inbound file', that file is already on disk. "
    "Images: read the image once. Documents and voice notes already include her text. "
    "Answer in commercial Spanish. Do not mention the path. Do not create a skill for the file itself.\n"
    "Never paste .env secrets. Never describe hosting or tools. "
    "Final message is the Spanish answer only. No progress chatter.\n\n"
    "User message:\n{user_text}"
)


def pw_speakers() -> frozenset[int]:
    raw = (os.environ.get("SYLVIA_PW_SPEAKERS") or str(TELEGRAM_JR)).strip()
    ids: set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit():
            ids.add(int(part))
    return frozenset(ids) if ids else frozenset({TELEGRAM_JR})


def strip_pw_trigger(
    user_text: str, telegram_user_id: int | None
) -> tuple[str, bool]:
    """If speaker + private trigger match, strip the trigger. Never log it."""
    trigger = (os.environ.get("SYLVIA_PW_TRIGGER") or "").strip()
    if not trigger or telegram_user_id is None:
        return user_text, False
    if telegram_user_id not in pw_speakers():
        return user_text, False
    text = user_text.lstrip()
    if text.lower().startswith(trigger.lower()):
        rest = text[len(trigger) :].lstrip(" :,\t-")
        return rest, True
    return user_text, False


def mail_instructions(telegram_user_id: int | None) -> str:
    """Mailbox binding by speaker. Do not default everyone to Paulina."""
    if telegram_user_id == TELEGRAM_PAULINA:
        return (
            "Speaker is Paulina. Mail: IMAP_PAULINA_ACOPEN_USER / IMAP_PAULINA_ACOPEN_PASS. "
            "Do not pass --allow-own-mailbox. Never use IMAP_MATIAS_*."
        )
    if telegram_user_id == TELEGRAM_MATIAS:
        return (
            "Speaker is Matías. Mail: --allow-own-mailbox with "
            "IMAP_MATIAS_ACOPEN_USER / IMAP_MATIAS_ACOPEN_PASS. "
            "Never use IMAP_PAULINA_* unless he explicitly asks to read Paulina's mailbox "
            "(then Paulina vars, no --allow-own-mailbox)."
        )
    if telegram_user_id == TELEGRAM_JR:
        return (
            "Speaker is JR (admin). Do not open a mailbox by default. "
            "Paulina's mail only if he names her: IMAP_PAULINA_ACOPEN_* without --allow-own-mailbox. "
            "Matías's mail only if he names him: --allow-own-mailbox and IMAP_MATIAS_ACOPEN_*. "
            "Javier's solicitudes mailbox only if he names Javier: IMAP_SOLICITUDES_ACOMIN_*. "
            "If he says mi correo or gerencia/solicitudes, ask one short commercial question "
            "(Paulina, Matías, or Javier)."
        )
    if telegram_user_id == TELEGRAM_JAVIER:
        return (
            "Speaker is Javier (solicitudes). Mail: IMAP_SOLICITUDES_ACOMIN_USER / "
            "IMAP_SOLICITUDES_ACOMIN_PASS. No --allow-own-mailbox needed. "
            "Acopen profile ACOPEN. Wherex: WHEREX_DEFAULT_USER / WHEREX_DEFAULT_PASSWORD. "
            "Never use IMAP_PAULINA_* or IMAP_MATIAS_* unless he explicitly names that mailbox."
        )
    return (
        "Unknown speaker. Do not open mail until the request names Paulina or Matías. "
        "Paulina: IMAP_PAULINA_ACOPEN_* without --allow-own-mailbox. "
        "Matías: --allow-own-mailbox and IMAP_MATIAS_ACOPEN_*."
    )


def prompt_for(user_text: str, telegram_user_id: int | None = None) -> str:
    now = datetime.now(ZoneInfo("America/Santiago")).strftime("%Y-%m-%d %H:%M")
    cleaned, _alt = strip_pw_trigger(user_text, telegram_user_id)
    area = _area_prompt()
    custom = getattr(area, "prompt_for", None) if area else None
    if callable(custom):
        return custom(cleaned, telegram_user_id, now)
    return PROMPT_WRAPPER.format(
        user_text=cleaned,
        now=now,
        telegram_user_id=telegram_user_id if telegram_user_id else "unknown",
        mail_instructions=mail_instructions(telegram_user_id),
        browser_instructions=browser_instructions(telegram_user_id),
    )


def remember_agent(chat_id: int, agent_id: str) -> None:
    LAST_AGENT[chat_id] = agent_id
    LAST_SEEN[chat_id] = time.time()


def live_agent(chat_id: int) -> str | None:
    agent_id = LAST_AGENT.get(chat_id)
    seen = LAST_SEEN.get(chat_id, 0.0)
    if not agent_id:
        return None
    if time.time() - seen > FOLLOW_IDLE_SECONDS:
        LAST_AGENT.pop(chat_id, None)
        LAST_SEEN.pop(chat_id, None)
        return None
    return agent_id


def normalize_user_text(text: str) -> str:
    """Strip an optional leading wake word so prompts stay clean."""
    raw = (text or "").strip()
    if not raw:
        return raw
    lower = raw.lower()
    for name in ("sylvia", "jarvis"):
        for prefix in (f"{name},", f"{name}:", f"{name} ", f"{name}\n"):
            if lower.startswith(prefix):
                return raw[len(prefix) :].lstrip()
        if lower == name:
            return raw
    return raw


def load_env(path: Path) -> None:
    if not path.is_file():
        raise SystemExit(f"FAIL: env file not found: {path}")
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        os.environ.setdefault(key, value.strip())
    apply_env_aliases()


def apply_env_aliases() -> None:
    """Map Sylvia .env names onto the bridge variable names."""
    pairs = (
        ("TELEGRAM_BOT_TOKEN", "telegram_api_key"),
        ("CURSOR_API_KEY", "api_key_cursor"),
    )
    for canon, alias in pairs:
        if (os.environ.get(canon) or "").strip():
            continue
        value = (os.environ.get(alias) or "").strip()
        if value:
            os.environ[canon] = value
    os.environ.setdefault("AGENT_RUNTIME", "machine")
    os.environ.setdefault("DEFAULT_BRANCH", "main")
    os.environ.setdefault("AUTO_CREATE_PR", "false")
    os.environ.setdefault("RUN_TIMEOUT_SECONDS", "3600")


def parse_allowed_user_ids() -> frozenset[int]:
    ids: set[int] = set()
    raw = (os.environ.get("ALLOWED_TELEGRAM_USER_IDS") or "").strip()
    for part in raw.split(","):
        part = part.strip()
        if part:
            ids.add(int(part))
    single = (os.environ.get("ALLOWED_TELEGRAM_USER_ID") or "").strip()
    if single:
        ids.add(int(single))
    if not ids:
        raise SystemExit(
            "FAIL: missing ALLOWED_TELEGRAM_USER_IDS (or ALLOWED_TELEGRAM_USER_ID)"
        )
    return frozenset(ids)


def require_env(name: str) -> str:
    value = (os.environ.get(name) or "").strip()
    if not value:
        raise SystemExit(f"FAIL: missing {name} in environment / .env")
    return value


def env_bool(name: str, default: bool = False) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def cursor_headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def check_cursor_api(api_key: str) -> dict:
    response = requests.get(
        f"{API_BASE}/me",
        headers=cursor_headers(api_key),
        timeout=30,
    )
    if response.status_code != 200:
        raise SystemExit(
            f"FAIL: Cursor API /v1/me returned HTTP {response.status_code}"
        )
    return response.json()


def collect_env_vars_for_cloud() -> dict[str, str]:
    """Pass selected local .env keys into the Cloud Agent (session-scoped).

    Cloud VMs do NOT see the gitignored local .env unless we inject envVars
    or configure Secrets in the Cursor dashboard.
    """
    prefixes = (
        "ODOO_",
        "IMAP_",
        "BENDER_",
        "ARIBA_",
        "WHEREX_",
        "SENEGOCIA_",
        "CODELCO_",
        "OLLAMA_",
        "OPENAI_",
    )
    # Never forward Telegram/Cursor bridge credentials into the agent VM.
    deny = {
        "TELEGRAM_BOT_TOKEN",
        "ALLOWED_TELEGRAM_USER_ID",
        "ALLOWED_TELEGRAM_USER_IDS",
        "telegram_api_key",
        "api_key_cursor",
        "CURSOR_API_KEY",
        "DEFAULT_REPO_URL",
        "DEFAULT_BRANCH",
        "AUTO_CREATE_PR",
        "AGENT_RUNTIME",
        "MACHINE_NAME",
    }
    out: dict[str, str] = {}
    for key, value in os.environ.items():
        if key in deny or not value:
            continue
        if any(key.startswith(p) for p in prefixes):
            # API limit: names <= 255 bytes, values <= 4096, max 50 entries.
            if len(key.encode()) > 255 or len(value.encode()) > 4096:
                continue
            out[key] = value
        if len(out) >= 50:
            break
    return out


def normalize_mode(mode: str | None) -> str:
    value = (mode or "agent").strip().lower()
    return "plan" if value == "plan" else "agent"


def chat_mode(chat_id: int) -> str:
    return normalize_mode(LAST_MODE.get(chat_id))


def set_chat_mode(chat_id: int, mode: str) -> str:
    value = normalize_mode(mode)
    LAST_MODE[chat_id] = value
    return value


def _iso_timestamp(value: str) -> float | None:
    text = (value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text).timestamp()
    except ValueError:
        return None


def response_is_capacity(response: requests.Response) -> bool:
    """Cursor sometimes returns 503 after the run was already created.

    Forum (Oct 2026): Composer 2.5 peaks are retryable. The body we saw is
    {"code":"unavailable","message":"Server at capacity"}.
    """
    if response.status_code != 503:
        return False
    body = (response.text or "").lower()
    return "server at capacity" in body or "unavailable" in body


def _cursor_get(api_key: str, path: str) -> dict | None:
    try:
        response = requests.get(
            f"{API_BASE}{path}",
            headers=cursor_headers(api_key),
            timeout=30,
        )
    except requests.RequestException as exc:
        print(f"BRIDGE capacity lookup failed: {exc}", flush=True)
        return None
    if response.status_code >= 400:
        return None
    data = response.json()
    return data if isinstance(data, dict) else None


def adopt_run_after_capacity(
    api_key: str,
    *,
    started: float,
    machine_name: str = "",
    agent_id: str | None = None,
) -> dict | None:
    """Return agent/run ids when a 503 still left a live run on the server."""
    newest: tuple[float, str, str] | None = None

    def consider(agent: dict) -> None:
        nonlocal newest
        aid = str(agent.get("id") or "")
        run_id = str(agent.get("latestRunId") or "")
        if not aid or not run_id:
            return
        env = agent.get("env") if isinstance(agent.get("env"), dict) else {}
        if machine_name and env.get("name") and env.get("name") != machine_name:
            return
        stamp = _iso_timestamp(str(agent.get("updatedAt") or ""))
        if stamp is None or stamp + 15 < started:
            return
        if newest is None or stamp > newest[0]:
            newest = (stamp, aid, run_id)

    if agent_id:
        agent = _cursor_get(api_key, f"/agents/{agent_id}")
        if agent:
            consider(agent.get("agent") if isinstance(agent.get("agent"), dict) else agent)
    else:
        page = _cursor_get(api_key, "/agents?limit=5")
        items = []
        if isinstance(page, dict):
            raw = page.get("agents") or page.get("items") or []
            if isinstance(raw, list):
                items = raw
        for item in items:
            if not isinstance(item, dict):
                continue
            if item.get("env"):
                consider(item)
                continue
            full = _cursor_get(api_key, f"/agents/{item.get('id')}")
            if isinstance(full, dict):
                consider(full.get("agent") if isinstance(full.get("agent"), dict) else full)

    if newest is None:
        return None
    _, aid, run_id = newest
    print(f"BRIDGE adopted run after capacity response agent={aid} run={run_id}", flush=True)
    return {"agent": {"id": aid, "latestRunId": run_id}, "run": {"id": run_id}}


def post_or_adopt(
    api_key: str,
    url: str,
    payload: dict,
    *,
    machine_name: str = "",
    agent_id: str | None = None,
) -> dict:
    """POST a create/follow-up. On capacity 503, poll the run Cursor already started."""
    started = time.time()
    last_error = "capacity"
    for attempt in range(3):
        response = requests.post(
            url,
            headers=cursor_headers(api_key),
            data=json.dumps(payload),
            timeout=180,
        )
        if response.status_code < 400:
            data = response.json()
            return data if isinstance(data, dict) else {}
        last_error = f"HTTP {response.status_code}: {response.text[:800]}"
        if not response_is_capacity(response):
            break
        print(
            f"BRIDGE capacity attempt {attempt + 1}: {last_error[:180]}",
            flush=True,
        )
        time.sleep(2)
        adopted = adopt_run_after_capacity(
            api_key,
            started=started,
            machine_name=machine_name,
            agent_id=agent_id,
        )
        if adopted:
            return adopted
        if attempt < 2:
            time.sleep(2 + attempt * 2)
    raise RuntimeError(last_error)


def create_agent(
    api_key: str,
    repo: str,
    branch: str,
    text: str,
    *,
    auto_create_pr: bool,
    runtime: str = "cloud",
    machine_name: str = "",
    telegram_user_id: int | None = None,
    mode: str = "agent",
) -> dict:
    """Create agent via official API.

    runtime=cloud  -> Cursor-hosted VM (needs secrets/envVars for private creds)
    runtime=machine -> My Machines worker on your PC (official; tools run locally)
    mode=plan -> Cloud Agents Plan mode (explore + draft; no implement by default)
    """
    mode = normalize_mode(mode)
    prompt_text = prompt_for(text, telegram_user_id)
    if mode == "plan":
        prompt_text = active_plan_prefix() + prompt_text
    payload: dict = {
        "prompt": {"text": prompt_text},
        "repos": [{"url": repo, "startingRef": branch}],
        "autoCreatePR": auto_create_pr,
        # Auto in the UI is model id "default" (aliases include "auto").
        # Omitting model uses the account default, which is often a premium
        # model and burns tokens. Force Auto unless CURSOR_MODEL_ID overrides.
        "model": {"id": cursor_model_id()},
        "mode": mode,
    }
    runtime = (runtime or "cloud").strip().lower()
    if runtime == "machine":
        if not machine_name:
            raise RuntimeError("AGENT_RUNTIME=machine requires MACHINE_NAME in .env")
        # Official My Machines target — no IDE scraping.
        payload["env"] = {"type": "machine", "name": machine_name}
        # Local worker already has disk/.env; dashboard envVars often don't apply.
    else:
        env_vars = collect_env_vars_for_cloud()
        if env_vars:
            payload["envVars"] = env_vars
    # Creating a machine-backed agent can sit >60s if the worker is slow/offline.
    # A 503 "Server at capacity" can still leave the run running; adopt it.
    return post_or_adopt(
        api_key,
        f"{API_BASE}/agents",
        payload,
        machine_name=machine_name if runtime == "machine" else "",
    )


def cursor_model_id() -> str:
    """Cloud Agents Auto = id 'default'. Override with CURSOR_MODEL_ID if needed."""
    return (os.environ.get("CURSOR_MODEL_ID") or "default").strip() or "default"


def followup_agent(
    api_key: str,
    agent_id: str,
    text: str,
    telegram_user_id: int | None = None,
    mode: str | None = None,
) -> dict:
    mode = normalize_mode(mode) if mode is not None else None
    prompt_text = prompt_for(text, telegram_user_id)
    if mode == "plan":
        prompt_text = active_plan_prefix() + prompt_text
    prompt = {"text": prompt_text}
    base: dict = {"prompt": prompt, "model": {"id": cursor_model_id()}}
    if mode:
        base["mode"] = mode
    payloads = [
        base,
        # Older run endpoints may reject model/mode; keep the thread alive.
        {k: v for k, v in base.items() if k != "model"},
        {"prompt": prompt},
    ]
    last_error = ""
    url = f"{API_BASE}/agents/{agent_id}/runs"
    for payload in payloads:
        try:
            return post_or_adopt(api_key, url, payload, agent_id=agent_id)
        except RuntimeError as exc:
            last_error = str(exc)
            if "server at capacity" in last_error.lower() or "unavailable" in last_error.lower():
                raise
            if payload == {"prompt": prompt}:
                break
            print(f"BRIDGE followup rejected, retry leaner: {last_error[:200]}", flush=True)
    raise RuntimeError(last_error or "followup failed")


def get_run(api_key: str, agent_id: str, run_id: str) -> dict:
    response = requests.get(
        f"{API_BASE}/agents/{agent_id}/runs/{run_id}",
        headers=cursor_headers(api_key),
        timeout=30,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"HTTP {response.status_code}: {response.text[:800]}")
    data = response.json()
    return data.get("run") if isinstance(data.get("run"), dict) else data


def extract_agent_id(data: dict) -> str | None:
    agent = data.get("agent") if isinstance(data.get("agent"), dict) else data
    if isinstance(agent, dict):
        agent_id = agent.get("id") or data.get("id")
        if agent_id:
            return str(agent_id)
    return None


def extract_run_id(data: dict) -> str | None:
    run = data.get("run") if isinstance(data.get("run"), dict) else None
    if isinstance(run, dict) and run.get("id"):
        return str(run["id"])
    if data.get("latestRunId"):
        return str(data["latestRunId"])
    agent = data.get("agent") if isinstance(data.get("agent"), dict) else None
    if isinstance(agent, dict) and agent.get("latestRunId"):
        return str(agent["latestRunId"])
    return None


async def wait_for_run_result(
    api_key: str,
    agent_id: str,
    run_id: str,
    *,
    bot,
    chat_id: int,
    poll_seconds: float = 4.0,
    timeout_seconds: float = 3600.0,
) -> dict:
    """Poll Cursor run; keep Telegram 'typing…' visible while waiting.

    Network errors during polling (ConnectionError, Timeout, HTTP 5xx after
    retries) are logged but do not abort the loop — the agent keeps running in
    Cursor and may finish while we wait. Only a hard timeout or a terminal
    status ends the loop.
    """
    deadline = time.monotonic() + timeout_seconds
    last: dict = {}
    consecutive_poll_errors = 0
    _MAX_POLL_ERRORS = 10  # ~40 s of failures before giving up
    beat = asyncio.create_task(_typing_heartbeat(bot, chat_id))
    try:
        while time.monotonic() < deadline:
            try:
                last = await asyncio.to_thread(get_run, api_key, agent_id, run_id)
                consecutive_poll_errors = 0
                status = str(last.get("status") or "").upper()
                if status in TERMINAL:
                    return last
            except Exception as exc:  # noqa: BLE001
                consecutive_poll_errors += 1
                print(
                    f"BRIDGE poll_error {consecutive_poll_errors}/{_MAX_POLL_ERRORS} "
                    f"run={run_id[:8]} {exc.__class__.__name__}: {str(exc)[:120]}",
                    flush=True,
                )
                if consecutive_poll_errors >= _MAX_POLL_ERRORS:
                    raise RuntimeError(
                        f"Cursor poll failed {_MAX_POLL_ERRORS} times in a row: {exc}"
                    ) from exc
            await asyncio.sleep(min(poll_seconds, 4.0))
        raise TimeoutError(
            f"Run {run_id} still not terminal after {int(timeout_seconds)}s "
            f"(last status={last.get('status')})"
        )
    finally:
        beat.cancel()
        try:
            await beat
        except asyncio.CancelledError:
            pass


def find_latest_plan_md(agent_id: str | None = None) -> Path | None:
    """Newest *.plan.md under the worker agent-store (Plan mode artifact)."""
    roots: list[Path] = []
    if agent_id and AGENT_STORES.is_dir():
        candidate = AGENT_STORES / agent_id
        if candidate.is_dir():
            roots.append(candidate)
    if AGENT_STORES.is_dir():
        roots.append(AGENT_STORES)
    newest: Path | None = None
    newest_mtime = 0.0
    for root in roots:
        try:
            for path in root.rglob("*.plan.md"):
                if not path.is_file():
                    continue
                try:
                    mtime = path.stat().st_mtime
                except OSError:
                    continue
                if mtime >= newest_mtime:
                    newest_mtime = mtime
                    newest = path
        except OSError:
            continue
    return newest


def plan_body_for_telegram(plan_path: Path) -> str:
    """Strip YAML frontmatter; keep markdown body for Telegram HTML convert."""
    raw = plan_path.read_text(encoding="utf-8", errors="replace")
    if raw.startswith("---"):
        end = raw.find("\n---", 3)
        if end != -1:
            raw = raw[end + 4 :].lstrip("\n")
    return raw.strip()


def plan_overview(plan_path: Path) -> str:
    raw = plan_path.read_text(encoding="utf-8", errors="replace")
    if raw.startswith("---"):
        end = raw.find("\n---", 3)
        if end != -1:
            head = raw[3:end]
            for line in head.splitlines():
                if line.strip().startswith("overview:"):
                    value = line.split(":", 1)[1].strip().strip("'\"")
                    if value:
                        return value
    return "Plan listo para revisar."


def copy_plan_outbound(plan_path: Path) -> Path:
    PLAN_OUTBOUND.mkdir(parents=True, exist_ok=True)
    dest = PLAN_OUTBOUND / plan_path.name
    dest.write_bytes(plan_path.read_bytes())
    return dest


def format_reply(run: dict, *, mode: str = "agent", agent_id: str | None = None) -> str:
    """User-facing Telegram text only — no status line.

    Plan mode: prefer the worker *.plan.md artifact over a short run.result.
    """
    status = str(run.get("status") or "").upper()
    result = (run.get("result") or "").strip()
    if status and status != "FINISHED" and not result:
        print(f"BRIDGE_ERROR: run status {status}", flush=True)
        return "No pude completar eso ahora. Escríbeme de nuevo en un rato."

    if normalize_mode(mode) == "plan":
        plan_path = find_latest_plan_md(agent_id)
        if plan_path and plan_path.is_file():
            try:
                outbound = copy_plan_outbound(plan_path)
                body = plan_body_for_telegram(plan_path)
                overview = plan_overview(plan_path)
                print(f"BRIDGE plan artifact={plan_path}", flush=True)
                # Document only — Telegram renders Markdown; do not paste the body.
                _ = body  # body written to outbound file
                lead = (
                    f"Plan listo: {overview}\n\n"
                    "Cómo seguir (abre el .md adjunto):\n"
                    "• Aceptar e implementar:\n"
                    "  /agent Implementa el plan\n"
                    "• Pedir cambios al plan (sin implementar):\n"
                    "  /plan Cambia esto: …\n"
                    "• Solo activar Plan / Agent sin texto:\n"
                    "  /plan   o   /agent\n"
                    "• Empezar de cero: /new\n"
                    "Tras el plan vuelvo a modo Agent."
                )
                return (
                    f"{lead}\n\n"
                    f"TELEGRAM_DOCUMENT: {outbound.resolve()} | Plan Sylvia"
                )
            except OSError as exc:
                print(f"BRIDGE_ERROR: plan artifact read {exc}", flush=True)

    if not result:
        print("BRIDGE_ERROR: empty result", flush=True)
        return "No me quedó nada para contarte. ¿Me lo pides de otra forma?"
    parts = [result]
    git = run.get("git") if isinstance(run.get("git"), dict) else {}
    branches = git.get("branches") if isinstance(git, dict) else None
    if isinstance(branches, list):
        for item in branches:
            if not isinstance(item, dict):
                continue
            pr = item.get("prUrl")
            if pr:
                parts.append(f"PR: {pr}")
    return "\n\n".join(parts)


def chunk_text(text: str, size: int = TG_MAX) -> list[str]:
    """Split long replies; prefer paragraph boundaries so Markdown stays intact."""
    if len(text) <= size:
        return [text]
    chunks: list[str] = []
    rest = text
    while rest:
        if len(rest) <= size:
            chunks.append(rest)
            break
        cut = rest.rfind("\n\n", 0, size)
        if cut < size // 3:
            cut = rest.rfind("\n", 0, size)
        if cut < size // 3:
            cut = size
        chunks.append(rest[:cut].rstrip())
        rest = rest[cut:].lstrip()
    return chunks


def wrap_expandable_html(html_body: str, source_len: int) -> str:
    """Keep a short lead visible; fold the rest into Telegram expandable quote."""
    if source_len < EXPANDABLE_MIN or not html_body:
        return html_body
    parts = re.split(r"\n\n", html_body, maxsplit=1)
    if len(parts) == 2 and parts[0].strip() and parts[1].strip():
        return f"{parts[0]}\n\n<blockquote expandable>{parts[1]}</blockquote>"
    return f"<blockquote expandable>{html_body}</blockquote>"


def markdown_to_telegram_html(text: str) -> str:
    """Convert common Markdown to Telegram HTML (more reliable than MarkdownV2)."""
    if not text:
        return text

    fences: list[str] = []

    def _fence(match: re.Match[str]) -> str:
        code = match.group(2) or ""
        fences.append(f"<pre><code>{html.escape(code)}</code></pre>")
        return f"\x00FENCE{len(fences) - 1}\x00"

    out = re.sub(r"```([^\n`]*)\n?(.*?)```", _fence, text, flags=re.DOTALL)

    inlines: list[str] = []

    def _inline(match: re.Match[str]) -> str:
        inlines.append(f"<code>{html.escape(match.group(1))}</code>")
        return f"\x00INLINE{len(inlines) - 1}\x00"

    out = re.sub(r"`([^`\n]+)`", _inline, out)

    links: list[str] = []

    def _link(match: re.Match[str]) -> str:
        label = html.escape(match.group(1))
        url = match.group(2).strip()
        if not re.match(r"^https?://", url, flags=re.I):
            return html.escape(match.group(0))
        links.append(f'<a href="{html.escape(url, quote=True)}">{label}</a>')
        return f"\x00LINK{len(links) - 1}\x00"

    out = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", _link, out)

    quotes: list[str] = []

    def _quote(match: re.Match[str]) -> str:
        lines = [re.sub(r"^>\s?", "", line) for line in match.group(0).splitlines()]
        quotes.append(f"<blockquote>{html.escape(chr(10).join(lines))}</blockquote>")
        return f"\x00QUOTE{len(quotes) - 1}\x00"

    out = re.sub(r"(?m)^(> ?.*(?:\n> ?.*)*)", _quote, out)
    out = re.sub(r"(?m)^(?:[-*]|\d+\.)\s+", "• ", out)

    # Escape remaining text, then restore bold/italic markers as tags.
    out = html.escape(out)
    out = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", out, flags=re.DOTALL)
    out = re.sub(r"__(.+?)__", r"<b>\1</b>", out, flags=re.DOTALL)
    out = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<i>\1</i>", out, flags=re.DOTALL)
    out = re.sub(r"~~(.+?)~~", r"<s>\1</s>", out, flags=re.DOTALL)
    # Headings → bold line
    out = re.sub(r"(?m)^#{1,6}\s+(.+)$", r"<b>\1</b>", out)

    for i, block in enumerate(fences):
        out = out.replace(f"\x00FENCE{i}\x00", block)
    for i, block in enumerate(inlines):
        out = out.replace(f"\x00INLINE{i}\x00", block)
    for i, block in enumerate(links):
        out = out.replace(f"\x00LINK{i}\x00", block)
    for i, block in enumerate(quotes):
        out = out.replace(f"\x00QUOTE{i}\x00", block)
    return wrap_expandable_html(out, len(text))


def _normalize_doc_path(raw: str) -> Path:
    path = (raw or "").strip().strip('"').strip("'")
    if path.lower().startswith("file://"):
        path = path[7:]
    # Windows: file:///G:/... → /G:/... → G:/...
    if re.match(r"^/[A-Za-z]:/", path):
        path = path[1:]
    return Path(path)


def split_telegram_documents(text: str) -> tuple[str, list[dict[str, str]]]:
    """Extract TELEGRAM_DOCUMENT markers; return (clean_text, [{path, caption}])."""
    docs: list[dict[str, str]] = []

    def _from_block(match: re.Match[str]) -> str:
        docs.append(
            {
                "path": str(_normalize_doc_path(match.group(1))),
                "caption": (match.group(2) or "").strip(),
            }
        )
        return ""

    cleaned = TELEGRAM_DOC_BLOCK.sub(_from_block, text or "")

    def _from_line(match: re.Match[str]) -> str:
        docs.append(
            {
                "path": str(_normalize_doc_path(match.group(1))),
                "caption": (match.group(2) or "").strip(),
            }
        )
        return ""

    cleaned = TELEGRAM_DOC_LINE.sub(_from_line, cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return cleaned, docs


async def reply_chunks(message, text: str) -> None:
    """Send reply as rendered Markdown (via Telegram HTML), with plain fallback."""
    for part in chunk_text(text):
        html_body = markdown_to_telegram_html(part)
        try:
            await message.reply_text(
                html_body,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )
            continue
        except BadRequest:
            pass
        try:
            await message.reply_text(
                part,
                parse_mode=ParseMode.MARKDOWN,
                disable_web_page_preview=True,
            )
            continue
        except BadRequest:
            await message.reply_text(part, disable_web_page_preview=True)


async def reply_text_and_documents(message, text: str) -> None:
    """Attach PDFs/files marked by the agent, then send remaining Markdown text."""
    body, docs = split_telegram_documents(text)
    for doc in docs:
        path = Path(doc["path"])
        if not path.is_file():
            await message.reply_text(f"FAIL: archivo no encontrado:\n`{path}`")
            continue
        caption = (doc.get("caption") or "")[:1024] or None
        size_kb = path.stat().st_size // 1024
        last_exc: Exception | None = None
        for attempt in range(1, DOC_SEND_RETRIES + 1):
            try:
                with path.open("rb") as fh:
                    await message.reply_document(
                        document=InputFile(fh, filename=path.name),
                        caption=caption,
                        connect_timeout=DOC_CONNECT_TIMEOUT,
                        read_timeout=DOC_READ_TIMEOUT,
                        write_timeout=DOC_WRITE_TIMEOUT,
                    )
                last_exc = None
                break
            except TimedOut as exc:
                last_exc = exc
                print(
                    f"WARN: Telegram document timeout "
                    f"({path.name} {size_kb}KB) attempt {attempt}/{DOC_SEND_RETRIES}",
                    flush=True,
                )
                await asyncio.sleep(2 * attempt)
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                break
        if last_exc is not None:
            await message.reply_text(
                f"FAIL: no se pudo enviar {path.name} ({size_kb} KB): {last_exc}\n"
                f"El archivo quedó en:\n`{path}`"
            )
    if body:
        await reply_chunks(message, body)
    elif not docs:
        await reply_chunks(message, text or "Sin texto de respuesta.")


def allowed(update: Update, allowed_user_id) -> bool:
    user = update.effective_user
    if not user:
        return False
    if isinstance(allowed_user_id, (set, frozenset, list, tuple)):
        return user.id in allowed_user_id
    return user.id == allowed_user_id


async def _typing(bot, chat_id: int) -> None:
    """Telegram clears 'typing…' if the bot sends any message; only use chat actions while waiting."""
    try:
        await bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
    except Exception as exc:  # noqa: BLE001
        print(f"TYPING_ERROR chat={chat_id} {exc.__class__.__name__}: {exc}", flush=True)


async def _typing_heartbeat(bot, chat_id: int, interval: float = 4.0) -> None:
    """Telegram drops the typing indicator after ~5s; refresh until cancelled."""
    print(f"TYPING_START chat={chat_id}", flush=True)
    try:
        while True:
            await _typing(bot, chat_id)
            await asyncio.sleep(interval)
    except asyncio.CancelledError:
        raise


async def _run_blocking_with_typing(bot, chat_id: int, fn):
    """Run a blocking callable while keeping Telegram typing visible."""
    beat = asyncio.create_task(_typing_heartbeat(bot, chat_id))
    try:
        return await asyncio.to_thread(fn)
    finally:
        beat.cancel()
        try:
            await beat
        except asyncio.CancelledError:
            pass


# ---------- Busy-state helpers -------------------------------------------

def _msg_sender(message) -> tuple[str | None, str | None, str | None]:
    """Telegram date plus the person who sent the message."""
    if message is None:
        return None, None, None
    msg_date = message.date.isoformat() if getattr(message, "date", None) else None
    user = getattr(message, "from_user", None)
    if user is None:
        return msg_date, None, None
    name = (user.full_name or "").strip() or None
    username = (user.username or "").strip() or None
    return msg_date, name, username


def _extract_doc_path(text: str) -> str | None:
    """Return first TELEGRAM_DOCUMENT path from a reply text, or None."""
    match = TELEGRAM_DOC_LINE.search(text or "")
    return match.group(1).strip() if match else None


def _log_msg(
    *,
    direction: str,
    chat_id: int,
    user_id: int | None,
    text: str,
    message_id: int | None = None,
    msg_date: str | None = None,
    sender_name: str | None = None,
    sender_username: str | None = None,
    doc_path: str | None = None,
    agent_id: str | None = None,
    run_id: str | None = None,
) -> None:
    """Append one JSON line to ROOT/data/messages.jsonl."""
    entry = {
        "ts": datetime.now().astimezone().isoformat(),
        "direction": direction,
        "chat_id": chat_id,
        "user_id": user_id,
        "message_id": message_id,
        "msg_date": msg_date,
        "sender_name": sender_name,
        "sender_username": sender_username,
        "text": (text or "")[:5000],
        "doc_path": doc_path,
        "agent_id": agent_id,
        "run_id": run_id,
    }
    log_path = ROOT / "data" / "messages.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError as exc:
        print(f"LOG_ERROR: {exc}", flush=True)


def _claim_chat(chat_id: int) -> bool:
    """True if this coroutine owns the chat. False = a run is already in flight."""
    if chat_id in _CHAT_BUSY:
        return False
    _CHAT_BUSY.add(chat_id)
    return True


def _release_chat(chat_id: int) -> None:
    _CHAT_BUSY.discard(chat_id)


async def _queue_pending(
    message,
    chat_id: int,
    text: str,
    speaker_id: int | None,
    mode: str,
) -> None:
    """Keep one text for this chat. A newer text replaces the previous one."""
    replaced = chat_id in _CHAT_PENDING
    msg_date, sender_name, sender_username = _msg_sender(message)
    _CHAT_PENDING[chat_id] = {
        "text": text,
        "speaker_id": speaker_id,
        "reply_msg_id": message.message_id,
        "mode": mode,
        "msg_date": msg_date,
        "sender_name": sender_name,
        "sender_username": sender_username,
    }
    print(f"BRIDGE queued chat={chat_id} replaced={replaced}", flush=True)
    await message.reply_text(_PENDING_REPLACE_ACK if replaced else _PENDING_ACK)


def _schedule_pending(chat_id: int, api_key: str, bot, context) -> None:
    """Start the stored follow-up, if any. Caller must already have released the chat."""
    pending = _CHAT_PENDING.pop(chat_id, None)
    if not pending:
        return
    asyncio.create_task(
        _send_pending(
            chat_id=chat_id,
            pending=pending,
            api_key=api_key,
            bot=bot,
            context=context,
        )
    )


class _Outbound:
    """Minimal stand-in so reply_text_and_documents can answer a stored message id."""

    def __init__(self, bot, chat_id: int, reply_to_message_id: int | None):
        self._bot = bot
        self._chat_id = chat_id
        self._reply_to = reply_to_message_id

    async def reply_text(self, text, **kwargs):
        kwargs.pop("reply_to_message_id", None)
        return await self._bot.send_message(
            chat_id=self._chat_id,
            text=text,
            reply_to_message_id=self._reply_to,
            **kwargs,
        )

    async def reply_document(self, **kwargs):
        return await self._bot.send_document(
            chat_id=self._chat_id,
            reply_to_message_id=self._reply_to,
            **kwargs,
        )


async def _send_pending(
    *,
    chat_id: int,
    pending: dict,
    api_key: str,
    bot,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Fire one queued text as a follow-up once the previous run is done."""
    if not _claim_chat(chat_id):
        # Another run started already; keep this text unless a newer one landed.
        _CHAT_PENDING.setdefault(chat_id, pending)
        return
    try:
        prior = live_agent(chat_id)
        text = pending["text"]
        speaker_id = pending.get("speaker_id")
        reply_msg_id = pending.get("reply_msg_id")
        mode = pending.get("mode", "agent")
        print(
            f"BRIDGE pending_fire chat={chat_id} prior={'yes' if prior else 'no'}",
            flush=True,
        )
        if prior:
            data = await asyncio.to_thread(
                followup_agent, api_key, prior, text, speaker_id, mode
            )
            if not extract_agent_id(data):
                data = dict(data)
                data["agent"] = {"id": prior}
        else:
            bd = context.application.bot_data
            data = await asyncio.to_thread(
                create_agent,
                api_key,
                bd["repo"],
                bd["branch"],
                text,
                auto_create_pr=bd["auto_create_pr"],
                runtime=bd["runtime"],
                machine_name=bd["machine_name"],
                telegram_user_id=speaker_id,
                mode=mode,
            )
        agent_id = extract_agent_id(data)
        run_id = extract_run_id(data)
        if not agent_id or not run_id:
            await bot.send_message(chat_id, "No pude procesar el mensaje pendiente.")
            return
        remember_agent(chat_id, agent_id)
        run = await wait_for_run_result(
            api_key,
            agent_id,
            run_id,
            bot=bot,
            chat_id=chat_id,
        )
        outbound = _Outbound(bot, chat_id, reply_msg_id)
        final_text = format_reply(run, mode=mode, agent_id=agent_id)
        _log_msg(
            direction="outbound",
            chat_id=chat_id,
            user_id=pending.get("speaker_id"),
            message_id=pending.get("reply_msg_id"),
            msg_date=pending.get("msg_date"),
            sender_name=pending.get("sender_name"),
            sender_username=pending.get("sender_username"),
            text=final_text,
            doc_path=_extract_doc_path(final_text),
            agent_id=agent_id,
            run_id=run_id,
        )
        await reply_text_and_documents(outbound, final_text)
    except Exception as exc:  # noqa: BLE001
        print(f"BRIDGE pending_error chat={chat_id} {exc}", flush=True)
        await bot.send_message(
            chat_id,
            "No pude procesar el mensaje que tenía guardado. Escríbemelo de nuevo.",
        )
    finally:
        _release_chat(chat_id)
        _schedule_pending(chat_id, api_key, bot, context)

# ---------- end busy-state helpers ---------------------------------------


async def run_and_reply(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    starter,
    mode: str = "agent",
    pending_text: str | None = None,
) -> None:
    api_key: str = context.application.bot_data["cursor_api_key"]
    chat = update.effective_chat
    if not chat or not update.message:
        return
    chat_id = chat.id
    bot = context.bot
    run_mode = normalize_mode(mode)

    # One run per chat. Text waits as a single follow-up. Media cannot be
    # stored (Telegram file ids expire) so the user must send it again.
    if not _claim_chat(chat_id):
        if pending_text:
            speaker_id = update.effective_user.id if update.effective_user else None
            await _queue_pending(
                update.message, chat_id, pending_text, speaker_id, run_mode
            )
        else:
            print(f"BRIDGE busy chat={chat_id} media_resend", flush=True)
            await update.message.reply_text(_MEDIA_BUSY_REPLY)
        return

    # Do NOT send an intermediate text like "Trabajando…" — that clears typing in Telegram.
    try:
        # create_agent / followup can take tens of seconds; heartbeat covers that gap.
        data = await _run_blocking_with_typing(bot, chat_id, starter)
        agent_id = extract_agent_id(data)
        run_id = extract_run_id(data)
        if agent_id:
            remember_agent(chat_id, agent_id)
        if not agent_id or not run_id:
            keys = sorted(data.keys()) if isinstance(data, dict) else []
            print(f"BRIDGE_ERROR: missing agent_id/run_id keys={keys}", flush=True)
            await update.message.reply_text(
                "No pude completar eso ahora. Escríbeme de nuevo en un rato."
            )
            return
        run_timeout = float(context.application.bot_data.get("run_timeout_seconds") or 3600)
        run = await wait_for_run_result(
            api_key,
            agent_id,
            run_id,
            bot=bot,
            chat_id=chat_id,
            timeout_seconds=run_timeout,
        )
        # First bot payload after the user message = final answer (+ optional PDFs).
        reply_text = format_reply(run, mode=run_mode, agent_id=agent_id)
        msg_date, sender_name, sender_username = _msg_sender(update.message)
        _log_msg(
            direction="outbound",
            chat_id=chat_id,
            user_id=update.effective_user.id if update.effective_user else None,
            message_id=update.message.message_id if update.message else None,
            msg_date=msg_date,
            sender_name=sender_name,
            sender_username=sender_username,
            text=reply_text,
            doc_path=_extract_doc_path(reply_text),
            agent_id=agent_id,
            run_id=run_id,
        )
        await reply_text_and_documents(update.message, reply_text)
        # Default back to Agent after a Plan run (sticky Plan only for that turn).
        if run_mode == "plan":
            LAST_MODE.pop(chat_id, None)
            print(f"BRIDGE mode reset to agent chat={chat_id}", flush=True)
    except Exception as exc:  # noqa: BLE001
        print(f"BRIDGE_ERROR: {exc}", flush=True)
        await update.message.reply_text(
            "No pude completar eso ahora. Escríbeme de nuevo en un rato."
        )
    finally:
        _release_chat(chat_id)
        _schedule_pending(chat_id, api_key, bot, context)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    allowed_user_id: int = context.application.bot_data["allowed_user_id"]
    if not allowed(update, allowed_user_id) or not update.message:
        return
    area = _area_prompt()
    greeting = getattr(area, "START_GREETING", None) if area else None
    if not isinstance(greeting, str) or not greeting.strip():
        greeting = (
            "Hola, soy Sylvia. Escríbeme como le escribirías a una compañera, "
            "o mándame una foto, un PDF o un audio.\n"
            "Por ejemplo: si llegó correo hoy, o el PDF de la orden S08694.\n"
            "Pon el cliente, el número o el día en el mismo mensaje."
        )
    await update.message.reply_text(greeting)


async def cmd_new(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    allowed_user_id: int = context.application.bot_data["allowed_user_id"]
    if not allowed(update, allowed_user_id) or not update.message:
        return
    chat_id = update.effective_chat.id if update.effective_chat else 0
    LAST_AGENT.pop(chat_id, None)
    LAST_SEEN.pop(chat_id, None)
    LAST_MODE.pop(chat_id, None)
    await update.message.reply_text(
        "Reset local: sin agent activo para /followup. "
        "Modo otra vez Agent. "
        "El próximo mensaje de texto creará un agent nuevo."
    )


async def cmd_plan(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Cloud Agents Plan mode: /plan [texto]. Without text, sticky for next messages."""
    allowed_user_id = context.application.bot_data["allowed_user_id"]
    if not allowed(update, allowed_user_id) or not update.message:
        return
    chat_id = update.effective_chat.id if update.effective_chat else 0
    text = normalize_user_text(" ".join(context.args) if context.args else "")
    set_chat_mode(chat_id, "plan")
    if not text:
        await update.message.reply_text(
            "Modo Plan activo. El próximo mensaje pide un plan "
            "(sin editar ni reiniciar). /agent para volver a trabajar."
        )
        return
    # Fresh agent so create gets mode=plan (not a sticky agent from Agent mode).
    LAST_AGENT.pop(chat_id, None)
    LAST_SEEN.pop(chat_id, None)
    await _start_task(
        update,
        context,
        text,
        api_key=context.application.bot_data["cursor_api_key"],
        repo=context.application.bot_data["repo"],
        branch=context.application.bot_data["branch"],
        auto_create_pr=context.application.bot_data["auto_create_pr"],
        runtime=context.application.bot_data["runtime"],
        machine_name=context.application.bot_data["machine_name"],
        mode="plan",
    )


async def cmd_agent(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Switch sticky mode back to Agent (implement). Optional text runs at once."""
    allowed_user_id = context.application.bot_data["allowed_user_id"]
    if not allowed(update, allowed_user_id) or not update.message:
        return
    chat_id = update.effective_chat.id if update.effective_chat else 0
    text = normalize_user_text(" ".join(context.args) if context.args else "")
    set_chat_mode(chat_id, "agent")
    if not text:
        await update.message.reply_text(
            "Modo Agent activo. El próximo mensaje implementa / trabaja como siempre."
        )
        return
    await _start_task(
        update,
        context,
        text,
        api_key=context.application.bot_data["cursor_api_key"],
        repo=context.application.bot_data["repo"],
        branch=context.application.bot_data["branch"],
        auto_create_pr=context.application.bot_data["auto_create_pr"],
        runtime=context.application.bot_data["runtime"],
        machine_name=context.application.bot_data["machine_name"],
        mode="agent",
    )


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    allowed_user_id: int = context.application.bot_data["allowed_user_id"]
    if not allowed(update, allowed_user_id) or not update.message:
        return
    await update.message.reply_text("https://cursor.com/agents")


async def cmd_ping(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    allowed_user_id: int = context.application.bot_data["allowed_user_id"]
    if not allowed(update, allowed_user_id) or not update.message:
        return
    await update.message.reply_text("pong — bridge running")


async def cmd_followup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    allowed_user_id: int = context.application.bot_data["allowed_user_id"]
    api_key: str = context.application.bot_data["cursor_api_key"]
    if not allowed(update, allowed_user_id) or not update.message:
        return
    chat_id = update.effective_chat.id if update.effective_chat else 0
    agent_id = live_agent(chat_id)
    text = normalize_user_text(" ".join(context.args) if context.args else "")
    if not agent_id or not text:
        await update.message.reply_text(
            "Uso: /followup <instrucciones> (después de una primera tarea)"
        )
        return

    speaker_id = update.effective_user.id if update.effective_user else None
    run_mode = chat_mode(chat_id)

    def starter() -> dict:
        return followup_agent(api_key, agent_id, text, speaker_id, mode=run_mode)

    print(f"BRIDGE mode={run_mode} chat={chat_id} followup", flush=True)
    await run_and_reply(update, context, starter=starter, mode=run_mode)


async def on_task(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    allowed_user_id: int = context.application.bot_data["allowed_user_id"]
    api_key: str = context.application.bot_data["cursor_api_key"]
    repo: str = context.application.bot_data["repo"]
    branch: str = context.application.bot_data["branch"]
    auto_create_pr: bool = context.application.bot_data["auto_create_pr"]
    runtime: str = context.application.bot_data["runtime"]
    machine_name: str = context.application.bot_data["machine_name"]
    if not allowed(update, allowed_user_id) or not update.message or not update.message.text:
        return
    text = normalize_user_text(update.message.text)
    await _start_task(
        update,
        context,
        text,
        api_key=api_key,
        repo=repo,
        branch=branch,
        auto_create_pr=auto_create_pr,
        runtime=runtime,
        machine_name=machine_name,
    )


def _inbound_meta(message) -> tuple[str, str, str, int] | None:
    """Return file_id, filename, mime, size. None when the message has no file."""
    if message.photo:
        photo = message.photo[-1]
        return photo.file_id, "photo.jpg", "image/jpeg", int(photo.file_size or 0)
    if message.voice:
        voice = message.voice
        return voice.file_id, "voice.ogg", voice.mime_type or "audio/ogg", int(voice.file_size or 0)
    if message.audio:
        audio = message.audio
        name = audio.file_name or "audio.mp3"
        return audio.file_id, name, audio.mime_type or "audio/mpeg", int(audio.file_size or 0)
    if message.document:
        doc = message.document
        name = doc.file_name or "file.bin"
        return doc.file_id, name, doc.mime_type or "", int(doc.file_size or 0)
    return None


async def on_media(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Photo, document, or voice note -> file on disk -> one agent task."""
    import inbound_media

    allowed_user_id: int = context.application.bot_data["allowed_user_id"]
    if not allowed(update, allowed_user_id) or not update.message:
        return
    meta = _inbound_meta(update.message)
    if meta is None:
        return
    file_id, raw_name, mime, size = meta
    if size > 20 * 1024 * 1024:
        await update.message.reply_text(
            "Ese archivo pesa demasiado. Mándamelo de nuevo, más liviano."
        )
        return

    chat = update.effective_chat
    bot = context.bot
    beat = asyncio.create_task(_typing_heartbeat(bot, chat.id)) if chat else None
    try:
        filename = inbound_media.safe_filename(raw_name, "file.bin")
        dest = inbound_media.stamp_path(ROOT, filename)
        tg_file = await context.bot.get_file(file_id)
        await tg_file.download_to_drive(custom_path=str(dest))
        kind = inbound_media.classify(dest.suffix, mime)
        print(f"INBOUND kind={kind} bytes={dest.stat().st_size} name={dest.name}", flush=True)
        if kind == "unsupported":
            dest.unlink(missing_ok=True)
            await update.message.reply_text(
                "Ese archivo no lo puedo leer. Mándame una foto, un PDF, una planilla o un audio."
            )
            return
        note = update.message.caption or ""
        body = ""
        truncated = False
        if kind == "document":
            body, truncated = inbound_media._clip(
                await asyncio.to_thread(inbound_media.extract_document, dest)
            )
            print(f"INBOUND document chars={len(body)} truncated={truncated}", flush=True)
        elif kind == "audio":
            body, truncated = inbound_media._clip(
                await asyncio.to_thread(inbound_media.transcribe, dest)
            )
            print(f"INBOUND audio chars={len(body)}", flush=True)
            if not body:
                await update.message.reply_text(
                    "No alcancé a entender el audio. ¿Me lo escribes o lo mandas otra vez?"
                )
                return
        text = inbound_media.compose_task(
            kind,
            inbound_media.agent_visible_path(ROOT, dest),
            note,
            body,
            truncated,
        )
        msg_date, sender_name, sender_username = _msg_sender(update.message)
        _log_msg(
            direction="inbound",
            chat_id=chat.id if chat else 0,
            user_id=update.effective_user.id if update.effective_user else None,
            message_id=update.message.message_id,
            msg_date=msg_date,
            sender_name=sender_name,
            sender_username=sender_username,
            text=note,
            doc_path=str(dest),
        )
    except Exception as exc:  # noqa: BLE001
        print(f"BRIDGE_ERROR: inbound {exc}", flush=True)
        await update.message.reply_text(
            "No pude leer eso. Mándamelo de nuevo, o escríbeme el pedido."
        )
        return
    finally:
        if beat is not None:
            beat.cancel()
            try:
                await beat
            except asyncio.CancelledError:
                pass

    await _start_task(
        update,
        context,
        text,
        api_key=context.application.bot_data["cursor_api_key"],
        repo=context.application.bot_data["repo"],
        branch=context.application.bot_data["branch"],
        auto_create_pr=context.application.bot_data["auto_create_pr"],
        runtime=context.application.bot_data["runtime"],
        machine_name=context.application.bot_data["machine_name"],
        queue_if_busy=False,  # file IDs expire; user must resend media
    )


async def _start_task(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    *,
    api_key: str,
    repo: str,
    branch: str,
    auto_create_pr: bool,
    runtime: str,
    machine_name: str,
    mode: str | None = None,
    queue_if_busy: bool = True,
) -> None:
    chat_id = update.effective_chat.id if update.effective_chat else 0
    speaker_id = update.effective_user.id if update.effective_user else None
    prior = live_agent(chat_id)
    run_mode = normalize_mode(mode) if mode is not None else chat_mode(chat_id)

    def starter() -> dict:
        if prior:
            try:
                data = followup_agent(
                    api_key, prior, text, speaker_id, mode=run_mode
                )
            except RuntimeError as exc:
                print(f"BRIDGE followup failed, new agent: {exc}", flush=True)
                LAST_AGENT.pop(chat_id, None)
                LAST_SEEN.pop(chat_id, None)
                data = None
            if isinstance(data, dict):
                # Follow-up replies with the run id and omits the agent id
                # (it was already in the URL). Keep the id we just used.
                if not extract_agent_id(data):
                    data = dict(data)
                    data["agent"] = {"id": prior}
                return data
        return create_agent(
            api_key,
            repo,
            branch,
            text,
            auto_create_pr=auto_create_pr,
            runtime=runtime,
            machine_name=machine_name,
            telegram_user_id=speaker_id,
            mode=run_mode,
        )

    print(f"BRIDGE mode={run_mode} chat={chat_id}", flush=True)
    msg_date, sender_name, sender_username = _msg_sender(update.message)
    _log_msg(
        direction="inbound",
        chat_id=chat_id,
        user_id=speaker_id,
        message_id=update.message.message_id if update.message else None,
        msg_date=msg_date,
        sender_name=sender_name,
        sender_username=sender_username,
        text=text,
    )
    await run_and_reply(
        update, context, starter=starter, mode=run_mode,
        pending_text=text if queue_if_busy else None,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Telegram -> Cursor Cloud Agents bridge")
    parser.add_argument(
        "--env-file",
        type=Path,
        default=DEFAULT_ENV,
        help="Path to .env (default: repo root .env)",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Validate .env + Cursor API /v1/me, then exit (no Telegram polling)",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    load_env(args.env_file.resolve())

    token = require_env("TELEGRAM_BOT_TOKEN")
    allowed_user_id = parse_allowed_user_ids()
    api_key = require_env("CURSOR_API_KEY")
    repo = require_env("DEFAULT_REPO_URL")
    branch = (os.environ.get("DEFAULT_BRANCH") or "main").strip() or "main"
    auto_create_pr = env_bool("AUTO_CREATE_PR", default=False)
    runtime = (os.environ.get("AGENT_RUNTIME") or "cloud").strip().lower()
    machine_name = (os.environ.get("MACHINE_NAME") or "").strip()
    run_timeout_seconds = float((os.environ.get("RUN_TIMEOUT_SECONDS") or "3600").strip() or "3600")
    if runtime not in {"cloud", "machine"}:
        raise SystemExit("FAIL: AGENT_RUNTIME must be 'cloud' or 'machine'")
    if runtime == "machine" and not machine_name:
        raise SystemExit("FAIL: MACHINE_NAME required when AGENT_RUNTIME=machine")

    me = check_cursor_api(api_key)
    me_hint = {
        k: me.get(k)
        for k in ("email", "name", "id", "userId", "username")
        if k in me
    }
    print("OK: Cursor API /v1/me")
    if me_hint:
        print(f"OK: identity keys present: {sorted(me_hint.keys())}")
    print(f"OK: DEFAULT_REPO_URL set ({'github.com' in repo})")
    print(f"OK: DEFAULT_BRANCH={branch}")
    print(f"OK: AUTO_CREATE_PR={auto_create_pr}")
    print(f"OK: CURSOR_MODEL_ID={cursor_model_id()}")
    print(f"OK: AGENT_RUNTIME={runtime}")
    if runtime == "machine":
        print(f"OK: MACHINE_NAME={machine_name}")
    print(f"OK: RUN_TIMEOUT_SECONDS={int(run_timeout_seconds)}")
    print(f"OK: ALLOWED_TELEGRAM_USER_IDS count={len(allowed_user_id)}")

    if args.check_only:
        print("OK: --check-only passed (bridge not started)")
        return

    app = (
        Application.builder()
        .token(token)
        .connect_timeout(DOC_CONNECT_TIMEOUT)
        .read_timeout(DOC_READ_TIMEOUT)
        .write_timeout(60.0)
        .media_write_timeout(DOC_WRITE_TIMEOUT)
        .pool_timeout(10.0)
        .concurrent_updates(True)
        .build()
    )
    app.bot_data["allowed_user_id"] = allowed_user_id
    app.bot_data["cursor_api_key"] = api_key
    app.bot_data["repo"] = repo
    app.bot_data["branch"] = branch
    app.bot_data["auto_create_pr"] = auto_create_pr
    app.bot_data["runtime"] = runtime
    app.bot_data["machine_name"] = machine_name
    app.bot_data["run_timeout_seconds"] = run_timeout_seconds

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("new", cmd_new))
    app.add_handler(CommandHandler("plan", cmd_plan))
    app.add_handler(CommandHandler("agent", cmd_agent))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("ping", cmd_ping))
    app.add_handler(CommandHandler("followup", cmd_followup))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_task))
    app.add_handler(
        MessageHandler(
            filters.PHOTO | filters.VOICE | filters.AUDIO | filters.Document.ALL,
            on_media,
        )
    )

    # Python 3.14 has no implicit event loop. PTB 21.6 still calls get_event_loop().
    asyncio.set_event_loop(asyncio.new_event_loop())
    print("OK: starting Telegram polling (Ctrl+C to stop)")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Stopped.", file=sys.stderr)
        raise SystemExit(0) from None

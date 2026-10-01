"""Стол «Тайное послание». Запуск: py server.py"""

import json
import os
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
import socket

import game

ROOT = Path(__file__).resolve().parent / "public"
PORT = int(os.environ.get("PORT", "8765"))
BOT_NAMES = ["Марфа", "Лев", "Софья", "Пётр", "Аглая"]

rooms = {}
rooms_lock = threading.Lock()


def lan_ip():
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("8.8.8.8", 80))
        return probe.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        probe.close()


LAN = lan_ip()


def new_code():
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    while True:
        code = "".join(__import__("random").choice(alphabet) for _ in range(4))
        if code not in rooms:
            return code


class Room:
    def __init__(self, code):
        self.code = code
        self.members = []
        self.host = None
        self.game = None
        self.version = 1
        self.cv = threading.Condition()
        self.bot_timer = None
        self.reveal_timer = None

    def member_by_token(self, token):
        for member in self.members:
            if member["token"] == token:
                return member
        return None

    def touch(self):
        self.version += 1
        self.cv.notify_all()


def cancel_timer(timer):
    if timer:
        timer.cancel()


def schedule_bot(room):
    cancel_timer(room.bot_timer)
    room.bot_timer = None
    actor = bot_to_move(room)
    if not actor:
        return

    def fire():
        with room.cv:
            current = bot_to_move(room)
            if not current or current["pid"] != actor["pid"]:
                return
            run_bot(room, current["pid"])
            room.touch()
            schedule_bot(room)
            arm_reveal(room)

    room.bot_timer = threading.Timer(0.85, fire)
    room.bot_timer.daemon = True
    room.bot_timer.start()


def bot_to_move(room):
    state = room.game
    if not state:
        return None
    if state["phase"] == "play":
        pid = state["current"]
    elif state["phase"] == "chancellor" and state["pending"]:
        pid = state["pending"]["pid"]
    else:
        return None
    player = game.getp(state, pid)
    if player and player["bot"]:
        return player
    return None


def run_bot(room, pid):
    state = room.game
    move = game.decide(state, pid)
    if move["kind"] == "keep":
        err = game.resolve_chancellor(state, pid, move["keep"], move["bottom"])
    else:
        err = game.play_card(state, pid, move["uid"], move["target"], move["guess"])
    if not err:
        return
    actor = game.getp(state, pid)
    if state["phase"] == "chancellor" and state["pending"]:
        cards = state["pending"]["cards"]
        game.resolve_chancellor(state, pid, cards[0]["uid"], [card["uid"] for card in cards[1:]])
        return
    if state["phase"] != "play" or not actor or not actor["hand"]:
        return
    card = actor["hand"][0]
    if game.must_countess(actor["hand"]):
        card = next(item for item in actor["hand"] if item["type"] == "countess")
    targets = game.legal_targets(state, actor, card)
    target = targets[0]["pid"] if targets else None
    guess = "priest" if card["type"] == "guard" else None
    game.play_card(state, pid, card["uid"], target, guess)


def arm_reveal(room):
    cancel_timer(room.reveal_timer)
    room.reveal_timer = None
    if not room.game or room.game["phase"] != "reveal":
        return

    def fire():
        with room.cv:
            if room.game and room.game["phase"] == "reveal":
                game.continue_round(room.game)
                room.touch()
                schedule_bot(room)

    room.reveal_timer = threading.Timer(7.0, fire)
    room.reveal_timer.daemon = True
    room.reveal_timer.start()


def add_member(room, name, is_bot):
    pid = "p" + uuid.uuid4().hex[:8]
    member = {
        "pid": pid,
        "token": uuid.uuid4().hex,
        "name": name,
        "bot": is_bot,
        "seen": time.time(),
    }
    room.members.append(member)
    if room.host is None and not is_bot:
        room.host = pid
    return member


def lobby_view(room, member):
    now = time.time()
    return {
        "v": room.version,
        "screen": "lobby",
        "room": room.code,
        "you": member["pid"],
        "host": room.host,
        "goal": game.goal_for(len(room.members)) if len(room.members) >= 2 else None,
        "players": [
            {
                "pid": item["pid"],
                "name": item["name"],
                "bot": item["bot"],
                "host": item["pid"] == room.host,
                "away": (not item["bot"]) and now - item["seen"] > 45,
            }
            for item in room.members
        ],
        "lan": f"http://{LAN}:{PORT}",
    }


def game_view(room, member):
    payload = game.view_for(room.game, member["pid"])
    payload["v"] = room.version
    payload["room"] = room.code
    payload["host"] = room.host
    payload["lan"] = f"http://{LAN}:{PORT}"
    now = time.time()
    seen = {item["pid"]: item for item in room.members}
    for player in payload["players"]:
        source = seen.get(player["pid"])
        player["away"] = bool(source and not source["bot"] and now - source["seen"] > 45)
        player["host"] = player["pid"] == room.host
    return payload


def view_for_member(room, member):
    member["seen"] = time.time()
    if room.game:
        return game_view(room, member)
    return lobby_view(room, member)


def apply_action(room, member, data):
    kind = data.get("type")
    if kind == "add_bot":
        if member["pid"] != room.host:
            return "Ботов добавляет хозяин стола"
        if room.game:
            return "Партия уже идёт"
        if len(room.members) >= 6:
            return "За столом уже шестеро"
        used = {item["name"] for item in room.members}
        name = next((base for base in BOT_NAMES if base not in used), None)
        if name is None:
            name = f"Гость {len(room.members)}"
        add_member(room, name, True)
        return None
    if kind == "remove_bot":
        if member["pid"] != room.host or room.game:
            return "Убрать бота сейчас нельзя"
        room.members = [
            item for item in room.members
            if not (item["bot"] and item["pid"] == data.get("pid"))
        ]
        return None
    if kind == "start":
        if member["pid"] != room.host:
            return "Партию начинает хозяин стола"
        if room.game:
            return "Партия уже идёт"
        if not 2 <= len(room.members) <= 6:
            return "Нужно от 2 до 6 игроков"
        room.game = game.new_game([
            {"pid": item["pid"], "name": item["name"], "bot": item["bot"]}
            for item in room.members
        ])
        return None
    if not room.game:
        return "Партия ещё не началась"
    state = room.game
    if kind == "play":
        return game.play_card(state, member["pid"], data.get("uid"), data.get("target"), data.get("guess"))
    if kind == "keep":
        return game.resolve_chancellor(state, member["pid"], data.get("keep"), data.get("bottom") or [])
    if kind == "next":
        cancel_timer(room.reveal_timer)
        room.reveal_timer = None
        return game.continue_round(state)
    if kind == "again":
        if member["pid"] != room.host:
            return "Новую партию запускает хозяин стола"
        return game.rematch(state)
    return "Неизвестное действие"


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        if args and "/api/state" in str(args[0]):
            return
        super().log_message(fmt, *args)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/state":
            self.handle_state(parse_qs(parsed.query))
            return
        if parsed.path == "/api/info":
            self.send_json(200, {"lan": f"http://{LAN}:{PORT}"})
            return
        self.serve_file(parsed.path)

    def do_POST(self):
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length", "0") or 0)
        try:
            data = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            self.send_json(400, {"ok": False, "error": "Плохой запрос"})
            return
        if parsed.path == "/api/create":
            self.handle_create(data)
            return
        if parsed.path == "/api/join":
            self.handle_join(data)
            return
        if parsed.path == "/api/action":
            self.handle_action(data)
            return
        self.send_json(404, {"ok": False, "error": "Нет такого адреса"})

    def handle_create(self, data):
        name = clean_name(data.get("name"))
        if not name:
            self.send_json(400, {"ok": False, "error": "Введите имя"})
            return
        with rooms_lock:
            code = new_code()
            room = Room(code)
            member = add_member(room, name, False)
            rooms[code] = room
        self.send_json(200, {"ok": True, "room": code, "token": member["token"], "pid": member["pid"]})

    def handle_join(self, data):
        code = str(data.get("room") or "").strip().upper()
        name = clean_name(data.get("name"))
        with rooms_lock:
            room = rooms.get(code)
        if not room:
            self.send_json(404, {"ok": False, "error": "Стол не найден"})
            return
        if not name:
            self.send_json(400, {"ok": False, "error": "Введите имя"})
            return
        with room.cv:
            if room.game:
                self.send_json(400, {"ok": False, "error": "Партия уже идёт"})
                return
            if len(room.members) >= 6:
                self.send_json(400, {"ok": False, "error": "Стол уже полный"})
                return
            if any(item["name"].lower() == name.lower() for item in room.members):
                self.send_json(400, {"ok": False, "error": "Такое имя уже за столом"})
                return
            member = add_member(room, name, False)
            room.touch()
        self.send_json(200, {"ok": True, "room": code, "token": member["token"], "pid": member["pid"]})

    def handle_action(self, data):
        room, member, error = open_member(data)
        if error:
            self.send_json(error[0], {"ok": False, "error": error[1]})
            return
        with room.cv:
            err = apply_action(room, member, data)
            if err:
                self.send_json(400, {"ok": False, "error": err})
                return
            room.touch()
            schedule_bot(room)
            arm_reveal(room)
            payload = view_for_member(room, member)
        self.send_json(200, {"ok": True, "state": payload})

    def handle_state(self, query):
        token = (query.get("token") or [""])[0]
        code = (query.get("room") or [""])[0].upper()
        try:
            since = int((query.get("since") or ["0"])[0])
        except ValueError:
            since = 0
        with rooms_lock:
            room = rooms.get(code)
        if not room:
            self.send_json(404, {"ok": False, "error": "Стол не найден"})
            return
        with room.cv:
            member = room.member_by_token(token)
            if not member:
                self.send_json(403, {"ok": False, "error": "Вас нет за этим столом"})
                return
            if room.version <= since:
                room.cv.wait(timeout=20)
            payload = view_for_member(room, member)
        self.send_json(200, payload)

    def serve_file(self, raw_path):
        rel = raw_path.lstrip("/") or "index.html"
        path = (ROOT / rel).resolve()
        if not str(path).startswith(str(ROOT.resolve())) or not path.is_file():
            self.send_error(404)
            return
        kind = "text/html; charset=utf-8"
        if path.suffix == ".css":
            kind = "text/css; charset=utf-8"
        elif path.suffix == ".js":
            kind = "text/javascript; charset=utf-8"
        elif path.suffix == ".svg":
            kind = "image/svg+xml"
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def send_json(self, code, obj):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)


def open_member(data):
    code = str(data.get("room") or "").strip().upper()
    token = str(data.get("token") or "")
    with rooms_lock:
        room = rooms.get(code)
    if not room:
        return None, None, (404, "Стол не найден")
    member = room.member_by_token(token)
    if not member:
        return None, None, (403, "Вас нет за этим столом")
    return room, member, None


def clean_name(value):
    name = " ".join(str(value or "").replace("<", "").replace(">", "").split())
    return name[:18]


def main():
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"Стол открыт: http://127.0.0.1:{PORT}")
    print(f"Для друзей в сети: http://{LAN}:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()

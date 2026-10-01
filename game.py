"""Правила издания на 21 карту (2–6 игроков). Тексты эффектов свои, не из буклета."""

import random

TYPES = {
    "spy": (0, 2, "Шпион"),
    "guard": (1, 6, "Страж"),
    "priest": (2, 2, "Священник"),
    "baron": (3, 2, "Барон"),
    "handmaid": (4, 2, "Служанка"),
    "prince": (5, 2, "Принц"),
    "chancellor": (6, 2, "Министр"),
    "king": (7, 1, "Король"),
    "countess": (8, 1, "Графиня"),
    "princess": (9, 1, "Принцесса"),
}

EFFECTS = {
    "spy": "В конце раунда даёт жетон, если вы единственный, кто ещё в игре и сбрасывал шпиона.",
    "guard": "Назовите карту соперника, кроме стража. Если угадали, он выбывает.",
    "priest": "Посмотрите карту одного соперника.",
    "baron": "Сравните карты. У кого число меньше, тот выбывает.",
    "handmaid": "До вашего следующего хода вас нельзя выбрать целью.",
    "prince": "Игрок сбрасывает карту и берёт новую. Можно выбрать себя.",
    "chancellor": "Возьмите до двух карт, оставьте одну, остальные уберите под низ колоды.",
    "king": "Поменяйтесь оставшейся картой с соперником.",
    "countess": "Если на руке ещё король или принц, графиню нужно сыграть.",
    "princess": "Если эту карту сыграть или сбросить, вы выбываете.",
}

TARGET = {
    "guard": "other",
    "priest": "other",
    "baron": "other",
    "prince": "any",
    "king": "other",
}

_uid = 0


def goal_for(n):
    return {2: 6, 3: 5, 4: 4, 5: 3, 6: 3}[n]


def _new_uid():
    global _uid
    _uid += 1
    return f"c{_uid}"


def make_card(kind):
    value, _count, name = TYPES[kind]
    return {"uid": _new_uid(), "type": kind, "value": value, "name": name}


def fresh_deck():
    deck = []
    for kind, (_value, count, _name) in TYPES.items():
        for _ in range(count):
            deck.append(make_card(kind))
    return deck


def catalog():
    rows = []
    for kind, (value, count, name) in TYPES.items():
        rows.append({
            "type": kind,
            "value": value,
            "count": count,
            "name": name,
            "effect": EFFECTS[kind],
        })
    return rows


def pub_card(card):
    if not card:
        return None
    return {
        "uid": card["uid"],
        "type": card["type"],
        "value": card["value"],
        "name": card["name"],
        "effect": EFFECTS[card["type"]],
    }


def getp(game, pid):
    for player in game["players"]:
        if player["pid"] == pid:
            return player
    return None


def alive_players(game):
    return [player for player in game["players"] if player["alive"]]


def pname(game, pid):
    player = getp(game, pid)
    return player["name"] if player else "?"


def say(game, text):
    game["log"].append(text)
    if len(game["log"]) > 40:
        del game["log"][:-40]


def whisper(game, pid, text):
    bucket = game["priv"].setdefault(pid, [])
    bucket.append(text)
    if len(bucket) > 8:
        del bucket[:-8]


def must_countess(hand):
    kinds = {card["type"] for card in hand}
    return "countess" in kinds and ("king" in kinds or "prince" in kinds)


def legal_targets(game, actor, card):
    kind = TARGET.get(card["type"])
    if not kind:
        return []
    found = []
    for player in game["players"]:
        if not player["alive"]:
            continue
        if player["pid"] == actor["pid"]:
            if kind == "any":
                found.append(player)
            continue
        if player["protected"]:
            continue
        found.append(player)
    return found


def remember(game, viewer, target, card):
    if not card:
        return
    game["intel"].setdefault(viewer, {})[target] = card["uid"]


def known_card(game, viewer, target):
    uid = game["intel"].get(viewer, {}).get(target)
    if not uid:
        return None
    player = getp(game, target)
    if not player:
        return None
    for card in player["hand"]:
        if card["uid"] == uid:
            return card
    return None


def eliminate(player):
    player["alive"] = False
    player["protected"] = False
    player["discard"].extend(player["hand"])
    player["hand"] = []


def card_total(game):
    total = len(game["deck"]) + len(game["faceup"])
    if game["burned"]:
        total += 1
    if game["pending"]:
        # pending cards are the same objects as the actor's hand
        pass
    for player in game["players"]:
        total += len(player["hand"]) + len(player["discard"])
    return total


def new_game(specs):
    game = {
        "players": [],
        "round": 0,
        "goal": goal_for(len(specs)),
        "deck": [],
        "burned": None,
        "faceup": [],
        "current": None,
        "phase": "play",
        "pending": None,
        "intel": {},
        "log": [],
        "priv": {},
        "result": None,
        "winners": [],
        "next_starter": None,
    }
    for spec in specs:
        game["players"].append({
            "pid": spec["pid"],
            "name": spec["name"],
            "bot": spec["bot"],
            "tokens": 0,
            "alive": True,
            "protected": False,
            "hand": [],
            "discard": [],
        })
    starter = random.choice(game["players"])["pid"]
    start_round(game, starter)
    return game


def start_round(game, starter):
    deck = fresh_deck()
    random.shuffle(deck)
    game["round"] += 1
    game["burned"] = deck.pop(0)
    game["faceup"] = [deck.pop(0) for _ in range(3)] if len(game["players"]) == 2 else []
    for player in game["players"]:
        player["alive"] = True
        player["protected"] = False
        player["discard"] = []
        player["hand"] = [deck.pop(0)]
    game["deck"] = deck
    game["intel"] = {}
    game["pending"] = None
    game["result"] = None
    game["winners"] = []
    game["current"] = starter
    game["phase"] = "play"
    say(game, f"Раунд {game['round']}. Первым ходит {pname(game, starter)}.")
    begin_turn(game)


def begin_turn(game):
    player = getp(game, game["current"])
    player["protected"] = False
    if not game["deck"]:
        end_round(game, "deck")
        return
    player["hand"].append(game["deck"].pop(0))
    game["phase"] = "play"


def draw_forced(game):
    if game["deck"]:
        return game["deck"].pop(0)
    if game["burned"]:
        card = game["burned"]
        game["burned"] = None
        return card
    return None


def end_round(game, reason):
    alive = alive_players(game)
    if reason == "last":
        winners = alive[:1]
    else:
        def hand_value(player):
            if not player["hand"]:
                return -1
            return max(card["value"] for card in player["hand"])

        best = max((hand_value(player) for player in alive), default=-1)
        winners = [player for player in alive if hand_value(player) == best]
    for player in winners:
        player["tokens"] += 1
    spies = [
        player for player in alive
        if any(card["type"] == "spy" for card in player["discard"])
    ]
    spy_bonus = []
    if len(spies) == 1:
        spies[0]["tokens"] += 1
        spy_bonus = [spies[0]]
    reveals = []
    if reason == "deck":
        for player in alive:
            if player["hand"]:
                shown = max(player["hand"], key=lambda card: card["value"])
                reveals.append({"pid": player["pid"], "name": player["name"], "card": pub_card(shown)})
    names = ", ".join(player["name"] for player in winners) or "никто"
    if reason == "last":
        say(game, f"В раунде остаётся {names} и забирает жетон.")
    elif len(winners) == 1:
        say(game, f"Колода пуста. {names} показывает старшую карту и берёт жетон.")
    else:
        say(game, f"Колода пуста. Ничья: жетон получают {names}.")
    if spy_bonus:
        say(game, f"Шпион приносит ещё один жетон: {spy_bonus[0]['name']}.")
    champs = [player for player in game["players"] if player["tokens"] >= game["goal"]]
    game["result"] = {
        "reason": reason,
        "winners": [{"pid": player["pid"], "name": player["name"]} for player in winners],
        "spy": [{"pid": player["pid"], "name": player["name"]} for player in spy_bonus],
        "reveals": reveals,
        "gameWinners": [{"pid": player["pid"], "name": player["name"]} for player in champs],
    }
    if champs:
        game["phase"] = "gameover"
        game["winners"] = [player["pid"] for player in champs]
        say(game, "Партия окончена. " + " и ".join(player["name"] for player in champs) + " принимает послание.")
    else:
        game["phase"] = "reveal"
        game["next_starter"] = random.choice(winners)["pid"] if winners else game["current"]


def after_action(game):
    if game["phase"] in ("reveal", "gameover"):
        return
    if len(alive_players(game)) <= 1:
        end_round(game, "last")
        return
    if not game["deck"]:
        end_round(game, "deck")
        return
    order = [player["pid"] for player in game["players"]]
    index = order.index(game["current"])
    count = len(order)
    for step in range(1, count + 1):
        nxt = game["players"][(index + step) % count]
        if nxt["alive"]:
            game["current"] = nxt["pid"]
            begin_turn(game)
            return


def play_card(game, pid, uid, target_id=None, guess=None):
    if game["phase"] != "play":
        return "Сейчас нельзя ходить"
    if game["current"] != pid:
        return "Сейчас ход другого игрока"
    actor = getp(game, pid)
    card = next((item for item in actor["hand"] if item["uid"] == uid), None)
    if not card:
        return "Такой карты на руке нет"
    if must_countess(actor["hand"]) and card["type"] != "countess":
        return "Нужно сыграть графиню"
    targets = legal_targets(game, actor, card)
    target = None
    if card["type"] in TARGET and targets:
        target = next((item for item in targets if item["pid"] == target_id), None)
        if not target:
            return "Эту цель выбрать нельзя"
        if card["type"] == "guard":
            if guess not in TYPES or guess == "guard":
                return "Стража называть нельзя"
    actor["hand"] = [item for item in actor["hand"] if item["uid"] != uid]
    actor["discard"].append(card)
    outcome = _resolve(game, actor, card, target, guess)
    if outcome == "wait":
        return None
    after_action(game)
    return None


def _resolve(game, actor, card, target, guess):
    kind = card["type"]
    if kind == "princess":
        eliminate(actor)
        say(game, f"{actor['name']} играет принцессу и выбывает.")
        return "done"
    if kind == "handmaid":
        actor["protected"] = True
        say(game, f"{actor['name']} прячется за служанкой.")
        return "done"
    if kind == "spy":
        say(game, f"{actor['name']} играет шпиона.")
        return "done"
    if kind == "countess":
        say(game, f"{actor['name']} играет графиню.")
        return "done"
    if kind == "chancellor":
        return _chancellor(game, actor)
    if target is None:
        say(game, f"{actor['name']} играет «{card['name']}», но цели нет, и эффект гаснет.")
        return "done"
    if kind == "guard":
        return _guard(game, actor, target, guess)
    if kind == "priest":
        seen = target["hand"][0] if target["hand"] else None
        remember(game, actor["pid"], target["pid"], seen)
        say(game, f"{actor['name']} через священника смотрит карту {target['name']}.")
        if seen:
            whisper(game, actor["pid"], f"У {target['name']} на руке {seen['name']}.")
        return "done"
    if kind == "baron":
        return _baron(game, actor, target)
    if kind == "prince":
        return _prince(game, actor, target)
    if kind == "king":
        return _king(game, actor, target)
    return "done"


def _guard(game, actor, target, guess):
    _value, _count, guess_name = TYPES[guess]
    actual = target["hand"][0]["type"] if target["hand"] else None
    if actual == guess:
        eliminate(target)
        say(game, f"{actor['name']} называет карту игрока {target['name']}: {guess_name}. Попадание, {target['name']} выбывает.")
    else:
        say(game, f"{actor['name']} называет карту игрока {target['name']}: {guess_name}. Мимо.")
    return "done"


def _baron(game, actor, target):
    mine = actor["hand"][0] if actor["hand"] else None
    theirs = target["hand"][0] if target["hand"] else None
    remember(game, actor["pid"], target["pid"], theirs)
    remember(game, target["pid"], actor["pid"], mine)
    my_value = mine["value"] if mine else -1
    their_value = theirs["value"] if theirs else -1
    whisper(
        game,
        actor["pid"],
        f"У вас {mine['name'] if mine else 'пусто'} ({my_value}), у {target['name']} {theirs['name'] if theirs else 'пусто'} ({their_value}).",
    )
    whisper(
        game,
        target["pid"],
        f"У вас {theirs['name'] if theirs else 'пусто'} ({their_value}), у {actor['name']} {mine['name'] if mine else 'пусто'} ({my_value}).",
    )
    if my_value < their_value:
        eliminate(actor)
        say(game, f"{actor['name']} сравнивает карты с {target['name']} и выбывает.")
    elif their_value < my_value:
        eliminate(target)
        say(game, f"{actor['name']} сравнивает карты с {target['name']}. {target['name']} выбывает.")
    else:
        say(game, f"{actor['name']} сравнивает карты с {target['name']}. Равенство, оба остаются.")
    return "done"


def _prince(game, actor, target):
    if not target["hand"]:
        say(game, f"{actor['name']} играет принца, но у {target['name']} нет карты.")
        return "done"
    dropped = target["hand"].pop(0)
    target["discard"].append(dropped)
    if dropped["type"] == "princess":
        target["alive"] = False
        target["protected"] = False
        say(game, f"{actor['name']} заставляет {target['name']} сбросить принцессу. {target['name']} выбывает.")
        return "done"
    drawn = draw_forced(game)
    if drawn:
        target["hand"].append(drawn)
        if target["pid"] == actor["pid"]:
            say(game, f"{actor['name']} из-за принца сбрасывает {dropped['name']} и берёт новую карту.")
        else:
            say(game, f"{actor['name']} заставляет {target['name']} сбросить {dropped['name']} и взять новую карту.")
        whisper(game, target["pid"], f"После принца у вас на руке {drawn['name']}.")
    else:
        target["alive"] = False
        say(game, f"{actor['name']} заставляет {target['name']} сбросить {dropped['name']}. Новой карты нет, {target['name']} выбывает.")
    return "done"


def _king(game, actor, target):
    if not actor["hand"] or not target["hand"]:
        say(game, f"{actor['name']} играет короля, но меняться нечем.")
        return "done"
    given = actor["hand"][0]
    taken = target["hand"][0]
    actor["hand"][0], target["hand"][0] = taken, given
    remember(game, actor["pid"], target["pid"], given)
    remember(game, target["pid"], actor["pid"], taken)
    say(game, f"{actor['name']} меняется картами с {target['name']}.")
    whisper(game, actor["pid"], f"Вы отдали {given['name']} и получили {taken['name']}.")
    whisper(game, target["pid"], f"Вы отдали {taken['name']} и получили {given['name']}.")
    return "done"


def _chancellor(game, actor):
    draw_n = min(2, len(game["deck"]))
    if draw_n == 0:
        say(game, f"{actor['name']} играет министра, но колода пуста.")
        return "done"
    for _ in range(draw_n):
        actor["hand"].append(game["deck"].pop(0))
    game["pending"] = {"pid": actor["pid"], "cards": list(actor["hand"])}
    game["phase"] = "chancellor"
    say(game, f"{actor['name']} играет министра и разбирает карты.")
    return "wait"


def resolve_chancellor(game, pid, keep_uid, bottom_uids):
    if game["phase"] != "chancellor" or not game["pending"]:
        return "Сейчас не ход министра"
    if game["pending"]["pid"] != pid:
        return "Карты министра разбирает другой игрок"
    actor = getp(game, pid)
    cards = game["pending"]["cards"]
    have = {card["uid"] for card in cards}
    if keep_uid not in have:
        return "Эту карту нельзя оставить"
    if set(bottom_uids) != have - {keep_uid} or len(bottom_uids) != len(have) - 1:
        return "Нужно убрать под колоду все остальные карты"
    by_uid = {card["uid"]: card for card in cards}
    actor["hand"] = [by_uid[keep_uid]]
    for uid in bottom_uids:
        game["deck"].append(by_uid[uid])
    game["pending"] = None
    game["phase"] = "play"
    say(game, f"{actor['name']} оставляет одну карту, остальные кладёт под колоду.")
    whisper(game, pid, f"Вы оставили {by_uid[keep_uid]['name']}.")
    after_action(game)
    return None


def continue_round(game):
    if game["phase"] != "reveal":
        return "Раунд ещё не закончен"
    start_round(game, game["next_starter"])
    return None


def rematch(game):
    for player in game["players"]:
        player["tokens"] = 0
    game["round"] = 0
    game["log"] = []
    game["priv"] = {}
    starter = random.choice(game["players"])["pid"]
    start_round(game, starter)
    return None


def unseen_counts(game, viewer_pid):
    counts = {kind: count for kind, (_value, count, _name) in TYPES.items()}
    seen = []
    seen.extend(game["faceup"])
    viewer = getp(game, viewer_pid)
    for player in game["players"]:
        seen.extend(player["discard"])
    if viewer:
        seen.extend(viewer["hand"])
        for player in game["players"]:
            if player["pid"] == viewer_pid:
                continue
            known = known_card(game, viewer_pid, player["pid"])
            if known:
                seen.append(known)
    for card in seen:
        counts[card["type"]] -= 1
    return counts


def view_for(game, pid):
    me = getp(game, pid)
    hand = [pub_card(card) for card in (me["hand"] if me else [])]
    must = None
    if me and game["phase"] == "play" and game["current"] == pid and must_countess(me["hand"]):
        countess = next(card for card in me["hand"] if card["type"] == "countess")
        must = countess["uid"]
    players = []
    for player in game["players"]:
        known = None if player["pid"] == pid else known_card(game, pid, player["pid"])
        players.append({
            "pid": player["pid"],
            "name": player["name"],
            "bot": player["bot"],
            "tokens": player["tokens"],
            "alive": player["alive"],
            "protected": player["protected"],
            "cardCount": len(player["hand"]),
            "discard": [pub_card(card) for card in player["discard"]],
            "known": pub_card(known),
        })
    choice = None
    if game["phase"] == "chancellor" and game["pending"] and game["pending"]["pid"] == pid:
        choice = [pub_card(card) for card in game["pending"]["cards"]]
    return {
        "screen": "game",
        "round": game["round"],
        "goal": game["goal"],
        "phase": game["phase"],
        "deck": len(game["deck"]),
        "burned": game["burned"] is not None,
        "faceup": [pub_card(card) for card in game["faceup"]],
        "current": game["current"],
        "players": players,
        "hand": hand,
        "must": must,
        "log": list(game["log"]),
        "privateLog": list(game["priv"].get(pid, [])),
        "catalog": catalog(),
        "choice": choice,
        "result": game["result"],
        "unseen": unseen_counts(game, pid),
        "you": pid,
    }


def decide(game, pid):
    """Ход бота только по открытой информации, своей руке и уже увиденным картам."""
    actor = getp(game, pid)
    if game["phase"] == "chancellor":
        cards = list(game["pending"]["cards"])
        keep = max(cards, key=lambda card: card["value"])
        rest = [card for card in cards if card["uid"] != keep["uid"]]
        rest.sort(key=lambda card: card["value"])
        return {"kind": "keep", "keep": keep["uid"], "bottom": [card["uid"] for card in rest]}

    hand = list(actor["hand"])
    if must_countess(hand):
        card = next(item for item in hand if item["type"] == "countess")
        return {"kind": "play", "uid": card["uid"], "target": None, "guess": None}

    candidates = []
    for card in hand:
        if card["type"] == "princess" and len(hand) > 1:
            continue
        others = [item for item in hand if item["uid"] != card["uid"]]
        other = others[0] if others else card
        targets = legal_targets(game, actor, card)
        if card["type"] in TARGET and targets:
            for target in targets:
                guess = _best_guess(game, pid, target["pid"]) if card["type"] == "guard" else None
                candidates.append((
                    _score(game, pid, card, other, target["pid"], guess),
                    card,
                    target["pid"],
                    guess,
                ))
        else:
            candidates.append((_score(game, pid, card, other, None, None), card, None, None))
    if not candidates:
        card = hand[0]
        candidates.append((0, card, None, None))
    candidates.sort(key=lambda item: item[0], reverse=True)
    _score_value, card, target_id, guess = candidates[0]
    return {"kind": "play", "uid": card["uid"], "target": target_id, "guess": guess}


def _best_guess(game, viewer, target_pid):
    known = known_card(game, viewer, target_pid)
    if known and known["type"] != "guard":
        return known["type"]
    counts = unseen_counts(game, viewer)
    options = [(kind, count) for kind, count in counts.items() if kind != "guard" and count > 0]
    if not options:
        return "priest"
    options.sort(key=lambda item: item[1], reverse=True)
    return options[0][0]


def _score(game, viewer, card, other, target_id, guess):
    kind = card["type"]
    if kind == "king":
        score = (4 - other["value"]) * 7
    elif kind == "prince" and target_id == viewer:
        score = 0
    else:
        score = other["value"] * 8
    known = known_card(game, viewer, target_id) if target_id and target_id != viewer else None
    if kind == "spy":
        score += 16
    elif kind == "handmaid":
        score += 24 if other["value"] >= 6 else (10 if other["value"] >= 4 else -8)
    elif kind == "chancellor":
        score += 18
    elif kind == "baron":
        score += 16 if other["value"] >= 5 else -14
        if known:
            score += 36 if known["value"] < other["value"] else -42
    elif kind == "guard":
        if known and known["type"] != "guard":
            score += 48
        elif known and known["type"] == "guard":
            score -= 30
        else:
            score += 11
    elif kind == "priest":
        score += -6 if known else 7
    elif kind == "king":
        if known:
            score += 28 if known["value"] > other["value"] else -30
        if other["type"] == "princess":
            score -= 40
    elif kind == "prince":
        if target_id == viewer:
            score += 12 if other["value"] <= 1 else -8
            if other["type"] == "princess":
                score -= 1000
        elif known and known["type"] == "princess":
            score += 55
        else:
            score += 9
    elif kind == "princess":
        score -= 500
    if target_id and target_id != viewer:
        target = getp(game, target_id)
        if target:
            score += target["tokens"] * 2
    score += random.random()
    return score

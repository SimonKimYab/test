const app = document.querySelector("#app");
let session = loadSession();
let state = null;
let ui = { card: null, target: null, guess: null, keep: null, order: [] };
let toastText = "";
let showRules = false;
let showCards = false;
let pollGen = 0;

const queryRoom = new URLSearchParams(location.search).get("room");

function loadSession() {
  try {
    return JSON.parse(localStorage.getItem("tp") || "null");
  } catch {
    return null;
  }
}

function saveSession(next) {
  session = next;
  localStorage.setItem("tp", JSON.stringify(next));
}

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[ch]));
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function toast(text) {
  toastText = text;
  render();
  setTimeout(() => {
    if (toastText === text) {
      toastText = "";
      render();
    }
  }, 3200);
}

async function post(url, body) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await response.json();
  if (!response.ok || data.ok === false) {
    throw new Error(data.error || "Не вышло");
  }
  return data;
}

function cardView(card, extra = "") {
  if (!card) return `<div class="mini back"></div>`;
  return `<article class="card v${card.value} ${extra}" data-uid="${esc(card.uid)}">
    <span class="val">${card.value}</span>
    <span class="nm">${esc(card.name)}</span>
    <span class="ef">${esc(card.effect)}</span>
  </article>`;
}

function mini(card) {
  if (!card) return "";
  return `<div class="mini"><b>${card.value}</b>${esc(card.name)}</div>`;
}

function hearts(tokens, goal) {
  const got = "♥".repeat(tokens);
  const left = "♡".repeat(Math.max(0, (goal || tokens) - tokens));
  return `<span class="hearts" title="${tokens} из ${goal || "?"}">${got}${left}</span>`;
}

function me() {
  return state?.players?.find((player) => player.pid === state.you);
}

function render() {
  if (!session) {
    app.innerHTML = homeHtml();
    bindHome();
    return;
  }
  if (!state) {
    app.innerHTML = `<main class="home"><p class="brand">Тайное послание</p><p>Собираем стол…</p></main>`;
    return;
  }
  if (state.screen === "lobby") app.innerHTML = lobbyHtml();
  else app.innerHTML = tableHtml();
  if (toastText) app.insertAdjacentHTML("beforeend", `<div class="toast">${esc(toastText)}</div>`);
  bindTable();
}

function homeHtml() {
  const code = queryRoom ? queryRoom.toUpperCase() : "";
  return `<main class="home">
    <p class="brand">Карточный стол</p>
    <h1>Тайное послание</h1>
    <p class="lede">Короткий дворцовый спор: одна скрытая карта, один ход и жетоны симпатии принцессы. До шести игроков, можно подсадить ботов.</p>
    <div class="home-grid">
      <section class="panel">
        <div class="row">
          <label>Ваше имя<input id="name" maxlength="18" placeholder="Например, Анна"></label>
        </div>
        <div class="row" style="margin-top:14px">
          <button class="btn" id="create">Создать стол</button>
        </div>
        <div class="row" style="margin-top:18px">
          <label>Код стола<input id="code" maxlength="4" value="${esc(code)}" placeholder="ABCD"></label>
          <button class="btn ghost" id="join">Сесть за стол</button>
        </div>
        <div class="row" style="margin-top:18px">
          <button class="btn ghost" id="rules">Коротко о правилах</button>
        </div>
      </section>
    </div>
    ${rulesOverlay()}
  </main>`;
}

function rulesOverlay() {
  if (!showRules) return "";
  return `<div class="overlay" id="close-rules">
    <section class="panel">
      <p class="brand">Памятка</p>
      <div class="ref-list">
        <p>У каждого одна закрытая карта. В ход берут ещё одну и сразу играют одну из двух. Сыгранная остаётся открытой перед вами.</p>
        <p>Одна карта в начале раунда уходит в сторону рубашкой вверх. Вдвоём ещё три карты лежат открытыми и в раунде не участвуют.</p>
        <p>Раунд кончается, когда колода пустеет или в игре остался один человек. Старшая карта берёт жетон. При равенстве жетон получает каждый из равных.</p>
        <p>Шпион даёт ещё один жетон, если его сбрасывали только вы и вы ещё в раунде. Это не мешает жетону за победу в раунде.</p>
        <p>Для победы: 2 игрока — 6 жетонов, 3 — 5, 4 — 4, 5 или 6 — 3. Если порог пересекли сразу несколько, победа общая.</p>
        <p>Служанка закрывает вас до вашего следующего хода. Графиню обязательно играть, если на руке король или принц. Принцесса выводит из раунда, если её сыграть или сбросить. Под низ колоды через министра её класть можно.</p>
      </div>
      <button class="btn" id="hide-rules">Понятно</button>
    </section>
  </div>`;
}

function lobbyHtml() {
  const mine = state.you === state.host;
  const players = state.players.map((player) => `<div class="seat ${player.pid === state.you ? "me" : ""}">
      <span>${esc(player.name)}${player.bot ? " · бот" : ""}</span>
      <span>${player.host ? "хозяин" : ""}${mine && player.bot ? ` <button class="btn ghost" data-remove="${esc(player.pid)}">убрать</button>` : ""}</span>
    </div>`).join("");
  return `<main class="lobby">
    <p class="brand">Стол ${esc(state.room)}</p>
    <div class="you-top">
      <h1>Ждём гостей</h1>
      <button class="btn ghost js-menu" type="button">В меню</button>
    </div>
    <div class="lobby-grid">
      <section class="panel">
        <div class="seat-list">${players}</div>
        <p>${state.goal ? `До победы ${state.goal} жетонов.` : "Нужен ещё хотя бы один игрок."}</p>
        <div class="row">
          ${mine ? `<button class="btn ghost" id="add-bot">Добавить бота</button>` : ""}
          ${mine ? `<button class="btn" id="start" ${state.players.length < 2 ? "disabled" : ""}>Начать</button>` : "<span>Ждём, пока хозяин начнёт.</span>"}
        </div>
      </section>
      <section class="panel">
        <p class="tag">Приглашение</p>
        <p>Код: <code>${esc(state.room)}</code></p>
        <p>Ссылка: <code>${esc(location.origin + "/?room=" + state.room)}</code></p>
        <button class="btn ghost" id="copy">Скопировать ссылку</button>
      </section>
    </div>
  </main>`;
}

function tableHtml() {
  const goal = state.goal;
  const mine = me();
  const others = state.players.filter((player) => player.pid !== state.you);
  const yourTurn = state.phase === "play" && state.current === state.you;
  const othersHtml = others.map((player) => personHtml(player, yourTurn)).join("");
  const hand = (state.hand || []).map((card) => {
    const locked = state.must && card.uid !== state.must;
    const selected = ui.card === card.uid ? "selected" : "";
    return cardView(card, `${selected} ${locked ? "locked" : ""}`);
  }).join("");
  const faceup = (state.faceup || []).length
    ? state.faceup.map(mini).join("")
    : `<div class="mini">нет</div>`;
  const result = state.result && (state.phase === "reveal" || state.phase === "gameover") ? resultHtml() : "";
  const choice = state.phase === "chancellor" && state.choice ? choiceHtml() : "";
  return `<main class="table">
    <p class="brand">Раунд ${state.round} · до победы ${goal}</p>
    <div class="you-top">
      <h1 style="font-size:42px">Тайное послание</h1>
      <div class="row">
        <button class="btn ghost js-menu" type="button">В меню</button>
        <button class="btn ghost" id="cards">Карты</button>
        <button class="btn ghost" id="rules">Правила</button>
      </div>
    </div>
    <div class="play-grid">
      <section>
        <div class="opponents">${othersHtml}</div>
        <div class="center-row">
          <div class="pile"><div class="back">${state.deck}</div>в колоде</div>
          <div class="pile">${state.burned ? `<div class="back">?</div>` : `<div class="mini">уже взята</div>`}скрытая</div>
          <div class="pile"><div class="tag">Вне игры</div><div class="mini-row">${faceup}</div></div>
        </div>
        <section class="you ${yourTurn ? "turn" : ""}">
          <div class="you-top">
            <strong>${esc(mine?.name || "Вы")} ${mine?.protected ? "· защита" : ""} ${yourTurn ? "· ваш ход" : ""}</strong>
            ${hearts(mine?.tokens || 0, goal)}
          </div>
          <div class="hand" id="hand">${hand}</div>
          <div class="mini-row">${(mine?.discard || []).map(mini).join("")}</div>
          ${yourTurn ? playControls() : `<p>${esc(turnText())}</p>`}
          ${(state.privateLog || []).slice(-2).map((line) => `<p class="note">${esc(line)}</p>`).join("")}
        </section>
      </section>
      <aside class="panel log">
        <p class="tag">Ход партии</p>
        <div class="scroll">${(state.log || []).slice(-12).map((line) => `<p>${esc(line)}</p>`).join("")}</div>
      </aside>
    </div>
    ${choice}${result}${rulesOverlay()}${cardsOverlay()}
  </main>`;
}

function personHtml(player, yourTurn) {
  const canTarget = yourTurn && player.alive && !player.protected && ui.card && needsTarget(ui.card);
  const picked = ui.target === player.pid ? "picked" : "";
  const known = player.known ? `<p class="note">Вы знаете: ${esc(player.known.name)}</p>` : "";
  return `<article class="person ${player.pid === state.current ? "turn" : ""} ${player.alive ? "" : "out"} ${canTarget ? "targetable" : ""} ${picked}" data-pid="${esc(player.pid)}">
    <div class="person-top"><strong>${esc(player.name)}</strong>${hearts(player.tokens, state.goal)}</div>
    <p class="tag">${player.alive ? (player.protected ? "под защитой" : `карт: ${player.cardCount}`) : "выбыл"}${player.bot ? " · бот" : ""}</p>
    ${known}
    <div class="mini-row">${player.discard.map(mini).join("")}</div>
  </article>`;
}

function needsTarget(uid) {
  const card = (state.hand || []).find((item) => item.uid === uid);
  return card && ["guard", "priest", "baron", "king", "prince"].includes(card.type);
}

function selectedCard() {
  return (state.hand || []).find((card) => card.uid === ui.card);
}

function playControls() {
  const card = selectedCard();
  const guesses = card?.type === "guard"
    ? `<div class="guesses">${state.catalog.filter((item) => item.type !== "guard").map((item) =>
        `<button class="btn ghost ${ui.guess === item.type ? "selected" : ""}" data-guess="${item.type}">${esc(item.name)}</button>`).join("")}</div>`
    : "";
  let hint = "Выберите карту.";
  if (card?.type === "prince") hint = "Принца можно направить и на себя.";
  if (card?.type === "guard") hint = "Сначала соперник, потом имя карты. Стража называть нельзя.";
  if (state.must) hint = "На руке король или принц: сейчас играется только графиня.";
  const self = card?.type === "prince" ? `<button class="btn ghost" id="self" ${ui.target === state.you ? "disabled" : ""}>На себя</button>` : "";
  return `<p>${hint}</p>${guesses}<div class="row" style="margin-top:10px">
    ${self}
    <button class="btn" id="commit">Сыграть</button>
  </div>`;
}

function turnText() {
  if (state.phase === "chancellor") {
    const who = state.players.find((player) => player.pid === state.current);
    return state.choice ? "Оставьте одну карту министра." : `${who?.name || "Игрок"} разбирает карты министра.`;
  }
  const who = state.players.find((player) => player.pid === state.current);
  if (state.phase === "reveal") return "Раунд закончен.";
  if (state.phase === "gameover") return "Партия закончена.";
  return `Ход: ${who?.name || "..."}`;
}

function choiceHtml() {
  const cards = state.choice.map((card) => {
    const mark = ui.keep === card.uid ? "selected" : "";
    const place = ui.order.indexOf(card.uid);
    return `<button class="card v${card.value} ${mark}" data-keep="${esc(card.uid)}">
      <span class="val">${card.value}</span><span class="nm">${esc(card.name)}</span>
      <span class="ef">${place >= 0 ? `под колоду, ${place + 1}-й` : esc(card.effect)}</span>
    </button>`;
  }).join("");
  return `<div class="overlay"><section class="panel">
    <p class="brand">Министр</p>
    <p>Нажмите карту, которую оставляете. Затем по очереди те, что уйдут под низ: первая из них выйдет раньше.</p>
    <div class="choice-row">${cards}</div>
    <div class="row">
      <button class="btn" id="confirm-keep">Оставить</button>
      <button class="btn ghost js-menu" type="button">В меню</button>
    </div>
  </section></div>`;
}

function resultHtml() {
  const result = state.result;
  const names = result.winners.map((player) => player.name).join(", ");
  const spy = result.spy.map((player) => player.name).join(", ");
  const reveals = result.reveals.map((item) => `<div>${mini(item.card)}<span>${esc(item.name)}</span></div>`).join("");
  const title = state.phase === "gameover"
    ? `Победа: ${result.gameWinners.map((player) => player.name).join(" и ")}`
    : `Жетон: ${names}`;
  const again = state.phase === "gameover" && state.you === state.host
    ? `<button class="btn" id="again">Ещё партию</button>` : "";
  const next = state.phase === "reveal" ? `<button class="btn" id="next">Дальше</button>` : "";
  return `<div class="overlay"><section class="panel">
    <p class="brand">${state.phase === "gameover" ? "Конец" : "Конец раунда"}</p>
    <h2>${esc(title)}</h2>
    <p>${result.reason === "last" ? "Остальные выбыли, последняя карта не вскрывается." : "Открытые карты:"}</p>
    <div class="mini-row">${reveals}</div>
    ${spy ? `<p class="note">Дополнительный жетон шпиона: ${esc(spy)}</p>` : ""}
    <div class="row">${next}${again}<button class="btn ghost js-menu" type="button">В меню</button></div>
  </section></div>`;
}

function cardsOverlay() {
  if (!showCards || !state?.catalog) return "";
  const rows = state.catalog.map((card) => `<div class="ref-item"><b>${card.value}</b><span>${esc(card.name)} ×${card.count}. ${esc(card.effect)} Ещё не видно: ${state.unseen?.[card.type] ?? "?"}</span></div>`).join("");
  return `<div class="overlay" id="close-cards"><section class="panel"><p class="brand">Колода</p><div class="ref-list">${rows}</div><button class="btn" id="hide-cards">Закрыть</button></section></div>`;
}

function bindHome() {
  document.querySelector("#create")?.addEventListener("click", async () => {
    try {
      const name = document.querySelector("#name").value;
      const data = await post("/api/create", { name });
      saveSession({ room: data.room, token: data.token, name });
      history.replaceState(null, "", `/?room=${data.room}`);
      startPoll();
    } catch (error) {
      toast(error.message);
    }
  });
  document.querySelector("#join")?.addEventListener("click", async () => {
    try {
      const name = document.querySelector("#name").value;
      const room = document.querySelector("#code").value.trim().toUpperCase();
      const data = await post("/api/join", { name, room });
      saveSession({ room: data.room, token: data.token, name });
      history.replaceState(null, "", `/?room=${data.room}`);
      startPoll();
    } catch (error) {
      toast(error.message);
    }
  });
  document.querySelector("#rules")?.addEventListener("click", () => {
    showRules = true;
    render();
  });
  document.querySelector("#hide-rules")?.addEventListener("click", () => {
    showRules = false;
    render();
  });
}

function leaveToMenu() {
  pollGen += 1;
  session = null;
  state = null;
  ui = { card: null, target: null, guess: null, keep: null, order: [] };
  showRules = false;
  showCards = false;
  localStorage.removeItem("tp");
  history.replaceState(null, "", location.pathname);
  render();
}

function bindTable() {
  document.querySelectorAll(".js-menu").forEach((button) => {
    button.addEventListener("click", leaveToMenu);
  });
  document.querySelector("#add-bot")?.addEventListener("click", () => act({ type: "add_bot" }));
  document.querySelector("#start")?.addEventListener("click", () => act({ type: "start" }));
  document.querySelector("#copy")?.addEventListener("click", async () => {
    const link = `${location.origin}/?room=${state.room}`;
    try {
      await navigator.clipboard.writeText(link);
      toast("Ссылка скопирована");
    } catch {
      toast(link);
    }
  });
  document.querySelectorAll("[data-remove]").forEach((button) => {
    button.addEventListener("click", () => act({ type: "remove_bot", pid: button.dataset.remove }));
  });
  document.querySelectorAll("#hand .card").forEach((node) => {
    node.addEventListener("click", () => {
      if (node.classList.contains("locked")) return;
      ui.card = node.dataset.uid;
      ui.target = null;
      ui.guess = null;
      render();
    });
  });
  document.querySelectorAll(".person.targetable").forEach((node) => {
    node.addEventListener("click", () => {
      ui.target = node.dataset.pid;
      render();
    });
  });
  document.querySelectorAll("[data-guess]").forEach((button) => {
    button.addEventListener("click", () => {
      ui.guess = button.dataset.guess;
      render();
    });
  });
  document.querySelector("#self")?.addEventListener("click", () => {
    ui.target = state.you;
    render();
  });
  document.querySelector("#commit")?.addEventListener("click", commitPlay);
  document.querySelectorAll("[data-keep]").forEach((node) => {
    node.addEventListener("click", () => pickChancellor(node.dataset.keep));
  });
  document.querySelector("#confirm-keep")?.addEventListener("click", confirmChancellor);
  document.querySelector("#next")?.addEventListener("click", () => act({ type: "next" }));
  document.querySelector("#again")?.addEventListener("click", () => act({ type: "again" }));
  document.querySelector("#rules")?.addEventListener("click", () => { showRules = true; render(); });
  document.querySelector("#hide-rules")?.addEventListener("click", () => { showRules = false; render(); });
  document.querySelector("#cards")?.addEventListener("click", () => { showCards = true; render(); });
  document.querySelector("#hide-cards")?.addEventListener("click", () => { showCards = false; render(); });
}

function pickChancellor(uid) {
  if (!ui.keep) {
    ui.keep = uid;
    const rest = (state.choice || []).map((card) => card.uid).filter((id) => id !== uid);
    ui.order = rest.length === 1 ? rest : [];
    render();
    return;
  }
  if (uid === ui.keep) {
    ui.keep = null;
    ui.order = [];
    render();
    return;
  }
  if (!ui.order.includes(uid)) ui.order.push(uid);
  render();
}

async function confirmChancellor() {
  const cards = state.choice || [];
  if (!ui.keep) {
    toast("Выберите карту, которую оставляете");
    return;
  }
  const rest = cards.map((card) => card.uid).filter((uid) => uid !== ui.keep);
  if (ui.order.length !== rest.length) {
    toast("Укажите порядок карт под колодой");
    return;
  }
  await act({ type: "keep", keep: ui.keep, bottom: ui.order });
  ui.keep = null;
  ui.order = [];
}

async function commitPlay() {
  const card = selectedCard();
  if (!card) {
    toast("Сначала выберите карту");
    return;
  }
  const payload = { type: "play", uid: card.uid, target: ui.target, guess: ui.guess };
  if (["guard", "priest", "baron", "king", "prince"].includes(card.type) && !ui.target) {
    const others = state.players.filter((player) => player.pid !== state.you && player.alive && !player.protected);
    if (others.length || card.type === "prince") {
      toast(card.type === "prince" ? "Выберите игрока или себя" : "Выберите, на кого играете");
      return;
    }
  }
  if (card.type === "guard" && ui.target && !ui.guess) {
    toast("Назовите карту");
    return;
  }
  await act(payload);
  ui = { card: null, target: null, guess: null, keep: null, order: [] };
}

async function act(payload) {
  try {
    const data = await post("/api/action", { ...payload, room: session.room, token: session.token });
    if (data.state) {
      state = data.state;
      render();
    }
  } catch (error) {
    toast(error.message);
  }
}

async function startPoll() {
  const gen = ++pollGen;
  let since = state?.v || 0;
  while (session && gen === pollGen) {
    try {
      const room = session.room;
      const token = session.token;
      const response = await fetch(`/api/state?room=${encodeURIComponent(room)}&token=${encodeURIComponent(token)}&since=${since}`);
      if (gen !== pollGen || !session) return;
      if (response.status === 403 || response.status === 404) {
        session = null;
        localStorage.removeItem("tp");
        toast("Стол недоступен");
        render();
        return;
      }
      const data = await response.json();
      if (gen !== pollGen || !session) return;
      since = data.v || since;
      if (!state || state.v !== data.v || state.phase !== data.phase) {
        if (state && (state.phase !== data.phase || state.current !== data.current || state.round !== data.round)) {
          ui = { card: null, target: null, guess: null, keep: ui.keep, order: ui.order };
        }
        state = data;
        render();
      }
    } catch {
      if (gen !== pollGen || !session) return;
      await sleep(1000);
    }
  }
}

if (session && (!queryRoom || queryRoom.toUpperCase() === session.room)) {
  render();
  startPoll();
} else {
  session = null;
  render();
}

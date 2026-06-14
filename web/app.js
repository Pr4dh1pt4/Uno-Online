const C2S = {
  REGISTER_REQ: "REGISTER_REQ",
  LOGIN_REQ: "LOGIN_REQ",
  SESSION_LOGIN_REQ: "SESSION_LOGIN_REQ",
  CREATE_ROOM_REQ: "CREATE_ROOM_REQ",
  JOIN_ROOM_REQ: "JOIN_ROOM_REQ",
  MATCHMAKE_REQ: "MATCHMAKE_REQ",
  START_MATCH_REQ: "START_MATCH_REQ",
  PLAY_CARD: "PLAY_CARD",
  DRAW_CARD: "DRAW_CARD",
  CALL_UNO: "CALL_UNO",
  LEAVE_ROOM: "LEAVE_ROOM",
  PING: "PING",
  GET_TOP_GLOBAL: "GET_TOP_GLOBAL",
  GET_STATS: "GET_STATS",
  GET_MATCH_HISTORY: "GET_MATCH_HISTORY",
};

const SESSION_KEY = "uno_web_session";
const DIRECT_ICE_SERVERS = [
  { urls: "stun:stun.l.google.com:19302" },
];
const TURN_ICE_SERVERS = [
  ...DIRECT_ICE_SERVERS,
  {
    urls: [
      "turn:72.155.88.239.sslip.io:3478?transport=udp",
      "turn:72.155.88.239.sslip.io:3478?transport=tcp",
    ],
    username: "uno",
    credential: "uno-turn-pass",
  },
];

const S2C = {
  REGISTER_OK: "REGISTER_OK",
  REGISTER_FAIL: "REGISTER_FAIL",
  LOGIN_OK: "LOGIN_OK",
  LOGIN_FAIL: "LOGIN_FAIL",
  ROOM_CREATED: "ROOM_CREATED",
  JOIN_OK: "JOIN_OK",
  JOIN_FAIL: "JOIN_FAIL",
  MATCH_FOUND: "MATCH_FOUND",
  ROOM_UPDATE: "ROOM_UPDATE",
  GAME_START: "GAME_START",
  STATE_UPDATE: "STATE_UPDATE",
  DRAW_RESULT: "DRAW_RESULT",
  ACTION_REJECTED: "ACTION_REJECTED",
  PLAYER_WIN: "PLAYER_WIN",
  ENTER_SPECTATOR: "ENTER_SPECTATOR",
  MATCH_RESULT: "MATCH_RESULT",
  PONG: "PONG",
  STATS: "STATS",
  TOP_GLOBAL: "TOP_GLOBAL",
  LEFT_ROOM: "LEFT_ROOM",
  MATCH_HISTORY: "MATCH_HISTORY",
  FORCE_LOGOUT: "FORCE_LOGOUT",
  DRAW_STACK_RESULT: "DRAW_STACK_RESULT",
  UNO_OK: "UNO_OK",
  UNO_ANNOUNCE: "UNO_ANNOUNCE",
  UNO_PENALTY: "UNO_PENALTY",
  UNO_CATCH: "UNO_CATCH",
  ERROR: "ERROR",
};

const els = {};
const state = {
  ws: null,
  connected: false,
  userId: null,
  username: "",
  token: "",
  stats: null,
  room: null,
  roomId: "",
  hand: [],
  game: null,
  selectedMode: "ranked",
  selectedIndices: [],
  selectedCards: [],
  pendingWild: null,
  isSpectator: false,
  soundOn: true,
  voiceOn: false,
  music: null,
  localStream: null,
  rtcPeerId: "",
  rtcPeers: new Map(),
  restoringSession: false,
  socketAuthenticated: false,
};

const SFX_SRC = {
  click: "/assets/sounds/click.mp3",
  card: "/assets/sounds/card_play.mp3",
  plus: "/assets/sounds/card_play_plus.mp3",
  win: "/assets/sounds/win.mp3",
  lose: "/assets/sounds/lose.mp3",
  leave: "/assets/sounds/leave.mp3",
};
const SFX_VOL = { click: 0.4, card: 0.7, plus: 0.7, win: 0.85, lose: 0.85, leave: 0.6 };
// Pool kecil per efek: klik beruntun memakai elemen Audio berbeda secara
// bergiliran, jadi suara tidak saling memotong dan terasa pas dengan tombol.
const sfxPool = {};
for (const name in SFX_SRC) {
  const nodes = Array.from({ length: 4 }, () => {
    const a = new Audio(SFX_SRC[name]);
    a.preload = "auto";
    return a;
  });
  nodes._i = 0;
  sfxPool[name] = nodes;
}

window.addEventListener("DOMContentLoaded", () => {
  cacheElements();
  bindEvents();
  showView("authView");
  connect();
});

function cacheElements() {
  document.querySelectorAll("[id]").forEach((el) => {
    els[el.id] = el;
  });
}

function bindEvents() {
  els.loginBtn.onclick = () => login(false);
  els.registerBtn.onclick = () => login(true);
  els.logoutBtn.onclick = () => { playSfx("click"); resetToAuth(); };
  els.rankedBtn.onclick = () => { playSfx("click"); setMode("ranked"); };
  els.classicBtn.onclick = () => { playSfx("click"); setMode("classic"); };
  els.quickBtn.onclick = () => { playSfx("click"); send(C2S.MATCHMAKE_REQ, { match_mode: state.selectedMode }); };
  els.createBtn.onclick = () => { playSfx("click"); send(C2S.CREATE_ROOM_REQ, { match_mode: state.selectedMode }); };
  els.joinBtn.onclick = () => { playSfx("click"); send(C2S.JOIN_ROOM_REQ, { room_code: els.roomCodeInput.value.trim().toUpperCase() }); };
  els.startBtn.onclick = () => { playSfx("click"); send(C2S.START_MATCH_REQ, {}); };
  els.leaveRoomBtn.onclick = leaveRoom;
  els.leaveGameBtn.onclick = leaveRoom;
  els.drawBtn.onclick = () => {
    clearSelection();
    send(C2S.DRAW_CARD, {});
    playSfx("click");
  };
  els.unoBtn.onclick = () => { playSfx("click"); send(C2S.CALL_UNO, { mode: "self" }); };
  els.catchUnoBtn.onclick = () => { playSfx("click"); send(C2S.CALL_UNO, { mode: "catch" }); };
  els.playSelectedBtn.onclick = playSelected;
  els.clearSelectedBtn.onclick = () => { playSfx("click"); clearSelection(); };
  els.refreshLeaderboardBtn.onclick = () => { playSfx("click"); requestLeaderboard(); };
  els.refreshHistoryBtn.onclick = () => { playSfx("click"); requestHistory(); };
  els.backLobbyBtn.onclick = () => {
    playSfx("click");
    showView("lobbyView");
    requestLobbyData();
  };
  els.soundBtn.onclick = toggleSound;
  els.voiceBtn.onclick = toggleVoice;
  document.querySelectorAll("#colorPicker button[data-color]").forEach((btn) => {
    btn.onclick = () => chooseWildColor(btn.dataset.color);
  });
  els.cancelWildBtn.onclick = cancelWild;
  [els.usernameInput, els.passwordInput, els.roomCodeInput].forEach((input) => {
    input.addEventListener("keydown", (ev) => {
      if (ev.key === "Enter") {
        if (input === els.roomCodeInput) els.joinBtn.click();
        else els.loginBtn.click();
      }
    });
  });
  // Escape membatalkan pilih-warna Wild atau seleksi kartu yang sedang berjalan.
  document.addEventListener("keydown", (ev) => {
    if (ev.key !== "Escape") return;
    if (state.pendingWild) cancelWild();
    else if (state.selectedCards.length) clearSelection();
  });
}

function connect() {
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  state.ws = new WebSocket(`${proto}//${location.host}/ws`);
  state.ws.onopen = () => {
    state.connected = true;
    state.socketAuthenticated = false;
    els.connStatus.textContent = "Connected";
    restoreSession();
  };
  state.ws.onclose = () => {
    state.connected = false;
    state.socketAuthenticated = false;
    els.connStatus.textContent = "Disconnected";
    setTimeout(connect, 1500);
  };
  state.ws.onerror = () => {
    els.connStatus.textContent = "Connection error";
  };
  state.ws.onmessage = (ev) => {
    try {
      handlePacket(JSON.parse(ev.data));
    } catch {
      setGameMsg("Paket server tidak valid");
    }
  };
}

function send(type, payload = {}) {
  if (!state.ws || state.ws.readyState !== WebSocket.OPEN) return;
  state.ws.send(JSON.stringify({ type, payload }));
}

setInterval(() => {
  if (state.userId && state.connected) {
    send(C2S.PING, { client_ts: Date.now() / 1000 });
  }
}, 2000);

function login(register) {
  const username = els.usernameInput.value.trim();
  const password = els.passwordInput.value;
  if (!username || !password) {
    setText(els.authMsg, "Username dan password wajib diisi");
    return;
  }
  send(register ? C2S.REGISTER_REQ : C2S.LOGIN_REQ, { username, password });
  playSfx("click");
}

function restoreSession() {
  const saved = loadSavedSession();
  if (!saved || !saved.token) {
    if (!state.userId) showView("authView");
    return;
  }
  state.restoringSession = true;
  send(C2S.SESSION_LOGIN_REQ, { token: saved.token });
  if (!state.userId) setText(els.authMsg, "Memulihkan session...");
}

function handlePacket(pkt) {
  const type = pkt.type;
  const payload = pkt.payload || {};

  if (type === S2C.PONG) {
    const clientTs = Number(payload.client_ts || 0);
    if (clientTs) els.pingStatus.textContent = `${Math.max(0, Math.round(Date.now() - clientTs * 1000))} ms`;
    return;
  }
  if (type === "WEBRTC_READY") {
    handleRtcReady(payload);
    return;
  }
  if (type === "WEBRTC_PEER_JOINED") {
    handleRtcPeerJoined(payload);
    return;
  }
  if (type === "WEBRTC_SIGNAL") {
    handleRtcSignal(payload);
    return;
  }
  if (type === "WEBRTC_PEER_LEFT") {
    closeRtcPeer(payload.peer_id);
    return;
  }
  if (type === "WEBRTC_REJECTED") {
    setGameMsg(`Voice ditolak: ${payload.reason || "-"}`);
    stopVoice();
    return;
  }

  switch (type) {
    case S2C.REGISTER_OK:
      setText(els.authMsg, "Register berhasil. Silakan login.");
      break;
    case S2C.REGISTER_FAIL:
    case S2C.LOGIN_FAIL:
      if (state.restoringSession) {
        if (payload.reason === "invalid_session") clearSavedSession();
        state.restoringSession = false;
      }
      setText(els.authMsg, `Gagal: ${payload.reason || "-"}`);
      break;
    case S2C.LOGIN_OK:
      onLogin(payload);
      break;
    case S2C.STATS:
      state.stats = payload;
      renderStats();
      break;
    case S2C.TOP_GLOBAL:
      renderLeaderboard(payload.entries || []);
      break;
    case S2C.MATCH_HISTORY:
      renderHistory(payload.entries || []);
      break;
    case S2C.ROOM_CREATED:
    case S2C.JOIN_OK:
    case S2C.MATCH_FOUND:
      state.room = payload;
      state.roomId = payload.room_id || "";
      showView("roomView");
      renderRoom();
      setText(els.lobbyMsg, "");
      break;
    case S2C.JOIN_FAIL:
      setText(els.lobbyMsg, `Join gagal: ${payload.reason || "-"}`);
      break;
    case S2C.ROOM_UPDATE:
      state.room = payload;
      state.roomId = payload.room_id || state.roomId;
      if (!state.game) showView("roomView");
      renderRoom();
      renderGame();
      break;
    case S2C.GAME_START:
      state.hand = payload.hand || [];
      state.game = payload.state || null;
      state.isSpectator = false;
      clearSelection();
      showView("gameView");
      playMusic("game");
      joinVoiceIfEnabled();
      renderGame();
      break;
    case S2C.STATE_UPDATE:
      state.game = payload.state || state.game;
      if (payload.hand) state.hand = payload.hand;
      pruneSelection();
      // Giliran sudah berpindah ke lawan: buang seleksi & pemilih warna yang
      // tertinggal supaya tidak ada aksi basi saat giliran kembali.
      if (!isMyTurn()) {
        clearSelection(false);
        cancelWild(false);
      }
      renderGame();
      break;
    case S2C.DRAW_RESULT:
      // Klik tombol deck sudah memberi suara saat ditekan; jangan dobel di sini.
      if (payload.card) state.hand.push(payload.card);
      renderGame();
      break;
    case S2C.DRAW_STACK_RESULT:
      setGameMsg(`Mengambil ${payload.count || 0} kartu`);
      playSfx("plus");
      break;
    case S2C.ACTION_REJECTED:
      setGameMsg(`Aksi ditolak: ${payload.reason || "-"}`);
      break;
    case S2C.UNO_OK:
      setGameMsg("UNO dipanggil");
      break;
    case S2C.UNO_ANNOUNCE:
      setGameMsg("Pemain memanggil UNO");
      break;
    case S2C.UNO_PENALTY:
      if (Array.isArray(payload.cards)) state.hand.push(...payload.cards);
      setGameMsg("Penalti UNO: +2 kartu");
      playSfx("plus");
      renderGame();
      break;
    case S2C.UNO_CATCH:
      setGameMsg(`${payload.caught_name || "Pemain"} tertangkap lupa UNO`);
      break;
    case S2C.PLAYER_WIN:
      if (payload.user_id === state.userId) {
        setGameMsg("Anda selesai. Masuk spectator sampai match selesai.");
        playSfx("win");
      }
      break;
    case S2C.ENTER_SPECTATOR:
      state.isSpectator = true;
      state.hand = [];
      clearSelection();
      renderGame();
      break;
    case S2C.MATCH_RESULT: {
      // Pemenang sudah mendengar "win" saat PLAYER_WIN; pemain posisi terakhir
      // mendapat isyarat "lose" di sini.
      const details = payload.ranking_details || [];
      const mine = details.find((r) => r.user_id === state.userId);
      const lastPos = details.reduce((m, r) => Math.max(m, r.finish_position || 0), 0);
      if (mine && details.length > 1 && mine.finish_position === lastPos) {
        playSfx("lose");
      }
      renderResult(payload);
      playMusic("lobby");
      showView("resultView");
      break;
    }
    case S2C.LEFT_ROOM:
      resetRoomState();
      showView("lobbyView");
      requestLobbyData();
      break;
    case S2C.FORCE_LOGOUT:
      stopVoice();
      setText(els.authMsg, payload.reason || "Session diambil alih perangkat lain");
      resetToAuth(false);
      break;
    case S2C.ERROR:
      setGameMsg(payload.reason || "Server error");
      break;
    default:
      break;
  }
}

function onLogin(payload) {
  state.restoringSession = false;
  state.socketAuthenticated = true;
  state.userId = payload.user_id;
  state.username = payload.username;
  state.token = payload.token;
  state.stats = payload.stats || null;
  saveSession(payload);
  els.welcomeText.textContent = `Lobby, ${state.username}`;
  setText(els.authMsg, "");
  playMusic("lobby");
  if (payload.resume) {
    const r = payload.resume;
    state.room = r.room;
    state.roomId = r.room_id;
    state.game = r.state;
    state.hand = r.hand || [];
    state.isSpectator = r.role === "SPECTATOR";
    showView("gameView");
    joinVoiceIfEnabled();
    renderGame();
    return;
  }
  showView("lobbyView");
  requestLobbyData();
}

function requestLobbyData() {
  if (!state.userId) return;
  send(C2S.GET_STATS, { user_id: state.userId });
  requestLeaderboard();
  requestHistory();
}

function requestLeaderboard() {
  send(C2S.GET_TOP_GLOBAL, { limit: 20 });
}

function requestHistory() {
  if (!state.userId) return;
  send(C2S.GET_MATCH_HISTORY, { user_id: state.userId, limit: 20 });
}

function setMode(mode) {
  state.selectedMode = mode;
  els.rankedBtn.classList.toggle("selected", mode === "ranked");
  els.classicBtn.classList.toggle("selected", mode === "classic");
}

function renderStats() {
  const st = state.stats || {};
  els.statsBox.innerHTML = [
    stat("Point", st.total_point ?? 0),
    stat("Rank", st.rank_tier || "Bronze"),
    stat("Win", st.total_win ?? 0),
    // win_rate dari server berupa pecahan 0..1 (total_win / total_match).
    stat("Win Rate", `${(Number(st.win_rate || 0) * 100).toFixed(1)}%`),
  ].join("");
}

function stat(label, value) {
  return `<div class="stat"><strong>${escapeHtml(String(value))}</strong><span>${label}</span></div>`;
}

function renderLeaderboard(entries) {
  if (!entries.length) {
    els.leaderboardBox.innerHTML = `<p class="muted">Belum ada data.</p>`;
    return;
  }
  els.leaderboardBox.innerHTML = entries.map((e, idx) => {
    const rank = idx + 1;
    const medal = rank <= 3 ? ` lb-${rank}` : "";
    return `
    <div class="entry${medal}">
      <span class="entry-name"><span class="lb-rank">${rank}</span>${escapeHtml(e.username || "-")}</span>
      <span class="badge">${e.total_point ?? 0} pts</span>
    </div>`;
  }).join("");
}

function renderHistory(entries) {
  if (!entries.length) {
    els.historyBox.innerHTML = `<p class="muted">Belum ada match. Main satu ronde dulu!</p>`;
    return;
  }
  els.historyBox.innerHTML = entries.map((e) => {
    const result = (e.result || "MID").toUpperCase();
    const resultClass = result === "WIN" ? "win" : result === "LOSE" ? "lose" : "mid";
    const resultLabel = result === "WIN" ? "Menang" : result === "LOSE" ? "Kalah" : "Selesai";
    const mode = (e.match_mode || "ranked").toLowerCase();
    const delta = Number(e.point_change || 0);
    const deltaText = mode === "ranked" ? `${delta >= 0 ? "+" : ""}${delta} pts` : "Classic";
    const pos = e.finish_position || "-";
    const total = e.player_count || "-";
    return `
      <div class="history-row">
        <span class="result-tag ${resultClass}">${resultLabel}</span>
        <div class="history-meta">
          <span>Peringkat ${pos}/${total} · ${mode === "ranked" ? "Ranked" : "Classic"}</span>
          <span class="muted">${escapeHtml(e.ended_at || "")}${e.winner_name ? ` · 🏆 ${escapeHtml(e.winner_name)}` : ""}</span>
        </div>
        <span class="badge ${delta > 0 ? "pos" : delta < 0 ? "neg" : ""}">${deltaText}</span>
      </div>
    `;
  }).join("");
}

function renderRoom() {
  const room = state.room || {};
  els.roomCodeText.textContent = room.room_code || "-";
  els.roomMeta.textContent = `${room.match_mode || "ranked"} | ${room.status || "WAITING"}`;
  const players = room.players || [];
  els.roomPlayers.innerHTML = players.map((p) => playerRow(p, room.host_id)).join("");
  els.startBtn.disabled = room.host_id !== state.userId || players.length < 2;
}

function playerRow(p, hostId) {
  const tags = [
    p.user_id === hostId ? "Host" : "",
    p.connected === false ? "Offline" : "Online",
    p.role || "PLAYER",
  ].filter(Boolean).join(" | ");
  return `
    <div class="player-row">
      <span>${escapeHtml(p.username || "-")}</span>
      <span class="badge">${escapeHtml(tags)}</span>
    </div>
  `;
}

function renderGame() {
  const gs = state.game;
  if (!gs) return;
  const players = gs.players || [];
  const current = players.find((p) => p.user_id === gs.current_turn);
  const me = players.find((p) => p.user_id === state.userId);
  const top = gs.top_card || null;

  const myTurn = gs.current_turn === state.userId && !state.isSpectator;
  els.turnInfo.textContent = gs.game_over
    ? "Game selesai"
    : myTurn
      ? `Giliran Anda${gs.pending_draw ? ` | wajib tumpuk/ambil +${gs.pending_draw}` : ""}`
      : `Giliran: ${current ? current.username : "-"}${gs.pending_draw ? ` | Stack +${gs.pending_draw}` : ""}`;
  els.turnInfo.classList.toggle("your-turn", myTurn && !gs.game_over);
  els.playersBox.innerHTML = players.map((p) => `
    <div class="player-row${p.user_id === gs.current_turn && !gs.game_over ? " current" : ""}">
      <span>${escapeHtml(p.username)}${p.user_id === state.userId ? " (Anda)" : ""}</span>
      <span class="badge">${p.hand_count} kartu | ${p.remaining_value} value${p.has_won ? " | Finish" : ""}</span>
    </div>
  `).join("");

  if (top) els.topCardImg.src = cardAsset(top);
  const activeColor = gs.active_color || "";
  els.activeColor.textContent = activeColor || "-";
  els.activeColor.className = `color-pill${activeColor ? ` ${activeColor.toLowerCase()}` : ""}`;
  const pendingDraw = gs.pending_draw || 0;
  // Boleh menarik bila giliran sendiri DAN (ada tumpukan +N yang wajib diambil,
  // ATAU belum menarik di giliran ini). Setelah menarik 1 kartu, deck dimatikan
  // supaya klik berulang tidak ditolak server ("already_drew") — inilah yang
  // tadinya terasa seperti "tidak bisa mengambil kartu".
  els.drawBtn.disabled = !myTurn || (pendingDraw === 0 && !!gs.drawn_this_turn);
  els.unoBtn.disabled = !me || state.isSpectator;
  els.catchUnoBtn.disabled = state.isSpectator;
  els.playSelectedBtn.disabled = !state.selectedCards.length || !myTurn;
  els.clearSelectedBtn.disabled = !state.selectedCards.length;

  els.handBox.innerHTML = "";
  if (state.isSpectator) {
    els.handBox.innerHTML = `<p class="muted">Mode spectator. Tunggu match selesai.</p>`;
    return;
  }
  state.hand.forEach((card, idx) => {
    const btn = document.createElement("button");
    const selected = state.selectedIndices.includes(idx);
    // Sorot kartu yang sah dimainkan sekarang (terangkat + bingkai emas),
    // sesuai aturan tampilan di README. Kartu lain tetap bisa diklik agar
    // multi-play angka sama (yang tidak match top) tetap bisa dipilih.
    const playable = myTurn && isCardPlayable(card, gs);
    btn.className = `card${selected ? " selected" : ""}${playable ? " playable" : ""}`;
    btn.disabled = !myTurn;
    btn.title = `${card.color} ${card.ctype}`;
    btn.innerHTML = `<img src="${cardAsset(card)}" alt="${card.color} ${card.ctype}">`;
    if (selected) {
      const order = state.selectedIndices.indexOf(idx) + 1;
      btn.innerHTML += `<span class="sel-badge">${order}</span>`;
    }
    btn.onclick = () => clickCard(card, idx);
    els.handBox.appendChild(btn);
  });
}

// Replika aturan kecocokan server (Card.matches) untuk menyorot kartu yang
// bisa dimainkan. Saat ada tumpukan +N, hanya kartu +2/+4 yang boleh.
function isCardPlayable(card, gs) {
  if (!card || !gs) return false;
  if ((gs.pending_draw || 0) > 0) {
    return card.ctype === "Draw" || card.ctype === "Wild_Draw";
  }
  if (card.color === "Wild") return true;
  if (card.color === (gs.active_color || "")) return true;
  const top = gs.top_card;
  return !!(top && card.ctype === top.ctype);
}

function clickCard(card, index) {
  if (!isMyTurn()) {
    playSfx("click");
    setGameMsg("Bukan giliran Anda");
    return;
  }
  if (card.color === "Wild") {
    state.pendingWild = card;
    els.colorPicker.classList.remove("hidden");
    clearSelection(false);
    playSfx("click");
    return;
  }
  if (!/^\d+$/.test(card.ctype) || (state.game && state.game.pending_draw > 0)) {
    send(C2S.PLAY_CARD, { card, chosen_color: null });
    playSfx(card.ctype === "Draw" || card.ctype === "Wild_Draw" ? "plus" : "card");
    return;
  }
  if (state.selectedCards.length && state.selectedCards[0].ctype !== card.ctype) {
    clearSelection(false);
  }
  const pos = state.selectedIndices.indexOf(index);
  if (pos >= 0) {
    state.selectedIndices.splice(pos, 1);
    state.selectedCards.splice(pos, 1);
  } else {
    state.selectedIndices.push(index);
    state.selectedCards.push(card);
  }
  playSfx("click");
  renderGame();
}

function playSelected() {
  if (!state.selectedCards.length) return;
  const cards = [...state.selectedCards];
  const payload = { card: cards[0], chosen_color: null };
  if (cards.length > 1) payload.cards = cards;
  send(C2S.PLAY_CARD, payload);
  playSfx("card");
  clearSelection();
}

function chooseWildColor(color) {
  if (!state.pendingWild) return;
  send(C2S.PLAY_CARD, { card: state.pendingWild, chosen_color: color });
  playSfx(state.pendingWild.ctype === "Wild_Draw" ? "plus" : "card");
  state.pendingWild = null;
  els.colorPicker.classList.add("hidden");
}

function cancelWild(sound = true) {
  if (!state.pendingWild) {
    els.colorPicker.classList.add("hidden");
    return;
  }
  state.pendingWild = null;
  els.colorPicker.classList.add("hidden");
  if (sound) playSfx("click");
}

function clearSelection(render = true) {
  state.selectedIndices = [];
  state.selectedCards = [];
  if (render) renderGame();
}

function pruneSelection() {
  const kept = [];
  const cards = [];
  state.selectedIndices.forEach((idx, i) => {
    if (state.hand[idx] && sameCard(state.hand[idx], state.selectedCards[i])) {
      kept.push(idx);
      cards.push(state.selectedCards[i]);
    }
  });
  state.selectedIndices = kept;
  state.selectedCards = cards;
}

function sameCard(a, b) {
  return a && b && a.color === b.color && a.ctype === b.ctype;
}

function isMyTurn() {
  return state.game && state.game.current_turn === state.userId && !state.isSpectator;
}

function renderResult(payload) {
  const names = payload.player_names || {};
  const details = payload.ranking_details || [];
  const results = payload.results || {};
  els.resultBox.innerHTML = details.map((r) => {
    const uid = String(r.user_id);
    const score = results[uid] || {};
    const delta = score.point_change ?? score.delta ?? r.point_change ?? 0;
    const remaining = score.remaining_value ?? r.remaining_value ?? r.hand_count ?? 0;
    return `
      <div class="result-row">
        <span>#${r.finish_position} ${escapeHtml(names[uid] || r.username || "-")}</span>
        <span class="badge">${delta >= 0 ? "+" : ""}${delta} pts | sisa ${r.hand_count} kartu | value ${remaining}</span>
      </div>
    `;
  }).join("");
}

function leaveRoom() {
  send(C2S.LEAVE_ROOM, {});
  playSfx("leave");
  stopVoice();
}

function resetRoomState() {
  state.room = null;
  state.roomId = "";
  state.game = null;
  state.hand = [];
  state.isSpectator = false;
  clearSelection(false);
}

function resetToAuth(sendLeave = true) {
  if (sendLeave && state.roomId) send(C2S.LEAVE_ROOM, {});
  stopVoice();
  resetRoomState();
  state.userId = null;
  state.username = "";
  state.token = "";
  state.stats = null;
  clearSavedSession();
  showView("authView");
}

function showView(id) {
  ["authView", "lobbyView", "roomView", "gameView", "resultView"].forEach((viewId) => {
    els[viewId].classList.toggle("hidden", viewId !== id);
  });
  // Bersihkan sisa notifikasi dari view sebelumnya agar tidak menempel.
  setText(els.gameMsg, "");
  setText(els.roomMsg, "");
  setText(els.lobbyMsg, "");
}

function cardAsset(card) {
  if (!card) return "/assets/cards/Deck.png";
  if (card.color === "Wild") return `/assets/cards/${card.ctype}.png`;
  return `/assets/cards/${card.color}_${card.ctype}.png`;
}

function playSfx(name) {
  if (!state.soundOn) return;
  const pool = sfxPool[name];
  if (!pool) return;
  const audio = pool[pool._i % pool.length];
  pool._i++;
  try {
    audio.currentTime = 0;
  } catch {
    // currentTime bisa gagal sebelum media siap; abaikan.
  }
  audio.volume = SFX_VOL[name] ?? 0.6;
  audio.play().catch(() => {});
}

function playMusic(name) {
  if (!state.soundOn) return;
  const src = name === "game" ? "/assets/sounds/game_bgm.mp3" : "/assets/sounds/lobby.mp3";
  if (state.music && state.music.src.endsWith(src)) {
    // Trek yang sama sudah dimuat. Jika sempat di-pause (mis. habis di-mute lalu
    // di-unmute), lanjutkan lagi alih-alih diam — ini bug "musik tidak balik".
    if (state.music.paused) state.music.play().catch(() => {});
    return;
  }
  if (state.music) state.music.pause();
  state.music = new Audio(src);
  state.music.loop = true;
  state.music.volume = 0.28;
  state.music.play().catch(() => {});
}

function toggleSound() {
  state.soundOn = !state.soundOn;
  els.soundBtn.textContent = state.soundOn ? "Sound" : "Muted";
  if (!state.soundOn && state.music) state.music.pause();
  if (state.soundOn) playMusic(state.game ? "game" : "lobby");
}

async function toggleVoice() {
  if (state.voiceOn) {
    stopVoice();
    return;
  }
  if (!state.token || !state.roomId) {
    setGameMsg("Masuk match dulu untuk voice");
    return;
  }
  try {
    await startVoice();
  } catch (err) {
    const secureHint = location.protocol !== "https:" && location.hostname !== "localhost"
      ? " Browser butuh HTTPS untuk akses mic di IP/domain publik."
      : "";
    setGameMsg(`Mic gagal aktif.${secureHint}`);
  }
}

async function startVoice() {
  state.localStream = await navigator.mediaDevices.getUserMedia({
    audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
  });
  state.voiceOn = true;
  els.voiceBtn.textContent = "Voice...";
  setGameMsg("Voice aktif, menunggu peer...");
  joinVoiceIfEnabled();
}

function joinVoiceIfEnabled() {
  if (!state.voiceOn || !state.roomId) return;
  send("WEBRTC_JOIN", {
    token: state.token,
    room_id: state.roomId,
    user_id: state.userId,
    username: state.username,
  });
}

function stopVoice() {
  send("WEBRTC_LEAVE", {});
  state.voiceOn = false;
  state.rtcPeerId = "";
  els.voiceBtn.textContent = "Mic Off";
  for (const peerId of Array.from(state.rtcPeers.keys())) {
    closeRtcPeer(peerId);
  }
  if (state.localStream) {
    state.localStream.getTracks().forEach((track) => track.stop());
  }
  state.localStream = null;
}

async function handleRtcReady(payload) {
  state.rtcPeerId = payload.peer_id || "";
  els.voiceBtn.textContent = "Mic On";
  const peers = payload.peers || [];
  setGameMsg(peers.length ? "Voice menghubungkan peer..." : "Voice aktif. Menunggu pemain lain aktifkan mic.");
  for (const peer of peers) {
    await createRtcPeer(peer.peer_id, true);
  }
}

async function handleRtcPeerJoined(payload) {
  if (!state.voiceOn || !payload.peer_id) return;
  setGameMsg("Voice peer masuk, menghubungkan...");
  await createRtcPeer(payload.peer_id, false);
}

// Tuning Opus agar suara tidak patah-patah: aktifkan in-band FEC (tahan packet
// loss), matikan DTX (hindari potongan saat hening), paksa mono + bitrate stabil.
function tuneOpusSdp(sdp) {
  if (!sdp) return sdp;
  const lines = sdp.split("\r\n");
  let pt = null;
  for (const line of lines) {
    const m = line.match(/^a=rtpmap:(\d+)\s+opus\/48000/i);
    if (m) { pt = m[1]; break; }
  }
  if (!pt) return sdp;
  const params = "minptime=10;useinbandfec=1;usedtx=0;stereo=0;maxaveragebitrate=40000";
  let applied = false;
  for (let i = 0; i < lines.length; i++) {
    if (lines[i].startsWith(`a=fmtp:${pt}`)) {
      lines[i] = `a=fmtp:${pt} ${params}`;
      applied = true;
      break;
    }
  }
  if (!applied) {
    for (let i = 0; i < lines.length; i++) {
      if (lines[i].startsWith(`a=rtpmap:${pt} opus`)) {
        lines.splice(i + 1, 0, `a=fmtp:${pt} ${params}`);
        break;
      }
    }
  }
  return lines.join("\r\n");
}

async function setTunedLocalDescription(pc, desc) {
  desc.sdp = tuneOpusSdp(desc.sdp);
  await pc.setLocalDescription(desc);
}

async function createRtcPeer(peerId, initiator) {
  if (!state.localStream || state.rtcPeers.has(peerId)) return state.rtcPeers.get(peerId);
  const pc = new RTCPeerConnection({
    iceServers: TURN_ICE_SERVERS,
    iceCandidatePoolSize: 4,
  });
  pc._pendingCandidates = [];
  pc._voiceTimer = setTimeout(() => {
    if (!["connected", "completed"].includes(pc.iceConnectionState)) {
      setGameMsg("Voice belum tersambung. Jika beda jaringan, buka TURN 3478 tcp/udp dan 49160-49200 udp di NSG.");
    }
  }, 6000);
  state.localStream.getTracks().forEach((track) => pc.addTrack(track, state.localStream));
  pc.onicecandidate = (ev) => {
    if (ev.candidate) {
      send("WEBRTC_SIGNAL", { target: peerId, data: { candidate: ev.candidate } });
    }
  };
  pc.ontrack = (ev) => {
    attachRemoteAudio(peerId, ev.streams[0]);
  };
  pc.onconnectionstatechange = () => {
    if (pc.connectionState === "connected") {
      clearTimeout(pc._voiceTimer);
      setGameMsg("Voice tersambung");
    }
    if (["failed", "closed"].includes(pc.connectionState)) {
      closeRtcPeer(peerId);
    }
  };
  pc.oniceconnectionstatechange = () => {
    if (pc.iceConnectionState === "connected" || pc.iceConnectionState === "completed") {
      clearTimeout(pc._voiceTimer);
      setGameMsg("Voice tersambung");
    } else if (pc.iceConnectionState === "failed") {
      setGameMsg("Voice gagal tersambung. Cek TURN/NSG 3478 dan 49160-49200 udp.");
    }
  };
  state.rtcPeers.set(peerId, pc);
  if (initiator) {
    const offer = await pc.createOffer({ offerToReceiveAudio: true });
    await setTunedLocalDescription(pc, offer);
    send("WEBRTC_SIGNAL", { target: peerId, data: { description: pc.localDescription } });
  }
  return pc;
}

async function handleRtcSignal(payload) {
  if (!state.voiceOn || !payload.from || !payload.data) return;
  const pc = await createRtcPeer(payload.from, false);
  const data = payload.data;
  if (data.description) {
    await pc.setRemoteDescription(data.description);
    while (pc._pendingCandidates && pc._pendingCandidates.length) {
      try {
        await pc.addIceCandidate(pc._pendingCandidates.shift());
      } catch {
        // Ignore stale candidates.
      }
    }
    if (data.description.type === "offer") {
      const answer = await pc.createAnswer();
      await setTunedLocalDescription(pc, answer);
      send("WEBRTC_SIGNAL", { target: payload.from, data: { description: pc.localDescription } });
    }
  } else if (data.candidate) {
    if (!pc.remoteDescription) {
      pc._pendingCandidates.push(data.candidate);
      return;
    }
    try {
      await pc.addIceCandidate(data.candidate);
    } catch {
      // ICE candidates can arrive during close/reconnect; ignore stale ones.
    }
  }
}

function attachRemoteAudio(peerId, stream) {
  let audio = document.getElementById(`voice-${peerId}`);
  if (!audio) {
    audio = document.createElement("audio");
    audio.id = `voice-${peerId}`;
    audio.autoplay = true;
    audio.playsInline = true;
    audio.dataset.voicePeer = peerId;
    document.body.appendChild(audio);
  }
  audio.srcObject = stream;
  audio.muted = false;
  audio.volume = 1;
  audio.play().catch(() => {});
}

function closeRtcPeer(peerId) {
  const pc = state.rtcPeers.get(peerId);
  if (pc) {
    clearTimeout(pc._voiceTimer);
    pc.close();
  }
  state.rtcPeers.delete(peerId);
  const audio = document.getElementById(`voice-${peerId}`);
  if (audio) audio.remove();
}

function setGameMsg(text) {
  // Notifikasi hanya tampil di panel view yang sedang aktif. Sebelumnya pesan
  // ditulis ke gameMsg + roomMsg + lobbyMsg sekaligus, sehingga teks in-game
  // (mis. "Mengambil 8 kartu") nyangkut di layar lobby/room dan terlihat seperti
  // output debug yang nyasar.
  setText(els.gameMsg, "");
  setText(els.roomMsg, "");
  setText(els.lobbyMsg, "");
  let target = null;
  if (!els.gameView.classList.contains("hidden")) target = els.gameMsg;
  else if (!els.roomView.classList.contains("hidden")) target = els.roomMsg;
  else if (!els.lobbyView.classList.contains("hidden")) target = els.lobbyMsg;
  if (target) setText(target, text);
}

function setText(el, text) {
  if (el) el.textContent = text;
}

function saveSession(payload) {
  if (!payload || !payload.token) return;
  localStorage.setItem(SESSION_KEY, JSON.stringify({
    token: payload.token,
    user_id: payload.user_id,
    username: payload.username,
  }));
}

function loadSavedSession() {
  try {
    return JSON.parse(localStorage.getItem(SESSION_KEY) || "null");
  } catch {
    return null;
  }
}

function clearSavedSession() {
  localStorage.removeItem(SESSION_KEY);
}

function escapeHtml(value) {
  return value.replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  }[ch]));
}

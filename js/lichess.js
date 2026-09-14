/* Lichess API: pull a user's games, and merge them into an opening tree
 * so you can drill the openings you actually play — blindfolded. */
(function (global) {
  'use strict';

  const CACHE_KEY = 'blindfold-lichess-cache-v1';

  // Share only public account identity with forms; the token stays on the server.
  let identity=null,identityRequest=null,identityVersion=0;
  const accountFields=new Map();
  function setIdentity(value){
    identityVersion++;identity=value;
    for(const [input,refresh] of accountFields){if(input.isConnected)refresh();else accountFields.delete(input);}
    global.dispatchEvent(new CustomEvent('caissa-account-changed',{detail:value}));
    return value;
  }
  async function account(){
    if(identity)return identity;
    if(!identityRequest){const version=identityVersion;
      identityRequest=fetch('/api/lichess/account').then(r=>{if(!r.ok)throw new Error('Account unavailable');return r.json();})
        .then(data=>version===identityVersion?setIdentity(data):identity)
        .catch(()=>({connected:false})).finally(()=>{identityRequest=null;});
    }
    return identityRequest;
  }
  function fillAccount(input,enabled=()=>true){
    let automatic='',edited=false;
    input.addEventListener('input',()=>{edited=true;});
    function refresh(){
      const name=enabled()&&identity?.connected?identity.username||'':'';
      if(!name){if(automatic&&input.value===automatic)input.value='';automatic='';return;}
      if(!edited||!input.value||input.value===automatic){input.value=name;automatic=name;}
    }
    for(const existing of accountFields.keys())if(!existing.isConnected)accountFields.delete(existing);
    accountFields.set(input,refresh);refresh();account().then(refresh);
    return refresh;
  }
  global.CaissaAccount={get:account,set:setIdentity,fill:fillAccount};

  function cacheRead() {
    try { return JSON.parse(localStorage.getItem(CACHE_KEY)) || {}; } catch (e) { return {}; }
  }
  function cacheWrite(obj) {
    try { localStorage.setItem(CACHE_KEY, JSON.stringify(obj)); } catch (e) { /* quota */ }
  }

  function splitGames(text) {
    return String(text)
      .split(/\n(?=\[Event )/)
      .map(function (s) { return s.trim(); })
      .filter(function (s) { return s.length > 0; });
  }

  /* Lichess allows exactly ONE export request at a time per IP, and punishes a
   * second one with 429 plus a cooldown. So: never run two at once, never run
   * them back to back, and wait it out politely when we are told to. */
  let inFlight = null;            // the promise of the request currently running
  let lastFinished = 0;           // when the last request ended
  const MIN_GAP_MS = 4000;        // breathing room between exports
  const COOLDOWN_MS = 65000;      // what lichess asks for after a 429
  let cooldownUntil = 0;

  function token() {
    try { return localStorage.getItem('blindfold-lichess-token') || ''; } catch (e) { return ''; }
  }
  function setToken(value) {
    try {
      if (value) localStorage.setItem('blindfold-lichess-token', value.trim());
      else localStorage.removeItem('blindfold-lichess-token');
    } catch (e) { /* private mode */ }
  }

  function cooldownLeft() { return Math.max(0, cooldownUntil - Date.now()); }
  function busy() { return !!inFlight; }

  function wait(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }

  function parseAll(pgns) {
    return pgns.map(function (pgn) {
      const parsed = PGN.parse(pgn);
      return { pgn: pgn, headers: parsed.headers, root: parsed.root, parsedOk: parsed.errors.length === 0 };
    });
  }

  /* opts: { user, max, color, rated, perf, since, onStatus, retries } */
  function fetchGames(opts) {
    const user = String(opts.user || '').trim();
    if (!user) return Promise.reject(new Error('Enter a lichess username first.'));
    const say = opts.onStatus || function () {};

    /* a second click while one is running joins the request already in progress */
    if (inFlight) {
      say('Already fetching from lichess — waiting for that request to finish.');
      return inFlight;
    }

    const params = [
      'max=' + (opts.max || 50),
      'moves=true', 'tags=true', 'clocks=false', 'evals=false',
      'opening=true', 'sort=dateDesc'
    ];
    if (opts.color) params.push('color=' + opts.color);
    if (opts.rated === true) params.push('rated=true');
    if (opts.perf) params.push('perfType=' + opts.perf);
    if (opts.since) params.push('since=' + opts.since);

    const url = 'https://lichess.org/api/games/user/' + encodeURIComponent(user) + '?' + params.join('&');
    const headers = { Accept: 'application/x-chess-pgn' };
    const auth = token();
    if (auth) headers.Authorization = 'Bearer ' + auth;

    let attemptsLeft = (opts.retries === undefined) ? 1 : opts.retries;

    function attempt() {
      const gap = Math.max(cooldownLeft(), MIN_GAP_MS - (Date.now() - lastFinished));
      const prelude = gap > 0 ? countdown(gap, say) : Promise.resolve();

      return prelude.then(function () {
        say('Fetching games from lichess…');
        return fetch(url, { headers: headers });
      }).then(function (res) {
        if (res.status === 404) throw new Error('No such lichess user: ' + user);
        if (res.status === 401) throw new Error('Lichess rejected the API token.');
        if (res.status === 429) {
          const retryAfter = parseInt(res.headers.get('Retry-After') || '', 10);
          cooldownUntil = Date.now() + (isNaN(retryAfter) ? COOLDOWN_MS : retryAfter * 1000);
          if (attemptsLeft > 0) {
            attemptsLeft--;
            return attempt();
          }
          throw new Error('Lichess is rate limiting this IP (only one export at a time). ' +
            'Wait about a minute, then try again — cached games still work meanwhile.');
        }
        if (!res.ok) throw new Error('Lichess returned ' + res.status);
        return res.text().then(function (text) {
          const pgns = splitGames(text);
          const games = parseAll(pgns);
          const cache = cacheRead();
          cache[user.toLowerCase()] = { at: Date.now(), pgns: pgns };
          cacheWrite(cache);
          return games;
        });
      });
    }

    inFlight = attempt();
    const settle = function () { inFlight = null; lastFinished = Date.now(); };
    inFlight.then(settle, settle);
    return inFlight;
  }

  function countdown(ms, say) {
    const until = Date.now() + ms;
    return new Promise(function (resolve) {
      (function loop() {
        const left = until - Date.now();
        if (left <= 0) { resolve(); return; }
        say('Lichess asked us to slow down — retrying in ' + Math.ceil(left / 1000) + 's…');
        setTimeout(loop, 500);
      })();
    });
  }

  function cachedGames(user) {
    const entry = cacheRead()[String(user || '').toLowerCase()];
    if (!entry) return null;
    return {
      at: entry.at,
      games: entry.pgns.map(function (pgn) {
        const parsed = PGN.parse(pgn);
        return { pgn: pgn, headers: parsed.headers, root: parsed.root, parsedOk: parsed.errors.length === 0 };
      })
    };
  }

  function clearCache() { cacheWrite({}); }

  function playerColor(headers, user) {
    const u = String(user).toLowerCase();
    if (String(headers.White || '').toLowerCase() === u) return 'w';
    if (String(headers.Black || '').toLowerCase() === u) return 'b';
    return null;
  }

  function resultFor(headers, color) {
    const r = headers.Result;
    if (r === '1-0') return color === 'w' ? 'win' : 'loss';
    if (r === '0-1') return color === 'b' ? 'win' : 'loss';
    if (r === '1/2-1/2') return 'draw';
    return 'unknown';
  }

  /* Merge many games into one weighted tree:
   *   node = { san, children:{san:node}, count, wins, draws, losses, ply, fenAfter }
   * Your moves and your opponents' moves are both counted, so the drill can ask
   * "what do you normally play here?" and answer with what they normally played. */
  function buildRepertoire(games, opts) {
    opts = opts || {};
    const user = opts.user;
    const wantColor = opts.color || null;      // 'w' | 'b' | null
    const maxPly = opts.maxPly || 16;
    const minCount = opts.minCount || 1;

    const root = { san: null, children: {}, count: 0, wins: 0, draws: 0, losses: 0, ply: 0,
                   fenAfter: Chess.DEFAULT_FEN, openings: {}, openingCounts: {} };
    let used = 0;

    games.forEach(function (g) {
      const color = playerColor(g.headers, user);
      if (!color) return;
      if (wantColor && color !== wantColor) return;
      if (g.headers.Variant && g.headers.Variant !== 'Standard') return;
      if (g.headers.FEN) return;
      const line = PGN.mainline(g.root);
      if (!line.length) return;
      used++;
      const outcome = resultFor(g.headers, color);
      const opening = g.headers.Opening || g.headers.ECO || 'Unknown opening';
      root.openingCounts[opening] = (root.openingCounts[opening] || 0) + 1;

      let node = root;
      node.count++;
      for (let i = 0; i < Math.min(line.length, maxPly); i++) {
        const san = line[i].san;
        if (!node.children[san]) {
          node.children[san] = {
            san: san, children: {}, count: 0, wins: 0, draws: 0, losses: 0,
            ply: node.ply + 1, fenAfter: line[i].fenAfter, openings: {}
          };
        }
        node = node.children[san];
        node.count++;
        if (outcome === 'win') node.wins++;
        else if (outcome === 'loss') node.losses++;
        else if (outcome === 'draw') node.draws++;
        node.openings[opening] = (node.openings[opening] || 0) + 1;
      }
    });

    prune(root, minCount);
    root.gamesUsed = used;
    root.color = wantColor;
    return root;
  }

  function prune(node, minCount) {
    Object.keys(node.children).forEach(function (san) {
      const child = node.children[san];
      if (child.count < minCount) delete node.children[san];
      else prune(child, minCount);
    });
  }

  function kids(node) {
    return Object.keys(node.children)
      .map(function (san) { return node.children[san]; })
      .sort(function (a, b) { return b.count - a.count; });
  }

  /* pick an opponent reply, weighted by how often it actually happened */
  function sampleChild(node) {
    const list = kids(node);
    if (!list.length) return null;
    let total = 0;
    list.forEach(function (c) { total += c.count; });
    let r = Math.random() * total;
    for (let i = 0; i < list.length; i++) {
      r -= list[i].count;
      if (r <= 0) return list[i];
    }
    return list[0];
  }

  /* the distinct openings you reached, most played first */
  function openingSummary(root) {
    const counts = root.openingCounts || {};
    return Object.keys(counts)
      .map(function (name) { return { name: name, count: counts[name] }; })
      .sort(function (a, b) { return b.count - a.count; });
  }

  /* narrow a tree to lines that end up in a named opening */
  function filterByOpening(root, openingName) {
    function clone(node) {
      const copy = {
        san: node.san, children: {}, count: node.count, wins: node.wins, draws: node.draws,
        losses: node.losses, ply: node.ply, fenAfter: node.fenAfter, openings: node.openings
      };
      let keep = (node.openings && node.openings[openingName]) ? true : false;
      kids(node).forEach(function (child) {
        const c = clone(child);
        if (c) { copy.children[child.san] = c; keep = true; }
      });
      return keep ? copy : null;
    }
    const out = clone(root) || { san: null, children: {}, count: 0, ply: 0, fenAfter: Chess.DEFAULT_FEN };
    out.gamesUsed = root.gamesUsed;
    out.color = root.color;
    return out;
  }

  global.Lichess = {
    fetchGames: fetchGames,
    cachedGames: cachedGames,
    clearCache: clearCache,
    token: token,
    setToken: setToken,
    busy: busy,
    cooldownLeft: cooldownLeft,
    splitGames: splitGames,
    playerColor: playerColor,
    resultFor: resultFor,
    buildRepertoire: buildRepertoire,
    kids: kids,
    sampleChild: sampleChild,
    openingSummary: openingSummary,
    filterByOpening: filterByOpening
  };
})(window);

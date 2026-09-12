/* PGN reader -> move tree (variations kept: they are the deviations you must punish). */
(function (global) {
  'use strict';

  function makeNode(parent, san, move, fenAfter) {
    return {
      san: san, move: move, parent: parent, children: [],
      fenAfter: fenAfter,
      comment: null, nags: [],
      ply: parent ? parent.ply + 1 : 0
    };
  }

  function parse(text) {
    const headers = {};
    let body = String(text).replace(/\r/g, '');

    body = body.replace(/^\s*\[([A-Za-z0-9_]+)\s+"((?:[^"\\]|\\.)*)"\]\s*$/gm, function (_, k, v) {
      headers[k] = v.replace(/\\([\\"])/g,'$1');
      return '';
    });

    const startFen = headers.FEN || Chess.DEFAULT_FEN;
    const root = makeNode(null, null, null, startFen);
    root.headers = headers;

    let game = new Chess(startFen);
    let cur = root;
    const stack = [];
    const errors = [];

    const tokenRe = /(\{[^}]*\}|;[^\n]*)|(\()|(\))|(\$\d+|!!|\?\?|!\?|\?!|!|\?)|(1-0|0-1|1\/2-1\/2|\*)|(\d+\.(?:\.\.)?)|([OoA-Za-z][A-Za-z0-9#+=\-]*)|(\S)/g;
    let m;
    while ((m = tokenRe.exec(body)) !== null) {
      if (m[1]) { const note=(m[1][0]===';'?m[1].slice(1):m[1].slice(1,-1)).trim();cur.comment=[cur.comment,note].filter(Boolean).join('\n');continue; }
      if (m[2]) {                       // start variation: alternative to cur
        stack.push(cur);
        cur = cur.parent || root;
        game = new Chess(cur.fenAfter);
        continue;
      }
      if (m[3]) {                       // end variation
        cur = stack.pop() || root;
        game = new Chess(cur.fenAfter);
        continue;
      }
      if (m[4]) { cur.nags.push(({'!':'$1','?':'$2','!!':'$3','??':'$4','!?':'$5','?!':'$6'})[m[4]]||m[4]); continue; }
      if (m[5] || m[6]) continue;       // result / move number
      if (m[7]) {
        const san = m[7];
        if (/^[A-Za-z]$/.test(san)) continue;
        const done = game.move(san);
        if (!done) { errors.push(san); continue; }
        const node = makeNode(cur, done.san, done, game.fen());
        cur.children.push(node);
        cur = node;
      }
    }

    return { headers: headers, root: root, startFen: startFen, errors: errors };
  }

  function mainline(root) {
    const out = [];
    let n = root;
    while (n.children.length) { n = n.children[0]; out.push(n); }
    return out;
  }

  function pathTo(node) {
    const out = [];
    let n = node;
    while (n && n.parent) { out.unshift(n); n = n.parent; }
    return out;
  }

  /* "1. e4 e5 2. Nf3" for a list of nodes */
  function lineToText(nodes, startPly) {
    let out = '', ply = startPly || 0;
    nodes.forEach(function (n) {
      if (ply % 2 === 0) out += (Math.floor(ply / 2) + 1) + '. ';
      out += n.san + ' ';
      ply++;
    });
    return out.trim();
  }

  /* split a plain move list (no variations) into [{num, white, black}] rows */
  function rows(sans) {
    const out = [];
    for (let i = 0; i < sans.length; i += 2) {
      out.push({ num: (i / 2) + 1, white: sans[i], black: sans[i + 1] || '' });
    }
    return out;
  }

  global.PGN = { parse: parse, mainline: mainline, pathTo: pathTo, lineToText: lineToText, rows: rows };
})(window);

/* Shared chart + page helpers for the Deadlock dashboards (no dependencies, works from file://). */
const NS = 'http://www.w3.org/2000/svg';
const $ = (id) => document.getElementById(id);
function el(tag, attrs, parent, text) {
  const e = document.createElementNS(NS, tag);
  for (const k in attrs || {}) e.setAttribute(k, attrs[k]);
  if (text !== undefined) e.textContent = text;
  if (parent) parent.appendChild(e);
  return e;
}
function h(tag, attrs, html, parent) {
  const e = document.createElement(tag);
  for (const k in attrs || {}) e.setAttribute(k, attrs[k]);
  if (html !== undefined) e.innerHTML = html;
  if (parent) parent.appendChild(e);
  return e;
}
const tip = (n, t) => el('title', {}, n, t);
const mm = (s) => Math.floor(s / 60) + ':' + String(Math.round(s % 60)).padStart(2, '0');
const k = (v) => (v < 0 ? '-' : '') + (Math.abs(v) >= 1000 ? (Math.abs(v) / 1000).toFixed(1) + 'k' : Math.round(Math.abs(v)));
const num = (v) => Math.round(v).toLocaleString();
const pct = (v) => Math.round(v * 100) + '%';
const sgn = (v, d = 1) => (v >= 0 ? '+' : '') + v.toFixed(d);
function sc(d0, d1, r0, r1) { return (v) => r0 + (v - d0) / ((d1 - d0) || 1) * (r1 - r0); }
function svg(container, w, hgt, cls) {
  const s = el('svg', { viewBox: `0 0 ${w} ${hgt}`, width: '100%', class: cls || '' }, container);
  return s;
}
function legend(container, items) {
  h('div', { class: 'legend' }, items.map(([c, t]) => `<span><i style="background:${c}"></i>${t}</span>`).join(''), container);
}
const HABIT_SHORT = { deaths: 'Deaths', early: 'Lane deaths', first: 'First to die', resist: 'Resist late', t3: 'Slow T3', lane: 'Lane', souls: 'Souls' };

/* ---------------------------------------------------------------- per-match charts */
function timeline(c, M) {
  const W = 1100, H = 300, m = { l: 86, r: 10, t: 26, b: 70 };
  const s = svg(c, W, H, 'wide'), dur = M.dur;
  const lim = Math.max(1000, ...M.nw_curve.map(p => Math.abs(p.gap)));
  const x = sc(0, dur, m.l, W - m.r), y = sc(-lim, lim, H - m.b, m.t);
  for (let t = 0; t <= dur; t += 300) { el('line', { x1: x(t), x2: x(t), y1: m.t, y2: H - m.b, class: 'axis' }, s); el('text', { x: x(t), y: H - m.b + 13, 'text-anchor': 'middle', class: 'mute' }, s, Math.round(t / 60) + 'm'); }
  for (const f of M.fights) { const r = el('rect', { x: x(f.t0) - 1, y: m.t, width: Math.max(4, x(f.t1) - x(f.t0)) + 2, height: H - m.b - m.t, fill: `var(--${{ won: 'win', lost: 'loss', even: 'even' }[f.res]})`, opacity: .16 }, s); tip(r, `${mm(f.t0)} fight ${f.res.toUpperCase()}: ${f.theirs} enemy / ${f.ours} ally deaths; you ${f.pres}${f.kill ? ', got a kill' : ''}`); }
  el('line', { x1: m.l, x2: W - m.r, y1: y(0), y2: y(0), class: 'axis' }, s);
  el('text', { x: m.l - 6, y: y(lim) + 4, 'text-anchor': 'end', class: 'mute' }, s, k(lim));
  el('text', { x: m.l - 6, y: y(-lim) + 4, 'text-anchor': 'end', class: 'mute' }, s, k(-lim));
  el('text', { x: m.l - 6, y: y(0) + 4, 'text-anchor': 'end', class: 'mute' }, s, '0');
  el('text', { x: m.l, y: 14 }, s, 'Team net-worth gap (your team minus enemy)').style.fontWeight = 600;
  el('polyline', { points: M.nw_curve.map(p => x(p.t) + ',' + y(p.gap)).join(' '), fill: 'none', stroke: 'var(--accent)', 'stroke-width': 2.2 }, s);
  // event rows under the chart
  const rows = { death: H - m.b + 26, kill: H - m.b + 40, obj: H - m.b + 54, item: H - m.b + 66 };
  el('text', { x: m.l - 6, y: rows.death + 4, 'text-anchor': 'end', class: 'mute' }, s, 'deaths');
  el('text', { x: m.l - 6, y: rows.kill + 4, 'text-anchor': 'end', class: 'mute' }, s, 'kills');
  el('text', { x: m.l - 6, y: rows.obj + 4, 'text-anchor': 'end', class: 'mute' }, s, 'objectives');
  el('text', { x: m.l - 6, y: rows.item + 4, 'text-anchor': 'end', class: 'mute' }, s, 'resist items');
  for (const d of M.deaths) { const n = el('path', { d: `M${x(d.t)} ${rows.death - 5} l5 9 l-10 0 z`, fill: 'var(--ink)' }, s); tip(n, `Death ${mm(d.t)} - killed by ${d.killer}; ${d.allies} ally / ${d.enemies} enemy near; respawn ${d.respawn}s`); }
  for (const t of M.kills) { const n = el('circle', { cx: x(t), cy: rows.kill, r: 4, fill: 'var(--accent)' }, s); tip(n, 'Kill ' + mm(t)); }
  for (const o of M.objectives) { const n = el('rect', { x: x(o.t) - 3, y: rows.obj - 4, width: 7, height: 7, fill: o.mine ? 'var(--win)' : 'var(--loss)' }, s); tip(n, `${mm(o.t)} ${o.name} ${o.mine ? 'destroyed by your team' : 'lost'}`); }
  for (const b of M.midboss) { const n = el('path', { d: `M${x(b.t)} ${m.t + 2} l6 6 l-6 6 l-6 -6 z`, fill: b.mine ? 'var(--win)' : 'var(--loss)' }, s); tip(n, `Mid boss claimed by ${b.mine ? 'your team' : 'the enemy'} at ${mm(b.t)}`); }
  for (const i of M.items.filter(i => i.tags.some(t => /^(spirit|bullet)_resist=/.test(t)))) { const n = el('rect', { x: x(i.t) - 4, y: rows.item - 4, width: 8, height: 8, fill: 'var(--ability)' }, s); tip(n, `${mm(i.t)} bought ${i.name} [${i.tags.join(', ')}]`); }
  legend(c, [['var(--win)', 'won fight / your objective / your mid boss'], ['var(--loss)', 'lost fight / lost objective / enemy mid boss'], ['var(--ink)', 'your death'], ['var(--accent)', 'your kill'], ['var(--ability)', 'resist item bought']]);
}

function laneNW(c, M) {
  const W = 540, H = 240, m = { l: 48, r: 10, t: 24, b: 22 }, s = svg(c, W, H);
  const T = M.nw_curve.filter(p => p.t <= M.dur), all = T.flatMap(p => [p.me, ...p.opp, ...p.mate]);
  const x = sc(0, M.dur, m.l, W - m.r), y = sc(0, Math.max(...all), H - m.b, m.t);
  el('text', { x: m.l, y: 14 }, s, 'Net worth in lane: you vs lane opponents').style.fontWeight = 600;
  for (let t = 0; t <= M.dur; t += 600) el('text', { x: x(t), y: H - 6, 'text-anchor': 'middle', class: 'mute' }, s, Math.round(t / 60) + 'm');
  el('text', { x: m.l - 6, y: y(Math.max(...all)) + 4, 'text-anchor': 'end', class: 'mute' }, s, k(Math.max(...all)));
  const line = (vals, col, w, dash, name) => { const p = el('polyline', { points: T.map((q, i) => x(q.t) + ',' + y(vals[i])).join(' '), fill: 'none', stroke: col, 'stroke-width': w, 'stroke-dasharray': dash || '' }, s); tip(p, name); };
  M.lane_opp.forEach((n, j) => line(T.map(p => p.opp[j]), j ? 'var(--bullet)' : 'var(--loss)', 1.6, j ? '4 3' : '', 'Opponent ' + n));
  M.lane_mate.forEach((n, j) => line(T.map(p => p.mate[j]), 'var(--even)', 1.6, '2 3', 'Lane partner ' + n));
  line(T.map(p => p.me), 'var(--accent)', 2.6, '', 'You');
  legend(c, [['var(--accent)', 'you'], ['var(--even)', 'lane partner'], ['var(--loss)', 'opponent 1: ' + (M.lane_opp[0] || '-')], ['var(--bullet)', 'opponent 2: ' + (M.lane_opp[1] || '-')]]);
}

function laneDuo(c, M) {
  const W = 540, H = 240, m = { l: 48, r: 10, t: 24, b: 22 }, s = svg(c, W, H), T = M.lane_curve;
  el('text', { x: m.l, y: 14 }, s, 'Your duo lead vs a typical ' + M.hero + ' duo').style.fontWeight = 600;
  if (!T.length) { el('text', { x: m.l, y: 60, class: 'mute' }, s, 'no benchmark data for this hero/lane'); return; }
  const lo = Math.min(...T.map(p => Math.min(p.mine, p.mean - p.sd))), hi = Math.max(...T.map(p => Math.max(p.mine, p.mean + p.sd)));
  const x = sc(T[0].t, T[T.length - 1].t, m.l, W - m.r), y = sc(lo, hi, H - m.b, m.t);
  el('polygon', { points: T.map(p => x(p.t) + ',' + y(p.mean + p.sd)).concat(T.slice().reverse().map(p => x(p.t) + ',' + y(p.mean - p.sd))).join(' '), fill: 'var(--even)', 'fill-opacity': .28 }, s);
  el('line', { x1: m.l, x2: W - m.r, y1: y(0), y2: y(0), class: 'axis' }, s);
  el('polyline', { points: T.map(p => x(p.t) + ',' + y(p.mean)).join(' '), fill: 'none', stroke: 'var(--even)', 'stroke-width': 1.5, 'stroke-dasharray': '4 3' }, s);
  el('polyline', { points: T.map(p => x(p.t) + ',' + y(p.mine)).join(' '), fill: 'none', stroke: 'var(--accent)', 'stroke-width': 2.4 }, s);
  for (const p of T) { const d = el('circle', { cx: x(p.t), cy: y(p.mine), r: 3.5, fill: 'var(--accent)' }, s); tip(d, `${mm(p.t)}: you ${num(p.mine)} vs typical ${num(p.mean)} (${sgn(p.z)} sd)`); }
  el('text', { x: m.l - 6, y: y(lo) - 2, 'text-anchor': 'end', class: 'mute' }, s, k(lo)); el('text', { x: m.l - 6, y: y(hi) + 4, 'text-anchor': 'end', class: 'mute' }, s, k(hi));
  T.filter((_, i) => i % 2 == 0).forEach(p => el('text', { x: x(p.t), y: H - 6, 'text-anchor': 'middle', class: 'mute' }, s, Math.round(p.t / 60) + 'm'));
  legend(c, [['var(--accent)', 'your duo'], ['var(--even)', 'typical duo (mean, band = 1 sd)']]);
}

/* ---- map: the Deadlock minimap, with game coordinates mapped as left=(x+R)/2R, top=(R-y)/2R (R=10752).
   Verified against spawns (team 0 at the bottom base, team 1 at the top) and lane positions (lane 1 left, 4 centre, 6 right). */
const MAP_R = 10752, MAP_REMOTE = 'https://assets-bucket.deadlock-api.com/assets-api-res/images/maps/minimap_midtown_mid.png';
const mapX = (x, S) => (x + MAP_R) / (2 * MAP_R) * S, mapY = (y, S) => (MAP_R - y) / (2 * MAP_R) * S;
function mapSvg(container, S, labels) {
  const s = svg(container, S, S);
  const id = 'mf' + Math.random().toString(36).slice(2, 7), defs = el('defs', {}, s);
  const f = el('filter', { id, 'color-interpolation-filters': 'sRGB', x: 0, y: 0, width: 1, height: 1 }, defs);
  el('feColorMatrix', { type: 'matrix', values: '0 0 0 0 0.42  0 0 0 0 0.45  0 0 0 0 0.56  -0.95 0 0 0 0.95' }, f);
  el('rect', { x: 0, y: 0, width: S, height: S, fill: '#0b0b11', stroke: 'var(--line)' }, s);
  const im = el('image', { href: (window.ASSET_BASE || '') + 'assets/map.png', x: 0, y: 0, width: S, height: S, filter: `url(#${id})` }, s);
  im.addEventListener('error', () => im.setAttribute('href', MAP_REMOTE), { once: true });
  const lab = (t, x, y, anchor) => el('text', { x: x * S, y: y * S, 'text-anchor': anchor || 'middle', class: 'mute', style: 'font-size:10px;letter-spacing:.15em;opacity:.8' }, s, t);
  lab('YORK', 0.17, 0.52); lab('BROADWAY', 0.5, 0.52); lab('GREENWICH', 0.85, 0.52);
  lab(labels[0], 0.56, 0.03); lab(labels[1], 0.44, 0.995);
  return s;
}
function deathMap(c, M) {
  const S = 520, s = mapSvg(c, S, M.team === 1 ? ['YOUR BASE', 'ENEMY BASE'] : ['ENEMY BASE', 'YOUR BASE']);
  M.deaths.forEach((d, i) => {
    const cx = mapX(d.x, S), cy = mapY(d.y, S);
    const n = el('circle', { cx, cy, r: 10, fill: d.side === 'enemy' ? 'var(--loss)' : 'var(--brand)', 'fill-opacity': .92, stroke: d.caught ? '#fff' : 'rgba(0,0,0,.5)', 'stroke-width': d.caught ? 2 : 1 }, s);
    tip(n, `#${i + 1} ${mm(d.t)} - killed by ${d.killer} (${d.side === 'enemy' ? 'enemy' : 'your'} half${d.caught ? ', alone/outnumbered' : ''})`);
    el('text', { x: cx, y: cy + 4, 'text-anchor': 'middle', style: 'fill:#000;font-weight:700;font-size:11px;pointer-events:none' }, s, i + 1);
  });
  legend(c, [['var(--loss)', 'died in enemy territory'], ['var(--brand)', 'died on your half'], ['#fff', 'white ring = alone / outnumbered']]);
}
function seasonMap(c, deaths) {
  const S = 560, s = mapSvg(c, S, ['TEAM 1 BASE (top)', 'TEAM 0 BASE (bottom)']);
  for (const d of deaths) {
    const n = el('circle', { cx: mapX(d.x, S), cy: mapY(d.y, S), r: 8, fill: d.side === 'enemy' ? 'var(--loss)' : 'var(--brand)', 'fill-opacity': .42, stroke: 'none' }, s);
    tip(n, `${d.game} ${mm(d.t)} - ${d.killer}${d.side === 'enemy' ? ' (enemy half)' : ' (your half)'}`);
  }
  legend(c, [['var(--loss)', 'died in enemy territory'], ['var(--brand)', 'died on your half'], ['var(--even)', 'brighter = more deaths in the same spot']]);
}

function dmgBars(c, M) {
  const W = 540, rowH = 26, m = { l: 90, r: 70, t: 22, b: 6 }, rows = M.dmg, H = m.t + rows.length * rowH + m.b, s = svg(c, W, H);
  const mx = Math.max(...rows.map(d => d.bullet + d.ability + d.melee), 1), x = sc(0, mx, m.l, W - m.r);
  el('text', { x: 4, y: 13 }, s, 'Damage you took, by enemy and type').style.fontWeight = 600;
  rows.forEach((d, i) => {
    const y0 = m.t + i * rowH, tot = d.bullet + d.ability + d.melee || 1;
    el('text', { x: m.l - 6, y: y0 + 16, 'text-anchor': 'end' }, s, d.hero);
    let cx = m.l;
    for (const [v, col, n] of [[d.bullet, 'var(--bullet)', 'bullet'], [d.ability, 'var(--ability)', 'ability / other'], [d.melee, 'var(--melee)', 'melee']]) {
      const w = x(v) - x(0); const r = el('rect', { x: cx, y: y0 + 4, width: Math.max(0, w), height: 16, fill: col }, s); tip(r, `${d.hero} ${n}: ${num(v)} (${pct(v / tot)})`); cx += w;
    }
    el('text', { x: cx + 6, y: y0 + 16, class: 'mute' }, s, num(tot));
  });
  legend(c, [['var(--bullet)', 'bullet'], ['var(--ability)', 'ability / other'], ['var(--melee)', 'melee']]);
}

function dmgOverTime(c, M) {
  const W = 540, H = 240, m = { l: 48, r: 44, t: 24, b: 22 }, s = svg(c, W, H), I = M.dmg_intervals;
  el('text', { x: m.l, y: 14 }, s, 'Damage taken per interval and the resist you owned').style.fontWeight = 600;
  if (!I.length) return;
  const mx = Math.max(...I.map(i => i.total)), x = sc(0, M.dur, m.l, W - m.r), y = sc(0, mx, H - m.b, m.t);
  const maxR = Math.max(35, ...I.map(i => Math.max(i.res_b, i.res_s))), yr = sc(0, maxR, H - m.b, m.t);
  let prev = 0;
  for (const i of I) {
    const x0 = x(prev), w = x(i.t) - x0 - 1; prev = i.t;
    const hb = y(0) - y(i.bullet), ho = y(0) - y(i.other);
    const a = el('rect', { x: x0, y: y(i.other) - hb, width: w, height: hb, fill: 'var(--bullet)' }, s); tip(a, `${mm(i.t)}: bullet ${num(i.bullet)}`);
    const b = el('rect', { x: x0, y: y(i.other), width: w, height: ho, fill: 'var(--ability)' }, s); tip(b, `${mm(i.t)}: ability/other ${num(i.other)}`);
  }
  const step = (key, col, name) => {
    const pts = []; let last = 0; pts.push(`${x(0)},${yr(0)}`);
    for (const i of I) { pts.push(`${x(i.t)},${yr(last)}`); pts.push(`${x(i.t)},${yr(i[key])}`); last = i[key]; }
    el('polyline', { points: pts.join(' '), fill: 'none', stroke: col, 'stroke-width': 2.4 }, s).appendChild(document.createElementNS(NS, 'title')).textContent = name;
  };
  step('res_s', 'var(--ink)', 'Spirit resist owned (%)'); step('res_b', 'var(--loss)', 'Bullet resist owned (%)');
  for (let t = 0; t <= M.dur; t += 600) el('text', { x: x(t), y: H - 6, 'text-anchor': 'middle', class: 'mute' }, s, Math.round(t / 60) + 'm');
  el('text', { x: W - m.r + 4, y: yr(maxR) + 4, class: 'mute' }, s, maxR + '%'); el('text', { x: m.l - 6, y: y(mx) + 4, 'text-anchor': 'end', class: 'mute' }, s, k(mx));
  legend(c, [['var(--bullet)', 'bullet damage'], ['var(--ability)', 'ability / other damage'], ['var(--ink)', 'spirit resist owned % (right axis)'], ['var(--loss)', 'bullet resist owned % (right axis)']]);
}

function itemLanes(c, M) {
  const names = ['You', ...Object.keys(M.enemy_t3)];
  const W = 1100, rowH = 26, m = { l: 90, r: 10, t: 22, b: 22 }, H = m.t + names.length * rowH + m.b, s = svg(c, W, H, 'wide'), x = sc(0, M.dur, m.l, W - m.r);
  for (let t = 0; t <= M.dur; t += 300) { el('line', { x1: x(t), x2: x(t), y1: m.t, y2: H - m.b, class: 'axis' }, s); el('text', { x: x(t), y: H - 6, 'text-anchor': 'middle', class: 'mute' }, s, Math.round(t / 60) + 'm'); }
  el('text', { x: 4, y: 13 }, s, 'Tier-3+ item purchases (hover for names). Purple = a resist item.').style.fontWeight = 600;
  names.forEach((n, i) => {
    const y0 = m.t + i * rowH; el('text', { x: m.l - 6, y: y0 + 16, 'text-anchor': 'end' }, s, n).style.fontWeight = i ? 400 : 700;
    const its = i ? M.enemy_t3[n] : M.items.filter(q => q.tier >= 3 && q.slot !== 'ability' && !q.sold).map(q => ({ t: q.t, name: q.name, tags: q.tags }));
    for (const q of its) {
      const res = (q.tags || []).some(t => /^(spirit|bullet)_resist=/.test(t));
      const d = el('rect', { x: x(q.t) - 4, y: y0 + 5, width: 9, height: 14, rx: 2, fill: res ? 'var(--ability)' : (i ? 'var(--even)' : 'var(--accent)') }, s); tip(d, `${mm(q.t)} ${q.name}${(q.tags || []).length ? ' [' + q.tags.join(', ') + ']' : ''}`);
    }
  });
}

function soulsBars(c, M) {
  const order = ['Neutrals', 'LaneCreeps', 'Players', 'Assists', 'Bosses', 'Treasure', 'Breakable', 'TeamBonus'];
  const W = 540, rowH = 40, m = { l: 90, r: 50, t: 22, b: 6 }, H = m.t + order.length * rowH + m.b, s = svg(c, W, H);
  const mx = Math.max(...order.flatMap(o => [M.souls[o] || 0, M.souls_team_avg[o] || 0, M.souls_lane_opp_avg[o] || 0]), 1), x = sc(0, mx, m.l, W - m.r);
  el('text', { x: 4, y: 13 }, s, 'Souls by source: you vs teammates vs lane opponents').style.fontWeight = 600;
  order.forEach((o, i) => {
    const y0 = m.t + i * rowH; el('text', { x: m.l - 6, y: y0 + 22, 'text-anchor': 'end' }, s, o);
    [[M.souls[o] || 0, 'var(--accent)', 'you'], [M.souls_team_avg[o] || 0, 'var(--even)', 'teammate avg'], [M.souls_lane_opp_avg[o] || 0, 'var(--loss)', 'lane opponent avg']].forEach(([v, col, n], j) => {
      const r = el('rect', { x: m.l, y: y0 + 3 + j * 11, width: Math.max(1, x(v) - x(0)), height: 9, fill: col }, s); tip(r, `${o} - ${n}: ${num(v)}`);
      if (j == 0) el('text', { x: x(v) + 5, y: y0 + 12, class: 'mute' }, s, num(v));
    });
  });
  legend(c, [['var(--accent)', 'you'], ['var(--even)', 'teammate average'], ['var(--loss)', 'lane opponent average']]);
}

function tbl(container, cols, rows, opts) {
  const t = h('table', {}, '', container);
  t.innerHTML = '<tr>' + cols.map(c => `<th class="${c.l ? 'l' : ''}">${c.h}</th>`).join('') + '</tr>' +
    rows.map(r => `<tr class="${(opts && opts.rowClass ? opts.rowClass(r) : '')}">` + cols.map(c => { const v = c.f(r); const cls = c.cls ? c.cls(r) : ''; return `<td class="${c.l ? 'l ' : ''}${cls}">${v}</td>`; }).join('') + '</tr>').join('');
  return t;
}

/* ---------------------------------------------------------------- navigation + copy-for-Claude */
function copyText(text, btn) {
  const flash = (msg) => { const o = btn.dataset.label || (btn.dataset.label = btn.textContent); btn.textContent = msg; setTimeout(() => (btn.textContent = o), 1800); };
  const manual = () => {  // clipboard blocked (e.g. some embedded browsers): show the text selected so Ctrl+C works
    const box = document.createElement('div');
    box.style.cssText = 'position:fixed;inset:0;z-index:50;background:rgba(0,0,0,.7);display:flex;align-items:center;justify-content:center;padding:20px';
    box.innerHTML = '<div style="background:var(--panel);border:1px solid var(--brand);max-width:820px;width:100%;padding:14px"><div style="display:flex;justify-content:space-between;margin-bottom:8px"><b style="font:700 12px var(--display);letter-spacing:.12em;text-transform:uppercase;color:var(--brand)">Press Ctrl+C to copy, then paste into Claude</b><button style="background:var(--panel2);color:var(--ink);border:1px solid var(--line);cursor:pointer">Close</button></div><textarea style="width:100%;height:55vh;background:var(--bg);color:var(--ink);border:1px solid var(--line);font:12px var(--mono)"></textarea></div>';
    const ta = box.querySelector('textarea'); ta.value = text; box.querySelector('button').onclick = () => box.remove(); box.onclick = (e) => { if (e.target === box) box.remove(); };
    document.body.appendChild(box); ta.focus(); ta.select();
  };
  const fallback = () => { const t = document.createElement('textarea'); t.value = text; t.style.cssText = 'position:fixed;left:0;top:0;width:1px;height:1px;opacity:0'; document.body.appendChild(t); t.select(); let ok = false; try { ok = document.execCommand('copy'); } catch (e) { } t.remove(); if (ok) flash('Copied!'); else manual(); };
  if (navigator.clipboard && window.isSecureContext) navigator.clipboard.writeText(text).then(() => flash('Copied!'), fallback); else fallback();
}
function renderNav(o) {
  const pre = o.page === 'match' ? '' : 'matches/', home = (o.page === 'match' ? '../' : '') + 'index.html';
  const idx = o.games.findIndex(g => g.id === o.current), prev = o.games[idx - 1], next = o.games[idx + 1];
  const opts = o.games.slice().reverse().map(g => `<option value="${g.id}" ${g.id === o.current ? 'selected' : ''}>${g.win ? 'W' : 'L'} · ${g.hero} · ${g.label}</option>`).join('');
  const latest = o.games[o.games.length - 1];
  const nav = $('nav');
  nav.innerHTML = `<div class="row"><span class="brand">Deadlock <b>// Analyst</b></span>
   <div class="links"><a class="nl ${o.page === 'overview' ? 'on' : ''}" href="${home}">Overview</a><a class="nl ${o.current === (latest || {}).id ? 'on' : ''}" href="${pre}${latest ? latest.id : ''}.html">Latest match</a></div>
   <span class="sp"></span>
   ${o.page === 'match' ? `<div class="pn">${prev ? `<a href="${prev.id}.html" title="Previous game">&lsaquo; prev</a>` : ''}${next ? `<a href="${next.id}.html" title="Next game">next &rsaquo;</a>` : ''}</div>` : ''}
   <select id="gamesel" title="Jump to a game"><option value="">Games&hellip;</option>${opts}</select>
   <button class="cp" id="cpbtn" title="Copy a summary to paste into Claude">Copy for Claude</button></div>
   ${o.chips && o.chips.length ? `<div class="chips">${o.chips.map(([id, t]) => `<a href="#${id}">${t}</a>`).join('')}</div>` : ''}`;
  $('gamesel').onchange = (e) => { if (e.target.value) location.href = pre + e.target.value + '.html'; };
  $('cpbtn').onclick = (e) => copyText(o.brief, e.target);
}

/* ---------------------------------------------------------------- per-match page */
function renderMatch(M, P, F) {
  const date = new Date(M.start * 1000).toISOString().slice(0, 16).replace('T', ' ') + ' UTC';
  $('head').innerHTML = `<div class="nav"><a href="../index.html">&larr; Overview</a></div>
   <h1>${M.hero} <span class="pill ${M.win ? 'win' : 'loss'}">${M.win ? 'WIN' : 'LOSS'}</span> <span style="font-weight:400;color:var(--mute);font-size:15px">match ${M.id}${M.calib ? ' &middot; calibration game ' + M.calib : ''}</span></h1>
   <div class="sub">${date} &middot; ${mm(M.dur)} &middot; ${M.lane} lane with ${M.lane_mate.join(', ') || 'nobody'} vs ${M.lane_opp.join(' + ')}</div>
   <div class="kv"><div>KDA<b>${M.kda.join(' / ')}</b></div><div>Net worth<b>${num(M.nw)}</b></div><div>Souls / min<b>${num(M.kpi.spm)}</b></div><div>Last hits<b>${M.lh}</b></div>
   <div>Deaths vs teammates<b>${M.kpi.deaths} vs ${M.kpi.mate_deaths.toFixed(1)}</b></div><div>Time dead<b>${pct(M.kpi.dead_pct)} <span style="font-weight:400;color:var(--mute)">(mates ${pct(M.kpi.mate_dead_pct)})</span></b></div>
   <div>Mid boss<b>${M.kpi.midboss_mine}/${M.kpi.midboss_total} yours</b></div>${M.sl ? `<div>Statlocker<b>${M.sl.mvp}/12 &middot; ${M.sl.grade}${M.sl.mmr != null ? ' &middot; ' + (M.sl.mmr > 0 ? '+' : '') + M.sl.mmr + ' MMR' : ''}</b></div>` : ''}</div>`;

  // key points
  const kp = $('points');
  const bad = P.problems.map(p => `<div class="pt bad"><b>${p.title}${p.recurring ? ' <span class="pill warn">recurring</span>' : ''}</b><span class="e">${p.evidence}</span></div>`).join('') || '<div class="pt good"><b>No major habit problems this game.</b></div>';
  const good = P.positives.map(p => `<div class="pt good"><b>${p.title}</b><span class="e">${p.evidence}</span></div>`).join('') || '<span class="e">Nothing clearly above average this game.</span>';
  const nxt = P.next.map(n => `<div class="pt next"><b>${n.text}${n.recurring ? ' <span class="pill warn">recurring focus</span>' : ''}</b></div>`).join('') || '<span class="e">Keep doing what you did.</span>';
  kp.innerHTML = `<div class="cols"><div class="card"><h3>Work on</h3>${bad}</div><div class="card"><h3>What went well</h3>${good}</div><div class="card"><h3>Try next game</h3>${nxt}
   <div class="sub" style="margin-top:8px">Your current focus areas: ${F.length ? F.map(f => `<span class="pill info">${f.title}</span>`).join(' ') : 'none yet'}</div></div></div>`;

  timeline($('c-timeline'), M);
  laneNW($('c-lane1'), M); laneDuo($('c-lane2'), M);
  dmgBars($('c-dmg1'), M); dmgOverTime($('c-dmg2'), M);
  itemLanes($('c-items'), M);
  soulsBars($('c-souls'), M); deathMap($('c-map'), M);

  tbl($('t-deaths'), [
    { h: '#', f: (d, i) => '', l: 1 }, { h: 'Time', f: d => mm(d.t), l: 1 }, { h: 'Killed by', f: d => d.killer + (d.killer_lane ? ' (lane)' : ''), l: 1 },
    { h: 'Your NW vs killer', f: d => d.nw_killer == null ? '-' : sgn((d.nw_me - d.nw_killer) / 1000) + 'k' },
    { h: 'Allies / enemies near', f: d => d.allies + ' / ' + d.enemies, cls: d => d.caught ? 'c-bad' : '' },
    { h: 'HP% 20/10/5/2s before', f: d => d.hp.join(' / ') }, { h: 'Respawn', f: d => d.respawn + 's' }, { h: 'Early', f: d => d.early ? 'yes' : '' }]
    .map((c, j) => j == 0 ? { h: '#', f: d => M.deaths.indexOf(d) + 1, l: 1 } : c), M.deaths);
  tbl($('t-fights'), [{ h: 'Time', f: f => mm(f.t0) + '-' + mm(f.t1), l: 1 }, { h: 'Result', f: f => f.res.toUpperCase(), cls: f => f.res == 'won' ? 'c-good' : (f.res == 'lost' ? 'c-bad' : '') },
    { h: 'Deaths (enemy / ally)', f: f => f.theirs + ' / ' + f.ours }, { h: 'First death', f: f => f.first + (f.first_us ? ' (ally)' : ' (enemy)'), l: 1 }, { h: 'You', f: f => f.pres + (f.kill ? ' + kill' : ''), l: 1 }], M.fights);
  tbl($('t-board'), [{ h: 'Hero', f: p => p.hero + (p.me ? ' (you)' : ''), l: 1 }, { h: 'Team', f: p => p.ally ? 'ally' : 'enemy', l: 1 }, { h: 'Lane', f: p => p.lane, l: 1 }, { h: 'K/D/A', f: p => p.k + '/' + p.d + '/' + p.a },
    { h: 'Net worth', f: p => num(p.nw) }, { h: 'Last hits', f: p => p.lh }, { h: 'Hero dmg', f: p => num(p.dmg) }, { h: 'Dmg taken', f: p => num(p.taken) }, { h: 'Healing', f: p => num(p.heal) }, { h: 'Lvl', f: p => p.lvl }], M.board, { rowClass: p => p.me ? 'me' : '' });
  tbl($('t-items'), [{ h: 'Time', f: i => mm(i.t), l: 1 }, { h: 'Item', f: i => i.name, l: 1 }, { h: 'Tier / slot', f: i => i.slot == 'ability' ? 'ability' : 'T' + i.tier + ' ' + i.slot, l: 1 }, { h: 'Sold', f: i => i.sold ? mm(i.sold) : '' }, { h: 'Notes', f: i => i.tags.join(', '), l: 1 }], M.items.filter(i => i.slot !== 'ability'));
  tbl($('t-obj'), [{ h: 'Time', f: o => mm(o.t), l: 1 }, { h: 'Objective', f: o => o.name, l: 1 }, { h: 'Result', f: o => o.mine ? 'destroyed by your team' : 'lost', l: 1 }], M.objectives);
  const b = M.bench;
  $('bench').innerHTML = b.hero_games ? `<div class="kv"><div>All-rank ${M.hero} games<b>${num(b.hero_games)}</b></div><div>Win rate<b>${pct(b.hero_winrate)}</b></div><div>Avg deaths / game<b>${b.hero_deaths.toFixed(1)}</b></div><div>Avg net worth<b>${num(b.hero_nw)}</b></div><div>Avg accuracy<b>${pct(b.hero_acc)}</b> <span class="e">(you ${pct(M.kpi.acc)})</span></div>
   ${Object.keys(M.nw_z).map(p => `<div>Net worth @${p}% of game<b>${sgn(M.nw_z[p].z)} sd</b></div>`).join('')}</div>` : '<span class="sub">No benchmark data cached.</span>';
}

/* ---------------------------------------------------------------- Statlocker community panel */
// Percentile bars: every bar is "better than X% of the community" (50 = average). Strengths on the left card, weaknesses on the right.
function pctBars(container, rows, good) {
  const W = 540, rowH = 34, m = { l: 8, r: 8, t: 6, b: 6 }, H = m.t + rows.length * rowH + m.b, s = svg(container, W, H);
  const x = sc(0, 100, m.l, W - m.r);
  el('line', { x1: x(50), x2: x(50), y1: m.t, y2: H - m.b, class: 'axis' }, s);
  rows.forEach((r, i) => {
    const y0 = m.t + i * rowH;
    el('text', { x: m.l + 2, y: y0 + 11 }, s, r.name + '  ' + r.value).style.fontWeight = 600;
    const bar = el('rect', { x: m.l, y: y0 + 16, width: Math.max(2, x(r.pct) - x(0)), height: 10, fill: good ? 'var(--win)' : 'var(--loss)', opacity: .85 }, s);
    tip(bar, `${r.name}: ${r.value} - better than ${Math.round(r.pct)}% of the community`);
    el('text', { x: Math.min(W - 40, x(r.pct) + 6), y: y0 + 25, class: 'mute' }, s, (r.pct >= 50 ? 'top ' + Math.max(1, Math.round(100 - r.pct)) + '%' : 'bottom ' + Math.max(1, Math.round(r.pct)) + '%'));
  });
}
function communityPanel(c, C) {
  const hint = (r) => r.hint ? `<div class="pt ${r.pct >= 50 ? 'good' : 'bad'}"><b>${r.name}</b><span class="e">${r.hint}</span></div>` : '';
  c.innerHTML = `<div class="sub">Statlocker snapshot from ${C.captured}: ${C.rank.in_game}; Statlocker rates you ${C.rank.statlocker} (${C.rank.pp} PP).
    Laning at 9:00: ${C.laning.wins} wins / ${C.laning.draws} draws / ${C.laning.losses} losses over ${C.laning.lanes} lanes.</div>
    <div class="cols"><div class="card"><h3>Strengths vs the community</h3><div id="cm-good"></div></div><div class="card"><h3>Weaknesses vs the community</h3><div id="cm-bad"></div></div></div>
    <div class="card" style="margin-top:12px"><h3>What these suggest</h3>${C.strengths.map(hint).join('')}${C.weaknesses.map(hint).join('')}
    <div class="sub" style="margin:8px 0 0">${C.meta.sample}. ${C.meta.caveat}</div></div>`;
  pctBars($('cm-good'), C.strengths, true); pctBars($('cm-bad'), C.weaknesses, false);
}

/* ---------------------------------------------------------------- overview */
function spark(container, vals, opts) {
  const W = opts.w || 180, H = opts.h || 44, m = 4, s = svg(container, W, H);
  const v = vals.filter(x => x != null); if (v.length < 2) return;
  let lo = Math.min(...v, opts.thresh == null ? Infinity : opts.thresh), hi = Math.max(...v, opts.thresh == null ? -Infinity : opts.thresh);
  if (lo === hi) { lo -= 1; hi += 1; }
  const x = sc(0, vals.length - 1, m, W - m), y = sc(lo, hi, H - m, m);
  if (opts.thresh != null) el('line', { x1: m, x2: W - m, y1: y(opts.thresh), y2: y(opts.thresh), stroke: 'var(--warn)', 'stroke-dasharray': '3 3', 'stroke-width': 1 }, s);
  const pts = vals.map((q, i) => q == null ? null : [x(i), y(q)]).filter(Boolean);
  el('polyline', { points: pts.map(p => p.join(',')).join(' '), fill: 'none', stroke: 'var(--accent)', 'stroke-width': 1.8 }, s);
  vals.forEach((q, i) => { if (q == null) return; const bad = opts.bad && opts.bad(q); const c = el('circle', { cx: x(i), cy: y(q), r: 3.2, fill: bad ? 'var(--loss)' : 'var(--accent)' }, s); tip(c, (opts.labels ? opts.labels[i] + ': ' : '') + (+q).toFixed(2)); });
}

function renderOverview(O) {
  const G = O.games, T = O.ov.trends, F = O.ov.focus;
  O.thresholds = {}; O.flagfn = {};
  for (const id in O.rules) { const r = O.rules[id]; O.thresholds[id] = r.v; O.flagfn[id] = r.op === '>=' ? (v => v >= r.v) : (v => v <= r.v); }
  const w = O.ov.outcome;
  $('head').innerHTML = `<h1>Deadlock: ranked season overview</h1><div class="sub">${G.length} ranked games this season (${w.wins} win${w.wins == 1 ? '' : 's'}). Built ${O.built}. Pick one or two focus areas, play, then re-run <code>python analyze.py overview</code> to see if the numbers move.</div>`;

  // focus
  $('focus').innerHTML = F.slice(0, 3).map((f, i) => `<div class="card"><h3>${i + 1}. ${f.title}</h3>
    <div class="sub" style="margin:0 0 6px"><span class="pill warn">flagged in ${f.flagged} of your last ${f.of} games</span></div>
    <div id="fs-${f.id}"></div>
    <div class="sub" style="margin:4px 0">Target: ${f.target}</div>
    ${f.advice.slice(0, 2).map(a => `<div class="pt next"><b style="font-weight:500">${a}</b></div>`).join('')}
    <div class="sub">Examples: ${f.examples.map(e => `<a href="matches/${e.id}.html">${e.id}</a>`).join(', ')}</div></div>`).join('') || '<div class="card">No recurring problems flagged yet.</div>';
  F.slice(0, 3).forEach(f => { const t = T.find(x => x.id == f.id); spark($('fs-' + f.id), t.series, { w: 330, h: 54, labels: G.map(g => '#' + g.id), thresh: O.thresholds[f.id], bad: v => O.flagfn[f.id](v) }); });

  // trends
  const rows = T.map(t => ({ ...t, ico: t.verdict == 'improving' ? '▲' : t.verdict == 'getting worse' ? '▼' : '•' }));
  const fmt = (t, v) => v == null ? '-' : (t.id == 't3' ? Math.round(v) + 's' : t.id == 'resist' ? v.toFixed(1) + '%' : v.toFixed(1));
  tbl($('trend'), [{ h: 'Habit', f: t => `<b>${t.title}</b><div class="sub" style="margin:0">${t.unit} (${t.better} is better; target ${t.target})</div>`, l: 1, cls: () => 'wrap' },
    { h: 'Baseline', f: t => fmt(t, t.baseline) }, { h: 'Recent', f: t => fmt(t, t.recent) },
    { h: 'Verdict', f: t => `<span class="pill ${t.verdict == 'improving' ? 'win' : t.verdict == 'getting worse' ? 'loss' : 'mute'}">${t.ico} ${t.verdict}${t.tentative ? ' (tentative)' : ''}</span>` },
    { h: 'Game by game', f: t => `<span id="tr-${t.id}"></span>` }], rows);
  rows.forEach(t => { const e = $('tr-' + t.id); if (e) spark(e, t.series, { w: 160, h: 36, labels: G.map(g => '#' + g.id), thresh: O.thresholds[t.id], bad: v => O.flagfn[t.id](v) }); });
  const need = O.ov.need;
  $('trend-note').innerHTML = `Baseline = your first ${w.b || '?'} games, recent = your latest ${w.b || '?'}. ` + (need > 0 ? `<b>Verdicts are tentative until you have 10 season games (${need} to go)</b>; ` : '') +
    `Win rate ${w.b ? `${pct(w.baseline_wr)} &rarr; ${pct(w.recent_wr)}` : 'n/a'} is shown for context only: a handful of games is mostly noise, so judge progress by the habit numbers, not by wins.`;

  // matrix
  const HID = T.map(t => t.id);
  tbl($('matrix'), [{ h: 'Game', f: g => `<a href="matches/${g.id}.html">${g.calib ? '#' + g.calib : g.id}</a>`, l: 1 }, { h: 'Result', f: g => `<span class="pill ${g.win ? 'win' : 'loss'}">${g.win ? 'W' : 'L'}</span>` }, { h: 'Hero', f: g => g.hero, l: 1 }, { h: 'KDA', f: g => g.kda.join('/') },
    ...HID.map(id => ({ h: HABIT_SHORT[id], f: g => { const r = g.habits[id]; return r.flag ? 'flag' : (r.value == null ? 'n/a' : 'ok'); }, cls: g => { const r = g.habits[id]; return r.flag ? 'c-bad' : (r.value == null ? 'c-na' : 'c-good'); } })),
    { h: 'Flags', f: g => HID.filter(id => g.habits[id].flag).length }], G);

  // games table
  tbl($('games'), [{ h: 'Game', f: g => `<a href="matches/${g.id}.html">${g.id}</a>`, l: 1 }, { h: 'Hero', f: g => g.hero, l: 1 }, { h: 'Lane', f: g => g.lane, l: 1 }, { h: 'Result', f: g => `${g.win ? 'W' : 'L'} ${mm(g.dur)}` }, { h: 'KDA', f: g => g.kda.join('/') },
    { h: 'Deaths vs mates', f: g => g.kpi.deaths + ' vs ' + g.kpi.mate_deaths.toFixed(1) }, { h: 'Souls/min', f: g => num(g.kpi.spm) }, { h: 'Mid boss', f: g => g.kpi.midboss_mine + '/' + g.kpi.midboss_total },
    ...(O.community ? [{ h: 'Match rank', f: g => g.sl ? g.sl.mvp + '/12' : '-' }, { h: 'Grade', f: g => g.sl ? g.sl.grade : '-' }, { h: 'MMR', f: g => g.sl && g.sl.mmr != null ? (g.sl.mmr > 0 ? '+' : '') + g.sl.mmr : '-' }] : [])], G);
  if (O.community) communityPanel($('community'), O.community);

  seasonMap($('c-seasonmap'), O.deaths);
  const ed = O.deaths.filter(d => d.side === 'enemy').length;
  $('seasonmap-note').textContent = `${ed} of ${O.deaths.length} deaths (${pct(ed / Math.max(1, O.deaths.length))}) happened in enemy territory; hover a dot for the game, time and killer.`;
  // by hero
  const by = {}; G.forEach(g => { (by[g.hero] = by[g.hero] || []).push(g); });
  tbl($('heroes'), [{ h: 'Hero', f: r => r[0], l: 1 }, { h: 'Games', f: r => r[1].length }, { h: 'W-L', f: r => r[1].filter(g => g.win).length + '-' + r[1].filter(g => !g.win).length },
    { h: 'Avg KDA', f: r => ['0', '1', '2'].map(i => (r[1].reduce((a, g) => a + g.kda[+i], 0) / r[1].length).toFixed(1)).join('/') }, { h: 'Avg souls/min', f: r => num(r[1].reduce((a, g) => a + g.kpi.spm, 0) / r[1].length) }], Object.entries(by).sort((a, b) => b[1].length - a[1].length));
  // team-level
  const mb = G.filter(g => g.kpi.midboss_total);
  $('team').innerHTML = `<div class="kv"><div>Games where your team claimed every mid boss<b>${mb.filter(g => g.kpi.midboss_mine == g.kpi.midboss_total).length} of ${mb.length}</b></div>
   <div>...and won<b>${mb.filter(g => g.kpi.midboss_mine == g.kpi.midboss_total && g.win).length}</b></div>
   <div>Games where the enemy claimed every mid boss<b>${mb.filter(g => g.kpi.midboss_mine == 0).length} of ${mb.length}</b></div>
   <div>...and you won<b>${mb.filter(g => g.kpi.midboss_mine == 0 && g.win).length}</b></div></div>`;
}

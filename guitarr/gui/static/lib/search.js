// Searching names typed by people: no accents or punctuation, and typos still find what you meant.

/** Lowercase, no accents, no punctuation: "Keb' Mo'" matches "keb mo", "Andrés" matches "andres". */
export const fold = x => String(x || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();

/** Edit distance (with swapped letters as one edit), stopping early past `max`. */
export function editDistance(a, b, max) {
  if (Math.abs(a.length - b.length) > max) return max + 1;
  let prev2 = [], prev = Array.from({ length: b.length + 1 }, (_, j) => j);
  for (let i = 1; i <= a.length; i++) {
    const cur = [i];
    let best = i;
    for (let j = 1; j <= b.length; j++) {
      cur[j] = Math.min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1));
      if (i > 1 && j > 1 && a[i - 1] === b[j - 2] && a[i - 2] === b[j - 1]) cur[j] = Math.min(cur[j], prev2[j - 2] + 1);
      best = Math.min(best, cur[j]);
    }
    if (best > max) return max + 1;
    prev2 = prev; prev = cur;
  }
  return prev[b.length];
}

/** How a folded word sounds, for names typed by ear (in English or Spanish): no h, no doubled letters, and letters
 * that sound alike made one. "ghalager" and "gallagher" both become "galager"; "jendrix", "yimi" find Hendrix, Jimi. */
export const soundKey = w => w.replace(/ph/g, "f").replace(/[jh]/g, "").replace(/[kq]/g, "c").replace(/v/g, "b")
  .replace(/z/g, "s").replace(/y/g, "i").replace(/w/g, "u").replace(/(.)\1+/g, "$1");

/** A typo still finds it: "henrix" → Hendrix, "ricotta" → Ricota, "stever" → Stevie, "ghalager" → Gallagher.
 * Words of 3 letters or fewer must be exact or sound the same; `text` is already folded. A word may also be the
 * start of a longer one ("henri" → hendrix). */
export function closeTo(word, text) {
  if (word.length >= 4 && text.replace(/ /g, "").includes(word)) return true;     // "pinkfloyd", "acdc"
  const toks = text.split(" ").filter(tok => tok.length >= 3);
  const ws = soundKey(word);
  if (ws.length >= 3 && toks.some(tok => {                                         // sounds like it
    const ts = soundKey(tok);
    return ts.startsWith(ws) || (ws.length >= 4 && editDistance(ws, ts.slice(0, ws.length + 1), 1) <= 1);
  })) return true;
  const max = word.length >= 5 ? 2 : word.length === 4 ? 1 : 0;
  if (!max) return false;
  return toks.some(tok => editDistance(word, tok, max) <= max
    || (tok.length > word.length && editDistance(word, tok.slice(0, word.length), 1) <= 1));
}

/** For a search that found nothing: the indexes of the `names` (folded) closest to what was typed, best first. */
export function suggest(query, names, n = 3) {
  const words = fold(query).split(" ").filter(Boolean).map(soundKey);
  if (!words.length) return [];
  const dist = name => {
    const toks = name.split(" ").filter(Boolean).map(soundKey);
    return words.reduce((sum, w) => sum + Math.min(...toks.map(t => editDistance(w, t.slice(0, Math.max(w.length, 3)), 9))), 0)
      / words.reduce((s, w) => s + w.length, 0);
  };
  return names.map((name, i) => [dist(name), i]).filter(([d]) => d <= 0.5).sort((a, b) => a[0] - b[0]).slice(0, n).map(([, i]) => i);
}

/** A word of `text` (folded) starts with `w`: "j" finds "John", not "Django". */
export const startsWord = (text, w) => ` ${text}`.includes(` ${w}`);

/** Matches a query against folded texts: every word must start a word of the text. As typed first; only when
 * that finds nothing at all do close spellings count (so an exact match never brings look-alikes). */
export function matcher(query, texts) {
  const words = fold(query).split(" ").filter(Boolean);
  const exact = q => words.every(w => startsWord(q, w));
  const loose = words.length > 0 && !texts.some(exact);
  return { words, loose, test: q => words.every(w => startsWord(q, w) || (loose && closeTo(w, q))) };
}

/** How well a result fits (lower is better). `fields` are folded texts, most important first (name, player,
 * bands, the rest): each word scores the first field where it starts a word, and a field that starts with the
 * whole query ("jo" → "Joe Perry") comes before one that only contains it ("Billy Joe"). */
export function rank(words, fields) {
  if (!words.length) return 0;
  const q = words.join(" ");
  const lead = fields.findIndex(f => f.startsWith(q));
  let score = lead < 0 ? fields.length : lead;
  for (const w of words) {
    const i = fields.findIndex(f => startsWord(f, w));
    score += i < 0 ? fields.length + 1 : i;
  }
  return score;
}

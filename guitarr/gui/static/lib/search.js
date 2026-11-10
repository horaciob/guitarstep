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

/** A typo still finds it: "henrix" → Hendrix, "ricotta" → Ricota, "stever" → Stevie. Words of 3 letters or
 * fewer must be exact; `text` is already folded. A word may also be the start of a longer one ("henri" → hendrix). */
export function closeTo(word, text) {
  if (word.length >= 4 && text.replace(/ /g, "").includes(word)) return true;     // "pinkfloyd", "acdc"
  const max = word.length >= 5 ? 2 : word.length === 4 ? 1 : 0;
  if (!max) return false;
  return text.split(" ").some(tok => tok.length >= 3 && (editDistance(word, tok, max) <= max
    || (tok.length > word.length && editDistance(word, tok.slice(0, word.length), 1) <= 1)));
}

/** Matches a query against folded texts: every word must be found. As typed first; only when that finds
 * nothing at all do close spellings count (so an exact match never brings look-alikes). */
export function matcher(query, texts) {
  const words = fold(query).split(" ").filter(Boolean);
  const exact = q => words.every(w => q.includes(w));
  const loose = words.length > 0 && !texts.some(exact);
  return { words, loose, test: q => words.every(w => q.includes(w) || (loose && closeTo(w, q))) };
}

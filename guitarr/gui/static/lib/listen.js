// "Listen to me": asks the backend to listen to the guitar for a task (chord, exercise,
// chord-change minute…) and reports the state until the report with the earned XP arrives.
import { api, progressChanged } from "./ui.js";
import { startLive } from "./browser-input.js";

export function listen(payload, { onState, onMessage, timeoutS = 0 } = {}) {
  let stopped = false, lastMsg = "", timer = null;
  const stop = async () => {
    if (stopped) return;
    stopped = true;
    try { await api("/api/live/stop", { method: "POST" }); } catch { /* already finished */ }
  };
  const done = (async () => {
    await startLive(payload);
    if (timeoutS) timer = setTimeout(stop, timeoutS * 1000);
    for (;;) {
      await new Promise(r => setTimeout(r, 120));
      let st;
      try { st = await api("/api/live/state"); } catch { continue; }
      if (st.state) {
        onState && onState(st.state);
        const key = st.state.last && JSON.stringify(st.state.last);
        if (key && key !== lastMsg) {
          lastMsg = key;
          onMessage && onMessage(st.state.last);
        }
        if (st.state.error) throw new Error(st.state.error);
      }
      if (st.report) {
        clearTimeout(timer);
        progressChanged();
        return st.report;
      }
    }
  })();
  return { done, stop };
}

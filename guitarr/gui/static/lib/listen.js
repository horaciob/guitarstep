// "Escuchame": le pide al backend que oiga la guitarra para una tarea (acorde, ejercicio,
// minuto de cambio…) y va avisando el estado hasta que llega el reporte con lo ganado.
import { api, progressChanged } from "./ui.js";

export function listen(payload, { onState, onMessage, timeoutS = 0 } = {}) {
  let stopped = false, lastMsg = "", timer = null;
  const stop = async () => {
    if (stopped) return;
    stopped = true;
    try { await api("/api/live/stop", { method: "POST" }); } catch { /* ya terminó */ }
  };
  const done = (async () => {
    await api("/api/live/start", { json: payload });
    if (timeoutS) timer = setTimeout(stop, timeoutS * 1000);
    for (;;) {
      await new Promise(r => setTimeout(r, 120));
      let st;
      try { st = await api("/api/live/state"); } catch { continue; }
      if (st.state) {
        onState && onState(st.state);
        if (st.state.last && st.state.last !== lastMsg) {
          lastMsg = st.state.last;
          onMessage && onMessage(lastMsg);
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

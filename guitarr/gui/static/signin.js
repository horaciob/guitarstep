// Web service sign-in: asks for a one-time link by email (the server log has it in local Docker).
import { applyDom, initI18n, t } from "./lib/i18n.js";

await initI18n();
applyDom();
const $ = s => document.querySelector(s);
$("#signinExpired").hidden = new URLSearchParams(location.search).get("signin") !== "expired";
$("#signinForm").onsubmit = async ev => {
  ev.preventDefault();
  const err = $("#signinErr"), email = $("#signinEmail").value.trim();
  err.hidden = true;
  if (!email) { err.textContent = t("errors.bad_email"); err.hidden = false; return; }
  let r;
  try {
    r = await fetch("/api/auth/link", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email }) });
  } catch { err.textContent = t("errors.generic"); err.hidden = false; return; }
  if (!r.ok) {
    const d = ((await r.json().catch(() => null)) || {}).detail || {};
    err.textContent = t(`errors.${d.code}`, { defaultValue: d.message || t("errors.generic") });
    err.hidden = false;
    return;
  }
  $("#signinSent").textContent = t("signin.sent", { email });
  $("#signinSent").hidden = false;
};

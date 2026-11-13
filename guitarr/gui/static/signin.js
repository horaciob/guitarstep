// Web service sign-in: asks for a one-time link by email (the server log has it in local Docker).
// Opening the link (/auth/verify?token=…) shows whose account it is; its button signs in.
import { applyDom, initI18n, t } from "./lib/i18n.js";

await initI18n();
applyDom();
const $ = s => document.querySelector(s);
const post = (url, body) => fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
const errorText = async r => {
  const d = ((await r.json().catch(() => null)) || {}).detail || {};
  return t(`errors.${d.code}`, { defaultValue: d.message || t("errors.generic") });
};
const token = location.pathname === "/auth/verify" && new URLSearchParams(location.search).get("token");
// where to go once signed in (an invitation link opened before signing in: #/class?join=…)
const AFTER = "guitarr.afterSignin";
try { if (!token && location.hash.length > 2) localStorage.setItem(AFTER, location.hash); } catch { /* private mode */ }
const afterSignin = () => {
  let h = "";
  try { h = localStorage.getItem(AFTER) || ""; localStorage.removeItem(AFTER); } catch { /* private mode */ }
  return "/" + (h.startsWith("#/") ? h : "");
};

if (token) {
  $("#signinForm").hidden = true;
  let r = null;
  try { r = await fetch(`/api/auth/link?token=${encodeURIComponent(token)}`); } catch { /* shown below */ }
  if (r && r.ok) {
    const link = await r.json();
    $("#confirmAs").textContent = t("signin.as", { email: link.email });
    $("#confirmElsewhere").hidden = link.same_browser;
    $("#confirmForm").hidden = false;
    $("#confirmForm").querySelector("button").focus();
  } else {
    $("#signinExpired").hidden = false;
    $("#signinForm").hidden = false;
  }
}

$("#confirmForm").onsubmit = async ev => {
  ev.preventDefault();
  const err = $("#confirmErr");
  err.hidden = true;
  let r;
  try { r = await post("/api/auth/verify", { token }); } catch { err.textContent = t("errors.generic"); err.hidden = false; return; }
  if (r.ok) { location.replace(afterSignin()); return; }
  err.textContent = await errorText(r);
  err.hidden = false;
};

$("#signinForm").onsubmit = async ev => {
  ev.preventDefault();
  const err = $("#signinErr"), email = $("#signinEmail").value.trim();
  err.hidden = true;
  if (!email) { err.textContent = t("errors.bad_email"); err.hidden = false; return; }
  let r;
  try { r = await post("/api/auth/link", { email }); } catch { err.textContent = t("errors.generic"); err.hidden = false; return; }
  if (!r.ok) { err.textContent = await errorText(r); err.hidden = false; return; }
  $("#signinSent").textContent = t("signin.sent", { email });
  $("#signinSent").hidden = false;
};

/* ============================================================================
   spontanees.js — table des entreprises + pilotage du pipeline
   ============================================================================ */
import { api } from "./api.js";

let stats = null;
let filtre = "all";

function ligne(e) {
  const aEmail = !!e.email;
  const statut = e.envoye
    ? `<span class="chip chip--vert">envoyé</span>`
    : aEmail
      ? `<span class="chip chip--ft">à envoyer</span>`
      : `<span class="chip chip--gris">ignoré</span>`;
  return `
    <div class="trow">
      <div>
        <div class="trow__name">${esc(e.nom || "—")}</div>
        <div class="trow__sub">${esc(e.ville || "")}</div>
      </div>
      <div class="trow__mail ${aEmail ? "" : "trow__mail--none"}">${aEmail ? esc(e.email) : "non trouvé"}</div>
      <div>${statut}</div>
    </div>`;
}

function rendreTable() {
  const el = document.querySelector('[data-list="spontanees"]');
  if (!el || !stats) return;
  let items = stats.dernieres || [];
  if (filtre === "email")  items = items.filter(e => e.email);
  if (filtre === "envoye") items = items.filter(e => e.envoye);

  el.innerHTML = items.length
    ? items.map(ligne).join("")
    : `<div class="empty" style="padding:40px 20px;">
         <div class="empty__title">Rien à afficher</div>
         <div class="empty__hint">Lance le pipeline pour récupérer des entreprises et leurs contacts.</div>
       </div>`;
}

function rendreKpis() {
  if (!stats) return;
  const set = (k, v) => { const e = document.querySelector(`[data-sp="${k}"]`); if (e) e.textContent = v; };
  set("raw", fmt(stats.raw));
  set("avec_email", fmt(stats.avec_email));
  set("mail_envoye", fmt(stats.mail_envoye));
  const taux = stats.raw ? Math.round((stats.avec_email / stats.raw) * 100) : 0;
  set("taux_email", `${taux}% de la base`);

  // compteur sidebar + pied
  const c = document.querySelector('[data-count="spontanees"]');
  if (c) c.textContent = fmt(stats.raw);
  const ae = document.querySelector('[data-stat="avec_email"]');
  if (ae) ae.textContent = fmt(stats.avec_email);
  const en = document.querySelector('[data-stat="envoyes"]');
  if (en) en.textContent = fmt(stats.mail_envoye);
  const tx = stats.avec_email ? Math.round((stats.mail_envoye / stats.avec_email) * 100) : 0;
  const bar = document.querySelector('[data-stat="taux-bar"]');
  if (bar) bar.style.width = `${tx}%`;
  const lbl = document.querySelector('[data-stat="taux"]');
  if (lbl) lbl.textContent = `${tx}% de taux d'envoi`;
}

/* Surligne l'étape active du pipeline + affiche l'état et le message */
function rendrePipe() {
  const pipe = document.querySelector("[data-pipe]");
  // Reset
  document.querySelectorAll("[data-step]").forEach(s => {
    s.classList.remove("is-active");
    const msg = s.querySelector("[data-step-msg]");
    if (msg) msg.textContent = "";
  });
  if (pipe) pipe.classList.remove("is-running");

  if (stats?.en_cours && stats.etape) {
    if (pipe) pipe.classList.add("is-running");
    const s = document.querySelector(`[data-step="${stats.etape}"]`);
    if (s) {
      s.classList.add("is-active");
      const msg = s.querySelector("[data-step-msg]");
      if (msg && stats.message) msg.textContent = stats.message;
      // Barre de progression (si un pourcentage est remonté)
      const pct = stats.pourcentage ?? 0;
      const bar = s.querySelector("[data-step-progress-bar]");
      const lbl = s.querySelector("[data-step-progress-pct]");
      if (bar) bar.style.width = pct + "%";
      if (lbl) lbl.textContent = pct + "%";
    }
  }
}

function fmt(n) { return (n ?? 0).toLocaleString("fr-FR"); }
function esc(s) {
  return String(s).replace(/[&<>"]/g, m => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[m]));
}

export const Spontanees = {
  async charger() {
    try { stats = await api.spStats(); } catch (_) { stats = null; }
    rendreKpis();
    rendreTable();
    rendrePipe();
  },

  setFiltre(f) { filtre = f; rendreTable(); },
  // Met à jour les cartes du pipeline depuis un état frais (appelé par le polling)
  majPipe(etatFrais) {
    stats = { ...(stats || {}), ...etatFrais };
    rendrePipe();
  },

  async action(nom) {
    try {
      if (nom === "fetch")    await api.spFetch();
      if (nom === "scraper")  await api.spScraper();
      if (nom === "envoyer") {
        const champ = document.querySelector("[data-envoyer-nombre]");
        let nb = parseInt(champ?.value, 10) || 10;
        nb = Math.max(1, Math.min(nb, 50));   // garde-fou : 1 à 50
        await api.spEnvoyer(nb);
      }
      this.charger();
    } catch (e) {
      alert(e.message);
    }
  },
};

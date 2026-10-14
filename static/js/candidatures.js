/* ============================================================================
   candidatures.js — tableau de suivi unique des candidatures du mode (D107)
   Offres où la personne a postulé et candidatures spontanées envoyées, lues
   par une seule route (/api/suivi) dans leurs tables d'origine : une seule
   notion de candidature, aucune liste recopiée.
   ============================================================================ */
import { api } from "./api.js";
import { etiquettesAutresModes } from "./spontanees.js";

// Statuts de suivi communs (ceux qui existaient) ; bounce : mail revenu, spontanées seulement
const STATUTS = [
  ["envoye",     "Envoyée"],
  ["a_relancer", "À relancer"],
  ["reponse",    "Réponse"],
  ["entretien",  "Entretien"],
  ["refus",      "Refus"],
  ["bounce",     "Bounce"],
];
const TYPES = { offre: "Offre", spontanee: "Spontanée" };

let _data = [];
let _filtre = "all";
let _type = "all";
let _ouvrir = null;    // fn(id) pour ouvrir la modale offre+lettre

const esc = s => String(s ?? "").replace(/[&<>"]/g, m => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[m]));
const dateFr = d => d ? d.split("-").reverse().join("/") : "—";

function ligne(c) {
  // « envoye » : « Postulée » pour une offre, « Envoyée » pour une spontanée
  const libelle = (v, label) => v === "envoye" && c.type === "offre" ? "Postulée" : label;
  const options = STATUTS.filter(([v]) => c.type === "spontanee" || v !== "bounce").map(([v, label]) =>
    `<option value="${v}"${v === c.statut ? " selected" : ""}>${libelle(v, label)}</option>`).join("");
  const lien = c.lien ? `<a class="cand-lien" href="${esc(c.lien)}" target="_blank" rel="noopener"
      title="${c.type === "offre" ? "Ouvrir l'offre en ligne" : "Site de l'entreprise"}">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg></a>` : "";
  const voir = c.type === "offre" ? `<button class="btn btn--sm" data-voir="${esc(c.id)}">Voir</button>` : "";
  return `<div class="suivi-row" data-type="${c.type}" data-id="${esc(c.id)}">
    <span class="suivi-row__nom">${esc(c.entreprise || "—")}${c.historique
      ? ' <span class="chip chip--gris" title="Contactée avant la refonte (import de l\'historique)">historique</span>' : ""}${
      c.type === "spontanee" ? etiquettesAutresModes(c) : ""}</span>
    <span title="${esc(c.poste)}">${esc(c.poste || "—")}</span>
    <span><span class="chip ${c.type === "offre" ? "chip--ft" : "chip--gris"}">${TYPES[c.type]}</span></span>
    <span>${dateFr(c.date)}</span>
    <select class="suivi-statut st-${c.statut}" data-cand-select="1">${options}</select>
    <span class="cand-actions">${voir}${lien}${c.contact ? `<span class="trow__sub" title="${esc(c.contact)}">${esc(c.contact)}</span>` : ""}</span>
  </div>`;
}

function rendre() {
  const el = document.querySelector('[data-list="candidatures"]');
  if (!el) return;
  const liste = _data.filter(c => (_filtre === "all" || c.statut === _filtre) && (_type === "all" || c.type === _type));
  el.innerHTML = liste.length ? liste.map(ligne).join("")
    : '<div class="suivi-empty">Aucune candidature dans cette catégorie.</div>';
}

export const Candidatures = {
  _branche: false,

  async charger() {
    try { _data = await api.suivi(); } catch (_) { return; }
    rendre();
    const c = document.querySelector('[data-count="candidatures"]');
    if (c) c.textContent = _data.length;
    if (this._branche) return;
    const liste = document.querySelector('[data-list="candidatures"]');
    // Changement de statut, écrit là où vit la candidature (offre ou spontanée)
    liste.addEventListener("change", async e => {
      if (!e.target.dataset.candSelect) return;
      const row = e.target.closest(".suivi-row");
      const statut = e.target.value;
      try {
        await api.suiviStatut(row.dataset.type, row.dataset.id, statut);
        const item = _data.find(c => c.type === row.dataset.type && String(c.id) === row.dataset.id);
        if (item) item.statut = statut;
        e.target.className = "suivi-statut st-" + statut;
      } catch (err) { alert(err.message); this.charger(); }
    });
    // Bouton « Voir » → modale offre + lettre
    liste.addEventListener("click", e => {
      const id = e.target.closest("[data-voir]")?.dataset.voir;
      if (id && _ouvrir) _ouvrir(id);
    });
    document.querySelectorAll('[data-filters="candidatures"] .filter').forEach(f =>
      f.addEventListener("click", () => {
        document.querySelectorAll('[data-filters="candidatures"] .filter').forEach(x => x.classList.remove("is-active"));
        f.classList.add("is-active");
        _filtre = f.dataset.filter;
        rendre();
      }));
    document.querySelector("[data-suivi-type]")?.addEventListener("change", e => { _type = e.target.value; rendre(); });
    this._branche = true;
  },

  onOuvrir(fn) { _ouvrir = fn; },
};

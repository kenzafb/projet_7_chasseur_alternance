/* ============================================================================
   candidatures.js — tableau de suivi des candidatures (offres avec lettre)
   Réutilise les données déjà chargées par Offres (une seule source).
   N'affiche que les candidatures réellement engagées : envoyé → refus.
   ============================================================================ */
import { api } from "./api.js";

// Statuts de suivi d'une candidature alternance (après génération de lettre)
const STATUTS = [
  ["envoye",    "Envoyé"],
  ["reponse",   "Réponse"],
  ["entretien", "Entretien"],
  ["refus",     "Refus"],
];
const STATUTS_SUIVIS = STATUTS.map(s => s[0]);

let _data = [];        // offres candidatées (statut dans STATUTS_SUIVIS)
let _filtre = "all";
let _refresh = null;
let _ouvrir = null;    // fn(id) pour ouvrir la modale offre+lettre

function scoreClass(n) {
  if (n >= 8) return "sc-haut";
  if (n >= 5) return "sc-moyen";
  return "sc-bas";
}

function ligne(o) {
  const st = o.statut || "envoye";
  const options = STATUTS.map(([v, label]) =>
    `<option value="${v}"${v === st ? " selected" : ""}>${label}</option>`).join("");
  const score = (o.score ?? o.note ?? "—");
  return `<div class="suivi-row" data-id="${o.id}">
    <span class="suivi-row__nom">${o.entreprise || "—"}</span>
    <span>${o.titre || "—"}</span>
    <span><span class="score-pill ${scoreClass(score)}">${score}</span></span>
    <select class="suivi-statut st-${st}" data-cand-select="1">${options}</select>
    <span class="cand-actions">
      <button class="btn btn--sm" data-voir="${o.id}">Voir</button>
      ${o.lien ? `<a class="cand-lien" href="${o.lien}" target="_blank" rel="noopener" title="Ouvrir l'offre en ligne">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>
      </a>` : ""}
    </span>
  </div>`;
}

function rendre() {
  const c = document.querySelector('[data-list="candidatures"]');
  if (!c) return;
  const liste = _filtre === "all" ? _data : _data.filter(o => (o.statut || "envoye") === _filtre);
  if (!liste.length) {
    c.innerHTML = '<div class="suivi-empty">Aucune candidature dans cette catégorie.</div>';
    return;
  }
  try {
    c.innerHTML = liste.map(ligne).join("");
  } catch (err) {
    console.error("[CAND] erreur rendu:", err);
  }
}

export const Candidatures = {
  _branche: false,

  rendre(offres) {
    // Ne garde que les candidatures réellement engagées
    _data = (offres || []).filter(o => STATUTS_SUIVIS.includes(o.statut));
    rendre();
    const c = document.querySelector('[data-count="candidatures"]');
    if (c) c.textContent = _data.length;

    if (!this._branche) {
      const liste = document.querySelector('[data-list="candidatures"]');
      // Changement de statut
      liste.addEventListener("change", async e => {
        if (!e.target.dataset.candSelect) return;
        const row = e.target.closest(".suivi-row");
        const id = row.dataset.id;
        const statut = e.target.value;
        try {
          await api.majStatut(id, statut);
          const item = _data.find(o => String(o.id) === String(id));
          if (item) item.statut = statut;
          e.target.className = "suivi-statut st-" + statut;
          if (_refresh) _refresh();
        } catch (_) {}
      });
      // Bouton "Voir" → modale offre + lettre
      liste.addEventListener("click", e => {
        const id = e.target.dataset.voir;
        if (id && _ouvrir) _ouvrir(id);
      });
      // Filtres
      document.querySelectorAll('[data-filters="candidatures"] .filter').forEach(f =>
        f.addEventListener("click", () => {
          document.querySelectorAll('[data-filters="candidatures"] .filter').forEach(x => x.classList.remove("is-active"));
          f.classList.add("is-active");
          _filtre = f.dataset.filter;
          rendre();
        }));
      this._branche = true;
    }
  },

  onRefresh(fn) { _refresh = fn; },
  onOuvrir(fn) { _ouvrir = fn; },
};

/* ============================================================================
   offres.js — rendu des offres + viseur de score (élément signature)
   ============================================================================ */
import { api } from "./api.js";

const SEUIL = 7;                 // score minimum "à postuler" — repère du viseur
let cache = [];                  // offres chargées
let filtre = "all";
let modeArchives = false;   // false = offres à postuler, true = archivées
let fOffres = { source: "all", zone: "all", score: "all" };  // filtres combinables du mode normal
const LABEL_RAISON = {
  manuel: "Manuel", note_basse: "Note basse", ecole_cfa: "École / CFA",
  hors_it: "Hors IT", public_specifique: "Public spécifique", stage: "Stage",
};

const $list = () => document.querySelector('[data-list="offres"]');

/* Couleur du verdict selon le score */
function teinte(score) {
  if (score >= SEUIL) return "vert";
  if (score >= 5)     return "ambre";
  return "rouge";
}

/* Le viseur : jauge graduée avec repère au seuil 7.0 */
function viseur(score) {
  const t = teinte(score);
  const pct = Math.max(0, Math.min(100, score * 10));
  return `
    <div class="viseur viseur--${t}">
      <span class="viseur__val">${score}<small>/10</small></span>
      <span class="viseur__track">
        <span class="viseur__fill" style="width:${pct}%"></span>
        <span class="viseur__tick" title="seuil à postuler"></span>
      </span>
    </div>`;
}

function badgeSource(src) {
  const lba = (src || "").toLowerCase().includes("bonne");
  return `<span class="chip ${lba ? "chip--lba" : "chip--ft"}">${lba ? "LBA" : "France Travail"}</span>`;
}

function carte(o) {
  const score = o.score ?? 0;
  const forts   = (o.points_forts   || []).map(p => `<li>${esc(p)}</li>`).join("");
  const faibles = (o.points_faibles || []).map(p => `<li>${esc(p)}</li>`).join("");
  const aLettre = !!o.lettre;

  return `
  <article class="card offre" data-id="${o.id}" data-search-text="${esc((o.titre||'')+' '+(o.entreprise||'')+' '+(o.lieu||o.zone||'')).toLowerCase()}">
    <div class="offre__head" data-toggle>
      <div class="offre__meta">
        <div class="offre__tags">
          ${badgeSource(o.source)}
          ${score >= SEUIL ? '<span class="chip chip--vert">à postuler</span>' : ""}
          ${o.domaine ? `<span class="chip chip--gris">${esc(o.domaine)}</span>` : ""}
        </div>
        <div class="offre__title">${esc(o.titre || "Sans titre")}</div>
        <div class="offre__org"><b>${esc(o.entreprise || "Entreprise inconnue")}</b> · ${esc(o.lieu || o.zone || "")}</div>
      </div>
      <div class="offre__score">${viseur(score)}</div>
      <svg class="offre__chevron" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"/></svg>
    </div>
    <div class="offre__body">
      ${o.resume_analyse ? `<p class="offre__resume">${esc(o.resume_analyse)}</p>` : ""}
      <div class="offre__analyse">
        <div class="analyse-col forts"><h4>Points forts</h4><ul>${forts || "<li>—</li>"}</ul></div>
        <div class="analyse-col faibles"><h4>Points faibles</h4><ul>${faibles || "<li>—</li>"}</ul></div>
      </div>
      <div class="offre__actions">
        ${o.lien ? `<a class="btn" href="${o.lien}" target="_blank" rel="noopener">Voir l'offre</a>` : ""}
        <button class="btn" data-act="analyser">Réanalyser</button>
        <button class="btn btn--signal" data-act="lettre">${aLettre ? "Voir la lettre" : "Générer la lettre"}</button>
        ${o.statut !== "archive" ? `
        <select class="archiver-select" data-archiver-select>
          <option value="">Archiver…</option>
          ${["manuel","note_basse","ecole_cfa","hors_it","public_specifique","stage"]
            .map(r => `<option value="${r}">→ ${LABEL_RAISON[r]}</option>`).join("")}
        </select>` : ""}
      </div>
      ${o.statut === "archive" ? `
      <div class="offre__archive-actions">
        <label class="archive-raison">
          <span>Raison :</span>
          <select data-raison-select>
            ${["manuel","note_basse","ecole_cfa","hors_it","public_specifique","stage"]
              .map(r => `<option value="${r}"${(o.raison_archivage||"manuel")===r?" selected":""}>${LABEL_RAISON[r]}</option>`).join("")}
          </select>
        </label>
        <button class="btn btn--ghost" data-act="desarchiver">Désarchiver</button>
      </div>` : ""}
    </div>
  </article>`;
}

function appliquerFiltre(o) {
  const estArchive = o.statut === "archive";
  // Mode archives : on ne montre QUE les archivées, filtrées par raison
  if (modeArchives) {
    if (!estArchive) return false;
    if (filtre === "all") return true;
    return (o.raison_archivage || "manuel") === filtre;
  }
  // Mode normal : non-archivées, filtres combinables (source ET zone ET score)
  if (estArchive) return false;
  const estLba = (o.source || "").toLowerCase().includes("bonne");
  // Source
  if (fOffres.source === "ft"  && estLba) return false;
  if (fOffres.source === "lba" && !estLba) return false;
  // Localisation (zone)
  if (fOffres.zone !== "all" && (o.zone || "") !== fOffres.zone) return false;
  // Score
  const sc = o.score ?? 0;
  if (fOffres.score === "haut"  && sc < 7) return false;
  if (fOffres.score === "moyen" && (sc < 5 || sc > 6)) return false;
  if (fOffres.score === "bas"   && sc >= 5) return false;
  return true;
}

function rendre() {
  const visibles = cache.filter(appliquerFiltre)
                        .sort((a, b) => (b.score ?? 0) - (a.score ?? 0));
  const el = $list();
  if (!visibles.length) {
    el.innerHTML = `<div class="empty">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="11" cy="11" r="7"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
      <div class="empty__title">Aucune offre dans ce filtre</div>
      <div class="empty__hint">Change de filtre ou lance une nouvelle recherche.</div></div>`;
    return;
  }
  el.innerHTML = visibles.map(carte).join("");
}

/* Met à jour les KPI du haut de page */
function rendreKpis() {
  const actives = cache.filter(o => o.statut !== "archive");
  const scores  = actives.map(o => o.score ?? 0);
  const moy     = scores.length ? (scores.reduce((a, b) => a + b, 0) / scores.length) : 0;
  const set = (k, v) => { const e = document.querySelector(`[data-kpi="${k}"]`); if (e) e.textContent = v; };
  set("nouvelles", actives.length);
  set("nouvelles-note", actives.length ? "offres actives" : "—");
  set("score-moyen", moy ? moy.toFixed(1) : "—");
  set("a-postuler", actives.filter(o => (o.score ?? 0) >= SEUIL).length);
  set("lettres", actives.filter(o => o.lettre).length);
  const c = document.querySelector('[data-count="offres"]');
  if (c) c.textContent = actives.length;
}

/* Échappement HTML basique */
function esc(s) {
  return String(s).replace(/[&<>"]/g, m => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[m]));
}

export const Offres = {
  _brancheRaison: false,
  async charger() {
    try {
      cache = await api.candidatures();
    } catch (e) {
      cache = [];
    }
    rendre();
    rendreKpis();
    // Listener du menu de raison d'archivage (branché une seule fois)
    if (!this._brancheRaison) {
      const liste = $list();
      if (liste) {
        liste.addEventListener("change", e => {
          const carteEl = e.target.closest(".offre");
          if (!carteEl) return;
          const id = carteEl.dataset.id;
          // Changer la raison d'une offre déjà archivée
          if (e.target.closest("[data-raison-select]")) {
            api.changerRaison(id, e.target.value).then(() => this.charger());
          }
          // Archiver une offre active avec la raison choisie
          else if (e.target.closest("[data-archiver-select]") && e.target.value) {
            api.changerRaison(id, e.target.value).then(() => this.charger());
          }
        });
        this._brancheRaison = true;
      }
    }
  },

  data: () => cache,

  setFiltre(f) { filtre = f; rendre(); },
  setFiltreOffre(dim, valeur) { fOffres[dim] = valeur; rendre(); },
  estModeArchives() { return modeArchives; },
  basculerArchives() {
    modeArchives = !modeArchives;
    filtre = "all";   // on repart sur "toutes" à chaque bascule
    rendre();
    return modeArchives;
  },

  /* Gestion des clics délégués depuis app.js */
  onClick(e, ouvrirLettre) {
    const carteEl = e.target.closest(".offre");
    if (!carteEl) return false;
    const id = carteEl.dataset.id;

    if (e.target.closest("[data-toggle]") && !e.target.closest(".offre__score a")) {
      carteEl.classList.toggle("is-open");
      return true;
    }
    const act = e.target.closest("[data-act]")?.dataset.act;
    if (act === "analyser") {
      api.analyser(id).then(() => this.charger());
      return true;
    }
    if (act === "lettre") {
      ouvrirLettre(id);
      return true;
    }
    if (act === "desarchiver") {
      api.desarchiver(id).then(() => this.charger());
      return true;
    }
    return false;
  },
};

/* ============================================================================
   candidatures.js — tableau de suivi du mode en colonnes (D107, D146)
   Envoyée, Relancée, Entretien, Réponse. Chaque carte a un bouton pour
   l'étape suivante et « Revenir à l'étape d'avant » ; Acceptée ou Refusée
   dans la dernière colonne. Aucun glisser-déposer : de vrais boutons.
   Offres postulées et candidatures spontanées envoyées, lues par une seule
   route (/api/suivi) dans leurs tables d'origine.
   ============================================================================ */
import { api, esc, lienSur } from "./api.js";
import { etiquettesAutresModes } from "./spontanees.js";

const COLONNES = [
  { cle: "envoyee",   titre: "Envoyée",   statuts: ["envoye", "a_relancer"],
    aide: "Tes candidatures envoyées arrivent ici." },
  { cle: "relancee",  titre: "Relancée",  statuts: ["relancee"], aide: "Après une relance, la carte passe ici." },
  { cle: "entretien", titre: "Entretien", statuts: ["entretien"], aide: "Quand on te propose un entretien." },
  { cle: "reponse",   titre: "Réponse",   statuts: ["reponse", "acceptee", "refus", "bounce"],
    aide: "Acceptée ou refusée : la candidature se termine ici." },
];
// Étape suivante et étape d'avant de chaque statut
const SUIVANT = { envoye: ["relancee", "J'ai relancé"], a_relancer: ["relancee", "J'ai relancé"],
  relancee: ["entretien", "J'ai un entretien"], entretien: ["reponse", "J'ai eu la réponse"] };
const AVANT = { relancee: "envoye", entretien: "relancee", reponse: "entretien", acceptee: "reponse", refus: "reponse",
  bounce: "envoye" };
// Tous les statuts, pour « Changer d'étape » (« envoye » : « Postulée » pour une offre)
const LIBELLES = [["envoye", "Envoyée"], ["a_relancer", "À relancer"], ["relancee", "Relancée"],
  ["entretien", "Entretien"], ["reponse", "Réponse, en attente de la suite"], ["acceptee", "Acceptée"],
  ["refus", "Refusée"], ["bounce", "Adresse invalide"]];
const ISSUES = { acceptee: ["Acceptée", "bien"], refus: ["Refusée", "refus"], bounce: ["Adresse invalide", "refus"] };
const TYPES = { offre: "Offre", spontanee: "Entreprise" };

let _data = [];
let _type = "all";
let _ouvrir = null;    // fn(id) pour ouvrir la lettre d'une offre
let _focus = null;     // carte à refocaliser après un changement d'étape

const MOIS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."];
const dateCourte = d => {
  const [a, m, j] = (d || "").split("-").map(Number);
  return a && m && j ? `${j} ${MOIS[m - 1]}` : "";
};
const cleCarte = c => `${c.type}:${c.id}`;

function carte(c) {
  const suivant = SUIVANT[c.statut];
  const avant = AVANT[c.statut];
  const issue = ISSUES[c.statut];
  const quand = dateCourte(c.date);
  const libelle = (v, l) => v === "envoye" && c.type === "offre" ? "Postulée" : l;
  const options = LIBELLES.filter(([v]) => c.type === "spontanee" || v !== "bounce")
    .map(([v, l]) => `<option value="${v}"${v === c.statut ? " selected" : ""}>${libelle(v, l)}</option>`).join("");
  const lien = lienSur(c.lien);
  return `<li class="carte-cand" data-type="${esc(c.type)}" data-id="${esc(c.id)}" data-cle="${esc(cleCarte(c))}">
    <p class="carte-cand__tags">
      <span class="chip chip--gris">${TYPES[c.type]}</span>
      ${c.statut === "a_relancer" ? '<span class="chip chip--ambre">À relancer</span>' : ""}
      ${issue ? `<span class="chip chip--${issue[1] === "bien" ? "vert" : "rouge"}">${issue[0]}</span>` : ""}
      ${c.historique ? '<span class="chip chip--gris" title="Contactée avant la refonte (import de l\'historique)">historique</span>' : ""}
      ${c.type === "spontanee" ? etiquettesAutresModes(c) : ""}
    </p>
    <h3 class="carte-cand__poste">${esc(c.poste || "Candidature")}</h3>
    <p class="carte-cand__qui">${esc(c.entreprise || "Entreprise inconnue")}${quand ? ` · envoyée le ${quand}` : ""}</p>
    <div class="carte-cand__actions">
      ${suivant ? `<button type="button" class="btn btn--sm btn--primary" data-etape="${suivant[0]}">${suivant[1]}</button>` : ""}
      ${c.statut === "reponse" ? `<button type="button" class="btn btn--sm btn--primary" data-etape="acceptee">Acceptée</button>
        <button type="button" class="btn btn--sm" data-etape="refus">Refusée</button>` : ""}
    </div>
    ${avant ? `<button type="button" class="lien-bouton carte-cand__avant" data-etape="${avant}">Revenir à l'étape d'avant</button>` : ""}
    <details class="carte-cand__plus">
      <summary>Plus<span class="visuellement-cache"> sur ${esc(c.entreprise || "cette candidature")}</span></summary>
      <div class="carte-cand__plus-corps">
        <label class="filtre"><span>Changer d'étape</span>
          <select class="filtre-menu" data-cand-select="1">${options}</select></label>
        ${c.type === "offre" ? `<label class="filtre"><span>Date de candidature</span>
          <input type="date" class="cand-date" data-cand-date value="${esc(c.date)}" max="${new Date().toLocaleDateString("sv-SE")}"></label>` : ""}
        ${c.contact ? `<p class="carte-cand__contact">Contact : ${esc(c.contact)}</p>` : ""}
        <p class="carte-cand__liens">
          ${lien ? `<a href="${esc(lien)}" target="_blank" rel="noopener">${c.type === "offre" ? "Voir l'offre en ligne" : "Site de l'entreprise"}<span class="visuellement-cache"> (nouvel onglet)</span></a>` : ""}
          ${c.type === "offre" ? `<button type="button" class="lien-bouton" data-voir="${esc(c.id)}">${c.lettre ? "Voir ma lettre" : "Préparer ma lettre"}</button>
          <button type="button" class="lien-bouton" data-annuler="${esc(c.id)}">Je n'ai pas postulé (remettre dans Offres)</button>` : ""}
        </p>
      </div>
    </details>
  </li>`;
}

function rendre() {
  const el = document.querySelector('[data-list="candidatures"]');
  if (!el) return;
  const liste = _data.filter(c => _type === "all" || c.type === _type);
  el.innerHTML = COLONNES.map(col => {
    const cartes = liste.filter(c => col.statuts.includes(c.statut));
    return `<section class="colonne" aria-labelledby="col-${col.cle}">
      <h2 class="colonne__titre" id="col-${col.cle}">${col.titre} <span class="colonne__nombre">${cartes.length}</span></h2>
      ${cartes.length ? `<ul class="colonne__cartes">${cartes.map(carte).join("")}</ul>`
        : `<p class="colonne__aide">${col.aide}</p>`}
    </section>`;
  }).join("");
  if (_focus) {
    el.querySelector(`[data-cle="${CSS.escape(_focus)}"] button, [data-cle="${CSS.escape(_focus)}"] summary`)?.focus();
    _focus = null;
  }
}

function annoncer(texte) {
  const m = document.querySelector("[data-cand-message]");
  if (m) m.textContent = texte;
}

export const Candidatures = {
  _branche: false,

  async charger() {
    try { _data = await api.suivi(); } catch (_) { return; }
    rendre();
    // Compteur du menu : ce qui attend, les candidatures à relancer
    const c = document.querySelector('[data-count="candidatures"]');
    const aRelancer = _data.filter(x => x.statut === "a_relancer").length;
    if (c) {
      c.textContent = aRelancer;
      c.hidden = !aRelancer;
      c.setAttribute("aria-label", `${aRelancer} à relancer`);
    }
    if (this._branche) return;
    const liste = document.querySelector('[data-list="candidatures"]');

    const changer = async (carteEl, statut) => {
      const item = _data.find(x => x.type === carteEl.dataset.type && String(x.id) === carteEl.dataset.id);
      try {
        await api.suiviStatut(carteEl.dataset.type, carteEl.dataset.id, statut);
        _focus = carteEl.dataset.cle;
        const titre = (LIBELLES.find(([v]) => v === statut) || [])[1] || statut;
        annoncer(`${item?.entreprise || "Candidature"} : ${titre}.`);
      } catch (err) { alert(err.message); }
      this.charger();
    };

    liste.addEventListener("change", async e => {
      const carteEl = e.target.closest(".carte-cand");
      if (!carteEl) return;
      // Date de candidature d'une offre, modifiable depuis le tableau
      if (e.target.matches("[data-cand-date]")) {
        try { await api.postuler(carteEl.dataset.id, { date: e.target.value }); } catch (err) { alert(err.message); }
        this.charger();
        return;
      }
      if (e.target.dataset.candSelect) changer(carteEl, e.target.value);
    });

    liste.addEventListener("click", async e => {
      const carteEl = e.target.closest(".carte-cand");
      if (!carteEl) return;
      const etape = e.target.closest("[data-etape]")?.dataset.etape;
      if (etape) { changer(carteEl, etape); return; }
      // « Je n'ai pas postulé » : l'offre revient dans la page Offres (D110)
      const annuler = e.target.closest("[data-annuler]")?.dataset.annuler;
      if (annuler) {
        try { await api.postuler(annuler, { annuler: true }); } catch (err) { alert(err.message); }
        await this.charger();
        annoncer("L'offre est revenue dans la page Offres.");
        document.dispatchEvent(new Event("offres:maj"));
        return;
      }
      const id = e.target.closest("[data-voir]")?.dataset.voir;
      if (id && _ouvrir) _ouvrir(id);
    });
    document.querySelector("[data-suivi-type]")?.addEventListener("change", e => { _type = e.target.value; rendre(); });
    this._branche = true;
  },

  onOuvrir(fn) { _ouvrir = fn; },
};

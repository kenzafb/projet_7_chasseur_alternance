/* ============================================================================
   profil.js — gestion du formulaire profil utilisateur
   - champs simples : [data-profil="..."]
   - tags : [data-tags="..."] + [data-tags-input="..."]
   - projets : [data-projets] (liste de cartes nom/url/description)
   ============================================================================ */

import { api, avecMode } from "./api.js";
import { CompteEnvoi } from "./compte_envoi.js";

const _tags = {};
let _modeProfilCourant = "alternance";   // mode du profil actuellement affiché
let _projets = [];

/* ── Tags ──────────────────────────────────────────────────────────────── */
function rendreTags(champ) {
  const c = document.querySelector(`[data-tags="${champ}"]`);
  if (!c) return;
  c.innerHTML = "";
  (_tags[champ] || []).forEach((v, i) => {
    const el = document.createElement("span");
    el.className = "tag";
    el.innerHTML = `<span>${v}</span><span class="tag__x" data-rm="${i}">×</span>`;
    c.appendChild(el);
  });
}
function brancherTags(champ) {
  const input = document.querySelector(`[data-tags-input="${champ}"]`);
  const c = document.querySelector(`[data-tags="${champ}"]`);
  if (!input || !c) return;
  input.addEventListener("keydown", e => {
    if (e.key === "Enter") {
      e.preventDefault();
      const v = input.value.trim();
      if (v && !(_tags[champ] || []).includes(v)) {
        (_tags[champ] = _tags[champ] || []).push(v);
        rendreTags(champ);
      }
      input.value = "";
    }
  });
  c.addEventListener("click", e => {
    const i = e.target.dataset.rm;
    if (i !== undefined) { _tags[champ].splice(Number(i), 1); rendreTags(champ); }
  });
}

/* ── Projets ───────────────────────────────────────────────────────────── */
function echap(s) { return (s || "").replace(/"/g, "&quot;"); }

function rendreProjets() {
  const c = document.querySelector("[data-projets]");
  if (!c) return;
  c.innerHTML = "";
  _projets.forEach((p, i) => {
    const el = document.createElement("div");
    el.className = "projet";
    el.innerHTML = `
      <span class="projet__rm" data-projet-rm="${i}">Retirer</span>
      <div class="projet__grid">
        <label class="field"><span class="field__label">Nom du projet</span>
          <input class="field__input" data-pj="${i}:nom" type="text" value="${echap(p.nom)}" placeholder="Mon projet"></label>
        <label class="field"><span class="field__label">Lien (GitHub…)</span>
          <input class="field__input" data-pj="${i}:url" type="text" value="${echap(p.url)}" placeholder="github.com/..."></label>
        <label class="field field--full"><span class="field__label">Description</span>
          <textarea class="field__area" data-pj="${i}:description" rows="2" placeholder="Ce que fait le projet, les technos utilisées…">${echap(p.description)}</textarea></label>
      </div>`;
    c.appendChild(el);
  });
}

function lireProjetsDepuisDOM() {
  document.querySelectorAll("[data-pj]").forEach(el => {
    const [i, champ] = el.dataset.pj.split(":");
    if (_projets[i]) _projets[i][champ] = el.value;
  });
}

function brancherProjets() {
  const btn = document.querySelector("[data-projet-add]");
  const c = document.querySelector("[data-projets]");
  if (btn) btn.addEventListener("click", () => {
    lireProjetsDepuisDOM();
    _projets.push({ nom: "", url: "", description: "" });
    rendreProjets();
  });
  if (c) c.addEventListener("click", e => {
    const i = e.target.dataset.projetRm;
    if (i !== undefined) { lireProjetsDepuisDOM(); _projets.splice(Number(i), 1); rendreProjets(); }
  });
}

/* ── Module ────────────────────────────────────────────────────────────── */
/* ── Validation de la lettre type ──────────────────────────────────────── */
function validerLettre(txt) {
  // Placeholders autorisés
  const autorises = ["contact_entreprise", "date", "paragraphe_entreprise"];
  // Trouve tous les {...}
  const trouves = [...txt.matchAll(/\{([^}]*)\}/g)].map(m => m[1].trim());
  // Accolades non fermées / vides
  const ouvrantes = (txt.match(/\{/g) || []).length;
  const fermantes = (txt.match(/\}/g) || []).length;
  if (ouvrantes !== fermantes) return "accolade non fermée détectée. Vérifie les { et }.";
  for (const t of trouves) {
    if (!autorises.includes(t)) {
      return `accolade non autorisée : {${t}}. Seuls {contact_entreprise}, {date} et {paragraphe_entreprise} sont permis.`;
    }
  }
  if (!trouves.includes("paragraphe_entreprise")) {
    return "il manque {paragraphe_entreprise} — c'est là que l'IA écrit le paragraphe personnalisé. Ajoute-le.";
  }
  return null;
}

/* ── Pièces jointes ────────────────────────────────────────────────────── */
function rendrePiecesJointes(pieces) {
  const c = document.querySelector("[data-pj-list]");
  if (!c) return;
  c.innerHTML = "";
  (pieces || []).forEach(pj => {
    const el = document.createElement("div");
    el.className = "pj-item";
    el.innerHTML = `
      <span class="pj-item__nom">${pj.nom}</span>
      <span class="pj-item__actions">
        <a class="pj-item__link" href="${avecMode(`/api/profil/piece?nom=${encodeURIComponent(pj.nom)}`)}" target="_blank">Voir</a>
        <span class="pj-item__rm" data-pj-rm="${pj.nom}">Supprimer</span>
      </span>`;
    c.appendChild(el);
  });
}

async function rafraichirPiecesJointes() {
  let p;
  try { p = await api.profil(); } catch (_) { return; }
  rendrePiecesJointes(p.pieces_jointes || []);
}

function brancherPiecesJointes() {
  const fileInput = document.querySelector("[data-pj-file]");
  const fname = document.querySelector("[data-pj-fname]");
  const btnUp = document.querySelector("[data-pj-upload]");
  const liste = document.querySelector("[data-pj-list]");

  if (fileInput) fileInput.addEventListener("change", () => {
    fname.textContent = fileInput.files[0] ? fileInput.files[0].name : "Aucun fichier";
  });

  if (btnUp) btnUp.addEventListener("click", async () => {
    const fichier = fileInput.files[0];
    if (!fichier) { alert("Choisis un fichier PDF."); return; }
    const fd = new FormData();
    fd.append("fichier", fichier);
    try {
      await api.envoyerPiece(fd);
      fileInput.value = ""; fname.textContent = "Aucun fichier";
      await rafraichirPiecesJointes();
    } catch (e) {
      alert(e.message || "Erreur lors du téléversement");
    }
  });

  if (liste) liste.addEventListener("click", async e => {
    const nom = e.target.dataset.pjRm;
    if (nom && confirm(`Supprimer la pièce « ${nom} » ?`)) {
      try { await api.supprimerPiece(nom); } catch (e) { alert(e.message); }
      await rafraichirPiecesJointes();
    }
  });
}

/* ── Domaines recherchés ───────────────────────────────────────────────
   Grands domaines (lettre) d'abord, affinables par domaine (3 caractères).
   Enregistrés en codes : ["M18"], ["C"], [] pour indifférent. Un grand
   domaine coché couvre tous ses domaines (cases grisées). */
function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

async function rendreDomaines(selectionnes, selecteur = "[data-domaines-choix]") {
  const c = document.querySelector(selecteur);
  if (!c) return;
  let arbre = [];
  try { arbre = await api.domaines(); } catch (_) { arbre = []; }
  const choisis = new Set(selectionnes);
  c.innerHTML = `
    <label class="domaine-case domaine-case--indifferent">
      <input type="checkbox" data-domaine-indifferent ${choisis.size ? "" : "checked"}>
      <span>Indifférent (tous les domaines)</span>
    </label>
    <div class="gd-liste">${arbre.map(g => `
      <div class="gd" data-gd="${esc(g.code)}">
        <div class="gd__tete">
          <label class="domaine-case">
            <input type="checkbox" value="${esc(g.code)}" data-gd-case ${choisis.has(g.code) ? "checked" : ""}>
            <span>${esc(g.libelle)}</span>
          </label>
          <button type="button" class="gd__affiner" data-gd-affiner>Affiner</button>
        </div>
        <div class="gd__domaines" data-gd-domaines hidden>${g.domaines.map(d => `
          <label class="domaine-case domaine-case--petit">
            <input type="checkbox" value="${esc(d.code)}" data-domaine-case ${choisis.has(d.code) ? "checked" : ""}>
            <span>${esc(d.libelle)}</span>
          </label>`).join("")}
        </div>
      </div>`).join("")}
    </div>`;

  majAffichageDomaines(c);
  if (c.dataset.branche) return;            // écouteurs posés une seule fois par conteneur
  c.dataset.branche = "1";
  c.addEventListener("change", e => {
    const indifferent = c.querySelector("[data-domaine-indifferent]");
    if (e.target === indifferent) {
      if (indifferent.checked) c.querySelectorAll("[data-gd-case], [data-domaine-case]").forEach(i => { i.checked = false; });
    } else if (e.target.checked) {
      indifferent.checked = false;
    }
    if (!c.querySelector("[data-gd-case]:checked, [data-domaine-case]:checked")) indifferent.checked = true;
    majAffichageDomaines(c);
  });
  c.addEventListener("click", e => {
    const bouton = e.target.closest("[data-gd-affiner]");
    if (!bouton) return;
    const liste = bouton.closest(".gd").querySelector("[data-gd-domaines]");
    liste.hidden = !liste.hidden;
  });
}

function majAffichageDomaines(c) {
  c.querySelectorAll(".gd").forEach(gd => {
    const lettre = gd.querySelector("[data-gd-case]");
    const sous = [...gd.querySelectorAll("[data-domaine-case]")];
    sous.forEach(i => {
      i.disabled = lettre.checked;
      if (lettre.checked) i.checked = false;
    });
    const n = sous.filter(i => i.checked).length;
    gd.querySelector("[data-gd-affiner]").textContent = lettre.checked ? "Tout le domaine"
      : n ? `${n} domaine${n > 1 ? "s" : ""} choisi${n > 1 ? "s" : ""}` : "Affiner";
    if (n) gd.querySelector("[data-gd-domaines]").hidden = false;
  });
  c.querySelectorAll(".domaine-case").forEach(l => {
    l.classList.toggle("is-checked", l.querySelector("input").checked);
  });
  // Bandeau d'invitation (alternance) tant qu'aucun domaine n'est choisi
  const bandeau = c.parentElement.querySelector("[data-domaines-vide]");
  if (bandeau) bandeau.hidden = !c.querySelector("[data-domaine-indifferent]")?.checked;
}

// Conteneur des domaines de chaque mode
const DOMAINES_DU_MODE = {
  alternance: "[data-domaines-choix]", job: "[data-domaines-choix-job]", stage: "[data-domaines-choix-stage]",
};

function lireDomainesCoches(selecteur = "[data-domaines-choix]") {
  const c = document.querySelector(selecteur);
  if (!c || c.querySelector("[data-domaine-indifferent]")?.checked) return [];
  const lettres = [...c.querySelectorAll("[data-gd-case]:checked")].map(i => i.value);
  const domaines = [...c.querySelectorAll("[data-domaine-case]:checked")].map(i => i.value)
    .filter(code => !lettres.includes(code[0]));
  return [...lettres, ...domaines];
}

/* ── Options de recherche : taille des offres (alternance, job), taille des
   candidatures spontanées (tous les modes, réglage distinct, D63), thèmes
   (job), départements des spontanées (tous les modes), secteurs employeur.
   Rien de coché : aucun filtre (spontanées : tout sauf « sans salarié »).
   Taille des offres filtrée après récupération. Mode stage : intitulés
   filtrés, pas de taille des offres (peu d'offres, D74). */
async function rendreOptions(rech, mode) {
  const c = document.querySelector(`[data-options-recherche="${mode}"]`);
  if (!c) return;
  let o;
  try { o = await api.criteresOptions(); } catch (_) { c.innerHTML = ""; return; }
  const avecOffres = mode !== "stage";
  const sources = mode === "alternance" ? "de Sirene et de La Bonne Alternance" : "de Sirene";
  // Avertissements des petites tailles écrits pour l'alternance (D55)
  const recrue = { stage: "stagiaire", job: "salarié en contrat court" }[mode];
  const avert = t => recrue ? t.replace(/d'alternant/g, `de ${recrue}`).replace(/un alternant/g, `un ${recrue}`) : t;
  const tailles = new Set(rech.tailles || []), secteurs = new Set(rech.secteurs || []);
  const themes = new Set(rech.themes || []), departements = new Set(rech.departements || []);
  const taillesSp = new Set(rech.tailles_spontanees || []);
  const caseOption = (attribut, valeur, libelle, coche, extra = "") => `
    <label class="domaine-case domaine-case--petit">
      <input type="checkbox" value="${esc(valeur)}" ${attribut} ${coche ? "checked" : ""}>
      <span>${esc(libelle)}${extra}</span>
    </label>`;
  c.innerHTML = `
    ${avecOffres ? `
    <div class="options-bloc">
      <span class="field__label">Taille de l'entreprise (offres)</span>
      <p class="profil-card__sub" style="margin:4px 0 10px;">Rien de coché : toutes les tailles. France Travail indique en général l'effectif de l'établissement qui recrute.${mode === "alternance" ? " Une petite entreprise qui publie une offre veut recruter : mieux vaut ne rien cocher ici." : ""}</p>
      <div class="domaines-choix">${o.tailles.filter(t => t.cle !== "sans_salarie").map(t => caseOption("data-taille-case", t.cle, t.libelle, tailles.has(t.cle))).join("")}
      </div>
      <div class="domaines-choix" style="margin-top:8px;">
        <label class="domaine-case domaine-case--petit">
          <input type="checkbox" data-taille-inconnue ${rech.taille_inconnue !== false ? "checked" : ""}>
          <span>Garder les offres dont l'effectif est inconnu</span>
        </label>
      </div>
    </div>` : ""}
    <div class="options-bloc">
      <span class="field__label">Taille de l'entreprise (candidatures spontanées)</span>
      <p class="profil-card__sub" style="margin:4px 0 10px;">Entreprises ${sources}, effectif de l'entreprise entière. Rien de coché : toutes les tailles sauf « sans salarié ».</p>
      <div class="domaines-choix">${o.tailles.map(t => caseOption("data-taille-sp-case", t.cle, t.libelle, taillesSp.has(t.cle),
        t.avertissement ? ` <small class="options-avert">(${esc(avert(t.avertissement))})</small>` : "")).join("")}
      </div>
      <div class="domaines-choix" style="margin-top:8px;">
        <label class="domaine-case domaine-case--petit">
          <input type="checkbox" data-taille-inconnue-sp ${rech.taille_inconnue_spontanees !== false ? "checked" : ""}>
          <span>Garder les entreprises dont l'effectif est inconnu</span>
        </label>
      </div>
    </div>
    ${mode === "job" ? `
    <div class="options-bloc">
      <span class="field__label">Thèmes <span style="opacity:.6;font-weight:400;">(optionnel)</span></span>
      <p class="profil-card__sub" style="margin:4px 0 10px;">Renseignés volontairement par l'employeur : cocher un thème écarte les offres qui ne l'ont pas.</p>
      <div class="domaines-choix">${o.themes.map(t => caseOption("data-theme-case", t.code, t.libelle, themes.has(t.code))).join("")}</div>
    </div>` : ""}
    <div class="options-bloc">
      <span class="field__label">Départements des candidatures spontanées</span>
      <p class="profil-card__sub" style="margin:4px 0 10px;">Entreprises cherchées sur Sirene. Rien de coché : toute l'Île-de-France.</p>
      <div class="domaines-choix">${o.departements.map(d => caseOption("data-departement-case", d.code, `${d.code} · ${d.libelle}`, departements.has(d.code))).join("")}</div>
    </div>
    <div class="options-bloc" data-bloc-tous-secteurs>
      <span class="field__label">Candidatures spontanées : tous les secteurs</span>
      <div class="domaines-choix" style="margin-top:8px;">
        <label class="domaine-case domaine-case--petit">
          <input type="checkbox" data-tous-secteurs ${rech.tous_secteurs === true ? "checked" : ""}>
          <span>Chercher dans tous les secteurs <small class="options-avert">(${esc(o.volume_tous_secteurs)})</small></span>
        </label>
      </div>
      <p class="profil-card__sub" style="margin:8px 0 10px;">Sans filtre d'activité : Sirene renvoie les entreprises des départements et tailles choisis, sans lien avec tes domaines, après celles de tes domaines et secteurs. La limite de « Récupérer » s'applique toujours.</p>
      <p class="domaines-vide" data-sp-rien hidden></p>
    </div>
    <details class="options-bloc" ${secteurs.size ? "open" : ""}>
      <summary class="field__label options-resume">Secteur de l'employeur <span style="opacity:.6;font-weight:400;">(optionnel${secteurs.size ? `, ${secteurs.size} choisi${secteurs.size > 1 ? "s" : ""}` : ""})</span></summary>
      <p class="profil-card__sub" style="margin:4px 0 10px;">Le secteur est l'activité de l'entreprise, pas le métier.${avecOffres ? " Offres : rien de coché, tous les secteurs." : ""} Candidatures spontanées : ces secteurs servent à chercher les entreprises sur Sirene quand aucun domaine n'est choisi, ou pour un domaine sans correspondance NAF (seuls l'informatique et l'immobilier en ont une).</p>
      <div class="secteurs-liste">${o.secteurs.map(s => caseOption("data-secteur-case", s.code, `${s.code} · ${s.libelle}`, secteurs.has(s.code))).join("")}</div>
    </details>`;
  c.dataset.charge = "1";
  _options = o;
  majMessageSpontanees(mode);
  c.querySelectorAll(".domaine-case").forEach(l => l.classList.toggle("is-checked", l.querySelector("input").checked));
  if (c.dataset.branche) return;
  c.dataset.branche = "1";
  c.addEventListener("change", e => {
    const l = e.target.closest(".domaine-case");
    if (l) l.classList.toggle("is-checked", e.target.checked);
  });
}

function lireOptions(mode) {
  const c = document.querySelector(`[data-options-recherche="${mode}"]`);
  if (!c || !c.dataset.charge) return {};   // options non chargées : on n'écrase rien
  const coches = attribut => [...c.querySelectorAll(`[${attribut}]:checked`)].map(i => i.value);
  const out = { secteurs: coches("data-secteur-case"),
                tous_secteurs: !!c.querySelector("[data-tous-secteurs]")?.checked };
  if (c.querySelector("[data-taille-inconnue]")) {
    out.tailles = coches("data-taille-case");
    out.taille_inconnue = c.querySelector("[data-taille-inconnue]").checked;
  }
  if (mode === "job") out.themes = coches("data-theme-case");
  if (c.querySelector("[data-taille-inconnue-sp]")) {   // toujours là depuis D75
    out.departements = coches("data-departement-case");
    out.tailles_spontanees = coches("data-taille-sp-case");
    out.taille_inconnue_spontanees = c.querySelector("[data-taille-inconnue-sp]").checked;
  }
  return out;
}

/* ── Candidatures spontanées : ce que « Récupérer » cherchera sur Sirene.
   Même règle que le serveur (shared/naf.py, avertissement_sirene) : rien
   sans domaine, secteur ni « tous les secteurs » ; un domaine sans
   correspondance NAF demande des secteurs ou « tous les secteurs ». ── */
let _options = null;

function majMessageSpontanees(mode) {
  const c = document.querySelector(`[data-options-recherche="${mode}"]`);
  const el = c?.querySelector("[data-sp-rien]");
  if (!el || !_options) return;
  const tous = !!c.querySelector("[data-tous-secteurs]")?.checked;
  const secteurs = c.querySelectorAll(".secteurs-liste input:checked").length;
  const conteneur = document.querySelector(DOMAINES_DU_MODE[mode] || DOMAINES_DU_MODE.alternance);
  const domaines = lireDomainesCoches(DOMAINES_DU_MODE[mode] || DOMAINES_DU_MODE.alternance);
  const couverts = new Set(_options.domaines_naf || []);
  const sousDomaines = lettre => [...(conteneur?.querySelectorAll(`.gd[data-gd="${lettre}"] [data-domaine-case]`) || [])]
    .map(i => i.value);
  const manquants = domaines.filter(code => code.length === 1
    ? sousDomaines(code).some(d => !couverts.has(d)) : !couverts.has(code));
  let texte = "";
  if (!tous && !domaines.length && !secteurs) texte = _options.message_rien_a_chercher;
  else if (!tous && manquants.length && !secteurs) {
    texte = `Domaines sans correspondance avec les secteurs de Sirene (${manquants.join(", ")}) : ils ne seront `
      + "pas cherchés pour les candidatures spontanées. Choisis des secteurs d'entreprise, ou coche « tous les secteurs ».";
  }
  el.textContent = texte;
  el.hidden = !texte;
}

/* ── Durée du stage : même règle que le serveur (shared/stage.py), jours
   du premier au dernier compris, divisés par 7, arrondis à la semaine la
   plus proche, au moins 1 ── */
function dureeSemaines(debut, fin) {
  if (!debut || !fin) return null;
  const jours = Math.round((Date.parse(fin) - Date.parse(debut)) / 86400000) + 1;
  if (Number.isNaN(jours) || jours < 1) return null;
  return Math.max(1, Math.floor((jours + 3) / 7));
}

function majDureeStage() {
  const el = document.querySelector("[data-duree-stage]");
  if (!el) return;
  const debut = document.querySelector('[data-profil="date_debut"]')?.value;
  const fin = document.querySelector('[data-profil="date_fin"]')?.value;
  const n = dureeSemaines(debut, fin);
  el.textContent = n ? `Durée : ${n} semaine${n > 1 ? "s" : ""} (balise {duree_semaines}).`
    : debut && fin ? "La date de fin est antérieure à la date de début."
    : "Durée : renseigne les deux dates.";
}

/* ── Affichage des sections selon le mode (alternance/job/stage) ────────── */
async function appliquerModeProfil() {
  let mode = "alternance";
  try { mode = (await api.mode()).mode || "alternance"; } catch (_) {}
  _modeProfilCourant = mode;
  document.querySelectorAll("[data-mode-section]").forEach(sec => {
    const m = sec.dataset.modeSection;
    sec.style.display = (m === "commun" || m === mode) ? "" : "none";
  });
  return mode;
}

/* Un champ est-il dans une section visible (pas masquée par le mode) ? */
function _champVisible(el) {
  const section = el.closest("[data-mode-section]");
  if (!section) return true;                 // hors section mode = toujours visible
  return section.style.display !== "none";   // visible si la section n'est pas masquée
}

export const Profil = {
  _charge: false,

  async charger() {
    const mode = await appliquerModeProfil();
    let p;
    try { p = await api.profil(); } catch (_) { return; }

    document.querySelectorAll("[data-profil]").forEach(el => {
      if (!_champVisible(el)) return;        // ignore les doublons masqués
      el.value = p[el.dataset.profil] ?? "";
    });

    _tags["competences"] = Array.isArray(p.competences) ? [...p.competences] : [];
    rendreTags("competences");

    _projets = Array.isArray(p.projets) ? p.projets.map(x => ({ nom: x.nom || "", url: x.url || "", description: x.description || "" })) : [];
    rendreProjets();

    // Critères de recherche
    const rech = p.recherche || {};
    document.querySelectorAll("[data-rech]").forEach(el => {
      if (!_champVisible(el)) return;        // ignore les doublons masqués
      // Champs en lecture seule : on garde leur valeur par défaut si le profil est vide
      const val = rech[el.dataset.rech];
      if (el.hasAttribute("readonly")) {
        if (val) el.value = val;          // garde le défaut HTML si vide
      } else {
        el.value = val ?? "";
      }
    });
    const domainesSel = Array.isArray(rech.domaines) ? rech.domaines : [];
    await rendreDomaines(domainesSel, DOMAINES_DU_MODE[mode] || DOMAINES_DU_MODE.alternance);
    await rendreOptions(rech, mode);
    majDureeStage();

    rendrePiecesJointes(p.pieces_jointes || []);
    CompteEnvoi.charger();

    if (!this._charge) {
      document.querySelectorAll("[data-stage-date]").forEach(el => el.addEventListener("input", majDureeStage));
      // Domaines, secteurs, « tous les secteurs » : message des spontanées à jour
      document.querySelector('[data-page-content="profil"]')?.addEventListener("change", () =>
        majMessageSpontanees(_modeProfilCourant));
      brancherTags("competences");
      brancherProjets();
      brancherPiecesJointes();
      this._charge = true;
    }
  },

  async sauvegarder() {
    const data = {};
    document.querySelectorAll("[data-profil]").forEach(el => {
      if (!_champVisible(el)) return;        // ignore les doublons masqués (évite d'écraser)
      data[el.dataset.profil] = el.value;
    });

    // Validation de la lettre type : placeholders autorisés uniquement
    const lettre = data.lettre_type || "";
    if (lettre.trim()) {
      const erreur = validerLettre(lettre);
      if (erreur) { alert("Lettre type : " + erreur); return false; }
    }
    data.competences = _tags["competences"] || [];
    lireProjetsDepuisDOM();
    data.projets = _projets.filter(p => p.nom || p.url || p.description);

    // Reconstruire l'objet recherche
    const rech = {};
    document.querySelectorAll("[data-rech]").forEach(el => {
      if (!_champVisible(el)) return;        // ignore les doublons masqués (évite d'écraser)
      rech[el.dataset.rech] = el.value;
    });
    rech.domaines = lireDomainesCoches(DOMAINES_DU_MODE[_modeProfilCourant] || DOMAINES_DU_MODE.alternance);
    Object.assign(rech, lireOptions(_modeProfilCourant));
    data.recherche = rech;

    try {
      return (await api.sauverProfil(data)).ok === true;
    } catch (e) {
      // Refus du serveur (date illisible, balise inconnue...) : message lisible
      if (e.message) alert(e.message);
      return false;
    }
  },
};

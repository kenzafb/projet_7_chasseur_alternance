/* ============================================================================
   profil.js — gestion du formulaire profil utilisateur
   - champs simples : [data-profil="..."]
   - tags : [data-tags="..."] + [data-tags-input="..."]
   - projets : [data-projets] (liste de cartes nom/url/description)
   ============================================================================ */

import { api } from "./api.js";
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
        <a class="pj-item__link" href="/api/profil/piece?nom=${encodeURIComponent(pj.nom)}" target="_blank">Voir</a>
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
}

function lireDomainesCoches(selecteur = "[data-domaines-choix]") {
  const c = document.querySelector(selecteur);
  if (!c || c.querySelector("[data-domaine-indifferent]")?.checked) return [];
  const lettres = [...c.querySelectorAll("[data-gd-case]:checked")].map(i => i.value);
  const domaines = [...c.querySelectorAll("[data-domaine-case]:checked")].map(i => i.value)
    .filter(code => !lettres.includes(code[0]));
  return [...lettres, ...domaines];
}

/* ── Affichage des sections selon le mode (alternance/job) ─────────────── */
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
    if (mode === "job") {
      await rendreDomaines(domainesSel, "[data-domaines-choix-job]");
    } else {
      await rendreDomaines(domainesSel, "[data-domaines-choix]");
    }

    rendrePiecesJointes(p.pieces_jointes || []);
    CompteEnvoi.charger();

    if (!this._charge) {
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
    rech.domaines = lireDomainesCoches(
      _modeProfilCourant === "job" ? "[data-domaines-choix-job]" : "[data-domaines-choix]"
    );
    data.recherche = rech;

    try {
      return (await api.sauverProfil(data)).ok === true;
    } catch (_) { return false; }
  },
};

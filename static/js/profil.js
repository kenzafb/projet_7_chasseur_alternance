/* ============================================================================
   profil.js — gestion du formulaire profil utilisateur
   - champs simples : [data-profil="..."]
   - tags : [data-tags="..."] + [data-tags-input="..."]
   - projets : [data-projets] (liste de cartes nom/url/description)
   ============================================================================ */

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
          <input class="field__input" data-pj="${i}:nom" type="text" value="${echap(p.nom)}" placeholder="Grabber"></label>
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
  const r = await fetch("/api/profil");
  if (!r.ok) return;
  const p = await r.json();
  rendrePiecesJointes(p.pieces_jointes || []);
}

function brancherPiecesJointes() {
  const fileInput = document.querySelector("[data-pj-file]");
  const fname = document.querySelector("[data-pj-fname]");
  const btnUp = document.querySelector("[data-pj-upload]");
  const nomInput = document.querySelector("[data-pj-nom]");
  const liste = document.querySelector("[data-pj-list]");

  if (fileInput) fileInput.addEventListener("change", () => {
    fname.textContent = fileInput.files[0] ? fileInput.files[0].name : "Aucun fichier";
  });

  if (btnUp) btnUp.addEventListener("click", async () => {
    const fichier = fileInput.files[0];
    if (!fichier) { alert("Choisis un fichier PDF."); return; }
    const fd = new FormData();
    fd.append("fichier", fichier);
    const r = await fetch("/api/profil/upload", { method: "POST", body: fd });
    const res = await r.json();
    if (res.ok) {
      fileInput.value = ""; fname.textContent = "Aucun fichier";
      await rafraichirPiecesJointes();
    } else {
      alert(res.erreur || "Erreur lors du téléversement");
    }
  });

  if (liste) liste.addEventListener("click", async e => {
    const nom = e.target.dataset.pjRm;
    if (nom && confirm(`Supprimer la pièce « ${nom} » ?`)) {
      await fetch("/api/profil/piece/supprimer", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ nom }),
      });
      await rafraichirPiecesJointes();
    }
  });
}

/* ── Domaines recherchés (cases à cocher) ──────────────────────────────── */
async function rendreDomaines(selectionnes, selecteur = "[data-domaines-choix]") {
  const c = document.querySelector(selecteur);
  if (!c) return;
  let dispo = [];
  try {
    const r = await fetch("/api/domaines");
    dispo = await r.json();
  } catch (_) { dispo = []; }
  c.innerHTML = "";
  dispo.forEach(d => {
    const checked = selectionnes.includes(d.cle);
    const label = document.createElement("label");
    label.className = "domaine-case" + (checked ? " is-checked" : "");
    label.innerHTML = `<input type="checkbox" value="${d.cle}"${checked ? " checked" : ""}><span>${d.label}</span>`;
    label.querySelector("input").addEventListener("change", e => {
      label.classList.toggle("is-checked", e.target.checked);
    });
    c.appendChild(label);
  });
}

function lireDomainesCoches(selecteur = "[data-domaines-choix]") {
  return [...document.querySelectorAll(selecteur + " input:checked")].map(i => i.value);
}

/* ── Affichage des sections selon le mode (alternance/job) ─────────────── */
async function appliquerModeProfil() {
  let mode = "alternance";
  try {
    const r = await fetch("/api/mode");
    const d = await r.json();
    mode = d.mode || "alternance";
  } catch (_) {}
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
    const r = await fetch("/api/profil");
    if (!r.ok) return;
    const p = await r.json();

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

    const r = await fetch("/api/profil", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    return (await r.json()).ok === true;
  },
};

/* ============================================================================
   copie_profil.js — « Copier depuis un autre mode » sur la page Profil (D119)
   1. mode source  2. sections copiables  3. aperçu actuel / copié, avec une
   confirmation explicite pour chaque section déjà remplie ici  4. copie.
   Le serveur refait toutes les vérifications (D117) : la fenêtre ne fait que
   les montrer.
   ============================================================================ */

import { api, MODE } from "./api.js";

const NOMS_MODES = { alternance: "Alternance", job: "Job", stage: "Stage" };

const $ = sel => document.querySelector(sel);

function esc(s) {
  return String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

/* Valeur d'un champ en texte lisible */
function texte(champ, v) {
  if (champ === "competences") return (v || []).join(", ");
  if (champ === "projets") return (v || []).map(p => [p.nom, p.url, p.description].filter(Boolean).join(" · ")).join("\n");
  if (champ === "pieces_jointes") return (v || []).map(p => p.nom).join("\n");
  return v || "";
}

function cellule(champ, v, titre) {
  const t = texte(champ, v);
  return `<div><span class="copie__mobile">${titre}</span>${t ? esc(t) : '<span class="copie__neant">vide</span>'}</div>`;
}

const etat = { source: null, apercu: [], modeCible: MODE };

function erreur(msg) {
  const el = $("[data-copie-erreur]");
  el.textContent = msg || "";
  el.hidden = !msg;
}

function sectionsCochees() {
  return [...document.querySelectorAll("[data-copie-section]:checked")].map(el => el.value);
}

/* « Copier » : au moins une section copiable, et chaque section remplie ici confirmée */
function majValider() {
  const copiables = etat.apercu.filter(s => !s.erreur);
  const nonConfirmees = copiables.filter(s => s.a_confirmer && !document.querySelector(`[data-copie-ecraser="${s.cle}"]`)?.checked);
  $("[data-copie-valider]").disabled = !copiables.length || nonConfirmees.length > 0;
  $("[data-copie-etat]").textContent = nonConfirmees.length
    ? `À confirmer avant de copier : ${nonConfirmees.map(s => s.libelle).join(", ")}`
    : "";
}

function viderApercu() {
  etat.apercu = [];
  $("[data-copie-etape-apercu]").hidden = true;
  $("[data-copie-apercu-liste]").innerHTML = "";
  majValider();
}

async function choisirSource(source) {
  etat.source = source;
  erreur("");
  viderApercu();
  let r;
  try { r = await api.copieSections(source); } catch (e) { erreur(e.message); return; }
  $("[data-copie-etape-sections]").hidden = false;
  $("[data-copie-source-vide]").hidden = r.source_existe;
  $("[data-copie-sections]").innerHTML = r.source_existe ? r.sections.map(s => `
    <label><input type="checkbox" value="${esc(s.cle)}" data-copie-section> ${esc(s.libelle)}</label>`).join("") : "";
  $("[data-copie-apercu]").disabled = true;
}

function rendreApercu() {
  const cible = NOMS_MODES[etat.modeCible] || etat.modeCible;
  const source = NOMS_MODES[etat.source] || etat.source;
  $("[data-copie-apercu-liste]").innerHTML = etat.apercu.map(s => {
    const classe = s.erreur ? "copie__section--erreur" : s.a_confirmer ? "copie__section--confirmer" : "";
    const badge = s.erreur ? '<span class="copie__badge copie__badge--erreur">copie impossible</span>'
      : s.a_confirmer ? '<span class="copie__badge copie__badge--confirmer">déjà rempli ici : sera écrasé</span>'
      : s.identique ? '<span class="copie__badge">identique : rien ne change</span>'
      : '<span class="copie__badge">vide ici</span>';
    const lignes = s.champs.map(c => `
      <div class="copie__champ">${esc(c.libelle)}</div>
      ${cellule(c.champ, c.actuel, `Actuel (${esc(cible)})`)}
      ${cellule(c.champ, c.copie, `Copié (${esc(source)})`)}`).join("");
    const pied = s.erreur ? `<div class="copie__message copie__badge--erreur">${esc(s.erreur)} Cette section ne sera pas copiée.</div>`
      : s.a_confirmer ? `<label class="copie__confirmer"><input type="checkbox" data-copie-ecraser="${esc(s.cle)}">
          Remplacer ce qui est rempli ici par la valeur copiée${s.vide ? " (vide)" : ""}</label>`
      : "";
    return `<div class="copie__section ${classe}">
      <div class="copie__titre"><span>${esc(s.libelle)}</span>${badge}</div>
      <div class="copie__grille">
        <div class="copie__entete">Champ</div>
        <div class="copie__entete">Actuel (${esc(cible)})</div>
        <div class="copie__entete">Copié depuis ${esc(source)}</div>
        ${lignes}
      </div>${pied}</div>`;
  }).join("");
  $("[data-copie-etape-apercu]").hidden = false;
  majValider();
}

async function voirApercu() {
  erreur("");
  try { etat.apercu = (await api.copieApercu(etat.source, sectionsCochees())).sections; }
  catch (e) { erreur(e.message); return; }
  rendreApercu();
}

async function valider(apresCopie) {
  const sections = etat.apercu.filter(s => !s.erreur).map(s => s.cle);
  const ecraser = [...document.querySelectorAll("[data-copie-ecraser]:checked")].map(el => el.dataset.copieEcraser);
  $("[data-copie-valider]").disabled = true;
  erreur("");
  try {
    await api.copierProfil(etat.source, sections, ecraser);
  } catch (e) {
    erreur(e.message);
    majValider();
    return;
  }
  fermer();
  await apresCopie(etat.apercu.filter(s => !s.erreur).map(s => s.libelle));
}

function ouvrir() {
  etat.source = null;
  erreur("");
  viderApercu();
  $("[data-copie-etape-sections]").hidden = true;
  $("[data-copie-sources]").innerHTML = Object.entries(NOMS_MODES).filter(([cle]) => cle !== etat.modeCible)
    .map(([cle, nom]) => `<label><input type="radio" name="copie-source" value="${cle}" data-copie-source> ${nom}</label>`)
    .join("");
  $("[data-copie-modal]").classList.add("is-open");
}

function fermer() {
  $("[data-copie-modal]").classList.remove("is-open");
}

export const CopieProfil = {
  _branche: false,
  /* apresCopie(libelles) : recharge le profil et affiche ce qui a été copié */
  brancher(modeCible, apresCopie) {
    etat.modeCible = modeCible || MODE;
    if (this._branche) return;
    this._branche = true;
    $("[data-copie-ouvrir]")?.addEventListener("click", ouvrir);
    $("[data-copie-fermer]")?.addEventListener("click", fermer);
    const modal = $("[data-copie-modal]");
    modal?.addEventListener("change", e => {
      if (e.target.matches("[data-copie-source]")) choisirSource(e.target.value);
      else if (e.target.matches("[data-copie-section]")) {
        $("[data-copie-apercu]").disabled = sectionsCochees().length === 0;
        viderApercu();                       // aperçu à refaire pour la nouvelle sélection
      } else if (e.target.matches("[data-copie-ecraser]")) majValider();
    });
    $("[data-copie-apercu]")?.addEventListener("click", voirApercu);
    $("[data-copie-valider]")?.addEventListener("click", () => valider(apresCopie));
  },
};

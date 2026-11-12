/* ============================================================================
   offres.js — page Offres : liste à gauche, volet de détail à droite (D145)
   Onglets À voir, Gardées, Écartées ; une offre jamais ouverte est en gras
   avec un point vert, et devient « vue » à l'ouverture. Sur téléphone, la
   liste puis le détail en plein écran.
   ============================================================================ */
import { api, esc, lienSur } from "./api.js";

// ANALYSE_IA=false (attribut posé par le serveur) : ni notation ni lettre automatique
const IA_ACTIVE = document.documentElement.dataset.analyseIa !== "non";
const NON_ANALYSEE = "non_analysee";
// Offre où la personne a postulé (D105) : suivie dans Candidatures seulement (D110)
const POSTULEE = ["envoye", "a_relancer", "relancee", "reponse", "entretien", "refus", "acceptee"];
const estPostulee = o => POSTULEE.includes(o.statut);
const aujourdhui = () => new Date().toLocaleDateString("sv-SE");   // AAAA-MM-JJ, jour local

/* Raisons d'un écartement par le Chasseur (« manuel » : écartée par toi) */
const RAISONS_CHASSEUR = {
  ineligible: "conditions non remplies", note_basse: "note trop basse", hors_domaine: "hors de tes domaines",
  ecole_cfa: "école ou CFA", public_specifique: "réservée à un public", stage: "pas un stage",
};

let cache = [];                  // offres chargées
let erreurChargement = "";       // échec du chargement : affiché à la place de la liste (D133)
let onglet = "avoir";            // avoir | garde | ecarte
let choisie = null;              // id de l'offre ouverte dans le volet
let messageVolet = "";           // confirmation affichée dans le volet (J'ai postulé...)
let filtres = { source: "all", zone: "all", score: "all", ecartees: "all" };
let ouvrirLettre = () => {};

/* Onglet d'une offre : postulées ailleurs (Candidatures), sinon À voir,
   Gardées ou Écartées */
function ongletDe(o) {
  if (estPostulee(o)) return null;
  if (o.statut === "archive") return "ecarte";
  if (o.statut === "gardee") return "garde";
  return "avoir";
}

/* Note : 6 et plus vert (Bien), 4 et 5 ambre (Moyen), moins de 4 neutre
   (Faible), toujours avec un mot (DESIGN.md) */
function ton(o) {
  if (o.verdict === NON_ANALYSEE) return { classe: "attente", mot: "Pas notée", verdict: "Pas encore notée par le Chasseur" };
  const n = o.score ?? 0;
  if (n >= 6) return { classe: "bien", mot: "Bien", verdict: "Correspond assez bien à ton profil" };
  if (n >= 4) return { classe: "moyen", mot: "Moyen", verdict: "Correspond en partie à ton profil" };
  return { classe: "faible", mot: "Faible", verdict: "Correspond peu à ton profil" };
}

/* « il y a 3 jours », « il y a 6 semaines » d'après la date de découverte */
function depuis(texte) {
  if (!texte) return "";
  const jours = Math.floor((Date.now() - Date.parse(texte)) / 86400000);
  if (Number.isNaN(jours) || jours < 0) return "";
  if (jours === 0) return "aujourd'hui";
  if (jours === 1) return "hier";
  if (jours < 14) return `il y a ${jours} jours`;
  if (jours < 60) return `il y a ${Math.floor(jours / 7)} semaines`;
  return `il y a ${Math.floor(jours / 30)} mois`;
}

/* Motif d'inéligibilité : raisons établies en Python, en tête des points
   faibles (« Inéligible : ... ») ; l'IA n'en décide jamais (D99) */
const PREFIXE_INELIGIBLE = "Inéligible : ";
const motifIneligible = o => (o.points_faibles || []).filter(p => p.startsWith(PREFIXE_INELIGIBLE))
  .map(p => p.slice(PREFIXE_INELIGIBLE.length)).join(" ; ");

function passeFiltres(o) {
  const estLba = (o.source || "").toLowerCase().includes("bonne");
  if (filtres.source === "ft" && estLba) return false;
  if (filtres.source === "lba" && !estLba) return false;
  if (filtres.zone !== "all" && (o.zone || "") !== filtres.zone) return false;
  if (filtres.score !== "all") {
    if (o.verdict === NON_ANALYSEE) return false;
    const n = o.score ?? 0;
    if (filtres.score === "haut" && n < 6) return false;
    if (filtres.score === "moyen" && (n < 4 || n > 5)) return false;
    if (filtres.score === "bas" && n >= 4) return false;
  }
  if (onglet === "ecarte" && filtres.ecartees !== "all") {
    const raison = o.raison_archivage || "manuel";
    if (filtres.ecartees === "toi") return raison === "manuel";
    if (filtres.ecartees === "chasseur") return raison !== "manuel";
    return raison === filtres.ecartees;
  }
  return true;
}

/* Les mieux notées en haut, les offres pas encore notées à la fin */
const trier = (a, b) => (a.verdict === NON_ANALYSEE) - (b.verdict === NON_ANALYSEE)
  || (b.score ?? 0) - (a.score ?? 0);

const MESSAGES_VIDES = {
  avoir: "Tu as tout trié. Cherche de nouvelles offres quand tu veux.",
  garde: "Aucune offre gardée pour l'instant.",
  ecarte: "Aucune offre écartée.",
};

function ligne(o) {
  const t = ton(o);
  const nonVue = !o.vue && onglet === "avoir";
  const lieu = [o.lieu || o.zone, depuis(o.date_trouvee)].filter(Boolean).join(" · ");
  const recherche = `${o.titre || ""} ${o.entreprise || ""} ${o.lieu || o.zone || ""}`.toLowerCase();
  return `<li class="offres__item" data-id="${esc(o.id)}" data-search-text="${esc(recherche)}">
    <button type="button" class="offre-ligne${nonVue ? " offre-ligne--nouvelle" : ""}" data-ouvrir
            ${o.id === choisie ? 'aria-current="true"' : ""}>
      <span class="note note--${t.classe}" aria-hidden="true">${o.verdict === NON_ANALYSEE ? "?" : esc(o.score ?? 0)}</span>
      <span class="offre-ligne__txt">
        <span class="offre-ligne__titre">${esc(o.titre || "Offre sans titre")}</span>
        <span class="offre-ligne__lieu">${esc(lieu)}</span>
        <span class="visuellement-cache">${o.verdict === NON_ANALYSEE ? "Pas encore notée"
          : `Notée ${esc(o.score ?? 0)} sur 10, ${t.mot.toLowerCase()}`}${nonVue ? ", pas encore vue" : ""}</span>
      </span>
      ${nonVue ? '<span class="offre-ligne__point" aria-hidden="true"></span>' : ""}
    </button>
  </li>`;
}

function listeVisible() {
  return cache.filter(o => ongletDe(o) === onglet && passeFiltres(o)).sort(trier);
}

function rendreListe() {
  const el = document.querySelector('[data-list="offres"]');
  const vide = document.querySelector("[data-offres-vide]");
  if (erreurChargement) {
    el.innerHTML = "";
    vide.textContent = `Offres non chargées : ${erreurChargement}. Recharge la page.`;
    vide.hidden = false;
    return;
  }
  const liste = listeVisible();
  el.innerHTML = liste.map(ligne).join("");
  const filtre = Object.entries(filtres).some(([k, v]) => v !== "all" && (k !== "ecartees" || onglet === "ecarte"));
  vide.textContent = filtre && cache.some(o => ongletDe(o) === onglet)
    ? "Aucune offre avec ces filtres." : MESSAGES_VIDES[onglet];
  vide.hidden = liste.length > 0;
  // Nombre d'offres de chaque onglet, et onglet choisi
  for (const k of ["avoir", "garde", "ecarte"]) {
    document.querySelector(`[data-onglet-nombre="${k}"]`).textContent = cache.filter(o => ongletDe(o) === k).length;
    document.querySelector(`[data-onglet="${k}"]`).setAttribute("aria-pressed", String(k === onglet));
  }
  document.querySelector("[data-filtre-ecartees]").hidden = onglet !== "ecarte";
}

function liste(points, vide, genre) {
  return points.length ? `<ul class="volet__points volet__points--${genre}">${points.map(p => `<li>${esc(p)}</li>`).join("")}</ul>`
    : `<p class="volet__rien">${vide}</p>`;
}

function rendreVolet() {
  const contenu = document.querySelector("[data-volet-contenu]");
  const o = cache.find(x => x.id === choisie && ongletDe(x) === onglet);
  document.querySelector("[data-offres-liste]").classList.toggle("is-cachee-mobile", !!o);
  document.querySelector("[data-volet]").classList.toggle("is-ouvert-mobile", !!o);
  document.querySelector("[data-volet-retour]").hidden = !o;
  if (!o) {
    contenu.innerHTML = `<p class="volet__vide">${messageVolet ? `${esc(messageVolet)} ` : ""}Choisis une offre dans la liste pour la lire ici.</p>`;
    return;
  }
  const t = ton(o);
  const nonNotee = o.verdict === NON_ANALYSEE;
  const motif = motifIneligible(o);
  const colle = (o.points_forts || []);
  const coince = (o.points_faibles || []).filter(p => !p.startsWith(PREFIXE_INELIGIBLE));
  const resume = o.resume_analyse || (o.description || "").slice(0, 600) + ((o.description || "").length > 600 ? "…" : "");
  const raison = o.raison_archivage || "manuel";
  const lien = lienSur(o.lien);
  const garder = o.statut === "gardee" ? "Remettre dans À voir" : "Garder pour plus tard";
  const ecarter = o.statut === "archive" ? "Remettre dans À voir" : "Pas pour moi";

  contenu.innerHTML = `
    <p class="volet__qui">${esc([o.entreprise || "Entreprise non communiquée", o.lieu || o.zone].filter(Boolean).join(" · "))}</p>
    <h2 class="volet__titre" id="volet-titre" tabindex="-1">${esc(o.titre || "Offre sans titre")}</h2>

    <div class="verdict verdict--${t.classe}">
      ${nonNotee ? "" : `<span class="verdict__note">${esc(o.score ?? 0)}<small>/10</small></span>`}
      <span class="verdict__txt"><strong>${esc(t.mot)}</strong> · ${esc(t.verdict)}</span>
      ${nonNotee && IA_ACTIVE ? '<button type="button" class="btn btn--sm" data-act="analyser">Noter cette offre</button>' : ""}
    </div>
    ${motif ? `<p class="volet__alerte">Conditions non remplies : ${esc(motif)}</p>`
      : nonNotee ? "" : '<p class="volet__ok">Tu remplis les conditions vérifiées par le Chasseur.</p>'}
    ${o.statut === "archive" ? `<p class="volet__ecartee">${raison === "manuel" ? "Écartée par toi."
      : `Écartée par le Chasseur : ${esc(RAISONS_CHASSEUR[raison] || raison)}.`}</p>` : ""}

    ${nonNotee ? "" : `
    <div class="volet__colonnes">
      <section><h3 class="volet__h3">Ce qui colle</h3>${liste(colle, "Rien de particulier.", "colle")}</section>
      <section><h3 class="volet__h3">Ce qui coince</h3>${liste(coince, "Rien de particulier.", "coince")}</section>
    </div>`}
    ${resume.trim() ? `<section><h3 class="volet__h3">L'offre en bref</h3><p class="volet__resume">${esc(resume)}</p></section>` : ""}
    <p class="volet__liens">
      ${lien ? `<a href="${esc(lien)}" target="_blank" rel="noopener">Lire l'annonce complète<span class="visuellement-cache"> (nouvel onglet)</span></a>` : ""}
      ${o.page_lba ? `<a href="${esc(o.page_lba)}" target="_blank" rel="noopener">Postuler sur La Bonne Alternance<span class="visuellement-cache"> (nouvel onglet)</span></a>` : ""}
    </p>

    <p class="volet__message" role="status" data-volet-message>${esc(messageVolet)}</p>
    <div class="volet__actions">
      <button type="button" class="btn btn--primary" data-act="lettre">${o.lettre ? "Voir ma lettre" : "Préparer ma lettre"}</button>
      <span class="volet__postuler">
        <button type="button" class="btn" data-act="postuler">J'ai postulé</button>
        <label class="volet__date"><span>le</span>
          <input type="date" data-postuler-date value="${aujourdhui()}" max="${aujourdhui()}" aria-label="Date de candidature"></label>
      </span>
      ${o.statut === "archive" ? "" : `<button type="button" class="btn" data-act="garder">${garder}</button>`}
      ${o.statut === "gardee" ? "" : `<button type="button" class="btn btn--ghost volet__ecarter" data-act="ecarter">${ecarter}</button>`}
    </div>
    ${!IA_ACTIVE && !o.lettre ? '<p class="volet__note">IA désactivée : tu écriras toi-même le paragraphe personnalisé.</p>' : ""}
    ${!nonNotee && IA_ACTIVE ? '<p class="volet__secondaire"><button type="button" class="lien-bouton" data-act="analyser">Faire noter à nouveau cette offre</button></p>' : ""}`;
}

function rendre() {
  rendreListe();
  rendreVolet();
}

/* Compteur du menu : offres à voir pas encore ouvertes ; bandeau des offres
   à noter */
function rendreCompteurs() {
  const nonVues = cache.filter(o => ongletDe(o) === "avoir" && !o.vue).length;
  const c = document.querySelector('[data-count="offres"]');
  if (c) {
    c.textContent = nonVues;
    c.hidden = !nonVues;
    c.setAttribute("aria-label", `${nonVues} pas encore vue${nonVues > 1 ? "s" : ""}`);
  }
  rendreAttente();
}

/* Offres à noter (pas encore analysées, ni écartées ni postulées) */
function rendreAttente() {
  const bandeau = document.querySelector("[data-analyse-attente]");
  if (!bandeau) return;
  const n = cache.filter(o => o.verdict === NON_ANALYSEE && o.statut !== "archive" && !estPostulee(o)).length;
  bandeau.hidden = !n;
  document.querySelector("[data-analyse-nombre]").textContent = n === 1 ? "1 nouvelle offre" : `${n} nouvelles offres`;
  document.querySelector("[data-analyse-pluriel]").textContent = n > 1 ? "s" : "";
  const champ = document.querySelector('[data-limite="analyses"]');
  if (champ && n) champ.max = Math.min(n, Number(champ.dataset.plafond ??= champ.max));
  const est = document.querySelector("[data-analyse-estimation]");
  if (est && n) {
    api.analyseStatut().then(s => {
      est.textContent = s.en_attente && s.estimation.texte ? `${s.estimation.texte[0].toUpperCase()}${s.estimation.texte.slice(1)} pour toutes.` : "";
    }, () => { est.textContent = ""; });
  }
}

/* Échec d'une action sur une offre : message, puis liste rechargée (D133) */
const echec = err => { alert(err.message); Offres.charger(); };

/* Ouvre une offre dans le volet ; jamais ouverte : marquée vue (D145) */
function ouvrir(id, { focus = true } = {}) {
  choisie = id;
  messageVolet = "";
  const o = cache.find(x => x.id === id);
  if (o && !o.vue) {
    o.vue = true;
    api.offreVue(id).catch(() => {});
    rendreCompteurs();
  }
  rendre();
  // Sur téléphone, le détail remplace la liste : le focus suit
  if (focus && matchMedia("(max-width: 900px)").matches) document.getElementById("volet-titre")?.focus();
}

/* Change l'onglet d'une offre, puis ouvre la suivante du même onglet */
async function deplacer(o, statutAppel, message) {
  const ordre = listeVisible().map(x => x.id);
  const suivante = ordre[ordre.indexOf(o.id) + 1] || ordre[ordre.indexOf(o.id) - 1] || null;
  try { await statutAppel(); } catch (e) { echec(e); return; }
  await Offres.charger();
  if (suivante) ouvrir(suivante, { focus: false });
  else { choisie = null; rendre(); }
  messageVolet = message;
  rendreVolet();
}

function agir(act, o, bouton) {
  if (act === "lettre") { ouvrirLettre(o.id); return; }
  if (act === "analyser") {
    bouton.disabled = true;
    bouton.textContent = "Notation en cours… (1 à 2 min)";
    api.analyser(o.id).then(() => Offres.charger(), err => { alert("Notation impossible : " + err.message); Offres.charger(); });
    return;
  }
  if (act === "postuler") {
    const date = document.querySelector("[data-postuler-date]")?.value;
    deplacer(o, () => api.postuler(o.id, { date }),
      "C'est noté : elle est dans tes Candidatures, avec cette date.")
      .then(() => document.dispatchEvent(new Event("candidatures:maj")));
    return;
  }
  // Retour dans À voir : « en cours » si une lettre est déjà prête
  const remettre = () => api.majStatut(o.id, o.lettre ? "en_cours" : "nouveau");
  if (act === "garder") {
    if (o.statut === "gardee") deplacer(o, remettre, "Remise dans À voir.");
    else deplacer(o, () => api.majStatut(o.id, "gardee"), "Gardée pour plus tard : elle t'attend dans Gardées.");
  }
  if (act === "ecarter") {
    if (o.statut === "archive") deplacer(o, () => api.desarchiver(o.id), "Remise dans À voir.");
    else deplacer(o, () => api.changerRaison(o.id, "manuel"), "Écartée : tu la retrouves dans Écartées.");
  }
}

export const Offres = {
  _branche: false,

  async charger() {
    try {
      cache = await api.candidatures();
      erreurChargement = "";
    } catch (e) {
      cache = [];
      erreurChargement = e.message || "erreur inconnue";
    }
    rendre();
    rendreCompteurs();
    this.brancher();
  },

  data: () => cache,

  /* Ouvre une offre depuis une autre page (Accueil : « Voir l'offre ») */
  montrer(id) {
    const o = cache.find(x => x.id === id);
    if (!o) return;
    onglet = ongletDe(o) || "avoir";
    ouvrir(id, { focus: false });
  },

  brancher(ouvrirLaLettre) {
    if (ouvrirLaLettre) ouvrirLettre = ouvrirLaLettre;
    if (this._branche) return;
    this._branche = true;
    document.querySelector('[data-list="offres"]').addEventListener("click", e => {
      const item = e.target.closest("[data-ouvrir]")?.closest("[data-id]");
      if (item) ouvrir(item.dataset.id);
    });
    document.querySelectorAll("[data-onglet]").forEach(b => b.addEventListener("click", () => {
      onglet = b.dataset.onglet;
      choisie = null;
      messageVolet = "";
      rendre();
    }));
    document.querySelectorAll("[data-foffre]").forEach(menu => menu.addEventListener("change", () => {
      filtres[menu.dataset.foffre] = menu.value;
      rendre();
    }));
    document.querySelector("[data-volet-contenu]").addEventListener("click", e => {
      const bouton = e.target.closest("[data-act]");
      const o = cache.find(x => x.id === choisie);
      if (bouton && o) agir(bouton.dataset.act, o, bouton);
    });
    // Téléphone : retour à la liste, le focus revient sur l'offre quittée
    document.querySelector("[data-volet-retour]").addEventListener("click", () => {
      const id = choisie;
      choisie = null;
      rendre();
      document.querySelector(`[data-id="${CSS.escape(id || "")}"] [data-ouvrir]`)?.focus();
    });
  },
};

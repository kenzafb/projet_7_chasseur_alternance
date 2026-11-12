/* ============================================================================
   app.js — orchestrateur de l'interface
   Navigation par ancres · tête de page contextuelle · menu du compte ·
   polling de l'état des pipelines. Tout le reste vit dans les modules dédiés.
   ============================================================================ */
import { api, limite, confirmerLancement, MODE } from "./api.js";
import { Accueil }       from "./accueil.js";
import { Lettre }        from "./lettre.js";
import { Offres }        from "./offres.js";
import { Candidatures }  from "./candidatures.js";
import { Spontanees }    from "./spontanees.js";
import { Profil }        from "./profil.js";
import { Parametres }    from "./parametres.js";

/* Ce que le mode cherche, pour les phrases de tête de page */
const CE_QUE_TU_CHERCHES = { alternance: "ton alternance", job: "ton job", stage: "ton stage" }[MODE] || "ta recherche";

/* Tête de chaque page : titre, phrase courte, action principale (D143) */
const TOPBAR = {
  accueil:      { title: "Accueil", action: null },   // la page a sa propre tête (salutation)
  lettre:       { title: "Ma lettre", action: null },  // sa barre : retour, enregistrer, PDF
  offres:       { title: "Offres", phrase: `Les offres trouvées pour ${CE_QUE_TU_CHERCHES}, les mieux notées en haut.`,
                  action: "Chercher de nouvelles offres", run: async () => {
    const demandee = limite("offres");
    confirmerLancement("offres", demandee, await api.recherche(demandee));
  } },
  candidatures: { title: "Candidatures",
                  phrase: "Où en est chaque candidature envoyée. Clique sur le bouton d'une carte pour la faire avancer.",
                  action: null },   // rechargée à chaque ouverture de la page
  spontanees:   { title: "Entreprises à contacter",
                  phrase: "Des entreprises de ton domaine qui ne publient pas forcément d'offre. "
                    + "Le Chasseur les trouve, cherche leur email et leur envoie ta candidature.",
                  action: null },   // chaque étape a son bouton
  profil:       { title: "Mon profil", phrase: "Ce que le Chasseur sait de toi pour noter les offres et écrire tes lettres.",
                  action: null },   // « Enregistrer » est sous la partie affichée
  parametres:   { title: "Paramètres", phrase: "Ton compte, l'envoi de tes mails et les réglages avancés de ce mode.",
                  action: null },   // chaque carte a ses boutons
};

let pageCourante = "accueil";
const PAGES_VALIDES = ["accueil", "offres", "candidatures", "spontanees", "profil", "parametres", "lettre"];

/* Page désignée par l'ancre de l'URL ; « spontanees-suivi » : ancienne page
   fondue dans le suivi unique (D107) ; inconnue : Accueil (D144) */
function pageDeLAncre() {
  const ancre = location.hash.replace("#", "");
  const page = ancre === "spontanees-suivi" ? "candidatures" : ancre;
  // Ma lettre sans offre ouverte (page rechargée) : retour aux offres
  if (page === "lettre" && !Lettre.id()) return "offres";
  return PAGES_VALIDES.includes(page) ? page : "accueil";
}

/* Clic dans le menu : nouvelle entrée d'historique (Précédent y revient),
   la page change par hashchange ; même page : rechargée sur place */
function naviguer(page) {
  if (location.hash === "#" + page) aller(page);
  else location.hash = page;
}

/* ── Navigation ──────────────────────────────────────────────────────────── */
function aller(page, { focus = false } = {}) {
  pageCourante = page;
  // Mémorise la page dans l'URL (pour la retrouver après actualisation)
  if (location.hash !== "#" + page) {
    history.replaceState(null, "", "#" + page);
  }
  document.querySelectorAll("[data-page-content]").forEach(s =>
    s.classList.toggle("is-active", s.dataset.pageContent === page));
  // Lien de la page ouverte : aria-current (menu principal et menu du compte) ;
  // la lettre fait partie des offres
  const courante = page === "lettre" ? "offres" : page;
  document.querySelectorAll(".menu__lien[data-page], .compte__lien[data-page]").forEach(n => {
    if (n.dataset.page === courante) n.setAttribute("aria-current", "page");
    else n.removeAttribute("aria-current");
  });

  if (page === "profil" && !Profil._charge) Profil.charger();
  if (page === "candidatures") Candidatures.charger();
  if (page === "parametres") Parametres.charger();
  if (page === "accueil") Accueil.charger();
  // L'Accueil a sa propre tête (salutation) : pas de titre de page en plus
  document.querySelector("[data-page-tete]").hidden = page === "accueil" || page === "lettre";
  // Pages au contenu étroit (1120 px, comme leurs maquettes) : la tête s'aligne dessus
  document.getElementById("contenu").classList.toggle("main--etroit", ["profil", "spontanees"].includes(page));
  const t = TOPBAR[page];
  document.querySelector('[data-topbar="title"]').textContent = t.title;
  document.querySelector('[data-topbar="phrase"]').textContent = t.phrase || "";
  document.querySelector('[data-topbar="action-label"]').textContent = t.action || "";
  document.querySelector('[data-topbar="action"]').hidden = !t.action;
  document.title = `${t.title} · Chasseur`;
  // Recherche dans la page : seulement là où il y a une liste à filtrer
  document.querySelector("[data-search-zone]").hidden = !LISTES_RECHERCHE[page];
  // Page choisie dans le menu : le lecteur d'écran repart du contenu
  if (focus) (page === "lettre" ? document.getElementById("lettre-titre")
    : document.getElementById("contenu")).focus({ preventScroll: true });
}

/* ── Mon compte : menu du rond aux initiales ─────────────────────────────── */
function brancherCompte() {
  const bouton = document.querySelector("[data-compte-bouton]");
  const menu = document.querySelector("[data-compte-menu]");
  const ouvrir = oui => {
    menu.hidden = !oui;
    bouton.setAttribute("aria-expanded", String(oui));
  };
  bouton.addEventListener("click", () => {
    ouvrir(menu.hidden);
    if (!menu.hidden) menu.querySelector("a, button")?.focus();
  });
  menu.addEventListener("keydown", e => {
    if (e.key === "Escape") { ouvrir(false); bouton.focus(); }
  });
  // Clic ailleurs ou focus sorti du menu : refermé
  document.addEventListener("click", e => {
    if (!menu.hidden && !e.target.closest(".compte")) ouvrir(false);
  });
  menu.addEventListener("focusout", e => {
    if (!menu.hidden && !e.relatedTarget?.closest?.(".compte")) ouvrir(false);
  });
  menu.querySelectorAll("a").forEach(a => a.addEventListener("click", () => ouvrir(false)));
}

/* ── Chargement global ───────────────────────────────────────────────────── */
async function recharger() {
  if (pageCourante === "accueil") Accueil.charger();
  await Offres.charger();
  await Candidatures.charger();   // suivi unique : offres postulées et spontanées envoyées
  await Spontanees.charger();
}

/* ── Polling : reflète l'état des pipelines en haut de page ───────────────
   Une requête au chargement, puis toutes les POLL_MS seulement tant qu'un
   pipeline tourne. Chaque lancement ou arrêt relance la surveillance. */
const POLL_MS = 5000;
let minuteur = null;     // prochain poll programmé
let enVol = false;       // une requête de statut est en cours
let aRelancer = false;   // surveiller() appelé pendant cette requête

/* Erreur d'un pipeline (IA injoignable, modèle absent...) :
   affichée dans le bandeau de confirmation jusqu'à un clic, une seule fois */
const erreursVues = new Set();
function signalerErreur(etat) {
  const texte = etat && !etat.en_cours && typeof etat.message === "string" ? etat.message : "";
  if (!texte.startsWith("Erreur") || erreursVues.has(texte)) return;
  erreursVues.add(texte);
  const el = document.querySelector("[data-confirmation]");
  if (!el) return;
  clearTimeout(confirmerLancement._minuteur);
  el.textContent = "❌ " + texte + " (clique pour fermer)";
  el.classList.add("is-erreur");
  el.hidden = false;
}

function surveiller() {
  if (enVol) { aRelancer = true; return; }
  clearTimeout(minuteur);
  minuteur = null;
  pollEtat();
}

async function pollEtat() {
  enVol = true;
  let actif = !!pollEtat._etaitActif;   // erreur réseau : on garde le dernier état connu
  try {
    const { recherche: rech, analyse: an, spontanees: sp } = await api.statutPipelines();
    actif = rech.en_cours || an.en_cours || sp.en_cours;
    signalerErreur(rech);
    signalerErreur(an);
    signalerErreur(sp);
    const bar = document.querySelector("[data-runbar]");
    bar.classList.toggle("is-on", actif);
    // Un seul pipeline de chaque type par utilisateur, tous modes confondus :
    // celui d'un autre mode (autre onglet) est signalé
    const autre = [rech, an, sp].find(e => e.en_cours && e.mode && e.mode !== MODE);
    const msg = document.querySelector("[data-runbar-msg]");
    if (msg) {
      msg.dataset.base ??= msg.textContent;
      // Analyse en cours : avancement et temps restant estimé avant le message fixe
      const avancement = an.en_cours ? `${an.message}. ` : "";
      msg.textContent = (autre ? `Traitement en cours en mode ${autre.mode} (autre onglet ou lancement précédent). ` : "")
        + avancement + msg.dataset.base;
    }
    if (actif) {
      // La bannière garde son message fixe d'avertissement (défini dans le HTML).
      // Jauge du runbar : seulement pour la RECHERCHE (les spontanées ont leurs cartes)
      const barre = document.querySelector("[data-runbar-bar]");
      const lbl   = document.querySelector("[data-runbar-pct]");
      const progress = document.querySelector("[data-runbar-progress]");
      const jauge = rech.en_cours ? rech : an.en_cours ? an : null;
      if (jauge) {
        const pct = jauge.pourcentage ?? 0;
        if (progress) progress.style.display = "flex";
        if (barre) barre.style.width = pct + "%";
        if (lbl)   lbl.textContent = pct + "%";
      } else if (progress) {
        progress.style.display = "none";   // pas de jauge dans la bannière pour les spontanées
      }
      // Analyse : les offres notées apparaissent au fur et à mesure
      if (an.en_cours && an.faites !== pollEtat._faites) {
        pollEtat._faites = an.faites;
        if (an.faites) Offres.charger();
      }
      // Met à jour les cartes du pipeline en temps réel (barre + message + pourcentage)
      if (sp.en_cours) Spontanees.majPipe(sp);
    } else {
      // un pipeline vient de finir → on rafraîchit les données une fois
      if (pollEtat._etaitActif) recharger();
    }
    pollEtat._etaitActif = actif;
    pollEtat._analyseEnCours = an.en_cours;
  } catch (_) {}
  enVol = false;
  if (aRelancer) { aRelancer = false; surveiller(); return; }
  if (actif) minuteur = setTimeout(pollEtat, POLL_MS);
}

/* ── Sauvegarde du profil (topbar + bouton de page) ──────────────────────── */
async function sauvegarderProfil() {
  const statut = document.querySelector("[data-profil-status]");
  const ok = await Profil.sauvegarder();
  if (statut) {
    statut.textContent = ok ? "✓ Profil enregistré" : "Erreur lors de l'enregistrement";
    statut.classList.toggle("is-ok", ok);
    setTimeout(() => { statut.textContent = ""; statut.classList.remove("is-ok"); }, 3000);
  }
}

/* ── Recherche contextuelle (filtre les lignes de la page courante) ──────── */
const LISTES_RECHERCHE = {
  offres:             { liste: '[data-list="offres"]',        ligne: ".offres__item" },
  candidatures:       { liste: '[data-list="candidatures"]',  ligne: ".carte-cand" },
  spontanees:         { liste: '[data-list="spontanees"]',    ligne: ".ent" },
};

function rechercher(texte) {
  const conf = LISTES_RECHERCHE[pageCourante];
  if (!conf) return;
  const conteneur = document.querySelector(conf.liste);
  if (!conteneur) return;
  const q = texte.trim().toLowerCase();
  let visibles = 0;
  conteneur.querySelectorAll(conf.ligne).forEach(ligne => {
    // Si la ligne a un data-search-text, on cherche seulement dedans (évite le bruit de l'analyse IA)
    const cible = ligne.dataset.searchText !== undefined
      ? ligne.dataset.searchText
      : ligne.textContent.toLowerCase();
    const match = !q || cible.includes(q);
    ligne.style.display = match ? "" : "none";
    if (match) visibles++;
  });
}

/* ── Branchement des événements ──────────────────────────────────────────── */
function brancher() {
  brancherCompte();
  // barre de recherche contextuelle
  const champRecherche = document.querySelector("[data-search]");
  if (champRecherche) champRecherche.addEventListener("input", e => rechercher(e.target.value));
  // bouton enregistrer du profil (dans la page)
  const btnProfil = document.querySelector("[data-profil-save]");
  if (btnProfil) btnProfil.addEventListener("click", sauvegarderProfil);
  // Navigation : de vrais liens (#offres...) ; la page change par hashchange,
  // et un clic sur la page déjà ouverte la recharge sur place
  document.querySelectorAll("a[data-page], a[data-nav]").forEach(n =>
    n.addEventListener("click", e => {
      const page = n.dataset.page || n.dataset.nav;
      if (location.hash === "#" + page) { e.preventDefault(); naviguer(page); }
    }));
  // Précédent / Suivant du navigateur, ou ancre modifiée à la main (D133)
  window.addEventListener("hashchange", () => aller(pageDeLAncre(), { focus: true }));

  // bouton d'action contextuel de la topbar
  document.querySelector('[data-topbar="action"]').addEventListener("click", async () => {
    try { await TOPBAR[pageCourante].run(); } catch (e) { alert(e.message); }
    surveiller();   // un pipeline vient peut-être de démarrer
  });

  // Page Offres : liste, onglets, filtres et volet (offres.js) ; la lettre s'ouvre ici
  Offres.brancher(id => Lettre.ouvrir(Offres.data().find(o => o.id === id), "offres"));
  Lettre.brancher();
  // « Voir l'offre » depuis l'Accueil : l'offre s'ouvre dans le volet
  document.addEventListener("offres:montrer", e => Offres.montrer(e.detail));

  // filtres
  // Onglets des entreprises à contacter
  document.querySelector('[data-filters="spontanees"]')?.addEventListener("click", e => {
    const btn = e.target.closest("[data-filter]");
    if (btn) Spontanees.setFiltre(btn.dataset.filter);
  });

  // actions pipeline spontanées
  document.querySelectorAll("[data-action]").forEach(b =>
    b.addEventListener("click", async () => { await Spontanees.action(b.dataset.action); surveiller(); }));

  // bouton arrêter du runbar : l'analyse en cours, sinon le pipeline spontané
  document.querySelector("[data-runbar-stop]").addEventListener("click", async () => {
    try {
      if (pollEtat._analyseEnCours) await api.analyseStop(); else await api.spStop();
    } catch (_) {}
    surveiller();
  });
  // Analyse des offres en attente : bouton de la page Offres, ou « Les noter » de l'Accueil
  const lancerAnalyse = async () => {
    const toute = !!document.querySelector("[data-analyse-toute-file]")?.checked;
    const demandee = toute ? undefined : limite("analyses");
    try { confirmerLancement("analyses", demandee, await api.analyseAttente(demandee, toute)); }
    catch (e) { alert(e.message); }
    surveiller();
  };
  document.querySelector("[data-analyse-lancer]")?.addEventListener("click", lancerAnalyse);
  document.addEventListener("analyse:lancer", lancerAnalyse);
  Accueil.brancher();
  // Boutons Arrêter sur les cartes du pipeline
  document.querySelectorAll("[data-stop]").forEach(b =>
    b.addEventListener("click", async () => {
      try { await api.spStop(); Spontanees.charger(); } catch (_) {}
      surveiller();
    }));
  // Bandeau de confirmation ou d'erreur : un clic le ferme
  const bandeau = document.querySelector("[data-confirmation]");
  if (bandeau) bandeau.addEventListener("click", () => { bandeau.hidden = true; });
  // Retour sur l'onglet : un pipeline a pu être lancé ailleurs (autre onglet)
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") surveiller();
  });

  // « J'ai postulé » ou son annulation depuis la page Offres : le suivi suit
  document.addEventListener("candidatures:maj", () => Candidatures.charger());
  // « Annuler la candidature » depuis le tableau : l'offre revient dans la page Offres
  document.addEventListener("offres:maj", () => Offres.charger());
  Candidatures.onOuvrir(id => Lettre.ouvrir(Offres.data().find(o => o.id === id), "candidatures"));
}

/* ── Démarrage ───────────────────────────────────────────────────────────── */
brancher();
recharger();

// Onboarding : si on arrive juste après inscription, diriger vers le profil
(function demarrer() {
  const params = new URLSearchParams(location.search);
  if (params.get("bienvenue") === "1") {
    // Message d'accueil renforcé dans le bandeau du profil
    const intro = document.querySelector("[data-profil-intro] .profil-intro__txt");
    if (intro) {
      intro.innerHTML = "<strong>Bienvenue sur le Chasseur d'Alternance ! 🎯</strong>" +
        "Pour commencer, complète ton profil ci-dessous. C'est lui qui permet à l'app " +
        "d'analyser les offres, de générer tes lettres de motivation et tes emails. " +
        "Compte une dizaine de minutes — tu pourras tout modifier plus tard. " +
        "Remplis au minimum ton identité, ta formation, tes compétences et ta lettre type.";
    }
    aller("profil");
    // Nettoie l'URL pour ne pas réafficher le message au prochain rechargement
    history.replaceState(null, "", location.pathname);
  } else {
    // Reprendre la page mémorisée dans l'URL (#candidatures, etc.), sinon l'Accueil
    aller(pageDeLAncre());
  }
})();
surveiller();

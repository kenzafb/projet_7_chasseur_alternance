/* ============================================================================
   app.js — orchestrateur de l'interface
   Navigation par onglets · topbar contextuelle · modale lettre ·
   polling de l'état des pipelines. Tout le reste vit dans les modules dédiés.
   ============================================================================ */
import { api }           from "./api.js";
import { Offres }        from "./offres.js";
import { Candidatures }  from "./candidatures.js";
import { Spontanees }    from "./spontanees.js";
import { Profil }        from "./profil.js";
import { Suivi }         from "./suivi.js";

/* Contenu contextuel de la topbar selon la page */
const TOPBAR = {
  offres:       { title: "Offres d'alternance",   action: "Lancer la recherche", run: () => api.recherche() },
  candidatures: { title: "Mes candidatures",      action: "Actualiser",          run: () => recharger() },
  spontanees:   { title: "Candidatures spontanées", action: "Récupérer",         run: () => Spontanees.action("fetch") },
  profil:       { title: "Mon profil",            action: "Enregistrer",         run: () => sauvegarderProfil() },
  "spontanees-suivi": { title: "Suivi des candidatures spontanées", action: "Actualiser", run: () => Suivi.charger() },
};

let pageCourante = "offres";

/* ── Navigation ──────────────────────────────────────────────────────────── */
function aller(page) {
  pageCourante = page;
  // Mémorise la page dans l'URL (pour la retrouver après actualisation)
  if (location.hash !== "#" + page) {
    history.replaceState(null, "", "#" + page);
  }
  document.querySelectorAll("[data-page-content]").forEach(s =>
    s.classList.toggle("is-active", s.dataset.pageContent === page));
  document.querySelectorAll(".nav__item[data-page]").forEach(n =>
    n.classList.toggle("is-active", n.dataset.page === page));

  if (page === "profil" && !Profil._charge) Profil.charger();
  if (page === "spontanees-suivi") Suivi.charger();
  const t = TOPBAR[page];
  let titre = t.title;
  // Le titre de la page Offres s'adapte au mode (alternance / job)
  if (page === "offres" && document.documentElement.getAttribute("data-mode") === "job") {
    titre = "Offres de jobs";
  }
  document.querySelector('[data-topbar="title"]').textContent = titre;
  document.querySelector('[data-topbar="action-label"]').textContent = t.action;
  majBadge();
}

/* Badge contextuel de la topbar (compteur de la page courante) */
function majBadge() {
  const badge = document.querySelector('[data-topbar="badge"]');
  const compteur = document.querySelector(`[data-count="${pageCourante}"]`);
  const n = compteur ? compteur.textContent : "0";
  const mots = { offres: "offres", candidatures: "candidatures", spontanees: "entreprises", profil: "", "spontanees-suivi": "envoyées" };
  if (pageCourante === "profil") { badge.textContent = ""; return; }
  badge.textContent = `${n} ${mots[pageCourante]}`;
}

/* ── Modale lettre ───────────────────────────────────────────────────────── */
const modal = {
  el:    () => document.querySelector("[data-modal]"),
  area:  () => document.querySelector("[data-modal-letter]"),
  id:    null,
  async ouvrir(id) {
    this.id = id;
    const offre = Offres.data().find(o => o.id === id);
    let lettre = offre?.lettre || "";
    if (!lettre) {
      this.area().value = "Génération en cours…";
      this.el().classList.add("is-open");
      try { lettre = (await api.genererLettre(id)).lettre; } catch (e) { lettre = "Erreur : " + e.message; }
    }
    this.area().value = lettre;
    this.el().classList.add("is-open");
  },
  fermer() { this.el().classList.remove("is-open"); this.id = null; },
  async enregistrer() {
    if (!this.id) return;
    await api.sauvegarder({ id: this.id, lettre: this.area().value });
    this.fermer();
    recharger();
  },
  async pdf() {
    if (!this.id) return;
    try {
      const r = await api.telechargerPdf(this.id, this.area().value);
      alert("PDF généré :\n" + (r.chemin || "lettres_pdf/"));
    } catch (e) { alert(e.message); }
  },
};

/* ── Chargement global ───────────────────────────────────────────────────── */
async function recharger() {
  await Offres.charger();
  Candidatures.rendre(Offres.data());
  await Spontanees.charger();
  majCompteurSuivi();
  majBadge();
}

// Met à jour le compteur "Spontanées envoyées" dans la sidebar (sans tout charger)
async function majCompteurSuivi() {
  try {
    const r = await fetch("/api/spontanees/suivi");
    if (!r.ok) return;
    const d = await r.json();
    const cnt = document.querySelector('[data-count="spontanees-suivi"]');
    if (cnt) cnt.textContent = d.length;
  } catch (_) {}
}

/* ── Polling : reflète l'état des pipelines en haut de page ─────────────── */
async function pollEtat() {
  try {
    const [rech, sp] = await Promise.all([api.statutRecherche(), api.spStatut()]);
    const actif = rech.en_cours || sp.en_cours;
    const bar = document.querySelector("[data-runbar]");
    bar.classList.toggle("is-on", actif);
    if (actif) {
      // La bannière garde son message fixe d'avertissement (défini dans le HTML).
      // Jauge du runbar : seulement pour la RECHERCHE (les spontanées ont leurs cartes)
      const barre = document.querySelector("[data-runbar-bar]");
      const lbl   = document.querySelector("[data-runbar-pct]");
      const progress = document.querySelector("[data-runbar-progress]");
      if (rech.en_cours) {
        const pct = rech.pourcentage ?? 0;
        if (progress) progress.style.display = "flex";
        if (barre) barre.style.width = pct + "%";
        if (lbl)   lbl.textContent = pct + "%";
      } else if (progress) {
        progress.style.display = "none";   // pas de jauge dans la bannière pour les spontanées
      }
      // Met à jour les cartes du pipeline en temps réel (barre + message + pourcentage)
      if (sp.en_cours) Spontanees.majPipe(sp);
    } else {
      // un pipeline vient de finir → on rafraîchit les données une fois
      if (pollEtat._etaitActif) recharger();
    }
    pollEtat._etaitActif = actif;
  } catch (_) {}
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
  offres:             { liste: '[data-list="offres"]',        ligne: ".offre__card, .offre" },
  candidatures:       { liste: '[data-list="candidatures"]',  ligne: ".suivi-row" },
  spontanees:         { liste: '[data-list="spontanees"]',    ligne: ".trow:not(.thead)" },
  "spontanees-suivi": { liste: '[data-list="suivi"]',         ligne: ".suivi-row" },
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
  // repli de la sidebar
  const btnToggle = document.querySelector("[data-sidebar-toggle]");
  const sidebar = document.querySelector("[data-sidebar]");
  if (btnToggle && sidebar) {
    btnToggle.addEventListener("click", () => {
      const replie = sidebar.classList.toggle("is-collapsed");
      try { localStorage.setItem("sidebar_repliee", replie ? "1" : "0"); } catch (_) {}
    });
    // Restaurer l'état mémorisé au chargement
    try {
      if (localStorage.getItem("sidebar_repliee") === "1") sidebar.classList.add("is-collapsed");
    } catch (_) {}
    // Retire la classe temporaire anti-flash (le vrai état est maintenant posé)
    document.documentElement.classList.remove("sidebar-pre-collapsed");
  }
  // barre de recherche contextuelle
  const champRecherche = document.querySelector("[data-search]");
  if (champRecherche) champRecherche.addEventListener("input", e => rechercher(e.target.value));
  // fermeture des encarts guide
  document.querySelectorAll("[data-guide-close]").forEach(x =>
    x.addEventListener("click", () => x.closest(".guide").classList.add("is-hidden")));
  // bouton enregistrer du profil (dans la page)
  const btnProfil = document.querySelector("[data-profil-save]");
  if (btnProfil) btnProfil.addEventListener("click", sauvegarderProfil);
  // navigation
  document.querySelectorAll(".nav__item[data-page]").forEach(n =>
    n.addEventListener("click", () => aller(n.dataset.page)));

  // bouton d'action contextuel de la topbar
  document.querySelector('[data-topbar="action"]').addEventListener("click", async () => {
    try { await TOPBAR[pageCourante].run(); } catch (e) { alert(e.message); }
  });

  // clics délégués sur les offres
  document.querySelector('[data-list="offres"]').addEventListener("click", e => {
    Offres.onClick(e, id => modal.ouvrir(id));
  });

  // filtres
  document.querySelectorAll("[data-filters]").forEach(grp => {
    grp.addEventListener("click", e => {
      const btn = e.target.closest("[data-filter]");
      if (!btn) return;
      grp.querySelectorAll(".filter").forEach(f => f.classList.remove("is-active"));
      btn.classList.add("is-active");
      const f = btn.dataset.filter;
      if (grp.dataset.filters === "offres" || grp.dataset.filters === "offres-archives") Offres.setFiltre(f);
      if (grp.dataset.filters === "spontanees") Spontanees.setFiltre(f);
    });
  });

  // bascule Offres ↔ Archivées
  const btnArchives = document.querySelector("[data-archives-toggle]");
  if (btnArchives) {
    btnArchives.addEventListener("click", () => {
      const enArchives = Offres.basculerArchives();
      const menusNormal     = document.querySelector('.filters-menus[data-mode="normal"]');
      const filtresArchives = document.querySelector('[data-filters="offres-archives"]');
      const label = document.querySelector("[data-archives-label]");
      if (enArchives) {
        if (menusNormal)     menusNormal.style.display = "none";
        if (filtresArchives) filtresArchives.style.display = "";
        if (label) label.textContent = "← Retour aux offres";
      } else {
        if (menusNormal)     menusNormal.style.display = "flex";
        if (filtresArchives) filtresArchives.style.display = "none";
        if (label) label.textContent = "Archivées";
      }
      // En mode archives, on remet le filtre raison sur "Toutes"
      if (filtresArchives) {
        filtresArchives.querySelectorAll(".filter").forEach(x => x.classList.remove("is-active"));
        const tout = filtresArchives.querySelector('[data-filter="all"]');
        if (tout) tout.classList.add("is-active");
      }
    });
  }

  // Menus de filtres combinables (mode normal Offres)
  document.querySelectorAll("[data-foffre]").forEach(menu =>
    menu.addEventListener("change", () =>
      Offres.setFiltreOffre(menu.dataset.foffre, menu.value)));

  // actions pipeline spontanées
  document.querySelectorAll("[data-action]").forEach(b =>
    b.addEventListener("click", () => Spontanees.action(b.dataset.action)));

  // modale
  document.querySelector("[data-modal-close]").addEventListener("click", () => modal.fermer());
  document.querySelector("[data-modal-save]").addEventListener("click", () => modal.enregistrer());
  document.querySelector("[data-modal-pdf]").addEventListener("click", () => modal.pdf());
  document.querySelector("[data-modal]").addEventListener("click", e => {
    if (e.target.matches("[data-modal]")) modal.fermer();
  });

  // bouton arrêter du runbar
  document.querySelector("[data-runbar-stop]").addEventListener("click", () => api.spStop());
  // Boutons Arrêter sur les cartes du pipeline
  document.querySelectorAll("[data-stop]").forEach(b =>
    b.addEventListener("click", async () => {
      try { await api.spStop(); Spontanees.charger(); } catch (_) {}
    }));

  // rafraîchir le kanban quand on déplace une carte
  Candidatures.onRefresh(() => recharger());
  Candidatures.onOuvrir(id => modal.ouvrir(id));
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
    history.replaceState(null, "", "/");
  } else {
    // Reprendre la page mémorisée dans l'URL (#candidatures, etc.), sinon Offres
    const PAGES_VALIDES = ["offres", "candidatures", "spontanees", "spontanees-suivi", "profil"];
    const hash = location.hash.replace("#", "");
    aller(PAGES_VALIDES.includes(hash) ? hash : "offres");
  }
})();
setInterval(pollEtat, 2500);

/* ============================================================================
   api.js — couche d'accès à l'API FastAPI
   Toutes les requêtes réseau passent par ici. Le reste du code ne connaît
   que des fonctions, jamais des URL.
   ============================================================================ */

/* Session absente ou expirée : retour à la page de connexion */
function verifierSession(r) {
  if (r.status === 401) window.location.href = "/login";
}

/* Limite saisie dans un champ [data-limite="cle"], envoyée telle quelle : le
   serveur la ramène dans ses bornes et renvoie la valeur appliquée, affichée
   par confirmerLancement. Champ absent ou vide : défaut du serveur */
export function limite(cle) {
  const champ = document.querySelector(`[data-limite="${cle}"]`);
  const n = parseInt(champ?.value, 10);
  return !champ || Number.isNaN(n) ? undefined : n;
}

/* Confirmation d'un lancement avec la valeur réellement appliquée par le
   serveur ; le champ reprend cette valeur. */
const LANCEMENTS = {
  analyses:    { champ: "max_analyses",    texte: n => `Recherche lancée : ${n} offres ${
    document.documentElement.dataset.analyseIa === "non" ? "ajoutées sans analyse" : "analysées"} au plus` },
  entreprises: { champ: "max_entreprises", texte: n => `Récupération lancée : ${n} nouvelles entreprises au plus` },
  scrapees:    { champ: "max_scrapees",    texte: n => `Scraping lancé : ${n} entreprises au plus` },
  mails:       { champ: "limite",          texte: n => `Envoi lancé : ${n} mails au plus` },
  revalidations: { champ: "max_revalidations", texte: n => `Validation IA lancée : ${n} entreprises au plus` },
};

export function confirmerLancement(cle, demandee, reponse) {
  const regle = LANCEMENTS[cle];
  const appliquee = reponse?.[regle.champ];
  if (appliquee === undefined) return;
  let texte = regle.texte(appliquee);
  if (demandee !== undefined && demandee !== appliquee) texte += ` (demandé : ${demandee}, ramené à ${appliquee})`;
  if (reponse.mode_test) texte += ". 🧪 Mode test : tout part vers ton adresse d'expédition";
  if (reponse.avertissement) texte += ". ⚠️ " + reponse.avertissement.replace(/\.$/, "");
  const champ = document.querySelector(`[data-limite="${cle}"]`);
  if (champ) champ.value = appliquee;
  const el = document.querySelector("[data-confirmation]");
  if (!el) return;
  el.classList.remove("is-erreur");
  el.textContent = texte + ".";
  el.hidden = false;
  clearTimeout(confirmerLancement._minuteur);
  confirmerLancement._minuteur = setTimeout(() => { el.hidden = true; }, 20000);
}

async function get(url) {
  const r = await fetch(url);
  verifierSession(r);
  if (!r.ok) throw new Error(`GET ${url} → ${r.status}`);
  return r.json();
}

async function post(url, body) {
  const r = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : "{}",
  });
  verifierSession(r);
  if (!r.ok) {
    let detail = "";
    try { detail = (await r.json()).erreur || ""; } catch (_) {}
    throw new Error(detail || `POST ${url} → ${r.status}`);
  }
  return r.json();
}

/* Envoi multipart (téléversement de fichier) */
async function postForm(url, formData) {
  const r = await fetch(url, { method: "POST", body: formData });
  verifierSession(r);
  if (!r.ok) {
    let detail = "";
    try { detail = (await r.json()).erreur || ""; } catch (_) {}
    throw new Error(detail || `POST ${url} → ${r.status}`);
  }
  return r.json();
}

/* Télécharge un fichier servi par l'API (PDF...) : vrai téléchargement
   navigateur, sous le nom donné par le serveur ou `nom` à défaut. */
async function telecharger(url, nom) {
  const r = await fetch(url);
  verifierSession(r);
  if (!r.ok) {
    let detail = "";
    try { detail = (await r.json()).erreur || ""; } catch (_) {}
    throw new Error(detail || `GET ${url} → ${r.status}`);
  }
  const blob = await r.blob();
  const lien = document.createElement("a");
  lien.href = URL.createObjectURL(blob);
  lien.download = nom || "document.pdf";
  document.body.appendChild(lien);
  lien.click();
  lien.remove();
  setTimeout(() => URL.revokeObjectURL(lien.href), 10000);
}

export const api = {
  // Offres / candidatures
  candidatures:      ()        => get("/api/candidatures"),
  recherche:         (max)     => post("/api/recherche", { max_analyses: max }),
  statutPipelines:   ()        => get("/api/statut_pipelines"),
  analyser:          (id)      => post("/api/analyser", { id }),
  genererLettre:     (id)      => post("/api/generer_lettre", { id }),
  majStatut:         (id, s)   => post("/api/maj_statut", { id, statut: s }),
  archiver:          (id)      => post("/api/archiver", { id }),
  desarchiver:       (id)      => post("/api/offre/archivage", { id, desarchiver: true }),
  changerRaison:     (id, r)   => post("/api/offre/archivage", { id, raison: r }),
  sauvegarder:       (payload) => post("/api/sauvegarder", payload),
  // Génère le PDF côté serveur puis le télécharge
  telechargerPdf:    async (id, l) => {
    const r = await post("/api/telecharger_pdf", { id, lettre: l });
    await telecharger(r.url, r.nom);
  },

  // Profil, mode, domaines
  profil:          ()        => get("/api/profil"),
  sauverProfil:    (donnees) => post("/api/profil", donnees),
  mode:            ()        => get("/api/mode"),
  domaines:        ()        => get("/api/domaines"),
  criteresOptions: ()        => get("/api/criteres_options"),
  envoyerPiece:    (fd)      => postForm("/api/profil/upload", fd),
  supprimerPiece:  (nom)     => post("/api/profil/piece/supprimer", { nom }),

  // Compte d'envoi (le mot de passe part au serveur, il n'en revient jamais)
  compteEnvoi:          ()      => get("/api/compte_envoi"),
  enregistrerCompte:    (corps) => post("/api/compte_envoi", corps),
  supprimerCompte:      ()      => post("/api/compte_envoi/supprimer"),
  testerCompte:         ()      => post("/api/compte_envoi/tester"),
  mailTestCompte:       ()      => post("/api/compte_envoi/mail_test"),
  modeTestCompte:       (actif) => post("/api/compte_envoi/mode_test", { actif }),

  // Spontanées
  spSuivi:       ()           => get("/api/spontanees/suivi"),
  spSuiviStatut: (id, statut) => post("/api/spontanees/suivi/statut", { id, statut }),
  spStats:    ()       => get("/api/spontanees/stats"),
  spFetch:    (max)    => post("/api/spontanees/fetch", { max_entreprises: max }),
  spScraper:  (max)    => post("/api/spontanees/scraper", { max_scrapees: max }),
  spEnvoyer:  (limite, test = false) => post("/api/spontanees/envoyer", { limite, test }),
  spStop:     ()       => post("/api/spontanees/stop"),
  spAValider:  ()      => get("/api/spontanees/a_valider"),
  spValider:   (id)    => post("/api/spontanees/valider", { id }),
  spRevalider: (max)   => post("/api/spontanees/revalider", { max_revalidations: max }),

  // Logs
  logs: () => get("/api/logs"),
};

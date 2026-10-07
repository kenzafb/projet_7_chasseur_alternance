/* ============================================================================
   api.js — couche d'accès à l'API FastAPI
   Toutes les requêtes réseau passent par ici. Le reste du code ne connaît
   que des fonctions, jamais des URL.
   ============================================================================ */

/* Session absente ou expirée : retour à la page de connexion */
function verifierSession(r) {
  if (r.status === 401) window.location.href = "/login";
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
  recherche:         ()        => post("/api/recherche"),
  statutRecherche:   ()        => get("/api/statut_recherche"),
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
  envoyerPiece:    (fd)      => postForm("/api/profil/upload", fd),
  supprimerPiece:  (nom)     => post("/api/profil/piece/supprimer", { nom }),

  // Spontanées
  spSuivi:       ()           => get("/api/spontanees/suivi"),
  spSuiviStatut: (id, statut) => post("/api/spontanees/suivi/statut", { id, statut }),
  spStats:    ()       => get("/api/spontanees/stats"),
  spStatut:   ()       => get("/api/spontanees/statut"),
  spFetch:    ()       => post("/api/spontanees/fetch"),
  spScraper:  ()       => post("/api/spontanees/scraper"),
  spEnvoyer:  (limite, test = false) => post("/api/spontanees/envoyer", { limite, test }),
  spStop:     ()       => post("/api/spontanees/stop"),

  // Logs
  logs: () => get("/api/logs"),
};

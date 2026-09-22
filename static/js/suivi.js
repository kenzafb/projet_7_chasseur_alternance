/* ============================================================================
   suivi.js — tableau de suivi des candidatures spontanées envoyées
   ============================================================================ */

const STATUTS = [
  ["envoye", "Envoyé"],
  ["a_relancer", "À relancer"],
  ["reponse", "Réponse"],
  ["entretien", "Entretien"],
  ["refus", "Refus"],
  ["bounce", "Bounce"],
];

let _data = [];
let _filtre = "all";

function ligne(e) {
  const st = e.statut_suivi || "envoye";
  const options = STATUTS.map(([v, label]) =>
    `<option value="${v}"${v === st ? " selected" : ""}>${label}</option>`).join("");
  return `<div class="suivi-row" data-id="${e._id}">
    <span class="suivi-row__nom">${e.nom_commercial || e.nom || "—"}</span>
    <span>${e.ville || "—"}</span>
    <span>${e.contact_rh || (e.emails_trouves && e.emails_trouves[0]) || "—"}</span>
    <span>${(e.telephones && e.telephones[0]) || e.telephone || "—"}</span>
    <span>${(e.mail_envoye_le || "").split(" ")[0] || "—"}</span>
    <select class="suivi-statut st-${st}" data-statut-select="1">${options}</select>
  </div>`;
}

function rendre() {
  const c = document.querySelector('[data-list="suivi"]');
  if (!c) return;
  const liste = _filtre === "all" ? _data : _data.filter(e => (e.statut_suivi || "envoye") === _filtre);
  if (!liste.length) {
    c.innerHTML = '<div class="suivi-empty">Aucune candidature dans cette catégorie.</div>';
    return;
  }
  try {
    c.innerHTML = liste.map(ligne).join("");
  } catch (err) {
    console.error("[SUIVI] erreur rendu:", err);
    c.innerHTML = '<div class="suivi-empty">Erreur rendu: ' + err.message + '</div>';
  }
}

export const Suivi = {
  _charge: false,

  async charger() {
    const r = await fetch("/api/spontanees/suivi");
    if (!r.ok) return;
    _data = await r.json();
    rendre();
    // compteur dans la nav
    const cnt = document.querySelector('[data-count="spontanees-suivi"]');
    if (cnt) cnt.textContent = _data.length;

    if (!this._charge) {
      // Changement de statut
      document.querySelector('[data-list="suivi"]').addEventListener("change", async e => {
        if (!e.target.dataset.statutSelect) return;
        const row = e.target.closest(".suivi-row");
        const id = Number(row.dataset.id);
        const statut = e.target.value;
        const res = await fetch("/api/spontanees/suivi/statut", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ id, statut }),
        });
        if ((await res.json()).ok) {
          // maj locale + couleur
          const item = _data.find(x => x._id === id);
          if (item) item.statut_suivi = statut;
          e.target.className = "suivi-statut st-" + statut;
        }
      });
      // Filtres
      document.querySelectorAll('[data-filters="suivi"] .filter').forEach(f =>
        f.addEventListener("click", () => {
          document.querySelectorAll('[data-filters="suivi"] .filter').forEach(x => x.classList.remove("is-active"));
          f.classList.add("is-active");
          _filtre = f.dataset.filter;
          rendre();
        }));
      this._charge = true;
    }
  },
};

/* ============================================================================
   accueil.js — page d'arrivée du mode (D144)
   Salutation, ce qui attend, la recherche en bref, l'avancement du profil :
   tout vient de /api/accueil, en une requête.
   ============================================================================ */
import { api, esc } from "./api.js";

const ICONES = {
  offre:    '<path d="M12 3l2.6 5.6 6 .7-4.5 4.1 1.2 6L12 16.5 6.7 19.4l1.2-6L3.4 9.3l6-.7z"/>',
  relance:  '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  a_noter:  '<path d="M4 6h16M4 12h10M4 18h7"/>',
};

/* Une tâche : icône, titre, phrase, et un bouton vers le bon écran. La
   première est l'action principale (verte) ; « Les noter » lance la notation. */
function tache(t, principale) {
  const classe = `btn${principale ? " btn--primary" : ""}`;
  const bouton = t.genre === "a_noter"
    ? `<button type="button" class="${classe}" data-accueil-noter>${esc(t.bouton)}</button>`
    : `<a class="${classe}" href="#${esc(t.page)}">${esc(t.bouton)}</a>`;
  return `<li class="afaire__ligne">
      <span class="afaire__icone afaire__icone--${esc(t.genre)}" aria-hidden="true">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${ICONES[t.genre] || ""}</svg>
      </span>
      <span class="afaire__txt"><strong>${esc(t.titre)}</strong><span>${esc(t.texte)}</span></span>
      ${bouton}
    </li>`;
}

function rendre(d) {
  const titre = document.querySelector("[data-accueil-salutation]");
  titre.textContent = d.prenom ? `${d.salutation} ${d.prenom}` : d.salutation;
  document.querySelector("[data-accueil-phrase]").textContent =
    [d.phrase, d.a_faire.length ? "Voici ce qui t'attend aujourd'hui." : ""].filter(Boolean).join(" ")
    || "Rien d'urgent pour l'instant.";

  const liste = document.querySelector("[data-accueil-afaire]");
  liste.innerHTML = d.a_faire.length ? d.a_faire.map((t, i) => tache(t, i === 0)).join("")
    : `<li class="afaire__vide">Tout est à jour. Cherche de nouvelles offres quand tu veux.
         <a class="btn btn--primary" href="#offres">Voir les offres</a></li>`;

  Object.entries(d.en_bref).forEach(([cle, n]) => {
    const el = document.querySelector(`[data-accueil-bref="${cle}"]`);
    if (el) el.textContent = n;
  });

  const p = d.profil;
  const barre = document.querySelector("[data-accueil-avancement]");
  barre.setAttribute("aria-valuenow", p.completes);
  barre.setAttribute("aria-valuetext", `${p.completes} parties complètes sur ${p.total}`);
  document.querySelector("[data-accueil-avancement-barre]").style.width = `${Math.round(100 * p.completes / p.total)}%`;
  const manques = p.parties.filter(x => !x.complet);
  document.querySelector("[data-accueil-profil-texte]").textContent = !manques.length
    ? "Complet. Plus il est précis, mieux le Chasseur note les offres."
    : manques.length === 1 ? "Presque complet. Plus il est précis, mieux le Chasseur note les offres."
    : `${p.completes} parties complètes sur ${p.total}.`;
  document.querySelector("[data-accueil-manques]").innerHTML = manques
    .map(x => `<li><strong>${esc(x.titre)}</strong> : ${esc(x.manque)}</li>`).join("");
  document.querySelector("[data-accueil-profil-lien]").textContent = manques.length ? "Compléter mon profil" : "Voir mon profil";
}

export const Accueil = {
  async charger() {
    let d;
    try { d = await api.accueil(); } catch (_) { return; }
    rendre(d);
  },
  brancher() {
    // « Les noter » : même lancement que sur la page Offres (app.js)
    document.querySelector("[data-accueil-afaire]").addEventListener("click", e => {
      if (e.target.closest("[data-accueil-noter]")) document.dispatchEvent(new CustomEvent("analyse:lancer"));
    });
  },
};

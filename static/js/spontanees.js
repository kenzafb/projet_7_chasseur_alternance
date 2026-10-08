/* ============================================================================
   spontanees.js — table des entreprises + pilotage du pipeline
   ============================================================================ */
import { api, limite, confirmerLancement } from "./api.js";

let stats = null;
let compte = null;    // compte d'envoi (mode test affiché en bandeau)
let aValider = [];    // entreprises aux emails non validés par l'IA
let filtre = "all";

function ligne(e) {
  const aEmail = !!e.email;
  const statut = e.envoye
    ? `<span class="chip chip--vert">envoyé</span>`
    : aEmail
      ? `<span class="chip chip--ft">à envoyer</span>`
      : `<span class="chip chip--gris">ignoré</span>`;
  // Entreprise à fort potentiel de La Bonne Alternance : traitée en priorité
  const lba = e.lba ? ` <span class="chip chip--lba" title="Fort potentiel d'embauche d'alternants (La Bonne Alternance)">LBA</span>` : "";
  const origine = aEmail && e.email_lba ? ` <span class="trow__sub">(fourni par LBA)</span>` : "";
  return `
    <div class="trow">
      <div>
        <div class="trow__name">${esc(e.nom || "—")}${lba}</div>
        <div class="trow__sub">${esc(e.ville || "")}</div>
      </div>
      <div class="trow__mail ${aEmail ? "" : "trow__mail--none"}">${aEmail ? esc(e.email) : "non trouvé"}${origine}</div>
      <div>${statut}</div>
    </div>`;
}

function rendreTable() {
  const el = document.querySelector('[data-list="spontanees"]');
  if (!el || !stats) return;
  // Prochaines entreprises (LBA d'abord, ordre du scraper et de l'envoyeur), puis les dernières envoyées
  let items = [...(stats.prochaines || []), ...(stats.dernieres || [])];
  if (filtre === "email")  items = items.filter(e => e.email);
  if (filtre === "envoye") items = items.filter(e => e.envoye);
  if (filtre === "lba")    items = items.filter(e => e.lba);

  el.innerHTML = items.length
    ? items.map(ligne).join("")
    : `<div class="empty" style="padding:40px 20px;">
         <div class="empty__title">Rien à afficher</div>
         <div class="empty__hint">Lance le pipeline pour récupérer des entreprises et leurs contacts.</div>
       </div>`;
}

function rendreKpis() {
  if (!stats) return;
  const set = (k, v) => { const e = document.querySelector(`[data-sp="${k}"]`); if (e) e.textContent = v; };
  set("raw", fmt(stats.raw));
  set("avec_email", fmt(stats.avec_email));
  set("mail_envoye", fmt(stats.mail_envoye));
  const taux = stats.raw ? Math.round((stats.avec_email / stats.raw) * 100) : 0;
  set("taux_email", `${taux}% de la base`);
  set("lba", stats.lba ? `dont ${fmt(stats.lba)} à fort potentiel (LBA)` : "dans la base");

  // compteur sidebar + pied
  const c = document.querySelector('[data-count="spontanees"]');
  if (c) c.textContent = fmt(stats.raw);
  const ae = document.querySelector('[data-stat="avec_email"]');
  if (ae) ae.textContent = fmt(stats.avec_email);
  const en = document.querySelector('[data-stat="envoyes"]');
  if (en) en.textContent = fmt(stats.mail_envoye);
  const tx = stats.avec_email ? Math.round((stats.mail_envoye / stats.avec_email) * 100) : 0;
  const bar = document.querySelector('[data-stat="taux-bar"]');
  if (bar) bar.style.width = `${tx}%`;
  const lbl = document.querySelector('[data-stat="taux"]');
  if (lbl) lbl.textContent = `${tx}% de taux d'envoi`;
}

/* Surligne l'étape active du pipeline + affiche l'état et le message */
function rendrePipe() {
  const pipe = document.querySelector("[data-pipe]");
  // Reset
  document.querySelectorAll("[data-step]").forEach(s => {
    s.classList.remove("is-active");
    const msg = s.querySelector("[data-step-msg]");
    if (msg) msg.textContent = "";
  });
  if (pipe) pipe.classList.remove("is-running");

  if (stats?.en_cours && stats.etape) {
    if (pipe) pipe.classList.add("is-running");
    const s = document.querySelector(`[data-step="${stats.etape}"]`);
    if (s) {
      s.classList.add("is-active");
      const msg = s.querySelector("[data-step-msg]");
      if (msg && stats.message) msg.textContent = stats.message;
      // Barre de progression (si un pourcentage est remonté)
      const pct = stats.pourcentage ?? 0;
      const bar = s.querySelector("[data-step-progress-bar]");
      const lbl = s.querySelector("[data-step-progress-pct]");
      if (bar) bar.style.width = pct + "%";
      if (lbl) lbl.textContent = pct + "%";
    }
  }
}

/* Bandeau du mode test : option du compte, ou envoi de test en cours */
function rendreModeTest() {
  const bandeau = document.querySelector("[data-sp-mode-test]");
  if (!bandeau) return;
  const actif = !!(compte && compte.mode_test) || !!(stats?.en_cours && stats.mode_test);
  bandeau.hidden = !actif;
  const adr = document.querySelector("[data-sp-mode-test-adresse]");
  if (adr) adr.textContent = compte ? compte.adresse : "ton adresse d'expédition";
}

/* Maximum d'un lancement : le plafond, borné par ce qui reste à traiter
   (entreprises à scraper, entreprises à contacter dans ce mode) */
function rendreMaximums() {
  const dispo = { scrapees: stats?.a_scraper, mails: stats?.a_envoyer };
  const textes = { scrapees: "aucune entreprise à scraper", mails: "aucune entreprise à contacter" };
  for (const [cle, n] of Object.entries(dispo)) {
    const champ = document.querySelector(`[data-limite="${cle}"]`);
    const etiquette = document.querySelector(`[data-limite-max="${cle}"]`);
    if (!champ || typeof n !== "number") continue;
    const plafond = parseInt(champ.dataset.plafond, 10) || n;
    const maximum = Math.min(plafond, n);
    champ.max = String(Math.max(maximum, 1));
    if (maximum >= 1 && parseInt(champ.value, 10) > maximum) champ.value = maximum;
    if (etiquette) {
      etiquette.textContent = maximum < 1 ? textes[cle]
        : `max ${maximum}${maximum < plafond ? `, ${n} disponible${n > 1 ? "s" : ""}` : ""}`;
    }
  }
}

/* Emails non validés : mention, validation manuelle une entreprise à la fois */
function rendreAValider() {
  const carte = document.querySelector("[data-a-valider]");
  const liste = document.querySelector('[data-list="a-valider"]');
  if (!carte || !liste) return;
  carte.hidden = aValider.length === 0;
  const nb = document.querySelector("[data-a-valider-nombre]");
  if (nb) nb.textContent = fmt(aValider.length);
  liste.innerHTML = aValider.map(e => `
    <div class="a-valider__ligne">
      <div><div class="trow__name">${esc(e.nom)}</div><div class="trow__sub">${esc(e.ville)}</div></div>
      <div class="trow__mail">${e.emails.map(esc).join(", ")}</div>
      <span class="chip chip--gris">non validé</span>
      <button class="btn btn--sm" data-valider="${e.id}">Valider</button>
    </div>`).join("");
}

function fmt(n) { return (n ?? 0).toLocaleString("fr-FR"); }
function esc(s) {
  return String(s).replace(/[&<>"]/g, m => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[m]));
}

export const Spontanees = {
  async charger() {
    try { stats = await api.spStats(); } catch (_) { stats = null; }
    try { compte = (await api.compteEnvoi()).compte; } catch (_) { compte = null; }
    try { aValider = await api.spAValider(); } catch (_) { aValider = []; }
    rendreAValider();
    if (!this._brancheValider) {
      const liste = document.querySelector('[data-list="a-valider"]');
      if (liste) liste.addEventListener("click", async e => {
        const id = e.target.closest("[data-valider]")?.dataset.valider;
        if (!id) return;
        try { await api.spValider(parseInt(id, 10)); } catch (err) { alert(err.message); }
        this.charger();
      });
      this._brancheValider = true;
    }
    rendreModeTest();
    rendreMaximums();
    rendreKpis();
    rendreTable();
    rendrePipe();
  },

  setFiltre(f) { filtre = f; rendreTable(); },
  // Met à jour les cartes du pipeline depuis un état frais (appelé par le polling)
  majPipe(etatFrais) {
    stats = { ...(stats || {}), ...etatFrais };
    rendrePipe();
    rendreModeTest();
  },

  async action(nom) {
    try {
      const cle = { fetch: "entreprises", scraper: "scrapees", envoyer: "mails", revalider: "revalidations" }[nom];
      const lancer = { fetch: api.spFetch, scraper: api.spScraper, envoyer: api.spEnvoyer,
                       revalider: api.spRevalider }[nom];
      if (lancer) {
        const demandee = limite(cle);
        confirmerLancement(cle, demandee, await lancer(demandee));
      }
      this.charger();
    } catch (e) {
      alert(e.message);
    }
  },
};

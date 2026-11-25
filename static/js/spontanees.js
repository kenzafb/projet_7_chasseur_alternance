/* ============================================================================
   spontanees.js — Entreprises à contacter (D148) : trois étapes (trouver,
   chercher les emails, envoyer), entreprises rangées par moyen de contact
   ============================================================================ */
import { api, limite, confirmerLancement, majCompteur, lienSur } from "./api.js";

let stats = null;
let compte = null;    // compte d'envoi (mode test affiché en bandeau)
let aValider = [];    // entreprises aux emails non validés par l'IA
let filtre = "pretes";
let source = "all";   // origine : all | coeur | transverse | lba | autre (D190)
const aujourdhui = () => new Date().toLocaleDateString("sv-SE");   // AAAA-MM-JJ, jour local

/* Contacts de l'entreprise dans les autres modes : simple étiquette,
   l'envoi dans le mode courant n'est jamais bloqué */
const NOMS_MODES = { alternance: "alternance", job: "job", stage: "stage" };
function dateFr(jour) {
  const [a, m, j] = (jour || "").split("-");
  return a && m && j ? `${j}/${m}/${a}` : "";
}
export function etiquettesAutresModes(e) {
  return (e.contacts_autres_modes || []).map(c => {
    const date = dateFr(c.date);
    const texte = `déjà contactée en ${NOMS_MODES[c.mode] || c.mode}${date ? ` le ${date}` : ""}`;
    const titre = c.historique ? "Contact antérieur à la refonte (import de l'historique)" : texte;
    return ` <span class="chip chip--ambre" title="${esc(titre)}">${esc(texte)}</span>`;
  }).join("");
}

/* Comment chaque adresse a été validée (phase 7) */
const VALIDATION = {
  regle: ["validée par règle", "chip--vert"], ia: ["validée par l'IA", "chip--vert"],
  manuelle: ["validée à la main", "chip--vert"], lba: ["fournie par LBA", "chip--lba"],
  inconnue: ["adresse validée", "chip--gris"], douteuse: ["à valider", "chip--gris"],
  ecartee_ia: ["écartée par l'IA", "chip--rouge"], rejetee: ["rejetée à la main", "chip--rouge"],
};
function etiquetteAdresse(a) {
  const [texte, classe] = VALIDATION[a.validation] || [a.validation, "chip--gris"];
  return `<span class="chip ${classe}" title="${esc(texte)}">${esc(texte)}</span>${a.meilleur ? ' <span class="chip chip--ft" title="Meilleur contact selon l\'IA">meilleur contact</span>' : ""}`;
}
function listeAdresses(adresses) {
  return adresses.map(a => `<p class="ent__detail">${esc(a.adresse)} ${etiquetteAdresse(a)}</p>`).join("");
}

/* Page de l'entreprise sur La Bonne Alternance (D129) : « Postuler » si LBA
   a un contact (formulaire sur la page), sinon simple lien d'information */
function boutonLba(e) {
  if (!e.lba?.url) return "";
  // « J'ai postulé » à côté du bouton (D130) : l'entreprise passe « Envoyée » à la date choisie
  return e.lba.formulaire
    ? `<div class="ent__actions"><a class="btn btn--sm" href="${esc(e.lba.url)}" target="_blank" rel="noopener">Postuler sur La Bonne Alternance<span class="visuellement-cache"> (nouvel onglet)</span></a>
       <label class="volet__date"><span>le</span><input type="date" data-lba-date value="${aujourdhui()}" max="${aujourdhui()}" aria-label="Date de candidature"></label>
       <button type="button" class="btn btn--sm" data-lba-postule="${e.id}">J'ai postulé</button></div>`
    : `<a class="ent__lien" href="${esc(e.lba.url)}" target="_blank" rel="noopener">Voir sur La Bonne Alternance<span class="visuellement-cache"> (nouvel onglet)</span></a>`;
}

/* Onglet d'une entreprise à contacter : email validé, formulaire LBA, site carrières,
   adresse à valider (liste de son onglet : aValider), ou rien */
const ongletDe = e => e.email ? "pretes" : e.lba?.formulaire ? "lba" : lienSur(e.carrieres) ? "carrieres"
  : (e.adresses || []).length ? "a_valider" : "aucun";
const AIDES = {
  pretes: "Leur email est trouvé : le Chasseur peut leur envoyer ta candidature (étape 3).",
  lba: "Pas d'email, mais un formulaire sur La Bonne Alternance. Postule là-bas, puis indique-le ici.",
  a_valider: "Ces adresses ne partent jamais seules, ni par l'envoi groupé ni par la campagne. Valide ou rejette chacune.",
  carrieres: "Grandes entreprises (500 salariés et plus) : elles recrutent par leur site carrières. Postule là-bas, ce n'est pas un échec.",
  aucun: "Pas d'email gardé : site non vérifié, ou formulaire de contact seulement (lien sur l'entreprise).",
  faites: "Elles sont aussi dans tes Candidatures, où tu suis leurs réponses.",
};
/* Pourquoi l'entreprise est là (D190) : origines calculées par le serveur */
const deLOrigine = e => source === "all" || !Array.isArray(e.origines)
  || e.origines.some(o => o.cle === source || (source === "autre" && ["secteur", "tous", "sirene"].includes(o.cle)));
const CLASSE_ORIGINE = { coeur: "chip--vert", transverse: "chip--gris", lba: "chip--lba" };
const etiquettesOrigine = e => (e.origines || []).map(o =>
  ` <span class="chip ${CLASSE_ORIGINE[o.cle] || "chip--gris"}">${esc(o.texte)}</span>`).join("");
const ETAPES_SUIVI = { envoye: "envoyée", a_relancer: "à relancer", relancee: "relancée", entretien: "entretien",
  reponse: "réponse reçue", acceptee: "acceptée", refus: "refusée", bounce: "adresse invalide" };
let contactees = [];   // candidatures spontanées envoyées (suivi)

function ligne(e) {
  const onglet = ongletDe(e);
  const detail = onglet === "pretes"
    ? `Email trouvé : ${esc(e.email)}${e.email_lba ? " (fourni par La Bonne Alternance)" : ""}`
    : onglet === "lba" ? "Formulaire de candidature sur La Bonne Alternance"
    : onglet === "carrieres" ? "Grande entreprise : candidature sur son site carrières"
    : e.formulaire ? "Pas d'email, mais un formulaire de contact sur son site"
    : e.site_non_verifie ? "Site non vérifié : ni son SIREN ni son nom trouvés sur un site, aucun email gardé"
    : "Ni email ni formulaire trouvés";
  // Formulaire de contact du site vérifié : moyen de candidature à la main (D161)
  const formulaire = onglet !== "pretes" && lienSur(e.formulaire)
    ? `<a class="ent__lien" href="${esc(lienSur(e.formulaire))}" target="_blank" rel="noopener">Ouvrir le formulaire de contact<span class="visuellement-cache"> (nouvel onglet)</span></a>` : "";
  const recherche = `${e.nom || ""} ${e.ville || ""} ${e.email || ""}`.toLowerCase();
  return `<li class="ent" data-search-text="${esc(recherche)}">
      <span class="ent__initiale" aria-hidden="true">${esc((e.nom || "?").trim()[0] || "?")}</span>
      <div class="ent__corps">
        <p class="ent__nom">${esc(e.nom || "Entreprise sans nom")}${e.nom_etablissement ? ` <span class="ent__etablissement">· ${esc(e.nom_etablissement)}</span>` : ""}${etiquettesAutresModes(e)}</p>
        <p class="ent__detail ent__origines">${etiquettesOrigine(e)}</p>
        <p class="ent__detail">${detail}${e.ville ? ` · ${esc(e.ville)}` : ""}</p>
        ${onglet === "pretes" && (e.adresses || []).length > 1 ? `<details class="ent__adresses"><summary>Ses ${e.adresses.length} adresses</summary>${listeAdresses(e.adresses)}</details>`
          : onglet === "pretes" && (e.adresses || []).length ? `<p class="ent__detail">${etiquetteAdresse(e.adresses[0])}</p>` : ""}
        ${boutonLba(e)}
        ${onglet === "carrieres" ? `<div class="ent__actions"><a class="btn btn--sm" href="${esc(lienSur(e.carrieres))}" target="_blank" rel="noopener">Postuler sur leur site carrières<span class="visuellement-cache"> (nouvel onglet)</span></a></div>` : ""}
        ${formulaire}
      </div>
    </li>`;
}

function ligneContactee(c) {
  const recherche = `${c.entreprise || ""} ${c.contact || ""}`.toLowerCase();
  return `<li class="ent" data-search-text="${esc(recherche)}">
      <span class="ent__initiale" aria-hidden="true">${esc((c.entreprise || "?").trim()[0] || "?")}</span>
      <div class="ent__corps">
        <p class="ent__nom">${esc(c.entreprise || "Entreprise")}${etiquettesAutresModes(c)}</p>
        <p class="ent__detail">${c.historique ? "Contactée avant la refonte" : `Contactée${c.date ? ` le ${esc(dateFr(c.date))}` : ""}`}${
          c.contact ? ` · ${esc(c.contact)}` : ""} · ${esc(ETAPES_SUIVI[c.statut] || c.statut)}</p>
        <a class="ent__lien" href="#candidatures">Voir dans Candidatures</a>
      </div>
    </li>`;
}

function rendreTable() {
  const el = document.querySelector('[data-list="spontanees"]');
  if (!el || !stats) return;
  // Les prochaines entreprises (ordre de la recherche d'emails et de l'envoi) ;
  // une fois contactées, elles sont dans Candidatures (D110)
  const prochaines = stats.prochaines || [];
  const compte = { pretes: 0, lba: 0, carrieres: 0, aucun: 0 };
  prochaines.forEach(e => { compte[ongletDe(e)]++; });
  compte.faites = contactees.length;
  compte.a_valider = enAttente().length;   // toutes, pas seulement les prochaines
  for (const [k, n] of Object.entries(compte)) {
    const nb = document.querySelector(`[data-sp-nombre="${k}"]`);
    if (nb) nb.textContent = fmt(n);
  }
  document.querySelectorAll('[data-filters="spontanees"] [data-filter]').forEach(b =>
    b.setAttribute("aria-pressed", String(b.dataset.filter === filtre)));
  const aide = document.querySelector("[data-sp-aide]");
  if (aide) aide.textContent = AIDES[filtre] || "";
  const bloc = document.querySelector("[data-a-valider]");
  if (bloc) bloc.hidden = filtre !== "a_valider" || !enAttente().length;
  const origine = document.querySelector("[data-sp-origine]");
  if (origine) origine.hidden = filtre === "a_valider";   // toutes origines : aucune adresse oubliée
  const items = filtre === "a_valider" ? lignesAValider()
    : filtre === "faites" ? contactees.filter(deLOrigine).map(ligneContactee)
    : prochaines.filter(e => ongletDe(e) === filtre && deLOrigine(e)).map(ligne);
  el.innerHTML = items.length ? items.join("") : '<li class="ent-liste__vide">Rien ici pour l\'instant.</li>';
}

/* Ligne d'état de chaque étape, d'après les chiffres du mode */
function rendreKpis() {
  if (!stats) return;
  const set = (k, v) => { const e = document.querySelector(`[data-sp-etat="${k}"]`); if (e) e.textContent = v; };
  const n = (x, un, plusieurs) => `${fmt(x)} ${x > 1 ? plusieurs : un}`;
  const lba = stats.par_source?.lba?.entreprises;
  set("fetch", stats.raw ? `${n(stats.raw, "trouvée", "trouvées")}${lba ? `, dont ${fmt(lba)} par La Bonne Alternance` : ""}.`
    : "Aucune entreprise pour l'instant.");
  set("scraper", `${n(stats.avec_email, "email trouvé", "emails trouvés")}${stats.a_postuler_lba
    ? `, ${n(stats.a_postuler_lba, "entreprise joignable", "entreprises joignables")} par La Bonne Alternance` : ""}${
    stats.a_scraper ? `. ${n(stats.a_scraper, "entreprise", "entreprises")} à chercher.` : "."}`);
  set("envoyer", stats.a_envoyer ? `${n(stats.a_envoyer, "entreprise prête", "entreprises prêtes")} à recevoir ta candidature.`
    : "Aucune entreprise prête pour l'instant.");
  const btnEnvoyer = document.querySelector('[data-sp-bouton="envoyer"]');
  if (btnEnvoyer && !stats.en_cours) btnEnvoyer.disabled = !stats.a_envoyer;
  const btnTrouver = document.querySelector('[data-sp-bouton="fetch"]');
  if (btnTrouver) btnTrouver.textContent = stats.raw ? "En trouver d'autres" : "Trouver des entreprises";
  const raw = document.querySelector('[data-sp="raw"]');
  if (raw) raw.textContent = fmt(stats.raw);
  rendreParSource(stats.par_source || {});

  // Compteur du menu : entreprises prêtes à recevoir la candidature
  majCompteur("spontanees", stats.a_envoyer || 0, `${stats.a_envoyer || 0} prêtes à envoyer`);
  const ae = document.querySelector('[data-stat="avec_email"]');
  if (ae) ae.textContent = fmt(stats.avec_email);
  const en = document.querySelector('[data-stat="envoyes"]');
  if (en) en.textContent = fmt(stats.mail_envoye);
  const tx = stats.avec_email ? Math.round((stats.mail_envoye / stats.avec_email) * 100) : 0;
  const bar = document.querySelector('[data-stat="taux-bar"]');
  if (bar) bar.style.width = `${tx}%`;
  const lbl = document.querySelector('[data-stat="taux"]');
  if (lbl) lbl.textContent = `${tx} % de taux d'envoi`;
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

/* « Passer en envoi réel » : coupe le mode essai du compte d'envoi, après confirmation */
async function passerEnEnvoiReel() {
  if (!confirm("Les prochains envois partiront vraiment vers les entreprises. Continuer ?")) return;
  try { compte = (await api.modeTestCompte(false)).compte || { ...compte, mode_test: false }; }
  catch (err) { alert(err.message); return; }
  rendreModeTest();
}

/* Ce que « Trouver des entreprises » ne cherchera pas, dit avant tout lancement */
function rendreAvertissement() {
  const bandeau = document.querySelector("[data-sp-avertissement]");
  if (!bandeau) return;
  const texte = stats?.avertissement_recuperer || "";
  bandeau.hidden = !texte;
  bandeau.textContent = texte;
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

/* Onglet « Adresses à valider » (D216) : chaque adresse se valide ou se rejette ;
   une adresse rejetée reste visible en bas, validable quand même */
const enAttente = () => aValider.filter(e => e.emails.length || e.ecartees_ia.length);

function adresseAValider(e, a) {
  const bouton = (action, texte, classe = "") => `<button type="button" class="btn btn--sm${classe}" data-adresse-action="${action}"
      data-adresse="${esc(a.adresse)}" data-entreprise="${e.id}">${texte}<span class="visuellement-cache"> ${esc(a.adresse)}</span></button>`;
  const boutons = a.validation === "douteuse" ? bouton("valider", "Valider") + bouton("rejeter", "Rejeter", " btn--ghost")
    : a.validation === "ecartee_ia" ? bouton("valider", "Valider quand même") + bouton("rejeter", "Rejeter", " btn--ghost")
    : a.validation === "rejetee" ? bouton("valider", "Valider quand même") : "";
  return `<div class="ent__actions a-valider__adresse"><span class="a-valider__email">${esc(a.adresse)}</span> ${etiquetteAdresse(a)} ${boutons}</div>`;
}

function ligneAValider(e, adresses) {
  const recherche = `${e.nom || ""} ${e.ville || ""} ${adresses.map(a => a.adresse).join(" ")}`.toLowerCase();
  const site = lienSur(e.site);
  return `<li class="ent" data-search-text="${esc(recherche)}">
      <span class="ent__initiale" aria-hidden="true">${esc((e.nom || "?").trim()[0] || "?")}</span>
      <div class="ent__corps">
        <p class="ent__nom">${esc(e.nom || "Entreprise sans nom")}${e.a_la_main ? ' <span class="chip chip--ambre">site reconnu à son titre seul</span>' : ""}</p>
        <p class="ent__detail">${esc([e.ville, e.preuve_site].filter(Boolean).join(" · "))}</p>
        ${site ? `<a class="ent__lien" href="${esc(site)}" target="_blank" rel="noopener">${esc(e.site)}<span class="visuellement-cache"> (nouvel onglet)</span></a>` : ""}
        ${adresses.map(a => adresseAValider(e, a)).join("")}
        ${adresses.filter(a => a.validation === "douteuse").length > 1 ? `<div class="ent__actions"><button type="button" class="btn btn--sm" data-adresse-action="tout"
          data-entreprise="${e.id}">Tout valider</button></div>` : ""}
      </div>
    </li>`;
}

function lignesAValider() {
  const rejetees = aValider.filter(e => e.rejetees.length)
    .map(e => ligneAValider(e, e.rejetees.map(adresse => ({ adresse, validation: "rejetee" }))));
  return [...enAttente().map(e => ligneAValider(e, e.adresses)),
    ...(rejetees.length ? ['<li class="a-valider__titre">Adresses rejetées</li>', ...rejetees] : [])];
}

async function agirSurAdresse(bouton) {
  bouton.disabled = true;
  try {
    const agir = { valider: api.spValiderAdresse, rejeter: api.spRejeterAdresse, tout: api.spValider }[bouton.dataset.adresseAction];
    await agir(parseInt(bouton.dataset.entreprise, 10), bouton.dataset.adresse);
  } catch (err) { alert(err.message); }
}

/* Répartition par source : entreprises, emails, envoyés, réponses, entretiens */
function rendreParSource(ps) {
  const liste = document.querySelector('[data-list="par-source"]');
  if (!liste) return;
  const lignes = [["Sirene", ps.sirene], ["La Bonne Alternance", ps.lba], ["Les deux", ps.les_deux]];
  liste.innerHTML = lignes.filter(([, l]) => l).map(([nom, l]) => `
    <tr><th scope="row">${nom}</th><td>${fmt(l.entreprises)}</td><td>${fmt(l.avec_email)}</td>
      <td>${fmt(l.envoyes)}</td><td>${fmt(l.reponses)}</td><td>${fmt(l.entretiens)}</td></tr>`).join("");
}

/* Dernière campagne automatique (D213) */
const ETATS_CAMPAGNE = { en_cours: "en cours", terminee: "terminée", arretee: "arrêtée", erreur: "en erreur", interrompue: "interrompue" };
async function rendreCampagne() {
  const bloc = document.querySelector("[data-campagne]");
  if (!bloc) return;
  let c = null;
  try { c = await api.spCampagne(); } catch (_) { /* bloc masqué */ }
  bloc.hidden = !c;
  if (!c) return;
  bloc.querySelector("[data-campagne-titre]").textContent = `${c.debut}, ${ETATS_CAMPAGNE[c.etat] || c.etat}`;
  bloc.querySelector("[data-campagne-bilan]").innerHTML = Object.entries(c.bilan).map(([mode, b]) =>
    `<li>${esc(mode)} : ${fmt(b.examinees)} examinées, ${fmt(b.emails_trouves)} emails trouvés, ${fmt(b.envoyes)} envoyés${
      b.essai ? " (mode essai)" : ""}${b.erreur || b.validation || b.raison ? ` (${esc(b.erreur || b.validation || b.raison)})` : ""}</li>`).join("");
  bloc.querySelector("[data-campagne-journal]").textContent = c.journal;
}

function fmt(n) { return (n ?? 0).toLocaleString("fr-FR"); }
function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, m => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[m]));
}

export const Spontanees = {
  async charger() {
    try { stats = await api.spStats(); } catch (_) { stats = null; }
    try { compte = (await api.compteEnvoi()).compte; } catch (_) { compte = null; }
    try { aValider = await api.spAValider(); } catch (_) { aValider = []; }
    try { contactees = (await api.suivi()).filter(c => c.type === "spontanee"); } catch (_) { contactees = []; }
    if (!this._brancheEssai) {
      document.querySelector("[data-sp-envoi-reel]")?.addEventListener("click", passerEnEnvoiReel);
      document.querySelector("[data-sp-source]")?.addEventListener("change", e => { source = e.target.value; rendreTable(); });
      this._brancheEssai = true;
    }
    rendreCampagne();
    if (!this._brancheValider) {
      document.querySelector('[data-list="spontanees"]')?.addEventListener("click", async e => {
        const bouton = e.target.closest("[data-adresse-action]");
        if (!bouton) return;
        await agirSurAdresse(bouton);
        this.charger();
      });
      this._brancheValider = true;
    }
    // « J'ai postulé » après une candidature sur La Bonne Alternance (D130)
    if (!this._branchePostule) {
      document.querySelector('[data-list="spontanees"]')?.addEventListener("click", async e => {
        const bouton = e.target.closest("[data-lba-postule]");
        if (!bouton) return;
        const date = bouton.parentElement.querySelector("[data-lba-date]")?.value;
        bouton.disabled = true;
        try {
          await api.postuleLba(parseInt(bouton.dataset.lbaPostule, 10), date);
          document.dispatchEvent(new Event("candidatures:maj"));
          this.charger();
        } catch (err) {
          alert(err.message);
          bouton.disabled = false;
        }
      });
      this._branchePostule = true;
    }
    rendreModeTest();
    rendreAvertissement();
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

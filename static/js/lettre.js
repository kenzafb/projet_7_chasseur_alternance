/* ============================================================================
   lettre.js — page Ma lettre (D149, à la place de la fenêtre de D106)
   Paragraphe personnalisé modifiable à gauche, aperçu fidèle au PDF à
   droite (/api/lettre/apercu : même HTML que le PDF, police livrée),
   paragraphe surligné. Enregistrer insère le paragraphe dans la lettre type
   (/api/lettre/assembler) ; une lettre modifiée en entier est enregistrée
   telle quelle (/api/sauvegarder).
   ============================================================================ */
import { api } from "./api.js";

const IA_ACTIVE = () => document.documentElement.dataset.analyseIa !== "non";
/* Balise restée dans la lettre (portfolio vide, D125) */
const A_COMPLETER = { portfolio: "Ton portfolio est vide (Mon profil, partie Toi) : la balise {portfolio} reste dans la lettre, à compléter" };
/* Entreprise inconnue (D138) : formulations neutres déjà dans la lettre (mêmes textes que shared/offres.py) */
const INFO_DESTINATAIRE = "Le contact de l'entreprise n'est pas donné dans l'offre : la lettre est adressée au service recrutement.";
const INFO_ENTREPRISE = "Le nom de l'entreprise n'est pas donné dans l'offre : la lettre parle de « votre entreprise ».";

const $ = sel => document.querySelector(sel);
const etat = {
  id: null,
  offre: null,
  entiere: false,       // la lettre entière a été modifiée à la main : c'est elle qui compte
  lettre: "",           // dernière lettre assemblée ou enregistrée
  retour: "offres",
  version: 0,
};
let minuteurApercu = null;

/* Message court en haut de page (enregistrée, erreur...) */
function annoncer(texte, ok = true) {
  const el = $("[data-lettre-etat]");
  el.textContent = texte;
  el.classList.toggle("is-ok", ok);
  el.classList.toggle("is-ko", !ok);
}

function infosDe(offre, texte) {
  if (!offre || offre.entreprise_connue !== false || !texte) return [];
  return [texte.includes("À l'attention du service recrutement") ? INFO_DESTINATAIRE : null,
          texte.includes("votre entreprise") ? INFO_ENTREPRISE : null].filter(Boolean);
}

/* Aperçu : même HTML que le PDF, mis à l'échelle de la colonne */
async function apercu() {
  const id = etat.id;
  if (!id) return;
  let r;
  try {
    r = await api.apercuLettre(id, $("[data-lettre-paragraphe]").value,
                               etat.entiere ? $("[data-lettre-texte]").value : null);
  } catch (e) {
    annoncer(`Aperçu impossible : ${e.message}`, false);
    return;
  }
  if (etat.id !== id) return;
  if (r.lettre && !etat.entiere) {
    etat.lettre = r.lettre;
    $("[data-lettre-texte]").value = r.lettre;
  }
  const iframe = $("[data-lettre-apercu]");
  iframe.srcdoc = r.html;
  const restes = (r.a_completer || []).map(b => A_COMPLETER[b]).filter(Boolean);
  const alerte = $("[data-lettre-alerte]");
  alerte.textContent = restes.join(" ; ");
  alerte.hidden = !restes.length;
  const infos = r.infos?.length ? r.infos : infosDe(etat.offre, r.lettre);
  const info = $("[data-lettre-info]");
  info.textContent = (infos || []).join(" ");
  info.hidden = !(infos || []).length;
}
function apercuBientot() {
  clearTimeout(minuteurApercu);
  minuteurApercu = setTimeout(apercu, 400);
}

/* La page A4 (21 cm, soit 794 px) tient dans la largeur de sa colonne */
function ajusterPapier() {
  const papier = $("[data-lettre-papier]");
  const iframe = $("[data-lettre-apercu]");
  const echelle = Math.min(1, papier.clientWidth / 794);
  let hauteur = 1123;
  try { hauteur = Math.max(1123, iframe.contentDocument.documentElement.scrollHeight); } catch (_) {}
  iframe.style.height = `${hauteur}px`;
  iframe.style.transform = `scale(${echelle})`;
  papier.style.height = `${Math.ceil(hauteur * echelle)}px`;
}

/* Paragraphe rédigé par l'IA locale : environ une minute, davantage si une
   notation d'offres occupe déjà l'IA */
async function rediger() {
  const id = etat.id;
  const zone = $("[data-lettre-redaction]");
  const debut = Date.now();
  let minuteur = null;
  const tic = () => {
    const s = Math.round((Date.now() - debut) / 1000);
    zone.textContent = `Le Chasseur écrit… ${s} s (environ une minute, davantage si des offres sont en train d'être notées).`;
    minuteur = setTimeout(tic, 1000);
  };
  tic();
  attendre(true);
  try {
    const { paragraphe, avertissement } = await api.paragrapheLettre(id);
    if (etat.id !== id) return;
    $("[data-lettre-paragraphe]").value = paragraphe;
    etat.version += 1;
    etat.entiere = false;
    $("[data-lettre-reprendre]").hidden = true;
    // Plus de 80 mots même après un second essai : gardé, avec un avertissement (D109)
    zone.textContent = avertissement || `Version ${etat.version}. Relis-la, change ce que tu veux, puis enregistre.`;
    apercu();
  } catch (e) {
    // Lettre type absente, sans {paragraphe}, IA indisponible : message, rien d'inventé
    zone.textContent = `Paragraphe non rédigé : ${e.message}`;
  } finally {
    clearTimeout(minuteur);
    attendre(false);
  }
}

/* Pendant la rédaction : ni enregistrement, ni PDF, ni nouvelle version */
function attendre(oui) {
  $("[data-lettre-paragraphe]").readOnly = oui;
  ["[data-lettre-enregistrer]", "[data-lettre-pdf]", "[data-lettre-regenerer]"].forEach(sel => {
    $(sel).disabled = oui || (sel === "[data-lettre-regenerer]" && !IA_ACTIVE());
  });
}

/* Enregistre ; renvoie la lettre enregistrée, ou null (message affiché, D133) */
async function enregistrer() {
  const id = etat.id;
  try {
    if (etat.entiere) {
      const lettre = $("[data-lettre-texte]").value;
      await api.sauvegarder({ id, lettre });
      etat.lettre = lettre;
    } else {
      const r = await api.assemblerLettre(id, $("[data-lettre-paragraphe]").value);
      etat.lettre = r.lettre;
      $("[data-lettre-texte]").value = r.lettre;
    }
  } catch (e) {
    annoncer(`Lettre non enregistrée : ${e.message}`, false);
    return null;
  }
  annoncer("Lettre enregistrée.");
  document.dispatchEvent(new Event("offres:maj"));
  return etat.lettre;
}

export const Lettre = {
  _branche: false,

  /* Ouvre la page de la lettre d'une offre ; retour : page d'où l'on vient */
  ouvrir(offre, retour = "offres") {
    if (!offre) return;
    Object.assign(etat, { id: offre.id, offre, entiere: false, lettre: offre.lettre || "", retour, version: 0 });
    $("[data-lettre-poste]").textContent = offre.titre || "cette offre";
    $("[data-lettre-retour]").setAttribute("href", `#${retour}`);
    $("[data-lettre-retour-texte]").textContent = retour === "candidatures" ? "Retour aux candidatures" : "Retour à l'offre";
    $("[data-lettre-paragraphe]").value = "";
    $("[data-lettre-texte]").value = offre.lettre || "";
    $("[data-lettre-redaction]").textContent = IA_ACTIVE() ? "" : "IA désactivée : écris le paragraphe toi-même.";
    $("[data-lettre-reprendre]").hidden = true;
    annoncer("");
    // Lettre déjà enregistrée : c'est elle qu'on montre ; sinon le paragraphe est rédigé tout de suite
    if (offre.lettre) {
      etat.entiere = true;
      $("[data-lettre-entiere]").open = true;
      $("[data-lettre-reprendre]").hidden = false;
      $("[data-lettre-aide]").textContent = "Ta lettre pour cette offre est déjà enregistrée, ci-dessous. "
        + "Propose une autre version du paragraphe pour la réécrire.";
      apercu();
    } else {
      $("[data-lettre-entiere]").open = false;
      $("[data-lettre-aide]").textContent = "Le Chasseur l'écrit à partir de l'offre et de ton profil. Relis-le et "
        + "change ce que tu veux : le reste de la lettre est ta lettre type.";
      apercu();
      if (IA_ACTIVE()) rediger();
    }
    location.hash = "lettre";
  },

  id: () => etat.id,

  brancher() {
    if (this._branche) return;
    this._branche = true;
    $("[data-lettre-apercu]").addEventListener("load", ajusterPapier);
    window.addEventListener("resize", ajusterPapier);
    $("[data-lettre-paragraphe]").addEventListener("input", () => {
      // Le paragraphe redevient la source : la lettre type avec ce paragraphe
      if (etat.entiere) { etat.entiere = false; $("[data-lettre-reprendre]").hidden = true; }
      apercuBientot();
    });
    $("[data-lettre-texte]").addEventListener("input", () => {
      etat.entiere = true;
      $("[data-lettre-reprendre]").hidden = false;
      apercuBientot();
    });
    $("[data-lettre-reprendre]").addEventListener("click", () => {
      etat.entiere = false;
      $("[data-lettre-reprendre]").hidden = true;
      apercu();
    });
    $("[data-lettre-regenerer]").addEventListener("click", rediger);
    $("[data-lettre-enregistrer]").addEventListener("click", enregistrer);
    $("[data-lettre-pdf]").addEventListener("click", async () => {
      const lettre = await enregistrer();
      if (!lettre) return;
      try { await api.telechargerPdf(etat.id, lettre); } catch (e) { annoncer(e.message, false); }
    });
    // « Modifier ma lettre type » : partie Tes documents du profil
    $("[data-lettre-type]").addEventListener("click", () =>
      document.dispatchEvent(new CustomEvent("profil:partie", { detail: "documents" })));
  },
};

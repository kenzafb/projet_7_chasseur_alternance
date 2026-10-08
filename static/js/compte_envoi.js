/* ============================================================================
   compte_envoi.js — section « Compte d'envoi » du profil
   Le mot de passe est en écriture seule : jamais prérempli, jamais relu.
   Le serveur ne renvoie que « configuré » et la date de dernière vérification.
   ============================================================================ */

import { api } from "./api.js";

const CHIFFREMENT = { 465: "ssl", 587: "starttls" };
let _branche = false;

const $ = sel => document.querySelector(sel);
const champ = nom => $(`[data-ce="${nom}"]`);
const presetChoisi = () => ($("[data-ce-preset]:checked") || {}).value || "gmail";

/* "AAAA-MM-JJ HH:MM" → "JJ/MM/AAAA à HH:MM" */
function dateLisible(t) {
  const m = /^(\d{4})-(\d{2})-(\d{2}) (\d{2}:\d{2})$/.exec(t || "");
  return m ? `${m[3]}/${m[2]}/${m[1]} à ${m[4]}` : t;
}

function message(texte, ok) {
  const el = $("[data-ce-message]");
  if (!el) return;
  el.textContent = texte || "";
  el.classList.toggle("is-ok", ok === true);
  el.classList.toggle("is-ko", ok === false);
}

function afficherPreset() {
  const autre = presetChoisi() === "autre";
  document.querySelectorAll("[data-ce-autre]").forEach(el => { el.style.display = autre ? "" : "none"; });
}

function rendre(r) {
  const etat = $("[data-ce-etat]");
  const form = $("[data-ce-formulaire]");
  if (!etat || !form) return;
  etat.classList.remove("is-ok", "is-ko");

  if (!r.disponible) {
    etat.textContent = r.raison;
    etat.classList.add("is-ko");
    form.style.display = "none";
    return;
  }
  form.style.display = "";
  const c = r.compte;
  if (!c) {
    etat.textContent = "Aucun compte configuré : les candidatures spontanées ne peuvent pas partir.";
  } else if (c.verifie) {
    etat.textContent = `${c.adresse} : configuré, vérifié le ${dateLisible(c.verifie_le)}.`;
    etat.classList.add("is-ok");
  } else {
    etat.textContent = `${c.adresse} : configuré, pas encore vérifié. Lance « Tester la connexion ».`;
    etat.classList.add("is-ko");
  }
  if (c && c.mode_test) etat.textContent += " 🧪 Mode test actif : les envois partent vers cette adresse.";

  const blocTest = $("[data-ce-mode-test-bloc]");
  if (blocTest) {
    blocTest.style.display = c ? "" : "none";   // sans compte, rien à régler
    blocTest.classList.toggle("is-on", !!(c && c.mode_test));
  }
  const caseTest = $("[data-ce-mode-test]");
  if (caseTest) caseTest.checked = !!(c && c.mode_test);

  const preset = c ? c.preset : "gmail";
  document.querySelectorAll("[data-ce-preset]").forEach(radio => { radio.checked = radio.value === preset; });
  champ("adresse").value = c ? c.adresse : "";
  champ("nom_affiche").value = c ? c.nom_affiche : "";
  champ("serveur").value = c && c.preset === "autre" ? c.serveur : "";
  champ("port").value = String(c && c.preset === "autre" ? c.port : 465);
  champ("identifiant").value = c && c.preset === "autre" && c.identifiant !== c.adresse ? c.identifiant : "";
  champ("mot_de_passe").value = "";
  const aide = $("[data-ce-mdp-aide]");
  if (aide) aide.textContent = c && c.mot_de_passe_configure ? "(enregistré ; vide = le garder)" : "";
  afficherPreset();
}

async function recharger() {
  try { rendre(await api.compteEnvoi()); } catch (e) { message(e.message, false); }
}

function corps() {
  const port = parseInt(champ("port").value, 10);
  const c = {
    preset: presetChoisi(),
    adresse: champ("adresse").value.trim(),
    nom_affiche: champ("nom_affiche").value.trim(),
  };
  if (c.preset === "autre") {
    Object.assign(c, {
      serveur: champ("serveur").value.trim(),
      port,
      chiffrement: CHIFFREMENT[port],
      identifiant: champ("identifiant").value.trim(),
    });
  }
  const mdp = champ("mot_de_passe").value;
  if (mdp) c.mot_de_passe = mdp;
  return c;
}

async function resultatTest(promesse) {
  const r = await promesse;
  await recharger();
  message(r.message, r.ok);
}

async function action(nom) {
  message("…");
  try {
    if (nom === "enregistrer") {
      await api.enregistrerCompte(corps());
      champ("mot_de_passe").value = "";
      await resultatTest(api.testerCompte());
    } else if (nom === "tester") {
      await resultatTest(api.testerCompte());
    } else if (nom === "mail_test") {
      await resultatTest(api.mailTestCompte());
    } else if (nom === "supprimer") {
      if (!confirm("Supprimer le compte d'envoi ? Les candidatures spontanées ne pourront plus partir.")) { message(""); return; }
      await api.supprimerCompte();
      await recharger();
      message("Compte supprimé.", true);
    }
  } catch (e) {
    message(e.message, false);
  }
}

export const CompteEnvoi = {
  async charger() {
    if (!_branche) {
      document.querySelectorAll("[data-ce-preset]").forEach(r => r.addEventListener("change", afficherPreset));
      document.querySelectorAll("[data-ce-action]").forEach(b =>
        b.addEventListener("click", () => action(b.dataset.ceAction)));
      const caseTest = $("[data-ce-mode-test]");
      if (caseTest) caseTest.addEventListener("change", async () => {
        try {
          await api.modeTestCompte(caseTest.checked);
          await recharger();
          message(caseTest.checked ? "Mode test activé : les envois partiront vers toi."
                                   : "Mode test coupé : les envois partiront vers les entreprises.", true);
        } catch (e) {
          caseTest.checked = !caseTest.checked;
          message(e.message, false);
        }
      });
      _branche = true;
    }
    await recharger();
  },
};

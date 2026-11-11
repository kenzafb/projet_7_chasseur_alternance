/* ============================================================================
   parametres.js — page Paramètres, commune aux trois modes (D122)
   Email de connexion, mot de passe, compte d'envoi. Les mots de passe saisis
   ne sont jamais gardés : formulaires vidés après chaque envoi.
   ============================================================================ */

import { api } from "./api.js";
import { CompteEnvoi } from "./compte_envoi.js";

const $ = sel => document.querySelector(sel);

function message(cle, texte, ok) {
  const el = $(`[data-compte-message="${cle}"]`);
  if (!el) return;
  el.textContent = texte || "";
  el.classList.toggle("is-ok", ok === true);
  el.classList.toggle("is-ko", ok === false);
}

async function afficherCompte() {
  try {
    const c = await api.compte();
    $("[data-compte-email]").textContent = c.email;
  } catch (_) {}
}

const ENVOIS = {
  email: async f => {
    const r = await api.changerEmail(f.email.value, f.mot_de_passe.value);
    $("[data-compte-email]").textContent = r.email;
    return `Email de connexion changé : ${r.email}.`;
  },
  mot_de_passe: async f => {
    await api.changerMotDePasse(f.ancien.value, f.nouveau.value, f.confirmation.value);
    await afficherCompte();
    return "Mot de passe changé. Tes autres sessions sont déconnectées.";
  },
};

export const Parametres = {
  _charge: false,

  async charger() {
    await afficherCompte();
    CompteEnvoi.charger();
    if (this._charge) return;
    this._charge = true;
    document.querySelectorAll("[data-compte-form]").forEach(form => {
      form.addEventListener("submit", async e => {
        e.preventDefault();
        const cle = form.dataset.compteForm;
        const bouton = form.querySelector('[type="submit"]');
        bouton.disabled = true;
        message(cle, "");
        try {
          message(cle, await ENVOIS[cle](form), true);
          form.reset();
        } catch (err) {
          message(cle, err.message, false);
        } finally {
          bouton.disabled = false;
        }
      });
    });
  },
};

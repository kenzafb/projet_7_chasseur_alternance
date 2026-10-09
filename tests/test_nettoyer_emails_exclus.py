"""scripts/nettoyer_emails_exclus.py : adresses exclues retirées des
entreprises déjà en base, rien d'écrit sans --appliquer (D47)."""

from database.connexion import SessionLocal
from database.entreprises_db import ajouter_entreprises, lire_entreprises
from database.models import Entreprise
from scripts.nettoyer_emails_exclus import nettoyer

SENTRY = "aa4c3f2b@o4506196830715904.ingest.us.sentry.io"


def test_liste_puis_applique(utilisateur):
    _, uid = utilisateur("a@test.fr", prenom="Alice")
    ajouter_entreprises(uid, [{"siret": f"S{i}", "nom": f"Ent {i}"} for i in range(3)])
    with SessionLocal() as db:
        lignes = db.query(Entreprise).order_by(Entreprise.id).all()
        lignes[0].emails_trouves = [SENTRY, "rh@ent0.fr"]
        lignes[1].emails_trouves = ["votre@email.com"]
        lignes[1].extra = {**lignes[1].extra, "emails_lba": ["votre@email.com"]}
        lignes[2].emails_trouves = ["contact@ent2.fr"]
        db.commit()
    sorties = []
    concernees = nettoyer(afficher=sorties.append)
    assert [c["retirees"] for c in concernees] == [[SENTRY], ["votre@email.com"]]
    assert "rien écrit" in sorties[-1]
    assert [e["emails_trouves"] for e in lire_entreprises(uid)][0] == [SENTRY, "rh@ent0.fr"]   # inchangé
    nettoyer(appliquer=True, afficher=sorties.append)
    ents = lire_entreprises(uid)
    assert [e["emails_trouves"] for e in ents] == [["rh@ent0.fr"], [], ["contact@ent2.fr"]]
    assert ents[1]["emails_lba"] == [] and ents[1]["_extra"]["emails_exclus_retires"] == ["votre@email.com"]
    assert "plus aucune adresse" in "\n".join(sorties)
    assert nettoyer(afficher=sorties.append) == []                     # second passage : rien


def test_adresses_contactees_exclues(utilisateur):
    """Phase 6b : les adresses contactées (historique importé compris) sont
    nettoyées par la même commande, tous modes, rien d'écrit sans --appliquer."""
    from database.dedup_db import ajouter_emails_contactes, lire_emails_contactes
    from scripts.nettoyer_emails_exclus import main, nettoyer_contactes
    _, uid = utilisateur("a@test.fr", prenom="Alice")
    wix = "1eeb89147c984dc6bc3ffafd9e6cd089@sentry.wixpress.com"
    ajouter_emails_contactes(uid, "alternance", [wix, "rh@acme.fr", "contact@monsite.com"])
    ajouter_emails_contactes(uid, "job", ["605a7b@sentry-next.wixpress.com", "jobs@beta.fr"])
    sorties = []
    entreprises, contactes = main(afficher=sorties.append)
    assert entreprises == []
    assert [(c["mode"], c["email"]) for c in contactes] == [
        ("alternance", wix), ("alternance", "contact@monsite.com"), ("job", "605a7b@sentry-next.wixpress.com")]
    assert "rien écrit" in sorties[-1] and len(lire_emails_contactes(uid, "alternance")) == 3   # inchangé
    nettoyer_contactes(appliquer=True, afficher=sorties.append)
    assert lire_emails_contactes(uid, "alternance") == {"rh@acme.fr"}
    assert lire_emails_contactes(uid, "job") == {"jobs@beta.fr"}
    assert "supprimées de la base" in sorties[-1]
    assert nettoyer_contactes(afficher=sorties.append) == []

var candidatures = [];
var filtreActif = 'tous';
var timers = {};

async function charger() {
    var r = await fetch('/api/candidatures');
    candidatures = await r.json();
    afficher();
    mettreAJourStats();
}

function mettreAJourStats() {
    document.getElementById('statTotal').textContent = candidatures.length;
    document.getElementById('statTop').textContent = candidatures.filter(function(c) { return c.score >= 7; }).length;
    document.getElementById('statEnv').textContent = candidatures.filter(function(c) { return c.statut === 'envoye'; }).length;
}

function filtrer(type) {
    filtreActif = type;
    document.querySelectorAll('.filtre').forEach(function(f) { f.classList.remove('actif'); });
    event.target.classList.add('actif');
    afficher();
}

function filtrerStatut(s) { filtreActif = s; afficher(); }

function afficher() {
    var conteneur = document.getElementById('offres');
    var liste = candidatures;
    if (filtreActif === 'haut') liste = candidatures.filter(function(c) { return c.score >= 8; });
    else if (filtreActif === 'moyen') liste = candidatures.filter(function(c) { return c.score >= 5 && c.score < 8; });
    else if (filtreActif === 'nouveau') liste = candidatures.filter(function(c) { return c.statut === 'nouveau'; });
    else if (filtreActif === 'envoye') liste = candidatures.filter(function(c) { return c.statut === 'envoye'; });
    liste.sort(function(a, b) { return b.score - a.score; });
    if (liste.length === 0) {
        conteneur.innerHTML = '<div class="empty"><div class="icon">🔍</div><p>Aucune offre trouvée.<br>Lance une nouvelle recherche pour commencer !</p></div>';
        return;
    }
    conteneur.innerHTML = liste.map(function(offre) { return construireOffre(offre); }).join('');
}

function construireOffre(o) {
    var scoreClass = o.score >= 8 ? 'haut' : (o.score >= 5 ? 'moyen' : 'bas');
    var statutClass = 'badge-' + (o.statut || 'nouveau');
    var statutLabels = {'nouveau': 'Nouvelle', 'en_cours': 'En cours', 'envoye': 'Envoyée', 'rejete': 'Rejetée', 'reponse': 'Réponse reçue', 'entretien': 'Entretien', 'refus': 'Refus'};
    var statutLabel = statutLabels[o.statut] || 'Nouvelle';
    var pointsForts = (o.points_forts || []).map(function(p) { return '<li>' + p + '</li>'; }).join('');
    var pointsFaibles = (o.points_faibles || []).map(function(p) { return '<li>' + p + '</li>'; }).join('');
    var lettre = (o.lettre || '').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    var emailCand = (o.email_candidature || '').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    var objetEmail = (o.objet_email || '').replace(/"/g, '&quot;');
    var dejAnalysee = o.resume_analyse && o.resume_analyse !== 'Non analysée' && o.resume_analyse !== 'Non analysee' && o.resume_analyse !== 'Analyse echouee';
    var inputStyle = 'width:100%;background:var(--bg);color:var(--text);border:1px solid var(--border);border-radius:var(--radius);padding:8px 12px;font-family:DM Mono,monospace;font-size:.76rem;outline:none;margin-bottom:8px';

    return '<div class="offre" id="offre-' + o.id + '">'
        + '<div class="offre-header" onclick="toggleOffre(\'' + o.id + '\')">'
        + '<div class="offre-left">'
        + '<div class="offre-titre">' + o.titre + '</div>'
        + '<div class="offre-meta">' + o.entreprise + ' · ' + o.lieu + ' · ' + o.source + ' · ' + o.date_trouvee + '</div>'
        + '</div>'
        + '<div class="offre-right">'
        + '<span class="badge-statut ' + statutClass + '">' + statutLabel + '</span>'
        + '<div class="score ' + scoreClass + '">' + o.score + '</div>'
        + (o.eligible === false ? '<span style="color:#ff6584;font-size:.65rem;border:1px solid rgba(255,101,132,.4);padding:2px 6px;border-radius:20px;background:rgba(255,101,132,.1)">Ineligible</span>' : '')
        + '</div></div>'
        + '<div class="offre-body" id="body-' + o.id + '">'

        // Analyse + Statut
        + '<div class="grid-2" style="margin-bottom:16px">'
        + '<div>'
        + '<div class="section-label">Analyse IA</div>'
        + '<div class="analyse-box">' + (o.resume_analyse || 'Non analysée') + '</div>'
        + (pointsForts ? '<ul class="points" style="margin-top:8px">' + pointsForts + '</ul>' : '')
        + (pointsFaibles ? '<ul class="points faibles" style="margin-top:4px">' + pointsFaibles + '</ul>' : '')
        + '<div style="margin-top:10px">'
        + '<a class="lien-offre" href="' + o.lien + '" target="_blank">Voir l\'offre →</a>'
        + '</div>'
        + '<div style="margin-top:8px">'
        + (dejAnalysee
            ? '<span style="font-size:.68rem;color:var(--muted)">✓ Déjà analysée</span>'
            : '<button class="btn btn-secondary" style="font-size:.7rem;padding:5px 10px" onclick="analyser(\'' + o.id + '\')">Analyser</button>')
        + '</div>'
        + '</div>'
        + '<div>'
        + '<div class="section-label">Statut candidature</div>'
        + '<div style="display:flex;flex-direction:column;gap:6px">'
        + '<select id="statut-' + o.id + '" onchange="changerStatut(\'' + o.id + '\')" style="background:var(--bg);color:var(--text);border:1px solid var(--border);border-radius:var(--radius);padding:6px 10px;font-family:DM Mono,monospace;font-size:.76rem;outline:none">'
        + '<option value="nouveau"' + (o.statut === 'nouveau' ? ' selected' : '') + '>Nouvelle</option>'
        + '<option value="en_cours"' + (o.statut === 'en_cours' ? ' selected' : '') + '>En cours</option>'
        + '<option value="envoye"' + (o.statut === 'envoye' ? ' selected' : '') + '>Envoyée</option>'
        + '<option value="reponse"' + (o.statut === 'reponse' ? ' selected' : '') + '>Réponse reçue</option>'
        + '<option value="entretien"' + (o.statut === 'entretien' ? ' selected' : '') + '>Entretien</option>'
        + '<option value="refus"' + (o.statut === 'refus' ? ' selected' : '') + '>Refus</option>'
        + '<option value="rejete"' + (o.statut === 'rejete' ? ' selected' : '') + '>Rejetée</option>'
        + '</select>'
        + '<input type="email" id="dest-' + o.id + '" placeholder="Email recruteur..." value="' + (o.email_recruteur || '') + '" style="' + inputStyle + '">'
        + '<button class="btn btn-primary" style="font-size:.72rem;width:100%" onclick="envoyerCandidature(\'' + o.id + '\')">Envoyer la candidature</button>'
        + (o.date_candidature ? '<span style="font-size:.68rem;color:var(--muted)">Envoyée le ' + o.date_candidature + '</span>' : '')
        + '</div>'
        + '</div>'
        + '</div>'

        // Lettre
        + '<div style="margin-bottom:16px">'
        + '<div class="section-label">Lettre de motivation <span style="font-size:.6rem;color:var(--muted)" id="statut-lettre-' + o.id + '"></span></div>'
        + '<textarea class="textarea-lettre" id="lettre-' + o.id + '" oninput="sauvegardeAuto(\'' + o.id + '\', \'lettre\')">' + lettre + '</textarea>'
        + '<div class="actions">'
        + '<button class="btn btn-primary" style="font-size:.72rem" onclick="genererLettre(\'' + o.id + '\')">Générer lettre</button>'
        + '<button class="btn btn-secondary" style="font-size:.72rem" onclick="telechargerPDF(\'' + o.id + '\')">PDF</button>'
        + (o.source === 'France Travail' ? '<button class="btn btn-primary" style="font-size:.72rem;background:#e8301e;border-color:#e8301e" onclick="postulerFranceTravail(\'' + o.id + '\', \'' + o.lien + '\')">Postuler sur France Travail</button>' : '')
        + '</div>'
        + '</div>'

        // Email avec champ objet séparé
        + '<div>'
        + '<div class="section-label">Email de candidature <span style="font-size:.6rem;color:var(--muted)" id="statut-email-' + o.id + '"></span></div>'
        + '<input type="text" id="objet-' + o.id + '" placeholder="Objet du mail (obligatoire)..." value="' + objetEmail + '" style="' + inputStyle + '" oninput="sauvegardeAuto(\'' + o.id + '\', \'objet\')">'
        + '<textarea class="textarea-lettre" id="email-' + o.id + '" style="min-height:140px" oninput="sauvegardeAuto(\'' + o.id + '\', \'email\')">' + emailCand + '</textarea>'
        + '<div class="actions">'
        + '<button class="btn btn-secondary" style="font-size:.72rem" onclick="genererEmail(\'' + o.id + '\')">Générer email</button>'
        + '</div>'
        + '</div>'

        + '</div></div>';
}

function toggleOffre(id) {
    var body = document.getElementById('body-' + id);
    if (body) body.classList.toggle('open');
}

function sauvegardeAuto(id, type) {
    var key = id + type;
    clearTimeout(timers[key]);
    var indicateur = document.getElementById('statut-' + type + '-' + id);
    if (indicateur) indicateur.textContent = '...';
    timers[key] = setTimeout(async function() {
        var payload = {id: id};
        if (type === 'lettre') {
            payload.lettre = document.getElementById('lettre-' + id).value;
            var c = candidatures.find(function(c) { return c.id === id; });
            if (c) c.lettre = payload.lettre;
        } else if (type === 'objet') {
            payload.objet_email = document.getElementById('objet-' + id).value;
            var c = candidatures.find(function(c) { return c.id === id; });
            if (c) c.objet_email = payload.objet_email;
        } else {
            payload.email_candidature = document.getElementById('email-' + id).value;
            var c = candidatures.find(function(c) { return c.id === id; });
            if (c) c.email_candidature = payload.email_candidature;
        }
        await fetch('/api/sauvegarder', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(payload)
        });
        if (indicateur) indicateur.textContent = '✓ sauvegardé';
        setTimeout(function() { if (indicateur) indicateur.textContent = ''; }, 2000);
    }, 2000);
}

async function lancerRecherche() {
    var btn = document.getElementById('btnRecherche');
    var status = document.getElementById('searchStatus');
    btn.disabled = true;
    status.textContent = 'Recherche en cours...';
    await fetch('/api/recherche', {method: 'POST'});
    var interval = setInterval(async function() {
        var r = await fetch('/api/statut_recherche');
        var s = await r.json();
        status.textContent = s.message || 'En cours...';
        if (!s.en_cours) {
            clearInterval(interval);
            btn.disabled = false;
            status.textContent = 'Terminé !';
            await charger();
            toast('Nouvelles offres chargées !', 'ok');
        }
    }, 3000);
}

async function genererLettre(id) {
    var btn = event.target;
    btn.disabled = true;
    btn.textContent = 'Génération...';
    toast('Génération lettre en cours...', 'ok');
    var r = await fetch('/api/generer_lettre', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({id: id})
    });
    var data = await r.json();
    if (data.lettre) {
        document.getElementById('lettre-' + id).value = data.lettre;
        var c = candidatures.find(function(c) { return c.id === id; });
        if (c) c.lettre = data.lettre;
        var indicateur = document.getElementById('statut-lettre-' + id);
        if (indicateur) indicateur.textContent = '✓ sauvegardée';
        toast('Lettre générée et sauvegardée !', 'ok');
    } else {
        toast('Erreur génération', 'err');
    }
    btn.disabled = false;
    btn.textContent = 'Générer lettre';
}

async function genererEmail(id) {
    var btn = event.target;
    btn.disabled = true;
    btn.textContent = 'Génération...';
    toast('Génération email en cours...', 'ok');
    var r = await fetch('/api/generer_email', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({id: id})
    });
    var data = await r.json();
    if (data.email) {
        // Extraire l'objet et le mettre dans sa case
        var lignes = data.email.split('\n');
        var objetTrouve = false;
        for (var i = 0; i < lignes.length; i++) {
            if (lignes[i].toLowerCase().startsWith('objet :') || lignes[i].toLowerCase().startsWith('objet:')) {
                var objetVal = lignes[i].split(':').slice(1).join(':').trim();
                var objetInput = document.getElementById('objet-' + id);
                if (objetInput) {
                    objetInput.value = objetVal;
                    // Sauvegarde objet
                    fetch('/api/sauvegarder', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:id,objet_email:objetVal})});
                }
                lignes.splice(i, 1);
                if (lignes[i] && lignes[i].trim() === '') lignes.splice(i, 1);
                objetTrouve = true;
                break;
            }
        }
        var corpsEmail = lignes.join('\n').trim();
        document.getElementById('email-' + id).value = corpsEmail;
        var c = candidatures.find(function(c) { return c.id === id; });
        if (c) c.email_candidature = corpsEmail;
        var indicateur = document.getElementById('statut-email-' + id);
        if (indicateur) indicateur.textContent = '✓ sauvegardé';
        toast('Email généré et sauvegardé !', 'ok');
    } else {
        toast('Erreur génération', 'err');
    }
    btn.disabled = false;
    btn.textContent = 'Générer email';
}

async function telechargerPDF(id) {
    var lettre = document.getElementById('lettre-' + id).value;
    if (!lettre.trim()) {
        toast('Génère d\'abord une lettre !', 'err');
        return;
    }
    await fetch('/api/sauvegarder', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({id: id, lettre: lettre})
    });
    var c = candidatures.find(function(c) { return c.id === id; });
    if (c) c.lettre = lettre;
    var r = await fetch('/api/telecharger_pdf', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({id: id, lettre: lettre})
    });
    if (r.ok) {
        var blob = await r.blob();
        var url = URL.createObjectURL(blob);
        var a = document.createElement('a');
        a.href = url;
        a.download = 'lettre.pdf';
        a.click();
        toast('PDF téléchargé !', 'ok');
    } else {
        toast('Erreur génération PDF', 'err');
    }
}

async function analyser(id) {
    toast('Analyse en cours...', 'ok');
    var r = await fetch('/api/analyser', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({id: id})
    });
    var data = await r.json();
    if (data.score) {
        var c = candidatures.find(function(c) { return c.id === id; });
        if (c) {
            c.score = data.score;
            c.verdict = data.verdict;
            c.eligible = data.eligible;
            c.points_forts = data.points_forts;
            c.points_faibles = data.points_faibles;
            c.resume_analyse = data.resume;
        }
        afficher();
        toast('Score : ' + data.score + '/10', 'ok');
    }
}

async function changerStatut(id) {
    var statut = document.getElementById('statut-' + id).value;
    await fetch('/api/maj_statut', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({id: id, statut: statut})
    });
    var c = candidatures.find(function(c) { return c.id === id; });
    if (c) c.statut = statut;
    mettreAJourStats();
    toast('Statut mis à jour !', 'ok');
}

async function envoyerCandidature(id) {
    var destinataire = document.getElementById('dest-' + id).value;
    var objet = document.getElementById('objet-' + id).value;
    if (!destinataire) { toast('Saisis l\'email du recruteur !', 'err'); return; }
    if (!objet.trim()) { toast('L\'objet est obligatoire !', 'err'); return; }
    var btn = event.target;
    btn.disabled = true;
    btn.textContent = 'Envoi...';
    toast('Envoi en cours...', 'ok');
    var r = await fetch('/api/envoyer_candidature', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({id: id, destinataire: destinataire, objet: objet})
    });
    var data = await r.json();
    if (data.succes) {
        var c = candidatures.find(function(c) { return c.id === id; });
        if (c) c.statut = 'envoye';
        afficher();
        mettreAJourStats();
        toast('Candidature envoyée !', 'ok');
    } else {
        toast('Erreur : ' + (data.erreur || 'inconnue'), 'err');
        btn.disabled = false;
        btn.textContent = 'Envoyer la candidature';
    }
}

async function postulerFranceTravail(id, lien) {
    var lettre = document.getElementById('lettre-' + id).value;
    if (!lettre.trim()) {
        toast('Génération de la lettre en cours...', 'ok');
        var r = await fetch('/api/generer_lettre', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({id: id})
        });
        var data = await r.json();
        if (data.lettre) {
            document.getElementById('lettre-' + id).value = data.lettre;
            var c = candidatures.find(function(c) { return c.id === id; });
            if (c) c.lettre = data.lettre;
        } else {
            toast('Erreur génération lettre', 'err');
            return;
        }
    }
    await telechargerPDF(id);
    setTimeout(function() { window.open(lien, '_blank'); }, 500);
    var c = candidatures.find(function(c) { return c.id === id; });
    if (c && c.statut === 'nouveau') {
        c.statut = 'en_cours';
        await fetch('/api/maj_statut', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({id: id, statut: 'en_cours'})
        });
        mettreAJourStats();
    }
    toast('PDF téléchargé — page France Travail ouverte !', 'ok');
}

function toast(msg, type) {
    var t = document.createElement('div');
    t.className = 'toast ' + type;
    t.textContent = msg;
    document.body.appendChild(t);
    setTimeout(function() { t.remove(); }, 3500);
}

charger();

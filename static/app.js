var candidatures = [];
var timers = {};
var sectionActive = 'offres';
var filtres = {score:'tous', zone:'tous', domaine:'tous', source:'tous'};
var filtreCand = 'tous';
var triActif = 'score';
var sidebarOpen = false;

function formatDate(d) {
    if (!d) return '';
    var mois = ['jan','fév','mar','avr','mai','jun','jul','aoû','sep','oct','nov','déc'];
    var parts = d.split('-');
    if (parts.length < 3) return d;
    return parts[2] + ' ' + mois[parseInt(parts[1])-1] + ' ' + parts[0];
}

// ─── SIDEBAR ─────────────────────────────────
function toggleSidebar() {
    sidebarOpen = !sidebarOpen;
    var sb = document.getElementById('sidebar');
    if (sidebarOpen) {
        sb.classList.remove('closing');
        sb.classList.add('open');
        document.getElementById('toggle-btn').textContent = '✕';
    } else {
        sb.classList.remove('open');
        sb.classList.add('closing');
        document.getElementById('toggle-btn').textContent = '☰';
    }
}

// ─── PANELS FILTRES/TRI ──────────────────────
function togglePanel(id) {
    ['panel-filtres','panel-tri'].forEach(function(p) {
        if (p !== id) document.getElementById(p).classList.remove('open');
    });
    document.getElementById(id).classList.toggle('open');
}

document.addEventListener('click', function(e) {
    if (!e.target.closest('#panel-filtres') && !e.target.closest('#btn-filtres'))
        document.getElementById('panel-filtres').classList.remove('open');
    if (!e.target.closest('#panel-tri') && !e.target.closest('#btn-tri'))
        document.getElementById('panel-tri').classList.remove('open');
});

// ─── TRI ─────────────────────────────────────
function setTri(type) {
    triActif = type;
    document.getElementById('tri-check-score').style.color = type==='score' ? 'var(--accent)' : 'transparent';
    document.getElementById('tri-check-date').style.color = type==='date' ? 'var(--accent)' : 'transparent';
    document.getElementById('tri-label').textContent = type==='score' ? 'Note' : 'Date';
    document.getElementById('panel-tri').classList.remove('open');
    afficherOffres();
}

// ─── FILTRES ─────────────────────────────────
function setFiltre(type, val, btn) {
    filtres[type] = val;
    var parent = btn.parentElement;
    parent.querySelectorAll('.fsm').forEach(function(b) { b.classList.remove('actif','actif-zone','actif-domaine'); });
    var cls = type==='zone' ? 'actif-zone' : type==='domaine' ? 'actif-domaine' : 'actif';
    btn.classList.add(cls);
    var nb = Object.values(filtres).filter(function(v){return v!=='tous';}).length;
    var fc = document.getElementById('filtres-count');
    fc.textContent = nb; fc.style.display = nb > 0 ? 'inline' : 'none';
    document.getElementById('panel-filtres').classList.remove('open');
    afficherOffres();
}

function reinitialiserFiltres() {
    filtres = {score:'tous', zone:'tous', domaine:'tous', source:'tous'};
    document.querySelectorAll('.fsm').forEach(function(b) {
        b.classList.remove('actif','actif-zone','actif-domaine');
        if (b.textContent === 'Tous') b.classList.add('actif');
    });
    document.getElementById('filtres-count').style.display = 'none';
    document.getElementById('panel-filtres').classList.remove('open');
    afficherOffres();
}

function setFiltreCand(val, btn) {
    filtreCand = val;
    btn.closest('.toolbar-filtres').querySelectorAll('.btn').forEach(function(b) {
        b.style.borderColor = ''; b.style.color = '';
    });
    btn.style.borderColor = 'var(--accent)'; btn.style.color = 'var(--accent)';
    afficherCandidatures();
}

// ─── NAVIGATION ──────────────────────────────
function afficherSection(section) {
    sectionActive = section;
    ['offres','candidatures','spontanees'].forEach(function(s) {
        document.getElementById('section-'+s).style.display = s===section ? 'block' : 'none';
        document.getElementById('nav-'+s).classList.toggle('active', s===section);
    });
    var titres = {offres:'Offres', candidatures:'Candidatures', spontanees:'Candidatures spontanées'};
    document.getElementById('page-title').textContent = titres[section];
    if (section==='candidatures') afficherCandidatures();
}

// ─── INIT ─────────────────────────────────────
async function charger() {
    var r = await fetch('/api/candidatures');
    candidatures = await r.json();
    mettreAJourStats();
    construireFiltresDynamiques();
    afficherOffres();
    afficherCandidatures();
}

// ─── STATS ───────────────────────────────────
function mettreAJourStats() {
    var actives = candidatures.filter(function(c){return !['envoye','reponse','entretien','refus','rejete'].includes(c.statut);});
    var env = candidatures.filter(function(c){return ['envoye','reponse','entretien','refus'].includes(c.statut);});
    document.getElementById('s-total').textContent = candidatures.length;
    document.getElementById('s-top').textContent = candidatures.filter(function(c){return c.score>=7;}).length;
    document.getElementById('s-env').textContent = env.length;
    document.getElementById('s-entr').textContent = candidatures.filter(function(c){return c.statut==='entretien';}).length;
    document.getElementById('badge-offres').textContent = actives.length;
    document.getElementById('badge-candidatures').textContent = env.length;
}

// ─── FILTRES DYNAMIQUES ──────────────────────
function construireFiltresDynamiques() {
    var zones = [...new Set(candidatures.map(function(c){return c.zone;}).filter(Boolean))].sort();
    var domaines = [...new Set(candidatures.map(function(c){return c.domaine;}).filter(Boolean))].sort();
    var sources = [...new Set(candidatures.map(function(c){return c.source;}).filter(Boolean))].sort();

    function build(elId, vals, type, cls) {
        var el = document.getElementById(elId);
        if (!el) return;
        el.innerHTML = '<button class="fsm actif" onclick="setFiltre(\''+type+'\',\'tous\',this)">Tous</button>';
        vals.forEach(function(v) {
            el.innerHTML += '<button class="fsm" onclick="setFiltre(\''+type+'\',\''+v+'\',this)">'+v+'</button>';
        });
    }
    build('filtres-zone', zones, 'zone', 'actif-zone');
    build('filtres-domaine', domaines, 'domaine', 'actif-domaine');
    build('filtres-source', sources, 'source', 'actif');
}

// ─── AFFICHAGE OFFRES ────────────────────────
function afficherOffres() {
    var liste = candidatures.filter(function(c){
        return !['envoye','reponse','entretien','refus'].includes(c.statut);
    });
    if (filtres.score==='haut') liste = liste.filter(function(c){return c.score>=8;});
    else if (filtres.score==='moyen') liste = liste.filter(function(c){return c.score>=5&&c.score<8;});
    else if (filtres.score==='bas') liste = liste.filter(function(c){return c.score<5;});
    if (filtres.zone!=='tous') liste = liste.filter(function(c){return c.zone===filtres.zone;});
    if (filtres.domaine!=='tous') liste = liste.filter(function(c){return c.domaine===filtres.domaine;});
    if (filtres.source!=='tous') liste = liste.filter(function(c){return c.source===filtres.source;});

    if (triActif==='date') liste.sort(function(a,b){return new Date(b.date_trouvee)-new Date(a.date_trouvee);});
    else liste.sort(function(a,b){return b.score-a.score;});

    var cnt = document.getElementById('offres-count');
    if (cnt) cnt.textContent = liste.length + ' offre' + (liste.length>1?'s':'');

    var el = document.getElementById('offres');
    if (liste.length===0) { el.innerHTML='<div class="empty"><div class="icon">🔍</div><p>Aucune offre.</p></div>'; return; }
    el.innerHTML = liste.map(construireOffre).join('');
}

// ─── AFFICHAGE CANDIDATURES ──────────────────
function afficherCandidatures() {
    var liste = candidatures.filter(function(c){return ['envoye','reponse','entretien','refus'].includes(c.statut);});
    if (filtreCand!=='tous') liste = liste.filter(function(c){return c.statut===filtreCand;});
    liste.sort(function(a,b){return new Date(b.date_candidature||0)-new Date(a.date_candidature||0);});
    var grid = document.getElementById('cand-grid');
    if (liste.length===0) { grid.innerHTML='<div class="empty" style="grid-column:1/-1"><div class="icon">📬</div><p>Aucune candidature envoyée.</p></div>'; return; }
    var sl = {envoye:'Envoyée',reponse:'Réponse reçue',entretien:'Entretien',refus:'Refus'};
    grid.innerHTML = liste.map(function(o) {
        return '<div class="cc">'
            + '<div class="cc-titre">'+o.titre+'</div>'
            + '<div class="cc-meta">'+o.entreprise+' · '+o.lieu+'</div>'
            + '<span class="badge-statut badge-'+o.statut+'">'+(sl[o.statut]||o.statut)+'</span>'
            + (o.date_candidature ? '<div class="cc-date">Envoyée le ' + formatDate(o.date_candidature) + '</div>' : '')
            + '<div class="cc-actions">'
            + '<a class="btn btn-secondary" style="font-size:.68rem;padding:4px 10px;text-decoration:none" href="'+o.lien+'" target="_blank">Voir l\'offre</a>'
            + '<select onchange="changerStatutCand(\''+o.id+'\',this.value)" style="background:var(--bg);color:var(--text);border:1px solid var(--border);border-radius:var(--radius);padding:4px 8px;font-family:DM Mono,monospace;font-size:.68rem;outline:none">'
            + '<option value="envoye"'+(o.statut==='envoye'?' selected':'')+'>Envoyée</option>'
            + '<option value="reponse"'+(o.statut==='reponse'?' selected':'')+'>Réponse reçue</option>'
            + '<option value="entretien"'+(o.statut==='entretien'?' selected':'')+'>Entretien</option>'
            + '<option value="refus"'+(o.statut==='refus'?' selected':'')+'>Refus</option>'
            + '</select></div></div>';
    }).join('');
}

async function changerStatutCand(id, statut) {
    await fetch('/api/maj_statut',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:id,statut:statut})});
    var c = candidatures.find(function(c){return c.id===id;});
    if (c) c.statut = statut;
    mettreAJourStats(); afficherCandidatures();
    toast('Statut mis à jour !','ok');
}

// ─── CONSTRUCTION OFFRE ──────────────────────
function construireOffre(o) {
    var sc = o.score>=8?'haut':(o.score>=5?'moyen':'bas');
    var sl = {nouveau:'Nouvelle',en_cours:'En cours',rejete:'Rejetée'};
    var pf = (o.points_forts||[]).map(function(p){return '<li>'+p+'</li>';}).join('');
    var pw = (o.points_faibles||[]).map(function(p){return '<li>'+p+'</li>';}).join('');
    var lt = (o.lettre||'').replace(/</g,'&lt;').replace(/>/g,'&gt;');
    var em = (o.email_candidature||'').replace(/</g,'&lt;').replace(/>/g,'&gt;');
    var obj = (o.objet_email||'').replace(/"/g,'&quot;');
    var da = o.resume_analyse && o.resume_analyse!=='Non analysée' && o.resume_analyse!=='Non analysee' && o.resume_analyse!=='Analyse echouee';

    return '<div class="offre" id="offre-'+o.id+'">'
        +'<div class="offre-header" onclick="toggleOffre(\''+o.id+'\')">'
        +'<div class="offre-left">'
        +'<div class="offre-titre">'+o.titre+'</div>'
        +'<div class="offre-meta">'+o.entreprise+' · '+o.lieu
        +(o.zone?' <span class="mtag mzone">'+o.zone+'</span>':'')
        +(o.domaine?' <span class="mtag mdom">'+o.domaine+'</span>':'')
        +' <span class="mtag msrc">'+o.source+'</span>'
        +' · '+formatDate(o.date_trouvee)+'</div></div>'
        +'<div class="offre-right">'
        +'<span class="badge-statut badge-'+(o.statut||'nouveau')+'">'+(sl[o.statut]||'Nouvelle')+'</span>'
        +'<div class="score '+sc+'">'+o.score+'</div>'
        +(o.eligible===false?'<span style="color:#ff6584;font-size:.6rem;border:1px solid rgba(255,101,132,.4);padding:1px 5px;border-radius:20px;background:rgba(255,101,132,.1)">✕</span>':'')
        +'</div></div>'
        +'<div class="offre-body" id="body-'+o.id+'">'
        +'<div class="grid-2" style="margin-bottom:14px">'
        +'<div><div class="sl">Analyse IA</div>'
        +'<div class="abox">'+(o.resume_analyse||'Non analysée')+'</div>'
        +(pf?'<ul class="points" style="margin-top:7px">'+pf+'</ul>':'')
        +(pw?'<ul class="points faibles" style="margin-top:3px">'+pw+'</ul>':'')
        +'<div style="margin-top:8px;display:flex;gap:8px;align-items:center">'
        +'<a class="lo" href="'+o.lien+'" target="_blank">Voir l\'offre →</a>'
        +(da?'<span style="font-size:.65rem;color:var(--muted)">✓ Analysée</span>'
            :'<button class="btn btn-secondary" style="font-size:.68rem;padding:4px 9px" onclick="analyser(\''+o.id+'\')">Analyser</button>')
        +'</div></div>'
        +'<div><div class="sl">Statut & envoi</div>'
        +'<div style="display:flex;flex-direction:column;gap:6px">'
        +'<select id="statut-'+o.id+'" onchange="changerStatut(\''+o.id+'\')" style="background:var(--bg);color:var(--text);border:1px solid var(--border);border-radius:var(--radius);padding:6px 10px;font-family:DM Mono,monospace;font-size:.74rem;outline:none">'
        +'<option value="nouveau"'+(o.statut==='nouveau'?' selected':'')+'>Nouvelle</option>'
        +'<option value="en_cours"'+(o.statut==='en_cours'?' selected':'')+'>En cours</option>'
        +'<option value="envoye"'+(o.statut==='envoye'?' selected':'')+'>Envoyée</option>'
        +'<option value="reponse"'+(o.statut==='reponse'?' selected':'')+'>Réponse reçue</option>'
        +'<option value="entretien"'+(o.statut==='entretien'?' selected':'')+'>Entretien</option>'
        +'<option value="refus"'+(o.statut==='refus'?' selected':'')+'>Refus</option>'
        +'<option value="rejete"'+(o.statut==='rejete'?' selected':'')+'>Rejetée</option>'
        +'</select>'
        +'<input type="email" id="dest-'+o.id+'" placeholder="Email recruteur..." value="'+(o.email_recruteur||'')+'" class="is">'
        +'<button class="btn btn-primary" style="font-size:.7rem;width:100%" onclick="envoyerCandidature(\''+o.id+'\')">✉ Envoyer</button>'
        +(o.date_candidature?'<span style="font-size:.65rem;color:var(--muted)">Envoyée le '+o.date_candidature+'</span>':'')
        +'</div></div></div>'
        +'<div style="margin-bottom:14px">'
        +'<div class="sl">Lettre <span style="font-size:.58rem;color:var(--muted)" id="statut-lettre-'+o.id+'"></span></div>'
        +'<textarea class="tl" id="lettre-'+o.id+'" oninput="sauvegardeAuto(\''+o.id+'\',\'lettre\')">'+lt+'</textarea>'
        +'<div class="actions">'
        +'<button class="btn btn-primary" style="font-size:.7rem" onclick="genererLettre(\''+o.id+'\')">Générer lettre</button>'
        +'<button class="btn btn-secondary" style="font-size:.7rem" onclick="telechargerPDF(\''+o.id+'\')">PDF</button>'
        +(o.source==='France Travail'?'<button class="btn btn-primary" style="font-size:.7rem;background:#e8301e;border-color:#e8301e" onclick="postulerFranceTravail(\''+o.id+'\',\''+o.lien+'\')">Postuler FT</button>':'')
        +'</div></div>'
        +'<div>'
        +'<div class="sl">Email <span style="font-size:.58rem;color:var(--muted)" id="statut-email-'+o.id+'"></span></div>'
        +'<input type="text" id="objet-'+o.id+'" placeholder="Objet (obligatoire)..." value="'+obj+'" class="is" oninput="sauvegardeAuto(\''+o.id+'\',\'objet\')">'
        +'<textarea class="tl" id="email-'+o.id+'" style="min-height:130px" oninput="sauvegardeAuto(\''+o.id+'\',\'email\')">'+em+'</textarea>'
        +'<div class="actions"><button class="btn btn-secondary" style="font-size:.7rem" onclick="genererEmail(\''+o.id+'\')">Générer email</button></div>'
        +'</div></div></div>';
}

function toggleOffre(id) {
    var b = document.getElementById('body-'+id);
    if (b) b.classList.toggle('open');
}

// ─── SAUVEGARDE AUTO ─────────────────────────
function sauvegardeAuto(id, type) {
    var key = id+type;
    clearTimeout(timers[key]);
    var ind = document.getElementById('statut-'+type+'-'+id);
    if (ind) ind.textContent = '...';
    timers[key] = setTimeout(async function() {
        var payload = {id:id};
        if (type==='lettre') { payload.lettre = document.getElementById('lettre-'+id).value; var c=candidatures.find(function(c){return c.id===id;}); if(c) c.lettre=payload.lettre; }
        else if (type==='objet') { payload.objet_email = document.getElementById('objet-'+id).value; var c=candidatures.find(function(c){return c.id===id;}); if(c) c.objet_email=payload.objet_email; }
        else { payload.email_candidature = document.getElementById('email-'+id).value; var c=candidatures.find(function(c){return c.id===id;}); if(c) c.email_candidature=payload.email_candidature; }
        await fetch('/api/sauvegarder',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
        var c = candidatures.find(function(c){return c.id===id;});
        if (c && c.statut==='nouveau') {
            c.statut='en_cours';
            fetch('/api/maj_statut',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:id,statut:'en_cours'})});
            var sel=document.getElementById('statut-'+id); if(sel) sel.value='en_cours';
            var offEl=document.getElementById('offre-'+id);
            if(offEl){var b=offEl.querySelector('.badge-statut');if(b){b.className='badge-statut badge-en_cours';b.textContent='En cours';}}
        }
        if (ind) { ind.textContent='✓'; setTimeout(function(){if(ind)ind.textContent='';},2000); }
    }, 2000);
}

// ─── RECHERCHE ───────────────────────────────
async function lancerRecherche() {
    var btn=document.getElementById('btnRecherche'), st=document.getElementById('searchStatus');
    btn.disabled=true; st.textContent='Recherche...';
    await fetch('/api/recherche',{method:'POST'});
    var iv=setInterval(async function(){
        var r=await fetch('/api/statut_recherche'), s=await r.json();
        st.textContent=s.message||'En cours...';
        if(!s.en_cours){clearInterval(iv);btn.disabled=false;st.textContent='Prêt';await charger();toast('Nouvelles offres chargées !','ok');}
    },3000);
}

// ─── GÉNÉRATION ──────────────────────────────
async function genererLettre(id) {
    var btn=event.target; btn.disabled=true; btn.textContent='...';
    toast('Génération lettre...','ok');
    var r=await fetch('/api/generer_lettre',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:id})});
    var data=await r.json();
    if(data.lettre){
        document.getElementById('lettre-'+id).value=data.lettre;
        var c=candidatures.find(function(c){return c.id===id;}); if(c) c.lettre=data.lettre;
        var ind=document.getElementById('statut-lettre-'+id); if(ind) ind.textContent='✓';
        toast('Lettre générée !','ok');
    } else toast('Erreur génération','err');
    btn.disabled=false; btn.textContent='Générer lettre';
}

async function genererEmail(id) {
    var btn=event.target; btn.disabled=true; btn.textContent='...';
    toast('Génération email...','ok');
    var r=await fetch('/api/generer_email',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:id})});
    var data=await r.json();
    if(data.email){
        var lignes=data.email.split('\n');
        for(var i=0;i<lignes.length;i++){
            if(lignes[i].toLowerCase().startsWith('objet :')||lignes[i].toLowerCase().startsWith('objet:')){
                var ov=lignes[i].split(':').slice(1).join(':').trim();
                var oi=document.getElementById('objet-'+id);
                if(oi){oi.value=ov;fetch('/api/sauvegarder',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:id,objet_email:ov})});}
                lignes.splice(i,1); if(lignes[i]&&lignes[i].trim()==='') lignes.splice(i,1); break;
            }
        }
        var corps=lignes.join('\n').trim();
        document.getElementById('email-'+id).value=corps;
        var c=candidatures.find(function(c){return c.id===id;}); if(c) c.email_candidature=corps;
        toast('Email généré !','ok');
    } else toast('Erreur génération','err');
    btn.disabled=false; btn.textContent='Générer email';
}

async function telechargerPDF(id) {
    var lt=document.getElementById('lettre-'+id).value;
    if(!lt.trim()){toast('Génère d\'abord une lettre !','err');return;}
    await fetch('/api/sauvegarder',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:id,lettre:lt})});
    var r=await fetch('/api/telecharger_pdf',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:id,lettre:lt})});
    if(r.ok){var blob=await r.blob(),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='lettre.pdf';a.click();toast('PDF téléchargé !','ok');}
    else toast('Erreur PDF','err');
}

async function postulerFranceTravail(id, lien) {
    window.open(lien,'_blank');
    var lt=document.getElementById('lettre-'+id).value;
    if(!lt.trim()){
        toast('Génération lettre...','ok');
        var r=await fetch('/api/generer_lettre',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:id})});
        var data=await r.json();
        if(data.lettre){document.getElementById('lettre-'+id).value=data.lettre;var c=candidatures.find(function(c){return c.id===id;});if(c)c.lettre=data.lettre;lt=data.lettre;}
        else{toast('Erreur lettre','err');return;}
    }
    await fetch('/api/sauvegarder',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:id,lettre:lt})});
    var r2=await fetch('/api/telecharger_pdf',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:id,lettre:lt})});
    if(r2.ok){var blob=await r2.blob(),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='lettre.pdf';a.click();}
    var c=candidatures.find(function(c){return c.id===id;});
    if(c&&c.statut==='nouveau'){c.statut='en_cours';fetch('/api/maj_statut',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:id,statut:'en_cours'})});mettreAJourStats();}
    toast('PDF téléchargé — France Travail ouvert !','ok');
}

async function analyser(id) {
    toast('Analyse en cours...','ok');
    var r=await fetch('/api/analyser',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:id})});
    var data=await r.json();
    if(data.score){
        var c=candidatures.find(function(c){return c.id===id;});
        if(c){c.score=data.score;c.verdict=data.verdict;c.eligible=data.eligible;c.points_forts=data.points_forts;c.points_faibles=data.points_faibles;c.resume_analyse=data.resume;}
        afficherOffres(); toast('Score : '+data.score+'/10','ok');
    }
}

async function changerStatut(id) {
    var statut=document.getElementById('statut-'+id).value;
    await fetch('/api/maj_statut',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:id,statut:statut})});
    var c=candidatures.find(function(c){return c.id===id;}); if(c) c.statut=statut;
    mettreAJourStats();
    if(['envoye','reponse','entretien','refus'].includes(statut)){afficherOffres();afficherCandidatures();toast('Déplacée dans Candidatures !','ok');}
    else toast('Statut mis à jour !','ok');
}

async function envoyerCandidature(id) {
    var dest=document.getElementById('dest-'+id).value, obj=document.getElementById('objet-'+id).value;
    if(!dest){toast('Saisis l\'email du recruteur !','err');return;}
    if(!obj.trim()){toast('L\'objet est obligatoire !','err');return;}
    var btn=event.target; btn.disabled=true; btn.textContent='Envoi...';
    toast('Envoi en cours...','ok');
    var r=await fetch('/api/envoyer_candidature',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:id,destinataire:dest,objet:obj})});
    var data=await r.json();
    if(data.succes){var c=candidatures.find(function(c){return c.id===id;});if(c)c.statut='envoye';mettreAJourStats();afficherOffres();afficherCandidatures();toast('Candidature envoyée !','ok');}
    else{toast('Erreur : '+(data.erreur||'inconnue'),'err');btn.disabled=false;btn.textContent='✉ Envoyer';}
}

function toast(msg, type) {
    var t=document.createElement('div'); t.className='toast '+type; t.textContent=msg;
    document.body.appendChild(t); setTimeout(function(){t.remove();},3500);
}

charger();

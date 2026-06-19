/* app.js — search page adapter (bridges index.html IDs to search logic) */
"use strict";

/* ── ID aliases matching index.html ─────────────────────────────── */
const ID = {
  promptInput:     "promptInput",
  promptError:     "promptErr",
  sectionAnalysis: "secAnalysis",
  catBox:          "langBadge",
  nlpGrid:         "nlpGrid",
  suggestSection:  "secSuggestions",
  suggestBox:      "suggGrid",
  sectionMissing:  "secMissing",
  dynamicForm:     "dynForm",
  formErrors:      "formErr",
  sectionComplete: "secComplete",
  sectionPrompt:   "secPrompt",
  optimizedPromptBox:"promptBox",
  sectionResults:  "secResults",
  resultsSummary:  "resSummary",
  noResults:       "noRes",
  resultsGrid:     "resGrid",
};

const el    = id => document.getElementById(ID[id] || id);
const showEl = id => el(id)?.classList.remove("d-none");
const hideEl = id => el(id)?.classList.add("d-none");
const showErr = (id, msg) => { const e=el(id); if(e){e.textContent=msg;e.classList.remove("d-none")} };

let _analysis=null, _profile=null, _results=null;

function setStep(n){
  for(let i=1;i<=4;i++){
    const s=document.getElementById("s"+i); if(!s) continue;
    s.classList.remove("active","done");
    if(i<n) s.classList.add("done");
    if(i===n) s.classList.add("active");
  }
}

/* ── Analyze ─────────────────────────────────────── */
async function analyzePrompt(){
  const prompt=(el("promptInput")?.value||"").trim();
  if(!prompt){toast("Décrivez votre recherche d'abord.","warning");return}
  hideEl("promptError"); spinner("Analyse NLP…"); setStep(1);
  try{
    const r=await fetch("/api/analyze",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({prompt})});
    const d=await r.json();
    if(!r.ok) throw new Error(d.error||"Erreur serveur");
    _analysis=d;
    renderNLP(d);
    showEl("sectionAnalysis");
    setStep(2);
    if(d.is_complete){hideEl("sectionMissing");showEl("sectionComplete")}
    else{showEl("sectionMissing");hideEl("sectionComplete");buildForm(d.form_fields||[])}
    if((d.suggestions||[]).length) renderSuggestions(d.suggestions);
    else hideEl("suggestSection");
  }catch(e){showErr("promptError",e.message)}
  finally{stopSpinner()}
}

function renderNLP(d){
  const lang=d.detected_language||"fr";
  const langLabels={fr:"🇫🇷 Français",en:"🇬🇧 English",ar:"🇸🇦 العربية",darija:"🇲🇦 Darija"};
  const conf=d.confidence||0;
  const confColor=conf>=80?"#10b981":conf>=60?"#f59e0b":"#ef4444";
  const catEl=el("catBox");
  if(catEl) catEl.innerHTML=`
    <div class="nlp-entity detected mb-3">
      <div class="nlp-icon" style="background:rgba(79,70,229,.15)">${d.category==="Appartement"?"🏠":"❓"}</div>
      <div class="flex-grow-1">
        <div class="nlp-lbl">Catégorie</div>
        <div class="d-flex align-items-center justify-content-between flex-wrap gap-2">
          <div class="nlp-val">${d.category}</div>
          <div class="d-flex align-items-center gap-2">
            <span class="lang-badge">${langLabels[lang]||lang}</span>
            <div style="min-width:80px;text-align:right">
              <div class="nlp-lbl">Confiance ${conf}%</div>
              <div class="conf-bar-bg"><div class="conf-bar" style="width:${conf}%;background:${confColor}"></div></div>
            </div>
          </div>
        </div>
      </div>
    </div>`;

  const grid=el("nlpGrid");
  if(!grid) return;
  const fields=[
    {k:"city",l:"Ville",icon:"📍",fmt:v=>v},
    {k:"budget",l:"Budget",icon:"💰",fmt:v=>Number(v).toLocaleString("fr-MA")+" MAD"},
    {k:"bedrooms",l:"Chambres",icon:"🛏️",fmt:v=>v+" ch."},
    {k:"surface",l:"Surface",icon:"📐",fmt:v=>v+" m²"},
  ];
  grid.innerHTML=fields.map(f=>{
    const det=d.detected?.[f.k]; const val=d[f.k];
    return `<div class="col-6 col-lg-3">
      <div class="nlp-entity ${det?"detected":"missing"}">
        <div class="nlp-icon" style="background:${det?"rgba(16,185,129,.12)":"rgba(245,158,11,.1)"};font-size:1rem">${f.icon}</div>
        <div>
          <div class="nlp-lbl">${f.l}</div>
          <div class="nlp-val" style="color:${det?"#10b981":"#f59e0b"}">${det?f.fmt(val):"—"}</div>
        </div>
        <div class="ms-auto">${det?'<i class="bi bi-check-circle-fill text-success"></i>':'<i class="bi bi-exclamation-circle text-warning"></i>'}</div>
      </div>
    </div>`;
  }).join("");
}

function renderSuggestions(suggestions){
  const box=el("suggestBox"); if(!box) return;
  box.innerHTML=`<div class="col-12"><p class="text-muted mb-2" style="font-size:.85rem"><i class="bi bi-lightbulb text-warning me-1"></i>Suggestions basées sur les statistiques :</p>
    <div>${suggestions.map(s=>`<span class="suggest-pill" onclick="applySug(${JSON.stringify(s).replace(/"/g,"&quot;")})">${s.label}</span>`).join("")}</div></div>`;
  showEl("suggestSection");
}

function applySug(s){
  const fe=document.getElementById("field_"+s.field);
  if(fe){fe.value=s.value;toast(`Valeur suggérée appliquée : ${s.label}`,"info")}
}

function buildForm(fields){
  const form=el("dynamicForm"); if(!form) return;
  const CITIES=["Casablanca","Dar Bouazza","Marrakech","Meknès","Tanger"];
  form.innerHTML=fields.map(f=>{
    if(f.type==="select") return `<div class="col-md-6">
      <label class="form-label">${f.label}</label>
      <select class="form-select" id="field_${f.field}" data-field="${f.field}">
        <option value="">— Choisissez —</option>
        ${CITIES.map(c=>`<option>${c}</option>`).join("")}
      </select></div>`;
    return `<div class="col-md-6">
      <label class="form-label">${f.label}</label>
      <input type="text" class="form-control" id="field_${f.field}" data-field="${f.field}" placeholder="${f.placeholder||""}"/>
      <div class="form-text" style="font-size:.72rem;color:var(--muted)">${f.min!=null?"Min "+Number(f.min).toLocaleString()+" — Max "+Number(f.max).toLocaleString():""}</div>
      <div class="invalid-feedback" id="err_${f.field}"></div></div>`;
  }).join("");
}

/* ── Complete profile ─────────────────────────────── */
async function completeProfile(){
  hideEl("formErrors"); spinner("Validation du profil…"); setStep(3);
  const form_data={};
  document.querySelectorAll("[data-field]").forEach(e=>{if(e.value.trim())form_data[e.dataset.field]=e.value.trim()});
  try{
    const r=await fetch("/api/complete-profile",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({initial:_analysis||{},form_data})});
    const d=await r.json();
    if(r.status===422&&d.errors){
      stopSpinner();setStep(2);
      Object.entries(d.errors).forEach(([k,msg])=>{
        const fe=document.getElementById("field_"+k);
        const err=document.getElementById("err_"+k);
        if(fe) fe.classList.add("is-invalid");
        if(err){err.textContent=msg;err.style.display="block"}
      });
      showErr("formErrors",Object.values(d.errors).join(" | ")); return;
    }
    if(!r.ok) throw new Error(d.error||"Erreur");
    _profile=d.profile;
    const pb=el("optimizedPromptBox"); if(pb) pb.textContent=d.optimized_prompt;
    showEl("sectionPrompt");
    await runRecommend(d.optimized_prompt);
  }catch(e){stopSpinner();setStep(2);showErr("formErrors",e.message)}
}

/* ── Recommend ───────────────────────────────────── */
async function runRecommend(optPrompt=""){
  spinner("Recherche des meilleurs appartements…");
  try{
    const r=await fetch("/api/recommend-ml",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({profile:_profile,top_n:5,
        original_query:el("promptInput")?.value||"",optimized_prompt:optPrompt})});
    const d=await r.json(); if(!r.ok) throw new Error(d.error||"Erreur");
    _results=d;
    // Save top IDs for map gold-star display (Priority 5)
    try{ sessionStorage.setItem("lastTopIds", JSON.stringify(d.top_ids||[])); }catch(e){}
    renderResults(d);
    showEl("sectionResults"); setStep(4);
    setTimeout(()=>document.getElementById("secResults")?.scrollIntoView({behavior:"smooth"}),200);
  }catch(e){showErr("promptError","Erreur: "+e.message)}
  finally{stopSpinner()}
}

function renderResults(data){
  const sum=el("resultsSummary");
  if(sum){sum.textContent=`${data.filtered} résultat(s) sur ${data.total_before}`;
    sum.className=`badge fs-6 ${data.filtered>0?"bg-success":"bg-secondary"}`}
  const noR=el("noResults");
  const rw=document.getElementById("relaxedWarn");
  if(data.message||!data.results?.length){
    if(noR){noR.textContent=data.message||"Aucun résultat.";noR.classList.remove("d-none")}
    document.getElementById("resGrid").innerHTML=""; return;
  }
  if(noR) noR.classList.add("d-none");
  if(data.is_relaxed && data.relaxed_msg){
    if(!rw){ const d2=document.createElement("div"); d2.id="relaxedWarn"; d2.className="alert alert-warning mb-3"; document.getElementById("secResults")?.prepend(d2); }
    const rw2=document.getElementById("relaxedWarn");
    if(rw2){rw2.innerHTML='<i class="bi bi-info-circle me-2"></i>'+data.relaxed_msg; rw2.classList.remove("d-none")}
  } else {
    if(rw) rw.classList.add("d-none");
  }
  const MEDALS={1:"🥇",2:"🥈",3:"🥉"};
  document.getElementById("resGrid").innerHTML=(data.results||[]).map(apt=>{
    const pct=Math.min(100,Math.max(0,apt.score_pct));
    const col=pct>=80?"#10b981":pct>=60?"#f59e0b":"#ef4444";
    const rc=apt.rank<=3?`rank-${apt.rank}`:"";
    const savings=apt.savings>0?`<div class="apt-savings"><i class="bi bi-arrow-down-circle-fill"></i>${Number(apt.savings).toLocaleString("fr-MA")} MAD d'économie</div>`:"";
    const isFav=apt.is_favorite;
    const expl=buildExplain(apt);
    const bd=Object.entries(apt.breakdown||{}).map(([k,v])=>{
      const ic={city:"📍",budget:"💰",surface:"📐",bedrooms:"🛏️"};
      const lb={city:"Ville",budget:"Budget",surface:"Surface",bedrooms:"Chambres"};
      return `<div class="bd-item"><span class="bd-lbl">${ic[k]||""} ${lb[k]||k}</span><span class="bd-val" style="color:${v>0?"#10b981":"#ef4444"}">${v>0?"+":""}${v}</span></div>`;
    }).join("");
    return `<div class="col-md-6 col-lg-4">
      <div class="apt-card ${rc}">
        <div class="apt-header">
          <div>
            <div class="d-flex align-items-center gap-2 mb-1">
              <span style="font-size:1.4rem">${MEDALS[apt.rank]||"#"+apt.rank}</span>
              <span class="badge bg-primary-subtle">#${apt.id} · ${apt.quartier}</span>
              <button class="fav-btn ${isFav?"active":""}" title="${isFav?"Retirer":"Ajouter"} favori"
                onclick="toggleFav(this,${apt.id},${JSON.stringify(apt).replace(/"/g,"&quot;")})">
                ${isFav?"❤️":"🤍"}</button>
            </div>
            <div class="apt-price">${Number(apt.prix).toLocaleString("fr-MA")} MAD</div>
            ${savings}
          </div>
          <div class="text-end">
            <div style="font-size:1.4rem;font-weight:800;color:${col}">${pct}%</div>
            <div style="font-size:.68rem;color:var(--muted)">compatibilité</div>
          </div>
        </div>
        <div class="apt-body">
          <span class="apt-badge"><i class="bi bi-geo-alt"></i>${apt.ville}</span>
          <span class="apt-badge"><i class="bi bi-rulers"></i>${apt.surface} m²</span>
          <span class="apt-badge"><i class="bi bi-door-open"></i>${apt.chambres} ch.</span>
          ${apt.ascenseur==="Yes"?'<span class="apt-badge">🛗 Asc.</span>':""}
          ${apt.parking==="Yes"?'<span class="apt-badge">🚗 Parking</span>':""}
          ${apt.terrasse==="Yes"?'<span class="apt-badge">☀️ Terrasse</span>':""}
        </div>
        ${expl?`<div class="px-3 pb-1">${expl}</div>`:""}
        ${buildMLInsight(apt)?`<div class="px-3 pb-1">${buildMLInsight(apt)}</div>`:""}
        <div class="apt-score">
          <div class="d-flex justify-content-between mb-1">
            <span style="font-size:.72rem;color:var(--muted);text-transform:uppercase;letter-spacing:.05em">Score IA</span>
            <span style="font-weight:700;color:${col}">${pct} pts</span>
          </div>
          <div class="score-bar-bg"><div class="score-bar" style="width:${pct}%;background:${col}"></div></div>
          ${bd?`<div class="breakdown-grid mt-1">${bd}</div>`:""}
        </div>
        <div class="px-3 pb-3 d-flex justify-content-between align-items-center flex-wrap gap-2">
          <div class="feedback-widget" data-apt-id="${apt.id}">
            <button class="btn btn-sm btn-outline-success like-btn" onclick="sendFeedback(${apt.id},{liked:1})" title="J'aime"><i class="bi bi-hand-thumbs-up"></i></button>
            <button class="btn btn-sm btn-outline-danger dislike-btn" onclick="sendFeedback(${apt.id},{liked:0})" title="Je n'aime pas"><i class="bi bi-hand-thumbs-down"></i></button>
            <span class="star-rating" data-apt-id="${apt.id}">
              ${[1,2,3,4,5].map(n=>`<i class="bi bi-star star-icon" data-val="${n}" onclick="sendFeedback(${apt.id},{rating:${n}})"></i>`).join("")}
            </span>
          </div>
          <button class="btn btn-sm btn-outline-primary" onclick="showSimilar(${apt.id})">
            <i class="bi bi-grid-3x3-gap me-1"></i>Similaires
          </button>
        </div>
        <div class="similar-section px-3 pb-3 d-none" id="similar-${apt.id}"></div>
      </div>
    </div>`;
  }).join("");
}

/* Feature 4 — Explainable AI */
function buildExplain(apt){
  const r=[]; const br=apt.breakdown||{};
  if(br.city>0)     r.push({ok:1,t:"Même ville"});
  if(br.budget>0)   r.push({ok:1,t:"Prix dans le budget"});
  if(br.budget<0)   r.push({ok:0,t:"Prix dépasse le budget"});
  if(br.surface>0)  r.push({ok:1,t:`Surface ${apt.surface} m² ✓`});
  if(br.bedrooms>0) r.push({ok:1,t:`${apt.chambres} chambre(s) ✓`});
  if(apt.savings>0) r.push({ok:1,t:`Économie ${Number(apt.savings).toLocaleString("fr-MA")} MAD`});
  if(!r.length) return "";
  return `<div class="explain-box">${r.slice(0,4).map(x=>`<div class="explain-item">${x.ok?"✅":"❌"} ${x.t}</div>`).join("")}</div>`;
}

/* ── Feedback (Phase 4: like/dislike/rating) ─────────────── */
async function sendFeedback(aptId, payload){
  const r=await fetch(`/api/feedback/${aptId}`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});
  if(r.status===401){toast("Connectez-vous pour laisser un avis","warning");return}
  const d=await r.json();
  if(!d.ok){toast(d.error||"Erreur","danger");return}

  const widget=document.querySelector(`.feedback-widget[data-apt-id="${aptId}"]`);
  if(!widget) return;

  if("liked" in payload){
    widget.querySelector(".like-btn").classList.toggle("active", payload.liked===1);
    widget.querySelector(".dislike-btn").classList.toggle("active", payload.liked===0);
  }
  if("rating" in payload){
    const stars=widget.querySelectorAll(".star-icon");
    stars.forEach(s=>{
      const filled=Number(s.dataset.val)<=payload.rating;
      s.classList.toggle("bi-star-fill",filled);
      s.classList.toggle("bi-star",!filled);
    });
  }
  toast("Merci pour votre avis !","success");
}

/* ── Similar Apartments (Phase 3) ─────────────────────────── */
async function showSimilar(aptId){
  const box=document.getElementById(`similar-${aptId}`);
  if(!box) return;
  if(!box.classList.contains("d-none")){ box.classList.add("d-none"); box.innerHTML=""; return; }

  box.classList.remove("d-none");
  box.innerHTML=`<div class="text-center text-muted py-3"><div class="spinner-border spinner-border-sm me-2"></div>Recherche d'appartements similaires…</div>`;

  const r=await fetch(`/api/similar/${aptId}?top_n=5`);
  const d=await r.json();
  if(d.error){box.innerHTML=`<div class="text-muted small">${d.error}</div>`;return}
  if(!d.similar?.length){box.innerHTML=`<div class="text-muted small">Aucun appartement similaire trouvé.</div>`;return}

  box.innerHTML=`<div class="similar-list mt-2">${d.similar.map(s=>`
    <div class="similar-item">
      <div class="d-flex justify-content-between align-items-center">
        <div>
          <span class="fw-semibold">#${s.id} — ${s.quartier}, ${s.ville}</span>
          <span class="badge bg-info-subtle ms-2">${s.similarity_pct}% similaire</span>
        </div>
        <div class="fw-bold">${Number(s.prix).toLocaleString("fr-MA")} MAD</div>
      </div>
      <div class="small text-muted mt-1">
        ${s.surface} m² · ${s.chambres} ch.
        ${s.why?.length ? " — " + s.why.join(", ") : ""}
      </div>
    </div>`).join("")}</div>`;
}

/* Favorites */
async function toggleFav(btn,aptId,apt){
  const isFav=btn.classList.contains("active");
  const r=await fetch(isFav?`/api/favorites/${aptId}`:"/api/favorites",{
    method:isFav?"DELETE":"POST",
    headers:{"Content-Type":"application/json"},
    body:isFav?null:JSON.stringify(apt)});
  if(r.status===401){toast("Connectez-vous pour gérer vos favoris","warning");return}
  const d=await r.json();
  if(d.ok||r.ok){
    btn.classList.toggle("active");
    btn.textContent=btn.classList.contains("active")?"❤️":"🤍";
    toast(isFav?"Retiré des favoris":"Ajouté aux favoris ❤️",isFav?"info":"success");
  }
}

/* PDF Export */
async function exportPDF(){
  if(!_profile||!_results){toast("Lancez d'abord une recherche","warning");return}
  spinner("Génération du PDF…");
  try{
    const r=await fetch("/api/export-pdf",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({profile:_profile,results:_results.results||[],
        original_query:el("promptInput")?.value||"",
        optimized_prompt:el("optimizedPromptBox")?.textContent||""})});
    if(!r.ok) throw new Error("Erreur PDF");
    const blob=await r.blob();
    const a=document.createElement("a");
    a.href=URL.createObjectURL(blob); a.download="rapport_appartements.pdf"; a.click();
    toast("PDF téléchargé ✅","success");
  }catch(e){toast("Erreur: "+e.message,"danger")}
  finally{stopSpinner()}
}

function resetAll(){
  const pi=el("promptInput"); if(pi) pi.value="";
  ["sectionAnalysis","sectionPrompt","sectionResults","promptError"].forEach(hideEl);
  _analysis=null; _profile=null; _results=null; setStep(1);
}

/* Feature 6 — ML Price Insight */
function buildMLInsight(apt){
  if(!apt.ml_deal_label) return "";
  const q=apt.ml_deal_quality;
  const color=q==="good_deal"?"rgba(16,185,129,.08)":q==="overpriced"?"rgba(239,68,68,.08)":"rgba(245,158,11,.08)";
  const border=q==="good_deal"?"rgba(16,185,129,.3)":q==="overpriced"?"rgba(239,68,68,.3)":"rgba(245,158,11,.3)";
  return `<div style="background:${color};border:1px solid ${border};border-radius:8px;padding:8px 12px;font-size:.8rem">
    <div style="font-weight:600;margin-bottom:3px">${apt.ml_deal_label}</div>
    <div style="color:var(--muted)">${apt.ml_deal_detail}</div>
    <div style="color:var(--muted);margin-top:2px">Prix estimé IA : <strong>${Number(apt.ml_predicted_price).toLocaleString("fr-MA")} MAD</strong></div>
  </div>`;
}

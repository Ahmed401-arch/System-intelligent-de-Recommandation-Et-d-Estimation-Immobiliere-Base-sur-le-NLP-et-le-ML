/* search.js — Main search page logic (Features 1-8, 11) */
"use strict";
let _analysis=null, _profile=null, _results=null;

function setStep(n){
  for(let i=1;i<=4;i++){
    const el=document.getElementById("s"+i);
    if(!el) continue;
    el.classList.remove("active","done");
    if(i<n) el.classList.add("done");
    if(i===n) el.classList.add("active");
  }
}

/* ── STEP 1: Analyze ─────────────────────────────── */
async function analyzePrompt(){
  const prompt=(document.getElementById("promptInput")?.value||"").trim();
  if(!prompt){toast("Décrivez votre recherche d'abord.","warning");return}
  hideEl("promptError"); spinner("Analyse NLP…"); setStep(1);
  try{
    const r=await fetch("/api/analyze",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({prompt})});
    const d=await r.json();
    if(!r.ok) throw new Error(d.error||"Erreur");
    _analysis=d;
    renderNLP(d);
    showEl("sectionAnalysis");
    setStep(2);
    if(d.is_complete){hideEl("sectionMissing");showEl("sectionComplete")}
    else{showEl("sectionMissing");hideEl("sectionComplete");buildForm(d.form_fields||[])}
    if((d.suggestions||[]).length) renderSuggestions(d.suggestions);
  }catch(e){showErr("promptError",e.message)}
  finally{stopSpinner()}
}

function renderNLP(d){
  const cat=d.category||"Autre";
  const conf=d.confidence||0;
  const confColor=conf>=80?"#10b981":conf>=60?"#f59e0b":"#ef4444";
  const lang=d.detected_language||"fr";
  const langLabels={fr:"🇫🇷 Français",en:"🇬🇧 English",ar:"🇸🇦 العربية",darija:"🇲🇦 Darija"};
  const catBox=document.getElementById("catBox");
  if(catBox) catBox.innerHTML=`
    <div class="nlp-entity detected p-3">
      <div class="nlp-icon" style="background:rgba(79,70,229,.15)">
        ${cat==="Appartement"?"🏠":cat==="Maison"?"🏡":"❓"}
      </div>
      <div class="flex-grow-1">
        <div class="nlp-lbl">Catégorie détectée</div>
        <div class="d-flex align-items-center justify-content-between flex-wrap gap-2">
          <div class="nlp-val">${cat}</div>
          <div class="d-flex align-items-center gap-2">
            <span class="lang-badge">${langLabels[lang]||lang}</span>
            <div style="min-width:90px;text-align:right">
              <div class="nlp-lbl">Confiance ${conf}%</div>
              <div class="conf-bar-bg"><div class="conf-bar" style="width:${conf}%;background:${confColor}"></div></div>
            </div>
          </div>
        </div>
      </div>
    </div>`;
  const fields=[
    {k:"city",   l:"Ville",   icon:"📍", fmt:v=>v},
    {k:"budget", l:"Budget",  icon:"💰", fmt:v=>formatPrice(v)},
    {k:"bedrooms",l:"Chambres",icon:"🛏️",fmt:v=>v+" ch."},
    {k:"surface",l:"Surface", icon:"📐", fmt:v=>v+" m²"},
  ];
  const grid=document.getElementById("nlpGrid");
  if(grid) grid.innerHTML=fields.map(f=>{
    const det=d.detected?.[f.k];
    const val=d[f.k];
    return `<div class="col-6 col-md-3">
      <div class="nlp-entity ${det?"detected":"missing"}">
        <div class="nlp-icon" style="background:${det?"rgba(16,185,129,.12)":"rgba(245,158,11,.1)}">${f.icon}</div>
        <div>
          <div class="nlp-lbl">${f.l}</div>
          <div class="nlp-val" style="color:${det?"#10b981":"#f59e0b"}">${det?f.fmt(val):"Non détecté"}</div>
        </div>
        <div class="ms-auto">${det?'<i class="bi bi-check-circle-fill text-success"></i>':'<i class="bi bi-exclamation-circle-fill text-warning"></i>'}</div>
      </div>
    </div>`;
  }).join("");
}

function renderSuggestions(suggestions){
  const box=document.getElementById("suggestBox");
  if(!box) return;
  box.innerHTML=suggestions.map(s=>`
    <div class="suggest-pill" onclick="applySuggestion(${JSON.stringify(s).replace(/"/g,'&quot;')})">
      <i class="bi bi-lightbulb"></i>${s.label}
    </div>`).join("");
  showEl("suggestSection");
}

function applySuggestion(s){
  if(!_analysis) return;
  if(s.field==="budget" && !_analysis.budget){
    const el=document.getElementById("field_budget");
    if(el){el.value=s.value;toast(`Budget suggéré : ${formatPrice(s.value)}`,"info")}
  }
}

function buildForm(fields){
  const form=document.getElementById("dynamicForm");
  if(!form) return;
  const CITIES=["Casablanca","Dar Bouazza","Marrakech","Meknès","Tanger"];
  form.innerHTML=fields.map(f=>{
    if(f.type==="select"){
      return `<div class="col-md-6">
        <label class="form-label">${f.label}</label>
        <select class="form-select" id="field_${f.field}" data-field="${f.field}">
          <option value="">— Choisissez —</option>
          ${CITIES.map(c=>`<option value="${c}">${c}</option>`).join("")}
        </select></div>`;
    }
    return `<div class="col-md-6">
      <label class="form-label">${f.label}</label>
      <input type="text" class="form-control" id="field_${f.field}" data-field="${f.field}" placeholder="${f.placeholder||""}"/>
      <div class="form-text" style="font-size:.73rem;color:var(--muted)">${f.min!=null?"Min "+Number(f.min).toLocaleString()+" — Max "+Number(f.max).toLocaleString():""}</div>
      <div class="invalid-feedback" id="err_${f.field}"></div>
    </div>`;
  }).join("");
}

/* ── STEP 2: Complete profile ─────────────────────── */
async function completeProfile(){
  hideEl("formErrors"); spinner("Validation…"); setStep(3);
  const initial=_analysis||{};
  const form_data={};
  document.querySelectorAll("[data-field]").forEach(el=>{
    if(el.value.trim()) form_data[el.dataset.field]=el.value.trim();
  });
  try{
    const r=await fetch("/api/complete-profile",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({initial,form_data})});
    const d=await r.json();
    if(r.status===422&&d.errors){
      stopSpinner(); setStep(2);
      Object.entries(d.errors).forEach(([k,msg])=>{
        const el=document.getElementById("field_"+k);
        const err=document.getElementById("err_"+k);
        if(el) el.classList.add("is-invalid");
        if(err){err.textContent=msg;err.style.display="block"}
      });
      showErr("formErrors",Object.values(d.errors).join(" | ")); return;
    }
    if(!r.ok) throw new Error(d.error||"Erreur");
    _profile=d.profile;
    document.getElementById("optimizedPromptBox").textContent=d.optimized_prompt;
    showEl("sectionPrompt");
    await runRecommend(d.optimized_prompt);
  }catch(e){stopSpinner();setStep(2);showErr("formErrors",e.message)}
}

/* ── STEP 3: Recommend ───────────────────────────── */
async function runRecommend(optPrompt=""){
  spinner("Recherche des meilleurs appartements…");
  try{
    const r=await fetch("/api/recommend",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({
        profile:_profile,top_n:5,
        original_query:document.getElementById("promptInput")?.value||"",
        optimized_prompt:optPrompt
      })});
    const d=await r.json();
    if(!r.ok) throw new Error(d.error||"Erreur");
    _results=d;
    renderResults(d);
    showEl("sectionResults");
    setStep(4);
    setTimeout(()=>document.getElementById("sectionResults")?.scrollIntoView({behavior:"smooth"}),200);
  }catch(e){showErr("promptError","Erreur: "+e.message)}
  finally{stopSpinner()}
}

function renderResults(data){
  const summary=document.getElementById("resultsSummary");
  if(summary){summary.textContent=`${data.filtered} résultat(s) sur ${data.total_before}`;summary.className=`badge fs-6 ${data.filtered>0?"bg-success":"bg-secondary"}`}
  const noRes=document.getElementById("noResults");
  if(data.message||!data.results?.length){
    if(noRes){noRes.textContent=data.message||"Aucun résultat.";showEl("noResults")}
    document.getElementById("resultsGrid").innerHTML=""; return;
  }
  if(noRes) hideEl("noResults");
  const MEDALS={1:"🥇",2:"🥈",3:"🥉"};
  document.getElementById("resultsGrid").innerHTML=(data.results||[]).map(apt=>{
    const pct=Math.min(100,Math.max(0,apt.score_pct));
    const col=scoreColor(pct);
    const rc=apt.rank<=3?`rank-${apt.rank}`:"";
    const savings=apt.savings>0?`<div class="apt-savings"><i class="bi bi-arrow-down-circle-fill"></i>${formatPrice(apt.savings)} d'économie</div>`:"";
    const isFav=apt.is_favorite;
    // Explainable AI (Feature 4)
    const expl=buildExplain(apt);
    const bd=Object.entries(apt.breakdown||{}).map(([k,v])=>{
      const icons={city:"📍",budget:"💰",surface:"📐",bedrooms:"🛏️"};
      const lbs={city:"Ville",budget:"Budget",surface:"Surface",bedrooms:"Chambres"};
      return `<div class="bd-item"><span class="bd-lbl">${icons[k]||""} ${lbs[k]||k}</span><span class="bd-val" style="color:${v>0?"#10b981":"#ef4444"}">${v>0?"+":""}${v}</span></div>`;
    }).join("");
    return `<div class="col-md-6 col-lg-4">
      <div class="apt-card ${rc}">
        <div class="apt-header">
          <div>
            <div class="d-flex align-items-center gap-2 mb-1">
              <span style="font-size:1.4rem">${MEDALS[apt.rank]||"#"+apt.rank}</span>
              <span class="badge bg-primary-subtle">#${apt.id} · ${apt.quartier}</span>
              <button class="fav-btn ${isFav?"active":""}" onclick="toggleFav(this,${JSON.stringify(apt).replace(/"/g,'&quot;')})" title="${isFav?"Retirer":"Ajouter"} favori">
                ${isFav?"❤️":"🤍"}
              </button>
            </div>
            <div class="apt-price">${formatPrice(apt.prix)}</div>
            ${savings}
          </div>
          <div class="text-end">
            <div style="font-size:1.45rem;font-weight:800;color:${col}">${pct}%</div>
            <div style="font-size:.68rem;color:var(--muted)">compatibilité</div>
          </div>
        </div>
        <div class="apt-body">
          <span class="apt-badge"><i class="bi bi-geo-alt"></i>${apt.ville}</span>
          <span class="apt-badge"><i class="bi bi-rulers"></i>${apt.surface} m²</span>
          <span class="apt-badge"><i class="bi bi-door-open"></i>${apt.chambres} ch.</span>
          ${apt.ascenseur==="Yes"?'<span class="apt-badge"><i class="bi bi-elevator"></i>Ascenseur</span>':""}
          ${apt.parking==="Yes"?'<span class="apt-badge"><i class="bi bi-car-front"></i>Parking</span>':""}
          ${apt.terrasse==="Yes"?'<span class="apt-badge"><i class="bi bi-sun"></i>Terrasse</span>':""}
        </div>
        ${expl?`<div class="px-3 pb-2">${expl}</div>`:""}
        <div class="apt-score">
          <div class="d-flex justify-content-between"><span style="font-size:.72rem;color:var(--muted);text-transform:uppercase">Score</span><span style="font-weight:700;color:${col}">${pct} pts</span></div>
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
            <i class="bi bi-grid-3x3-gap me-1"></i>Appartements similaires
          </button>
        </div>
        <div class="similar-section px-3 pb-3 d-none" id="similar-${apt.id}"></div>
      </div>
    </div>`;
  }).join("");
}

/* Feature 4 — Explainable AI */
function buildExplain(apt){
  const reasons=[];
  const br=apt.breakdown||{};
  if(br.city>0)      reasons.push({ok:true, txt:"Même ville"});
  if(br.budget>0)    reasons.push({ok:true, txt:"Prix dans le budget"});
  if(br.budget<0)    reasons.push({ok:false,txt:"Prix dépasse le budget"});
  if(br.surface>0)   reasons.push({ok:true, txt:`Surface ${apt.surface} m² correcte`});
  if(br.bedrooms>0)  reasons.push({ok:true, txt:`${apt.chambres} chambre(s) correspond`});
  if(apt.savings>0)  reasons.push({ok:true, txt:`Économie de ${formatPrice(apt.savings)}`});
  if(!reasons.length) return "";
  return `<div class="explain-box">${reasons.slice(0,4).map(r=>`
    <div class="explain-item">
      <span>${r.ok?"✅":"❌"}</span><span>${r.txt}</span>
    </div>`).join("")}</div>`;
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
        <div class="fw-bold">${formatPrice(s.prix)}</div>
      </div>
      <div class="small text-muted mt-1">
        ${s.surface} m² · ${s.chambres} ch.
        ${s.why?.length ? " — " + s.why.join(", ") : ""}
      </div>
    </div>`).join("")}</div>`;
}


async function toggleFav(btn, apt){
  const isFav=btn.classList.contains("active");
  const url=isFav?`/api/favorites/${apt.id}`:"/api/favorites";
  const method=isFav?"DELETE":"POST";
  const r=await fetch(url,{method,headers:{"Content-Type":"application/json"},body:isFav?null:JSON.stringify(apt)});
  const d=await r.json();
  if(r.status===401){toast("Connectez-vous pour gérer vos favoris","warning");return}
  if(d.ok||r.ok){
    btn.classList.toggle("active");
    btn.textContent=btn.classList.contains("active")?"❤️":"🤍";
    toast(isFav?"Retiré des favoris":"Ajouté aux favoris ❤️",isFav?"info":"success");
  }
}

/* ── PDF Export ──────────────────────────────────── */
async function exportPDF(){
  if(!_profile||!_results) return;
  spinner("Génération du PDF…");
  try{
    const r=await fetch("/api/export-pdf",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({profile:_profile,results:_results.results||[],
        original_query:document.getElementById("promptInput")?.value||"",
        optimized_prompt:document.getElementById("optimizedPromptBox")?.textContent||""})});
    if(!r.ok) throw new Error("Erreur PDF");
    const blob=await r.blob();
    const a=document.createElement("a");
    a.href=URL.createObjectURL(blob);
    a.download="rapport_appartements.pdf"; a.click();
    toast("PDF téléchargé ✅","success");
  }catch(e){toast("Erreur PDF: "+e.message,"danger")}
  finally{stopSpinner()}
}

function resetAll(){
  document.getElementById("promptInput").value="";
  ["sectionAnalysis","sectionPrompt","sectionResults","promptError"].forEach(hideEl);
  _analysis=null;_profile=null;_results=null;
  setStep(1);
}

function showEl(id){document.getElementById(id)?.classList.remove("d-none")}
function hideEl(id){document.getElementById(id)?.classList.add("d-none")}
function showErr(id,msg){const el=document.getElementById(id);if(el){el.textContent=msg;el.classList.remove("d-none")}}

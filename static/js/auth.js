/* auth.js — Global auth state, navbar update, toast, spinner, logout */
"use strict";
const $ = id => document.getElementById(id);
const show = id => $( id)?.classList.remove("d-none");
const hide = id => $( id)?.classList.add("d-none");

function spinner(msg="Traitement…"){$("spinnerMsg").textContent=msg;show("globalSpinner")}
function stopSpinner(){hide("globalSpinner")}

function toast(msg, type="success"){
  const id="t"+Date.now();
  const colors={success:"bg-success",danger:"bg-danger",warning:"bg-warning text-dark",info:"bg-info text-dark"};
  const el=document.createElement("div");
  el.id=id; el.className=`toast align-items-center text-white ${colors[type]||"bg-secondary"} border-0`;
  el.setAttribute("role","alert"); el.setAttribute("aria-live","assertive");
  el.innerHTML=`<div class="d-flex"><div class="toast-body">${msg}</div>
    <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button></div>`;
  document.getElementById("toast-container").appendChild(el);
  new bootstrap.Toast(el,{delay:3500}).show();
  setTimeout(()=>el.remove(),4000);
}

async function checkAuth(){
  try{
    const r=await fetch("/api/auth/me");
    const d=await r.json();
    if(d.logged_in){
      hide("guestLinks"); show("userLinks");
      const un=$("navUsername"); if(un) un.textContent=d.username;
      ["navHistory","navFavs","navDash"].forEach(id=>{
        const el=$(id); if(el) el.style.display="";
      });
      if(d.role==="admin"){
        const a=$("navAdmin"); if(a) a.style.display="";
      }
    } else {
      show("guestLinks"); hide("userLinks");
    }
  } catch(e){}
}

async function logout(){
  await fetch("/api/auth/logout",{method:"POST"});
  toast("Déconnexion réussie","info");
  setTimeout(()=>window.location.href="/",600);
}

function useEx(btn){
  const ta=document.getElementById("promptInput");
  if(ta){ta.value=btn.textContent.trim();ta.focus()}
}

function formatPrice(n){return Number(n).toLocaleString("fr-MA")+" MAD"}
function scoreColor(p){return p>=80?"#10b981":p>=60?"#f59e0b":"#ef4444"}

document.addEventListener("DOMContentLoaded",checkAuth);

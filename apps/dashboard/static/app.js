let chart;
const el = id => document.getElementById(id);
const val = (n, suffix = "") => n === undefined || n === null ? "—" : `${n}${suffix}`;
const gib = n => val(n, " GiB");

function createChart() {
  chart = new Chart(el("usageChart"), {type:"line",data:{labels:[],datasets:[
    {label:"CPU %",data:[],borderColor:"#63d4ff",tension:.25},{label:"RAM %",data:[],borderColor:"#a78bfa",tension:.25},{label:"GPU %",data:[],borderColor:"#46e6a6",tension:.25},{label:"GPU °C",data:[],borderColor:"#fbbf24",tension:.25,yAxisID:"temp"}
  ]},options:{responsive:true,maintainAspectRatio:false,animation:false,plugins:{legend:{labels:{color:"#cbd5e1"}}},scales:{x:{ticks:{color:"#94a3b8",maxTicksLimit:8}},y:{beginAtZero:true,max:100,ticks:{color:"#94a3b8"}},temp:{position:"right",beginAtZero:true,ticks:{color:"#fbbf24"},grid:{drawOnChartArea:false}}}}});
}
function system(data) {
  const g=data.gpu||{},r=data.ram||{},d=data.disk||{},n=data.network||{};
  el("meta").textContent=`${data.hostname||"unknown host"} · snapshot ${data.time||"unavailable"}`;
  el("cpu").textContent=val(data.cpu?.percent," %"); el("ram").textContent=val(r.percent," %"); el("ram-detail").textContent=`${gib(r.used)} / ${gib(r.total)}`;
  el("gpu").textContent=val(g.load," %"); el("gpu-detail").textContent=`${gib(g.vram_used)} / ${gib(g.vram_total)}`;
  el("temp").textContent=val(g.temperature," °C"); el("temp-detail").textContent=`${val(g.power," W")} · ${val(g.clock," MHz")}`;
  el("disk").textContent=`${val(d.percent," %")} · ${gib(d.used)} / ${gib(d.total)}`; el("net-recv").textContent=val(n.recv," MiB cumulative"); el("net-sent").textContent=val(n.sent," MiB cumulative");
  el("gpu-name").textContent=g.name||"N/A"; el("vram").textContent=`${gib(g.vram_used)} / ${gib(g.vram_total)}`; el("power").textContent=val(g.power," W"); el("clocks").textContent=`${val(g.clock," MHz")} core · ${val(g.memory_clock," MHz")} memory`;
}
function history(items) { chart.data.labels=items.map(x=>(x.time||"").slice(11)); chart.data.datasets[0].data=items.map(x=>x.cpu); chart.data.datasets[1].data=items.map(x=>x.ram); chart.data.datasets[2].data=items.map(x=>x.gpu?.load); chart.data.datasets[3].data=items.map(x=>x.gpu?.temperature); chart.update(); }
function services(items=[]) { el("services").innerHTML=items.map(x=>`<div class="service ${x.status==="running"?"ok":"bad"}"><span>●</span><b>${x.name}</b><small>${x.status}</small></div>`).join("")||"No service data"; }
function autonomy(data,events) { const records=Object.values(data.services||{}); const latest=records.map(x=>x.last_check).filter(Boolean).sort().at(-1); el("autonomy-count").textContent=`${records.length} services`; el("autonomy-check").textContent=latest||"No check recorded"; el("events").innerHTML=events.slice().reverse().map(x=>`<div class="event"><b>${x.event||"event"}</b><small>${x.time||""}${x.service?` · ${x.service}`:""}</small></div>`).join("")||"No events recorded"; }
function controlPanel() { document.querySelector("header").insertAdjacentHTML("afterend", `<section class="panel chart-panel"><h2>Service control</h2><p class="control-note">Tailnet-only access. Restart is limited to allowlisted services and every action is audited.</p><div class="services">${["router","agent","dashboard","ollama","llama-server","monitor","autonomy"].map(s=>`<button class="control" data-service="${s}">Restart ${s}</button>`).join("")}</div><small id="control-result"></small></section>`); document.querySelectorAll(".control").forEach(button=>button.onclick=async()=>{const service=button.dataset.service; if(!confirm(`Restart ${service}?`))return; button.disabled=true; try{const r=await fetch("/api/control/restart",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({service})});const d=await r.json();el("control-result").textContent=r.ok?`${service}: ${d.status}`:`${service}: ${d.detail||"request failed"}`;update()}catch(e){el("control-result").textContent=`${service}: network error`}finally{button.disabled=false}}); }
async function update() { try { const r=await fetch("/api/overview"); if(!r.ok) throw Error(r.status); const d=await r.json(); system(d.system||{}); history(d.history||[]); services(d.system?.services); autonomy(d.autonomy||{},d.autonomy_events||[]); el("freshness").textContent="Live";el("freshness").className="pill live"; } catch(e) {el("freshness").textContent="Unavailable";el("freshness").className="pill error";console.error(e);} }
window.onload=()=>{createChart();controlPanel();update();setInterval(update,5000)};

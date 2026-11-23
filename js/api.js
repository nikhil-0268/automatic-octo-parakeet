/* Shared HTTP adapter for the Flask + SQLite backend. No browser-local request data. */
"use strict";
(function () {
  const DEPOT = {lat:27.7010,lng:85.3350};
  const collectorNumber = id => Number(String(id).replace(/^COL-/i,''));
  const collectorCode = id => id == null ? null : `COL-${String(id).padStart(2,'0')}`;
  async function http(route, data) {
    let response;
    try { response=await fetch('/api/'+route,{method:data===undefined?'GET':'POST',credentials:'same-origin',headers:data===undefined?{}:{'Content-Type':'application/json'},body:data===undefined?undefined:JSON.stringify(data),signal:AbortSignal.timeout(15000)}); }
    catch { throw new Error('Cannot reach the backend. Start the app with npm start and open http://localhost:3000.'); }
    let result;
    try { result=await response.json(); } catch {throw new Error('The API is unavailable here. Open http://localhost:3000 instead of Live Server.');}
    if(!response.ok){const error=new Error(result.error?.message || 'The request failed.');error.status=response.status;throw error;}
    return result;
  }
  function ticket(t) {
    if(!t)return null;
    return {...t,bag_color:t.waste_type.toUpperCase(),status:({requested:'REQUESTED',assigned:'ASSIGNED',completed:'COLLECTED',cancelled:'CANCELLED',expired:'EXPIRED'})[t.status],collector_id:collectorCode(t.collector_id),accepted_at:t.assigned_at,collected_at:t.closed_at,household:Number.isFinite(t.lat)&&Number.isFinite(t.lng)?{owner_name:t.household_name,ward:`Ward ${t.ward}`,lat:t.lat,lng:t.lng}:null};
  }
  async function getHousehold(gate) {
    const h=await http('households/'+encodeURIComponent(String(gate).trim().toUpperCase()));
    const latest=h.active_ticket || h.latest_ticket;
    return {...h,owner_name:h.name,ward:`Ward ${h.ward}`,green_points:h.green_points_balance,active_request:latest&&['requested','assigned','completed'].includes(latest.status)?ticket(latest):null};
  }
  async function requestPickup(gate,bag) {
    const result=await http('requests',{gate_id:gate,waste_type:String(bag).toLowerCase()});
    if(result.duplicate)throw new Error(result.message);
    return ticket(result.ticket);
  }
  async function listOpenRequests(){const result=await http('requests?limit=500');return result.requests.filter(t=>['requested','assigned'].includes(t.status)).map(ticket);}
  async function activeTicket(gate){const h=await http('households/'+encodeURIComponent(gate));if(!h.active_ticket)throw new Error('This gate has no active pickup request.');return h.active_ticket;}
  async function acceptRequest(gate,id){const t=await activeTicket(gate);return ticket(await http(`requests/${t.id}/assign`,{collector_id:collectorNumber(id)}));}
  async function completeRequest(gate,id,clean){
    const scanned=window.prompt('Enter the Gate ID from the gate sticker to verify this pickup:');
    if(scanned===null)throw new Error('Pickup verification cancelled.');
    const t=await activeTicket(gate);
    return http(`requests/${t.id}/collect`,{collector_id:collectorNumber(id),scanned_gate_id:scanned.trim().toUpperCase(),segregation_verified:Boolean(clean)});
  }
  async function listLogs(id){const result=await http('collections?limit=500');return result.collections.filter(e=>e.collector_id===collectorNumber(id)).map(e=>({...e,owner_name:e.household_name,bag_color:e.waste_type.toUpperCase(),clean:e.segregation_verified,points_added:e.points_awarded,collector_id:collectorCode(e.collector_id)}));}
  function distanceKm(a,b){const rad=d=>d*Math.PI/180;const h=Math.sin(rad(b.lat-a.lat)/2)**2+Math.cos(rad(a.lat))*Math.cos(rad(b.lat))*Math.sin(rad(b.lng-a.lng)/2)**2;return 6371*2*Math.asin(Math.sqrt(Math.min(1,h)));}
  window.tringggApi={
    getHousehold,requestPickup,listOpenRequests,acceptRequest,completeRequest,listLogs,
    collectorLogin:(collector_id,pin)=>http('collector-login',{collector_id,pin}),
    collectorSession:()=>http('collector-session'),collectorLogout:()=>http('collector-logout',{}),
    updateCollectorLocation:(id,lat,lng,source='gps')=>http(`collectors/${collectorNumber(id)}/location`,{lat,lng,source}),
    getCollectorLocation:id=>http(`collectors/${collectorNumber(id)}/location`),
    resetDemo:async()=>{throw new Error('Database records are persistent. Demo reset is disabled.');},
    distanceKm,etaMinutes:km=>Math.max(1,Math.round(km*1.3/15*60)),DEPOT,
    STORE_KEY:'tringgg_backend',STREAK_FOR_DISCOUNT:8,NORMAL_BILL_NPR:400,DISCOUNT_BILL_NPR:320
  };
})();

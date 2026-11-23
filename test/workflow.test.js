const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../js/api.js'),'utf8');
test('HTTP adapter maps backend tickets and rewards for the existing dashboards',async()=>{
 const calls=[];
 const raw={id:7,gate_id:'KTM-W10-0042',waste_type:'both',status:'completed',collector_id:1,verified_clean:true,points_awarded:20};
 const context={window:{},AbortSignal,fetch:async(url,options)=>{calls.push({url,options});return {ok:true,json:async()=>({gate_id:raw.gate_id,name:'Sita',ward:10,green_points_balance:20,streak_count:1,monthly_bill_npr:400,active_ticket:null,latest_ticket:raw})};}};
 vm.runInNewContext(source,context);
 const house=await context.window.tringggApi.getHousehold('ktm-w10-0042');
 assert.equal(house.owner_name,'Sita');assert.equal(house.green_points,20);
 assert.equal(house.active_request.status,'COLLECTED');assert.equal(house.active_request.bag_color,'BOTH');assert.equal(house.active_request.collector_id,'COL-01');assert.equal(house.active_request.points_awarded,20);
 assert.equal(calls[0].url,'/api/households/KTM-W10-0042');assert.equal(calls[0].options.credentials,'same-origin');
});
test('all local HTML references resolve, including logo and QR sticker images',()=>{
 const root=path.resolve(__dirname,'..');
 for(const file of ['index.html','resident/dashboard.html','collector/index.html','qr/print.html']){
  const html=fs.readFileSync(path.join(root,file),'utf8');
  for(const match of html.matchAll(/(?:src|href)="([^"#?]+)[^"]*"/g)){
   const ref=match[1];if(/^(https?:|data:)/.test(ref))continue;
   assert.ok(fs.existsSync(path.resolve(root,path.dirname(file),ref)),`${file}: missing ${ref}`);
  }
 }
});

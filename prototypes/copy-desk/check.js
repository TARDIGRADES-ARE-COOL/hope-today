// Copy Desk puzzle checker: correctness + "feels like logic" rules.
// Usage: node check.js [copy-desk.html]
const fs=require('fs');const file=process.argv.slice(2).find(a=>!a.startsWith('-'))||'copy-desk.html';
const m=fs.readFileSync(file,'utf8').match(/<script id="engine">([\s\S]*?)<\/script>/);eval(m[1]);const E=globalThis.ENGINE;
// smallest number of visible clues that proves `card` in this state (0 = the count/kind rules alone)
function minProof(d,placed,card){const vis=E.visibleClues(d,placed);
  for(let size=0;size<=vis.length;size++){let found=false;
    (function pick(s,acc){if(found)return;if(acc.length===size){if(E.provable(d,acc,placed)[card])found=true;return;}
      for(let i=s;i<vis.length;i++){acc.push(vis[i]);pick(i+1,acc);acc.pop();}})(0,[]);
    if(found)return size;}
  return Infinity;}
const key=pl=>Object.entries(pl).sort().map(([c,k])=>c+"="+k).join();
let allOk=true;
for(const d of E.DAYS){
  const home=Object.fromEntries(d.cards.map(c=>[c.id,c.home]));const N=d.cards.length;
  const truthOk=d.clues.every(c=>c.f(home));
  const sols=E.solutions(d,d.clues.map(c=>c.id),{});
  const unique=sols.length===1&&d.cards.every(c=>sols[0][c.id]===home[c.id]);
  const seen=new Set();let dead=0,wrong=0,noHint=0,choiceStates=0,states=0,provSum=0;const q=[{}];
  while(q.length){const pl=q.pop();const k=key(pl);if(seen.has(k))continue;seen.add(k);
    const left=N-Object.keys(pl).length;if(!left)continue;states++;
    const p=E.provable(d,E.visibleClues(d,pl),pl);const ids=Object.keys(p);provSum+=ids.length;
    if(!ids.length){dead++;continue;}
    if(!E.bestHint(d,pl))noHint++;
    ids.forEach(id=>{if(p[id]!==home[id])wrong++;});
    if(left>=3&&new Set(ids.map(id=>p[id])).size>=2)choiceStates++;
    ids.forEach(id=>q.push(Object.assign({},pl,{[id]:p[id]})));}
  // Rule 6: can the whole puzzle be finished using at most ONE clue per move? If yes, it is a chain.
  const memo=new Map();
  function oneClueFinish(pl){const k=key(pl);if(memo.has(k))return memo.get(k);
    if(Object.keys(pl).length===N){memo.set(k,true);return true;}
    const p=E.provable(d,E.visibleClues(d,pl),pl);let r=false;
    for(const id of Object.keys(p)){ if(minProof(d,pl,id)<=1&&oneClueFinish(Object.assign({},pl,{[id]:p[id]}))){r=true;break;} }
    memo.set(k,r);return r;}
  const chainOnly=oneClueFinish({});
  // chain score along the hint path: share of moves proven by the clue that was revealed just before
  let pl={},prevVis=E.visibleClues(d,{}),chainMoves=0,moves=0;
  while(Object.keys(pl).length<N){const h=E.bestHint(d,pl);if(!h)break;moves++;
    const vis=E.visibleClues(d,pl);const fresh=vis.filter(c=>!prevVis.includes(c));
    if(fresh.length&&fresh.some(c=>E.provable(d,[c],pl)[h.card]))chainMoves++;
    prevVis=vis;pl=Object.assign({},pl,{[h.card]:h.story});}
  const chain=moves?chainMoves/moves:0;
  const openers=d.clues.filter(c=>Object.keys(E.provable(d,[c.id],{})).length).map(c=>c.id);
  const rules={
    "1 the real filing fits every clue":truthOk,
    "2 one answer":unique,
    "3 never stuck, never a wrong proof":dead===0&&wrong===0,
    "4 a hint exists in every state":noHint===0,
    "5 at most 2 clues file a fact on sight":openers.length<=2,
    "6 every solve path needs a two-clue step":!chainOnly,
    "7 a real choice of where to go next":choiceStates>0,
    "8 chain score at most 0.5":chain<=0.5,
  };
  const ok=Object.values(rules).every(Boolean);allOk=allOk&&ok;
  console.log(`${d.label} · ${d.size}: ${ok?"PASS":"FAIL"}  openers=[${openers.join(",")}] states=${states} avg-provable=${(provSum/states).toFixed(2)} chain=${chain.toFixed(2)}`);
  for(const [k,v] of Object.entries(rules)) if(!v||process.argv.includes("-v")) console.log(`   ${v?"✓":"✗"} ${k}`);
}
process.exit(allOk?0:1);

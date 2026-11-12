window.__dbTables = window.__dbTables || {seen:new Map(), settings:new Map()};
window.IDBKeyRange={upperBound:(value,open)=>({value,open})};
Object.defineProperty(window, 'indexedDB', { configurable:true, value: {
  open(name,version) {
    const req={result:null,onupgradeneeded:null,onsuccess:null,onerror:null};
    const db={
      name,
      createObjectStore(n){window.__dbTables[n] ||= new Map();return {createIndex(){}};},
      transaction(store,mode){
        const tx={oncomplete:null,onerror:null,onabort:null};
        tx.objectStore=(n)=>{
          const map=window.__dbTables[n];
          const api={
            index(name){return {openCursor(range){return api.openCursor(range);}};},
            put(item){map.set(item.key,{...item});queueMicrotask(()=>tx.oncomplete?.());},
            get(key){const r={result:null,onsuccess:null,onerror:null};setTimeout(()=>{r.result=map.get(key);r.onsuccess?.();},0);return r;},
            openCursor(range){
              const r={result:null,onsuccess:null,onerror:null};
              const entries=Array.from(map.entries()).filter(([key,val])=>!range || (range.open ? val.when < range.value : val.when <= range.value));let i=0;
              const advance=()=>{
                if(i>=entries.length){r.result=null;r.onsuccess?.();queueMicrotask(()=>tx.oncomplete?.());return;}
                const [key,val]=entries[i++];
                r.result={key,value:val,delete:()=>map.delete(key),continue:()=>setTimeout(advance,0)};
                r.onsuccess?.();
              };
              setTimeout(advance,0);return r;
            }
          };
          return api;
        };
        return tx;
      }
    };
    setTimeout(()=>{req.result=db;req.onupgradeneeded?.();req.onsuccess?.();},0);
    return req;
  }
}});
const originalSrc=Object.getOwnPropertyDescriptor(HTMLImageElement.prototype,'src');
Object.defineProperty(HTMLImageElement.prototype,'src',{
  configurable:true,enumerable:true,
  get(){return originalSrc.get.call(this);},
  set(url){
    if(String(url).startsWith('https://')){
      return originalSrc.set.call(this,/\/mock\/l/.test(String(url))?window.__landscape:window.__portrait);
    }
    return originalSrc.set.call(this,url);
  }
});
window.__GALLERY_TEST__={
  intervalMs:220, shown:[],
  onShow:(art,orient)=>window.__GALLERY_TEST__.shown.push({key:art.key,orient}),
  request:async(kind,param)=>{
    if(kind==='cleveland'){
      const data=Array.from({length:130},(_,i)=>({
        id:i+1,title:'Artwork '+(i+1),creators:[{description:'Artist '+(i+1)}],
        type:'Painting',technique:'Oil on canvas',share_license_status:'CC0',
        images:{web:{url:'https://openaccess-cdn.clevelandart.org/mock/'+(i<91?'p':'l')+(i+1)+'.jpg',width:i<91?400:620,height:i<91?620:400}}
      }));
      return {info:{total:130},data};
    }
    if(kind==='chicago')return {config:{iiif_url:'https://www.artic.edu/iiif/2'},pagination:{total_pages:1},data:[]};
    if(kind==='metSearch')return {total:0,objectIDs:[]};
    throw Error('Unexpected API '+kind);
  }
};

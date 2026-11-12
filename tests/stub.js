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
      const match=String(url).match(/00000000-0000-0000-0000-[0-9]{12}/);
      return originalSrc.set.call(this,match&&window.__mockOrientation?.get(match[0])===false?window.__landscape:window.__portrait);
    }
    return originalSrc.set.call(this,url);
  }
});
const TEST_MOVEMENTS=['Renaissance','Baroque','Rococo','Neoclassicism','Romanticism','Realism',
  'Impressionism','Post-Impressionism','Expressionism','Cubism','Surrealism','Abstract Art','Contemporary Art'];
const TEST_ARTWORKS=Array.from({length:12},(_,r)=>TEST_MOVEMENTS.map((style,m)=>{
  const id=10000+r*13+m,portrait=(r%10)<7;
  return {id,title:'Artwork '+id,artist_title:'Test Artist '+id,
    image_id:'00000000-0000-0000-0000-'+String(id).padStart(12,'0'),
    artwork_type_title:'Painting',medium_display:'Oil on canvas',style_title:style,
    style_titles:[style],date_display:'1900',is_public_domain:true,
    thumbnail:{width:portrait?420:720,height:portrait?720:420}};
})).flat();
window.__mockOrientation=new Map(TEST_ARTWORKS.map(a=>[a.image_id,a.thumbnail.height>a.thumbnail.width]));
window.__GALLERY_TEST__={
  intervalMs:220, shown:[],
  onShow:(art,orient)=>window.__GALLERY_TEST__.shown.push({key:art.key,orient,movement:art.movement}),
  request:async(kind,param)=>{
    if(kind==='cleveland'){
      const data=Array.from({length:130},(_,i)=>({
        id:i+1,title:'Artwork '+(i+1),creators:[{description:'Artist '+(i+1)}],
        type:'Painting',technique:'Oil on canvas',share_license_status:'CC0',
        images:{web:{url:'https://openaccess-cdn.clevelandart.org/mock/'+(i<91?'p':'l')+(i+1)+'.jpg',width:i<91?1250:1850,height:i<91?1850:1250}}
      }));
      return {info:{total:130},data};
    }
    if(kind==='chicago')return {config:{iiif_url:'https://www.artic.edu/iiif/2'},pagination:{total_pages:1},data:TEST_ARTWORKS};
    if(kind==='chicagoMovement'){const id=String(param).split(':')[0];const m=window.GalleryCore.MOVEMENTS.find(x=>x.id===id);return {config:{iiif_url:'https://www.artic.edu/iiif/2'},pagination:{total_pages:1},data:TEST_ARTWORKS.filter(a=>a.style_title===m?.en)};}
    if(kind==='asianCommons'||kind==='africanCommons'){
      const museumId=String(param).split(':')[0];
      const seed=Array.from(museumId).reduce((n,c)=>n+c.charCodeAt(0),0)*1000;
      const pages=Array.from({length:12},(_,i)=>({
        pageid:seed+i+1,title:'File:Art_'+museumId+'_'+(i+1)+'.jpg',
        imageinfo:[{mime:'image/jpeg',width:1250,height:1850,
          thumburl:'https://upload.wikimedia.org/wikipedia/commons/thumb/mock_'+museumId+'_'+(i+1)+'.jpg',
          extmetadata:{LicenseShortName:{value:'Public domain'},Artist:{value:'Test Painter'}}}]
      }));
      return {query:{pages,searchinfo:{totalhits:12}}};
    }
    if(kind==='metSearch')return {total:0,objectIDs:[]};
    throw Error('Unexpected API '+kind);
  }
};

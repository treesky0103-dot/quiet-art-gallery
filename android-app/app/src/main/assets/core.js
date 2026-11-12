/* Artwork selection core. Zero external dependencies. */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.GalleryCore = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';
  const NINETY_DAYS_MS = 90 * 24 * 60 * 60 * 1000;
  const BLOCKLIST = /(?:\bsculpture\b|\bceramic(?:s)?\b|\bpottery\b|\bfurniture\b|\btextile\b|\btapestry\b|\barmor\b|\barmour\b|\bweapon\b|\bphotograph(?:y)?\b|\binstallation\b|\bstatue\b|\bvase\b|\bcoin\b|\bmedal\b|\bjewelry\b|\bjewellery\b|\barchitecture\b|\bdecorative art\b|\bframe(?:d)?\b|\bgallery view\b|\bexhibition view\b|\b3d\b|\bvideo\b|\bfilm\b|\bglass\b|\bcarpet\b|\bcostume\b|\bcarving\b|\brelief\b|\bbook cover\b)/i;
  const ALLOW_TYPES = /(?:painting|paintings|drawing|drawings|print|prints|watercolo[u]?r|etching|lithograph|woodblock|woodcut|illustration|gouache|collage|pastel|ink on paper|oil on canvas|oil on panel|acrylic on|tempera on|aquatint|serigraph|screenprint|engraving)/i;
  function string(x) { return typeof x === 'string' ? x : ''; }
  function safeURL(url) {
    try {
      const u = new URL(url);
      if (u.protocol !== 'https:' || u.username || u.password || (u.port && u.port !== '443')) return false;
      const h = u.hostname.toLowerCase();
      return h === 'images.metmuseum.org' || h === 'www.artic.edu' || h === 'artic.edu' || h === 'openaccess-cdn.clevelandart.org' || h.endsWith('.clevelandart.org');
    } catch (_) { return false; }
  }
  function fingerprint(a) {
    const norm = value => string(value).normalize('NFKC').toLowerCase().replace(/[^\p{L}\p{N}]/gu, '').slice(0, 95);
    const title = norm(a.title), artist = norm(a.artist);
    return title.length >= 4 && artist.length >= 3 ? `fp:${title}:${artist}` : null;
  }
  function orientation(a) {
    const w = Number(a.width), h = Number(a.height);
    if (w > 0 && h > 0) return h > w * 1.02 ? 'portrait' : 'other';
    return 'unknown';
  }
  // EXACTLY seven portrait goals per 10 slots (orientation is a target, not a false guarantee).
  function targetOrientation(slot) { return ((Math.max(0, Math.floor(slot)) % 10) < 7) ? 'portrait' : 'other'; }
  function kstRenewalDay(epoch) {
    // KST midnight 10:00 boundary = 01:00 UTC. Use UTC-1h day-shift.
    return new Date(epoch - 60 * 60 * 1000).toISOString().slice(0, 10);
  }
  function canReshow(previous, now = Date.now()) {
    if (!Number.isFinite(previous)) return true;
    // Clock rolled back: never bypass a 90-day embargo.
    return now >= previous && now - previous >= NINETY_DAYS_MS;
  }
  function eligibleArt(a) {
    if (!a || !a.key || /:(?:undefined|null|NaN)$/.test(a.key) || !a.image || !safeURL(a.image) || !a.rightsOK) return false;
    const t = string(a.type).trim();
    const medium = string(a.medium).trim();
    const classification = string(a.classification).trim();
    const visualClass = [t, classification, medium].filter(Boolean).join(' | ');
    // Type (or known metadata) must explicitly identify a 2D visual work.
    if (!visualClass || !ALLOW_TYPES.test(visualClass)) return false;
    if (BLOCKLIST.test(visualClass)) return false;
    // Reject obvious photo-of-gallery or framed-object metadata; titles can refer to a painted frame,
    // so do not reject artwork titles for merely mentioning a frame.
    if (BLOCKLIST.test(string(a.description).slice(0, 160))) return false;
    if (/\b(?:unknown|unverified|copyrighted|restricted)\b/i.test(string(a.license))) return false;
    return true;
  }
  function normalizeCleveland(item) {
    const img = item && item.images && item.images.web;
    const creator = item && item.creators && item.creators[0];
    return {
      key: `cma:${item && item.id}`,
      source: '클리블랜드', title: string(item && item.title) || '제목 미상',
      artist: string(creator && creator.description) || '작가 미상',
      image: string(img && img.url),
      width: Number(img && img.width) || 0, height: Number(img && img.height) || 0,
      type: string(item && item.type), medium: string(item && item.technique),
      classification: string(item && item.type),
      description: '', license: string(item && item.share_license_status),
      rightsOK: (item && item.share_license_status) === 'CC0',
      page: string(item && item.url)
    };
  }
  function normalizeChicago(item, iiifBase) {
    const imgid = string(item && item.image_id);
    const base = string(iiifBase).replace(/\/$/, '');
    // image_id comes from museum metadata; path may only contain safe token characters.
    const image = imgid && /^[a-zA-Z0-9_-]{15,100}$/.test(imgid) && /^https:\/\/www\.artic\.edu\/iiif\/2$/i.test(base)
      ? `${base}/${imgid}/full/843,/0/default.jpg` : '';
    return {
      key: `aic:${item && item.id}`,
      source: '시카고', title: string(item && item.title) || '제목 미상',
      artist: string(item && item.artist_title) || '작가 미상',
      image,
      width: Number(item && item.thumbnail && item.thumbnail.width) || 0,
      height: Number(item && item.thumbnail && item.thumbnail.height) || 0,
      type: string(item && item.artwork_type_title),
      medium: string(item && item.medium_display), classification: string(item && item.artwork_type_title),
      description: '', license: 'Public domain',
      rightsOK: !!(item && item.is_public_domain),
      page: item && Number.isInteger(item.id) ? `https://www.artic.edu/artworks/${item.id}` : ''
    };
  }
  function normalizeMet(item) {
    return {
      key: `met:${item && item.objectID}`,
      source: '메트로폴리탄', title: string(item && item.title) || '제목 미상',
      artist: string(item && item.artistDisplayName) || '작가 미상',
      image: string(item && item.primaryImageSmall),
      width: 0, height: 0,
      type: string(item && item.objectName), medium: string(item && item.medium),
      classification: string(item && item.classification),
      description: '', license: 'CC0',
      rightsOK: !!(item && item.isPublicDomain), page: string(item && item.objectURL)
    };
  }
  function pickCandidate(candidates, goal, seen, now) {
    function available(a) {
      if (!eligibleArt(a)) return false;
      const s = seen.get(a.key), fp = fingerprint(a), f = fp ? seen.get(fp) : null;
      return canReshow(s, now) && canReshow(f, now);
    }
    const exact = candidates.findIndex(a => available(a) && orientation(a) === goal);
    if (exact >= 0) return exact;
    const unknown = candidates.findIndex(a => available(a) && orientation(a) === 'unknown');
    if (unknown >= 0) return unknown;
    return candidates.findIndex(available);
  }
  function prettyBytes(bytes) {
    const v = Number(bytes) || 0;
    return v < 1024 * 1024 ? `${(v / 1024).toFixed(0)}KB` : `${(v / (1024 * 1024)).toFixed(1)}MB`;
  }
  return { NINETY_DAYS_MS, safeURL, eligibleArt, fingerprint, orientation, targetOrientation,
    kstRenewalDay, canReshow, normalizeCleveland, normalizeChicago, normalizeMet,
    pickCandidate, prettyBytes };
});

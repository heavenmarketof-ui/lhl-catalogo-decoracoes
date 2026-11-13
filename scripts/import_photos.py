#!/usr/bin/env python3
"""Importa catálogo completo da origem autorizada, com fotos e preços de origem.
Os preços públicos são calculados pelo site usando multiplicador 3.
"""
import asyncio, json, re, pathlib, os
from urllib.parse import urljoin, urlparse, parse_qs
from playwright.async_api import async_playwright

ROOT="https://loquefacil.com/c/decoracoes4you"
HERE=pathlib.Path(__file__).resolve().parents[1]
PAT=re.compile(r"window\\.LHL_PRODUCTS\\s*=\\s*(\\[.*?\\])\\s*;",re.S)
m=PAT.search((HERE/"products.js").read_text())
if not m: raise SystemExit("products.js não reconhecido")
existing=json.loads(m.group(1))
by_id={p["id"]:p for p in existing}
PRICE=re.compile(r"R\\$\\s*([\\d.]+,\\d{2})")
CODE=re.compile(r"\\b([A-Z]{1,4}[- ]?\\d{3,8})\\b")
def number(s): return float(s.replace(".","").replace(",","."))
def clean(s): return re.sub(r"\\s+"," ",s or "").strip()
async def main():
  listing={}
  async with async_playwright() as pw:
    browser=await pw.chromium.launch()
    page=await browser.new_page(viewport={"width":1280,"height":900},locale="pt-BR")
    # Descobre todos os links nas páginas da categoria, sem limitar aos 20 códigos existentes.
    empty=0
    for n in range(1,151):
      url=ROOT if n==1 else ROOT+"?page="+str(n)
      try:
        await page.goto(url,wait_until="domcontentloaded",timeout=45000)
        await page.wait_for_timeout(550)
        found=await page.locator('a[href*="/product/"]').evaluate_all("""els=>els.map(a=>({url:a.href,text:(a.closest('article,li,.card,.product')||a).innerText||a.innerText}))""")
      except Exception as exc:
        print("Erro listagem",n,str(exc)[:120]);continue
      before=len(listing)
      for item in found:
        u=item["url"].split("?")[0]
        if urlparse(u).netloc!=urlparse(ROOT).netloc:continue
        listing.setdefault(u,clean(item["text"]))
      print("Página",n,"links",len(found),"únicos",len(listing),flush=True)
      empty=empty+1 if len(listing)==before else 0
      if empty>=3 and n>=3:break
    print("TOTAL LINKS ENCONTRADOS",len(listing),flush=True)
    # Protege o catálogo já publicado se a coleta não encontrar produtos.
    if len(listing)<20: raise SystemExit("Coleta insuficiente: nenhum arquivo será substituído")
    processed=0;created=0;photos=0;failures=[]
    for url,hint in listing.items():
      try:
        await page.goto(url,wait_until="domcontentloaded",timeout=45000)
        await page.wait_for_timeout(350)
        body=await page.locator("body").inner_text()
        heading=clean(await page.locator("h1").first.inner_text()) if await page.locator("h1").count() else ""
        codes=CODE.findall(body[:2200]+" "+hint)
        code=next((c.replace(" ","-") for c in codes if c.replace(" ","-") in by_id),None)
        if not code:
          code=next((c.replace(" ","-") for c in codes),None)
        if not code:
          slug=urlparse(url).path.rstrip("/").split("/")[-1]
          code="REF-"+re.sub(r"[^A-Za-z0-9]","",slug).upper()[:24]
        item=by_id.get(code)
        prices=PRICE.findall(body[:3500])
        if not item and not prices:
          failures.append({"url":url,"reason":"preço não identificado"});continue
        base=item["base"] if item else number(prices[0])
        if not (0<base<1000000):continue
        name=item["name"] if item else (heading or clean(hint.split("\\n")[0]) or code)
        imgs=await page.locator("img").evaluate_all("""els=>els.map(i=>({src:i.currentSrc||i.src,w:i.naturalWidth,h:i.naturalHeight}))""")
        gallery=[]
        for im in imgs:
          src=im["src"]
          if "storage.loquefacil.com/photos/" not in src:continue
          if im["w"]<180 or im["h"]<180:continue
          if src not in gallery:gallery.append(src)
        if not item:
          item={"id":code,"name":name,"category":"Decorações","base":base}
          by_id[code]=item;created+=1
        if gallery:
          item["image"]=gallery[0];item["gallery"]=gallery;photos+=1
        processed+=1
        if processed%25==0:print("Processados",processed,"novos",created,flush=True)
      except Exception as exc:
        failures.append({"url":url,"reason":str(exc)[:180]})
    await browser.close()
  # Nunca reduz os 20 existentes. Grava o resultado e um relatório para conferência.
  result=list(by_id.values())
  (HERE/"products.js").write_text("window.LHL_PRODUCTS = "+json.dumps(result,ensure_ascii=False,indent=2)+";\\n")
  (HERE/"photo-audit.json").write_text(json.dumps({"links_found":len(listing),"processed":processed,"new_products":created,"total":len(result),"with_images":sum(bool(p.get("image")) for p in result),"failures":failures[:100]},ensure_ascii=False,indent=2))
  print("IMPORTAÇÃO FINALIZADA",len(result),"produtos;",photos,"fotos principais;",len(failures),"falhas",flush=True)
asyncio.run(main())

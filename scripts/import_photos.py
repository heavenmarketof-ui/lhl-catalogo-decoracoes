#!/usr/bin/env python3
"""Coleta imagens carregadas no navegador por produto, com validação por código.
Não inventa URLs. Não altera preços ou nomes existentes.
"""
import asyncio, json, re, pathlib
from urllib.parse import urljoin
from playwright.async_api import async_playwright

ROOT="https://loquefacil.com/c/decoracoes4you"
HERE=pathlib.Path(__file__).resolve().parents[1]
PAT=re.compile(r"window\.LHL_PRODUCTS\s*=\s*(\[.*?\])\s*;",re.S)
text=(HERE/"products.js").read_text()
m=PAT.search(text)
if not m: raise SystemExit("products.js não reconhecido")
products=json.loads(m.group(1))
codes={p["id"]:p for p in products}
async def main():
    updated=0
    async with async_playwright() as pw:
        browser=await pw.chromium.launch()
        page=await browser.new_page(viewport={"width":1280,"height":900})
        await page.goto(ROOT,wait_until="domcontentloaded",timeout=60000)
        links={}
        for n in range(1,69):
            if n>1:
                await page.goto(ROOT+"?page="+str(n),wait_until="domcontentloaded",timeout=60000)
            await page.wait_for_timeout(900)
            found=await page.locator('a[href*="/product/"]').evaluate_all("""els => els.map(a=>({url:a.href, text:a.innerText}))""")
            for item in found:
                for code in codes:
                    if code in item["text"]:links[code]=item["url"]
            if len(links)==len(codes):break
        print("Páginas de produtos identificadas:",len(links),"de",len(codes))
        for code,url in links.items():
            try:
                await page.goto(url,wait_until="domcontentloaded",timeout=60000)
                await page.wait_for_timeout(900)
                body=await page.locator("body").inner_text()
                if code not in body:
                    print("IGNORADO: código divergente",code,url);continue
                imgs=await page.locator("img").evaluate_all("""els => els.map(i=>({src:i.currentSrc||i.src,w:i.naturalWidth,h:i.naturalHeight,alt:i.alt}))""")
                gallery=[]
                for im in imgs:
                    src=im["src"]
                    if "storage.loquefacil.com/photos/" not in src:continue
                    if im["w"]<180 or im["h"]<180:continue
                    if src not in gallery:gallery.append(src)
                if gallery:
                    codes[code]["image"]=gallery[0]
                    codes[code]["gallery"]=gallery
                    updated+=1
                    print(code,len(gallery),"imagens")
                else:print("SEM FOTOS",code)
            except Exception as e:print("ERRO",code,str(e)[:150])
        await browser.close()
    (HERE/"products.js").write_text("window.LHL_PRODUCTS = "+json.dumps(products,ensure_ascii=False,indent=2)+";\n")
    (HERE/"photo-audit.json").write_text(json.dumps({"processed":len(links),"with_images":updated,"total":len(codes)},indent=2))
    print("Produtos atualizados:",updated)
asyncio.run(main())

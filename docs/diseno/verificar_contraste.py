# Verifica los contrastes WCAG de docs/diseno/tokens.css (claro y oscuro).
# Uso: python docs/diseno/verificar_contraste.py docs/diseno/tokens.css
import re, sys
sys.stdout.reconfigure(encoding='utf-8')
css=open(sys.argv[1],encoding='utf8').read()
print('llaves balanceadas:', css.count('{')==css.count('}'))
def bloque(sel):
    i=css.index(sel); j=css.index('{',i); d=1; k=j+1
    while d: d+= {'{':1,'}':-1}.get(css[k],0); k+=1
    return dict(re.findall(r'(--[\w-]+):\s*(#[0-9a-fA-F]{6})',css[j:k]))
claro=bloque(':root {'); oscuro={**claro, **bloque(':root[data-theme="dark"]')}
med=bloque(':root:not([data-theme="light"])')
print('dark media == data-theme:', med==bloque(':root[data-theme="dark"]'))
def lum(h):
    h=h.lstrip('#'); r,g,b=(int(h[i:i+2],16)/255 for i in (0,2,4))
    f=lambda c: c/12.92 if c<=0.04045 else ((c+0.055)/1.055)**2.4
    return 0.2126*f(r)+0.7152*f(g)+0.0722*f(b)
def cr(a,b):
    la,lb=sorted((lum(a),lum(b)),reverse=True); return (la+0.05)/(lb+0.05)
pares=[('fg','bg',4.5),('fg','surface',4.5),('fg','surface-2',4.5),('fg','surface-3',4.5),('fg','surface-code',4.5),
 ('fg-muted','bg',4.5),('fg-muted','surface',4.5),('fg-muted','surface-2',4.5),('fg-muted','surface-3',4.5),
 ('fg-heading','bg',4.5),('fg-heading','surface-2',4.5),('on-primary','primary',4.5),('on-primary','primary-hover',4.5),('on-primary','primary-active',4.5),
 ('link','bg',4.5),('link','surface',4.5),('link','surface-2',4.5),('link','surface-3',4.5),
 ('border-strong','bg',3),('border-strong','surface',3),('border-strong','surface-2',3),('border-strong','surface-3',3),('focus','bg',3),('focus','surface',3),('focus','surface-2',3),
 ('success','success-bg',4.5),('warning','warning-bg',4.5),('danger','danger-bg',4.5),('info','info-bg',4.5),('diag','diag-bg',4.5),
 ('fg','diag-bg',4.5),('fg','info-bg',4.5),
 ('chart-1','bg',3),('chart-2','bg',3),('chart-3','bg',3),('chart-4','bg',3),('chart-5','bg',3),('chart-6','bg',3)]
print('| Par (texto / fondo) | Claro | Oscuro | Mínimo |'); print('|---|---|---|---|')
fallas=0
for a,b,m in pares:
    rc=cr(claro['--color-'+a],claro['--color-'+b]); ro=cr(oscuro['--color-'+a],oscuro['--color-'+b])
    ok=lambda r: f"{r:.2f}:1" + ('' if r>=m else ' **FALLA**')
    fallas+= (rc<m)+(ro<m)
    print(f"| `{a}` / `{b}` | {ok(rc)} | {ok(ro)} | {m}:1 |")
print('fallas:',fallas)

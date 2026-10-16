#!/usr/bin/env python3
"""Loopback-only Yu Lab editor. Python standard library; Git owns authentication."""
import argparse, base64, hashlib, html, json, mimetypes, os, re, secrets, shutil, subprocess, threading, time, webbrowser
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from html.parser import HTMLParser

ROOT = Path(__file__).resolve().parent.parent
PAGES = {'index':'Home', 'about-the-pi':'About the PI', 'meet-the-team':'People & lab photos', 'publications':'Publications', 'news':'News', 'contact':'Contact', 'layout':'Shared header & footer'}
BLOCK = re.compile(r'(<div\b[^>]*data-testid="richTextElement"[^>]*>)(.*?)(</div>)', re.S)
IMAGE = re.compile(r'<img\b[^>]*>', re.S)
LOCK = threading.Lock()
TOKEN = secrets.token_urlsafe(32)
PORT = 0

def run(*args, timeout=90):
    env = dict(os.environ, GIT_TERMINAL_PROMPT='0', GCM_INTERACTIVE='Never')
    p = subprocess.run(args, cwd=ROOT, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
    if p.returncode:
        raise ValueError((p.stderr or p.stdout or 'Command failed').strip()[-4000:])
    return p.stdout.strip()

def git(*args): return run('git', *args)
def digest(s): return hashlib.sha256(s.encode()).hexdigest()
def template(page):
    if page not in PAGES: raise ValueError('Unknown page.')
    return ROOT/'templates'/(page+'.njk')
def attrs(tag): return dict(re.findall(r'([\w-]+)="([^"]*)"', tag))
def safe_url(value, image=False):
    if not isinstance(value,str) or any(ord(c)<32 for c in value): raise ValueError('Invalid link or image address.')
    value=value.strip()
    if image:
        if not re.fullmatch(r'assets/[A-Za-z0-9_./%+ -]+', value) or '..' in value.split('/'):
            raise ValueError('Choose an image from the local media library.')
        if not (ROOT/'site'/value).is_file(): raise ValueError('Image is missing.')
    elif not (re.match(r'^(https?://|mailto:|tel:|#)', value) or (not re.match(r'^\w+:|^//',value) and not any(c in value for c in '\\<>\r\n'))):
        raise ValueError('Use a website, email, phone, or relative link.')
    return value

class CleanHTML(HTMLParser):
    tags = set('p br span strong b em i u s a ul ol li h1 h2 h3 h4 h5 h6 sub sup'.split())
    def __init__(self): super().__init__(convert_charrefs=True); self.parts=[]; self.stack=[]
    def handle_starttag(self, tag, attributes):
        if tag not in self.tags: raise ValueError('Unsupported formatting. Paste text using the Paste plain text button.')
        out=[]
        for k,v in attributes:
            v=v or ''
            if k in ('class','title','style'):
                if k=='style' and re.search(r'url|expression|@|\\|behavior|position|display',v,re.I): continue
                out.append((k,v))
            elif tag=='a' and k=='href': out.append((k,safe_url(v)))
        self.parts.append('<'+tag+''.join(' '+k+'="'+html.escape(v,quote=True)+'"' for k,v in out)+'>')
        if tag!='br': self.stack.append(tag)
    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag,attrs)
        if tag!='br': self.handle_endtag(tag)
    def handle_endtag(self,tag):
        if tag=='br': return
        if not self.stack or self.stack.pop()!=tag: raise ValueError('Formatting is unbalanced. Undo your last edit and try again.')
        self.parts.append('</'+tag+'>')
    def handle_data(self,data): self.parts.append(html.escape(data))
    def result(self):
        if self.stack: raise ValueError('Formatting is incomplete.')
        result=''.join(self.parts)
        if any(x in result for x in ('{{','{%','{#')): raise ValueError('Template commands are not allowed in page content.')
        return result

def clean(s):
    if not isinstance(s,str) or len(s)>500000: raise ValueError('Text is too large.')
    parser=CleanHTML(); parser.feed(s); return parser.result()

def read_layout(tag):
    a=attrs(tag)
    return {'x':float(a.get('data-cms-x',0)), 'y':float(a.get('data-cms-y',0)), 'width':a.get('data-cms-width','')}

def layout_tag(tag, data):
    if not isinstance(data,dict): raise ValueError('Invalid layout.')
    values={}
    for key in ('x','y','width'):
        value=data.get(key,'' if key=='width' else 0)
        if key=='width' and value=='': values[key]=''; continue
        try: value=float(value)
        except (TypeError,ValueError): raise ValueError('Layout values must be numbers.')
        if not (-4000<=value<=4000) or (key=='width' and value<20): raise ValueError('Layout value is outside the supported range.')
        values[key]=str(round(value,2))
    old=attrs(tag); style=html.unescape(old.get('style',''))
    style=re.sub(r'(?:^|;)\s*translate\s*:[^;]*','',style)
    if 'data-cms-width' in old or values['width']: style=re.sub(r'(?:^|;)\s*width\s*:[^;]*','',style)
    style=style.strip(';')+';translate:'+values['x']+'px '+values['y']+'px;'
    if values['width']: style+='width:'+values['width']+'px;'
    for key,value in [('style',style)]+[('data-cms-'+k,v) for k,v in values.items()]:
        replacement=key+'="'+html.escape(value,quote=True)+'"'
        if key in old: tag=re.sub(r'(?<![\w-])'+key+r'="[^"]*"',lambda m:replacement,tag)
        else: tag=tag.replace('>',' '+replacement+'>',1) if not tag.endswith('/>') else tag[:-2]+' '+replacement+'/>'
    return tag

def load_page(page):
    source=template(page).read_text()
    blocks=[{'id':i,'html':m[2], 'domId':attrs(m[1]).get('id',''), 'layout':read_layout(m[1]), 'label':html.unescape(re.sub('<[^>]+>',' ',m[2])).strip()[:100]} for i,m in enumerate(BLOCK.finditer(source))]
    images=[]
    for i,m in enumerate(IMAGE.finditer(source)):
        a=attrs(m[0]); src=html.unescape(a.get('src','')).replace('{{ root_path }}','')
        images.append({'id':i,'domId':a.get('id',''),'layout':read_layout(m[0]),'src':src,'alt':html.unescape(a.get('alt',''))})
    return {'page':page,'label':PAGES[page],'version':digest(source),'blocks':blocks,'images':images,'preview':'/' if page in ('index','layout') else '/'+page+'/'}

def atomic(path,content):
    tmp=path.with_name(path.name+'.cms-tmp'); tmp.write_text(content); tmp.replace(path)

def build():
    try: run('node', 'scripts/build.js')
    except FileNotFoundError: raise ValueError('Install Node.js, then reopen the editor.')

def save_page(data):
    path=template(data['page']); old=path.read_text()
    if data.get('version')!=digest(old): raise ValueError('This page changed in another window or on disk. Reload the page before saving; your current editor text is still here.')
    changes=[]; blocks=list(BLOCK.finditer(old)); images=list(IMAGE.finditer(old))
    for item in data.get('blocks',[]):
        idx=item['id']
        if type(idx)!=int or not 0<=idx<len(blocks): raise ValueError('Unknown text block.')
        m=blocks[idx]
        if item.get('layout') is not None and item['layout']!=read_layout(m[1]):
            changes.append((m.start(1),m.end(1),layout_tag(m[1],item['layout'])))
        # Keep untouched markup byte-for-byte, including entity and whitespace conventions.
        if item['html']!=m[2]: changes.append((m.start(2),m.end(2),clean(item['html'])))
    for item in data.get('images',[]):
        idx=item['id']
        if type(idx)!=int or not 0<=idx<len(images): raise ValueError('Unknown image.')
        m=images[idx]
        if item.get('remove'):
            changes.append((m.start(),m.end(),'')); continue
        a=attrs(m[0]); src=safe_url(item['src'],True)
        tag=m[0]
        for key,val in [('src','{{ root_path }}'+src),('alt',item.get('alt',''))]:
            if any(x in val for x in ('{%','{#')) or (key=='alt' and '{{' in val): raise ValueError('Invalid image description.')
            escaped=html.escape(val,quote=True)
            if key in a: tag=re.sub(r'\b'+key+r'="[^"]*"',lambda _:key+'="'+escaped+'"',tag)
            else: tag=tag.replace('<img','<img '+key+'="'+escaped+'"',1)
        if item.get('layout') is not None and item['layout']!=read_layout(m[0]): tag=layout_tag(tag,item['layout'])
        changes.append((m.start(),m.end(),tag))
    new=old
    for start,end,value in sorted(changes,reverse=True): new=new[:start]+value+new[end:]
    addition=data.get('addition')
    if addition:
        if data['page']=='layout': raise ValueError('Add entries to a specific page.')
        body=clean(addition['html']); photo=addition.get('image',''); markup=''
        if photo: markup='<img src="{{ root_path }}'+html.escape(safe_url(photo,True),quote=True)+'" alt="" style="max-width:240px;width:100%;height:auto"/>'
        markup='<section style="max-width:980px;margin:32px auto;padding:24px;box-sizing:border-box;font-family:Arial,sans-serif;color:#222;line-height:1.6">'+markup+'<div data-testid="richTextElement">'+body+'</div></section>\n'
        pos=new.rfind('{% endblock %}'); new=new[:pos]+markup+new[pos:]
    backup=Path(git('rev-parse','--absolute-git-dir'))/'local-cms-backups'
    backup.mkdir(exist_ok=True); (backup/(str(time.time_ns())+'-'+path.name)).write_text(old)
    atomic(path,new)
    try: build()
    except Exception:
        atomic(path,old)
        try: build()
        except Exception: pass
        raise ValueError('Preview build failed. The previous template has been restored. Check Node.js and run npm ci, then retry.')
    return load_page(data['page'])

def allowed(path):
    return (path.startswith(('templates/','local-cms/','site/assets/uploads/')) or path in ('README.md','scripts/build.js','package.json','package-lock.json','.gitignore','LOCAL-CMS.md','Start CMS.command','Start CMS.bat','.github/workflows/deploy-pages.yml','.github/workflows/static.yml') or bool(re.fullmatch(r'site/(?:index.html|(?:about-the-pi|contact|meet-the-team|news|publications)/index.html)',path)))

def changed():
    # NUL-separated paths preserve filenames containing whitespace.
    raw=subprocess.check_output(['git','status','--porcelain=v1','-z','--untracked-files=all'],cwd=ROOT).decode()
    entries=raw.split('\0'); result=[]; i=0
    while i<len(entries):
        entry=entries[i]; i+=1
        if not entry: continue
        result.append(entry[3:])
        if 'R' in entry[:2] or 'C' in entry[:2]:
            result.append(entries[i]); i+=1
    return sorted(set(result))

def status():
    branch=git('branch','--show-current')
    return {'branch':branch,'files':changed(),'remote':git('remote','get-url','origin'),'message':'Saved on this computer. Publish sends changes to GitHub.'}

def publish():
    branch=git('branch','--show-current')
    if branch!='main': raise ValueError('Publishing requires the main branch. Switch to main before publishing.')
    remote=git('remote','get-url','origin')
    if os.environ.get('LOCAL_CMS_TEST')!='1' and not re.fullmatch(r'(?:https://github\.com/|git@github\.com:|ssh://git@github\.com/)YuGliaLab/(?:YuGliaLab\.github\.io|yulab\.github\.com)(?:\.git)?/?',remote,re.I):
        raise ValueError('Origin is not the YuGliaLab website repository. Check your Git remote before publishing.')
    gd=Path(git('rev-parse','--absolute-git-dir'))
    if any((gd/x).exists() for x in ('MERGE_HEAD','rebase-merge','rebase-apply','CHERRY_PICK_HEAD')): raise ValueError('An unfinished Git merge or rebase needs to be resolved before publishing.')
    files=changed(); outside=[f for f in files if not allowed(f)]
    if outside: raise ValueError('Other repository changes need review before publishing: '+', '.join(outside))
    try: git('fetch','origin','main')
    except Exception as e: raise ValueError('Could not reach GitHub. Your edits are safe locally. Check your connection and existing GitHub login, then retry. '+str(e))
    build(); files=changed()
    if files:
        git('add','--',*files)
        try: git('commit','-m','Update Yu Lab website with local CMS')
        except Exception as e: raise ValueError('Could not create a commit. Your files are saved. Check your Git name/email or signing configuration. '+str(e))
    # Normal merge preserves both histories; a failed merge is aborted without losing the local commit.
    try: git('merge','--no-edit','origin/main')
    except Exception as e:
        conflicts=git('diff','--name-only','--diff-filter=U')
        if (gd/'MERGE_HEAD').exists(): git('merge','--abort')
        raise ValueError('GitHub has overlapping changes. Nothing was pushed; your edits are saved in a local commit. Ask a maintainer to merge origin/main and resolve these files, then retry Publish: '+(conflicts or str(e)))
    # Refuse to push a merge whose generated output no longer agrees with its templates.
    build()
    generated=[f for f in changed() if allowed(f)]
    if generated:
        git('add','--',*generated); git('commit','-m','Rebuild website after merging GitHub updates')
    try: git('push','origin','HEAD:main')
    except Exception as e: raise ValueError('The commit is saved locally, but GitHub did not accept the push. Check login, network, branch rules, or newer remote changes and retry Publish. No force-push was used. '+str(e))
    return {'message':'Sent to GitHub. GitHub Pages is building the live website; deployment may take a few minutes.','commit':git('rev-parse','--short','HEAD'),'actions':'https://github.com/YuGliaLab/YuGliaLab.github.io/actions'}

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def reply(self,status,body,kind='application/json'):
        raw=json.dumps(body).encode() if kind=='application/json' else body
        self.send_response(status); self.send_header('Content-Type',kind); self.send_header('Content-Length',str(len(raw)))
        self.send_header('Cache-Control','no-store'); self.send_header('X-Content-Type-Options','nosniff'); self.send_header('Referrer-Policy','no-referrer')
        if kind=='text/html': self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; frame-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'self'")
        self.end_headers(); self.wfile.write(raw)
    def guard(self,write=False):
        if self.headers.get('Host')!=f'127.0.0.1:{PORT}': raise ValueError('Open the exact local address printed by the launcher.')
        if write and (self.headers.get('Origin')!=f'http://127.0.0.1:{PORT}' or self.headers.get('X-CMS-Token')!=TOKEN): raise ValueError('Session expired. Reload the editor.')
    def do_GET(self):
        try:
            self.guard(); route=self.path.split('?')[0]
            if route=='/api/pages': return self.reply(200,{'pages':PAGES,'token':TOKEN})
            if route=='/api/status': return self.reply(200,status())
            if route=='/api/media':
                return self.reply(200,{'files':[str(p.relative_to(ROOT/'site')) for p in sorted((ROOT/'site/assets').rglob('*')) if p.is_file() and p.suffix.lower() in ('.png','.jpg','.jpeg','.gif','.webp')]})
            if route.startswith('/api/page/'):
                with LOCK: data=load_page(route.rsplit('/',1)[1])
                return self.reply(200,data)
            if route=='/favicon.ico': return self.reply(200,(ROOT/'site/assets/pfavico.ico').read_bytes(),'image/x-icon')
            if route in ('/','/app.js','/visual.js','/style.css'):
                f=ROOT/'local-cms'/({'/':'index.html'}.get(route,route[1:]))
            elif route.startswith('/preview/'):
                from urllib.parse import unquote
                base=(ROOT/'site').resolve(); f=(base/unquote(route[len('/preview/'):])).resolve()
                if base not in f.parents and f!=base: raise ValueError('Invalid path.')
                if f.is_dir(): f=f/'index.html'
                if f.suffix.lower() not in ('.html','.css','.js','.png','.jpg','.jpeg','.gif','.webp','.ico','.woff','.woff2','.svg','.pdf'): raise ValueError('Unsupported preview file.')
            else: return self.reply(404,{'error':'Not found'})
            if not f.is_file(): return self.reply(404,{'error':'File not found'})
            raw=f.read_bytes()
            if route.startswith('/preview/') and f.suffix=='.html':
                source=raw.decode('utf-8')
                source=re.sub(r'<script\b[^>]*>.*?</script\s*>','',source,flags=re.S|re.I)
                source=re.sub(r'''\s+on[a-z]+\s*=\s*(?:"[^"]*"|'[^']*')''','',source,flags=re.I)
                source=re.sub(r'@font-face\s*\{[^}]*\}','',source,flags=re.S|re.I)
                source=re.sub(r'<link\b[^>]*>',lambda m: '' if re.search(r'href=[\"\'](?:https?:)?//',m[0]) else m[0],source,flags=re.I)
                raw=source.encode()
            self.reply(200,raw,mimetypes.guess_type(str(f))[0] or 'application/octet-stream')
        except Exception as e: self.reply(400,{'error':str(e)})
    def do_POST(self):
        try:
            self.guard(True)
            if self.headers.get('Content-Type')!='application/json': raise ValueError('Expected JSON.')
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<15000000: raise ValueError('File too large (maximum image size: 8 MB).')
            data=json.loads(self.rfile.read(length))
            if not LOCK.acquire(blocking=False): return self.reply(409,{'error':'Another save or publish is running. Wait for it to finish.'})
            try:
                if self.path=='/api/save': result=save_page(data)
                elif self.path=='/api/publish': result=publish()
                elif self.path=='/api/upload':
                    raw=base64.b64decode(data['data'],validate=True)
                    if len(raw)>8*1024*1024: raise ValueError('Please choose an image smaller than 8 MB.')
                    ext=None
                    if raw.startswith(b'\x89PNG\r\n\x1a\n'): ext='.png'
                    elif raw.startswith(b'\xff\xd8\xff'): ext='.jpg'
                    elif raw.startswith((b'GIF87a',b'GIF89a')): ext='.gif'
                    elif raw.startswith(b'RIFF') and raw[8:12]==b'WEBP': ext='.webp'
                    if not ext: raise ValueError('Choose a PNG, JPEG, GIF, or WebP image.')
                    name=re.sub(r'[^A-Za-z0-9_-]','-',Path(data.get('name','image')).stem)[:60] or 'image'
                    rel='assets/uploads/'+name+'-'+hashlib.sha256(raw).hexdigest()[:12]+ext
                    dest=ROOT/'site'/rel; dest.parent.mkdir(exist_ok=True); dest.write_bytes(raw)
                    result={'path':rel}
                else: raise ValueError('Unknown action.')
                self.reply(200,result)
            finally: LOCK.release()
        except Exception as e: self.reply(400,{'error':str(e)})

def main():
    global PORT
    parser=argparse.ArgumentParser(); parser.add_argument('--no-open',action='store_true'); parser.add_argument('--port',type=int,default=0); args=parser.parse_args()
    server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler); PORT=server.server_port
    url=f'http://127.0.0.1:{PORT}/'; print('Yu Lab local CMS: '+url,flush=True)
    if not args.no_open: webbrowser.open(url)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()
if __name__=='__main__': main()

import importlib.util, json, os, shutil, subprocess, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('cms',Path(__file__).with_name('server.py'))
cms=importlib.util.module_from_spec(spec);spec.loader.exec_module(cms)
SOURCE=cms.ROOT
class CMS(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.base=Path(self.temp.name);self.repo=self.base/'repo'
        shutil.copytree(SOURCE,self.repo,ignore=shutil.ignore_patterns('.git','__pycache__'))
        cms.ROOT=self.repo
        self.git('init','-b','main');self.git('config','user.name','CMS Test');self.git('config','user.email','cms@example.invalid')
        self.git('add','.');self.git('commit','-m','baseline')
    def tearDown(self): cms.ROOT=SOURCE;self.temp.cleanup()
    def git(self,*args):return subprocess.check_output(['git',*args],cwd=self.repo,stderr=subprocess.STDOUT,text=True).strip()
    def remote(self):
        remote=self.base/'remote.git';subprocess.check_call(['git','init','--bare',str(remote)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        self.git('remote','add','origin',str(remote));self.git('push','-u','origin','main');return remote
    def test_noop_preserves_all_templates(self):
        for key in cms.PAGES:
            p=cms.load_page(key);before=cms.template(key).read_bytes()
            with patch.object(cms,'build'):cms.save_page({'page':key,'version':p['version'],'blocks':p['blocks']})
            self.assertEqual(before,cms.template(key).read_bytes())
    def test_save_build_and_stale_window(self):
        p=cms.load_page('index');p['blocks'][0]['html']='<h1>Edited lab title</h1>'
        cms.save_page(p)
        self.assertIn('Edited lab title',(self.repo/'site/index.html').read_text())
        with self.assertRaisesRegex(ValueError,'another window'):cms.save_page(p)
    def test_failed_build_restores_template(self):
        p=cms.load_page('index');before=cms.template('index').read_bytes();p['blocks'][0]['html']='<p>Change</p>'
        with patch.object(cms,'build',side_effect=ValueError('fail')):
            with self.assertRaisesRegex(ValueError,'restored'):cms.save_page(p)
        self.assertEqual(before,cms.template('index').read_bytes())
    def test_reject_code_and_unsafe_links(self):
        for value in ['<script>alert(1)</script>','<p>{{ 7*7 }}</p>','<a href="javascript:alert(1)">x</a>','<img src="x">']:
            with self.assertRaises(ValueError):cms.clean(value)
        self.assertEqual(cms.clean('<p><b>Good</b> text</p>'),'<p><b>Good</b> text</p>')
    def test_new_entry_and_image(self):
        p=cms.load_page('news');p['addition']={'html':'<h3>New discovery</h3><p>Details</p>','image':'assets/Brain_research_logo.png'}
        cms.save_page(p);source=(self.repo/'site/news/index.html').read_text()
        self.assertIn('New discovery',source);self.assertIn('../assets/Brain_research_logo.png',source)
    def test_publish_and_retry_no_new_commit(self):
        remote=self.remote()
        p=cms.load_page('index');p['blocks'][0]['html']='<p>Publish test</p>';cms.save_page(p)
        with patch.dict(os.environ,LOCAL_CMS_TEST='1'):
            result=cms.publish();first=self.git('rev-parse','HEAD');cms.publish()
        self.assertEqual(first,self.git('rev-parse','HEAD'))
        self.assertEqual(first,subprocess.check_output(['git','--git-dir',str(remote),'rev-parse','main'],text=True).strip())
        self.assertIn('Sent to GitHub',result['message'])
    def test_conflict_aborts_and_preserves_local_commit(self):
        remote=self.remote();other=self.base/'other';subprocess.check_call(['git','clone','-b','main',str(remote),str(other)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        def othergit(*args):subprocess.check_call(['git','-C',str(other),*args],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        othergit('config','user.name','Other');othergit('config','user.email','other@example.invalid')
        path=other/'templates/index.njk';path.write_text(path.read_text().replace('YU LAB','Remote lab'))
        othergit('add','.');othergit('commit','-m','remote change');othergit('push')
        local=cms.template('index');local.write_text(local.read_text().replace('YU LAB','Local lab'))
        with patch.dict(os.environ,LOCAL_CMS_TEST='1'):
            with self.assertRaisesRegex(ValueError,'overlapping'):cms.publish()
        self.assertIn('Local lab',local.read_text());self.assertFalse((self.repo/'.git/MERGE_HEAD').exists());self.assertEqual(self.git('status','--porcelain'),'')
    def test_unrelated_files_block_publish(self):
        self.remote();(self.repo/'private-notes.txt').write_text('Do not publish')
        with patch.dict(os.environ,LOCAL_CMS_TEST='1'):
            with self.assertRaisesRegex(ValueError,'Other repository changes'):cms.publish()
    def test_rejected_push_retries_saved_commit(self):
        remote=self.remote();hook=remote/'hooks/pre-receive';hook.write_text('#!/bin/sh\nexit 1\n');hook.chmod(0o755)
        cms.template('index').write_text(cms.template('index').read_text().replace('YU LAB','Saved retry'))
        with patch.dict(os.environ,LOCAL_CMS_TEST='1'):
            with self.assertRaisesRegex(ValueError,'did not accept'):cms.publish()
            saved=self.git('rev-parse','HEAD');hook.unlink();cms.publish()
        self.assertEqual(saved,self.git('rev-parse','HEAD'))
    def test_http_origin_guard_and_preview(self):
        import threading, urllib.request, urllib.error
        server=cms.ThreadingHTTPServer(('127.0.0.1',0),cms.Handler);cms.PORT=server.server_port
        worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
        base='http://127.0.0.1:'+str(cms.PORT)
        try:
            req=urllib.request.Request(base+'/api/upload',data=b'{}',headers={'Content-Type':'application/json'})
            with self.assertRaises(urllib.error.HTTPError):urllib.request.urlopen(req)
            req=urllib.request.Request(base+'/api/pages',headers={'Host':'evil.example'})
            with self.assertRaises(urllib.error.HTTPError):urllib.request.urlopen(req)
            with urllib.request.urlopen(base+'/preview/') as response:
                self.assertNotIn('<script',response.read().decode().lower())
            payload={'name':'test.png','data':'iVBORw0KGgo='}
            req=urllib.request.Request(base+'/api/upload',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json','Origin':base,'X-CMS-Token':cms.TOKEN})
            with urllib.request.urlopen(req) as response:self.assertIn('assets/uploads/test-',response.read().decode())
        finally:server.shutdown();server.server_close();worker.join()
    def test_swap_file_does_not_block_or_publish(self):
        remote=self.remote();swap=self.repo/'.LOCAL-CMS.md.swp';swap.write_text('local recovery data')
        self.assertNotIn('.LOCAL-CMS.md.swp',cms.changed())
        with patch.dict(os.environ,LOCAL_CMS_TEST='1'):cms.publish()
        self.assertTrue(swap.exists())
        self.assertNotIn('.LOCAL-CMS.md.swp',self.git('ls-tree','-r','--name-only','HEAD'))
    def test_canvas_layout_persists_and_resets(self):
        p=cms.load_page('index');block=p['blocks'][0]
        self.assertTrue(block['domId'])
        block['layout']={'x':18,'y':24,'width':420}
        updated=cms.save_page({'page':'index','version':p['version'],'blocks':[block]})
        self.assertEqual(updated['blocks'][0]['layout'],{'x':18.0,'y':24.0,'width':'420.0'})
        self.assertIn('translate:18.0px 24.0px',(self.repo/'site/index.html').read_text())
        updated['blocks'][0]['layout']={'x':0,'y':0,'width':''}
        restored=cms.save_page({'page':'index','version':updated['version'],'blocks':[updated['blocks'][0]]})
        self.assertEqual(restored['blocks'][0]['layout']['width'],'')
    def test_layout_validation(self):
        for values in [{'x':'nan'},{'width':-10},{'y':9000},{'x':'bad'}]:
            with self.assertRaises(ValueError):cms.layout_tag('<div>',values)
    def test_path_validation(self):
        with self.assertRaises(ValueError):cms.template('../secret')
        with self.assertRaises(ValueError):cms.safe_url('assets/../../secret',True)
if __name__=='__main__':unittest.main()

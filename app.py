import os, shutil, hashlib, threading, queue, datetime, re
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk, ExifTags

EXTS={'.jpg','.jpeg','.png','.webp','.bmp','.tif','.tiff','.gif'}
CATEGORIES={'수목':['tree','forest','plant','flower','leaf'],'공사현장':['construction','building','road','equipment'],'인물':['person','portrait','people'],'문서':['document','paper','text'],'제품':['product','object','tool']}

def photo_date(p):
    try:
        with Image.open(p) as im:
            exif=im.getexif()
            for key in (36867,36868,306):
                v=exif.get(key)
                if v:
                    return datetime.datetime.strptime(str(v)[:19],'%Y:%m:%d %H:%M:%S')
    except Exception: pass
    return datetime.datetime.fromtimestamp(p.stat().st_mtime)

def digest(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()

def phash(p):
    try:
        import imagehash
        with Image.open(p) as im:return imagehash.phash(im.convert('RGB'))
    except Exception:return None

class App:
    def __init__(self,root):
        self.root=root;root.title('Photo Organizer AI — 사진 정리');root.geometry('1100x690')
        self.source=tk.StringVar();self.dest=tk.StringVar();self.status=tk.StringVar(value='사진 폴더를 선택하세요.');self.items=[];self.q=queue.Queue();self.hashes={};self.running=False
        top=ttk.Frame(root,padding=12);top.pack(fill='x')
        for label,var in [('원본 사진 폴더',self.source),('정리 결과 폴더',self.dest)]:
            row=ttk.Frame(top);row.pack(fill='x',pady=3);ttk.Label(row,text=label,width=17).pack(side='left');ttk.Entry(row,textvariable=var).pack(side='left',fill='x',expand=True);ttk.Button(row,text='찾아보기',command=lambda v=var:v.set(filedialog.askdirectory() or v.get())).pack(side='left',padx=5)
        bar=ttk.Frame(top);bar.pack(fill='x',pady=8)
        ttk.Button(bar,text='1. 사진 분석',command=self.scan).pack(side='left',padx=3)
        ttk.Button(bar,text='2. 승인한 사진 복사 정리',command=self.copy).pack(side='left',padx=3)
        ttk.Button(bar,text='중복만 보기',command=lambda:self.filter('duplicate')).pack(side='left',padx=3)
        ttk.Button(bar,text='전체 보기',command=lambda:self.filter('all')).pack(side='left',padx=3)
        ttk.Label(bar,text='검색:').pack(side='left',padx=(20,3));self.search=tk.StringVar();ttk.Entry(bar,textvariable=self.search,width=24).pack(side='left');self.search.trace_add('write',lambda *_:self.filter('search'))
        self.tree=ttk.Treeview(root,columns=('date','category','duplicate','target'),show='tree headings',selectmode='extended')
        self.tree.heading('#0',text='원본 파일');self.tree.column('#0',width=300)
        for key,label,w in [('date','촬영일',110),('category','분류 (수정 가능)',150),('duplicate','중복',95),('target','정리될 경로',380)]:self.tree.heading(key,text=label);self.tree.column(key,width=w)
        self.tree.pack(fill='both',expand=True,padx=12,pady=4);self.tree.bind('<Double-1>',self.edit_category)
        bottom=ttk.Frame(root,padding=12);bottom.pack(fill='x');ttk.Label(bottom,textvariable=self.status).pack(side='left');ttk.Label(bottom,text='더블클릭: 분류 수정 | 원본은 삭제하지 않습니다.').pack(side='right')
        root.after(100,self.poll)
    def run_worker(self,fn):
        if self.running:return
        self.running=True;threading.Thread(target=fn,daemon=True).start()
    def scan(self):
        src=Path(self.source.get()).expanduser();dst=Path(self.dest.get()).expanduser() if self.dest.get() else None
        if not src.is_dir():messagebox.showerror('오류','원본 폴더를 선택하세요.');return
        if dst and (dst==src or src in dst.parents):messagebox.showerror('오류','정리 결과 폴더는 원본 폴더 밖에 지정하세요.');return
        self.items=[];self.hashes={};self.tree.delete(*self.tree.get_children())
        def work():
            try:
                paths=[p for p in src.rglob('*') if p.is_file() and p.suffix.lower() in EXTS]
                seen={};perceptual=[]
                for i,p in enumerate(paths):
                    try:
                        dt=photo_date(p);sha=digest(p);dup='완전 중복' if sha in seen else ''
                        if not dup:seen[sha]=p
                        ph=phash(p)
                        if ph is not None and not dup:
                            if any(abs(ph-h)<=5 for h in perceptual):dup='유사 사진'
                            perceptual.append(ph)
                        cat='미분류';target=f'{cat}/{dt:%Y}/{dt:%m}/{dt:%Y%m%d}_{i+1:05d}{p.suffix.lower()}'
                        item={'path':p,'date':dt,'category':cat,'duplicate':dup,'target':target,'approved':True}
                        self.q.put(('item',item))
                    except Exception as e:self.q.put(('status',f'읽기 실패: {p.name}: {e}'))
                    if i%20==0:self.q.put(('status',f'분석 중 {i+1}/{len(paths)}'))
                self.q.put(('status',f'분석 완료: {len(paths)}개 파일. 분류는 더블클릭하여 지정하세요.'))
            except Exception as e:self.q.put(('error',str(e)))
            finally:self.q.put(('done',None))
        self.run_worker(work)
    def edit_category(self,event):
        iid=self.tree.identify_row(event.y)
        if not iid:return
        item=self.items[int(iid)];win=tk.Toplevel(self.root);win.title('사진 분류 수정');win.geometry('320x135');win.transient(self.root);win.grab_set()
        ttk.Label(win,text='분류명을 선택하거나 직접 입력하세요.').pack(pady=8)
        v=tk.StringVar(value=item['category']);cb=ttk.Combobox(win,textvariable=v,values=['수목','조경','공사현장','제품','인물','문서','일상','기타','미분류']);cb.pack(fill='x',padx=14)
        def save():
            item['category']=re.sub(r'[\\/:*?"<>|]','_',v.get().strip()) or '미분류';item['target']=f"{item['category']}/{item['date']:%Y}/{item['date']:%m}/{item['date']:%Y%m%d}_{int(iid)+1:05d}{item['path'].suffix.lower()}";self.tree.item(iid,values=(item['date'].strftime('%Y-%m-%d'),item['category'],item['duplicate'],item['target']));win.destroy()
        ttk.Button(win,text='적용',command=save).pack(pady=10)
    def filter(self,mode):
        term=self.search.get().lower();self.tree.delete(*self.tree.get_children())
        for i,item in enumerate(self.items):
            if mode=='duplicate' and not item['duplicate']:continue
            if mode=='search' and term not in (str(item['path'])+' '+item['category']+' '+item['date'].strftime('%Y-%m-%d')).lower():continue
            self.tree.insert('', 'end',iid=str(i),text=item['path'].name,values=(item['date'].strftime('%Y-%m-%d'),item['category'],item['duplicate'],item['target']))
    def copy(self):
        if self.running:return
        dst=Path(self.dest.get()).expanduser()
        if not self.dest.get():messagebox.showerror('오류','정리 결과 폴더를 선택하세요.');return
        src=Path(self.source.get()).expanduser()
        if dst==src or src in dst.parents:messagebox.showerror('오류','결과 폴더를 원본 폴더 밖에 지정하세요.');return
        if not self.items:return
        if not messagebox.askyesno('복사 확인',f'{len(self.items)}개 파일을 결과 폴더에 복사할까요? 원본은 유지됩니다.'):return
        def work():
            try:
                for i,item in enumerate(self.items):
                    target=dst/item['target'];target.parent.mkdir(parents=True,exist_ok=True)
                    if target.exists():
                        stem=target.stem;n=1
                        while target.exists():target=target.with_name(f'{stem}_{n}{target.suffix}');n+=1
                    shutil.copy2(item['path'],target)
                    if i%10==0:self.q.put(('status',f'복사 중 {i+1}/{len(self.items)}'))
                self.q.put(('status',f'복사 완료: {len(self.items)}개. 원본 유지.'))
            except Exception as e:self.q.put(('error',str(e)))
            finally:self.q.put(('done',None))
        self.run_worker(work)
    def poll(self):
        try:
            while True:
                kind,data=self.q.get_nowait()
                if kind=='item':
                    i=len(self.items);self.items.append(data);self.tree.insert('','end',iid=str(i),text=data['path'].name,values=(data['date'].strftime('%Y-%m-%d'),data['category'],data['duplicate'],data['target']))
                elif kind=='status':self.status.set(data)
                elif kind=='error':self.status.set('오류: '+data)
                elif kind=='done':self.running=False
        except queue.Empty:pass
        self.root.after(100,self.poll)
if __name__=='__main__':
    root=tk.Tk();App(root);root.mainloop()

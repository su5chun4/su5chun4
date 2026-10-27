import hashlib
import re
import queue
import shutil
import threading
import datetime as dt
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image

EXTS = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tif', '.tiff', '.gif'}

def filename_datetime(name):
    """Return a filename-derived datetime and an explanatory source, or None."""
    stem = Path(name).stem
    # Samsung, KakaoTalk, Resized and ordinary camera exports often retain
    # YYYYMMDD_HHMMSS, sometimes followed immediately by milliseconds.
    match = re.search(r'(?<!\d)((?:19|20)\d{2})(\d{2})(\d{2})[_\- .]?(\d{2})(\d{2})(\d{2})(?:\d{3})?(?!\d)', stem)
    if match:
        try:
            value = dt.datetime(*map(int, match.groups()))
            return value, '파일명 날짜·시간 (추정)'
        except ValueError:
            pass
    # Files named with UNIX milliseconds, e.g. 1792972599775.jpg.
    # Interpreted as Korea Standard Time (UTC+09:00).
    for match in re.finditer(r'(?<!\d)(\d{13})(?!\d)', stem):
        try:
            value = dt.datetime.fromtimestamp(int(match.group(1)) / 1000, tz=dt.timezone(dt.timedelta(hours=9))).replace(tzinfo=None)
            if 2000 <= value.year <= 2100:
                return value, '파일명 UNIX ms (추정·한국시간)'
        except (ValueError, OSError, OverflowError):
            pass
    # Date-only filenames: hour is *unknown*. Return midnight for folder
    # placement, but make that limitation conspicuous in the source column.
    match = re.search(r'(?<!\d)((?:19|20)\d{2})(\d{2})(\d{2})(?!\d)', stem)
    if match:
        try:
            value = dt.datetime(*map(int, match.groups()))
            return value, '파일명 날짜만 (시각 미상: 00시 임시값)'
        except ValueError:
            pass
    return None


def taken_at(path):
    try:
        with Image.open(path) as image:
            exif = image.getexif()
            for tag in (36867, 36868, 306):
                value = exif.get(tag)
                if value:
                    try:
                        value = dt.datetime.strptime(str(value)[:19], '%Y:%m:%d %H:%M:%S')
                        source = 'EXIF 촬영일' if tag == 36867 else ('EXIF 원본 생성일' if tag == 36868 else 'EXIF 이미지 수정일 (촬영일 미확인)')
                        return value, source
                    except ValueError:
                        pass
    except Exception:
        pass
    from_name = filename_datetime(path.name)
    if from_name:
        return from_name
    return dt.datetime.fromtimestamp(path.stat().st_mtime), '파일 수정일 (촬영일 미확인)'

def sha256(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()

def is_inside(path, folder):
    return path == folder or folder in path.parents

class PhotoOrganizer:
    def __init__(self, root):
        self.root = root
        root.title('Photo Organizer AI | 날짜·시간 자동 정리 v3')
        root.geometry('1050x700')
        self.source = tk.StringVar()
        self.dest = tk.StringVar()
        self.remove_duplicates = tk.BooleanVar(value=True)
        self.by_date = tk.BooleanVar(value=True)
        self.by_hour = tk.BooleanVar(value=False)
        self.status = tk.StringVar(value='원본 폴더와 결과 폴더를 선택하세요.')
        self.items = []
        self.q = queue.Queue()
        self.busy = False
        self.scanned_source = None
        self.dirty = True

        top = ttk.Frame(root, padding=12)
        top.pack(fill='x')
        for label, var in [('1. 원본 사진 폴더', self.source), ('결과 저장 폴더', self.dest)]:
            line = ttk.Frame(top)
            line.pack(fill='x', pady=4)
            ttk.Label(line, text=label, width=19).pack(side='left')
            ttk.Entry(line, textvariable=var).pack(side='left', expand=True, fill='x')
            ttk.Button(line, text='폴더 선택', command=lambda v=var: self.browse(v)).pack(side='left', padx=5)

        controls = ttk.LabelFrame(root, text='원하는 기능만 선택', padding=12)
        controls.pack(fill='x', padx=12, pady=5)
        ttk.Label(controls, text='2. 사진 분석: EXIF → 파일명 → 수정일로 날짜·시간 추출 (항상 실행)').pack(anchor='w', pady=3)
        ttk.Checkbutton(controls, text='3. 완전히 같은 중복 사진은 결과에서 제외', variable=self.remove_duplicates, command=self.update_plan).pack(anchor='w', pady=3)
        ttk.Checkbutton(controls, text='4. 날짜별 폴더 정리 (연도 / 월 / 일)', variable=self.by_date, command=self.date_changed).pack(anchor='w', pady=3)
        ttk.Checkbutton(controls, text='5. 시간별 폴더까지 정리 (연도 / 월 / 일 / 00시~23시)', variable=self.by_hour, command=self.hour_changed).pack(anchor='w', pady=3)
        actions = ttk.Frame(controls)
        actions.pack(fill='x', pady=(8, 2))
        self.preview_button = ttk.Button(actions, text='사진 분석 / 미리보기', command=self.analyze)
        self.preview_button.pack(side='left', padx=(0, 8))
        self.execute_button = ttk.Button(actions, text='선택 기능 한 번에 정리', command=self.organize)
        self.execute_button.pack(side='left')
        self.plan = tk.StringVar()
        ttk.Label(controls, textvariable=self.plan).pack(anchor='w', pady=(10, 0))
        self.update_plan()

        results = ttk.Frame(root, padding=(12, 0, 12, 0))
        results.pack(fill='both', expand=True)
        self.tree = ttk.Treeview(results, columns=('date', 'source', 'duplicate', 'target'), show='tree headings')
        self.tree.heading('#0', text='사진 파일명')
        self.tree.column('#0', width=220)
        for name, label, width in [('date', '촬영 일시', 155), ('source', '날짜 출처', 90), ('duplicate', '중복 여부', 110), ('target', '결과 경로 (예정)', 430)]:
            self.tree.heading(name, text=label)
            self.tree.column(name, width=width)
        scrollbar = ttk.Scrollbar(results, orient='vertical', command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')
        footer = ttk.Frame(root, padding=12)
        footer.pack(fill='x')
        ttk.Label(footer, textvariable=self.status).pack(side='left')
        ttk.Label(footer, text='원본 사진은 삭제하거나 이동하지 않습니다.').pack(side='right')
        self.source.trace_add('write', lambda *_: self.invalidate())
        root.after(100, self.poll)

    def browse(self, var):
        selected = filedialog.askdirectory()
        if selected:
            var.set(selected)

    def invalidate(self):
        self.dirty = True

    def date_changed(self):
        if not self.by_date.get():
            self.by_hour.set(False)
        self.update_plan()

    def hour_changed(self):
        if self.by_hour.get():
            self.by_date.set(True)
        self.update_plan()

    def update_plan(self):
        if self.by_hour.get():
            grouping = '연도 / 월 / 일 / 시간'
        elif self.by_date.get():
            grouping = '연도 / 월 / 일'
        else:
            grouping = '폴더 구분 없음'
        self.plan.set(f"결과: {grouping} | 중복: {'제외' if self.remove_duplicates.get() else '포함'} | 처리 방식: 원본 유지 + 복사")
        if self.items and not self.busy:
            self.refresh_tree()

    def valid_paths(self, needs_destination=False):
        if not self.source.get().strip():
            messagebox.showerror('원본 폴더', '원본 사진 폴더를 선택해 주세요.')
            return None
        src = Path(self.source.get()).expanduser().resolve()
        if not src.is_dir():
            messagebox.showerror('원본 폴더', '원본 사진 폴더가 존재하지 않습니다.')
            return None
        dst = None
        if self.dest.get().strip():
            dst = Path(self.dest.get()).expanduser().resolve()
            if is_inside(dst, src) or is_inside(src, dst):
                messagebox.showerror('폴더 지정', '원본 폴더와 결과 폴더가 서로 포함되지 않도록 별도 폴더를 선택하세요.')
                return None
        elif needs_destination:
            messagebox.showerror('결과 폴더', '결과 저장 폴더를 선택해 주세요.')
            return None
        return src, dst

    def folder_part(self, item):
        stamp = item['date']
        if self.by_hour.get():
            return Path(stamp.strftime('%Y년')) / stamp.strftime('%m월') / stamp.strftime('%d일') / stamp.strftime('%H시')
        if self.by_date.get():
            return Path(stamp.strftime('%Y년')) / stamp.strftime('%m월') / stamp.strftime('%d일')
        return Path('.')

    def target_name(self, item):
        stamp = item['date'].strftime('%Y%m%d_%H%M%S')
        return f"{stamp}_{item['index']:06d}{item['path'].suffix.lower()}"

    def should_skip(self, item):
        return self.remove_duplicates.get() and item['duplicate']

    def refresh_tree(self):
        self.tree.delete(*self.tree.get_children())
        for i, item in enumerate(self.items):
            destination = '복사 제외 (완전 중복)' if self.should_skip(item) else str(self.folder_part(item) / self.target_name(item))
            self.tree.insert('', 'end', iid=str(i), text=item['path'].name, values=(item['date'].strftime('%Y-%m-%d %H:%M:%S'), item['date_source'], '완전 중복' if item['duplicate'] else '-', destination))

    def begin(self, work):
        if self.busy:
            return
        self.busy = True
        self.preview_button.state(['disabled'])
        self.execute_button.state(['disabled'])
        threading.Thread(target=work, daemon=True).start()

    def analyze(self):
        paths = self.valid_paths()
        if paths is None or self.busy:
            return
        src, _ = paths
        self.items.clear()
        self.tree.delete(*self.tree.get_children())
        self.dirty = True
        self.status.set('사진 분석 시작...')
        self.begin(lambda: self.worker_scan(src, copy_after=False))

    def organize(self):
        paths = self.valid_paths(needs_destination=True)
        if paths is None or self.busy:
            return
        src, dst = paths
        if not messagebox.askyesno('정리 실행 확인', '선택한 기능으로 사진을 분석하고 결과 폴더에 복사할까요?\n원본 파일은 삭제하지 않습니다.\n완전 중복은 옵션에 따라 결과에서 제외합니다.'):
            return
        self.items.clear()
        self.tree.delete(*self.tree.get_children())
        self.status.set('사진 분석 및 정리 시작...')
        self.begin(lambda: self.worker_scan(src, copy_after=True, dst=dst))

    def worker_scan(self, src, copy_after=False, dst=None):
        try:
            paths = sorted((p for p in src.rglob('*') if p.is_file() and p.suffix.lower() in EXTS), key=lambda p: str(p).casefold())
            count = len(paths)
            seen = {}
            all_items = []
            errors = []
            for index, path in enumerate(paths, start=1):
                try:
                    stamp, origin = taken_at(path)
                    hash_value = sha256(path)
                    repeated = hash_value in seen
                    if not repeated:
                        seen[hash_value] = path
                    all_items.append({'path': path, 'index': index, 'date': stamp, 'date_source': origin, 'duplicate': repeated})
                except Exception as exc:
                    errors.append(f'{path}: {exc}')
                if index % 10 == 0 or index == count:
                    self.q.put(('status', f'분석 중 {index}/{count}장'))
            self.q.put(('items', (src, all_items)))
            if copy_after:
                self.worker_copy(all_items, dst, errors)
            else:
                self.q.put(('complete', f'분석 완료: {len(all_items)}장 / 중복 {sum(x["duplicate"] for x in all_items)}장 / 읽기 실패 {len(errors)}장'))
        except Exception as exc:
            self.q.put(('error', str(exc)))
        finally:
            self.q.put(('done', None))

    def worker_copy(self, items, dst, errors):
        # Options are captured at execution start; UI controls are disabled during processing.
        omit_duplicates = self.remove_duplicates.get()
        group_hour = self.by_hour.get()
        group_date = self.by_date.get()
        copied, skipped = 0, 0
        dst.mkdir(parents=True, exist_ok=True)
        for idx, item in enumerate(items, start=1):
            if omit_duplicates and item['duplicate']:
                skipped += 1
                continue
            try:
                stamp = item['date']
                folder = dst
                if group_date:
                    folder = folder / stamp.strftime('%Y년') / stamp.strftime('%m월') / stamp.strftime('%d일')
                if group_hour:
                    folder = folder / stamp.strftime('%H시')
                folder.mkdir(parents=True, exist_ok=True)
                target = folder / self.target_name(item)
                original_stem = target.stem
                suffix_index = 1
                while target.exists():
                    target = folder / f'{original_stem}_{suffix_index}{target.suffix}'
                    suffix_index += 1
                shutil.copy2(item['path'], target)
                copied += 1
            except Exception as exc:
                errors.append(f'{item["path"]}: {exc}')
            if idx % 10 == 0 or idx == len(items):
                self.q.put(('status', f'정리 중 {idx}/{len(items)}장 · 복사 {copied}장'))
        report = dst / 'photo_organizer_report.txt'
        with report.open('w', encoding='utf-8') as fh:
            fh.write(f'처리 시각: {dt.datetime.now().isoformat(timespec="seconds")}\n')
            fh.write(f'원본 파일: {len(items)}장\n복사 성공: {copied}장\n중복 제외: {skipped}장\n오류: {len(errors)}건\n')
            fh.write('중복 판정: 파일 SHA-256 완전 일치 (비슷한 사진은 제거하지 않음)\n')
            fh.write('날짜 출처: EXIF 촬영일 → 파일명 추정 → 파일 수정일 대체\n')
            fh.write('파일명 UNIX ms는 한국시간(KST, UTC+9) 기준으로 해석함\n')
            fh.write('주의: 파일명 날짜는 실제 촬영 시간이 아닐 수 있음\n')
            fh.write('\n사진별 날짜 출처:\n')
            for item in items:
                fh.write(f"{item['path']} | {item['date']:%Y-%m-%d %H:%M:%S} | {item['date_source']} | {'중복' if item['duplicate'] else '고유'}\n")
            fh.write('원본 파일은 삭제하거나 이동하지 않음\n')
            if errors:
                fh.write('\n오류 목록:\n' + '\n'.join(errors))
        self.q.put(('complete', f'정리 완료: 복사 {copied}장 / 중복 제외 {skipped}장 / 오류 {len(errors)}건 · 보고서 저장'))

    def poll(self):
        try:
            while True:
                kind, data = self.q.get_nowait()
                if kind == 'status':
                    self.status.set(data)
                elif kind == 'items':
                    self.scanned_source, self.items = data
                    self.dirty = False
                    self.refresh_tree()
                elif kind == 'complete':
                    self.status.set(data)
                    messagebox.showinfo('처리 완료', data)
                elif kind == 'error':
                    self.status.set('오류: ' + data)
                    messagebox.showerror('오류', data)
                elif kind == 'done':
                    self.busy = False
                    self.preview_button.state(['!disabled'])
                    self.execute_button.state(['!disabled'])
        except queue.Empty:
            pass
        self.root.after(100, self.poll)

if __name__ == '__main__':
    window = tk.Tk()
    PhotoOrganizer(window)
    window.mainloop()

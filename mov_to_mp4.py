"""
MOV -> MP4 converter with a GUI, per-file progress bars, and bounded parallel
conversion (a worker pool).

How it works (the short version):
- A ThreadPoolExecutor is a counting-semaphore-style worker pool: at most N files
  convert at once. A queued file waits until a worker frees a slot.
- Each worker thread launches ONE ffmpeg subprocess (a separate OS process) and
  reads its progress. Threading is fine here because the heavy work is in ffmpeg,
  so Python's GIL is released while the thread waits on the subprocess.
- We cap threads-per-ffmpeg so (workers x threads) is close to your core count,
  which avoids oversubscribing the CPU.

Each .mp4 is saved in the SAME folder as the original.

Run:  python mov_to_mp4.py   (or double-click Convert_MOV_to_MP4.bat)
"""

import os
import re
import time
import threading
import subprocess
from datetime import datetime
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from shutil import which
from concurrent.futures import ThreadPoolExecutor

DUR_RE = re.compile(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)")
TIME_RE = re.compile(r"time=\s*(\d+):(\d+):(\d+(?:\.\d+)?)")

CORES = os.cpu_count() or 4
# You asked for 5 by default; the field lets you change it.
DEFAULT_WORKERS = 5
MAX_WORKERS = 16  # you can oversubscribe past your core count if you want


def get_ffmpeg():
    """Return a path to an ffmpeg executable, preferring a system install."""
    system = which("ffmpeg")
    if system:
        return system
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def _hms(h, m, s):
    return int(h) * 3600 + int(m) * 60 + float(s)


def _iter_progress_lines(stream):
    """Yield lines from ffmpeg output, splitting on both \\r and \\n."""
    buf = ""
    while True:
        ch = stream.read(1)
        if not ch:
            if buf:
                yield buf
            break
        if ch in ("\r", "\n"):
            if buf:
                yield buf
                buf = ""
        else:
            buf += ch


class FileRow:
    """One row: filename, status, progress bar. Failed rows show the reason."""

    def __init__(self, parent, path):
        self.path = path
        self.error = ""
        self.frame = tk.Frame(parent, bd=1, relief="solid", padx=10, pady=8)
        self.frame.pack(fill="x", padx=6, pady=4)

        top = tk.Frame(self.frame)
        top.pack(fill="x")
        tk.Label(
            top, text=os.path.basename(path),
            font=("Segoe UI", 10, "bold"), anchor="w",
        ).pack(side="left")
        self.status = tk.Label(
            top, text="Queued", font=("Segoe UI", 9), fg="#888", anchor="e"
        )
        self.status.pack(side="right")

        self.bar_var = tk.DoubleVar(value=0)
        ttk.Progressbar(
            self.frame, maximum=100, variable=self.bar_var, length=100
        ).pack(fill="x", pady=(6, 0))

        self.err_label = None

    def set_status(self, text, color):
        self.status.configure(text=text, fg=color)

    def set_progress(self, pct):
        self.bar_var.set(max(0, min(100, pct)))

    def set_state(self):
        return self.status.cget("text")

    def show_error(self, msg):
        self.error = msg
        if self.err_label is None:
            self.err_label = tk.Label(
                self.frame, text="", font=("Consolas", 8), fg="#d33",
                anchor="w", justify="left", wraplength=520,
            )
            self.err_label.pack(fill="x", pady=(4, 0))
        short = msg.strip().splitlines()[-1] if msg.strip() else "Conversion failed"
        self.err_label.configure(text=short[:200])


class App:
    def __init__(self, root):
        self.root = root
        self.rows = []
        self.running = False
        self.done_count = 0
        self.total_count = 0
        self.lock = threading.Lock()

        root.title("MOV -> MP4 Converter")
        root.geometry("640x560")
        root.minsize(540, 440)

        tk.Label(
            root, text="MOV -> MP4 Converter", font=("Segoe UI", 15, "bold")
        ).pack(pady=(14, 2))
        tk.Label(
            root,
            text=f"Each .mp4 is saved next to its original. Detected {CORES} CPU cores.",
            font=("Segoe UI", 9), fg="#555",
        ).pack(pady=(0, 8))

        # Controls
        ctl = tk.Frame(root)
        ctl.pack(fill="x", padx=10)
        self.add_btn = tk.Button(
            ctl, text="Add .MOV file(s)", font=("Segoe UI", 10, "bold"),
            command=self.pick_files, padx=12, pady=6,
        )
        self.add_btn.pack(side="left")
        self.clear_btn = tk.Button(
            ctl, text="Clear finished", font=("Segoe UI", 10),
            command=self.clear_finished, padx=12, pady=6,
        )
        self.clear_btn.pack(side="left", padx=6)

        tk.Label(ctl, text="Parallel files:", font=("Segoe UI", 9)).pack(
            side="left", padx=(10, 2)
        )
        self.worker_var = tk.StringVar(value=str(DEFAULT_WORKERS))
        self.worker_box = ttk.Spinbox(
            ctl, from_=1, to=MAX_WORKERS, width=4, textvariable=self.worker_var,
            justify="center",
        )
        self.worker_box.pack(side="left")

        self.convert_btn = tk.Button(
            ctl, text="Convert all", font=("Segoe UI", 10, "bold"),
            bg="#2d6cdf", fg="white", activebackground="#1f4fa8",
            command=self.start, padx=12, pady=6, state="disabled",
        )
        self.convert_btn.pack(side="right")

        # Running-total header
        self.header = tk.Label(
            root, text="No files queued.", font=("Segoe UI", 10, "bold"), fg="#333"
        )
        self.header.pack(pady=(10, 0))

        # Scrollable list
        container = tk.Frame(root)
        container.pack(fill="both", expand=True, padx=10, pady=8)
        self.canvas = tk.Canvas(container, highlightthickness=0)
        scroll = ttk.Scrollbar(container, orient="vertical", command=self.canvas.yview)
        self.list_frame = tk.Frame(self.canvas)
        self.list_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")),
        )
        self.win = self.canvas.create_window((0, 0), window=self.list_frame, anchor="nw")
        self.canvas.bind(
            "<Configure>", lambda e: self.canvas.itemconfig(self.win, width=e.width)
        )
        self.canvas.configure(yscrollcommand=scroll.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.canvas.bind_all("<MouseWheel>", self._on_wheel)

    def _on_wheel(self, e):
        self.canvas.yview_scroll(int(-e.delta / 120), "units")

    def refresh_convert_button(self):
        """Enabled only when idle AND something still needs converting
        (Queued or a Failed file to retry). Fully-successful run -> stays off."""
        if self.running:
            self.convert_btn.configure(state="disabled")
            return
        has_pending = any(r.set_state() in ("Queued", "Failed") for r in self.rows)
        self.convert_btn.configure(state="normal" if has_pending else "disabled")

    # ---- marshal a call onto the Tk main thread ----
    def ui(self, fn, *args):
        self.root.after(0, lambda: fn(*args))

    def pick_files(self):
        paths = filedialog.askopenfilenames(
            title="Select .mov file(s)",
            filetypes=[("QuickTime video", "*.mov *.MOV"), ("All files", "*.*")],
        )
        existing = {r.path for r in self.rows}
        for p in paths:
            if p not in existing:
                self.rows.append(FileRow(self.list_frame, p))
        self.update_header()
        self.refresh_convert_button()

    def clear_finished(self):
        if self.running:
            return
        keep = []
        for r in self.rows:
            if r.set_state() in ("Finished", "Failed"):
                r.frame.destroy()
            else:
                keep.append(r)
        self.rows = keep
        self.update_header()
        self.refresh_convert_button()

    def update_header(self):
        if self.running:
            self.header.configure(
                text=f"{self.done_count} of {self.total_count} finished..."
            )
        else:
            n = len(self.rows)
            self.header.configure(
                text="No files queued." if n == 0 else f"{n} file(s) queued."
            )

    def start(self):
        if self.running:
            return
        pending = [r for r in self.rows if r.set_state() in ("Queued", "Failed")]
        if not pending:
            messagebox.showinfo("Nothing to do", "Add some .mov files first.")
            return
        ffmpeg = get_ffmpeg()
        if not ffmpeg:
            messagebox.showerror(
                "ffmpeg not found",
                "Could not find ffmpeg. Run Convert_MOV_to_MP4.bat, or install the "
                "'imageio-ffmpeg' Python package.",
            )
            return

        try:
            workers = int(self.worker_var.get())
        except ValueError:
            workers = DEFAULT_WORKERS
        workers = max(1, min(MAX_WORKERS, workers))
        self.worker_var.set(str(workers))
        # Split cores across the concurrent ffmpeg processes to avoid oversubscription.
        threads = max(1, CORES // workers)

        for r in pending:
            r.set_status("Queued", "#888")
            r.set_progress(0)

        self.running = True
        self.done_count = 0
        self.total_count = len(pending)
        self.convert_btn.configure(state="disabled")
        self.add_btn.configure(state="disabled")
        self.worker_box.configure(state="disabled")
        self.update_header()

        threading.Thread(
            target=self.run_batch, args=(ffmpeg, pending, workers, threads),
            daemon=True,
        ).start()

    def run_batch(self, ffmpeg, rows, workers, threads):
        ok = [0]
        failed = []

        def work(row):
            try:
                self.convert_one(ffmpeg, row, threads)
                with self.lock:
                    ok[0] += 1
            except Exception as e:
                msg = str(e)
                self.ui(row.set_status, "Failed", "#d33")
                self.ui(row.set_progress, 0)
                self.ui(row.show_error, msg)
                with self.lock:
                    failed.append(os.path.basename(row.path))
            finally:
                with self.lock:
                    self.done_count += 1
                self.ui(self.update_header)

        # The pool = a bounded, semaphore-like worker set. `with` waits for all.
        with ThreadPoolExecutor(max_workers=workers) as ex:
            for r in rows:
                ex.submit(work, r)

        print(
            f"[DEBUG] Batch complete: {ok[0]}/{self.total_count} processed"
            + (f" | failed ({len(failed)}): {', '.join(failed)}" if failed else " | none failed")
        )

        self.running = False
        self.ui(lambda: self.add_btn.configure(state="normal"))
        self.ui(lambda: self.worker_box.configure(state="normal"))
        self.ui(self.update_header)
        # Convert-all only re-enables if something failed (retry) or files were added.
        self.ui(self.refresh_convert_button)
        self.ui(
            lambda: messagebox.showinfo(
                "Done", f"{ok[0]} converted, {self.total_count - ok[0]} failed."
            )
        )

    def convert_one(self, ffmpeg, row, threads):
        path = row.path
        folder = os.path.dirname(path)
        base = os.path.splitext(os.path.basename(path))[0]
        out_path = os.path.join(folder, base + ".mp4")
        counter = 1
        while os.path.exists(out_path):
            out_path = os.path.join(folder, f"{base}_{counter}.mp4")
            counter += 1

        start_time = time.time()
        start_stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        in_size_mb = os.path.getsize(path) / (1024 * 1024)
        print(
            f"[DEBUG :: {start_stamp}] Converting: {os.path.basename(path)} {in_size_mb:.1f} MB"
        )

        self.ui(row.set_status, "Converting", "#2d6cdf")
        self.ui(row.set_progress, 0)

        cmd = [
            ffmpeg, "-i", path,
            "-threads", str(threads),
            "-c:v", "libx264", "-preset", "medium", "-crf", "20",
            "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart", "-y", out_path,
        ]

        startupinfo = None
        if os.name == "nt":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

        proc = subprocess.Popen(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            universal_newlines=True, startupinfo=startupinfo,
        )

        total = None
        tail = ""
        for line in _iter_progress_lines(proc.stderr):
            tail = line
            if total is None:
                m = DUR_RE.search(line)
                if m:
                    total = _hms(*m.groups())
            m = TIME_RE.search(line)
            if m and total:
                self.ui(row.set_progress, _hms(*m.groups()) / total * 100)

        proc.wait()
        if proc.returncode != 0:
            raise RuntimeError(tail or "ffmpeg failed")

        end_time = time.time()
        end_stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        elapsed = end_time - start_time
        out_size_mb = os.path.getsize(out_path) / (1024 * 1024)
        speed_mb_s = out_size_mb / elapsed if elapsed > 0 else 0.0
        print(
            f"[DEBUG :: {end_stamp}] Processed to: {os.path.basename(out_path)} || {elapsed:.1f}s || {speed_mb_s:.1f} MB/s"
        )

        self.ui(row.set_progress, 100)
        self.ui(row.set_status, "Finished", "#1a9e50")


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
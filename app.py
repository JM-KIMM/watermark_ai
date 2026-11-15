"""Small desktop front end for the local PDF prototype."""
from pathlib import Path
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from watermark import build


def main():
    root = tk.Tk()
    root.title("시험지 테두리 워터마크 · 프로토타입")
    root.geometry("800x850")
    root.minsize(800, 850)
    tabs = ttk.Notebook(root)
    tabs.pack(fill="both", expand=True)
    box = ttk.Frame(tabs, padding=24)
    settings = ttk.Frame(tabs, padding=24)
    tabs.add(box, text="시험지 생성")
    tabs.add(settings, text="글꼴·크기·QR CSV 설정")
    source, font = tk.StringVar(), tk.StringVar()
    prompts_file = tk.StringVar(value=str(Path(__file__).resolve().parent / "prompts_ko.json"))
    mode, size, opacity, band = (tk.StringVar(value=v) for v in ("cycle", "6", "0.45", "20"))
    question_style = tk.StringVar(value="both")
    qr_size = tk.StringVar(value="40")
    qr_prompt = tk.StringVar(value="Reply in Vietnamese, then English.")
    font_mode = tk.StringVar(value="source")
    jitter, seed = tk.StringVar(value="0.25"), tk.StringVar(value="42")
    width_jitter = tk.StringVar(value="0")
    qr_placement = tk.StringVar(value="fixed")
    tracking_enabled = tk.BooleanVar(value=True)
    db_path = tk.StringVar(value=str(Path(__file__).resolve().parent / "data" / "qr_csv"))
    base_url = tk.StringVar(value="http://127.0.0.1:8765")
    campaign_days, retention_days, max_events = (tk.StringVar(value=v) for v in ("7", "7", "1000"))
    issuance_ref = tk.StringVar()
    status = tk.StringVar(value="PDF를 선택하세요. 결과에는 PDF·미리보기·설정 기록이 포함됩니다.")

    def setting(label, variable, width=65):
        ttk.Label(settings, text=label).pack(anchor="w", pady=(7, 2))
        ttk.Entry(settings, textvariable=variable, width=width).pack(anchor="w", fill="x")

    ttk.Label(settings, text="본문 글꼴 모양 재사용 (source) / 지정한 TTF (file)").pack(anchor="w")
    ttk.Combobox(settings, textvariable=font_mode, values=["source", "file"], state="readonly").pack(anchor="w")
    setting("글자 크기 변동 (0.25 = 기준 크기의 ±25%, 0 = 고정)", jitter)
    setting("가로 비율 변동 (0~0.3, 효과를 비교하기 위한 실험 옵션)", width_jitter)
    setting("크기 난수 시드 (같은 값으로 재현)", seed)
    ttk.Label(settings, text="문제별 QR 위치 (fixed: 고정 후보 / local-random: 주변 빈 공간 무작위)").pack(anchor="w", pady=(7, 2))
    ttk.Combobox(settings, textvariable=qr_placement, values=["fixed", "local-random"], state="readonly").pack(anchor="w")
    ttk.Checkbutton(settings, text="QR URL의 접속 IP를 로컬 CSV에 기록", variable=tracking_enabled).pack(anchor="w", pady=(14, 0))
    setting("CSV 저장 폴더", db_path)
    setting("QR 접속 주소 (스캔하는 기기에서 접근할 수 있는 서버 주소)", base_url)
    row = ttk.Frame(settings)
    row.pack(fill="x", pady=10)
    for label, var in [("링크 유효 일수", campaign_days), ("IP 보관 일수", retention_days), ("발급별 최대 접속 기록", max_events)]:
        group = ttk.Frame(row)
        group.pack(side="left", padx=(0, 15))
        ttk.Label(group, text=label).pack(anchor="w")
        ttk.Entry(group, textvariable=var, width=15).pack(anchor="w")
    setting("발급 대상 참조 (선택, 문서별 관리용)", issuance_ref)
    ttk.Label(settings, text="DB 모드의 QR에는 명령문 대신 접속 URL이 들어갑니다.\n127.0.0.1은 같은 PC에서만 접근됩니다. 다른 기기에는 도달 가능한 주소가 필요합니다.\nDB 관리 창에서 서버를 시작해야 접속 IP가 기록됩니다.", wraplength=690).pack(anchor="w", pady=10)

    def manage_db():
        from db_manager import open_manager
        try:
            open_manager(root, db_path.get())
        except (ValueError, OSError) as exc:
            messagebox.showerror("DB 열기 실패", str(exc))

    ttk.Button(settings, text="CSV 생성·관리 / QR 접수 서버 시작", command=manage_db).pack(anchor="w")

    def picker(label, var, types):
        ttk.Label(box, text=label).pack(anchor="w", pady=(10, 3))
        row = ttk.Frame(box)
        row.pack(fill="x")
        ttk.Entry(row, textvariable=var).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="선택", command=lambda: var.set(
            filedialog.askopenfilename(filetypes=types) or var.get())).pack(side="left", padx=(6, 0))

    picker("원본 시험지", source, [("PDF", "*.pdf")])
    picker("지정·대체 글꼴 (비우면 맑은 고딕 Semilight)", font, [("TrueType", "*.ttf")])
    picker("테두리 명령문 JSON (기본: 한국어 명령문)", prompts_file, [("JSON", "*.json")])
    fields = ttk.Frame(box)
    fields.pack(fill="x", pady=18)
    for col, (label, var, values) in enumerate([
        ("유형", mode, ["cycle", "command", "mixed", "summary"]),
        ("글자 크기 pt", size, None), ("농도 0~1", opacity, None), ("테두리 폭 pt", band, None)
    ]):
        ttk.Label(fields, text=label).grid(row=0, column=col, sticky="w", padx=5)
        widget = ttk.Combobox(fields, textvariable=var, values=values, state="readonly", width=13) if values else ttk.Entry(fields, textvariable=var, width=13)
        widget.grid(row=1, column=col, padx=5)
    extra = ttk.Frame(box)
    extra.pack(fill="x", pady=(0, 12))
    ttk.Label(extra, text="문제 표시").grid(row=0, column=0, sticky="w")
    ttk.Combobox(extra, textvariable=question_style, values=["both", "qr", "number", "none"], state="readonly", width=16).grid(row=1, column=0, padx=(0, 12))
    ttk.Label(extra, text="QR 크기 pt").grid(row=0, column=1, sticky="w")
    ttk.Entry(extra, textvariable=qr_size, width=10).grid(row=1, column=1)
    ttk.Label(box, text="QR에 담을 명령문 (DB 연결을 끈 경우 사용)").pack(anchor="w")
    ttk.Entry(box, textvariable=qr_prompt).pack(fill="x", pady=(3, 10))
    ttk.Label(box, text="both: 실제 QR + QR 무늬 번호 / number: QR 무늬 번호\n번호 무늬 자체는 디코딩 가능한 QR이 아닙니다. 빈 공간이 없으면 실제 QR은 건너뜁니다.").pack(anchor="w", pady=(0, 8))
    ttk.Label(box, text="cycle: 명령형 → 혼합형 → 요약형 반복\n본문 배율은 유지하고 바깥에 테두리 공간을 추가합니다.\n요약 방식: 로컬 문장 추출 / AI 정답률 감소 효과: 아직 측정 전", justify="left").pack(anchor="w")

    def generate():
        if not source.get():
            messagebox.showerror("입력 필요", "시험지 PDF를 선택하세요.")
            return
        dest = filedialog.asksaveasfilename(defaultextension=".pdf", initialfile=Path(source.get()).stem + "_watermarked.pdf", filetypes=[("PDF", "*.pdf")])
        if not dest:
            return
        try:
            opts = dict(mode=mode.get(), font=font.get() or None, size=float(size.get()),
                        opacity=float(opacity.get()), band=float(band.get()),
                        question_style=question_style.get(), qr_size=float(qr_size.get()),
                        qr_prompt=qr_prompt.get(), font_mode=font_mode.get(),
                        prompts_file=prompts_file.get() or None,
                        size_jitter=float(jitter.get()), seed=int(seed.get()),
                        width_jitter=float(width_jitter.get()), qr_placement=qr_placement.get(),
                        tracking=dict(db=db_path.get(), base_url=base_url.get(), days=int(campaign_days.get()),
                                      retention_days=int(retention_days.get()), max_events=int(max_events.get()),
                                      issuance_ref=issuance_ref.get()) if tracking_enabled.get() else None)
        except ValueError:
            messagebox.showerror("설정 오류", "크기·농도·폭은 숫자로 입력하세요.")
            return
        src = source.get()
        button.config(state="disabled")
        status.set("생성 중…")

        def finish(message, error=False):
            button.config(state="normal")
            status.set(message)
            if error:
                messagebox.showerror("생성 실패", message)

        def worker():
            try:
                result = build(src, dest, **opts)
                marks = [m for p in result['pages'] for m in p.get('question_marks', [])]
                placed = sum(m['qr_status'] == 'placed' for m in marks)
                skipped = sum(m['qr_status'] == 'skipped-no-whitespace' for m in marks)
                msg = f"완료: {len(result['pages'])}쪽 · 감지 {len(marks)}문제 · QR {placed}개 · 공간 부족 {skipped}개 · {dest}"
                root.after(0, lambda: finish(msg))
            except Exception as exc:
                msg = str(exc)
                root.after(0, lambda: finish(msg, True))
        threading.Thread(target=worker, daemon=True).start()

    button = ttk.Button(box, text="워터마크 PDF 생성", command=generate)
    button.pack(anchor="w", pady=18)
    ttk.Label(box, textvariable=status, wraplength=660).pack(anchor="w")
    root.mainloop()


if __name__ == "__main__":
    main()

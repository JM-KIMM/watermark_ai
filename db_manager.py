# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 JM-KIMM and contributors.
"""Local desktop management; no network-accessible administrative API."""
from pathlib import Path
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from tracking_db import open_store, create_server, stamp
from csv_store import export_csv


def open_manager(parent, db_path):
    store = open_store(db_path)
    window = tk.Toplevel(parent)
    window.title("QR 접속 IP / 사건 CSV 관리")
    window.geometry("1100x760")
    main = ttk.Frame(window, padding=12)
    main.pack(fill="both", expand=True)
    ttk.Label(main, text=f"CSV 폴더: {store.path}").pack(anchor="w")
    ttk.Label(main, text="QR 해독만으로 기록되지 않습니다. URL 접속 IP이며, AI·프록시 서버의 IP일 수 있습니다.").pack(anchor="w")
    toolbar = ttk.Frame(main)
    toolbar.pack(fill="x", pady=8)
    host, port = tk.StringVar(value="127.0.0.1"), tk.StringVar(value="8765")
    ttk.Label(toolbar, text="서버 바인딩").pack(side="left")
    ttk.Entry(toolbar, textvariable=host, width=16).pack(side="left", padx=5)
    ttk.Entry(toolbar, textvariable=port, width=7).pack(side="left", padx=5)
    server = None
    status = tk.StringVar(value="서버 중지 · 목록은 새로고침으로 갱신")

    def stop():
        nonlocal server
        if server:
            running = server
            server = None
            threading.Thread(target=lambda: (running.shutdown(), running.server_close()), daemon=True).start()
        status.set("서버 중지")

    def start():
        nonlocal server
        if server:
            return
        try:
            server = create_server(store, host.get(), int(port.get()))
        except (ValueError, OSError) as exc:
            messagebox.showerror("서버 시작 실패", str(exc), parent=window)
            return
        threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 1}, daemon=True).start()
        status.set(f"서버 실행: {host.get()}:{server.server_port} · 창을 닫으면 중지")

    ttk.Button(toolbar, text="서버 시작", command=start).pack(side="left", padx=4)
    ttk.Button(toolbar, text="서버 중지", command=stop).pack(side="left", padx=4)
    tabs = ttk.Notebook(main)
    tabs.pack(fill="both", expand=True)

    def table(title, columns):
        frame = ttk.Frame(tabs, padding=8)
        tabs.add(frame, text=title)
        tree = ttk.Treeview(frame, columns=[key for key, _ in columns], show="headings", height=13)
        for key, label in columns:
            tree.heading(key, text=label)
            tree.column(key, width=130, minwidth=55, stretch=True)
        tree.pack(fill="both", expand=True, side="top")
        return frame, tree

    campaign_frame, campaigns = table("QR 발급·만료", [("id", "발급 ID"), ("title", "시험지"),
        ("expires", "링크 만료"), ("active", "활성"), ("issued", "QR 수"), ("issuance_ref", "발급 대상 참조")])
    scan_frame, scans = table("접속 IP", [("id", "기록 ID"), ("timestamp", "접속 시각"), ("ip", "관측 IP"),
        ("campaign_id", "발급 ID"), ("page", "페이지"), ("question", "문제"), ("issuance_ref", "발급 대상 참조")])
    case_frame, cases = table("사건 기록", [("id", "사건 ID"), ("subject_ref", "대상 참조"), ("status", "상태"),
        ("scan_id", "접속 기록 ID"), ("expires", "자동 삭제 예정"), ("notes", "내용")])
    case_id = None
    subject, scan_id, case_status, days = (tk.StringVar(value=v) for v in ("", "", "검토중", "7"))
    row = ttk.Frame(case_frame)
    row.pack(fill="x", pady=8)
    for label, variable, width in [("대상 참조", subject, 22), ("접속 ID (선택)", scan_id, 12), ("보관 일수", days, 7)]:
        ttk.Label(row, text=label).pack(side="left", padx=3)
        ttk.Entry(row, textvariable=variable, width=width).pack(side="left")
    ttk.Combobox(row, textvariable=case_status, values=["검토중", "확인", "기각"], state="readonly", width=10).pack(side="left", padx=8)
    notes = tk.Text(case_frame, height=5, wrap="word")
    notes.pack(fill="x")
    cached_cases = {}

    def refresh():
        try:
            groups = [(campaigns, store.campaigns()), (scans, store.scans()), (cases, store.cases())]
            cached_cases.clear()
            for tree, rows in groups:
                for item in tree.get_children():
                    tree.delete(item)
                for data in rows:
                    if tree is cases:
                        cached_cases[str(data["id"])] = data
                    values = []
                    for key in tree["columns"]:
                        value = data.get(key)
                        values.append(stamp(value) if key in ("expires", "timestamp") else ("" if value is None else value))
                    tree.insert("", "end", iid=str(data["id"]), values=values)
        except Exception as exc:
            messagebox.showerror("DB 오류", str(exc), parent=window)

    def selected(tree):
        return tree.selection()[0] if tree.selection() else None

    def campaign_action(delete=False):
        identifier = selected(campaigns)
        if identifier:
            (store.delete_campaign if delete else store.revoke)(identifier)
            refresh()

    ttk.Button(campaign_frame, text="선택 링크 비활성화", command=campaign_action).pack(side="left", pady=8)
    ttk.Button(campaign_frame, text="선택 발급·접속 기록 삭제", command=lambda: campaign_action(True)).pack(side="left", padx=8)

    def export():
        dest = filedialog.asksaveasfilename(parent=window, defaultextension=".csv", initialfile="qr_access.csv", filetypes=[("CSV", "*.csv")])
        if dest:
            rows = [dict(row, timestamp=stamp(row["timestamp"])) for row in store.scans(10000)]
            export_csv(dest, rows)

    ttk.Button(scan_frame, text="접속 기록 CSV 내보내기", command=export).pack(side="left", pady=8)

    def new_case():
        nonlocal case_id
        case_id = None
        subject.set(""); scan_id.set(""); case_status.set("검토중"); days.set("7")
        notes.delete("1.0", "end")

    def load_case():
        nonlocal case_id
        data = cached_cases.get(selected(cases))
        if data:
            case_id = data["id"]
            subject.set(data["subject_ref"])
            scan_id.set(data["scan_id"] or "")
            case_status.set(data["status"])
            notes.delete("1.0", "end"); notes.insert("1.0", data["notes"])

    def save_case():
        try:
            store.save_case(subject.get(), notes.get("1.0", "end").strip(), status=case_status.get(),
                            scan_id=int(scan_id.get()) if scan_id.get().strip() else None,
                            days=int(days.get()), case_id=case_id)
            refresh(); new_case()
        except (ValueError, OSError) as exc:
            messagebox.showerror("사건 저장 실패", str(exc), parent=window)

    def delete_case():
        identifier = selected(cases)
        if identifier:
            store.delete_case(int(identifier)); refresh(); new_case()

    actions = ttk.Frame(case_frame)
    actions.pack(fill="x", pady=8)
    for label, callback in [("새 사건", new_case), ("선택 사건 불러오기", load_case), ("저장", save_case), ("선택 사건 삭제", delete_case)]:
        ttk.Button(actions, text=label, command=callback).pack(side="left", padx=3)
    footer = ttk.Frame(main)
    footer.pack(fill="x", pady=8)
    ttk.Button(footer, text="새로고침·기한 지난 기록 정리", command=refresh).pack(side="left")
    ttk.Label(footer, textvariable=status).pack(side="left", padx=10)

    def close():
        stop()
        window.destroy()

    window.protocol("WM_DELETE_WINDOW", close)
    refresh()
    return window


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="로컬 QR 접속 IP·사건 DB 관리")
    parser.add_argument("--db", default=str(Path(__file__).resolve().parent/"data"/"qr_csv"))
    args = parser.parse_args()
    root = tk.Tk()
    root.withdraw()
    window = open_manager(root, args.db)
    window.bind("<Destroy>", lambda event: root.destroy() if event.widget is window else None)
    root.mainloop()

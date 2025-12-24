import sys
import os
import time
import ctypes
import cv2
import numpy as np
import tkinter as tk
from tkinter import ttk, messagebox
from ctypes import wintypes
from unittest.mock import MagicMock

# ==========================================
# 1. 模擬環境與載入 Driver
# ==========================================
if 'core' not in sys.modules:
    mock_core = MagicMock()
    mock_interfaces = MagicMock()
    class MockCaptureController: pass
    mock_interfaces.CaptureController = MockCaptureController
    sys.modules['core'] = mock_core
    sys.modules['core.interfaces'] = mock_interfaces

try:
    sys.path.append(os.getcwd())
    # 匯入原始 Driver
    from wgc_driver import WGCDriver
except ImportError:
    print("❌ 找不到 wgc_driver.py，請確認檔案位置！")
    sys.exit(1)

# ==========================================
# 2. 客製化 Driver (支援手動設定 ROI 與還原視窗)
# ==========================================
class FPS_WGCDriver(WGCDriver):
    """
    繼承原始 Driver，並覆寫初始化邏輯，
    讓我們可以手動指定「全螢幕」或「中心裁切」。
    """
    def __init__(self, crop_mode="FULL", crop_w=640, crop_h=640):
        self.custom_mode = crop_mode # 'FULL' or 'CENTER'
        self.target_crop_w = crop_w
        self.target_crop_h = crop_h
        super().__init__()

    def _initialize_wgc(self):
        """
        覆寫原本的初始化邏輯，強制套用 UI 設定的解析度
        並加入防止讀取到最小化尺寸的機制
        """
        if not self.hwnd:
            return False

        # 1. 嘗試獲取視窗實際大小 (加入簡單的重試機制)
        rect = wintypes.RECT()
        win_w, win_h = 0, 0
        
        # 嘗試最多 3 次，防止剛剛還原視窗時讀到舊數據
        for i in range(3):
            ctypes.windll.user32.GetWindowRect(self.hwnd, ctypes.byref(rect))
            win_w = rect.right - rect.left
            win_h = rect.bottom - rect.top
            # 如果寬度大於 200，通常表示視窗已正常展開
            if win_w > 200 and win_h > 100:
                break
            time.sleep(0.1)
        
        # 如果還是讀到奇怪的數值 (例如 160x28)，則報錯
        if win_w <= 160 or win_h <= 40: 
            print(f"[WGC] Error: 偵測到視窗尺寸異常 ({win_w}x{win_h})，視窗可能仍處於最小化或隱藏狀態。")
            return False
        
        # 2. 根據模式計算 ROI
        if self.custom_mode == "CENTER":
            # FPS 模式：只取中心
            # 確保裁切框不會比視窗還大
            valid_crop_w = min(win_w, self.target_crop_w)
            valid_crop_h = min(win_h, self.target_crop_h)
            
            self.roi_w = valid_crop_w
            self.roi_h = valid_crop_h
            self.roi_x = (win_w - self.roi_w) // 2
            self.roi_y = (win_h - self.roi_h) // 2
        else:
            # 全螢幕模式
            self.roi_w = win_w
            self.roi_h = win_h
            self.roi_x = 0
            self.roi_y = 0

        print(f"[WGC] 初始化模式: {self.custom_mode}")
        print(f"[WGC] 視窗尺寸: {win_w}x{win_h}")
        print(f"[WGC] 最終 ROI: {self.roi_w}x{self.roi_h} at ({self.roi_x},{self.roi_y})")
        
        # 3. 呼叫 C++ DLL
        if not self.lib:
            print("[WGC] Error: DLL not loaded")
            return False

        if self.lib.InitCapture(self.hwnd, self.roi_x, self.roi_y, self.roi_w, self.roi_h):
            self.is_initialized = True
            self.buffer_size = self.roi_w * self.roi_h * 4
            self.buffer = (ctypes.c_uint8 * self.buffer_size)()
            time.sleep(0.2) # WGC 暖機稍微加長一點
            return True
        return False

# ==========================================
# 3. 視窗列表工具
# ==========================================
def get_window_list():
    user32 = ctypes.windll.user32
    windows = []
    def enum_handler(hwnd, ctx):
        if user32.IsWindowVisible(hwnd):
            length = user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buff = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buff, length + 1)
                title = buff.value
                
                # 取得 PID
                pid = ctypes.c_ulong()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                
                # 過濾掉 Program Manager 等系統視窗
                if title != "Program Manager":
                    windows.append((hwnd, pid.value, title))
        return True
    user32.EnumWindows(ctypes.CFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)(enum_handler), 0)
    return sorted(windows, key=lambda x: x[2])

# ==========================================
# 4. Tkinter UI 主程式
# ==========================================
class WGCDemoApp:
    def __init__(self, root):
        self.root = root
        self.root.title("WGC FPS 極速截圖測試")
        self.root.geometry("450x420")
        
        # 樣式設定
        style = ttk.Style()
        style.configure("TButton", font=("Arial", 10))
        style.configure("TLabel", font=("Arial", 10))
        
        # --- 1. 視窗選擇區 ---
        frame_win = ttk.LabelFrame(root, text="1. 選擇目標視窗 (PID Selection)", padding=10)
        frame_win.pack(fill="x", padx=10, pady=5)
        
        self.win_list = []
        self.combo_var = tk.StringVar()
        self.combo = ttk.Combobox(frame_win, textvariable=self.combo_var, state="readonly")
        self.combo.pack(fill="x", pady=5)
        
        btn_refresh = ttk.Button(frame_win, text="🔄 刷新視窗清單", command=self.refresh_windows)
        btn_refresh.pack(fill="x")

        # --- 2. 模式設定區 ---
        frame_mode = ttk.LabelFrame(root, text="2. 截圖模式 (FPS Mode)", padding=10)
        frame_mode.pack(fill="x", padx=10, pady=5)
        
        self.mode_var = tk.StringVar(value="CENTER")
        
        # Radio Buttons
        r1 = ttk.Radiobutton(frame_mode, text="🎯 FPS 戰術模式 (中心裁切)", variable=self.mode_var, value="CENTER", command=self.toggle_entries)
        r2 = ttk.Radiobutton(frame_mode, text="📺 全螢幕監控", variable=self.mode_var, value="FULL", command=self.toggle_entries)
        r1.pack(anchor="w")
        r2.pack(anchor="w")
        
        # Resolution Inputs
        frame_res = ttk.Frame(frame_mode)
        frame_res.pack(fill="x", pady=5)
        
        ttk.Label(frame_res, text="寬度:").pack(side="left")
        self.entry_w = ttk.Entry(frame_res, width=6)
        self.entry_w.insert(0, "640")
        self.entry_w.pack(side="left", padx=5)
        
        ttk.Label(frame_res, text="高度:").pack(side="left")
        self.entry_h = ttk.Entry(frame_res, width=6)
        self.entry_h.insert(0, "640")
        self.entry_h.pack(side="left", padx=5)
        
        ttk.Label(frame_res, text="(僅 FPS 模式有效)").pack(side="left", padx=5)

        # --- 3. 啟動區 ---
        frame_action = ttk.Frame(root, padding=10)
        frame_action.pack(fill="x", pady=5)
        
        btn_start = ttk.Button(frame_action, text="🚀 啟動 OpenCV 預覽", command=self.start_capture)
        btn_start.pack(fill="x", ipady=5)
        
        lbl_tip = ttk.Label(root, text="若目標視窗最小化，將自動嘗試還原。", foreground="gray", font=("Arial", 9))
        lbl_tip.pack(pady=2)

        # 初始化
        self.refresh_windows()

    def toggle_entries(self):
        state = "normal" if self.mode_var.get() == "CENTER" else "disabled"
        self.entry_w.config(state=state)
        self.entry_h.config(state=state)

    def refresh_windows(self):
        self.win_list = get_window_list()
        values = []
        default_idx = 0
        
        for i, (hwnd, pid, title) in enumerate(self.win_list):
            display_text = f"[{pid}] {title}"
            values.append(display_text)
            if "Discord" in title or "Chrome" in title or "Game" in title:
                default_idx = i
                
        self.combo['values'] = values
        if values:
            self.combo.current(default_idx)

    def force_restore_window(self, hwnd):
        """
        檢查並還原被最小化的視窗
        """
        user32 = ctypes.windll.user32
        
        # 檢查是否最小化 (IsIconic 回傳非 0 表示最小化)
        if user32.IsIconic(hwnd):
            print(f"[System] 偵測到視窗 (HWND: {hwnd}) 處於最小化狀態，正在還原...")
            # SW_RESTORE = 9
            user32.ShowWindow(hwnd, 9)
            
            # 嘗試將其移至最前 (Optional)
            user32.SetForegroundWindow(hwnd)
            
            # 重要：給予 Windows 動畫時間，否則 GetWindowRect 還是會抓到舊數值
            time.sleep(0.5)
            return True
        return False

    def start_capture(self):
        idx = self.combo.current()
        if idx == -1:
            messagebox.showwarning("提示", "請先選擇一個視窗！")
            return
            
        hwnd, pid, title = self.win_list[idx]
        
        # 1. 檢查並還原視窗
        self.force_restore_window(hwnd)

        # 讀取設定
        mode = self.mode_var.get()
        try:
            cw = int(self.entry_w.get())
            ch = int(self.entry_h.get())
        except:
            cw, ch = 640, 640

        # 2. 初始化 Driver
        driver = FPS_WGCDriver(crop_mode=mode, crop_w=cw, crop_h=ch)
        
        print(f"嘗試連接: {title} (HWND: {hwnd})")
        if not driver.init_session(hwnd, "window"):
            messagebox.showerror("錯誤", "WGC Session 綁定失敗。")
            return

        # 3. 底層初始化 (此時視窗應該已經恢復正常大小)
        if not driver._initialize_wgc():
            messagebox.showerror("錯誤", 
                "WGC 初始化失敗！\n\n可能原因：\n1. 視窗未能成功還原\n2. 視窗權限受限 (例如管理員權限)\n3. 視窗實際上不可見")
            return

        # 隱藏主視窗
        self.root.withdraw()
        
        # 進入 OpenCV 迴圈
        self.run_opencv_loop(driver, title, mode)
        
        # 結束後釋放並顯示主視窗
        driver.release()
        self.root.deiconify()

    def run_opencv_loop(self, driver, title, mode):
        win_name = f"FPS Monitor - {title}"
        cv2.namedWindow(win_name, cv2.WINDOW_NORMAL)
        
        # 防呆：避免 crash
        safe_w = max(driver.roi_w, 200)
        safe_h = max(driver.roi_h, 100)

        if mode == "FULL":
            cv2.resizeWindow(win_name, 1280, 720)
        else:
            cv2.resizeWindow(win_name, safe_w, safe_h)

        prev_time = time.time()
        fps_history = []
        
        # 預備背景
        bg_wait = np.zeros((safe_h, safe_w, 3), dtype=np.uint8)
        cv2.putText(bg_wait, "WAITING...", (safe_w//2 - 60, safe_h//2), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)

        try:
            while True:
                curr_time = time.time()
                pil_img = driver.capture()
                
                if pil_img is not None:
                    # 轉 OpenCV (最速路徑)
                    frame = cv2.cvtColor(np.asarray(pil_img), cv2.COLOR_RGB2BGR)
                    
                    # --- 繪製 FPS ---
                    dt = curr_time - prev_time
                    prev_time = curr_time
                    fps = 1.0 / dt if dt > 0 else 0
                    fps_history.append(fps)
                    if len(fps_history) > 30: fps_history.pop(0)
                    avg_fps = sum(fps_history) / len(fps_history)
                    
                    cv2.putText(frame, f"FPS: {avg_fps:.1f}", (10, 30), 
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                    
                    # --- 繪製準心 ---
                    h, w = frame.shape[:2]
                    cx, cy = w // 2, h // 2
                    
                    cv2.line(frame, (cx - 20, cy), (cx + 20, cy), (0, 255, 0), 2)
                    cv2.line(frame, (cx, cy - 20), (cx, cy + 20), (0, 255, 0), 2)
                    
                    cv2.imshow(win_name, frame)
                else:
                    cv2.imshow(win_name, bg_wait)
                    time.sleep(0.01)

                # 按 Q 離開
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
                    
        except KeyboardInterrupt:
            pass
        finally:
            cv2.destroyAllWindows()

if __name__ == "__main__":
    root = tk.Tk()
    app = WGCDemoApp(root)
    root.mainloop()
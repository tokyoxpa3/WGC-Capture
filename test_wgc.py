import ctypes
from ctypes import wintypes
import numpy as np
import cv2
import time
import psutil

# 定義 WINDOWPLACEMENT 結構體
class WINDOWPLACEMENT(ctypes.Structure):
    _fields_ = [
        ('length', wintypes.UINT),
        ('flags', wintypes.UINT),
        ('showCmd', wintypes.UINT),
        ('ptMinPosition', wintypes.POINT),
        ('ptMaxPosition', wintypes.POINT),
        ('rcNormalPosition', wintypes.RECT),
    ]

# 設定 DPI 感知 (這非常重要，否則截圖只會截到一部分或解析度錯誤)
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    ctypes.windll.user32.SetProcessDPIAware()

# 載入 DLL
wgc_lib = ctypes.CDLL('./x64/Release/Wgc.dll')

# 定義函數參數
wgc_lib.CaptureWindow.argtypes = [
    wintypes.HWND,
    ctypes.POINTER(ctypes.c_uint8),
    ctypes.c_int,
    ctypes.c_int
]
wgc_lib.CaptureWindow.restype = ctypes.c_bool

def get_window_rect(hwnd):
    rect = wintypes.RECT()
    # 使用 DwmGetWindowAttribute 可能比 GetWindowRect 更準確 (排除陰影)
    # 但為了簡單，先用 GetWindowRect，若有黑邊再調整
    ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
    w = rect.right - rect.left
    h = rect.bottom - rect.top
    return w, h

def capture_window(hwnd):
    width, height = get_window_rect(hwnd)
    if width <= 10 or height <= 10: # 過濾無效大小
        print(f"Skipping capture: Window too small ({width}x{height})")
        return None

    # 分配 Buffer (BGRA)
    size = width * height * 4
    buffer = (ctypes.c_uint8 * size)()
    
    print(f"Attempting capture -> HWND: {hwnd}, Size: {width}x{height}")
    
    # 記錄時間
    start_time = time.time()
    success = wgc_lib.CaptureWindow(hwnd, buffer, width, height)
    end_time = time.time()
    
    if success:
        print(f"Capture success! Time taken: {end_time - start_time:.4f}s")
        image_data = np.ctypeslib.as_array(buffer).reshape(height, width, 4)
        return image_data
    else:
        print(f"Capture failed. (Time taken: {end_time - start_time:.4f}s)")
        print("Possible reasons: Window minimized, window not updating, or DLL error.")
        return None

def find_best_window(process_name):
    """
    找到該進程下「面積最大」且「可見」的視窗
    """
    candidates = []

    def enum_windows_proc(hwnd, lParam):
        if ctypes.windll.user32.IsWindowVisible(hwnd):
            pid = wintypes.DWORD()
            ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            try:
                proc = psutil.Process(pid.value)
                if proc.name().lower() == process_name.lower():
                    # 獲取標題
                    length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
                    buff = ctypes.create_unicode_buffer(length + 1)
                    ctypes.windll.user32.GetWindowTextW(hwnd, buff, length + 1)
                    title = buff.value
                    
                    # 獲取尺寸
                    w, h = get_window_rect(hwnd)
                    area = w * h
                    
                    # 只有當尺寸大於一定程度才視為有效候選 (例如 100x100)
                    if area > 10000: 
                        candidates.append((area, hwnd, title, w, h))
            except:
                pass
        return True

    ctypes.windll.user32.EnumWindows(ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)(enum_windows_proc), 0)

    if not candidates:
        return None

    # 根據面積排序，最大的排前面
    candidates.sort(key=lambda x: x[0], reverse=True)
    
    print(f"Found {len(candidates)} candidate windows for {process_name}:")
    for area, hwnd, title, w, h in candidates:
        print(f" - HWND: {hwnd}, Size: {w}x{h}, Title: '{title}'")

    # 返回最大的那個
    return candidates[0][1]

if __name__ == "__main__":
    process_name = "MHClient-Connect.exe" # 請確認這是遊戲主程式，而非啟動器
    # 有些遊戲啟動器叫 xxx.exe，但實際遊戲視窗是另一個 xxx-Shipping.exe
    
    print(f"Searching for windows of: {process_name}")
    hwnd = find_best_window(process_name)

    if hwnd:
        # 如果視窗是最小化的，WGC 捕捉會暫停或黑屏
        # 這裡嘗試還原視窗 (若需要)
        placement = WINDOWPLACEMENT()
        placement.length = ctypes.sizeof(WINDOWPLACEMENT)
        ctypes.windll.user32.GetWindowPlacement(hwnd, ctypes.byref(placement))
        if placement.showCmd == 2: # SW_SHOWMINIMIZED
            print("Window is minimized. Restoring...")
            ctypes.windll.user32.ShowWindow(hwnd, 9) # SW_RESTORE
            time.sleep(0.5) # 等待還原動畫

        img = capture_window(hwnd)
        if img is not None:
            # 顯示結果
            cv2.imshow("Result", img)
            cv2.waitKey(0)
            cv2.destroyAllWindows()
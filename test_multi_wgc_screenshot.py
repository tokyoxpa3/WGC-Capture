import ctypes
from ctypes import wintypes
import numpy as np
import cv2
import time
import psutil
from concurrent.futures import ThreadPoolExecutor, as_completed

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
    
    # 使用 WGC 方法進行截圖
    start_time = time.time()
    success = wgc_lib.CaptureWindow(hwnd, buffer, width, height)
    end_time = time.time()
    
    if success:
        print(f"Capture success! Time taken: {end_time - start_time:.4f}s")
        image_data = np.ctypeslib.as_array(buffer).reshape(height, width, 4)
        return image_data
    else:
        print(f"WGC capture failed. (Time taken: {end_time - start_time:.4f}s)")
        print("Possible reasons: Window minimized, window not updating, or DLL error.")
        return None

def find_best_window(process_name):
    """
    找到該進程下最合適的視窗（包括最小化的視窗）
    優先選擇標題包含關鍵字的視窗，如果沒有則選擇面積最大的
    """
    candidates = []

    def enum_windows_proc(hwnd, lParam):
        # 不再檢查 IsWindowVisible，這樣可以找到最小化的視窗
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
                
                # 排除無標題或尺寸極小的視窗 (例如面積 > 100，避免奇怪的隱藏視窗)
                if area > 100:
                    candidates.append((area, hwnd, title, w, h))
        except:
            pass
        return True

    ctypes.windll.user32.EnumWindows(ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)(enum_windows_proc), 0)

    if not candidates:
        return None

    print(f"Found {len(candidates)} candidate windows for {process_name}:")
    for area, hwnd, title, w, h in candidates:
        # 檢查視窗是否最小化
        placement = WINDOWPLACEMENT()
        placement.length = ctypes.sizeof(WINDOWPLACEMENT)
        ctypes.windll.user32.GetWindowPlacement(hwnd, ctypes.byref(placement))
        status = "minimized" if placement.showCmd == 2 else "normal"
        print(f" - HWND: {hwnd}, Size: {w}x{h}, Title: '{title}', Status: {status}")

    # 按優先級排序：
    # 1. 如果標題包含關鍵字（如遊戲名稱），優先選擇
    # 2. 否則選擇面積最大的
    def calculate_priority(item):
        area, hwnd, title, w, h = item
        priority = 0
        
        # 檢查標題是否包含常見的遊戲窗口關鍵字
        title_lower = title.lower()
        if any(keyword in title_lower for keyword in ['墨魂', 'mhclient', 'game', '主視窗', 'window', 'client']):
            priority += 10000  # 給一個很高的優先級
        
        # 添加面積作為次要優先級
        priority += area
        
        return priority

    candidates.sort(key=calculate_priority, reverse=True)
    
    # 返回優先級最高的那個
    return candidates[0][1]

def capture_window_threaded(process_name, output_filename=None):
    """
    多線程截圖函數 - 專門用於在線程中執行截圖操作
    """
    print(f"[Thread] Searching for window: {process_name}")
    hwnd = find_best_window(process_name)
    
    if not hwnd:
        print(f"[Thread] Window not found for {process_name}")
        # 即使找不到視窗也要返回一個結果對象，這樣才能正確統計
        return {
            'process_name': process_name,
            'hwnd': None,
            'image': None,
            'success': False
        }
    
    # 檢查視窗是否最小化並恢復
    placement = WINDOWPLACEMENT()
    placement.length = ctypes.sizeof(WINDOWPLACEMENT)
    ctypes.windll.user32.GetWindowPlacement(hwnd, ctypes.byref(placement))
    
    window_was_minimized = False
    if placement.showCmd == 2:  # SW_SHOWMINIMIZED
        print(f"[Thread] Window {process_name} is minimized. Restoring...")
        ctypes.windll.user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        window_was_minimized = True
        time.sleep(1.0)  # 等待還原動畫，增加等待時間
    elif placement.showCmd == 0:  # SW_HIDE
        print(f"[Thread] Window {process_name} is hidden. Showing...")
        ctypes.windll.user32.ShowWindow(hwnd, 5)  # SW_SHOW
        window_was_minimized = True
        time.sleep(1.0)  # 等待顯示

    print(f"[Thread] Attempting to capture window for {process_name} (HWND: {hwnd})")
    img = capture_window(hwnd)
    
    # 如果視窗原本是最小化的，在截圖完成後恢復最小化狀態
    if window_was_minimized:
        print(f"[Thread] Restoring minimized state for {process_name}")
        ctypes.windll.user32.ShowWindow(hwnd, 6)  # SW_MINIMIZE
        time.sleep(0.2)  # 給系統一點時間來處理
    
    if img is not None and output_filename:
        cv2.imwrite(output_filename, img)
        print(f"[Thread] Screenshot for {process_name} saved as {output_filename}")
    elif img is not None:
        # 如果沒有指定輸出檔案名，生成一個預設名稱
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        filename = f"screenshot_{process_name.replace('.exe', '')}_{timestamp}.png"
        cv2.imwrite(filename, img)
        print(f"[Thread] Screenshot for {process_name} saved as {filename}")
    else:
        print(f"[Thread] Failed to capture window for {process_name}")
    
    return {
        'process_name': process_name,
        'hwnd': hwnd,
        'image': img,
        'success': img is not None
    }

if __name__ == "__main__":
    # 多線程截圖測試
    processes_to_capture = ["MHClient-Connect.exe", "Notepad.exe"]
    
    print("Starting multi-threaded screenshot capture...")
    print(f"Attempting to capture windows for: {', '.join(processes_to_capture)}")
    
    # 使用 ThreadPoolExecutor 進行多線程截圖
    with ThreadPoolExecutor(max_workers=len(processes_to_capture)) as executor:
        # 提交任務到線程池
        future_to_process = {
            executor.submit(capture_window_threaded, proc_name): proc_name 
            for proc_name in processes_to_capture
        }
        
        # 等待所有任務完成
        results = []
        for future in as_completed(future_to_process):
            proc_name = future_to_process[future]
            try:
                result = future.result()
                results.append(result)
                print(f"Completed capture for {proc_name}")
            except Exception as exc:
                print(f"Thread for {proc_name} generated an exception: {exc}")
    
    # 輸出結果摘要
    successful_captures = [r for r in results if r and r['success']]
    failed_captures = [r for r in results if r and not r['success']]
    
    print(f"\n=== Multi-threaded Screenshot Results ===")
    print(f"Total processes attempted: {len(processes_to_capture)}")
    print(f"Successful captures: {len(successful_captures)}")
    print(f"Failed captures: {len(failed_captures)}")
    
    for result in successful_captures:
        if result:
            print(f"- Successfully captured: {result['process_name']} (HWND: {result['hwnd']})")
    
    for result in failed_captures:
        if result:
            print(f"- Failed to capture: {result['process_name']}")

import ctypes
import os
from ctypes import wintypes
import numpy as np
from PIL import Image
import cv2
import time
from core.interfaces import CaptureController

class WGCDriver(CaptureController):
    def __init__(self):
        self.lib = None
        self.hwnd = 0
        self.is_initialized = False
        
        # 預設 ROI (全螢幕)
        self.roi_x = 0
        self.roi_y = 0
        self.roi_w = 0
        self.roi_h = 0
        
        self._load_dll()

    def _load_dll(self):
        dll_path = os.path.join(os.getcwd(), 'libs', 'WGC.dll')
        if not os.path.exists(dll_path):
            raise FileNotFoundError(f"找不到 WGC DLL: {dll_path}")
        self.lib = ctypes.CDLL(dll_path)
        
        # 定義函式原型
        self.lib.InitCapture.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int]
        self.lib.InitCapture.restype = ctypes.c_bool
        
        self.lib.GetLatestFrame.argtypes = [ctypes.POINTER(ctypes.c_uint8), ctypes.c_int]
        self.lib.GetLatestFrame.restype = ctypes.c_bool
        
        # 【關鍵修改】名稱變更為 CleanupCapture
        try:
            self.lib.CleanupCapture.argtypes = []
            self.lib.CleanupCapture.restype = None
        except AttributeError:
            # 如果 DLL 沒重新編譯成功，還是舊名字，這裡做個相容
            print("Warning: Loading old DLL symbol 'ReleaseCapture'")
            self.lib.ReleaseCapture.argtypes = []
            self.lib.ReleaseCapture.restype = None

    def init_session(self, target_id, target_type, *args):
        if target_type == "window":
            self.hwnd = target_id # 簡化邏輯，假設傳入的是 HWND
            return True
        return False

    def _initialize_wgc(self):
        """
        初始化底層 WGC session。
        我們在這裡強制設定 ROI 為 320x320 的中心區域 (如果需要的話)。
        或者預設全螢幕。
        """
        # 獲取視窗尺寸
        rect = wintypes.RECT()
        ctypes.windll.user32.GetWindowRect(self.hwnd, ctypes.byref(rect))
        w = rect.right - rect.left
        h = rect.bottom - rect.top
        
        if w <= 0 or h <= 0: return False
        
        # --- 設定裁切策略 (可根據需求修改) ---
        # 策略：如果解析度大於 1080p，或者是為了 AimBot，我們只截中心 640x640
        CROP_SIZE = 640
        if w > CROP_SIZE and h > CROP_SIZE:
            self.roi_w = CROP_SIZE
            self.roi_h = CROP_SIZE
            self.roi_x = (w - CROP_SIZE) // 2
            self.roi_y = (h - CROP_SIZE) // 2
        else:
            self.roi_w = w
            self.roi_h = h
            self.roi_x = 0
            self.roi_y = 0
            
        print(f"[WGC] 初始化 ROI: {self.roi_w}x{self.roi_h} at ({self.roi_x},{self.roi_y})")
        
        # 呼叫 C++ 初始化
        if self.lib.InitCapture(self.hwnd, self.roi_x, self.roi_y, self.roi_w, self.roi_h):
            self.is_initialized = True
            # 預先分配緩衝區 (重複使用，避免 malloc)
            self.buffer_size = self.roi_w * self.roi_h * 4
            self.buffer = (ctypes.c_uint8 * self.buffer_size)()
            time.sleep(0.1) # 等待 WGC 暖機
            return True
        return False

    def capture(self):
        # Lazy Init
        if not self.is_initialized:
            if not self._initialize_wgc():
                return None

        # 極速獲取
        if self.lib.GetLatestFrame(self.buffer, self.buffer_size):
            try:
                # 這裡的 copy 是必須的，因為 buffer 是共用的
                # 但因為我們已經 crop 過了 (例如 640x640)，這個 copy 很快
                raw = bytes(self.buffer)
                
                # 轉 PIL
                # 注意：這裡回傳的是 BGRA，需要轉 RGB
                # 使用 numpy + cv2 是最快的路徑
                arr = np.frombuffer(raw, dtype=np.uint8).reshape(self.roi_h, self.roi_w, 4)
                
                # BGR -> RGB (OpenCV 很快)
                # 這裡我們只取前3個通道 (RGB)，丟棄 Alpha
                rgb_arr = arr[..., [2, 1, 0]] 
                
                return Image.fromarray(rgb_arr)
                
            except Exception as e:
                print(f"Capture Error: {e}")
                return None
        return None

    def release(self):
        if self.is_initialized:
            # 【關鍵修改】呼叫新名稱
            if hasattr(self.lib, 'CleanupCapture'):
                self.lib.CleanupCapture()
            else:
                self.lib.ReleaseCapture()
            self.is_initialized = False